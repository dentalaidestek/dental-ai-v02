"""HTTP regressions from the broader audit. All records and providers are synthetic."""
import asyncio
from io import BytesIO
import threading
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select, func

from app import main, mobile_api, mobile_analysis_api, mobile_modern_api_v3
from app.browser_origin import BrowserOriginGuard


@pytest.fixture
def platform_db(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path}/synthetic.db', pool_size=2, max_overflow=0)
    SQLModel.metadata.create_all(engine)
    for module in (main, mobile_api, mobile_analysis_api, mobile_modern_api_v3):
        monkeypatch.setattr(module, 'engine', engine)
    monkeypatch.setattr(main, '_maintenance_response', lambda request: None)
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username='audit-owner', display_name='Synthetic', role='DOCTOR',
                         email_verified_at=main._utcnow_naive())
        outsider = main.User(username='audit-other', display_name='Other', role='DOCTOR',
                             email_verified_at=main._utcnow_naive())
        session.add_all([user, outsider]); session.commit()
        patient = main.Patient(owner_user_id=user.id, anonymous_id='synthetic')
        session.add(patient); session.commit()
        ids = SimpleNamespace(user=user, outsider=outsider, patient=patient.id)
    monkeypatch.setattr(main, 'get_current_user', lambda request: user)
    monkeypatch.chdir(tmp_path)
    yield engine, ids
    engine.dispose()


@pytest.mark.parametrize('origin', ['https://evil.example', 'https://evil.dentalai.tr', 'null',
                                   'https://dentalai.tr.evil.example', 'https://dentalai.tr:444'])
def test_untrusted_browser_origin_cannot_create_owned_course(platform_db, origin):
    engine, ids = platform_db
    client = TestClient(main.app, base_url='https://dentalai.tr')
    result = client.post('/notes/courses', data={'title': 'Synthetic course'},
                         headers={'Origin': origin}, follow_redirects=False)
    assert result.status_code == 403
    with Session(engine) as session:
        assert session.exec(select(func.count(main.StudyCourse.id))).one() == 0


@pytest.mark.parametrize('origin', [None, 'https://dentalai.tr', 'https://www.dentalai.tr'])
def test_same_origin_or_native_no_origin_keeps_existing_contract(platform_db, origin):
    client = TestClient(main.app, base_url='https://dentalai.tr')
    result = client.post('/notes/courses', data={'title': 'Synthetic course'},
        headers={'Origin': origin} if origin else {}, follow_redirects=False)
    assert result.status_code == 303


def test_origin_guard_rejects_cross_site_fetch_metadata_without_db_work():
    app = FastAPI()
    calls = []
    @app.post('/mutation')
    async def mutation():
        calls.append(1)
        return {'ok': True}
    app.add_middleware(BrowserOriginGuard)
    client = TestClient(app)
    assert client.post('/mutation', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert calls == []
    assert client.post('/mutation').status_code == 200


@pytest.mark.parametrize('kind', ['patient', 'compatibility_patient', 'analysis'])
def test_mobile_upload_offloads_and_releases_db_during_storage(platform_db, monkeypatch, kind):
    engine, ids = platform_db
    module, endpoint = {
        'patient': (mobile_api, mobile_api.mobile_patient_media_upload),
        'compatibility_patient': (mobile_modern_api_v3, mobile_modern_api_v3.mobile_upload_media),
        'analysis': (mobile_analysis_api, mobile_analysis_api.create_mobile_analysis),
    }[kind]
    entered, release = threading.Event(), threading.Event()
    threads = {}
    published = []
    async def publish(event):
        published.append(threading.get_ident())
    monkeypatch.setattr(module, '_publish_realtime_event', publish, raising=False)
    def persist(path, **kwargs):
        threads['storage'] = threading.get_ident()
        assert engine.pool.checkedout() == 0
        entered.set()
        assert release.wait(3), 'Test did not release synthetic storage'
    monkeypatch.setattr(module, 'storage_persist_file', persist)
    if kind == 'analysis':
        monkeypatch.setattr(module, 'classify_dental_image', lambda path: 'OTHER')
        monkeypatch.setattr(module, '_enqueue_work', lambda *a: SimpleNamespace(id=123))
    app = FastAPI()
    path = '/upload' if kind == 'analysis' else '/upload/{patient_id}'
    app.add_api_route(path, endpoint, methods=['POST'])
    app.dependency_overrides[mobile_api._mobile_user] = lambda: ids.user
    @app.get('/fast')
    async def fast():
        return {'ok': True}
    image = BytesIO(); Image.new('RGB', (16, 16), 'white').save(image, format='PNG')
    async def exercise():
        threads['loop'] = threading.get_ident()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic') as client:
            url = '/upload' if kind == 'analysis' else f'/upload/{ids.patient}'
            data = {'patient_id': str(ids.patient)} if kind == 'analysis' else {}
            field = 'images' if kind == 'analysis' else 'file'
            task = asyncio.create_task(client.post(url, data=data,
                files={field: ('synthetic.png', image.getvalue(), 'image/png')}))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert (await asyncio.wait_for(client.get('/fast'), 1)).status_code == 200
            finally:
                release.set()
            response = await task
            assert response.status_code == 200, response.text
    asyncio.run(exercise())
    assert threads['storage'] != threads['loop']
    if kind != 'compatibility_patient':
        assert published == [threads['loop']]
    assert engine.pool.checkedout() == 0


def test_legacy_ai_uses_bounded_dashboard_and_does_not_leak_upstream_error(platform_db, monkeypatch):
    engine, ids = platform_db
    from app import ai_provider
    secret = 'SYNTHETIC_UPSTREAM_SECRET'
    def fail(prompt):
        raise RuntimeError(secret)
    monkeypatch.setattr(ai_provider, 'ask_ai', fail)
    with Session(engine) as session:
        session.add_all([main.Patient(owner_user_id=ids.user.id, anonymous_id=f'synthetic-{i}')
                         for i in range(20)])
        session.commit()
    loads = []
    def loaded(target, context):
        loads.append(type(target).__name__)
    for model in (main.Patient, main.Analysis, main.ClinicalRecord):
        event.listen(model, 'load', loaded)
    monkeypatch.setattr(main, '_dashboard_next_schedule_occurrence', lambda *a: None)
    monkeypatch.setattr(main.templates, 'TemplateResponse', lambda **kw: SimpleNamespace(context=kw['context']))
    try:
        result = main.ai_ask(SimpleNamespace(state=SimpleNamespace()), 'Sentetik soru')
        assert len(result.context['patients']) == 3
        assert loads.count('Patient') == 3
        assert 'Analysis' not in loads and 'ClinicalRecord' not in loads
        assert secret not in result.context['ai_error']
    finally:
        for model in (main.Patient, main.Analysis, main.ClinicalRecord):
            event.remove(model, 'load', loaded)
    assert main.ai_ask(None, 'x' * 8001).status_code == 400


@pytest.mark.parametrize('failure', ['invalid_image', 'storage', 'queue'])
def test_failed_native_analysis_intake_has_no_stuck_row_or_unreferenced_local_files(
        platform_db, monkeypatch, failure):
    from pathlib import Path
    from app.object_storage import ObjectStorageError
    from app.work_jobs import WorkCapacity
    engine, ids = platform_db
    module = mobile_analysis_api
    def persist(path, **kwargs):
        assert engine.pool.checkedout() == 0
        if failure == 'storage':
            raise ObjectStorageError('synthetic outage')
    monkeypatch.setattr(module, 'storage_persist_file', persist)
    monkeypatch.setattr(module, 'storage_delete', lambda path: Path(path).unlink(missing_ok=True))
    monkeypatch.setattr(module, 'classify_dental_image', lambda path: 'OTHER')
    if failure == 'queue':
        def full(*args):
            raise WorkCapacity('synthetic full queue')
        monkeypatch.setattr(module, '_enqueue_work', full)
    image = BytesIO(); Image.new('RGB', (16, 16), 'white').save(image, format='PNG')
    content = b'invalid' if failure == 'invalid_image' else image.getvalue()
    main.app.dependency_overrides[mobile_api._mobile_user] = lambda: ids.user
    try:
        response = TestClient(main.app, base_url='https://dentalai.tr').post('/api/mobile/v1/analyses',
            data={'patient_id': str(ids.patient)}, files={'images': ('synthetic.png', content, 'image/png')})
        assert response.status_code == (422 if failure == 'invalid_image' else 503)
        with Session(engine) as session:
            assert session.exec(select(func.count(main.Analysis.id))).one() == 0
            assert session.exec(select(func.count(main.ImageAsset.id))).one() == 0
        assert list(Path('uploads').glob('analysis_*')) == []
    finally:
        main.app.dependency_overrides.pop(mobile_api._mobile_user, None)


def test_native_analysis_commits_job_and_survives_live_notification_failure(platform_db, monkeypatch):
    engine, ids = platform_db
    module = mobile_analysis_api
    monkeypatch.setattr(module, 'storage_persist_file', lambda path: None)
    monkeypatch.setattr(module, 'classify_dental_image', lambda path: 'OTHER')
    async def unavailable(event):
        raise RuntimeError('synthetic websocket delivery failure')
    monkeypatch.setattr(module, '_publish_realtime_event', unavailable)
    image = BytesIO(); Image.new('RGB', (16, 16), 'white').save(image, format='PNG')
    main.app.dependency_overrides[mobile_api._mobile_user] = lambda: ids.user
    try:
        response = TestClient(main.app, base_url='https://dentalai.tr').post('/api/mobile/v1/analyses',
            data={'patient_id': str(ids.patient)}, files={'images': ('synthetic.png', image.getvalue(), 'image/png')})
        assert response.status_code == 200, response.text
        data = response.json()
        with Session(engine) as session:
            assert session.get(main.Analysis, data['analysis_id']) is not None
            job = session.get(main.work_jobs.WorkJob, data['job_id'])
            assert job.status == 'QUEUED' and job.owner_user_id == ids.user.id
            assert session.exec(select(func.count(main.RealtimeEvent.id))).one() >= 1
    finally:
        main.app.dependency_overrides.pop(mobile_api._mobile_user, None)


def test_patient_directory_is_owned_paged_and_searches_older_rows(platform_db, monkeypatch):
    engine, ids = platform_db
    with Session(engine) as session:
        oldest = session.get(main.Patient, ids.patient)
        oldest.first_name = 'OlderMatch'; session.add(oldest)
        session.add_all([main.Patient(anonymous_id=f'local-{i}', owner_user_id=ids.user.id)
                         for i in range(111)])
        session.add(main.Patient(anonymous_id='foreign', owner_user_id=ids.outsider.id))
        session.commit()
    monkeypatch.setattr(main.templates, 'TemplateResponse', lambda **kw: SimpleNamespace(context=kw['context']))
    before, seen = None, []
    for _ in range(4):
        result = main.all_patients(None, before=before).context
        assert len(result['patients']) <= 50
        assert all(patient.owner_user_id == ids.user.id for patient in result['patients'])
        seen.extend(patient.id for patient in result['patients'])
        before = result['next_before']
        if before is None:
            break
    assert len(seen) == len(set(seen)) == 112
    matches = main.all_patients(None, q='OlderMatch').context['patients']
    assert [patient.id for patient in matches] == [ids.patient]


def test_password_hash_and_verification_share_bounded_slots_and_release_after_failure(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app import auth
    monkeypatch.setattr(auth, '_password_slots', threading.BoundedSemaphore(1))
    entered, release = threading.Event(), threading.Event()
    def slow_hash(password):
        entered.set()
        assert release.wait(2)
        return 'synthetic-hash'
    monkeypatch.setattr(auth, '_PASSWORD_HASHER', SimpleNamespace(hash=slow_hash, verify=lambda *a: True))
    with ThreadPoolExecutor(max_workers=1) as pool:
        held = pool.submit(auth.hash_password, 'synthetic')
        try:
            assert entered.wait(1)
            with pytest.raises(main.HTTPException) as error:
                auth.verify_password('synthetic', '$argon2-synthetic')
            assert error.value.status_code == 503 and error.value.headers['Retry-After']
        finally:
            release.set()
        assert held.result() == 'synthetic-hash'
    assert auth.verify_password('synthetic', '$argon2-synthetic')
    def fail(password):
        raise ValueError('synthetic failure')
    auth._PASSWORD_HASHER.hash = fail
    with pytest.raises(ValueError):
        auth.hash_password('synthetic')
    assert auth.verify_password('synthetic', '$argon2-synthetic')


@pytest.mark.parametrize('path', ['/login', '/register', '/api/mobile/v1/auth/login', '/ai/ask'])
def test_text_only_auth_and_direct_ai_routes_reject_large_bodies_before_processing(path):
    from app.request_limits import RequestLimits
    app = FastAPI()
    called = []
    async def process():
        called.append(1)
        return {'ok': True}
    app.add_api_route(path, process, methods=['POST'])
    app.add_middleware(RequestLimits)
    assert TestClient(app).post(path, content=b'x' * 65537).status_code == 413
    assert called == []


@pytest.mark.parametrize('kind', ['patient', 'compatibility_patient', 'analysis', 'result', 'consultation'])
def test_native_downloads_release_database_and_reject_other_owner(platform_db, monkeypatch, kind):
    from pathlib import Path
    engine, ids = platform_db
    with Session(engine, expire_on_commit=False) as session:
        analysis = main.Analysis(patient_id=ids.patient, result_path='uploads/synthetic-result.json')
        media = main.PatientMedia(patient_id=ids.patient, owner_user_id=ids.user.id,
            original_filename='synthetic.png', stored_filename='synthetic.png', file_path='uploads/synthetic.png')
        session.add_all([analysis, media]); session.commit()
        asset = main.ImageAsset(analysis_id=analysis.id, original_filename='synthetic.png',
            stored_filename='synthetic.png', file_path='uploads/synthetic.png')
        session.add(asset); session.commit()
        aid, mid, asset_id = analysis.id, media.id, asset.id
        expert = main.User(username='synthetic-expert', role='DOCTOR', display_name='Expert')
        session.add(expert); session.flush()
        case = main.ConsultationCase(requester_user_id=ids.user.id, expert_user_id=expert.id,
            specialty='Endodonti', clinical_summary='Synthetic', question='Synthetic',
            expert_response_deadline=main._utcnow_naive())
        session.add(case); session.flush()
        message = main.ConsultationMessage(case_id=case.id, sender_user_id=ids.user.id,
            content='Synthetic', media_path='uploads/synthetic.png')
        session.add(message); session.commit()
        cid, message_id = case.id, message.id
    local = Path('synthetic.json' if kind == 'result' else 'synthetic.png')
    local.write_bytes(b'{"ai_result":{"status":"synthetic"}}' if kind == 'result' else b'image')
    def ensure(reference):
        assert engine.pool.checkedout() == 0
        return local
    module = mobile_api if kind == 'patient' else mobile_modern_api_v3 if kind == 'compatibility_patient' else mobile_modern_api_v3 if kind == 'consultation' else mobile_analysis_api
    monkeypatch.setattr(module, 'storage_ensure_local', ensure)
    call = (lambda user: module.mobile_patient_media_file(ids.patient, mid, user)) if kind == 'patient' else (
        lambda user: module.mobile_media_file(ids.patient, mid, user)) if kind == 'compatibility_patient' else (
        lambda user: module.mobile_analysis_image(aid, asset_id, user)) if kind == 'analysis' else (
        lambda user: module.mobile_consultation_message_media(cid, message_id, user)) if kind == 'consultation' else (
        lambda user: module.mobile_analysis(aid, user))
    result = call(ids.user)
    if kind == 'result':
        assert result['ai_result']['status'] == 'synthetic'
    else:
        assert result.headers['cache-control'] == 'private, no-store'
    with pytest.raises(main.HTTPException) as error:
        call(ids.outsider)
    assert error.value.status_code == 404


@pytest.mark.parametrize('kind', ['patient', 'compatibility_patient', 'analysis'])
def test_account_disabled_during_storage_cannot_publish_new_upload(platform_db, monkeypatch, kind):
    engine, ids = platform_db
    module, endpoint = {
        'patient': (mobile_api, mobile_api.mobile_patient_media_upload),
        'compatibility_patient': (mobile_modern_api_v3, mobile_modern_api_v3.mobile_upload_media),
        'analysis': (mobile_analysis_api, mobile_analysis_api.create_mobile_analysis),
    }[kind]
    def persist(path, **kwargs):
        with Session(engine) as session:
            user = session.get(main.User, ids.user.id)
            user.is_active = False; session.add(user); session.commit()
    monkeypatch.setattr(module, 'storage_persist_file', persist)
    if kind == 'analysis':
        from pathlib import Path
        monkeypatch.setattr(module, 'classify_dental_image', lambda path: 'OTHER')
        monkeypatch.setattr(module, 'storage_delete', lambda path: Path(path).unlink(missing_ok=True))
    app = FastAPI()
    app.add_api_route('/upload' if kind == 'analysis' else '/upload/{patient_id}', endpoint, methods=['POST'])
    app.dependency_overrides[mobile_api._mobile_user] = lambda: ids.user
    image = BytesIO(); Image.new('RGB', (16, 16), 'white').save(image, format='PNG')
    response = TestClient(app).post('/upload' if kind == 'analysis' else f'/upload/{ids.patient}',
        data={'patient_id': str(ids.patient)} if kind == 'analysis' else {},
        files={'images' if kind == 'analysis' else 'file': ('synthetic.png', image.getvalue(), 'image/png')})
    assert response.status_code == 404
    with Session(engine) as session:
        assert session.exec(select(func.count(main.PatientMedia.id))).one() == 0
        assert session.exec(select(func.count(main.Analysis.id))).one() == 0
