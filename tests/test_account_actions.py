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
    assert 'href="/logout"' in ACCOUNT_TEMPLATE
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
