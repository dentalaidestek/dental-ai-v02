from datetime import datetime
from types import SimpleNamespace

import pytest

from app.clinical_media_gallery import (
    CLINICAL_MEDIA_GALLERY_PAGE_SIZE,
    media_page_slice,
    normalize_media_page_cursor,
    serialize_media_page,
)


def _media(ident: int, media_type: str = "RADIOGRAPH"):
    return SimpleNamespace(
        id=ident,
        media_type=media_type,
        uploaded_at=datetime(2026, 11, 20, 5, 30),
        tooth_number="36",
        note="Kontrol notu",
        file_path="r2://private/patient-1/secret-original.png",
        original_filename="secret-original.png",
        owner_user_id=99,
    )


@pytest.mark.parametrize("value,expected", [(None, None), (1, 1), ("42", 42)])
def test_media_cursor_accepts_only_positive_integer_values(value, expected):
    assert normalize_media_page_cursor(value) == expected


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, " 1", "+1", "1.0", "", str(1 << 53)])
def test_media_cursor_rejects_coercive_or_out_of_range_values(value):
    with pytest.raises(ValueError):
        normalize_media_page_cursor(value)


def test_media_page_uses_last_visible_id_as_stable_descending_cursor():
    rows = [_media(90), _media(80), _media(70)]
    page, cursor = media_page_slice(rows, limit=2)
    assert [item.id for item in page] == [90, 80]
    assert cursor == 80


def test_media_page_has_no_cursor_when_all_rows_fit():
    page, cursor = media_page_slice([_media(90), _media(80)], limit=2)
    assert [item.id for item in page] == [90, 80]
    assert cursor is None


def test_serialized_page_exposes_only_display_metadata_and_same_origin_paths():
    payload = serialize_media_page([_media(90), _media(80), _media(70)], patient_id=7, limit=2)
    assert [item["id"] for item in payload["items"]] == [90, 80]
    assert payload["next_before"] == 80
    first = payload["items"][0]
    assert first == {
        "id": 90,
        "media_type": "RADIOGRAPH",
        "uploaded_at": "20.11.2026 · 05:30",
        "tooth_number": "36",
        "note": "Kontrol notu",
        "url": "/patients/7/media/90/file",
        "thumbnail_url": "/patients/7/media/90/thumbnail",
        "delete_url": "/patients/7/media/90/delete",
    }
    assert "file_path" not in first
    assert "original_filename" not in first
    assert "owner_user_id" not in first


def test_page_size_and_media_identifiers_are_bounded():
    assert CLINICAL_MEDIA_GALLERY_PAGE_SIZE == 40
    with pytest.raises(ValueError):
        media_page_slice([], limit=41)
    with pytest.raises(ValueError):
        serialize_media_page([_media(1, "UNKNOWN")], patient_id=7)
    with pytest.raises(ValueError):
        serialize_media_page([_media(1 << 53)], patient_id=7)
