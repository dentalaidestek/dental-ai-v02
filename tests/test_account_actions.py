from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_TEMPLATE = (ROOT / "app/templates/account.html").read_text(encoding="utf-8")


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_profile_exposes_logout_and_guarded_account_deletion():
    assert 'method="post" action="/logout"' in ACCOUNT_TEMPLATE
    assert 'action="/account/delete"' in ACCOUNT_TEMPLATE
    assert 'name="confirm_username"' in ACCOUNT_TEMPLATE
    assert 'name="password"' in ACCOUNT_TEMPLATE
    assert "accountDeleteDialog" in ACCOUNT_TEMPLATE
    assert "user.role != 'ADMIN'" in ACCOUNT_TEMPLATE


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_self_delete_requires_password_then_revokes_account_and_session(monkeypatch):
    engine = _engine()
    token = "delete-account-token"
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(
            username="deleteowner",
            email="delete@example.test",
            role="DOCTOR",
            display_name="Delete Owner",
            password_hash=main.hash_password("correct-password"),
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(token),
            user_id=user_id,
            expires_at=main._utcnow_naive() + main.timedelta(days=1),
        ))
        session.commit()

    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "storage_delete", lambda _path: None)

    with TestClient(main.app) as client:
        profile = client.get(
            "/account", cookies={main.SESSION_COOKIE: token}, follow_redirects=False
        )
        assert profile.status_code == 200
        assert "Çıkış Yap" in profile.text
        assert "Hesabımı Sil" in profile.text

        rejected = client.post(
            "/account/delete",
            data={"confirm_username": "deleteowner", "password": "wrong-password"},
            cookies={main.SESSION_COOKIE: token},
            follow_redirects=False,
        )
        assert rejected.status_code == 403

        accepted = client.post(
            "/account/delete",
            data={"confirm_username": "deleteowner", "password": "correct-password"},
            cookies={main.SESSION_COOKIE: token},
            follow_redirects=False,
        )
        assert accepted.status_code == 303
        assert accepted.headers["location"] == "/login?account_deleted=1"

    with Session(engine) as session:
        deleted = session.get(main.User, user_id)
        assert deleted is not None
        assert not deleted.is_active
        assert deleted.display_name == "Silinmiş Kullanıcı"
        assert deleted.email is None
        assert deleted.password_hash is None
        assert not session.exec(
            select(main.SessionToken).where(main.SessionToken.user_id == user_id)
        ).first()


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_deleted_account_login_page_confirms_completion():
    with TestClient(main.app) as client:
        response = client.get("/login?account_deleted=1")
    assert response.status_code == 200
    assert "Hesabınız silindi" in response.text


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_display_name_edit_route_normalizes_and_publishes(monkeypatch):
    engine = _engine()
    token = "display-name-token"
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username="displayuser", role="DOCTOR", display_name="Old Name")
        session.add(user); session.commit(); session.refresh(user)
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(token), user_id=user.id,
            expires_at=main._utcnow_naive() + main.timedelta(days=1),
        ))
        session.commit()
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as client:
        response = client.post("/account/display-name", data={"display_name": "  New   Name  "}, cookies={main.SESSION_COOKIE: token}, follow_redirects=False)
    assert response.status_code == 303
    with Session(engine) as session:
        assert session.get(main.User, user.id).display_name == "New Name"


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_verified_expert_display_name_is_not_changed_from_account(monkeypatch):
    engine = _engine()
    token = "verified-display-name-token"
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username="verifieduser", role="DOCTOR", display_name="Verified Name")
        session.add(user); session.flush()
        session.add(main.ExpertProfile(
            user_id=user.id, specialty="Endodonti", application_status="APPROVED",
            verification_status="VERIFIED", specialty_verified=True,
            credential_document_path="r2/key", phone="05000000000",
            availability="AVAILABLE", consultation_price=200,
        ))
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(token), user_id=user.id,
            expires_at=main._utcnow_naive() + main.timedelta(days=1),
        ))
        session.commit()
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as client:
        response = client.post("/account/display-name", data={"display_name": "Changed Name"}, cookies={main.SESSION_COOKIE: token}, follow_redirects=False)
    assert response.status_code == 409
    with Session(engine) as session:
        assert session.get(main.User, user.id).display_name == "Verified Name"


def test_profile_mobile_edit_controls_are_present():
    assert 'action="/account/display-name"' in ACCOUNT_TEMPLATE
    assert 'name="display_name"' in ACCOUNT_TEMPLATE
    assert '.account-container{max-width:820px;' in ACCOUNT_TEMPLATE
