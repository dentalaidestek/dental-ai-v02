"""Concurrency and provider-boundary regressions; no external credentials."""
import asyncio
import io
import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from app.execution import CapacityExceeded, LoopWakeup, WorkGate, offload, on_loop
from app.http_transport import urlopen


def test_blocked_handler_does_not_block_event_loop_and_callbacks_return_to_loop():
    entered, release = threading.Event(), threading.Event()
    app = FastAPI()
    threads = {}

    @app.post('/slow')
    @offload
    def slow(request: Request):
        threads['worker'] = threading.get_ident()
        entered.set()
        assert release.wait(3)
        return on_loop(request.json)

    @app.get('/fast')
    async def fast():
        threads['loop'] = threading.get_ident()
        return {'ok': True}

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            task = asyncio.create_task(client.post('/slow', json={'body': 'preserved'}))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                response = await asyncio.wait_for(client.get('/fast'), 1)
                assert response.json() == {'ok': True}
            finally:
                release.set()
            assert (await task).json() == {'body': 'preserved'}
    asyncio.run(exercise())
    assert threads['worker'] != threads['loop']


def test_gate_releases_capacity_after_exception():
    gate = WorkGate(1)
    with pytest.raises(ValueError):
        with gate.enter():
            with pytest.raises(CapacityExceeded):
                with gate.enter():
                    pytest.fail('overflow admitted')
            raise ValueError('work failed')
    with gate.enter():
        pass


def test_wakeup_survives_lifespan_restart_and_cross_thread_signal():
    wakeup = LoopWakeup()
    async def exercise():
        wakeup.bind()
        await asyncio.to_thread(wakeup.set)
        await asyncio.wait_for(wakeup.wait(), 1)
        wakeup.clear()
        assert not wakeup.event.is_set()
    asyncio.run(exercise())
    asyncio.run(exercise())


def test_transport_reuses_connections_and_preserves_http_error():
    ports = []
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def do_GET(self):
            ports.append(self.client_address[1])
            body = b'line1\nline2\n'
            self.send_response(429 if self.path == '/error' else 200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        for _ in range(2):
            with urlopen(url) as response:
                assert response.read() == b'line1\nline2\n'
        assert ports[0] == ports[1]
        with pytest.raises(urllib.error.HTTPError) as error:
            urlopen(url + '/error')
        assert error.value.code == 429
        assert error.value.read() == b'line1\nline2\n'
        with urlopen(url) as response:
            assert list(response) == [b'line1\n', b'line2\n']
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


def test_vision_busy_response_and_upload_cleanup(monkeypatch):
    from pathlib import Path
    from vision_service import app as vision
    entered, release = threading.Event(), threading.Event()
    paths = []
    monkeypatch.setattr(vision, 'VISION_API_KEY', 'synthetic-test-key')
    def inference(path):
        paths.append(path)
        assert Path(path).read_bytes() == b'synthetic-image'
        entered.set()
        assert release.wait(3)
        return {'ok': True}
    monkeypatch.setattr(vision, 'analyze_panorama', inference)
    with TestClient(vision.app) as client, ThreadPoolExecutor(1) as pool:
        def request():
            return client.post('/analyze', headers={'X-Vision-Key': 'synthetic-test-key'}, files={'image': ('x.png', b'synthetic-image')})
        first = pool.submit(request)
        try:
            assert entered.wait(2)
            second = request()
            assert second.status_code == 503
            assert second.headers['retry-after'] == '2'
        finally:
            release.set()
        assert first.result().status_code == 200
    assert paths and all(not Path(path).exists() for path in paths)


def test_vision_oversize_rejected_and_temp_files_removed(monkeypatch):
    from pathlib import Path
    from fastapi import HTTPException
    from vision_service import app as vision
    monkeypatch.setattr(vision, '_MAX_IMAGE_BYTES', 3)
    with pytest.raises(HTTPException) as error:
        with vision._saved_image(UploadFile(io.BytesIO(b'abcd'), filename='x.png'), 'x.png'):
            pytest.fail('oversized upload accepted')
    assert error.value.status_code == 413
    with pytest.raises(RuntimeError):
        with vision._saved_image(UploadFile(io.BytesIO(b'abc'), filename='x.png'), 'x.png') as path:
            raise RuntimeError('inference failed')
    assert not Path(path).exists()


def test_vision_failure_is_retryable_and_success_cache_cannot_be_mutated(tmp_path, monkeypatch):
    from app import vision_llm_context as vision
    image = tmp_path / 'test.png'
    image.write_bytes(b'synthetic')
    calls = []
    def infer(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('temporary unavailability')
        return {'ok': True, 'findings': [], 'teeth': []}
    vision._CACHE.clear()
    monkeypatch.setattr(vision, '_modal_panorama_result', infer)
    first = vision.structured_vision_payload([str(image)], 'PANORAMIC')
    assert first['status'] != 'ok'
    second = vision.structured_vision_payload([str(image)], 'PANORAMIC')
    assert second['status'] == 'ok'
    second['images'].clear()
    third = vision.structured_vision_payload([str(image)], 'PANORAMIC')
    assert third['images'] and len(calls) == 2
    vision._CACHE.clear()


def test_rag_cache_keeps_rank_ties_and_avoids_warm_disk_reads(monkeypatch):
    from dental_rag import rag
    rag._search_chunks.cache_clear()
    documents = [dict(source=name, category='general', text='dentin enamel') for name in ('b', 'a')]
    monkeypatch.setattr(rag, 'load_documents', lambda: documents)
    try:
        assert [r['source'] for r in rag.search('dentin')] == ['b', 'a']
        monkeypatch.setattr(rag, 'load_documents', lambda: pytest.fail('warm search reread files'))
        assert [r['source'] for r in rag.search('enamel')] == ['b', 'a']
    finally:
        rag._search_chunks.cache_clear()


def test_v2_configuration_prevents_accidental_double_indexing(monkeypatch):
    from app.study_v2_service import legacy_indexing_required, validate_configuration
    monkeypatch.setenv('STUDY_ACADEMIC_V2_READS', '1')
    monkeypatch.setenv('STUDY_ACADEMIC_V2_INDEXING', '0')
    with pytest.raises(RuntimeError):
        validate_configuration()
    monkeypatch.setenv('STUDY_ACADEMIC_V2_INDEXING', '1')
    monkeypatch.delenv('STUDY_V1_SHADOW_INDEXING', raising=False)
    validate_configuration()
    assert not legacy_indexing_required()
    monkeypatch.setenv('STUDY_V1_SHADOW_INDEXING', '1')
    assert legacy_indexing_required()


@pytest.mark.parametrize('delete_during_generation', [False, True])
def test_study_generation_releases_db_connection_and_rechecks_course(tmp_path, monkeypatch, delete_during_generation):
    from types import SimpleNamespace
    from fastapi import BackgroundTasks
    from sqlmodel import Session, SQLModel, create_engine, select
    from app import main
    engine = create_engine(f'sqlite:///{tmp_path / "generation.db"}')
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(main, 'get_current_user', lambda request: SimpleNamespace(id=1, role="DOCTOR"))
    monkeypatch.setattr(main, 'classify_course_scope', lambda *args: 'DENTAL')
    monkeypatch.setattr(main, 'study_v2_reads_enabled', lambda: False)
    monkeypatch.setattr(main, 'course_index_ready', lambda *args, **kwargs: True)
    with Session(engine) as session:
        session.add(main.User(id=1, username='synthetic', role='DOCTOR', display_name='Synthetic'))
        session.add(main.StudyCourse(id=1, owner_user_id=1, title='Ortodonti'))
        session.add(main.StudyMaterial(id=1, owner_user_id=1, course_id=1,
            original_filename='note.pdf', display_name='Note', stored_filename='note.pdf',
            file_path='synthetic.pdf', material_type='PDF', mime_type='application/pdf', size_bytes=1))
        session.commit()
    def retrieval(*args, **kwargs):
        assert engine.pool.checkedout() == 0
        return SimpleNamespace(note_context=['source'], memory_context=[], attachments=[],
                               source_material_ids=[1], used_semantic_search=False)
    monkeypatch.setattr(main, 'retrieve_course_context', retrieval)
    def generate(*args):
        assert engine.pool.checkedout() == 0
        if delete_during_generation:
            with Session(engine) as session:
                session.delete(session.get(main.StudyCourse, 1))
                session.commit()
        return 'Synthetic answer'
    monkeypatch.setattr(main, 'ask_study_ai', generate)
    try:
        response = main.study_ai_ask(None, 1, BackgroundTasks(), message='Angle sınıf II?')
        assert response.status_code == (409 if delete_during_generation else 200)
        with Session(engine) as session:
            messages = session.exec(select(main.StudyChatMessage)).all()
            assert len(messages) == (0 if delete_during_generation else 2)
            if delete_during_generation:
                assert session.get(main.StudyCourse, 1) is None
    finally:
        engine.dispose()


def test_patient_media_upload_releases_db_during_storage(tmp_path, monkeypatch):
    from sqlmodel import Session, SQLModel, create_engine, select
    from starlette.datastructures import UploadFile
    from app import main

    engine = create_engine(f'sqlite:///{tmp_path / "patient-media.db"}')
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username='media-owner', role='DOCTOR', display_name='Media Owner')
        session.add(user); session.commit()
        patient = main.Patient(anonymous_id='media-patient', owner_user_id=user.id)
        session.add(patient); session.commit()
        user_id, patient_id = user.id, patient.id
    monkeypatch.setattr(main, 'get_current_user', lambda request: user)

    def persist(path, **kwargs):
        assert engine.pool.checkedout() == 0
        assert path.read_bytes().startswith(b'\xff\xd8\xff')
        return str(path)

    monkeypatch.setattr(main, 'storage_persist_file', persist)
    try:
        response = asyncio.run(main.upload_patient_media(
            None,
            patient_id,
            media_type='PHOTO',
            tooth_number=None,
            note=None,
            files=[UploadFile(file=io.BytesIO(b'\xff\xd8\xffsynthetic'), filename='photo.jpg')],
        ))
        assert response.status_code == 303
        with Session(engine) as session:
            rows = session.exec(select(main.PatientMedia).where(
                main.PatientMedia.patient_id == patient_id,
                main.PatientMedia.owner_user_id == user_id,
            )).all()
            assert len(rows) == 1
    finally:
        engine.dispose()


def test_consultation_media_upload_releases_db_during_storage(tmp_path, monkeypatch):
    from sqlmodel import Session, SQLModel, create_engine, select
    from starlette.datastructures import UploadFile
    from app import main

    engine = create_engine(f'sqlite:///{tmp_path / "consultation-media.db"}')
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    monkeypatch.setattr(main, 'on_loop', lambda *args, **kwargs: None)
    with Session(engine, expire_on_commit=False) as session:
        requester = main.User(username='requester', role='DOCTOR', display_name='Requester')
        expert = main.User(username='expert', role='DOCTOR', display_name='Expert')
        session.add(requester); session.add(expert); session.commit()
        case = main.ConsultationCase(
            requester_user_id=requester.id,
            expert_user_id=expert.id,
            specialty='Endodonti',
            clinical_summary='Synthetic',
            question='Synthetic',
            status='ACTIVE',
            expert_response_deadline=main._utcnow_naive() + main.timedelta(hours=1),
        )
        session.add(case); session.commit()
        case_id = case.id
    monkeypatch.setattr(main, 'get_current_user', lambda request: requester)

    def write(path, content, **kwargs):
        assert engine.pool.checkedout() == 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    monkeypatch.setattr(main, 'storage_write_bytes', write)
    try:
        response = asyncio.run(main.expert_support_media_message(
            type('Request', (), {'headers': {'x-requested-with': 'fetch'}})(),
            case_id,
            UploadFile(
                file=io.BytesIO(b'\xff\xd8\xffsynthetic'),
                filename='scan.jpg',
                headers={'content-type': 'image/jpeg'},
            ),
            reply_to_message_id=None,
            client_message_id='',
        ))
        assert response.status_code == 200
        with Session(engine) as session:
            rows = session.exec(select(main.ConsultationMessage).where(
                main.ConsultationMessage.case_id == case_id,
            )).all()
            assert len(rows) == 1 and rows[0].message_type == 'IMAGE'
    finally:
        engine.dispose()


def test_mixed_worker_services_ocr_under_continuous_normal_backlog(monkeypatch):
    from types import SimpleNamespace
    from sqlmodel import create_engine
    from app import study_index_worker_main as worker
    engine = create_engine('sqlite://')
    from app import migrate
    monkeypatch.setattr(migrate, 'require_schema', lambda engine: None)
    monkeypatch.setattr(worker, '_stop', False)
    monkeypatch.setattr(worker, 'build_worker_engine', lambda: engine)
    monkeypatch.setattr(worker.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(worker, 'require_worker_capabilities', lambda session: SimpleNamespace(fts=True, embedding_array=True, pgvector=False))
    monkeypatch.setattr(worker, 'run_deletion_slice', lambda session: None)
    monkeypatch.setattr(worker, 'enqueue_legacy_material_rows_v2', lambda session, limit: 0)
    monkeypatch.setenv('STUDY_V2_RESOURCE_CLASS', 'MIXED')
    classes = []
    def run_slice(session, resource_class):
        classes.append(resource_class)
        if len(classes) == 4:
            worker._stop = True
        return 'DONE'
    monkeypatch.setattr(worker, 'run_one_slice', run_slice)
    worker.main()
    assert classes == ['NORMAL', 'OCR_HEAVY', 'NORMAL', 'OCR_HEAVY']


def test_academic_legacy_backfill_does_not_require_web_model_graph(monkeypatch):
    from app import study_v2_service as service

    class Result:
        def mappings(self):
            return self

        def all(self):
            return [{
                'id': 7,
                'owner_user_id': 11,
                'course_id': 13,
                'mime_type': 'application/pdf',
                'deleted_at': None,
            }]

    class Session:
        def __init__(self):
            self.calls = []

        def execute(self, statement, params):
            self.calls.append((str(statement), params))
            return Result()

    monkeypatch.setenv('STUDY_ACADEMIC_V2_INDEXING', '1')
    seen = []
    monkeypatch.setattr(service, 'enqueue_material_v2', lambda session, material: seen.append(material) or 'v2')
    session = Session()
    assert service.enqueue_legacy_material_rows_v2(session, limit=10) == 1
    assert session.calls[0][1] == {'limit': 10}
    assert 'FROM studymaterial' in session.calls[0][0]
    assert [(row.id, row.owner_user_id, row.course_id, row.mime_type) for row in seen] == [
        (7, 11, 13, 'application/pdf')
    ]


def test_postgres_notice_channels_do_not_wake_unrelated_workers():
    from app import main

    reconnect, channels = main._postgres_notice_state([
        (main.PG_REALTIME_CHANNEL, '10'),
        (main.PG_REALTIME_CHANNEL, '11'),
    ])
    assert not reconnect
    assert channels == {main.PG_REALTIME_CHANNEL}

    reconnect, channels = main._postgres_notice_state([None])
    assert reconnect
    assert channels == set()
