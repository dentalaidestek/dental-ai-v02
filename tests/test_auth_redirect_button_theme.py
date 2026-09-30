from pathlib import Path

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
        session.add(main.User(
            username="doctor",
            email="doctor@example.test",
            role="DOCTOR",
            display_name="Doctor",
            password_hash=main.hash_password("correct-password"),
        ))
        session.commit()

    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as client:
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
    assert ".expert-send-circle" in theme
    assert "#studySendButton" in theme
    assert ".support-reply-actions button" in theme
    assert ".admin-support-message-form button" in theme
