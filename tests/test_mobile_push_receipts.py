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
    assert not ({"title", "body", "message", "payload_json"} & set(rows[0].model_fields_set))


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
