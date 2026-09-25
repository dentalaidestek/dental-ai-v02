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
BASE = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
PATIENTS = (ROOT / "app/templates/patients_all.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "app/templates/patient_detail.html").read_text(encoding="utf-8")
PHOTO_TEMPLATES = [
    ROOT / "app/templates/account.html",
    ROOT / "app/templates/expert_profile_edit.html",
    ROOT / "app/templates/expert_support.html",
    ROOT / "app/templates/expert_public_profile.html",
    ROOT / "app/templates/_message_row.html",
    ROOT / "app/templates/admin_expert_verifications.html",
]


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _user_and_token(engine, username="owner"):
    token = f"{username}-token"
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username=username, role="DOCTOR", display_name=username.title())
        session.add(user)
        session.commit()
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(token), user_id=user.id,
            expires_at=main._utcnow_naive() + main.timedelta(days=1),
        ))
        session.commit()
        return user.id, token


def test_profile_templates_use_one_versioned_photo_helper_and_simple_copy():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in PHOTO_TEMPLATES)
    assert 'src="/profile-photo/' not in combined
    assert "profile_photo_url(" in combined
    assert "data-profile-user-id" in combined
    assert "Fotoğraf seç ve kırp" not in combined
    assert "Fotoğraf seç ve yuvarlak kırp" not in combined
    assert "Profil fotoğrafı ekle" in combined
    assert "Profil fotoğrafını değiştir" in combined


def test_profile_photo_realtime_targets_only_matching_avatar():
    assert "refreshProfileImages(data.user_id,data.photo_url)" in BASE
    assert "Number(img.dataset.profileUserId)===Number(userId)" in BASE
    assert 'querySelectorAll("img[data-profile-user-id]")' in BASE
    assert "?v=" in main._profile_photo_url(
        main.User(id=9, username="u", profile_photo_path="uploads/profile_photos/new.jpg")
    )


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_profile_photo_replacement_commits_before_old_delete_and_emits_event(monkeypatch):
    engine = _engine()
    user_id, token = _user_and_token(engine)
    with Session(engine) as session:
        user = session.get(main.User, user_id)
        user.profile_photo_path = "uploads/profile_photos/old.jpg"
        session.add(user)
        session.commit()
    deleted = []
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "_save_profile_photo", lambda *_: "uploads/profile_photos/new.jpg")
    monkeypatch.setattr(main, "storage_delete", lambda path: deleted.append(str(path)))
    with TestClient(main.app) as client:
        response = client.post(
            "/account/profile-photo", data={"profile_photo_data": "data:image/jpeg;base64,x"},
            cookies={main.SESSION_COOKIE: token}, follow_redirects=False,
        )
    assert response.status_code == 303
    with Session(engine) as session:
        user = session.get(main.User, user_id)
        event = session.exec(select(main.RealtimeEvent).where(
            main.RealtimeEvent.user_id == user_id,
            main.RealtimeEvent.event_type == "PROFILE_PHOTO_UPDATED",
        )).one()
        assert user.profile_photo_path.endswith("new.jpg")
        assert f'"user_id": {user_id}' in event.payload_json
        assert "?v=" in event.payload_json
    assert deleted == ["uploads/profile_photos/old.jpg"]


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_failed_profile_upload_preserves_current_photo(monkeypatch):
    engine = _engine()
    user_id, token = _user_and_token(engine)
    with Session(engine) as session:
        user = session.get(main.User, user_id)
        user.profile_photo_path = "uploads/profile_photos/working.jpg"
        session.add(user)
        session.commit()
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "_save_profile_photo", lambda *_: (_ for _ in ()).throw(ValueError("bozuk")))
    with TestClient(main.app) as client:
        response = client.post(
            "/account/profile-photo", data={"profile_photo_data": "bad"},
            cookies={main.SESSION_COOKIE: token}, follow_redirects=False,
        )
    assert response.status_code == 400
    with Session(engine) as session:
        assert session.get(main.User, user_id).profile_photo_path.endswith("working.jpg")


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_patient_crud_records_owner_only_durable_events_and_enforces_isolation(monkeypatch):
    engine = _engine()
    owner_id, owner_token = _user_and_token(engine, "owner")
    other_id, other_token = _user_and_token(engine, "other")
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as client:
        created = client.post(
            "/patients/new",
            data={"first_name": "Ada", "last_name": "Yılmaz", "phone": "05012345678"},
            cookies={main.SESSION_COOKIE: owner_token}, follow_redirects=False,
        )
        assert created.status_code == 303
        patient_id = int(created.headers["location"].rsplit("/", 1)[-1])
        assert client.get(
            f"/patients/{patient_id}/realtime", cookies={main.SESSION_COOKIE: other_token}
        ).status_code == 403
        updated = client.post(
            f"/patients/{patient_id}/edit",
            data={"first_name": "Ada", "last_name": "Demir", "phone": "05012345678", "address": "Ankara"},
            headers={"Accept": "application/json"}, cookies={main.SESSION_COOKIE: owner_token},
        )
        assert updated.status_code == 200
        snapshot = client.get(
            f"/patients/{patient_id}/realtime", cookies={main.SESSION_COOKIE: owner_token}
        ).json()["patient"]
        assert snapshot["display_name"] == "Ada Demir"
        assert snapshot["address"] == "Ankara"
        deleted = client.post(
            f"/patients/{patient_id}/delete", headers={"Accept": "application/json"},
            cookies={main.SESSION_COOKIE: owner_token},
        )
        assert deleted.status_code == 200
    with Session(engine) as session:
        events = session.exec(select(main.RealtimeEvent).order_by(main.RealtimeEvent.id)).all()
        patient_events = [event for event in events if event.event_type.startswith("PATIENT_")]
        assert [event.event_type for event in patient_events] == [
            "PATIENT_CREATED", "PATIENT_UPDATED", "PATIENT_DELETED"
        ]
        assert {event.user_id for event in patient_events} == {owner_id}
        assert other_id not in {event.user_id for event in patient_events}


def test_patient_pages_apply_minimal_realtime_updates_without_polling_or_full_reload():
    assert '"PATIENT_CREATED","PATIENT_UPDATED","PATIENT_DELETED"' in BASE
    assert 'fetch("/patients/"+patientId+"/realtime"' in BASE
    assert "setInterval" not in BASE.split("const patientFetches", 1)[1].split("function applySyncEvent", 1)[0]
    assert "data-patient-id" in PATIENTS
    assert "dai:patient-record" in PATIENTS
    assert "data-patient-detail-id" in DETAIL
    assert 'location.assign("/patients?deleted=1")' in BASE

