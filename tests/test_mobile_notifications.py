"""Mobile notification read-all ownership and cutoff regression tests."""
from datetime import timedelta, timezone
import json

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main, mobile_api


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_mobile_notification_read_all_is_owner_scoped_and_respects_cutoff(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "mobile-notifications.db"),
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(mobile_api, "engine", engine)
    monkeypatch.setattr(mobile_api, "on_loop", lambda *_args: None)

    now = main._utcnow_naive()
    cutoff = now - timedelta(minutes=5)
    owner_token = "mobile-notice-owner-token"
    other_token = "mobile-notice-other-token"
    with Session(engine, expire_on_commit=False) as session:
        owner = main.User(
            username="mobile-notice-owner", role="DOCTOR",
            display_name="Owner", email_verified_at=now,
        )
        other = main.User(
            username="mobile-notice-other", role="DOCTOR",
            display_name="Other", email_verified_at=now,
        )
        session.add_all([owner, other])
        session.commit()
        session.add_all([
            main.SessionToken(
                token_hash=main.hash_session_token(owner_token), user_id=owner.id,
                expires_at=now + timedelta(days=1),
            ),
            main.SessionToken(
                token_hash=main.hash_session_token(other_token), user_id=other.id,
                expires_at=now + timedelta(days=1),
            ),
        ])
        old_notice = main.AdminNotice(
            user_id=owner.id, title="Eski", message="İçerik", notice_type="TEST",
            status="ACTIVE", is_read=False, created_at=cutoff - timedelta(minutes=1),
        )
        future_notices = [
            main.AdminNotice(
                user_id=owner.id, title=f"Yeni {index}", message="İçerik", notice_type="TEST",
                status="ACTIVE", is_read=False, created_at=cutoff + timedelta(seconds=index + 1),
            )
            for index in range(25)
        ]
        stale_read_at_notice = main.AdminNotice(
            user_id=owner.id, title="Okunmamış eski işaret", message="İçerik", notice_type="TEST",
            status="ACTIVE", is_read=False, read_at=cutoff + timedelta(seconds=27),
            created_at=cutoff + timedelta(seconds=26),
        )
        legacy_read_notice = main.AdminNotice(
            user_id=owner.id, title="Eski okundu işareti", message="İçerik", notice_type="TEST",
            status="ACTIVE", is_read=True, read_at=None, created_at=cutoff + timedelta(seconds=28),
        )
        other_notice = main.AdminNotice(
            user_id=other.id, title="Diğer", message="İçerik", notice_type="TEST",
            status="ACTIVE", is_read=False, created_at=cutoff - timedelta(minutes=1),
        )
        resolved_notice = main.AdminNotice(
            user_id=owner.id, title="Çözüldü", message="İçerik", notice_type="TEST",
            status="RESOLVED", is_read=False, created_at=cutoff - timedelta(minutes=1),
        )
        session.add_all([old_notice, *future_notices, stale_read_at_notice, legacy_read_notice, other_notice, resolved_notice])
        session.commit()
        owner_id, other_id = owner.id, other.id
        old_id, future_ids = old_notice.id, [notice.id for notice in future_notices]
        stale_read_at_id, legacy_read_id = stale_read_at_notice.id, legacy_read_notice.id
        other_id_notice, resolved_id = other_notice.id, resolved_notice.id

    payload = {"seen_before": cutoff.replace(tzinfo=timezone.utc).isoformat()}
    headers = {"Authorization": "Bearer " + owner_token}
    with TestClient(main.app) as client:
        first = client.post("/api/mobile/v1/notifications/read-all", headers=headers, json=payload)
        assert first.status_code == 200, first.text
        assert first.json() == {"ok": True, "read_count": 1, "unread_count": 26}
        replay = client.post("/api/mobile/v1/notifications/read-all", headers=headers, json=payload)
        assert replay.status_code == 200
        assert replay.json() == {"ok": True, "read_count": 0, "unread_count": 26}
        listing = client.get("/api/mobile/v1/notifications", headers=headers)
        assert listing.status_code == 200
        assert len(listing.json()["notifications"]) == 20
        assert listing.json()["unread_count"] == 26
        listed_items = listing.json()["items"]
        stale_item = next(item for item in listed_items if item["id"] == stale_read_at_id)
        legacy_item = next(item for item in listed_items if item["id"] == legacy_read_id)
        assert stale_item["is_read"] is False and stale_item["read_at"] is not None
        assert legacy_item["is_read"] is True and legacy_item["read_at"] is None

        count = client.get("/api/mobile/v1/notifications/unread-count", headers=headers)
        assert count.status_code == 200
        assert count.json() == {"unread_count": 26}
        assert set(count.json()) == {"unread_count"}, "the badge endpoint must not return notice content"
        assert "no-store" in count.headers.get("cache-control", "").lower()
        assert "authorization" in count.headers.get("vary", "").lower()
        other_count = client.get(
            "/api/mobile/v1/notifications/unread-count",
            headers={"Authorization": "Bearer " + other_token},
        )
        assert other_count.status_code == 200
        assert other_count.json() == {"unread_count": 1}
        assert client.get("/api/mobile/v1/notifications/unread-count").status_code == 401
        assert client.post("/api/mobile/v1/notifications/read-all", json=payload).status_code == 401
        assert client.post(
            "/api/mobile/v1/notifications/read-all", headers=headers,
            json={"seen_before": "not-a-date"},
        ).status_code == 422

    with Session(engine) as session:
        old_row = session.get(main.AdminNotice, old_id)
        future_rows = [session.get(main.AdminNotice, notice_id) for notice_id in future_ids]
        other_row = session.get(main.AdminNotice, other_id_notice)
        resolved_row = session.get(main.AdminNotice, resolved_id)
        stale_read_at_row = session.get(main.AdminNotice, stale_read_at_id)
        legacy_read_row = session.get(main.AdminNotice, legacy_read_id)
        events = session.exec(select(main.RealtimeEvent).where(
            main.RealtimeEvent.user_id == owner_id,
            main.RealtimeEvent.event_type == "NOTIFICATIONS_READ",
        )).all()
    assert old_row.is_read is True and old_row.read_at is not None
    assert all(row.is_read is False and row.read_at is None for row in future_rows)
    assert other_row.is_read is False and other_row.read_at is None
    assert resolved_row.is_read is False and resolved_row.read_at is None
    assert stale_read_at_row.is_read is False and stale_read_at_row.read_at is not None
    assert legacy_read_row.is_read is True and legacy_read_row.read_at is None
    assert len(events) == 1
    assert json.loads(events[0].payload_json)["unread_count"] == 26
