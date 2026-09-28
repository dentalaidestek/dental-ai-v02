from datetime import datetime, timedelta

from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel

from app.study_index_jobs import (
    StudyIndexChunk,
    StudyIndexJob,
    StudyIndexPage,
    begin_material_build,
    claim_next_index_job,
    enqueue_index_job,
    publish_index_version,
    tombstone_material,
    yield_index_job,
)


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE studymaterial (
                id INTEGER PRIMARY KEY,
                owner_user_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                deleted_at TIMESTAMP,
                index_status VARCHAR NOT NULL DEFAULT 'LEGACY',
                active_index_version VARCHAR,
                building_index_version VARCHAR,
                index_error VARCHAR
            )
            """
        )
    return engine


def _material(session: Session, material_id=1, owner=10, course=20):
    session.exec(
        text(
            """
            INSERT INTO studymaterial
                (id, owner_user_id, course_id, index_status)
            VALUES (:id, :owner, :course, 'LEGACY')
            """
        ),
        params={"id": material_id, "owner": owner, "course": course},
    )
    session.commit()


def _job(session: Session, version="v1"):
    assert begin_material_build(
        session, material_id=1, owner_user_id=10, index_version=version
    )
    job = enqueue_index_job(
        session,
        owner_user_id=10,
        course_id=20,
        material_id=1,
        index_version=version,
    )
    session.commit()
    return job


def _ready_artifacts(session: Session, version="v1"):
    session.add(
        StudyIndexPage(
            owner_user_id=10,
            course_id=20,
            material_id=1,
            index_version=version,
            page_number=1,
            status="EXTRACTED",
            text_content="abc",
        )
    )
    session.add(
        StudyIndexChunk(
            owner_user_id=10,
            course_id=20,
            material_id=1,
            index_version=version,
            chunk_index=0,
            page_start=1,
            page_end=1,
            text_content="abc",
            text_sha256="x",
            embedding_json="[0.1]",
        )
    )
    session.commit()


def test_expired_lease_is_reclaimed_and_old_worker_cannot_yield():
    engine = _db()
    with Session(engine) as s:
        _material(s)
        _job(s)
        first = claim_next_index_job(s, worker_id="worker-a", lease_seconds=30)
        assert first and first.lease_token
        old_token = first.lease_token
        s.exec(
            text("UPDATE studyindexjob SET lease_until=:past WHERE id=:id"),
            params={"past": datetime.utcnow() - timedelta(seconds=1), "id": first.id},
        )
        s.commit()

        second = claim_next_index_job(s, worker_id="worker-b", lease_seconds=30)
        assert second and second.id == first.id
        assert second.lease_token != old_token
        assert not yield_index_job(
            s,
            job_id=first.id,
            lease_token=old_token,
            worker_id="worker-a",
            stage="EMBED",
        )


def test_delete_during_build_blocks_publish_and_cancels_job():
    engine = _db()
    with Session(engine) as s:
        _material(s)
        _job(s)
        claimed = claim_next_index_job(s, worker_id="worker-a", lease_seconds=120)
        assert claimed and claimed.lease_token
        _ready_artifacts(s)

        assert tombstone_material(s, material_id=1, owner_user_id=10)
        s.commit()
        assert not publish_index_version(
            s,
            material_id=1,
            owner_user_id=10,
            index_version="v1",
            job_id=claimed.id,
            lease_token=claimed.lease_token,
            worker_id="worker-a",
        )
        status = s.exec(text("SELECT status FROM studyindexjob WHERE id=:id"), params={"id": claimed.id}).one()
        assert status[0] == "CANCELLED"


def test_incomplete_build_cannot_publish():
    engine = _db()
    with Session(engine) as s:
        _material(s)
        _job(s)
        claimed = claim_next_index_job(s, worker_id="worker-a", lease_seconds=120)
        assert claimed and claimed.lease_token
        s.add(
            StudyIndexPage(
                owner_user_id=10,
                course_id=20,
                material_id=1,
                index_version="v1",
                page_number=1,
                status="EXTRACTED",
                text_content="abc",
            )
        )
        s.commit()
        assert not publish_index_version(
            s,
            material_id=1,
            owner_user_id=10,
            index_version="v1",
            job_id=claimed.id,
            lease_token=claimed.lease_token,
            worker_id="worker-a",
        )


def test_superseded_generation_cannot_publish():
    engine = _db()
    with Session(engine) as s:
        _material(s)
        _job(s, "v1")
        claimed = claim_next_index_job(s, worker_id="worker-a", lease_seconds=120)
        assert claimed and claimed.lease_token
        _ready_artifacts(s, "v1")

        assert begin_material_build(s, material_id=1, owner_user_id=10, index_version="v2")
        s.commit()
        assert not publish_index_version(
            s,
            material_id=1,
            owner_user_id=10,
            index_version="v1",
            job_id=claimed.id,
            lease_token=claimed.lease_token,
            worker_id="worker-a",
        )


def test_complete_current_generation_publishes_atomically():
    engine = _db()
    with Session(engine) as s:
        _material(s)
        _job(s)
        claimed = claim_next_index_job(s, worker_id="worker-a", lease_seconds=120)
        assert claimed and claimed.lease_token
        _ready_artifacts(s)

        assert publish_index_version(
            s,
            material_id=1,
            owner_user_id=10,
            index_version="v1",
            job_id=claimed.id,
            lease_token=claimed.lease_token,
            worker_id="worker-a",
        )
        row = s.exec(
            text("SELECT active_index_version, building_index_version, index_status FROM studymaterial WHERE id=1")
        ).one()
        assert tuple(row) == ("v1", None, "READY")


def test_resource_classes_do_not_block_each_other():
    engine = _db()
    with Session(engine) as s:
        _material(s)
        normal = _job(s, "normal-v")
        s.exec(text("UPDATE studyindexjob SET resource_class='NORMAL' WHERE id=:id"), params={"id": normal.id})
        s.commit()

        # Second material represents OCR-heavy work.
        _material(s, material_id=2, owner=10, course=20)
        assert begin_material_build(s, material_id=2, owner_user_id=10, index_version="ocr-v")
        ocr = enqueue_index_job(
            s,
            owner_user_id=10,
            course_id=20,
            material_id=2,
            index_version="ocr-v",
            resource_class="OCR_HEAVY",
        )
        s.commit()

        claimed_normal = claim_next_index_job(s, worker_id="normal-worker", resource_class="NORMAL")
        assert claimed_normal and claimed_normal.id == normal.id
        claimed_ocr = claim_next_index_job(s, worker_id="ocr-worker", resource_class="OCR_HEAVY")
        assert claimed_ocr and claimed_ocr.id == ocr.id
