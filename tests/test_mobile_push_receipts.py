"""Durable Expo receipt state, owner binding and migration regressions."""
from datetime import timedelta
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from app import main
from app.mobile_push import token_fingerprint
from app.mobile_push_receipts import (
    complete_mobile_push_deliveries,
    poll_due_mobile_push_receipts,
    reserve_mobile_push_deliveries,
)


def _engine(tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "expo-receipts.db"),
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    now = main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username="push-receipt-owner", role="DOCTOR", display_name="Owner")
        session.add(user)
        session.commit()
        device = main.MobilePushDevice(
            user_id=user.id,
            device_id=str(uuid.uuid4()),
            expo_push_token="ExpoPushToken[abcdefgh12345678]",
            platform="android",
            enabled=True,
        )
        session.add(device)
        session.commit()
        session.refresh(device)
        return engine, user.id, device.device_id, device.expo_push_token


def _pending(engine, user_id, device_id, token, *, age_minutes=20, due_minutes=1):
    stamp = main._utcnow_naive()
    receipt_id = str(uuid.uuid4())
    row = main.MobilePushDelivery(
        event_id=991,
        user_id=user_id,
        device_id=device_id,
        token_fingerprint=token_fingerprint(token),
        ticket_id=receipt_id,
        status="PENDING_RECEIPT",
        next_check_at=stamp - timedelta(minutes=due_minutes),
        created_at=stamp - timedelta(minutes=age_minutes),
        updated_at=stamp - timedelta(minutes=age_minutes),
    )
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id, receipt_id


def test_event_device_reservation_is_idempotent_and_stores_no_raw_token(tmp_path):
    engine, user_id, device_id, token = _engine(tmp_path)
    with Session(engine) as session:
        device = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()

    first = reserve_mobile_push_deliveries(
        engine, event_id=44, user_id=user_id, devices=[device],
    )
    replay = reserve_mobile_push_deliveries(
        engine, event_id=44, user_id=user_id, devices=[device],
    )

    assert len(first) == 1
    assert replay == []
    assert first[0]["token"] == token  # transient send input only
    with Session(engine) as session:
        rows = session.exec(select(main.MobilePushDelivery)).all()
    assert len(rows) == 1
    assert rows[0].token_fingerprint == token_fingerprint(token)
    assert not hasattr(rows[0], "expo_push_token")
    columns = set(rows[0].__table__.columns.keys())
    assert not ({"expo_push_token", "title", "body", "message", "payload_json"} & columns)


def test_reservation_rechecks_opt_out_after_device_snapshot(tmp_path):
    engine, user_id, device_id, token = _engine(tmp_path)
    with Session(engine) as session:
        stale_snapshot = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()

    # The sender's initial SELECT happened before the user opted out.
    with Session(engine) as session:
        current = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()
        current.enabled = False
        session.add(current)
        session.commit()

    reserved = reserve_mobile_push_deliveries(
        engine, event_id=443, user_id=user_id, devices=[stale_snapshot],
    )
    assert reserved == []
    with Session(engine) as session:
        assert session.exec(select(main.MobilePushDelivery)).all() == []
    engine.dispose()


def test_reservation_uses_rotated_live_token_not_stale_snapshot(tmp_path):
    engine, user_id, device_id, old_token = _engine(tmp_path)
    with Session(engine) as session:
        stale_snapshot = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()

    new_token = "ExpoPushToken[abcdefgh87654321]"
    with Session(engine) as session:
        current = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()
        current.expo_push_token = new_token
        session.add(current)
        session.commit()

    reserved = reserve_mobile_push_deliveries(
        engine, event_id=444, user_id=user_id, devices=[stale_snapshot],
    )
    assert len(reserved) == 1
    assert reserved[0]["token"] == new_token
    assert reserved[0]["token"] != old_token
    assert reserved[0]["token_fingerprint"] == token_fingerprint(new_token)
    with Session(engine) as session:
        row = session.exec(select(main.MobilePushDelivery)).one()
    assert row.token_fingerprint == token_fingerprint(new_token)
    engine.dispose()


def test_reservation_deduplicates_candidates_and_ignores_other_owner(tmp_path):
    engine, user_id, device_id, token = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as session:
        owner_device = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()
        other = main.User(username="push-receipt-other", role="DOCTOR", display_name="Other")
        session.add(other)
        session.commit()
        other_device = main.MobilePushDevice(
            user_id=other.id,
            device_id=str(uuid.uuid4()),
            expo_push_token="ExpoPushToken[otherdevice123456]",
            platform="ios",
            enabled=True,
        )
        session.add(other_device)
        session.commit()
        session.refresh(other_device)

    reserved = reserve_mobile_push_deliveries(
        engine,
        event_id=445,
        user_id=user_id,
        devices=[owner_device, owner_device, other_device],
    )
    assert len(reserved) == 1
    assert reserved[0]["device_id"] == device_id
    assert reserved[0]["token"] == token
    with Session(engine) as session:
        rows = session.exec(select(main.MobilePushDelivery)).all()
    assert len(rows) == 1
    assert rows[0].user_id == user_id
    engine.dispose()


def test_disabled_transport_does_not_leave_a_receipt_poll_pending(tmp_path):
    engine, user_id, device_id, token = _engine(tmp_path)
    with Session(engine) as session:
        device = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()
    reserved = reserve_mobile_push_deliveries(
        engine, event_id=441, user_id=user_id, devices=[device],
    )
    complete_mobile_push_deliveries(engine, reserved, {
        "enabled": False, "tickets": [], "errors": [],
    })
    with Session(engine) as session:
        row = session.exec(select(main.MobilePushDelivery)).one()
    assert row.status == "SEND_DISABLED"
    assert row.error_code == "PUSH_DISABLED"
    assert row.ticket_id is None


def test_definite_http_rejection_is_not_marked_as_ambiguous(tmp_path):
    engine, user_id, device_id, token = _engine(tmp_path)
    with Session(engine) as session:
        device = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()
    reserved = reserve_mobile_push_deliveries(
        engine, event_id=442, user_id=user_id, devices=[device],
    )
    complete_mobile_push_deliveries(engine, reserved, {
        "enabled": True, "tickets": [],
        "errors": [{"error_code": "HTTP_429", "ambiguous": False}],
    })
    with Session(engine) as session:
        row = session.exec(select(main.MobilePushDelivery)).one()
    assert row.status == "SEND_FAILED"
    assert row.error_code == "HTTP_429"


def test_ticket_acknowledgement_is_durable_and_schedules_first_receipt_check(tmp_path):
    engine, user_id, device_id, token = _engine(tmp_path)
    with Session(engine) as session:
        device = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()
    reserved = reserve_mobile_push_deliveries(
        engine, event_id=45, user_id=user_id, devices=[device],
    )
    receipt_id = str(uuid.uuid4())
    completed = complete_mobile_push_deliveries(engine, reserved, {
        "tickets": [{
            "token_fingerprint": token_fingerprint(token),
            "status": "ok",
            "ticket_id": receipt_id,
            "error_code": None,
        }],
        "errors": [],
    })

    assert completed == 1
    with Session(engine) as session:
        row = session.exec(select(main.MobilePushDelivery)).one()
    assert row.status == "PENDING_RECEIPT"
    assert row.ticket_id == receipt_id
    assert row.next_check_at >= main._utcnow_naive() + timedelta(minutes=14)
    assert row.token_fingerprint == token_fingerprint(token)


def test_ticket_level_device_not_registered_disables_only_matching_device(tmp_path):
    engine, user_id, device_id, token = _engine(tmp_path)
    with Session(engine) as session:
        device = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()
    reserved = reserve_mobile_push_deliveries(
        engine, event_id=46, user_id=user_id, devices=[device],
    )
    complete_mobile_push_deliveries(engine, reserved, {
        "tickets": [{
            "token_fingerprint": token_fingerprint(token),
            "status": "error",
            "ticket_id": None,
            "error_code": "DeviceNotRegistered",
        }],
        "errors": [],
    })

    with Session(engine) as session:
        device = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()
        row = session.exec(select(main.MobilePushDelivery)).one()
    assert device.enabled is False
    assert row.status == "DEVICE_NOT_REGISTERED"


def test_ok_receipt_means_provider_accepted_not_device_delivered(tmp_path, monkeypatch):
    import app.mobile_push_receipts as receipts

    engine, user_id, device_id, token = _engine(tmp_path)
    _, receipt_id = _pending(engine, user_id, device_id, token)
    monkeypatch.setattr(receipts, "get_push_receipts", lambda ids: {
        "ok": True, "receipts": {receipt_id: {"status": "ok"}},
    })

    assert poll_due_mobile_push_receipts(engine) == 1
    with Session(engine) as session:
        row = session.exec(select(main.MobilePushDelivery)).one()
        device = session.exec(select(main.MobilePushDevice)).one()
    assert row.status == "PROVIDER_ACCEPTED"
    assert row.checked_at is not None
    assert device.enabled is True


def test_receipt_device_not_registered_disables_only_the_same_token(tmp_path, monkeypatch):
    import app.mobile_push_receipts as receipts

    engine, user_id, device_id, token = _engine(tmp_path)
    _, receipt_id = _pending(engine, user_id, device_id, token)
    monkeypatch.setattr(receipts, "get_push_receipts", lambda ids: {
        "ok": True, "receipts": {
            receipt_id: {"status": "error", "details": {"error": "DeviceNotRegistered"}},
        },
    })

    assert poll_due_mobile_push_receipts(engine) == 1
    with Session(engine) as session:
        row = session.exec(select(main.MobilePushDelivery)).one()
        device = session.exec(select(main.MobilePushDevice)).one()
    assert row.status == "DEVICE_NOT_REGISTERED"
    assert device.enabled is False


def test_stale_receipt_cannot_disable_a_rotated_device_token(tmp_path, monkeypatch):
    import app.mobile_push_receipts as receipts

    engine, user_id, device_id, old_token = _engine(tmp_path)
    _, receipt_id = _pending(engine, user_id, device_id, old_token)
    new_token = "ExpoPushToken[abcdefgh87654321]"
    with Session(engine) as session:
        device = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == user_id,
            main.MobilePushDevice.device_id == device_id,
        )).one()
        device.expo_push_token = new_token
        session.add(device)
        session.commit()
    monkeypatch.setattr(receipts, "get_push_receipts", lambda ids: {
        "ok": True, "receipts": {
            receipt_id: {"status": "error", "details": {"error": "DeviceNotRegistered"}},
        },
    })

    assert poll_due_mobile_push_receipts(engine) == 1
    with Session(engine) as session:
        row = session.exec(select(main.MobilePushDelivery)).one()
        device = session.exec(select(main.MobilePushDevice)).one()
    assert row.status == "DEVICE_NOT_REGISTERED"
    assert device.expo_push_token == new_token
    assert device.enabled is True


def test_missing_receipt_is_rescheduled_without_deactivating_device(tmp_path, monkeypatch):
    import app.mobile_push_receipts as receipts

    engine, user_id, device_id, token = _engine(tmp_path)
    _, receipt_id = _pending(engine, user_id, device_id, token)
    monkeypatch.setattr(receipts, "get_push_receipts", lambda ids: {
        "ok": True, "receipts": {},
    })

    assert poll_due_mobile_push_receipts(engine) == 1
    with Session(engine) as session:
        row = session.exec(select(main.MobilePushDelivery)).one()
        device = session.exec(select(main.MobilePushDevice)).one()
    assert row.status == "PENDING_RECEIPT"
    assert row.attempts == 1
    assert row.next_check_at >= main._utcnow_naive() + timedelta(minutes=14)
    assert row.error_code == "RECEIPT_NOT_READY"
    assert device.enabled is True


def test_missing_receipt_expires_after_expo_retention_window(tmp_path, monkeypatch):
    import app.mobile_push_receipts as receipts

    engine, user_id, device_id, token = _engine(tmp_path)
    row_id, receipt_id = _pending(engine, user_id, device_id, token, age_minutes=25 * 60)
    monkeypatch.setattr(receipts, "get_push_receipts", lambda ids: {
        "ok": True, "receipts": {},
    })

    assert poll_due_mobile_push_receipts(engine) == 1
    with Session(engine) as session:
        row = session.get(main.MobilePushDelivery, row_id)
    assert row.status == "RECEIPT_EXPIRED"
    assert row.error_code == "RECEIPT_NOT_READY"


def test_terminal_receipt_cleanup_processes_a_bounded_thousand_rows(tmp_path):
    from app.mobile_push_receipts import _maintain_receipt_rows

    engine, user_id, _, _ = _engine(tmp_path)
    old = main._utcnow_naive() - timedelta(days=31)
    with Session(engine) as session:
        session.add_all([
            main.MobilePushDelivery(
                event_id=10000 + index,
                user_id=user_id,
                device_id=str(uuid.uuid4()),
                token_fingerprint=f"{index:064x}",
                status="PROVIDER_ACCEPTED",
                created_at=old,
                updated_at=old,
                checked_at=old,
            )
            for index in range(1005)
        ])
        session.commit()

    assert _maintain_receipt_rows(engine) == 1000
    with Session(engine) as session:
        remaining = session.exec(select(main.MobilePushDelivery)).all()
    assert len(remaining) == 5
    engine.dispose()


def test_receipt_poll_batch_is_bounded_to_five_hundred(tmp_path):
    from app.mobile_push_receipts import RECEIPT_BATCH_LIMIT

    engine, _, _, _ = _engine(tmp_path)
    assert RECEIPT_BATCH_LIMIT == 500
    with pytest.raises(ValueError, match="between 1 and 500"):
        poll_due_mobile_push_receipts(engine, limit=501)
    engine.dispose()


def test_receipt_maintenance_rejects_unbounded_batch_size(tmp_path):
    from app.mobile_push_receipts import _maintain_receipt_rows

    engine, _, _, _ = _engine(tmp_path)
    with pytest.raises(ValueError, match="between 1 and 1,000"):
        _maintain_receipt_rows(engine, limit=1001)
    engine.dispose()


def test_worker_receipt_checks_are_throttled_instead_of_per_queue_iteration(monkeypatch):
    import app.mobile_push_receipts as receipts

    clock = {"now": 1000.0}
    calls = []
    monkeypatch.setattr(receipts.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(receipts, "_last_poll_at", 0.0)
    monkeypatch.setattr(receipts, "_last_maintenance_at", 0.0)
    monkeypatch.setattr(
        receipts, "poll_due_mobile_push_receipts",
        lambda engine: calls.append("poll") or 0,
    )
    monkeypatch.setattr(
        receipts, "_maintain_receipt_rows",
        lambda engine: calls.append("maintenance") or 0,
    )

    assert receipts.run_mobile_push_receipt_maintenance(object()) is False
    assert calls == ["poll", "maintenance"]

    clock["now"] = 1059.0
    assert receipts.run_mobile_push_receipt_maintenance(object()) is False
    assert calls == ["poll", "maintenance"]

    clock["now"] = 1060.0
    assert receipts.run_mobile_push_receipt_maintenance(object()) is False
    assert calls == ["poll", "maintenance", "poll"]

    clock["now"] = 1300.0
    assert receipts.run_mobile_push_receipt_maintenance(object()) is False
    assert calls == ["poll", "maintenance", "poll", "poll", "maintenance"]


def test_existing_revision_15_schema_bootstraps_both_push_tables(tmp_path):
    from app import migrate

    engine = create_engine(
        "sqlite:///" + str(tmp_path / "schema-push-receipts.db"),
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO dental_schema_revision (id, version) VALUES (1, 15)"
        ))

    migrate.require_schema(engine)

    inspector = inspect(engine)
    assert inspector.has_table("mobilepushdevice")
    assert inspector.has_table("mobilepushdelivery")
    columns = {column["name"] for column in inspector.get_columns("mobilepushdelivery")}
    assert {
        "event_id", "user_id", "device_id", "token_fingerprint", "ticket_id",
        "status", "error_code", "attempts", "next_check_at", "lease_token",
        "lease_until", "created_at", "updated_at", "checked_at",
    }.issubset(columns)
    assert not ({"expo_push_token", "title", "body", "message", "payload_json"} & columns)
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT version FROM dental_schema_revision WHERE id=1"
        )).scalar_one() == 15
    engine.dispose()


def test_receipt_poll_rejects_boolean_batch_limit(tmp_path):
    engine, _, _, _ = _engine(tmp_path)
    with pytest.raises(ValueError, match="between 1 and 500"):
        poll_due_mobile_push_receipts(engine, limit=True)
    engine.dispose()


def test_receipt_maintenance_recovers_rows_with_missing_leases(tmp_path):
    from app.mobile_push_receipts import _maintain_receipt_rows

    engine, user_id, device_id, token = _engine(tmp_path)
    stamp = main._utcnow_naive()
    with Session(engine) as session:
        session.add_all([
            main.MobilePushDelivery(
                event_id=9101, user_id=user_id, device_id=device_id,
                token_fingerprint=token_fingerprint(token), status="SENDING",
                lease_token=None, lease_until=None,
                created_at=stamp - timedelta(minutes=5),
                updated_at=stamp - timedelta(minutes=5),
            ),
            main.MobilePushDelivery(
                event_id=9102, user_id=user_id, device_id=device_id,
                token_fingerprint=token_fingerprint(token), ticket_id=str(uuid.uuid4()),
                status="CHECKING", attempts=1, lease_token=None, lease_until=None,
                created_at=stamp - timedelta(minutes=20),
                updated_at=stamp - timedelta(minutes=5),
            ),
        ])
        session.commit()

    assert _maintain_receipt_rows(engine) == 2
    with Session(engine) as session:
        rows = {
            row.event_id: row
            for row in session.exec(select(main.MobilePushDelivery)).all()
        }
    assert rows[9101].status == "SEND_UNCERTAIN"
    assert rows[9101].error_code == "SENDER_LEASE_EXPIRED"
    assert rows[9102].status == "PENDING_RECEIPT"
    assert rows[9102].error_code == "CHECK_LEASE_EXPIRED"
    assert rows[9102].next_check_at >= stamp + timedelta(minutes=4)
    assert rows[9101].lease_token is None and rows[9102].lease_token is None
    engine.dispose()


def test_invalid_receipt_ticket_does_not_poison_valid_provider_batch(tmp_path, monkeypatch):
    import app.mobile_push_receipts as receipts

    engine, user_id, device_id, token = _engine(tmp_path)
    stamp = main._utcnow_naive()
    valid_ticket = str(uuid.uuid4())
    with Session(engine) as session:
        session.add_all([
            main.MobilePushDelivery(
                event_id=9201, user_id=user_id, device_id=device_id,
                token_fingerprint=token_fingerprint(token), ticket_id=valid_ticket,
                status="PENDING_RECEIPT", next_check_at=stamp - timedelta(minutes=1),
                created_at=stamp - timedelta(minutes=20), updated_at=stamp - timedelta(minutes=1),
            ),
            main.MobilePushDelivery(
                event_id=9202, user_id=user_id, device_id=device_id,
                token_fingerprint=token_fingerprint(token), ticket_id="not-a-provider-uuid",
                status="PENDING_RECEIPT", next_check_at=stamp - timedelta(minutes=1),
                created_at=stamp - timedelta(minutes=20), updated_at=stamp - timedelta(minutes=1),
            ),
        ])
        session.commit()

    requested = []
    monkeypatch.setattr(receipts, "get_push_receipts", lambda ids: (
        requested.append(ids) or {
            "ok": True,
            "receipts": {valid_ticket: {"status": "ok"}},
        }
    ))

    assert poll_due_mobile_push_receipts(engine) == 2
    assert requested == [[valid_ticket]]
    with Session(engine) as session:
        rows = {
            row.event_id: row
            for row in session.exec(select(main.MobilePushDelivery)).all()
        }
    assert rows[9201].status == "PROVIDER_ACCEPTED"
    assert rows[9202].status == "RECEIPT_ERROR"
    assert rows[9202].error_code == "INVALID_TICKET"
    engine.dispose()
