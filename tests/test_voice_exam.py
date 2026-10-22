import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace, ModuleType
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Field, Session, create_engine, select

from app import voice_exam_core as core
from app import voice_exam as voice
from app.work_jobs import WorkJob


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    role: str = 'DOCTOR'
    is_active: bool = True


class Patient(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int
    anonymous_id: str = 'ANON'
    first_name: str | None = None
    last_name: str | None = None
    age: int | None = None
    birth_date: str | None = None
    chief_complaint: str | None = None


class Analysis(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int
    status: str = 'DRAFT'
    clinical_notes: str = ''


class ToothStatus(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int
    tooth_number: str
    status: str
    note: str | None = None
    updated_at: datetime = Field(default_factory=datetime.now)


class ScheduleEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int
    patient_id: int
    title: str
    start_at: str


class StudyCourse(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int
    title: str


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv('VOICE_EXAM_ENABLED', '1')
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine)
    main = ModuleType('app.main');main.engine = engine
    for model in (User, Patient, Analysis, ToothStatus, ScheduleEvent, StudyCourse):setattr(main, model.__name__, model)
    main.get_current_user = lambda request: (SimpleNamespace(id=1, role=request.headers.get('x-role', 'DOCTOR'), is_active=True)
        if request.headers.get('x-login', '1') == '1' else None)
    main._record_patient_realtime_events = lambda *a: []
    main._record_program_realtime_event = lambda *a: 'event'
    main._sync_program_reminder = lambda *a: None
    main._wake_program_reminder_worker = lambda: None
    main._publish_realtime_event = lambda *a: None
    main.on_loop = lambda *a: None
    def schedule(session, user, kind, title, start, end, patient, *args):
        if not start or start == 'invalid':return None, 'Tarih geçersiz'
        return {'title': title, 'start_at': start, 'patient_id': int(patient)}, None
    main._validate_schedule_input = schedule
    main._owned_study_course = lambda session, user, ident: session.exec(select(StudyCourse).where(
        StudyCourse.id == ident, StudyCourse.owner_user_id == user.id)).first()
    monkeypatch.setitem(sys.modules, 'app.main', main)
    import app
    monkeypatch.setattr(app, 'main', main, raising=False)
    with Session(engine) as session:
        session.add_all([User(id=1), User(id=2), Patient(id=1, owner_user_id=1, first_name='Mevcut', age=40,
            chief_complaint='Eski şikâyet'), Patient(id=2, owner_user_id=2),
            StudyCourse(id=1, owner_user_id=1, title='Notlarım'), StudyCourse(id=2, owner_user_id=2, title='Yabancı ders')])
        session.commit()
    application = FastAPI();application.include_router(voice.router);application.add_middleware(voice.VoiceBodyLimitMiddleware)
    with TestClient(application) as client:
        yield client, engine
    engine.dispose()


def payload(engine, **updates):
    with Session(engine) as session:
        revision = core.revision(session.get(Patient, 1))
    return {'request_key': 'a' * 32, 'revision': revision, 'confirmed': True,
            'fields': {'clinical_findings': 'Hekim gözlemi'}, **updates}


def test_review_changes_only_selected_fields_and_is_idempotent(app_client):
    client, engine = app_client
    data = payload(engine, fields={'chief_complaint': 'Soğukla ağrı', 'allergies': 'Hasta penisilin alerjisi olduğunu söylüyor'})
    first = client.post('/patients/1/voice-exam/apply', json=data)
    assert first.status_code == 200
    second = client.post('/patients/1/voice-exam/apply', json=data)
    assert second.json()['already_saved']
    with Session(engine) as session:
        patient = session.get(Patient, 1)
        assert patient.first_name == 'Mevcut' and patient.age == 40
        assert patient.chief_complaint == 'Soğukla ağrı'
        notes = session.exec(select(Analysis)).all()
        assert len(notes) == 1 and 'hasta beyanı' in notes[0].clinical_notes
        assert len(session.exec(select(WorkJob)).all()) == 1
        assert session.exec(select(WorkJob)).one().payload_json == '{}'


@pytest.mark.parametrize('path', ['audio', 'text', 'apply'])
def test_foreign_patient_rejected_before_provider(app_client, monkeypatch, path):
    client, engine = app_client
    monkeypatch.setattr(core, 'extract', lambda **kw: pytest.fail('Provider must not be called'))
    if path == 'audio':
        result = client.post('/patients/2/voice-exam/audio', content=b'\x1aE\xdf\xa3' + b'x' * 100,
            headers={'Content-Type': 'audio/webm', 'X-Voice-Consent': 'yes'})
    else:
        result = client.post('/patients/2/voice-exam/' + path,
            json=payload(engine) if path == 'apply' else {'transcript': 'örnek', 'consent': True})
    assert result.status_code == 404


@pytest.mark.parametrize('headers', [{'x-login': '0'}, {'x-role': 'CITIZEN'}, {'origin': 'https://foreign.example'}, {'sec-fetch-site': 'cross-site'}])
def test_session_role_and_cross_site_protection(app_client, headers):
    client, engine = app_client
    assert client.post('/patients/1/voice-exam/apply', json=payload(engine), headers=headers).status_code == 401


def test_unconfirmed_and_stale_review_do_not_mutate(app_client):
    client, engine = app_client
    data = payload(engine, confirmed=False)
    assert client.post('/patients/1/voice-exam/apply', json=data).status_code == 400
    data = payload(engine)
    with Session(engine) as session:
        patient = session.get(Patient, 1);patient.age = 41;session.add(patient);session.commit()
    assert client.post('/patients/1/voice-exam/apply', json=data).status_code == 409
    with Session(engine) as session:assert not session.exec(select(Analysis)).all()


def test_schedule_and_chart_only_when_explicitly_selected(app_client):
    client, engine = app_client
    data = payload(engine, teeth=[{'tooth': '44', 'status': 'CARIES', 'note': 'Hekimin onayı'}],
        appointment={'title': 'Kontrol', 'start_at': '2026-11-20T10:00'})
    assert client.post('/patients/1/voice-exam/apply', json=data).status_code == 200
    with Session(engine) as session:
        assert session.exec(select(ToothStatus)).one().tooth_number == '44'
        assert session.exec(select(ScheduleEvent)).one().patient_id == 1


def test_validation_rolls_back_appointment_when_age_conflicts(app_client):
    client, engine = app_client
    with Session(engine) as session:
        patient = session.get(Patient, 1);patient.birth_date = '1986-01-01';session.add(patient);session.commit()
    data = payload(engine, fields={'age': '30'}, appointment={'title': 'Kontrol', 'start_at': '2026-11-20T10:00'})
    assert client.post('/patients/1/voice-exam/apply', json=data).status_code == 409
    with Session(engine) as session:
        assert not session.exec(select(ScheduleEvent)).all()
        assert session.get(Patient, 1).age == 40


def test_invalid_or_duplicate_teeth_cannot_apply(app_client):
    client, engine = app_client
    for teeth in ([{'tooth': '99', 'status': 'CARIES'}], [{'tooth': '44', 'status': 'HEALTHY'}],
                  [{'tooth': '44', 'status': 'CARIES'}, {'tooth': '44', 'status': 'FILLING'}]):
        assert client.post('/patients/1/voice-exam/apply', json=payload(engine, teeth=teeth)).status_code in (400, 422)


def test_audio_limit_and_consent_before_external_processing(app_client, monkeypatch):
    client, _ = app_client
    monkeypatch.setattr(core, 'extract', lambda **kw: pytest.fail('No external request expected'))
    assert client.post('/patients/1/voice-exam/audio', content=b'x' * 200, headers={'Content-Type': 'audio/webm'}).status_code == 400
    assert client.post('/patients/1/voice-exam/audio', content=b'x' * 200,
        headers={'Content-Type': 'audio/webm', 'X-Voice-Consent': 'yes'}).status_code == 422
    assert client.post('/patients/1/voice-exam/audio', content=b'',
        headers={'Content-Length': str(core.MAX_AUDIO + 100000)}).status_code == 413


def test_audio_extract_returns_review_without_writing_clinical_records(app_client, monkeypatch):
    client, engine = app_client
    from sqlalchemy import event
    connections = [0]
    event.listen(engine, 'checkout', lambda *a: connections.__setitem__(0, connections[0] + 1))
    event.listen(engine, 'checkin', lambda *a: connections.__setitem__(0, connections[0] - 1))
    def extract(**kwargs):
        assert connections[0] == 0
        assert kwargs['mime'] == 'audio/webm'
        assert set(kwargs) == {'data', 'mime'}
        return {'transcript': 'Ağrım var.', 'fields': {}, 'teeth': [], 'uncertain': '', 'appointment': None}
    monkeypatch.setattr(core, 'extract', extract)
    result = client.post('/patients/1/voice-exam/audio', content=b'\x1aE\xdf\xa3' + b'x' * 100,
        headers={'Content-Type': 'audio/webm;codecs=opus', 'X-Voice-Consent': 'yes'})
    assert result.status_code == 200 and result.json()['review']['transcript'] == 'Ağrım var.'
    with Session(engine) as session:
        assert not session.exec(select(Analysis)).all()
        assert session.get(Patient, 1).chief_complaint == 'Eski şikâyet'


def test_normalize_preserves_negation_and_drops_unsupported_claims():
    data = core.normalize({'transcript': 'Alerjim yok. Yaşım kırk.', 'fields': {
        'allergies': {'value': 'Hasta alerjisi olmadığını söylüyor', 'quote': 'Alerjim yok.'},
        'medications': {'value': 'Warfarin', 'quote': 'Söylenmeyen cümle'},
        'age': {'value': '140', 'quote': 'Yaşım kırk.'}}, 'teeth': []})
    assert set(data['fields']) == {'allergies'}
    assert data['fields']['allergies']['quote'] == 'Alerjim yok.'


def test_gemini_only_transport_and_truncation(monkeypatch):
    import app.http_transport as transport
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
    monkeypatch.setenv('VOICE_EXAM_GEMINI_MODEL', 'gemini-test')
    budget = ModuleType('app.provider_budget');budget.reservation = lambda *a: nullcontext()
    monkeypatch.setitem(sys.modules, 'app.provider_budget', budget)
    requests = []
    class Response:
        finish = 'STOP'
        def __enter__(self):return self
        def __exit__(self, *args):pass
        def read(self, limit):
            return json.dumps({'candidates': [{'finishReason': self.finish, 'content': {'parts': [
                {'text': json.dumps({'transcript': 'Soğukta ağrıyor.', 'fields': {}, 'teeth': []})}]}}]}).encode()
    def open_request(request, **kw):requests.append(request);return Response()
    monkeypatch.setattr(transport, 'urlopen', open_request)
    assert core.extract(transcript='Soğukta ağrıyor.')['transcript']
    assert len(requests) == 1 and requests[0].full_url.startswith('https://generativelanguage.googleapis.com/')
    assert 'synthetic-key' not in requests[0].full_url
    assert 'responseSchema' in json.loads(requests[0].data)['generationConfig']
    Response.finish = 'MAX_TOKENS'
    with pytest.raises(core.VoiceError, match='tamamlanmadı'):core.extract(transcript='Örnek')


def test_disabled_feature_and_anonymous_entry(app_client, monkeypatch):
    client, engine = app_client
    result = client.post('/voice-exams/anonymous', follow_redirects=False)
    assert result.status_code == 303
    with Session(engine) as session:
        patients = session.exec(select(Patient).where(Patient.owner_user_id == 1)).all()
        assert len(patients) == 2 and patients[-1].first_name is None
    monkeypatch.setenv('VOICE_EXAM_ENABLED', '0')
    assert client.post('/patients/1/voice-exam/apply', json=payload(engine)).status_code == 503


def test_sources_reuse_owned_published_retriever_without_generation(app_client, monkeypatch):
    client, _ = app_client
    module = ModuleType('app.study_retrieval_v2');calls = []
    def retrieve(session, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(evidence=[SimpleNamespace(display_name='Not.pdf', page_start=3, page_end=3, text='Kaynak alıntısı')])
    module.retrieve_course_context_v2 = retrieve
    monkeypatch.setitem(sys.modules, 'app.study_retrieval_v2', module)
    result = client.post('/patients/1/voice-exam/sources', json={'course_id': 1, 'query': 'Alerji'})
    assert result.status_code == 200 and result.json()['references'][0]['page_start'] == 3
    assert calls[0]['owner_user_id'] == 1 and calls[0]['recent_history'] == []
    assert client.post('/patients/1/voice-exam/sources', json={'course_id': 2, 'query': 'Alerji'}).status_code == 404
    assert client.post('/patients/2/voice-exam/sources', json={'course_id': 1, 'query': 'Alerji'}).status_code == 404
    assert len(calls) == 1
    assert client.get('/voice-exams/capabilities').json()['courses'] == [{'id': 1, 'title': 'Notlarım'}]
