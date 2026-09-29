"""Behavioral regressions for queue, storage, realtime and admission boundaries."""
import asyncio
from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine, select
from app import main, work_jobs, object_cache, provider_budget


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path}/test.db')
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(provider_budget, '_engine', lambda: engine)
    with Session(engine, expire_on_commit=False) as s:
        user = main.User(username='synthetic', role='DOCTOR', display_name='Synthetic')
        s.add(user); s.commit()
        patient = main.Patient(anonymous_id='synthetic', owner_user_id=user.id)
        s.add(patient); s.commit()
        analysis = main.Analysis(patient_id=patient.id)
        guest = main.GuestAnalysis(owner_user_id=user.id)
        s.add(analysis); s.add(guest); s.commit()
        ids = SimpleNamespace(user=user.id, patient=patient.id, analysis=analysis.id, guest=guest.id)
    yield engine, ids
    engine.dispose()


def enqueue(engine, ids, kind='PRELIMINARY', guest=False):
    with Session(engine, expire_on_commit=False) as s:
        job = work_jobs.enqueue(s, kind=kind, resource_type='GUEST' if guest else 'ANALYSIS',
                                resource_id=ids.guest if guest else ids.analysis)
        s.commit()
        return job


def test_dedupe_resource_serialization_and_stale_lease(database):
    engine, ids = database
    first = enqueue(engine, ids)
    assert enqueue(engine, ids).id == first.id
    enqueue(engine, ids, 'FINAL')
    claimed = work_jobs.claim(engine)
    assert claimed.id == first.id
    assert work_jobs.claim(engine) is None
    with engine.begin() as c:
        c.execute(text('UPDATE workjob SET lease_until=:past WHERE id=:id'),
                  {'past': work_jobs.now()-timedelta(seconds=1), 'id': first.id})
    replacement = work_jobs.claim(engine)
    assert replacement.lease_token != claimed.lease_token
    assert not work_jobs.heartbeat(engine, claimed)
    work_jobs.finish(engine, claimed, status='DONE')
    with Session(engine) as s:
        assert s.get(work_jobs.WorkJob, first.id).status == 'RUNNING'


def test_source_edit_fences_publication_and_retry(database):
    engine, ids = database
    enqueue(engine, ids)
    job = work_jobs.claim(engine)
    token = work_jobs.current_job.set(job)
    try:
        with Session(engine) as s:
            work_jobs.guard_publication(s)
        with Session(engine) as s:
            patient = s.get(main.Patient, ids.patient)
            patient.chief_complaint = 'updated'; s.add(patient); s.commit()
        with Session(engine) as s, pytest.raises(work_jobs.WorkCancelled, match='SOURCE_CHANGED'):
            work_jobs.guard_publication(s)
    finally:
        work_jobs.current_job.reset(token)


def test_atomic_publication_has_no_connection_during_blob_io(database, monkeypatch, tmp_path):
    engine, ids = database
    monkeypatch.chdir(tmp_path)
    enqueue(engine, ids)
    job = work_jobs.claim(engine)
    writes = []
    def write(path, content, **kwargs):
        assert engine.pool.checkedout() == 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        writes.append(str(path))
    monkeypatch.setattr(main, 'storage_write_text', write)
    token = work_jobs.current_job.set(job)
    try:
        with Session(engine, expire_on_commit=False) as s:
            analysis = s.get(main.Analysis, ids.analysis)
            main._publish_clinical_result(s, analysis, json.dumps({'ai_result': {'status': 'OK'}}), status='AI_ANALYZED')
        with Session(engine) as s:
            assert s.get(main.Analysis, ids.analysis).result_path == writes[0]
            assert s.get(work_jobs.WorkJob, job.id).status == 'DONE'
            assert not s.exec(select(work_jobs.WorkGarbage)).all()
    finally:
        work_jobs.current_job.reset(token)


def test_analysis_asset_releases_connection_before_blob_io(database, monkeypatch, tmp_path):
    engine, ids = database
    with Session(engine, expire_on_commit=False) as s:
        user = s.get(main.User, ids.user)
        s.add(main.ImageAsset(
            analysis_id=ids.analysis,
            original_filename='scan.jpg',
            stored_filename='scan.jpg',
            file_path='uploads/scan.jpg',
        ))
        s.commit()

    local_path = tmp_path / 'scan.jpg'
    local_path.write_bytes(b'image')
    monkeypatch.setattr(main, 'get_current_user', lambda request: user)

    def ensure_local(reference):
        assert reference == 'uploads/scan.jpg'
        assert engine.pool.checkedout() == 0
        return local_path

    monkeypatch.setattr(main, 'storage_ensure_local', ensure_local)
    response = main.analysis_primary_asset(None, ids.analysis)

    assert Path(response.path) == local_path


def test_admin_storage_releases_connection_before_metadata_io(database, monkeypatch):
    engine, ids = database
    with Session(engine, expire_on_commit=False) as s:
        user = s.get(main.User, ids.user)
        user.profile_photo_path = 'uploads/profile.jpg'
        s.add(user)
        s.commit()

    def size(reference):
        assert reference == 'uploads/profile.jpg'
        assert engine.pool.checkedout() == 0
        return 17

    monkeypatch.setattr(main, 'storage_size', size)
    with Session(engine, expire_on_commit=False) as s:
        summary = main._admin_user_storage_summaries(s, [user])

    assert summary[ids.user]['total_bytes'] == 17


def test_admin_user_detail_storage_releases_connection_before_metadata_io(database, monkeypatch):
    engine, ids = database
    with Session(engine, expire_on_commit=False) as s:
        user = s.get(main.User, ids.user)
        user.profile_photo_path = 'uploads/profile.jpg'
        s.add(user)
        s.commit()

    def size(reference):
        assert reference == 'uploads/profile.jpg'
        assert engine.pool.checkedout() == 0
        return 23

    monkeypatch.setattr(main, 'storage_size', size)
    with Session(engine, expire_on_commit=False) as s:
        summary = main._admin_user_storage_summary(s, ids.user)

    assert summary['total_bytes'] == 23


def test_pending_ui_has_bounded_completion_detection_delay():
    templates = Path(main.__file__).parent / 'templates'
    viewer = (templates / 'analysis_viewer.html').read_text()
    pending = (templates / 'work_pending.html').read_text()

    assert 'Math.min(5000,2000*Math.pow(1.3,n))' in viewer
    assert 'Math.min(10000,Math.round(delay*1.4))' in pending
    assert 'Math.min(15000,' not in viewer
    assert 'Math.min(30000,' not in pending


@pytest.mark.parametrize('guest', [False, True])
def test_vision_updates_correct_table_and_retries_partial(database, monkeypatch, guest):
    engine, ids = database
    monkeypatch.setattr(main, '_persisted_vision_payload', lambda *a: {'status': 'partial'})
    with pytest.raises(RuntimeError, match='VISION_PROVIDER_UNAVAILABLE'):
        main._run_vision(ids.guest if guest else ids.analysis, guest=guest)
    with Session(engine) as s:
        assert s.get(main.GuestAnalysis if guest else main.Analysis, ids.guest if guest else ids.analysis).status == 'VISION_READY'
        assert s.get(main.Analysis if guest else main.GuestAnalysis, ids.analysis if guest else ids.guest).status == 'DRAFT'


def test_cache_reader_pins_budget_and_invalidation(tmp_path, monkeypatch):
    monkeypatch.setenv('R2_CACHE_DIR', str(tmp_path))
    monkeypatch.setenv('R2_CACHE_MAX_BYTES', '8')
    def get(key, value):
        return object_cache.materialize(key, metadata=lambda: {'ContentLength': len(value)},
            download=lambda path, size: path.write_bytes(value))
    with object_cache.scope():
        old = get('one.txt', b'12345678')
        with pytest.raises(object_cache.CacheCapacityError):
            get('two.txt', b'x')
        object_cache.invalidate('one.txt')
        assert old.read_bytes() == b'12345678'
    with object_cache.scope():
        new = get('one.txt', b'updated')
        assert new.read_bytes() == b'updated'
    assert not old.exists()
    assert sum(p.stat().st_size for p in tmp_path.glob('*.data*')) <= 8


def test_provider_global_capacity_and_wildcard_budget(database, monkeypatch):
    engine, _ = database
    monkeypatch.setenv('STUDY_ROUTER_REQUEST_BUDGETS_JSON', '{"gemini:*":{"day":2}}')
    with provider_budget.reservation('gemini', 'one', capacity=1):
        assert engine.pool.checkedout() == 0
        with pytest.raises(provider_budget.ProviderBusy, match='capacity'):
            with provider_budget.reservation('gemini', 'two', capacity=1):
                pass
    with provider_budget.reservation('gemini', 'two', capacity=1):
        pass
    with pytest.raises(provider_budget.ProviderBusy, match='budget'):
        with provider_budget.reservation('gemini', 'three'):
            pass
    with Session(engine) as s:
        assert not s.exec(select(provider_budget.ProviderSlot)).all()


def test_request_limits_chunked_and_slot_release():
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from app.request_limits import RequestLimits
    app = FastAPI()
    @app.post('/')
    async def body(request: Request):
        return {'bytes': len(await request.body())}
    app.add_middleware(RequestLimits, max_bytes=4)
    with TestClient(app) as client:
        assert client.post('/', content=b'12345').status_code == 413
        assert client.post('/', content=iter([b'12', b'345'])).status_code == 413
        assert client.post('/', content=b'1234').json() == {'bytes': 4}


def test_socket_writes_serialize_without_blocking_loop():
    from app.realtime_io import SocketWrites
    async def scenario():
        writes = SocketWrites()
        class Socket:
            active = 0
            async def accept(self): pass
            async def close(self, **kwargs): pass
            async def send_json(self, payload):
                self.active += 1
                assert self.active == 1
                await asyncio.sleep(.005)
                self.active -= 1
        socket = Socket()
        assert await writes.accept(socket)
        assert all(await asyncio.gather(*(writes.send(socket, {'n': i}) for i in range(10))))
        writes.discard(socket)
        assert not writes.states
    asyncio.run(scenario())


def test_realtime_listener_delivers_late_lower_id_and_resync(database, monkeypatch):
    engine, ids = database
    with Session(engine, expire_on_commit=False) as s:
        events = [main.RealtimeEvent(user_id=ids.user, event_type='MESSAGE_CREATED', entity_type='case', entity_id=1, payload_json='{}') for _ in range(2)]
        s.add_all(events); s.commit()
    seen = []
    class Listener:
        def __init__(self, *args):
            self.batches = [[(main.PG_REALTIME_CHANNEL, str(events[1].id))], [(main.PG_REALTIME_CHANNEL, str(events[0].id))], [None]]
        def start(self): pass
        async def batch(self):
            if not self.batches: raise asyncio.CancelledError()
            return self.batches.pop(0)
        async def close(self): pass
    async def send(uid, payload): seen.append(payload)
    rows = main._realtime_listener_rows
    monkeypatch.setattr(main, 'PostgresNotices', Listener)
    monkeypatch.setattr(main.user_realtime_socket_hub, 'users', {ids.user: set()})
    monkeypatch.setattr(main.user_realtime_socket_hub, 'send', send)
    monkeypatch.setattr(main, 'DATABASE_URL', 'postgresql://synthetic')
    from sqlalchemy.engine import make_url
    fake = SimpleNamespace(dialect=SimpleNamespace(name='postgresql'), url=make_url('postgresql://synthetic'))
    monkeypatch.setattr(main, 'engine', fake)
    def load(after, users, event_ids=None):
        with Session(engine, expire_on_commit=False) as s:
            return list(s.exec(select(main.RealtimeEvent).where(main.RealtimeEvent.id.in_(event_ids))).all())
    monkeypatch.setattr(main, '_realtime_listener_rows', load)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main._postgres_event_listener(listen_deadline=False, listen_program=False))
    assert [p.get('event_id') for p in seen] == [events[1].id, events[0].id, None]
    assert seen[-1] == {'type': 'resync'}


@pytest.mark.parametrize('guest', [False, True])
def test_upload_queues_atomically_and_closes_db_for_storage(database, monkeypatch, tmp_path, guest):
    from fastapi.testclient import TestClient
    engine, ids = database
    with Session(engine) as s:
        user = s.get(main.User, ids.user)
    monkeypatch.setattr(main, 'get_current_user', lambda request: user)
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    def persist(path, **kwargs):
        assert engine.pool.checkedout() == 0
        assert Path(path).read_bytes() == b'synthetic image'
        return str(path)
    monkeypatch.setattr(main, 'storage_persist_file', persist)
    def classify(path):
        assert engine.pool.checkedout() == 0
        return 'PANORAMIC'
    monkeypatch.setattr(main, 'classify_dental_image', classify)
    client = TestClient(main.app)
    url = '/analysis/guest/new' if guest else f'/analysis/new/{ids.patient}'
    response = client.post(url, files={'images': ('example.jpg', b'synthetic image', 'image/jpeg')}, follow_redirects=False)
    assert response.status_code == 303
    with Session(engine) as s:
        jobs = s.exec(select(work_jobs.WorkJob)).all()
        assert len(jobs) == 1 and jobs[0].kind == 'VISION'
        job_id = jobs[0].id
    assert client.get(f'/jobs/{job_id}').json()['status'] == 'QUEUED'
    assert client.post(f'/jobs/{job_id}/cancel').status_code == 200
    assert client.get(f'/jobs/{job_id}').json()['status'] == 'CANCELLED'


def test_deletion_retry_is_fenced_and_remote_io_has_no_transaction(database, monkeypatch):
    from app import study_deletion_worker as worker
    from app.study_index_jobs import StudyDeletionJob
    engine, ids = database
    with Session(engine) as s:
        s.add(StudyDeletionJob(owner_user_id=ids.user, material_id=999, storage_reference='uploads/synthetic'))
        s.commit()
    def fail(reference):
        assert engine.pool.checkedout() == 0
        raise IOError('synthetic provider failure')
    monkeypatch.setattr(worker, 'storage_delete', fail)
    with Session(engine, expire_on_commit=False) as s:
        assert worker.run_deletion_slice(s) == 'RETRY'
        job = s.exec(select(StudyDeletionJob)).one()
        assert job.status == 'FAILED'
        job.next_retry_at = work_jobs.now()-timedelta(seconds=1)
        s.add(job); s.commit()
        stale = worker._claim(s)
        job = s.get(StudyDeletionJob, stale['id'])
        job.next_retry_at = work_jobs.now()-timedelta(seconds=1)
        s.add(job); s.commit()
        replacement = worker._claim(s)
        assert replacement['attempts'] == stale['attempts']+1
        assert not worker._finish(s, stale, status='DONE')
        assert worker._finish(s, replacement, status='DONE')


def test_r2_failed_delete_preserves_local_source(tmp_path, monkeypatch):
    from app import object_storage as store
    path = tmp_path/'synthetic'
    path.write_bytes(b'original')
    monkeypatch.setenv('R2_ENABLED', '1')
    monkeypatch.setattr(store, '_settings', lambda: ('synthetic', '', '', ''))
    class Client:
        def delete_object(self, **kwargs): raise OSError('unavailable')
    monkeypatch.setattr(store, '_client', lambda: Client())
    with pytest.raises(store.ObjectStorageError):
        store.delete(path)
    assert path.read_bytes() == b'original'


def test_index_queue_admission_rolls_back_material_build(database, monkeypatch):
    from app.study_index_jobs import enqueue_index_job
    engine, ids = database
    monkeypatch.setenv('STUDY_MAX_PENDING_INDEX_JOBS', '1')
    with Session(engine) as s:
        enqueue_index_job(s, owner_user_id=ids.user, course_id=1, material_id=1, index_version='first')
        s.commit()
        with pytest.raises(work_jobs.WorkCapacity):
            enqueue_index_job(s, owner_user_id=ids.user, course_id=1, material_id=2, index_version='second')
        s.rollback()
        assert len(s.exec(select(main.StudyIndexJob)).all()) == 1


def test_oversize_image_leaves_no_file(tmp_path):
    from app.upload_io import copy_image
    from io import BytesIO
    from starlette.exceptions import HTTPException
    target = tmp_path/'image.jpg'
    with pytest.raises(HTTPException) as caught:
        copy_image(BytesIO(b'12345'), target, maximum=4)
    assert caught.value.status_code == 413 and not target.exists()


def test_storage_outage_is_not_reported_as_missing(monkeypatch):
    from app import object_storage as store
    monkeypatch.setenv('R2_ENABLED', '1')
    monkeypatch.setattr(store, '_settings', lambda: ('synthetic', '', '', ''))
    class Client:
        def head_object(self, **kwargs): raise OSError('unavailable')
    monkeypatch.setattr(store, '_client', lambda: Client())
    with pytest.raises(store.ObjectStorageError): store.exists('uploads/synthetic')
    with pytest.raises(store.ObjectStorageError): store.size('uploads/synthetic')


def test_read_receipts_are_durable_for_both_users_and_do_not_repeat(database):
    engine, ids = database
    with Session(engine, expire_on_commit=False) as s:
        other = main.User(username='peer', role='DOCTOR', display_name='Peer')
        s.add(other); s.commit()
        case = main.ConsultationCase(requester_user_id=ids.user, expert_user_id=other.id,
            specialty='Endodonti', clinical_summary='Synthetic', question='Synthetic',
            status='ACTIVE', expert_response_deadline=work_jobs.now()+timedelta(hours=1))
        s.add(case); s.commit()
        message = main.ConsultationMessage(case_id=case.id, sender_user_id=other.id, content='Synthetic')
        s.add(message); s.commit()
    receipt = main._socket_case_authorized(ids.user, case.id, mark_read=True)
    assert receipt['through_id'] == message.id
    assert {event.user_id for event in receipt['events']} == {ids.user, other.id}
    assert all(event.event_type == 'CASE_READ' for event in receipt['events'])
    assert main._socket_case_authorized(ids.user, case.id, mark_read=True)['events'] == []
    assert main._socket_case_authorized(999999, case.id, mark_read=True) is False


def test_worker_dispatch_retries_transient_failure_without_open_session(database, monkeypatch):
    from app import work_worker
    engine, ids = database
    submitted = enqueue(engine, ids, guest=True)
    def unavailable(ident):
        assert ident == ids.guest and engine.pool.checkedout() == 0
        raise IOError('synthetic temporary failure')
    monkeypatch.setattr(main, '_run_guest_preliminary_ai', unavailable)
    assert work_worker.run_one(engine)
    with Session(engine) as s:
        job = s.get(work_jobs.WorkJob, submitted.id)
        assert job.status == 'QUEUED' and job.attempts == 1
        assert job.available_at > work_jobs.now() and job.lease_token is None
