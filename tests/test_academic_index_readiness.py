import ast
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.orm import registry
from sqlmodel import Session
from starlette.background import BackgroundTasks
from starlette.responses import JSONResponse

from app import academic_index_readiness as readiness
from app import study_v2_service as service
from app.study_index_jobs import StudyIndexJob


@pytest.fixture
def database(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    StudyIndexJob.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(text('''CREATE TABLE studymaterial (
            id INTEGER PRIMARY KEY, owner_user_id INTEGER, course_id INTEGER,
            active_index_version TEXT, building_index_version TEXT, mime_type TEXT,
            deleted_at TIMESTAMP, index_status TEXT, index_error TEXT)'''))
    class Material:
        pass
    mapper = registry()
    mapper.map_imperatively(Material, Table('studymaterial', MetaData(), autoload_with=engine))
    monkeypatch.setenv('STUDY_ACADEMIC_V2_INDEXING', '1')
    monkeypatch.setenv('STUDY_ACADEMIC_V2_READS', '1')
    monkeypatch.setattr(service, 'queue_owned_legacy_course_materials', lambda *a, **kw: 0)
    monkeypatch.setattr(service, 'queue_owned_course_profile_upgrade', lambda *a, **kw: 0)
    readiness._wake_times.clear()
    yield engine, Material
    mapper.dispose()
    engine.dispose()
    readiness._wake_times.clear()


def add_material(session, mid=4, owner=1, course=7, building='current', active=None, deleted=None):
    session.execute(text('''INSERT INTO studymaterial VALUES
        (:id,:owner,:course,:active,:building,'application/pdf',:deleted,:state,NULL)'''),
        {'id': mid, 'owner': owner, 'course': course, 'active': active,
         'building': building, 'deleted': deleted, 'state': 'READY' if active else 'PROCESSING'})


def add_job(session, **overrides):
    values = dict(owner_user_id=1, course_id=7, material_id=4, index_version='current', status='QUEUED')
    values.update(overrides)
    session.add(StudyIndexJob(**values))
    session.commit()


@pytest.mark.parametrize('state', ['FAILED', 'CANCELLED'])
def test_terminal_current_job_is_failed_even_when_material_still_processing(database, state):
    engine, _ = database
    with Session(engine) as session:
        add_material(session)
        add_job(session, status=state)
        assert readiness.course_has_failed_build(session, owner_user_id=1, course_id=7)
        assert not readiness.course_has_due_build(session, owner_user_id=1, course_id=7)


def test_orphan_reservation_is_visible_without_creating_a_replacement_job(database):
    engine, _ = database
    with Session(engine) as session:
        add_material(session)
        session.commit()
        assert readiness.course_has_failed_build(session, owner_user_id=1, course_id=7)
        assert session.execute(text('SELECT COUNT(*) FROM studyindexjob')).scalar() == 0


def test_foreign_deleted_and_superseded_failures_do_not_block_owned_current_build(database):
    engine, _ = database
    with Session(engine) as session:
        add_material(session, mid=4, owner=2)
        add_job(session, owner_user_id=2, status='FAILED')
        add_material(session, mid=5, course=8)
        add_job(session, material_id=5, course_id=8, status='FAILED')
        add_material(session, mid=6, deleted=datetime(2026, 10, 24))
        add_job(session, material_id=6, status='FAILED')
        add_material(session, mid=7)
        add_job(session, material_id=7, index_version='old', status='FAILED')
        add_job(session, material_id=7, status='RUNNING', lease_until=datetime(2099, 1, 1))
        assert not readiness.course_has_failed_build(session, owner_user_id=1, course_id=7)
        assert not readiness.course_has_due_build(session, owner_user_id=1, course_id=7)


@pytest.mark.parametrize('state,retry,lease,due', [
    ('QUEUED', None, None, True), ('QUEUED', -1, None, True),
    ('QUEUED', 60, None, False), ('RUNNING', None, -1, True),
    ('RUNNING', None, 60, False), ('RUNNING', None, None, False),
    ('FAILED', None, -1, False), ('DONE', None, None, False)])
def test_wakes_only_claimable_owned_current_work(database, monkeypatch, state, retry, lease, due):
    engine, _ = database
    now = datetime(2026, 10, 24, 10)
    monkeypatch.setattr(readiness, '_now', lambda: now)
    with Session(engine) as session:
        add_material(session)
        add_job(session, status=state,
            next_retry_at=now + timedelta(seconds=retry) if retry is not None else None,
            lease_until=now + timedelta(seconds=lease) if lease is not None else None)
        assert readiness.course_has_due_build(session, owner_user_id=1, course_id=7) is due


def test_recovery_poll_coalesces_wakes_without_requeue_or_checkpoint_changes(database, monkeypatch):
    engine, Material = database
    clock = [100.0]
    monkeypatch.setattr(readiness, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    with Session(engine) as session:
        add_material(session)
        add_job(session, status='RUNNING', stage='OCR', lease_until=datetime(2020, 1, 1))
        def probe():
            tasks = BackgroundTasks()
            assert not service.course_v2_ready(session, material_model=Material,
                owner_user_id=1, course_id=7, upgrade_profile=True,
                background_tasks=tasks, wake_existing=True, recovery_poll=True)
            return tasks
        assert len(probe().tasks) == 1
        for _ in range(4):
            clock[0] += 15
            tasks = probe()
            assert len(tasks.tasks) == (1 if clock[0] == 160 else 0)
        row = session.execute(text('SELECT status,stage,lease_until,index_version FROM studyindexjob')).one()
        assert row[0] == 'RUNNING' and row[1] == 'OCR' and row[3] == 'current'


def test_simultaneous_poll_schedules_one_wake(database):
    with ThreadPoolExecutor(max_workers=8) as executor:
        answers = list(executor.map(lambda _: readiness.allow_recovery_poll_wake(
            owner_user_id=1, course_id=7), range(32)))
    assert sum(answers) == 1


def test_live_status_contract_reports_three_of_four_failed_instead_of_preparing(database):
    engine, Material = database
    with Session(engine) as session:
        for mid in (1, 2, 3):
            add_material(session, mid=mid, building=None, active='published')
        add_material(session)
        add_job(session, status='FAILED')
    # Exercise the actual endpoint body without importing unrelated application
    # integrations or needing production credentials.
    tree = ast.parse((Path(__file__).parents[1] / 'app/main.py').read_text())
    endpoint = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'study_ai_index_status')
    endpoint.decorator_list = []
    code = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), endpoint], type_ignores=[])
    namespace = dict(Session=Session, engine=engine, select=__import__('sqlmodel').select,
        StudyMaterial=Material, JSONResponse=JSONResponse, course_v2_ready=service.course_v2_ready,
        get_current_user=lambda request: SimpleNamespace(id=1), _owned_study_course=lambda *a: True)
    exec(compile(ast.fix_missing_locations(code), '<actual-index-status>', 'exec'), namespace)
    tasks = BackgroundTasks()
    response = namespace['study_ai_index_status'](SimpleNamespace(query_params={}), 7, tasks)
    data = json.loads(response.body)
    assert data['completed'] == 3 and data['total'] == 4
    assert data['state'] == 'failed' and data['ready'] is False
    assert not tasks.tasks
