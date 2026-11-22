from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine
from starlette.requests import Request

from app import main


@pytest.fixture
def media_delivery(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    main.Patient.__table__.create(engine)
    main.PatientMedia.__table__.create(engine)
    with Session(engine) as session:
        session.add(main.Patient(
            id=7,
            anonymous_id="synthetic-patient-7",
            owner_user_id=9,
        ))
        session.add(main.PatientMedia(
            id=42,
            patient_id=7,
            owner_user_id=9,
            original_filename="synthetic-clinical.jpg",
            stored_filename="patient_7_" + "a" * 32 + ".jpg",
            file_path="r2://uploads/patient-media/patient_7_" + "a" * 32 + ".jpg",
            media_type="RADIOGRAPH",
        ))
        session.commit()

    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(
        main,
        "get_current_user",
        lambda _request: SimpleNamespace(id=9, role="DOCTOR"),
    )
    image = tmp_path / "clinical.jpg"
    image.write_bytes(b"synthetic clinical image")
    yield engine, image
    engine.dispose()


def _request():
    path = b"/patients/7/media/42/file"
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path.decode(),
        "raw_path": path,
        "query_string": b"",
        "headers": [],
        "client": ("test", 12345),
        "server": ("test", 443),
    })


def test_web_original_media_is_inline_private_and_has_a_verified_image_type(
    media_delivery, monkeypatch
):
    _engine, image = media_delivery
    monkeypatch.setattr(main, "storage_ensure_local", lambda _reference: image)

    response = main.patient_media_file(_request(), 7, 42)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["vary"] == "Cookie"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"


def test_web_original_media_is_not_served_if_the_row_is_deleted_during_storage_hydration(
    media_delivery, monkeypatch
):
    engine, image = media_delivery

    def delete_during_hydration(_reference):
        with Session(engine) as session:
            media = session.get(main.PatientMedia, 42)
            session.delete(media)
            session.commit()
        return image

    monkeypatch.setattr(main, "storage_ensure_local", delete_during_hydration)

    response = main.patient_media_file(_request(), 7, 42)

    assert response.status_code == 404
    assert response.headers["cache-control"] == "private, no-store"
    assert b"bulunamad" in response.body.lower()


def test_web_original_media_rechecks_patient_and_media_ownership_after_hydration(
    media_delivery, monkeypatch
):
    engine, image = media_delivery

    def transfer_patient_during_hydration(_reference):
        with Session(engine) as session:
            patient = session.get(main.Patient, 7)
            media = session.get(main.PatientMedia, 42)
            patient.owner_user_id = 10
            media.owner_user_id = 10
            session.add(patient)
            session.add(media)
            session.commit()
        return image

    monkeypatch.setattr(main, "storage_ensure_local", transfer_patient_during_hydration)

    response = main.patient_media_file(_request(), 7, 42)

    assert response.status_code == 404
    assert response.headers["cache-control"] == "private, no-store"


def test_web_original_media_rejects_a_replaced_storage_reference_after_hydration(
    media_delivery, monkeypatch
):
    engine, image = media_delivery

    def replace_reference_during_hydration(_reference):
        with Session(engine) as session:
            media = session.get(main.PatientMedia, 42)
            media.file_path = "r2://uploads/patient-media/replacement.jpg"
            media.original_filename = "replacement.jpg"
            session.add(media)
            session.commit()
        return image

    monkeypatch.setattr(main, "storage_ensure_local", replace_reference_during_hydration)

    response = main.patient_media_file(_request(), 7, 42)

    assert response.status_code == 404
    assert response.headers["cache-control"] == "private, no-store"


def test_admin_access_remains_compatible_when_the_patient_owner_changes_during_hydration(
    media_delivery, monkeypatch
):
    engine, image = media_delivery
    monkeypatch.setattr(
        main,
        "get_current_user",
        lambda _request: SimpleNamespace(id=1, role="ADMIN"),
    )

    def transfer_during_hydration(_reference):
        with Session(engine) as session:
            patient = session.get(main.Patient, 7)
            media = session.get(main.PatientMedia, 42)
            patient.owner_user_id = 10
            media.owner_user_id = 10
            session.add(patient)
            session.add(media)
            session.commit()
        return image

    monkeypatch.setattr(main, "storage_ensure_local", transfer_during_hydration)

    response = main.patient_media_file(_request(), 7, 42)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"


def test_web_original_media_storage_outage_is_private_and_retryable(
    media_delivery, monkeypatch
):
    def fail_storage(_reference):
        raise RuntimeError("synthetic R2 outage")

    monkeypatch.setattr(main, "storage_ensure_local", fail_storage)

    response = main.patient_media_file(_request(), 7, 42)

    assert response.status_code == 503
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Cookie"
    assert response.headers["retry-after"] == "2"


def test_web_original_media_rejects_cross_account_before_storage_access(
    media_delivery, monkeypatch
):
    _engine, _image = media_delivery
    calls = []
    monkeypatch.setattr(
        main,
        "get_current_user",
        lambda _request: SimpleNamespace(id=10, role="DOCTOR"),
    )
    monkeypatch.setattr(main, "storage_ensure_local", lambda ref: calls.append(ref))

    response = main.patient_media_file(_request(), 7, 42)

    assert response.status_code == 403
    assert response.headers["cache-control"] == "private, no-store"
    assert calls == []


def test_web_original_media_is_not_served_if_the_patient_is_deleted_during_hydration(
    media_delivery, monkeypatch
):
    engine, image = media_delivery

    def delete_patient_during_hydration(_reference):
        with Session(engine) as session:
            patient = session.get(main.Patient, 7)
            session.delete(patient)
            session.commit()
        return image

    monkeypatch.setattr(main, "storage_ensure_local", delete_patient_during_hydration)

    response = main.patient_media_file(_request(), 7, 42)

    assert response.status_code == 404
    assert response.headers["cache-control"] == "private, no-store"


def test_web_original_media_fails_closed_when_the_post_hydration_database_check_fails(
    media_delivery, monkeypatch
):
    _engine, image = media_delivery
    original_session = main.Session
    session_calls = 0

    def fail_second_session(*args, **kwargs):
        nonlocal session_calls
        session_calls += 1
        if session_calls == 2:
            raise RuntimeError("synthetic database recheck outage")
        return original_session(*args, **kwargs)

    monkeypatch.setattr(main, "Session", fail_second_session)
    monkeypatch.setattr(main, "storage_ensure_local", lambda _reference: image)

    response = main.patient_media_file(_request(), 7, 42)

    assert response.status_code == 503
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["retry-after"] == "2"
