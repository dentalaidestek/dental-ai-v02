"""Owner-scoped native push registration and notification deep-link tests."""
from datetime import timedelta
import hashlib
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main, mobile_api


def _client_db(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "mobile-push-registration.db"),
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(mobile_api, "engine", engine)
    now = main._utcnow_naive()
    owner_token = "mobile-push-owner-session"
    other_token = "mobile-push-other-session"
    with Session(engine, expire_on_commit=False) as session:
        owner = main.User(
            username="mobile-push-owner", role="DOCTOR",
            display_name="Owner", email_verified_at=now,
        )
        other = main.User(
            username="mobile-push-other", role="DOCTOR",
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
        session.commit()
        owner_id, other_id = owner.id, other.id
    return engine, owner_id, other_id, owner_token, other_token


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_push_registration_is_strict_owner_scoped_and_revocable(monkeypatch, tmp_path):
    monkeypatch.delenv("MOBILE_PUSH_ENABLED", raising=False)
    engine, owner_id, other_id, owner_token, other_token = _client_db(monkeypatch, tmp_path)
    device_id = str(uuid.uuid4())
    push_token = "ExpoPushToken[abcdefgh12345678]"
    owner_headers = {"Authorization": "Bearer " + owner_token}
    other_headers = {"Authorization": "Bearer " + other_token}

    with TestClient(main.app) as client:
        registered = client.post(
            "/api/mobile/v1/push/devices",
            headers=owner_headers,
            json={"device_id": device_id, "expo_push_token": push_token, "platform": "android"},
        )
        assert registered.status_code == 200, registered.text
        assert registered.headers.get("cache-control") == "private, no-store"
        assert registered.json()["delivery_enabled"] is False

        conflict = client.post(
            "/api/mobile/v1/push/devices",
            headers=other_headers,
            json={"device_id": str(uuid.uuid4()), "expo_push_token": push_token, "platform": "ios"},
        )
        assert conflict.status_code == 409

        invalid_device = client.post(
            "/api/mobile/v1/push/devices",
            headers=owner_headers,
            json={"device_id": "device-from-client", "expo_push_token": push_token, "platform": "android"},
        )
        assert invalid_device.status_code == 422
        invalid_token = client.post(
            "/api/mobile/v1/push/devices",
            headers=owner_headers,
            json={"device_id": str(uuid.uuid4()), "expo_push_token": "ExpoPushToken[bad token]", "platform": "android"},
        )
        assert invalid_token.status_code == 422

        # Another account cannot revoke a device by guessing its stable ID.
        other_delete = client.delete(f"/api/mobile/v1/push/devices/{device_id}", headers=other_headers)
        assert other_delete.status_code == 200
        with Session(engine) as session:
            row = session.exec(select(main.MobilePushDevice).where(
                main.MobilePushDevice.user_id == owner_id,
                main.MobilePushDevice.device_id == device_id,
            )).first()
        assert row is not None

        owner_delete = client.delete(f"/api/mobile/v1/push/devices/{device_id}", headers=owner_headers)
        assert owner_delete.status_code == 200
        assert owner_delete.headers.get("cache-control") == "private, no-store"
        repeated_delete = client.delete(f"/api/mobile/v1/push/devices/{device_id}", headers=owner_headers)
        assert repeated_delete.status_code == 200

    with Session(engine) as session:
        assert session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == owner_id,
        )).all() == []
        assert session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == other_id,
        )).all() == []


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_push_refresh_replaces_same_device_and_caps_account_devices(monkeypatch, tmp_path):
    engine, owner_id, _, owner_token, _ = _client_db(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer " + owner_token}
    first_device = str(uuid.uuid4())

    with TestClient(main.app) as client:
        first = client.post(
            "/api/mobile/v1/push/devices", headers=headers,
            json={"device_id": first_device, "expo_push_token": "ExpoPushToken[abcdefgh00000001]", "platform": "android"},
        )
        assert first.status_code == 200
        refreshed = client.post(
            "/api/mobile/v1/push/devices", headers=headers,
            json={"device_id": first_device, "expo_push_token": "ExpoPushToken[abcdefgh00000002]", "platform": "ios"},
        )
        assert refreshed.status_code == 200

        for index in range(9):
            response = client.post(
                "/api/mobile/v1/push/devices", headers=headers,
                json={
                    "device_id": str(uuid.uuid4()),
                    "expo_push_token": f"ExpoPushToken[device{index:04d}abcdef]",
                    "platform": "android",
                },
            )
            assert response.status_code == 200, response.text

        overflow = client.post(
            "/api/mobile/v1/push/devices", headers=headers,
            json={
                "device_id": str(uuid.uuid4()),
                "expo_push_token": "ExpoPushToken[overflow00000001]",
                "platform": "android",
            },
        )
        assert overflow.status_code == 409

    with Session(engine) as session:
        rows = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == owner_id,
        )).all()
    assert len(rows) == 10
    assert sum(row.device_id == first_device for row in rows) == 1
    assert all(row.expo_push_token != "ExpoPushToken[abcdefgh00000001]" for row in rows)


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_notification_push_lookup_includes_only_requested_owners_notice(monkeypatch, tmp_path):
    engine, owner_id, other_id, owner_token, other_token = _client_db(monkeypatch, tmp_path)
    now = main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as session:
        notices = [
            main.AdminNotice(
                user_id=owner_id, title=f"Notice {index}", message="Genel bildirim",
                notice_type="TEST", status="ACTIVE", created_at=now - timedelta(minutes=index),
            )
            for index in range(21)
        ]
        other_notice = main.AdminNotice(
            user_id=other_id, title="Other notice", message="Genel bildirim",
            notice_type="TEST", status="ACTIVE", created_at=now,
        )
        session.add_all([*notices, other_notice])
        session.commit()
        oldest_id = notices[-1].id

    with TestClient(main.app) as client:
        owner_headers = {"Authorization": "Bearer " + owner_token}
        other_headers = {"Authorization": "Bearer " + other_token}
        page = client.get("/api/mobile/v1/notifications", headers=owner_headers)
        assert page.status_code == 200
        assert page.headers.get("cache-control") == "private, no-store"
        assert len(page.json()["items"]) == 20

        deep_link = client.get(
            f"/api/mobile/v1/notifications?notice_id={oldest_id}",
            headers=owner_headers,
        )
        assert deep_link.status_code == 200
        assert len(deep_link.json()["items"]) == 21
        assert oldest_id in {item["id"] for item in deep_link.json()["items"]}

        other_lookup = client.get(
            f"/api/mobile/v1/notifications?notice_id={oldest_id}",
            headers=other_headers,
        )
        assert other_lookup.status_code == 200
        assert len(other_lookup.json()["items"]) == 1
        assert all(item["id"] != oldest_id for item in other_lookup.json()["items"])



@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
@pytest.mark.parametrize("prefix", ["ExpoPushToken", "ExponentPushToken"])
def test_push_registration_accepts_both_canonical_expo_prefixes(monkeypatch, tmp_path, prefix):
    engine, owner_id, _, owner_token, _ = _client_db(monkeypatch, tmp_path)
    device_id = str(uuid.uuid4())
    headers = {"Authorization": "Bearer " + owner_token}
    token = f"{prefix}[abcdefgh12345678]"

    with TestClient(main.app) as client:
        response = client.post(
            "/api/mobile/v1/push/devices",
            headers=headers,
            json={"device_id": device_id, "expo_push_token": token, "platform": "android"},
        )
        assert response.status_code == 200, response.text
        assert response.headers.get("cache-control") == "private, no-store"

    with Session(engine) as session:
        row = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == owner_id,
            main.MobilePushDevice.device_id == device_id,
        )).first()
    assert row is not None
    assert row.expo_push_token == token
    engine.dispose()


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
@pytest.mark.parametrize("token", [
    "ExpoPushToken[short]",
    "ExpoPushToken[bad token]",
    r"ExpoPushToken\[abcdefgh12345678\]",
    "ExpoPushToken[" + "a" * 129 + "]",
    "OtherPushToken[abcdefgh12345678]",
])
def test_push_registration_rejects_noncanonical_token_shapes(monkeypatch, tmp_path, token):
    engine, _, _, owner_token, _ = _client_db(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer " + owner_token}
    with TestClient(main.app) as client:
        response = client.post(
            "/api/mobile/v1/push/devices",
            headers=headers,
            json={"device_id": str(uuid.uuid4()), "expo_push_token": token, "platform": "android"},
        )
    assert response.status_code == 422
    engine.dispose()


def test_revision_15_push_device_bootstrap_keeps_release_guard_strict(tmp_path):
    from app import migrate

    engine = create_engine(
        "sqlite:///" + str(tmp_path / "schema-push.db"),
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO dental_schema_revision (id, version) VALUES (1, 15)"
        ))
        # Simulate a production revision-15 table created before installation proofs.
        connection.execute(text(
            "CREATE TABLE mobilepushdevice (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "device_id VARCHAR NOT NULL, expo_push_token VARCHAR NOT NULL UNIQUE, "
            "platform VARCHAR NOT NULL, enabled BOOLEAN NOT NULL, updated_at DATETIME NOT NULL)"
        ))

    migrate._ensure_mobile_push_device_table(engine)
    with pytest.raises(RuntimeError, match="Expected schema revision 19"):
        migrate.require_schema(engine)

    inspector = inspect(engine)
    assert inspector.has_table("mobilepushdevice")
    columns = {column["name"] for column in inspector.get_columns("mobilepushdevice")}
    assert {"user_id", "device_id", "device_proof_hash", "expo_push_token", "platform", "enabled", "updated_at"}.issubset(columns)
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT version FROM dental_schema_revision WHERE id=1"
        )).scalar_one() == 15
    engine.dispose()


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_device_claim_revokes_previous_account_before_optional_push_opt_in(monkeypatch, tmp_path):
    engine, owner_id, other_id, owner_token, other_token = _client_db(monkeypatch, tmp_path)
    device_id = str(uuid.uuid4())
    proof = "a" * 64
    owner_headers = {"Authorization": "Bearer " + owner_token}
    other_headers = {"Authorization": "Bearer " + other_token}

    with TestClient(main.app) as client:
        registered = client.post(
            "/api/mobile/v1/push/devices",
            headers=owner_headers,
            json={
                "device_id": device_id,
                "expo_push_token": "ExpoPushToken[abcdefgh11111111]",
                "platform": "android",
                "installation_proof": proof,
            },
        )
        assert registered.status_code == 200, registered.text

        # A new account on the same installation claims the device even if it
        # has not opted into notifications and therefore must not register a token.
        claimed = client.post(
            "/api/mobile/v1/push/devices/claim",
            headers=other_headers,
            json={"device_id": device_id, "installation_proof": proof},
        )
        assert claimed.status_code == 200, claimed.text
        assert claimed.headers.get("cache-control") == "private, no-store"
        assert claimed.json()["revoked_previous_owners"] == 1

        with Session(engine) as session:
            assert session.exec(select(main.MobilePushDevice).where(
                main.MobilePushDevice.device_id == device_id,
            )).all() == []

        # Opt-in remains a separate, explicit action for the new account.
        registered_new = client.post(
            "/api/mobile/v1/push/devices",
            headers=other_headers,
            json={
                "device_id": device_id,
                "expo_push_token": "ExpoPushToken[abcdefgh22222222]",
                "platform": "ios",
                "installation_proof": proof,
            },
        )
        assert registered_new.status_code == 200, registered_new.text

    with Session(engine) as session:
        rows = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.device_id == device_id,
        )).all()
    assert len(rows) == 1
    assert rows[0].user_id == other_id
    assert rows[0].device_proof_hash == hashlib.sha256(proof.encode()).hexdigest()
    engine.dispose()


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_device_claim_rejects_another_installations_proof_without_deleting_owner(monkeypatch, tmp_path):
    engine, owner_id, _, owner_token, other_token = _client_db(monkeypatch, tmp_path)
    device_id = str(uuid.uuid4())
    owner_proof = "b" * 64
    attacker_proof = "c" * 64
    with TestClient(main.app) as client:
        registered = client.post(
            "/api/mobile/v1/push/devices",
            headers={"Authorization": "Bearer " + owner_token},
            json={
                "device_id": device_id,
                "expo_push_token": "ExpoPushToken[abcdefgh33333333]",
                "platform": "android",
                "installation_proof": owner_proof,
            },
        )
        assert registered.status_code == 200
        claimed = client.post(
            "/api/mobile/v1/push/devices/claim",
            headers={"Authorization": "Bearer " + other_token},
            json={"device_id": device_id, "installation_proof": attacker_proof},
        )
        assert claimed.status_code == 409

    with Session(engine) as session:
        rows = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.device_id == device_id,
        )).all()
    assert len(rows) == 1
    assert rows[0].user_id == owner_id
    assert rows[0].device_proof_hash == hashlib.sha256(owner_proof.encode()).hexdigest()
    engine.dispose()


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_registration_transfers_legacy_device_row_and_stores_new_proof(monkeypatch, tmp_path):
    engine, _, other_id, _, other_token = _client_db(monkeypatch, tmp_path)
    device_id = str(uuid.uuid4())
    proof = "d" * 64
    with Session(engine) as session:
        legacy_owner = main.User(username="legacy-push-owner", role="DOCTOR", display_name="Legacy")
        session.add(legacy_owner)
        session.commit()
        session.add(main.MobilePushDevice(
            user_id=legacy_owner.id,
            device_id=device_id,
            expo_push_token="ExpoPushToken[abcdefgh44444444]",
            platform="android",
            enabled=True,
        ))
        session.commit()
        legacy_owner_id = legacy_owner.id

    with TestClient(main.app) as client:
        transferred = client.post(
            "/api/mobile/v1/push/devices",
            headers={"Authorization": "Bearer " + other_token},
            json={
                "device_id": device_id,
                "expo_push_token": "ExpoPushToken[abcdefgh55555555]",
                "platform": "ios",
                "installation_proof": proof,
            },
        )
        assert transferred.status_code == 200, transferred.text

    with Session(engine) as session:
        rows = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.device_id == device_id,
        )).all()
    assert len(rows) == 1
    assert rows[0].user_id == other_id
    assert rows[0].user_id != legacy_owner_id
    assert rows[0].device_proof_hash == hashlib.sha256(proof.encode()).hexdigest()
    engine.dispose()


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_device_claim_does_not_delete_another_installation(monkeypatch, tmp_path):
    engine, owner_id, _, owner_token, other_token = _client_db(monkeypatch, tmp_path)
    first_device, second_device = str(uuid.uuid4()), str(uuid.uuid4())
    first_proof, second_proof = "e" * 64, "f" * 64
    with TestClient(main.app) as client:
        for device_id, proof, token in [
            (first_device, first_proof, "ExpoPushToken[abcdefgh66666661]"),
            (second_device, second_proof, "ExpoPushToken[abcdefgh66666662]"),
        ]:
            response = client.post(
                "/api/mobile/v1/push/devices",
                headers={"Authorization": "Bearer " + owner_token},
                json={"device_id": device_id, "expo_push_token": token, "platform": "android", "installation_proof": proof},
            )
            assert response.status_code == 200, response.text

        claimed = client.post(
            "/api/mobile/v1/push/devices/claim",
            headers={"Authorization": "Bearer " + other_token},
            json={"device_id": first_device, "installation_proof": first_proof},
        )
        assert claimed.status_code == 200

    with Session(engine) as session:
        rows = session.exec(select(main.MobilePushDevice).where(
            main.MobilePushDevice.user_id == owner_id,
        )).all()
    assert [row.device_id for row in rows] == [second_device]
    engine.dispose()


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
@pytest.mark.parametrize("proof", ["A" * 64, "g" * 64, "short", ""])
def test_push_registration_rejects_malformed_installation_proof(monkeypatch, tmp_path, proof):
    engine, _, _, owner_token, _ = _client_db(monkeypatch, tmp_path)
    with TestClient(main.app) as client:
        response = client.post(
            "/api/mobile/v1/push/devices",
            headers={"Authorization": "Bearer " + owner_token},
            json={
                "device_id": str(uuid.uuid4()),
                "expo_push_token": "ExpoPushToken[abcdefgh77777777]",
                "platform": "android",
                "installation_proof": proof,
            },
        )
    assert response.status_code == 422
    engine.dispose()


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_claim_requires_a_valid_uuid4_and_hex_proof(monkeypatch, tmp_path):
    engine, _, _, _, other_token = _client_db(monkeypatch, tmp_path)
    with TestClient(main.app) as client:
        bad_device = client.post(
            "/api/mobile/v1/push/devices/claim",
            headers={"Authorization": "Bearer " + other_token},
            json={"device_id": "not-a-uuid", "installation_proof": "a" * 64},
        )
        bad_proof = client.post(
            "/api/mobile/v1/push/devices/claim",
            headers={"Authorization": "Bearer " + other_token},
            json={"device_id": str(uuid.uuid4()), "installation_proof": "z" * 64},
        )
    assert bad_device.status_code == 422
    assert bad_proof.status_code == 422
    engine.dispose()
