from sqlalchemy import create_engine, text
from sqlmodel import Session, select

from app.study_index_jobs import StudyIndexJob
from app.study_index_profile import index_fingerprint
from app.study_v2_service import queue_owned_course_profile_upgrade


def test_profile_upgrade_is_owned_idempotent_and_preserves_published_sources(monkeypatch):
    monkeypatch.setenv('STUDY_ACADEMIC_V2_INDEXING', '1')
    monkeypatch.setenv('STUDY_ACADEMIC_V2_READS', '1')
    engine = create_engine('sqlite:///:memory:')
    StudyIndexJob.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text('''CREATE TABLE studymaterial (
            id INTEGER PRIMARY KEY, owner_user_id INTEGER, course_id INTEGER,
            active_index_version TEXT, building_index_version TEXT,
            mime_type TEXT, deleted_at TIMESTAMP, index_status TEXT, index_error TEXT
        )'''))
    with Session(engine) as session:
        for mid, owner, course, profile in (
            (1, 10, 20, 'old'), (2, 11, 20, 'old'), (3, 10, 21, 'old'),
            (4, 10, 20, index_fingerprint()), (5, 10, 20, None),
        ):
            session.execute(text('''INSERT INTO studymaterial
                (id, owner_user_id, course_id, active_index_version, mime_type, index_status)
                VALUES (:id, :owner, :course, 'published', 'application/pdf', 'READY')'''),
                {'id': mid, 'owner': owner, 'course': course})
            session.add(StudyIndexJob(owner_user_id=owner, course_id=course,
                material_id=mid, index_version='published', status='DONE',
                index_fingerprint=profile))
        session.commit()
        assert queue_owned_course_profile_upgrade(session, owner_user_id=10, course_id=20) == 1
        session.commit()
        assert queue_owned_course_profile_upgrade(session, owner_user_id=10, course_id=20) == 0
        sources = session.execute(text('SELECT * FROM studymaterial ORDER BY id')).mappings().all()
        assert sources[0]['building_index_version']
        assert all(row['active_index_version'] == 'published' for row in sources)
        assert all(row['index_status'] == 'READY' for row in sources)
        assert all(row['building_index_version'] is None for row in sources[1:])
        pending = session.exec(select(StudyIndexJob).where(StudyIndexJob.status == 'QUEUED')).all()
        assert len(pending) == 1
        assert pending[0].material_id == 1
        assert pending[0].index_version == sources[0]['building_index_version']


def test_disabled_profile_upgrade_does_not_touch_database(monkeypatch):
    monkeypatch.setenv('STUDY_ACADEMIC_V2_INDEXING', '0')
    assert queue_owned_course_profile_upgrade(None, owner_user_id=10, course_id=20) == 0


def test_readiness_rolls_back_reservation_when_queue_is_full(monkeypatch):
    import app.study_v2_service as service
    from app.work_jobs import WorkCapacity
    from unittest.mock import Mock
    session = Mock()
    def full(*args, **kwargs):
        raise WorkCapacity('queue full')
    monkeypatch.setattr(service, 'queue_owned_course_profile_upgrade', full)
    assert not service.course_v2_ready(session, material_model=None,
        owner_user_id=10, course_id=20, upgrade_profile=True)
    session.rollback.assert_called_once()
    session.commit.assert_not_called()
