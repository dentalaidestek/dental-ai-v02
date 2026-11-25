"""Yeni cihaz doğrulama akışı testleri (web + mobil).

Kural: hesap sahibi tanıdık cihazdan girerse oturum doğrudan açılır; tanımadığımız
cihazda e-postaya 6 haneli kod gider (kod = bildirim + doğrulama). Eski APK
(X-Device-Id göndermez) güvenli tarafta kalır: her girişte kod istenir.
"""

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app import main
from app import mobile_api

WEB_LOGIN = {"login": "expert-1", "password": "correct-password"}
DEVICE_HEADERS = {"X-Device-Id": "a" * 32}


@pytest.fixture
def client(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "device.db"),
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(mobile_api, "engine", engine)
    sent = []
    monkeypatch.setattr(main, "send_expert_device_code", lambda email, code: sent.append((email, code)))
    with Session(engine) as s:
        s.add(main.User(
            id=1,
            username="expert-1",
            display_name="Expert One",
            role="DOCTOR",
            is_active=True,
            email="expert@example.test",
            email_verified_at=main._utcnow_naive(),
            password_hash=main.hash_password("correct-password"),
        ))
        s.commit()
    # dai_dev çerezi secure=True: TestClient'ın https base URL kullanması gerekir.
    c = TestClient(main.app, base_url="https://testserver")
    return c, engine, sent


def _challenge_token(html: str):
    match = re.search(r'name="challenge_token"\s+value="([^"]+)"', html)
    return match.group(1) if match else None


def test_web_new_device_requires_email_code_then_trusts(client):
    c, engine, sent = client
    first = c.post("/login", data={**WEB_LOGIN, "next_url": "/"}, follow_redirects=False)
    assert first.status_code == 200, first.text
    token = _challenge_token(first.text)
    assert token, "yeni cihazda doğrulama formu render edilmeli"
    assert sent and sent[0][0] == "expert@example.test"
    cookie_names = {chunk.split("=", 1)[0] for chunk in first.headers.get_list("set-cookie")}
    assert "dai_dev" in cookie_names

    verified = c.post("/verify-email", data={"challenge_token": token, "code": sent[-1][1], "next_url": "/"}, follow_redirects=False)
    assert verified.status_code == 303, verified.text

    second = c.post("/login", data={**WEB_LOGIN, "next_url": "/"}, follow_redirects=False)
    assert second.status_code == 303, second.text
    assert _challenge_token(second.text) is None


def test_web_device_challenge_binds_to_browser(client):
    c, engine, sent = client
    first = c.post("/login", data={**WEB_LOGIN}, follow_redirects=False)
    token = _challenge_token(first.text)
    assert token

    other_browser = TestClient(main.app, base_url="https://testserver")
    forged = other_browser.post(
        "/verify-email",
        data={"challenge_token": token, "code": sent[-1][1], "next_url": "/"},
        follow_redirects=False,
    )
    assert forged.status_code == 400
    with Session(engine) as s:
        assert not s.exec(select(main.ExpertTrustedDevice)).all()


def test_web_wrong_code_locks_after_five(client):
    c, engine, sent = client
    first = c.post("/login", data={**WEB_LOGIN}, follow_redirects=False)
    token = _challenge_token(first.text)
    for _ in range(5):
        wrong = c.post("/verify-email", data={"challenge_token": token, "code": "000000", "next_url": "/"}, follow_redirects=False)
        assert wrong.status_code == 400
    locked = c.post("/verify-email", data={"challenge_token": token, "code": sent[-1][1], "next_url": "/"}, follow_redirects=False)
    assert locked.status_code == 429


def test_mobile_new_device_requires_code_then_trusts(client):
    c, engine, sent = client
    first = c.post("/api/mobile/v1/auth/login", json={**WEB_LOGIN}, headers=DEVICE_HEADERS)
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["access_token"] is None and data["challenge_token"]
    assert sent[-1][0] == "expert@example.test"

    verified = c.post(
        "/api/mobile/v1/auth/verify-email",
        json={"challenge_token": data["challenge_token"], "code": sent[-1][1]},
        headers=DEVICE_HEADERS,
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["access_token"]

    with Session(engine) as s:
        rows = s.exec(select(main.ExpertTrustedDevice).where(main.ExpertTrustedDevice.user_id == 1)).all()
        assert len(rows) == 1 and rows[0].platform == "mobile"

    second = c.post("/api/mobile/v1/auth/login", json={**WEB_LOGIN}, headers=DEVICE_HEADERS)
    assert second.status_code == 200 and second.json()["access_token"]


def test_mobile_without_device_header_stays_challenge_gated(client):
    """Eski APK X-Device-Id göndermez: güvenli tarafta kalır, her girişte kod istenir."""
    c, engine, sent = client
    first = c.post("/api/mobile/v1/auth/login", json={**WEB_LOGIN})
    assert first.json()["access_token"] is None and first.json()["challenge_token"]
    verified = c.post(
        "/api/mobile/v1/auth/verify-email",
        json={"challenge_token": first.json()["challenge_token"], "code": sent[-1][1]},
    )
    assert verified.status_code == 200 and verified.json()["access_token"]
    with Session(engine) as s:
        assert not s.exec(select(main.ExpertTrustedDevice)).all()
    second = c.post("/api/mobile/v1/auth/login", json={**WEB_LOGIN})
    assert second.json()["access_token"] is None and second.json()["challenge_token"]


def test_mobile_wrong_code_locks_after_five(client):
    c, engine, sent = client
    first = c.post("/api/mobile/v1/auth/login", json={**WEB_LOGIN}, headers=DEVICE_HEADERS)
    token = first.json()["challenge_token"]
    for _ in range(5):
        wrong = c.post(
            "/api/mobile/v1/auth/verify-email",
            json={"challenge_token": token, "code": "000000"},
            headers=DEVICE_HEADERS,
        )
        assert wrong.status_code == 400
    locked = c.post(
        "/api/mobile/v1/auth/verify-email",
        json={"challenge_token": token, "code": sent[-1][1]},
        headers=DEVICE_HEADERS,
    )
    assert locked.status_code == 429


def test_mobile_device_mismatch_rejected(client):
    c, engine, sent = client
    first = c.post("/api/mobile/v1/auth/login", json={**WEB_LOGIN}, headers=DEVICE_HEADERS)
    token = first.json()["challenge_token"]
    hijack = c.post(
        "/api/mobile/v1/auth/verify-email",
        json={"challenge_token": token, "code": sent[-1][1]},
        headers={"X-Device-Id": "b" * 32},
    )
    assert hijack.status_code == 400


def test_trusted_device_cap_deactivates_oldest(client):
    c, engine, sent = client
    for index in range(6):
        headers = {"X-Device-Id": f"{index:016d}" + "x" * 16}
        first = c.post("/api/mobile/v1/auth/login", json={**WEB_LOGIN}, headers=headers)
        c.post(
            "/api/mobile/v1/auth/verify-email",
            json={"challenge_token": first.json()["challenge_token"], "code": sent[-1][1]},
            headers=headers,
        )
    with Session(engine) as s:
        rows = s.exec(select(main.ExpertTrustedDevice).where(main.ExpertTrustedDevice.user_id == 1)).all()
        active = [row for row in rows if row.is_active]
        assert len(rows) == 6 and len(active) == 5


def test_public_token_migration_adds_column_to_legacy_table(monkeypatch):
    """Kolon eklenmeden oluşturulmuş eski tabloda init_db migrasyonu eklemeli."""
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            'CREATE TABLE expertdevicechallenge (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, '
            'device_key_hash VARCHAR NOT NULL, device_name VARCHAR, platform VARCHAR, public_key VARCHAR, '
            'code_hash VARCHAR NOT NULL, expires_at DATETIME NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, '
            'used_at DATETIME, created_at DATETIME)'
        )
    monkeypatch.setattr(main, "engine", engine)
    main.init_db()
    with engine.connect() as conn:
        cols = {row[1] for row in conn.exec_driver_sql('PRAGMA table_info("expertdevicechallenge")').fetchall()}
    assert "public_token" in cols
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO expertdevicechallenge (user_id, device_key_hash, code_hash, expires_at, public_token) "
            "VALUES (1, 'h', 'c', '2026-01-01', 'tok-1')"
        )
