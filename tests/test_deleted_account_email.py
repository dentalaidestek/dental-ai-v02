from datetime import timedelta

from fastapi import Request
from sqlmodel import Session, SQLModel, create_engine, select

import app.main as main
from app.main import (
    DeletedAccountEmail,
    SessionToken,
    User,
    _canonical_registration_email,
    _deleted_email_fingerprint,
    _email_is_permanently_blocked,
    _utcnow_naive,
)
from app.auth import hash_session_token


def test_gmail_aliases_share_one_registration_identity():
    expected = "cihanakak@gmail.com"
    assert _canonical_registration_email("Cihan.Akak@gmail.com") == expected
    assert _canonical_registration_email("cihan.akak+yenikayit@googlemail.com") == expected


def test_non_gmail_addresses_are_only_case_normalized():
    assert _canonical_registration_email("Name.Sales+one@Example.COM") == "name.sales+one@example.com"


def test_deleted_email_block_is_persistent_and_does_not_store_plain_email(monkeypatch):
    monkeypatch.setenv("ACCOUNT_BLOCKLIST_SECRET", "test-only-secret")
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    original = "cihan.akak+old@gmail.com"
    fingerprint = _deleted_email_fingerprint(original)

    assert "cihan" not in fingerprint
    with Session(engine) as session:
        session.add(DeletedAccountEmail(
            email_fingerprint=fingerprint,
            deleted_user_id=42,
            deleted_by_admin_id=1,
        ))
        session.commit()
        assert _email_is_permanently_blocked(session, "cihanakak@gmail.com")
        assert not _email_is_permanently_blocked(session, "another@gmail.com")


def test_admin_delete_anonymizes_account_revokes_session_and_blocks_gmail(monkeypatch):
    monkeypatch.setenv("ACCOUNT_BLOCKLIST_SECRET", "test-only-secret")
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        admin = User(
            username="systemadmin",
            role="ADMIN",
            display_name="Admin",
            password_hash="hash",
            is_active=True,
        )
        target = User(
            username="cihanakak",
            role="DOCTOR",
            display_name="Cihan Akak",
            email="cihan.akak@gmail.com",
            password_hash="hash",
            profile_photo_path="uploads/profile.jpg",
            is_active=True,
        )
        session.add(admin)
        session.add(target)
        session.commit()
        session.refresh(admin)
        session.refresh(target)
        session.add(SessionToken(
            token_hash=hash_session_token("active-session"),
            user_id=target.id,
            expires_at=_utcnow_naive() + timedelta(days=1),
        ))
        session.commit()

    removed_paths = []
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "_admin_only", lambda request: admin)
    monkeypatch.setattr(main, "storage_delete", removed_paths.append)
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})

    response = main.admin_center_delete_user(request, target.id, "cihanakak")
    assert response.status_code == 303

    with Session(engine) as session:
        deleted = session.get(User, target.id)
        assert deleted is not None
        assert deleted.display_name == "Silinmiş Kullanıcı"
        assert deleted.email is None
        assert deleted.password_hash is None
        assert deleted.profile_photo_path is None
        assert not deleted.is_active
        assert not session.exec(
            select(SessionToken).where(SessionToken.user_id == target.id)
        ).first()
        assert _email_is_permanently_blocked(session, "cihanakak+again@gmail.com")
    assert removed_paths == ["uploads/profile.jpg"]
