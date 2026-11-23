"""Bounded, session-authenticated clinical media gallery page helpers.

The cursor is the descending PatientMedia primary key, matching the native
archive contract. Only display metadata and same-origin route paths are exposed.
"""
from __future__ import annotations

from typing import Any

CLINICAL_MEDIA_GALLERY_PAGE_SIZE = 40
_MAX_SAFE_MEDIA_ID = (1 << 53) - 1


def normalize_media_page_cursor(value: Any) -> int | None:
    """Accept only a positive integer cursor; booleans and coercive strings fail."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Invalid clinical media cursor")
    if isinstance(value, int):
        cursor = value
    elif isinstance(value, str) and value.isascii() and value.isdecimal():
        cursor = int(value)
    else:
        raise ValueError("Invalid clinical media cursor")
    if cursor < 1 or cursor > _MAX_SAFE_MEDIA_ID:
        raise ValueError("Invalid clinical media cursor")
    return cursor


def media_page_slice(rows: list[Any], limit: int = CLINICAL_MEDIA_GALLERY_PAGE_SIZE):
    """Return a bounded page and the last visible id when another page exists."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= CLINICAL_MEDIA_GALLERY_PAGE_SIZE:
        raise ValueError("Invalid clinical media page size")
    materialized = list(rows)
    page = materialized[:limit]
    has_more = len(materialized) > limit
    if not has_more or not page:
        return page, None
    cursor = getattr(page[-1], "id", None)
    if isinstance(cursor, bool) or not isinstance(cursor, int) or not 1 <= cursor <= _MAX_SAFE_MEDIA_ID:
        raise ValueError("Invalid clinical media page row")
    return page, cursor


def serialize_media_page_item(media: Any, patient_id: int) -> dict[str, Any]:
    """Serialize only owner-authorized display metadata and same-origin paths."""
    media_id = getattr(media, "id", None)
    if isinstance(media_id, bool) or not isinstance(media_id, int) or not 1 <= media_id <= _MAX_SAFE_MEDIA_ID:
        raise ValueError("Invalid clinical media id")
    if isinstance(patient_id, bool) or not isinstance(patient_id, int) or patient_id < 1:
        raise ValueError("Invalid patient id")
    uploaded_at = getattr(media, "uploaded_at", None)
    date_label = uploaded_at.strftime("%d.%m.%Y · %H:%M") if hasattr(uploaded_at, "strftime") else ""
    media_type = str(getattr(media, "media_type", "") or "").upper()
    if media_type not in {"PHOTO", "RADIOGRAPH"}:
        raise ValueError("Invalid clinical media type")
    base = f"/patients/{patient_id}/media/{media_id}"
    return {
        "id": media_id,
        "media_type": media_type,
        "uploaded_at": date_label,
        "tooth_number": str(getattr(media, "tooth_number", None) or ""),
        "note": str(getattr(media, "note", None) or ""),
        "url": base + "/file",
        "thumbnail_url": base + "/thumbnail",
        "delete_url": base + "/delete",
    }


def serialize_media_page(rows: list[Any], patient_id: int, limit: int = CLINICAL_MEDIA_GALLERY_PAGE_SIZE):
    page, next_before = media_page_slice(rows, limit)
    return {
        "items": [serialize_media_page_item(item, patient_id) for item in page],
        "next_before": next_before,
    }
