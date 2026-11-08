from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_TEMPLATE = (ROOT / "app/templates/account.html").read_text(encoding="utf-8")


def _engine(tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "account.db"), connect_args={"check_same_thread": False}
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
def test_self_delete_requires_password_then_revokes_account_and_session(monkeypatch, tmp_path):
    engine = _engine(tmp_path)
    token = "delete-account-token"
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(
            username="deleteowner",
            email_verified_at=main._utcnow_naive(),
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
        session.add(main.E2EEDeviceKey(user_id=user_id, device_id="erase-test-device", public_key="synthetic-public-key"))
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
        erased_key = session.exec(select(main.E2EEDeviceKey).where(main.E2EEDeviceKey.user_id == user_id)).one()
        assert erased_key.revoked_at is not None

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
def test_display_name_edit_route_normalizes_and_publishes(monkeypatch, tmp_path):
    engine = _engine(tmp_path)
    token = "display-name-token"
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username="displayuser", role="DOCTOR", display_name="Old Name", email_verified_at=main._utcnow_naive())
        session.add(user); session.commit(); session.refresh(user)
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(token), user_id=user.id,
            expires_at=main._utcnow_naive() + main.timedelta(days=1),
        ))
        session.commit()
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as client:
        response = client.post("/account/display-name", data={"display_name": "  New   Name  "}, cookies={main.SESSION_COOKIE: token}, follow_redirects=False)
        confirmation = client.get('/account?name_saved=1', cookies={main.SESSION_COOKIE: token})
        unauthenticated = client.post('/account/display-name', data={'display_name': 'Intruder'}, follow_redirects=False)
    assert response.status_code == 303
    assert unauthenticated.status_code == 303
    assert unauthenticated.headers['location'] == '/login'
    assert 'Ad soyadınız güncellendi.' in confirmation.text
    assert 'Mesleki durumunuz güncellendi.' not in confirmation.text
    from html.parser import HTMLParser
    class ProfileSections(HTMLParser):
        def __init__(self):
            super().__init__()
            self.sections = 0
            self.form_depth = 0
            self.actions = []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'details' and attrs.get('class') == 'account-section':
                self.sections += 1
            if tag == 'form':
                assert self.form_depth == 0
                self.form_depth += 1
                self.actions.append(attrs.get('action'))
        def handle_endtag(self, tag):
            if tag == 'form':
                self.form_depth -= 1
    parser = ProfileSections()
    parser.feed(confirmation.text)
    # Personal, professional, expert entry, notifications, password, account.
    assert parser.sections == 6
    assert parser.form_depth == 0
    assert {'/account/display-name', '/account/username', '/account/password', '/account/professional-title', '/account/profile-photo', '/logout', '/account/delete'} <= set(parser.actions)
    with Session(engine) as session:
        assert session.get(main.User, user.id).display_name == "New Name"


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_verified_expert_can_edit_display_name_without_reverification(monkeypatch, tmp_path):
    engine = _engine(tmp_path)
    token = "verified-display-name-token"
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username="verifieduser", role="DOCTOR", display_name="Verified Name", email_verified_at=main._utcnow_naive())
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
    assert response.status_code == 303
    assert response.headers['location'] == '/account?name_saved=1'
    with Session(engine) as session:
        assert session.get(main.User, user.id).display_name == "Changed Name"
        profile = session.exec(select(main.ExpertProfile).where(main.ExpertProfile.user_id == user.id)).one()
        assert profile.verification_status == "VERIFIED"
        assert profile.application_status == "APPROVED"
        assert profile.credential_document_path == "r2/key"
        assert profile.specialty_verified is True


def test_profile_mobile_edit_controls_are_present():
    assert 'action="/account/display-name"' in ACCOUNT_TEMPLATE
    assert 'name="display_name"' in ACCOUNT_TEMPLATE
    assert '.account-container{max-width:820px;' in ACCOUNT_TEMPLATE

