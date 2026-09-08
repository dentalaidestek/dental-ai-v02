from __future__ import annotations

from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import logging
import secrets
import threading

_LOG = logging.getLogger("dental_ai.study_trace")
_EVENTS = deque(maxlen=800)
_LOCK = threading.Lock()
_TRACE_ID = ContextVar("study_trace_id", default="")
_OWNER_ID = ContextVar("study_trace_owner_id", default=None)


def _user_tag(owner_user_id):
    if owner_user_id is None:
        return None
    return hashlib.sha256(f"study:{owner_user_id}".encode("utf-8")).hexdigest()[:10]


def _safe(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:240]
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value[:20]]
    if isinstance(value, dict):
        return {str(k)[:80]: _safe(v) for k, v in list(value.items())[:30]}
    return str(value)[:240]


def begin_trace(owner_user_id: int, prefix: str = "acad") -> str:
    trace_id = f"{prefix}_{secrets.token_hex(4)}"
    _TRACE_ID.set(trace_id)
    _OWNER_ID.set(owner_user_id)
    trace_event("trace.begin", trace_id=trace_id, owner_user_id=owner_user_id)
    return trace_id


def current_trace_id() -> str:
    return _TRACE_ID.get() or ""


def current_owner_user_id():
    return _OWNER_ID.get()


def trace_event(stage: str, *, trace_id=None, owner_user_id=None, **fields) -> None:
    trace_id = trace_id or current_trace_id() or f"orphan_{secrets.token_hex(3)}"
    owner = owner_user_id if owner_user_id is not None else current_owner_user_id()
    event = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "trace_id": trace_id,
        "stage": stage,
        "_owner_user_id": owner,
        "user_tag": _user_tag(owner),
    }
    for key, value in fields.items():
        low = str(key).lower()
        if any(token in low for token in (
            "api_key", "password", "secret", "prompt_text",
            "note_text", "answer_text", "query_text"
        )):
            continue
        event[str(key)] = _safe(value)
    with _LOCK:
        _EVENTS.append(event)
    public = {key: value for key, value in event.items() if key != "_owner_user_id"}
    _LOG.warning("[STUDY_TRACE] %s", json.dumps(public, ensure_ascii=False, separators=(",", ":")))


def get_trace_events(owner_user_id: int, limit: int = 150):
    limit = max(1, min(int(limit or 150), 300))
    with _LOCK:
        rows = [dict(item) for item in _EVENTS if item.get("_owner_user_id") == owner_user_id][-limit:]
    for row in rows:
        row.pop("_owner_user_id", None)
    return rows
