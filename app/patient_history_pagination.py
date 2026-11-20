"""Stable, bounded cursor helpers for the web patient-history lists."""
from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime, timezone
from typing import Any

HISTORY_PAGE_SIZE = 20
_MAX_CURSOR_CHARS = 192
_MAX_RECORD_ID = (1 << 53) - 1
_CURSOR_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def encode_history_cursor(created_at: datetime, record_id: int) -> str:
    """Encode the exact descending (created_at, id) boundary for a page."""
    if not isinstance(created_at, datetime):
        raise ValueError("Invalid patient-history timestamp")
    if isinstance(record_id, bool) or not isinstance(record_id, int) or not 1 <= record_id <= _MAX_RECORD_ID:
        raise ValueError("Invalid patient-history id")
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
    raw = f"{created_at.isoformat()}|{record_id}".encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_history_cursor(value: Any) -> tuple[datetime, int] | None:
    """Decode a bounded cursor; callers must still scope every query to one patient."""
    if value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= _MAX_CURSOR_CHARS or not value.isascii():
        raise ValueError("Invalid patient-history cursor")
    if not _CURSOR_RE.fullmatch(value):
        raise ValueError("Invalid patient-history cursor")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        timestamp_text, id_text = raw.decode("ascii").split("|", 1)
        created_at = datetime.fromisoformat(timestamp_text)
        if created_at.tzinfo is not None:
            created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
        if not id_text.isascii() or not id_text.isdecimal():
            raise ValueError("Invalid patient-history id")
        record_id = int(id_text)
    except (binascii.Error, UnicodeDecodeError, TypeError) as exc:
        raise ValueError("Invalid patient-history cursor") from exc
    if isinstance(record_id, bool) or not 1 <= record_id <= _MAX_RECORD_ID:
        raise ValueError("Invalid patient-history id")
    return created_at, record_id


def history_page_slice(rows: list[Any], limit: int = HISTORY_PAGE_SIZE) -> tuple[list[Any], str | None]:
    """Trim a limit+1 query result and return a stable cursor when more rows exist."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= HISTORY_PAGE_SIZE:
        raise ValueError("Invalid patient-history page size")
    materialized = list(rows)
    page = materialized[:limit]
    if len(materialized) <= limit or not page:
        return page, None
    last = page[-1]
    return page, encode_history_cursor(getattr(last, "created_at", None), getattr(last, "id", None))
