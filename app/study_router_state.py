from __future__ import annotations

import atexit
import json
import logging
import math
import os
import queue
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, SQLModel, Session, create_engine, select

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persistent schema
# ---------------------------------------------------------------------------

class StudyAIModelState(SQLModel, table=True):
    """Persistent health/quota state for one provider+model target.

    No prompts, answers, patient data or note contents are stored here. The row
    only contains operational metadata needed to avoid slow blind fallback.
    """

    __tablename__ = "studyaimodelstate"
    __table_args__ = (
        UniqueConstraint("provider", "model", name="uq_study_ai_model_state_target"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    model: str = Field(index=True)

    day_key: str = ""
    day_requests: int = 0
    day_generation_requests: int = 0
    day_embedding_requests: int = 0
    month_key: str = ""
    month_requests: int = 0

    total_requests: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_429: int = 0
    total_prompt_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0

    consecutive_failures: int = 0
    circuit_open_until: Optional[datetime] = None
    last_status_code: Optional[int] = None
    last_error_kind: Optional[str] = None

    last_latency_ms: int = 0
    ewma_latency_ms: float = 0.0

    provider_limit_requests: Optional[int] = None
    provider_remaining_requests: Optional[int] = None
    provider_limit_tokens: Optional[int] = None
    provider_remaining_tokens: Optional[int] = None
    provider_reset_at: Optional[datetime] = None
    quota_source: str = "observed"

    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StudyAIProviderState(SQLModel, table=True):
    """Provider-wide circuit used for key/auth or known shared-quota failures."""

    __tablename__ = "studyaiproviderstate"
    __table_args__ = (
        UniqueConstraint("provider", name="uq_study_ai_provider_state_provider"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    day_key: str = ""
    day_requests: int = 0
    month_key: str = ""
    month_requests: int = 0
    total_requests: int = 0
    total_429: int = 0
    provider_limit_requests: Optional[int] = None
    provider_remaining_requests: Optional[int] = None
    provider_limit_tokens: Optional[int] = None
    provider_remaining_tokens: Optional[int] = None
    provider_reset_at: Optional[datetime] = None
    quota_source: str = "observed"
    consecutive_failures: int = 0
    circuit_open_until: Optional[datetime] = None
    last_status_code: Optional[int] = None
    last_error_kind: Optional[str] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StudyAIUsageEvent(SQLModel, table=True):
    """Small audit row for quota/latency accounting; contains no conversation text."""

    __tablename__ = "studyausageevent"

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    model: str = Field(index=True)
    operation: str = Field(index=True)
    success: bool = Field(index=True)
    status_code: Optional[int] = Field(default=None, index=True)
    latency_ms: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    error_kind: Optional[str] = None
    quota_source: str = "observed"
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# In-memory hot state
# ---------------------------------------------------------------------------

@dataclass
class _TargetMemory:
    provider: str
    model: str
    day_key: str = ""
    day_requests: int = 0
    day_generation_requests: int = 0
    day_embedding_requests: int = 0
    month_key: str = ""
    month_requests: int = 0
    total_requests: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_429: int = 0
    total_prompt_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    consecutive_failures: int = 0
    circuit_open_until_epoch: float = 0.0
    last_status_code: Optional[int] = None
    last_error_kind: Optional[str] = None
    last_latency_ms: int = 0
    ewma_latency_ms: float = 0.0
    provider_limit_requests: Optional[int] = None
    provider_remaining_requests: Optional[int] = None
    provider_limit_tokens: Optional[int] = None
    provider_remaining_tokens: Optional[int] = None
    provider_reset_at_epoch: float = 0.0
    quota_source: str = "observed"
    last_success_at_epoch: float = 0.0
    last_failure_at_epoch: float = 0.0
    updated_at_epoch: float = 0.0


@dataclass
class _ProviderMemory:
    provider: str
    day_key: str = ""
    day_requests: int = 0
    month_key: str = ""
    month_requests: int = 0
    total_requests: int = 0
    total_429: int = 0
    provider_limit_requests: Optional[int] = None
    provider_remaining_requests: Optional[int] = None
    provider_limit_tokens: Optional[int] = None
    provider_remaining_tokens: Optional[int] = None
    provider_reset_at_epoch: float = 0.0
    quota_source: str = "observed"
    consecutive_failures: int = 0
    circuit_open_until_epoch: float = 0.0
    last_status_code: Optional[int] = None
    last_error_kind: Optional[str] = None
    last_success_at_epoch: float = 0.0
    last_failure_at_epoch: float = 0.0
    updated_at_epoch: float = 0.0


@dataclass
class _PersistItem:
    target: dict[str, Any]
    provider_state: dict[str, Any]
    event: dict[str, Any]


_STATE_LOCK = threading.RLock()
_TARGETS: dict[tuple[str, str], _TargetMemory] = {}
_PROVIDERS: dict[str, _ProviderMemory] = {}
_BOOTSTRAPPED = False
_BOOTSTRAP_LOCK = threading.Lock()
_QUEUE: queue.Queue[_PersistItem | None] = queue.Queue(maxsize=4096)
_WORKER: threading.Thread | None = None
_STOP = threading.Event()
_PERSISTED_EVENTS = 0


def _utcnow() -> datetime:
    return datetime.utcnow()


def _dt_to_epoch(value: Optional[datetime]) -> float:
    if not value:
        return 0.0
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.timestamp()


def _epoch_to_dt(value: float) -> Optional[datetime]:
    if not value or value <= 0:
        return None
    return datetime.utcfromtimestamp(value)


def _database_url() -> str:
    configured = (os.getenv("DATABASE_URL") or "").strip()
    if configured:
        return configured
    base = Path(__file__).resolve().parent.parent
    return f"sqlite:///{base / 'dental_ai.db'}"


def _create_router_engine():
    url = _database_url()
    if url.startswith("sqlite:"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


_ENGINE = _create_router_engine()


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(
        _ENGINE,
        tables=[
            StudyAIModelState.__table__,
            StudyAIProviderState.__table__,
            StudyAIUsageEvent.__table__,
        ],
    )


def _memory_from_model(row: StudyAIModelState) -> _TargetMemory:
    return _TargetMemory(
        provider=row.provider,
        model=row.model,
        day_key=row.day_key or "",
        day_requests=row.day_requests or 0,
        day_generation_requests=row.day_generation_requests or 0,
        day_embedding_requests=row.day_embedding_requests or 0,
        month_key=row.month_key or "",
        month_requests=row.month_requests or 0,
        total_requests=row.total_requests or 0,
        total_successes=row.total_successes or 0,
        total_failures=row.total_failures or 0,
        total_429=row.total_429 or 0,
        total_prompt_tokens=row.total_prompt_tokens or 0,
        total_output_tokens=row.total_output_tokens or 0,
        total_tokens=row.total_tokens or 0,
        consecutive_failures=row.consecutive_failures or 0,
        circuit_open_until_epoch=_dt_to_epoch(row.circuit_open_until),
        last_status_code=row.last_status_code,
        last_error_kind=row.last_error_kind,
        last_latency_ms=row.last_latency_ms or 0,
        ewma_latency_ms=float(row.ewma_latency_ms or 0.0),
        provider_limit_requests=row.provider_limit_requests,
        provider_remaining_requests=row.provider_remaining_requests,
        provider_limit_tokens=row.provider_limit_tokens,
        provider_remaining_tokens=row.provider_remaining_tokens,
        provider_reset_at_epoch=_dt_to_epoch(row.provider_reset_at),
        quota_source=row.quota_source or "observed",
        last_success_at_epoch=_dt_to_epoch(row.last_success_at),
        last_failure_at_epoch=_dt_to_epoch(row.last_failure_at),
        updated_at_epoch=_dt_to_epoch(row.updated_at),
    )


def _memory_from_provider(row: StudyAIProviderState) -> _ProviderMemory:
    return _ProviderMemory(
        provider=row.provider,
        day_key=row.day_key or "",
        day_requests=row.day_requests or 0,
        month_key=row.month_key or "",
        month_requests=row.month_requests or 0,
        total_requests=row.total_requests or 0,
        total_429=row.total_429 or 0,
        provider_limit_requests=row.provider_limit_requests,
        provider_remaining_requests=row.provider_remaining_requests,
        provider_limit_tokens=row.provider_limit_tokens,
        provider_remaining_tokens=row.provider_remaining_tokens,
        provider_reset_at_epoch=_dt_to_epoch(row.provider_reset_at),
        quota_source=row.quota_source or "observed",
        consecutive_failures=row.consecutive_failures or 0,
        circuit_open_until_epoch=_dt_to_epoch(row.circuit_open_until),
        last_status_code=row.last_status_code,
        last_error_kind=row.last_error_kind,
        last_success_at_epoch=_dt_to_epoch(row.last_success_at),
        last_failure_at_epoch=_dt_to_epoch(row.last_failure_at),
        updated_at_epoch=_dt_to_epoch(row.updated_at),
    )


def _worker_loop() -> None:
    global _PERSISTED_EVENTS
    while not _STOP.is_set():
        try:
            item = _QUEUE.get(timeout=0.5)
        except queue.Empty:
            continue
        if item is None:
            _QUEUE.task_done()
            break
        try:
            _persist(item)
            _PERSISTED_EVENTS += 1
            if _PERSISTED_EVENTS % 250 == 0:
                _prune_old_events()
        except Exception:
            logger.exception("Academic AI router state could not be persisted.")
        finally:
            _QUEUE.task_done()


def _start_worker() -> None:
    global _WORKER
    if _WORKER and _WORKER.is_alive():
        return
    _WORKER = threading.Thread(
        target=_worker_loop,
        name="study-ai-router-state",
        daemon=True,
    )
    _WORKER.start()


def ensure_started() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        _start_worker()
        return
    with _BOOTSTRAP_LOCK:
        if _BOOTSTRAPPED:
            _start_worker()
            return
        try:
            _ensure_tables()
            with Session(_ENGINE) as session:
                target_rows = session.exec(select(StudyAIModelState)).all()
                provider_rows = session.exec(select(StudyAIProviderState)).all()
            with _STATE_LOCK:
                for row in target_rows:
                    _TARGETS[(row.provider, row.model)] = _memory_from_model(row)
                for row in provider_rows:
                    _PROVIDERS[row.provider] = _memory_from_provider(row)
        except Exception:
            # Router persistence must never take Academic AI down. The in-memory
            # circuit still works even if the DB is temporarily unavailable.
            logger.exception("Academic AI router state bootstrap failed; using memory-only state.")
        _BOOTSTRAPPED = True
        _start_worker()


def _get_target(provider: str, model: str) -> _TargetMemory:
    key = (provider, model)
    state = _TARGETS.get(key)
    if state is None:
        state = _TargetMemory(provider=provider, model=model)
        _TARGETS[key] = state
    return state


def _get_provider_state(provider: str) -> _ProviderMemory:
    state = _PROVIDERS.get(provider)
    if state is None:
        state = _ProviderMemory(provider=provider)
        _PROVIDERS[provider] = state
    return state


def _shared_quota_providers() -> set[str]:
    raw = os.getenv("STUDY_SHARED_QUOTA_PROVIDERS", "cohere,openrouter")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _request_budget(provider: str, model: str) -> dict[str, int]:
    """Optional verified request budgets supplied by configuration.

    Example:
      STUDY_ROUTER_REQUEST_BUDGETS_JSON='{"cohere:*":{"month":1000}}'

    Dental AI never invents a hard quota when this is unset. Provider headers
    remain the preferred exact source; these budgets are only for limits that an
    administrator has explicitly verified for the active account/tier.
    """
    raw = (os.getenv("STUDY_ROUTER_REQUEST_BUDGETS_JSON") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        logger.warning("STUDY_ROUTER_REQUEST_BUDGETS_JSON is invalid JSON; ignored.")
        return {}
    if not isinstance(parsed, dict):
        return {}
    provider = (provider or "").strip().lower()
    model = (model or "").strip()
    value = parsed.get(f"{provider}:{model}")
    if value is None:
        value = parsed.get(f"{provider}:*")
    if value is None:
        value = parsed.get(provider)
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key in ("day", "month"):
        try:
            number = int(value.get(key) or 0)
        except (TypeError, ValueError):
            number = 0
        if number > 0:
            result[key] = number
    return result


def _budget_exhausted(provider: str, model: str, state: _TargetMemory | None, pstate: _ProviderMemory | None) -> bool:
    budget = _request_budget(provider, model)
    if not budget:
        return False
    now = _utcnow()
    today = now.strftime("%Y-%m-%d")
    month = now.strftime("%Y-%m")
    # provider:* budgets are naturally represented by provider aggregate counters;
    # exact model budgets use the target counters.
    raw = (os.getenv("STUDY_ROUTER_REQUEST_BUDGETS_JSON") or "").strip()
    provider_wide = False
    try:
        parsed = json.loads(raw) if raw else {}
        provider_wide = isinstance(parsed, dict) and (
            f"{provider}:*" in parsed or (provider in parsed and f"{provider}:{model}" not in parsed)
        )
    except Exception:
        provider_wide = False
    source: Any = pstate if provider_wide and pstate is not None else state
    if source is None:
        return False
    day_count = source.day_requests if source.day_key == today else 0
    month_count = source.month_requests if source.month_key == month else 0
    if budget.get("day") and day_count >= budget["day"]:
        return True
    if budget.get("month") and month_count >= budget["month"]:
        return True
    return False


def _error_kind(status_code: Optional[int], success: bool) -> Optional[str]:
    if success:
        return None
    if status_code == 429:
        return "quota"
    if status_code in {401, 403}:
        return "auth"
    if status_code == 404:
        return "model"
    if status_code == 408:
        return "timeout"
    if status_code and status_code >= 500:
        return "provider"
    if status_code and status_code >= 400:
        return "request"
    return "network"


def _backoff_seconds(
    status_code: Optional[int],
    consecutive_failures: int,
    retry_after_seconds: Optional[float],
) -> float:
    if retry_after_seconds is not None and retry_after_seconds > 0:
        return min(max(retry_after_seconds, 5.0), 24 * 3600.0)
    index = max(0, consecutive_failures - 1)
    if status_code == 429:
        values = [600, 1800, 7200, 21600, 43200]
    elif status_code in {401, 403}:
        values = [21600, 86400]
    elif status_code == 404:
        values = [21600, 86400]
    elif status_code == 408 or (status_code is not None and status_code >= 500):
        values = [30, 120, 300, 600]
    else:
        values = [20, 60, 180, 600]
    return float(values[min(index, len(values) - 1)])


def _parse_duration(value: str | None) -> Optional[float]:
    if not value:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None:
        if numeric > 1_000_000_000_000:
            return max(0.0, numeric / 1000.0 - time.time())
        if numeric > 1_000_000_000:
            return max(0.0, numeric - time.time())
        return max(0.0, numeric)
    total = 0.0
    matched = False
    for number, unit in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(ms|s|m|h|d)", text):
        matched = True
        amount = float(number)
        total += amount * {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}[unit]
    return total if matched else None


def _parse_retry_after(value: str | None) -> Optional[float]:
    if not value:
        return None
    duration = _parse_duration(value)
    if duration is not None:
        return duration
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, parsed.timestamp() - time.time())
    except Exception:
        return None


def _int_header(headers: dict[str, str], *keys: str) -> Optional[int]:
    for key in keys:
        value = headers.get(key)
        if value is None:
            continue
        try:
            return max(0, int(float(str(value).strip())))
        except (TypeError, ValueError):
            continue
    return None


def _usage_from_json(payload: Any) -> tuple[int, int, int]:
    if not isinstance(payload, dict):
        return 0, 0, 0

    # Gemini generateContent
    meta = payload.get("usageMetadata") or {}
    if isinstance(meta, dict) and meta:
        prompt = int(meta.get("promptTokenCount") or 0)
        output = int(meta.get("candidatesTokenCount") or meta.get("responseTokenCount") or 0)
        total = int(meta.get("totalTokenCount") or (prompt + output))
        return prompt, output, total

    # OpenAI-compatible APIs
    usage = payload.get("usage") or {}
    if isinstance(usage, dict) and usage:
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        output = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total = int(usage.get("total_tokens") or (prompt + output))
        if prompt or output or total:
            return prompt, output, total

        # Cohere v2 may nest token counters.
        for nested_key in ("tokens", "billed_units"):
            nested = usage.get(nested_key) or {}
            if isinstance(nested, dict):
                prompt = int(nested.get("input_tokens") or nested.get("input_units") or 0)
                output = int(nested.get("output_tokens") or nested.get("output_units") or 0)
                total = prompt + output
                if total:
                    return prompt, output, total

    meta = payload.get("meta") or {}
    if isinstance(meta, dict):
        billed = meta.get("billed_units") or {}
        if isinstance(billed, dict):
            prompt = int(billed.get("input_tokens") or 0)
            output = int(billed.get("output_tokens") or 0)
            total = prompt + output
            if total:
                return prompt, output, total
    return 0, 0, 0


def extract_rate_limit_meta(
    response_headers: Any = None,
    response_json: Any = None,
    error_body: str | None = None,
) -> dict[str, Any]:
    """Normalize vendor rate-limit metadata without assuming a fake quota."""
    headers: dict[str, str] = {}
    if response_headers is not None:
        try:
            headers = {str(k).lower(): str(v) for k, v in response_headers.items()}
        except Exception:
            headers = {}

    remaining_requests = _int_header(
        headers,
        "x-ratelimit-remaining-requests",
        "ratelimit-remaining-requests",
        "ratelimit-remaining",
        "x-ratelimit-remaining",
    )
    limit_requests = _int_header(
        headers,
        "x-ratelimit-limit-requests",
        "ratelimit-limit-requests",
        "ratelimit-limit",
        "x-ratelimit-limit",
    )
    remaining_tokens = _int_header(
        headers,
        "x-ratelimit-remaining-tokens",
        "ratelimit-remaining-tokens",
    )
    limit_tokens = _int_header(
        headers,
        "x-ratelimit-limit-tokens",
        "ratelimit-limit-tokens",
    )

    retry_after = _parse_retry_after(headers.get("retry-after"))
    reset_candidates: list[float] = []
    for key in (
        "x-ratelimit-reset-requests",
        "ratelimit-reset-requests",
        "ratelimit-reset",
        "x-ratelimit-reset",
    ):
        value = _parse_duration(headers.get(key))
        if value is not None:
            reset_candidates.append(value)

    parsed_error: Any = None
    if error_body:
        try:
            parsed_error = json.loads(error_body)
        except Exception:
            parsed_error = None
    if isinstance(parsed_error, dict):
        details = ((parsed_error.get("error") or {}).get("details") or parsed_error.get("details") or [])
        if isinstance(details, list):
            for item in details:
                if not isinstance(item, dict):
                    continue
                retry_delay = item.get("retryDelay") or item.get("retry_delay")
                value = _parse_duration(str(retry_delay)) if retry_delay is not None else None
                if value is not None:
                    reset_candidates.append(value)
                    if retry_after is None:
                        retry_after = value

    reset_seconds = min(reset_candidates) if reset_candidates else None
    reset_at_epoch = time.time() + reset_seconds if reset_seconds is not None else 0.0
    prompt_tokens, output_tokens, total_tokens = _usage_from_json(response_json)

    exact = any(
        value is not None
        for value in (remaining_requests, limit_requests, remaining_tokens, limit_tokens)
    )
    return {
        "remaining_requests": remaining_requests,
        "limit_requests": limit_requests,
        "remaining_tokens": remaining_tokens,
        "limit_tokens": limit_tokens,
        "retry_after_seconds": retry_after,
        "reset_at_epoch": reset_at_epoch,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "quota_source": "provider_header" if exact else "observed",
    }


def target_available(provider: str, model: str) -> bool:
    ensure_started()
    provider = (provider or "").strip().lower()
    model = (model or "").strip()
    now = time.time()
    with _STATE_LOCK:
        pstate = _PROVIDERS.get(provider)
        if pstate and pstate.circuit_open_until_epoch > now:
            return False
        if pstate and (
            pstate.provider_remaining_requests is not None
            and pstate.provider_remaining_requests <= 0
            and pstate.provider_reset_at_epoch > now
        ):
            return False
        state = _TARGETS.get((provider, model))
        if _budget_exhausted(provider, model, state, pstate):
            return False
        if not state:
            return True
        if state.circuit_open_until_epoch > now:
            return False
        if (
            state.provider_remaining_requests is not None
            and state.provider_remaining_requests <= 0
            and state.provider_reset_at_epoch > now
        ):
            return False
        return True


def _score_target(state: _TargetMemory | None, base_index: int, profile: str) -> float:
    # Static order expresses quality/capacity preference. Runtime observations then
    # move slow or unreliable targets down without expensive probing.
    score = 1000.0 - (base_index * 10.0)
    if state is None:
        return score

    total = max(1, state.total_requests)
    if state.total_requests >= 3:
        reliability = state.total_successes / total
        score += (reliability - 0.85) * 120.0

    if state.ewma_latency_ms > 0:
        if profile in {"complex", "deep", "broad", "exam"}:
            score -= min(45.0, state.ewma_latency_ms / 260.0)
        else:
            score -= min(120.0, state.ewma_latency_ms / 90.0)

    if state.provider_remaining_requests is not None:
        remaining = state.provider_remaining_requests
        quota_window_active = (
            state.provider_reset_at_epoch <= 0
            or state.provider_reset_at_epoch > time.time()
        )
        if quota_window_active:
            if remaining <= 2:
                score -= 120.0
            elif remaining <= 10:
                score -= 45.0
            elif remaining <= 50:
                score -= 15.0

    # Small balancing penalty keeps one target from consuming every observed call
    # when several similarly-ranked targets are healthy. It is deliberately mild
    # because vendor limits are not assumed unless the provider reports them.
    if state.day_requests > 0:
        score -= min(22.0, math.log1p(state.day_requests) * 3.5)
    return score


def rank_targets(
    candidates: list[tuple[str, str]],
    profile: str = "standard",
    limit: int = 8,
) -> list[tuple[str, str]]:
    ensure_started()
    profile = (profile or "standard").strip().lower()
    now = time.time()
    scored: list[tuple[float, int, str, str]] = []
    with _STATE_LOCK:
        for index, (provider_raw, model_raw) in enumerate(candidates):
            provider = (provider_raw or "").strip().lower()
            model = (model_raw or "").strip()
            if not provider or not model:
                continue
            pstate = _PROVIDERS.get(provider)
            if pstate and pstate.circuit_open_until_epoch > now:
                continue
            if pstate and (
                pstate.provider_remaining_requests is not None
                and pstate.provider_remaining_requests <= 0
                and pstate.provider_reset_at_epoch > now
            ):
                continue
            state = _TARGETS.get((provider, model))
            if _budget_exhausted(provider, model, state, pstate):
                continue
            if state and state.circuit_open_until_epoch > now:
                continue
            if state and (
                state.provider_remaining_requests is not None
                and state.provider_remaining_requests <= 0
                and state.provider_reset_at_epoch > now
            ):
                continue
            score = _score_target(state, index, profile)
            budget = _request_budget(provider, model)
            if budget:
                today = _utcnow().strftime("%Y-%m-%d")
                month_key = _utcnow().strftime("%Y-%m")
                raw_budget = (os.getenv("STUDY_ROUTER_REQUEST_BUDGETS_JSON") or "").strip()
                provider_wide = False
                try:
                    parsed_budget = json.loads(raw_budget) if raw_budget else {}
                    provider_wide = isinstance(parsed_budget, dict) and (
                        f"{provider}:*" in parsed_budget or (provider in parsed_budget and f"{provider}:{model}" not in parsed_budget)
                    )
                except Exception:
                    pass
                source = pstate if provider_wide and pstate is not None else state
                if source is not None:
                    fractions = []
                    if budget.get("day"):
                        count = source.day_requests if source.day_key == today else 0
                        fractions.append(count / budget["day"])
                    if budget.get("month"):
                        count = source.month_requests if source.month_key == month_key else 0
                        fractions.append(count / budget["month"])
                    pressure = max(fractions) if fractions else 0.0
                    if pressure >= 0.9:
                        score -= 90.0
                    elif pressure >= 0.75:
                        score -= 35.0
                    elif pressure >= 0.5:
                        score -= 12.0
            scored.append((score, index, provider, model))

    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored:
        return []

    # Keep fallback provider diversity when it costs little in score. The actual
    # request loop still allows at most one fallback API call.
    ordered: list[tuple[str, str]] = []
    top_score, _, top_provider, top_model = scored[0]
    ordered.append((top_provider, top_model))
    remaining = scored[1:]
    if remaining:
        diversity = next(
            (item for item in remaining if item[2] != top_provider and item[0] >= top_score - 35.0),
            None,
        )
        if diversity is not None:
            ordered.append((diversity[2], diversity[3]))
            remaining.remove(diversity)
    for _, _, provider, model in remaining:
        if (provider, model) not in ordered:
            ordered.append((provider, model))
        if len(ordered) >= max(1, limit):
            break
    return ordered[: max(1, limit)]


def record_api_result(
    *,
    provider: str,
    model: str,
    operation: str,
    success: bool,
    status_code: Optional[int],
    latency_ms: int,
    response_headers: Any = None,
    response_json: Any = None,
    error_body: str | None = None,
) -> dict[str, Any]:
    """Update hot state immediately and persist the compact ledger in background."""
    ensure_started()
    provider = (provider or "").strip().lower()
    model = (model or "").strip()
    operation = (operation or "generation").strip().lower()
    now_epoch = time.time()
    now_dt = _utcnow()
    day_key = now_dt.strftime("%Y-%m-%d")
    month_key = now_dt.strftime("%Y-%m")
    meta = extract_rate_limit_meta(response_headers, response_json, error_body)
    error_kind = _error_kind(status_code, success)

    with _STATE_LOCK:
        state = _get_target(provider, model)
        if state.day_key != day_key:
            state.day_key = day_key
            state.day_requests = 0
            state.day_generation_requests = 0
            state.day_embedding_requests = 0
        if state.month_key != month_key:
            state.month_key = month_key
            state.month_requests = 0

        state.day_requests += 1
        state.month_requests += 1
        state.total_requests += 1
        if operation.startswith("embed"):
            state.day_embedding_requests += 1
        else:
            state.day_generation_requests += 1

        state.last_status_code = status_code
        state.last_latency_ms = max(0, int(latency_ms or 0))
        if state.last_latency_ms:
            if state.ewma_latency_ms <= 0:
                state.ewma_latency_ms = float(state.last_latency_ms)
            else:
                state.ewma_latency_ms = (state.ewma_latency_ms * 0.75) + (state.last_latency_ms * 0.25)

        prompt_tokens = int(meta.get("prompt_tokens") or 0)
        output_tokens = int(meta.get("output_tokens") or 0)
        total_tokens = int(meta.get("total_tokens") or (prompt_tokens + output_tokens))
        state.total_prompt_tokens += prompt_tokens
        state.total_output_tokens += output_tokens
        state.total_tokens += total_tokens

        if meta.get("limit_requests") is not None:
            state.provider_limit_requests = int(meta["limit_requests"])
        if meta.get("remaining_requests") is not None:
            state.provider_remaining_requests = int(meta["remaining_requests"])
        if meta.get("limit_tokens") is not None:
            state.provider_limit_tokens = int(meta["limit_tokens"])
        if meta.get("remaining_tokens") is not None:
            state.provider_remaining_tokens = int(meta["remaining_tokens"])
        if meta.get("reset_at_epoch"):
            state.provider_reset_at_epoch = float(meta["reset_at_epoch"])
        if meta.get("quota_source") == "provider_header":
            state.quota_source = "provider_header"

        pstate = _get_provider_state(provider)
        if pstate.day_key != day_key:
            pstate.day_key = day_key
            pstate.day_requests = 0
        if pstate.month_key != month_key:
            pstate.month_key = month_key
            pstate.month_requests = 0
        pstate.day_requests += 1
        pstate.month_requests += 1
        pstate.total_requests += 1
        if status_code == 429:
            pstate.total_429 += 1
        if meta.get("limit_requests") is not None:
            pstate.provider_limit_requests = int(meta["limit_requests"])
        if meta.get("remaining_requests") is not None:
            pstate.provider_remaining_requests = int(meta["remaining_requests"])
        if meta.get("limit_tokens") is not None:
            pstate.provider_limit_tokens = int(meta["limit_tokens"])
        if meta.get("remaining_tokens") is not None:
            pstate.provider_remaining_tokens = int(meta["remaining_tokens"])
        if meta.get("reset_at_epoch"):
            pstate.provider_reset_at_epoch = float(meta["reset_at_epoch"])
        if meta.get("quota_source") == "provider_header":
            pstate.quota_source = "provider_header"

        if success:
            state.total_successes += 1
            state.consecutive_failures = 0
            state.last_error_kind = None
            state.last_success_at_epoch = now_epoch
            state.circuit_open_until_epoch = 0.0
            pstate.consecutive_failures = 0
            pstate.last_error_kind = None
            pstate.last_status_code = status_code
            pstate.last_success_at_epoch = now_epoch
            pstate.circuit_open_until_epoch = 0.0
            # If the successful call consumed the last provider-reported request,
            # do not send the next user into a guaranteed 429 before reset.
            if (
                state.provider_remaining_requests is not None
                and state.provider_remaining_requests <= 0
                and state.provider_reset_at_epoch > now_epoch
            ):
                state.circuit_open_until_epoch = state.provider_reset_at_epoch
            if (
                provider in _shared_quota_providers()
                and pstate.provider_remaining_requests is not None
                and pstate.provider_remaining_requests <= 0
                and pstate.provider_reset_at_epoch > now_epoch
            ):
                pstate.circuit_open_until_epoch = pstate.provider_reset_at_epoch
        else:
            state.total_failures += 1
            state.consecutive_failures += 1
            state.last_error_kind = error_kind
            state.last_failure_at_epoch = now_epoch
            if status_code == 429:
                state.total_429 += 1
            retry_after = meta.get("retry_after_seconds")
            if not retry_after and meta.get("reset_at_epoch"):
                retry_after = max(0.0, float(meta["reset_at_epoch"]) - now_epoch)
            state.circuit_open_until_epoch = max(
                state.circuit_open_until_epoch,
                now_epoch + _backoff_seconds(status_code, state.consecutive_failures, retry_after),
            )

            provider_wide = status_code in {401, 403} or (
                status_code == 429 and provider in _shared_quota_providers()
            )
            if provider_wide:
                pstate.consecutive_failures += 1
                pstate.last_status_code = status_code
                pstate.last_error_kind = error_kind
                pstate.last_failure_at_epoch = now_epoch
                pstate.circuit_open_until_epoch = max(
                    pstate.circuit_open_until_epoch,
                    state.circuit_open_until_epoch,
                )

        state.updated_at_epoch = now_epoch
        pstate.updated_at_epoch = now_epoch

        target_snapshot = asdict(state)
        provider_snapshot = asdict(pstate)

    item = _PersistItem(
        target=target_snapshot,
        provider_state=provider_snapshot,
        event={
            "provider": provider,
            "model": model,
            "operation": operation,
            "success": success,
            "status_code": status_code,
            "latency_ms": max(0, int(latency_ms or 0)),
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "error_kind": error_kind,
            "quota_source": str(meta.get("quota_source") or "observed"),
            "created_at": now_dt,
        },
    )
    try:
        _QUEUE.put_nowait(item)
    except queue.Full:
        logger.warning("Academic AI router persistence queue is full; hot state kept in memory.")
    return meta


def record_local_failure(
    provider: str,
    model: str,
    *,
    status_code: Optional[int] = None,
) -> None:
    """Circuit a target for a local/config failure that made no vendor API call.

    It intentionally does not increment quota request counters because no external
    request was sent.
    """
    ensure_started()
    provider = (provider or "").strip().lower()
    model = (model or "").strip()
    now = time.time()
    with _STATE_LOCK:
        state = _get_target(provider, model)
        state.consecutive_failures += 1
        state.last_status_code = status_code
        state.last_error_kind = _error_kind(status_code, False)
        state.last_failure_at_epoch = now
        state.circuit_open_until_epoch = max(
            state.circuit_open_until_epoch,
            now + _backoff_seconds(status_code, state.consecutive_failures, None),
        )
        state.updated_at_epoch = now
        pstate = _get_provider_state(provider)
        if status_code in {401, 403}:
            pstate.consecutive_failures += 1
            pstate.last_status_code = status_code
            pstate.last_error_kind = "auth"
            pstate.last_failure_at_epoch = now
            pstate.circuit_open_until_epoch = max(pstate.circuit_open_until_epoch, state.circuit_open_until_epoch)
            pstate.updated_at_epoch = now
        target_snapshot = asdict(state)
        provider_snapshot = asdict(pstate)

    # Persist only state, not a usage event, because no API quota was consumed.
    item = _PersistItem(
        target=target_snapshot,
        provider_state=provider_snapshot,
        event={},
    )
    try:
        _QUEUE.put_nowait(item)
    except queue.Full:
        pass


def _assign_target_row(row: StudyAIModelState, data: dict[str, Any]) -> None:
    direct = (
        "day_key", "day_requests", "day_generation_requests", "day_embedding_requests",
        "month_key", "month_requests", "total_requests", "total_successes", "total_failures",
        "total_429", "total_prompt_tokens", "total_output_tokens", "total_tokens",
        "consecutive_failures", "last_status_code", "last_error_kind", "last_latency_ms",
        "ewma_latency_ms", "provider_limit_requests", "provider_remaining_requests",
        "provider_limit_tokens", "provider_remaining_tokens", "quota_source",
    )
    for name in direct:
        setattr(row, name, data.get(name))
    row.circuit_open_until = _epoch_to_dt(float(data.get("circuit_open_until_epoch") or 0.0))
    row.provider_reset_at = _epoch_to_dt(float(data.get("provider_reset_at_epoch") or 0.0))
    row.last_success_at = _epoch_to_dt(float(data.get("last_success_at_epoch") or 0.0))
    row.last_failure_at = _epoch_to_dt(float(data.get("last_failure_at_epoch") or 0.0))
    row.updated_at = _epoch_to_dt(float(data.get("updated_at_epoch") or 0.0)) or _utcnow()


def _assign_provider_row(row: StudyAIProviderState, data: dict[str, Any]) -> None:
    row.day_key = str(data.get("day_key") or "")
    row.day_requests = int(data.get("day_requests") or 0)
    row.month_key = str(data.get("month_key") or "")
    row.month_requests = int(data.get("month_requests") or 0)
    row.total_requests = int(data.get("total_requests") or 0)
    row.total_429 = int(data.get("total_429") or 0)
    row.provider_limit_requests = data.get("provider_limit_requests")
    row.provider_remaining_requests = data.get("provider_remaining_requests")
    row.provider_limit_tokens = data.get("provider_limit_tokens")
    row.provider_remaining_tokens = data.get("provider_remaining_tokens")
    row.provider_reset_at = _epoch_to_dt(float(data.get("provider_reset_at_epoch") or 0.0))
    row.quota_source = str(data.get("quota_source") or "observed")
    row.consecutive_failures = int(data.get("consecutive_failures") or 0)
    row.last_status_code = data.get("last_status_code")
    row.last_error_kind = data.get("last_error_kind")
    row.circuit_open_until = _epoch_to_dt(float(data.get("circuit_open_until_epoch") or 0.0))
    row.last_success_at = _epoch_to_dt(float(data.get("last_success_at_epoch") or 0.0))
    row.last_failure_at = _epoch_to_dt(float(data.get("last_failure_at_epoch") or 0.0))
    row.updated_at = _epoch_to_dt(float(data.get("updated_at_epoch") or 0.0)) or _utcnow()


def _persist(item: _PersistItem) -> None:
    target = item.target
    provider_state = item.provider_state
    with Session(_ENGINE) as session:
        row = session.exec(
            select(StudyAIModelState).where(
                StudyAIModelState.provider == target["provider"],
                StudyAIModelState.model == target["model"],
            )
        ).first()
        if row is None:
            row = StudyAIModelState(provider=target["provider"], model=target["model"])
            session.add(row)
        _assign_target_row(row, target)

        prow = session.exec(
            select(StudyAIProviderState).where(StudyAIProviderState.provider == provider_state["provider"])
        ).first()
        if prow is None:
            prow = StudyAIProviderState(provider=provider_state["provider"])
            session.add(prow)
        _assign_provider_row(prow, provider_state)

        if item.event:
            session.add(StudyAIUsageEvent(**item.event))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            # A second worker/process may have created the unique state row first.
            # Re-read and update once; usage event is still written only once here.
            row = session.exec(
                select(StudyAIModelState).where(
                    StudyAIModelState.provider == target["provider"],
                    StudyAIModelState.model == target["model"],
                )
            ).first()
            if row is not None:
                _assign_target_row(row, target)
            prow = session.exec(
                select(StudyAIProviderState).where(StudyAIProviderState.provider == provider_state["provider"])
            ).first()
            if prow is not None:
                _assign_provider_row(prow, provider_state)
            if item.event:
                session.add(StudyAIUsageEvent(**item.event))
            session.commit()


def _prune_old_events() -> None:
    try:
        retention_days = max(7, min(365, int(os.getenv("STUDY_ROUTER_USAGE_RETENTION_DAYS", "45"))))
    except ValueError:
        retention_days = 45
    cutoff = _utcnow() - timedelta(days=retention_days)
    try:
        with Session(_ENGINE) as session:
            old_rows = session.exec(
                select(StudyAIUsageEvent).where(StudyAIUsageEvent.created_at < cutoff).limit(1000)
            ).all()
            if not old_rows:
                return
            for row in old_rows:
                session.delete(row)
            session.commit()
    except Exception:
        logger.exception("Academic AI old usage rows could not be pruned.")


def get_router_snapshot() -> list[dict[str, Any]]:
    """Future admin/status endpoint helper; safe operational data only."""
    ensure_started()
    now = time.time()
    with _STATE_LOCK:
        result: list[dict[str, Any]] = []
        for state in _TARGETS.values():
            pstate = _PROVIDERS.get(state.provider)
            blocked_until = max(
                state.circuit_open_until_epoch,
                pstate.circuit_open_until_epoch if pstate else 0.0,
            )
            result.append({
                "provider": state.provider,
                "model": state.model,
                "status": "cooldown" if blocked_until > now else "active",
                "cooldown_until": _epoch_to_dt(blocked_until),
                "day_requests": state.day_requests,
                "day_generation_requests": state.day_generation_requests,
                "day_embedding_requests": state.day_embedding_requests,
                "month_requests": state.month_requests,
                "remaining_requests": state.provider_remaining_requests,
                "remaining_tokens": state.provider_remaining_tokens,
                "reset_at": _epoch_to_dt(state.provider_reset_at_epoch),
                "quota_source": state.quota_source,
                "provider_day_requests": pstate.day_requests if pstate else 0,
                "provider_month_requests": pstate.month_requests if pstate else 0,
                "provider_remaining_requests": pstate.provider_remaining_requests if pstate else None,
                "provider_reset_at": _epoch_to_dt(pstate.provider_reset_at_epoch) if pstate else None,
                "ewma_latency_ms": round(state.ewma_latency_ms, 1),
                "success_rate": round(state.total_successes / max(1, state.total_requests), 4),
                "last_status_code": state.last_status_code,
            })
        return sorted(result, key=lambda item: (item["provider"], item["model"]))


def _shutdown() -> None:
    _STOP.set()
    try:
        _QUEUE.put_nowait(None)
    except queue.Full:
        return
    worker = _WORKER
    if worker and worker.is_alive():
        worker.join(timeout=1.0)


atexit.register(_shutdown)
