from datetime import timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app import clinical_media_thumbnail as thumbnails, main, object_storage, work_jobs


@pytest.fixture
def media_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    work_jobs.WorkGarbage.__table__.create(engine)
    main.Patient.__table__.create(engine)
    main.PatientMedia.__table__.create(engine)
    yield engine
    engine.dispose()


def media_path(folder=""):
    prefix = f"uploads/{folder}" if folder else "uploads/"
    return prefix + "patient_42_" + ("a" * 32) + ".jpg"


def test_cleanup_admission_accepts_only_server_generated_media_object_keys(media_engine):
    web_path = media_path()
    native_path = media_path("patient-media/")
    web_thumbnail = thumbnails.thumbnail_reference(web_path)
    native_thumbnail = thumbnails.thumbnail_reference(native_path)
    assert work_jobs.is_patient_media_reference(web_path)
    assert work_jobs.is_patient_media_reference(native_path)
    assert work_jobs.is_patient_media_reference(web_thumbnail)
    assert work_jobs.is_patient_media_reference(native_thumbnail)
    for unsafe in (
        "../uploads/patient_42_" + ("a" * 32) + ".jpg",
        "/uploads/patient_42_" + ("a" * 32) + ".jpg",
        "uploads/analysis_42_" + ("a" * 32) + ".jpg",
        "uploads/patient_42_" + ("A" * 32) + ".jpg",
        "uploads/patient_42_" + ("a" * 32) + ".exe",
        "uploads/patient_42_" + ("a" * 32) + ".thumb.thumb.jpg",
        "uploads/patient-media/patient_42_" + ("a" * 32) + ".thumb.exe",
        "uploads/patient-media/patient_42_" + ("a" * 32) + ".thumb.png",
        "uploads/patient-media/patient_42_" + ("a" * 32) + ".thumb.jpg/extra",
    ):
        assert not work_jobs.is_patient_media_reference(unsafe)


def test_cleanup_receipt_is_deduplicated_and_contains_only_the_opaque_path(media_engine):
    reference = media_path()
    with Session(media_engine) as session:
        assert work_jobs.enqueue_patient_media_cleanup(session, reference)
        assert work_jobs.enqueue_patient_media_cleanup(session, reference)
        session.commit()
        rows = session.exec(select(work_jobs.WorkGarbage)).all()
        assert len(rows) == 1
        assert rows[0].reference == reference
        assert rows[0].attempts == 1


def test_requeue_advances_cleanup_fence_and_makes_receipt_due(media_engine):
    reference = media_path()
    with Session(media_engine) as session:
        session.add(work_jobs.WorkGarbage(
            reference=reference,
            available_at=work_jobs.now() + timedelta(hours=1),
            attempts=4,
        ))
        session.commit()
        assert work_jobs.enqueue_patient_media_cleanup(session, reference)
        session.commit()
        row = session.exec(
            select(work_jobs.WorkGarbage).where(
                work_jobs.WorkGarbage.reference == reference
            )
        ).one()
        assert row.attempts == 5
        assert row.available_at <= work_jobs.now()


def test_media_row_delete_and_cleanup_receipt_share_one_transaction(media_engine):
    reference = media_path()
    with Session(media_engine) as session:
        session.add(main.PatientMedia(
            id=42,
            patient_id=7,
            owner_user_id=9,
            original_filename="synthetic.png",
            stored_filename=reference.rsplit("/", 1)[-1],
            file_path=reference,
        ))
        session.commit()

    # Roll back only the delete + cleanup receipt transaction, not the fixture insert.
    with Session(media_engine) as session:
        media = session.get(main.PatientMedia, 42)
        assert media is not None
        assert work_jobs.enqueue_patient_media_cleanup(session, reference)
        session.delete(media)
        session.flush()
        session.rollback()

    with Session(media_engine) as session:
        assert session.get(main.PatientMedia, 42) is not None
        assert session.exec(select(work_jobs.WorkGarbage)).all() == []


def test_worker_deletes_unreferenced_media_and_removes_its_receipt(media_engine, monkeypatch):
    reference = media_path()
    with Session(media_engine) as session:
        session.add(work_jobs.WorkGarbage(
            reference=reference,
            available_at=work_jobs.now() - timedelta(seconds=1),
        ))
        session.commit()

    deleted = []
    monkeypatch.setattr(object_storage, "delete", lambda value: deleted.append(value))
    work_jobs.collect_garbage(media_engine)

    assert deleted == [reference]
    with Session(media_engine) as session:
        assert session.exec(select(work_jobs.WorkGarbage)).all() == []


def test_worker_deletes_unreferenced_thumbnail_and_removes_its_receipt(media_engine, monkeypatch):
    reference = thumbnails.thumbnail_reference(media_path("patient-media/"))
    with Session(media_engine) as session:
        session.add(work_jobs.WorkGarbage(
            reference=reference,
            available_at=work_jobs.now() - timedelta(seconds=1),
        ))
        session.commit()

    deleted = []
    monkeypatch.setattr(object_storage, "delete", lambda value: deleted.append(value))
    work_jobs.collect_garbage(media_engine)

    assert deleted == [reference]
    with Session(media_engine) as session:
        assert session.exec(select(work_jobs.WorkGarbage)).all() == []


def test_worker_preserves_an_object_still_referenced_by_a_live_media_row(media_engine, monkeypatch):
    reference = media_path("patient-media/")
    with Session(media_engine) as session:
        session.add(main.PatientMedia(
            id=43,
            patient_id=7,
            owner_user_id=9,
            original_filename="synthetic.png",
            stored_filename=reference.rsplit("/", 1)[-1],
            file_path=reference,
        ))
        session.add(work_jobs.WorkGarbage(
            reference=reference,
            available_at=work_jobs.now() - timedelta(seconds=1),
        ))
        session.commit()

    deleted = []
    monkeypatch.setattr(object_storage, "delete", lambda value: deleted.append(value))
    work_jobs.collect_garbage(media_engine)

    assert deleted == []
    with Session(media_engine) as session:
        assert session.get(main.PatientMedia, 43) is not None
        assert session.exec(select(work_jobs.WorkGarbage)).all() == []


@pytest.mark.parametrize("reference", [
    media_path(),
    thumbnails.thumbnail_reference(media_path("patient-media/")),
])
def test_remote_delete_failure_keeps_a_delayed_retry(media_engine, monkeypatch, reference):

    def fail(_reference):
        raise RuntimeError("synthetic object-store outage")

    with Session(media_engine) as session:
        session.add(work_jobs.WorkGarbage(
            reference=reference,
            available_at=work_jobs.now() - timedelta(seconds=1),
        ))
        session.commit()

    monkeypatch.setattr(object_storage, "delete", fail)
    work_jobs.collect_garbage(media_engine)

    with Session(media_engine) as session:
        row = session.exec(select(work_jobs.WorkGarbage)).one()
        assert row.attempts == 1
        assert row.available_at > work_jobs.now()


def test_web_and_native_delete_paths_enqueue_before_committing_metadata_removal():
    main_source = open(main.__file__, encoding="utf-8").read()
    single = main_source.split(
        '@app.post("/patients/{patient_id}/media/{media_id}/delete")', 1
    )[1].split('@app.post("/patients/{patient_id}/media/delete-all")', 1)[0]
    bulk = main_source.split(
        '@app.post("/patients/{patient_id}/media/delete-all")', 1
    )[1].split('@app.get("/analyses"', 1)[0]
    mobile_source = open(main.__file__.replace("main.py", "mobile_api.py"), encoding="utf-8").read()
    native = mobile_source.split(
        '@router.delete("/patients/{patient_id}/media/{media_id}")', 1
    )[1].split('@router.get("/patients/{patient_id}/media/{media_id}/file")', 1)[0]

    assert single.index("enqueue_patient_media_cleanup") < single.index("s.commit()")
    assert "limit(100)" in bulk
    assert "s.flush()" in bulk and "s.expunge_all()" in bulk
    assert bulk.index("enqueue_patient_media_cleanup") < bulk.index("s.commit()")
    assert native.index("enqueue_patient_media_cleanup") < native.index("session.commit()")



def test_native_single_delete_queues_original_and_thumbnail_without_synchronous_storage_delete(media_engine, monkeypatch):
    from types import SimpleNamespace
    from app import mobile_api

    reference = media_path("patient-media/")
    thumbnail = thumbnails.thumbnail_reference(reference)
    with Session(media_engine) as session:
        session.add(main.Patient(
            id=7,
            anonymous_id="synthetic-patient-7",
            owner_user_id=9,
        ))
        session.add(main.PatientMedia(
            id=42,
            patient_id=7,
            owner_user_id=9,
            original_filename="synthetic.png",
            stored_filename=reference.rsplit("/", 1)[-1],
            file_path=reference,
        ))
        session.commit()

    monkeypatch.setattr(mobile_api, "engine", media_engine)
    monkeypatch.setattr(mobile_api, "_record_realtime_event", lambda *args: {"event": "synthetic"})
    monkeypatch.setattr(mobile_api, "on_loop", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mobile_api,
        "storage_delete",
        lambda value: pytest.fail(f"supported media cleanup must be queued, not synchronous: {value}"),
    )

    result = mobile_api.mobile_delete_patient_media(
        7,
        42,
        SimpleNamespace(id=9, role="DOCTOR"),
    )

    assert result["ok"] is True
    assert result["storage_cleanup_pending"] is True
    with Session(media_engine) as session:
        references = set(session.exec(select(work_jobs.WorkGarbage.reference)).all())
        assert references == {reference, thumbnail}
        assert session.get(main.PatientMedia, 42) is None
