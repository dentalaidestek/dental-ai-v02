from __future__ import annotations

from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import secrets
import threading

_EVENTS = deque(maxlen=1000)
_LOCK = threading.Lock()
_TRACE_ID = ContextVar("xray_trace_id", default="")
_OWNER_ID = ContextVar("xray_trace_owner_id", default=None)


def _user_tag(owner_user_id):
    if owner_user_id is None:
        return None
    return hashlib.sha256(f"xray:{owner_user_id}".encode("utf-8")).hexdigest()[:10]


def _safe(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:320]
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value[:30]]
    if isinstance(value, dict):
        return {str(k)[:80]: _safe(v) for k, v in list(value.items())[:40]}
    return str(value)[:320]


def begin_xray_trace(owner_user_id: int | None, *, stage: str, analysis_id: int | None, guest: bool) -> str:
    trace_id = f"xray_{secrets.token_hex(4)}"
    _TRACE_ID.set(trace_id)
    _OWNER_ID.set(owner_user_id)
    xray_trace_event(
        "trace.begin",
        stage=stage,
        analysis_id=analysis_id,
        guest=bool(guest),
    )
    return trace_id


def xray_trace_event(event: str, **data) -> None:
    trace_id = _TRACE_ID.get()
    owner_id = _OWNER_ID.get()
    if not trace_id:
        return
    item = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "user": _user_tag(owner_id),
        "event": str(event),
    }
    for key, value in data.items():
        # Ham hasta notu, soru, cevap, prompt, AI yanıtı veya görüntü bytes loglanmaz.
        item[str(key)[:80]] = _safe(value)
    with _LOCK:
        _EVENTS.append(item)


def end_xray_trace(**data) -> None:
    if _TRACE_ID.get():
        xray_trace_event("trace.end", **data)
    _TRACE_ID.set("")
    _OWNER_ID.set(None)


def get_xray_trace_events(owner_user_id: int, limit: int = 200):
    tag = _user_tag(owner_user_id)
    limit = max(1, min(int(limit or 200), 500))
    with _LOCK:
        rows = [dict(item) for item in _EVENTS if item.get("user") == tag]
    return rows[-limit:]
