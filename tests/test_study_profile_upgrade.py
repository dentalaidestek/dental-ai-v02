from sqlalchemy import create_engine, text
from sqlmodel import Session, select

from app.study_index_jobs import StudyIndexJob
from app.study_index_profile import index_fingerprint
from app.study_v2_service import queue_owned_course_profile_upgrade


def test_owned_legacy_course_is_queued_once_and_woken_after_durable_commit(monkeypatch):
    from sqlalchemy import MetaData, Table
    from sqlalchemy.orm import registry
    from starlette.background import BackgroundTasks
    from app.study_v2_service import course_v2_ready
    monkeypatch.setenv('STUDY_ACADEMIC_V2_INDEXING','1')
    monkeypatch.setenv('STUDY_ACADEMIC_V2_READS','1')
    engine=create_engine('sqlite:///:memory:')
    StudyIndexJob.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text('''CREATE TABLE studymaterial (
            id INTEGER PRIMARY KEY, owner_user_id INTEGER, course_id INTEGER,
            active_index_version TEXT, building_index_version TEXT,
            mime_type TEXT, deleted_at TIMESTAMP,index_status TEXT,index_error TEXT)'''))
        conn.execute(text("INSERT INTO studymaterial VALUES (1,10,20,NULL,NULL,'application/pdf',NULL,'LEGACY',NULL),"
            "(2,11,20,NULL,NULL,'application/pdf',NULL,'LEGACY',NULL),"
            "(3,10,21,NULL,NULL,'application/pdf',NULL,'LEGACY',NULL)"))
    class Material:
        pass
    mapper=registry()
    mapper.map_imperatively(Material,Table('studymaterial',MetaData(),autoload_with=engine))
    with Session(engine) as session:
        tasks=BackgroundTasks()
        assert not course_v2_ready(session,material_model=Material,owner_user_id=10,course_id=20,
            upgrade_profile=True,background_tasks=tasks)
        jobs=session.exec(select(StudyIndexJob)).all()
        assert len(jobs)==1 and jobs[0].material_id==1
        assert jobs[0].index_version.startswith('upgrade-'+index_fingerprint()[:16]+'-')
        assert len(tasks.tasks)==1
        assert not course_v2_ready(session,material_model=Material,owner_user_id=10,course_id=20,
            upgrade_profile=True,background_tasks=BackgroundTasks())
        assert len(session.exec(select(StudyIndexJob)).all())==1
        # A worker-specific OCR fingerprint must not schedule a second full
        # rebuild immediately after this initial index finishes.
        job=jobs[0];job.status='DONE';job.index_fingerprint='worker-specific';session.add(job)
        session.execute(text("UPDATE studymaterial SET active_index_version=building_index_version,"
            "building_index_version=NULL,index_status='READY' WHERE id=1"));session.commit()
        assert course_v2_ready(session,material_model=Material,owner_user_id=10,course_id=20,
            upgrade_profile=True,background_tasks=BackgroundTasks())
        assert len(session.exec(select(StudyIndexJob)).all())==1


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
        # A lost dispatch is recovered on page open, without dispatching again
        # on each readiness poll or sending the request before DB commit.
        from sqlalchemy import MetaData, Table
        from sqlalchemy.orm import registry
        from starlette.background import BackgroundTasks
        from app.study_v2_service import course_v2_ready
        class Material:
            pass
        mapper = registry()
        mapper.map_imperatively(Material, Table('studymaterial', MetaData(), autoload_with=engine))
        page_tasks = BackgroundTasks()
        assert not course_v2_ready(session, material_model=Material, owner_user_id=10,
            course_id=20, upgrade_profile=True, background_tasks=page_tasks, wake_existing=True)
        assert len(page_tasks.tasks) == 1
        assert page_tasks.tasks[0].func.__name__ == 'wake_academic_modal_indexer'
        poll_tasks = BackgroundTasks()
        assert not course_v2_ready(session, material_model=Material, owner_user_id=10,
            course_id=20, upgrade_profile=True, background_tasks=poll_tasks)
        assert not poll_tasks.tasks
        # New upgrades schedule one wake after their transaction is committed.
        session.execute(text("UPDATE studyindexjob SET index_fingerprint='old' WHERE material_id=4"))
        session.commit()
        upgrade_tasks = BackgroundTasks()
        assert not course_v2_ready(session, material_model=Material, owner_user_id=10,
            course_id=20, upgrade_profile=True, background_tasks=upgrade_tasks)
        assert len(upgrade_tasks.tasks) == 1
        with Session(engine) as other_session:
            assert len(other_session.exec(select(StudyIndexJob).where(StudyIndexJob.status == 'QUEUED')).all()) == 2
        # Modal can publish a fingerprint derived from different OCR settings.
        # The requested target is still one completed attempt, not a new job
        # on each poll. Worker retries remain bounded by the existing job.
        version = sources[0]['building_index_version']
        assert version.startswith('upgrade-' + index_fingerprint()[:16] + '-')
        session.execute(text('''UPDATE studymaterial SET active_index_version=:version,
            building_index_version=NULL WHERE id=1'''), {'version': version})
        session.execute(text('''UPDATE studyindexjob SET status='DONE',
            index_fingerprint='worker-specific-profile' WHERE material_id=1 AND index_version=:version'''),
            {'version': version})
        session.commit()
        assert queue_owned_course_profile_upgrade(session, owner_user_id=10, course_id=20) == 0


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
