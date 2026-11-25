from pathlib import Path

import re

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_new_patient_login_returns_user_to_requested_page(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(main.User(email_verified_at=main._utcnow_naive(),
            username="doctor",
            email="doctor@example.test",
            role="DOCTOR",
            display_name="Doctor",
            password_hash=main.hash_password("correct-password"),
        ))
        session.commit()

    monkeypatch.setattr(main, "engine", engine)
    device_codes = []
    monkeypatch.setattr(main, "send_expert_device_code", lambda email, code: device_codes.append(code))
    with TestClient(main.app, base_url="https://testserver") as client:
        guarded = client.get("/patients/new", follow_redirects=False)
        assert guarded.status_code == 303
        assert guarded.headers["location"] == "/login?next=%2Fpatients%2Fnew"

        login_page = client.get(guarded.headers["location"])
        assert login_page.status_code == 200
        assert 'name="next_url" value="/patients/new"' in login_page.text

        logged_in = client.post(
            "/login",
            data={
                "login": "doctor",
                "password": "correct-password",
                "next_url": "/patients/new",
            },
            follow_redirects=False,
        )
        # Yeni cihaz: e-posta kodu adımı zorunlu; doğrulayınca istenen sayfaya dönülür.
        if logged_in.status_code == 200:
            match = re.search(r'name="challenge_token"\s+value="([^"]+)"', logged_in.text)
            assert match, "yeni cihazda doğrulama formu gelmeli"
            verified = client.post(
                "/verify-email",
                data={"challenge_token": match.group(1), "code": device_codes[-1], "next_url": "/patients/new"},
                follow_redirects=False,
            )
            assert verified.status_code == 303, verified.text
            logged_in = verified
        assert logged_in.status_code == 303
        assert logged_in.headers["location"] == "/patients/new"
        assert main.SESSION_COOKIE in logged_in.cookies

        # Phone + birth date builds multiple duplicate filters. This exact path
        # previously crashed in production because it referenced an unimported or_.
        created = client.post(
            "/patients/new",
            data={
                "first_name": "Ada",
                "last_name": "Yılmaz",
                "birth_date": "1998-04-12",
                "phone": "05012345678",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        assert created.headers["location"].startswith("/patients/")


def test_login_next_rejects_external_or_protocol_relative_redirects():
    assert main._safe_login_next("https://example.test/steal") == "/"
    assert main._safe_login_next("//example.test/steal") == "/"
    assert main._safe_login_next("/patients/new?next=analysis") == "/patients/new?next=analysis"


def test_navy_button_theme_is_loaded_last_and_excludes_message_senders():
    base = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    theme = (ROOT / "app/static/button-theme.css").read_text(encoding="utf-8")
    assert base.index("button-theme.css") > base.index("dashboard-v2.css")
    assert "--dai-button-navy: #0b2341" in theme
    assert "background-color: var(--dai-button-navy) !important" in theme
    assert "background: var(--dai-button-navy)" not in theme
    # The legacy design-system uses high-specificity !important shorthands.
    # Keeping an ID alternative inside :is() makes the theme win without
    # changing any template markup or button dimensions.
    assert "#dai-button-theme-specificity" in theme
    assert ".expert-send-circle" in theme
    assert "#studySendButton" in theme
    assert ".support-reply-actions button" in theme
    assert ".admin-support-message-form button" in theme
    assert ".message-title strong" in theme
    assert ".visual-section-head a" in theme
    assert ".visual-empty a" in theme
    assert ".study-back-link" in theme
    assert ".mobile-nav-item.active" in theme
