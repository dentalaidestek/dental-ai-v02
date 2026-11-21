import base64
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.mobile_program_api import (
    _decode_program_cursor,
    _encode_program_cursor,
    _program_local_start_utc,
    _program_cursor_key,
)

ISTANBUL = ZoneInfo("Europe/Istanbul")
SESSION_TOKEN = "A" * 43


@pytest.mark.parametrize("local_start", [
    datetime(2026, 11, 17, 0, 15),
    datetime(2026, 11, 17, 23, 30),
])
def test_program_cursor_round_trip_uses_istanbul_wall_time(local_start):
    focus = date(2026, 11, 17)
    snapshot_at = datetime(2026, 11, 17, 19, 50)
    now_utc = datetime(2026, 11, 17, 19, 51, tzinfo=timezone.utc)
    item = {"id": 41, "start_local": local_start}

    cursor = _encode_program_cursor(
        "today", focus, 7, snapshot_at, item, ISTANBUL, SESSION_TOKEN
    )
    decoded_snapshot, after_utc, after_id = _decode_program_cursor(
        cursor, "today", focus, 7, ISTANBUL, now_utc, SESSION_TOKEN
    )

    assert decoded_snapshot == snapshot_at
    assert after_id == 41
    assert after_utc == local_start.replace(tzinfo=ISTANBUL).astimezone(timezone.utc)
    assert after_utc.astimezone(ISTANBUL).replace(tzinfo=None) == local_start


def test_program_cursor_rejects_a_cursor_from_another_account():
    focus = date(2026, 11, 17)
    cursor = _encode_program_cursor(
        "week",
        focus,
        7,
        datetime(2026, 11, 17, 19, 50),
        {"id": 41, "start_local": datetime(2026, 11, 17, 23, 30)},
        ISTANBUL,
        SESSION_TOKEN,
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        _decode_program_cursor(
            cursor,
            "week",
            focus,
            8,
            ISTANBUL,
            datetime(2026, 11, 17, 19, 51, tzinfo=timezone.utc),
            SESSION_TOKEN,
        )
    assert error.value.status_code == 422


def test_program_local_start_conversion_does_not_use_host_timezone():
    local_start = datetime(2026, 11, 17, 23, 30)
    expected = datetime(2026, 11, 17, 20, 30, tzinfo=timezone.utc)

    assert _program_local_start_utc(local_start, ISTANBUL) == expected
    assert _program_local_start_utc(local_start.replace(tzinfo=ISTANBUL), ISTANBUL) == expected



def test_program_cursor_key_is_domain_separated_and_rejects_non_session_tokens():
    import hashlib

    token = "A" * 43
    expected = hashlib.sha256(b"dental-ai:program-cursor:v2:" + token.encode("ascii")).digest()
    assert _program_cursor_key(token) == expected
    assert _program_cursor_key(token) != token.encode("ascii")

    with pytest.raises(ValueError):
        _program_cursor_key("short")


def test_program_cursor_rejects_payload_tampering_and_session_token_rotation():
    from fastapi import HTTPException

    focus = date(2026, 11, 17)
    now = datetime(2026, 11, 17, 19, 51, tzinfo=timezone.utc)
    cursor = _encode_program_cursor(
        "today",
        focus,
        7,
        datetime(2026, 11, 17, 19, 50),
        {"id": 41, "start_local": datetime(2026, 11, 17, 23, 30)},
        ISTANBUL,
        SESSION_TOKEN,
    )

    with pytest.raises(HTTPException) as rotated:
        _decode_program_cursor(cursor, "today", focus, 7, ISTANBUL, now, "B" * 43)
    assert rotated.value.status_code == 422

    packed = bytearray(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    packed[0] ^= 1
    tampered = base64.urlsafe_b64encode(bytes(packed)).decode("ascii").rstrip("=")
    with pytest.raises(HTTPException) as forged:
        _decode_program_cursor(tampered, "today", focus, 7, ISTANBUL, now, SESSION_TOKEN)
    assert forged.value.status_code == 422


def test_program_cursor_rejects_expired_and_future_snapshots():
    from fastapi import HTTPException

    focus = date(2026, 11, 17)
    item = {"id": 41, "start_local": datetime(2026, 11, 17, 23, 30)}
    expired = _encode_program_cursor(
        "today", focus, 7, datetime(2026, 11, 17, 19, 30), item, ISTANBUL, SESSION_TOKEN
    )
    with pytest.raises(HTTPException) as old:
        _decode_program_cursor(
            expired, "today", focus, 7, ISTANBUL,
            datetime(2026, 11, 17, 19, 46, tzinfo=timezone.utc), SESSION_TOKEN
        )
    assert old.value.status_code == 410

    future = _encode_program_cursor(
        "today", focus, 7, datetime(2026, 11, 17, 19, 52), item, ISTANBUL, SESSION_TOKEN
    )
    with pytest.raises(HTTPException) as ahead:
        _decode_program_cursor(
            future, "today", focus, 7, ISTANBUL,
            datetime(2026, 11, 17, 19, 50, tzinfo=timezone.utc), SESSION_TOKEN
        )
    assert ahead.value.status_code == 422
