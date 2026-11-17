from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.mobile_program_api import (
    _decode_program_cursor,
    _encode_program_cursor,
    _program_local_start_utc,
)

ISTANBUL = ZoneInfo("Europe/Istanbul")


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
        "today", focus, 7, snapshot_at, item, ISTANBUL
    )
    decoded_snapshot, after_utc, after_id = _decode_program_cursor(
        cursor, "today", focus, 7, ISTANBUL, now_utc
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
        )
    assert error.value.status_code == 422


def test_program_local_start_conversion_does_not_use_host_timezone():
    local_start = datetime(2026, 11, 17, 23, 30)
    expected = datetime(2026, 11, 17, 20, 30, tzinfo=timezone.utc)

    assert _program_local_start_utc(local_start, ISTANBUL) == expected
    assert _program_local_start_utc(local_start.replace(tzinfo=ISTANBUL), ISTANBUL) == expected
