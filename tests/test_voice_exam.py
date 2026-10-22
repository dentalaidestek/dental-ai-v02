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
    main._user_schedule_occurrences = lambda *args: []
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
        revision = voice._fingerprint(session, sys.modules['app.main'], session.get(Patient, 1))
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


def test_official_sources_do_not_use_academic_or_transfer_patient_data(app_client, monkeypatch):
    from app import voice_exam_sources as sources
    def fetched(doc):
        return dict(id=doc[0], institution=doc[1], title=doc[2], url=doc[3], retrieved_at='now', excerpts=['Verified document paragraph'])
    monkeypatch.setattr(sources, '_fetch', fetched)
    client, _ = app_client
    result = client.post('/patients/1/voice-exam/sources', json={'query': 'profilaksi'})
    assert result.status_code == 200
    assert result.json()['references'][0]['institution'] == 'ADA'
    assert result.json()['references'][0]['url'].startswith('https://www.ada.org/')
    assert client.post('/patients/2/voice-exam/sources', json={'query': 'kalp'}).status_code == 404
    assert client.post('/patients/1/voice-exam/sources', json={'course_id': 1, 'query': 'kalp'}).status_code == 422
    assert client.post('/patients/1/voice-exam/sources', json={'query': 'bilinmeyen'}).json()['references'] == []
    assert 'courses' not in client.get('/voice-exams/capabilities').json()


def test_communication_requires_exact_transcript_evidence():
    result = core.normalize({'transcript': 'Anlamadım.', 'communication': [
        {'quote': 'Anlamadım.', 'observation': 'Açıklama ihtiyacı', 'suggestion': 'Daha sade açıkla'},
        {'quote': 'Uydurma', 'observation': 'Eksik', 'suggestion': 'Satış yap'}]})
    assert len(result['communication']) == 1


def test_private_coaching_is_not_an_apply_field(app_client):
    client, engine = app_client
    body = payload(engine)
    body['fields'] = {'communication': 'Özel hayat anlatısı'}
    assert client.post('/patients/1/voice-exam/apply', json=body).status_code == 400


def test_raw_transcript_is_not_an_apply_property(app_client):
    client, engine = app_client
    body = payload(engine)
    body['transcript'] = 'Özel görüşme'
    assert client.post('/patients/1/voice-exam/apply', json=body).status_code == 422


@pytest.mark.parametrize('quote,acceptance,expected', [
    ('Yarın 15:30 gelin.', 'Tamam.', '2026-10-23T15:30'),
    ('24.10.2026 saat 09:00 gelin.', 'Olur.', '2026-10-24T09:00'),
    ('Yarın üçte gelin.', 'Tamam.', None),
    ('Yarın 15:30 gelin.', 'Belki', None),
    ('Yarın 15:30 veya 16:00 gelin.', 'Tamam.', None),
    ('Yarın 15:30 olmaz.', 'Tamam.', None),
    ('23.02.2026 15:30 gelin.', 'Tamam.', None),
    ('Öbür yarın 15:30 gelin.', 'Tamam.', None),
])
def test_calendar_only_resolves_unambiguous_agreed_time(quote, acceptance, expected):
    from zoneinfo import ZoneInfo
    now = datetime(2026, 10, 22, 12, 0, tzinfo=ZoneInfo('Europe/Istanbul'))
    assert core.resolve_appointment(quote, acceptance, now) == expected


def test_context_rejects_transcript_private_coaching_and_oversize():
    for context in ({'transcript': 'özel hayat'}, {'communication': []}, {'fields': {'secret': {}}},
                    {'fields': {'plan': {'value': 'x'*3001, 'quote': 'q'}}}):
        with pytest.raises(core.VoiceError):
            core.clinical_context(context)
    assert core.clinical_context({'fields': {'medications': {'value': 'metformin', 'quote': 'metformin kullanıyorum'}}})['fields']['medications']['value'] == 'metformin'


def test_clinical_output_requires_document_and_patient_anchors():
    from app.voice_exam_clinical import grounded_items
    field = {'medications': {'value': 'warfarin kullanıyorum'}}
    sources = [{'id': 'ada', 'excerpts': ['Dental bleeding risk requires assessment.']}]
    item = dict(source_id='ada', source_quote='bleeding risk', patient_field='medications',
                patient_quote='warfarin', consideration='Değerlendir', missing_information='İşlem', alternative='')
    assert grounded_items({'items': [item]}, field, sources) == [item]
    assert grounded_items({'items': [{**item, 'source_quote': 'fabricated'}]}, field, sources) == []
    assert grounded_items({'items': [{**item, 'patient_quote': 'aspirin'}]}, field, sources) == []
    assert grounded_items({'items': [{**item, 'source_id': 'invented'}]}, field, sources) == []


def test_sources_fail_closed_without_claiming_safety(monkeypatch):
    from app import voice_exam_sources as sources
    def failed(doc):
        raise TimeoutError()
    monkeypatch.setattr(sources, '_fetch', failed)
    result = sources.retrieve('metformin')
    assert not result['references'] and result['unavailable'] == ['ada-diabetes']
    assert result['coverage'] == 'limited'


def test_clinical_route_requires_consent_and_patient_ownership(app_client):
    client, _ = app_client
    body = {'context': {'fields': {}}, 'consent': False}
    assert client.post('/patients/1/voice-exam/clinical', json=body).status_code == 400
    assert client.post('/patients/2/voice-exam/clinical', json={**body, 'consent': True}).status_code == 404


def test_calendar_conflicts_include_recurring_occurrence_and_point_bookings():
    start = datetime(2026, 10, 23, 15, 0)
    occurrence = {'status': 'ACTIVE', 'start_local': start, 'end_local': datetime(2026, 10, 23, 16, 0)}
    assert voice.appointment_conflict([occurrence], datetime(2026, 10, 23, 15, 30))
    assert voice.appointment_conflict([occurrence], datetime(2026, 10, 23, 14, 30), datetime(2026, 10, 23, 15, 30))
    assert not voice.appointment_conflict([occurrence], datetime(2026, 10, 23, 16, 0))
    assert not voice.appointment_conflict([{**occurrence, 'status': 'COMPLETED'}], start)


def test_decision_barriers_require_short_direct_evidence():
    item = {'category': 'FEAR', 'quote': 'İğneden korkuyorum.', 'observation': 'Korku dile getirildi',
            'question': 'En çok hangi aşama kaygılandırıyor?', 'explanation': 'Aşamaları anlat'}
    result = core.normalize({'transcript': 'İğneden korkuyorum.', 'decision_barriers': [item, {**item, 'quote': 'Gelirim yok.'}]})
    assert result['decision_barriers'] == [item]


def test_next_segment_context_reaches_provider_but_private_text_is_rejected(app_client, monkeypatch):
    client, _ = app_client
    seen = []
    def extract(**kwargs):
        seen.append(kwargs)
        return {'transcript': 'Metformin kullanıyorum.', 'fields': {}, 'teeth': []}
    monkeypatch.setattr(core, 'extract', extract)
    context = {'fields': {'medical_history': {'value': 'Diyabet beyanı', 'quote': 'Şekerim var.'}}}
    result = client.post('/patients/1/voice-exam/text', json={'transcript': 'Metformin kullanıyorum.', 'consent': True, 'context': context})
    assert result.status_code == 200 and seen[0]['context']['fields'] == context['fields']
    result = client.post('/patients/1/voice-exam/text', json={'transcript': 'Örnek', 'consent': True, 'context': {'transcript': 'Özel hayat'}})
    assert result.status_code == 422 and len(seen) == 1


def test_clinical_provider_receives_only_clinical_fields_and_fixed_sources(monkeypatch):
    from app import voice_exam_clinical as clinical
    import app.http_transport as transport
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
    monkeypatch.setenv('VOICE_EXAM_GEMINI_MODEL', 'gemini-test')
    budget = ModuleType('app.provider_budget');budget.reservation = lambda *a: nullcontext()
    monkeypatch.setitem(sys.modules, 'app.provider_budget', budget)
    source = dict(id='ada', institution='ADA', title='Example', url='https://www.ada.org/', excerpts=['Dental bleeding risk assessment.'])
    monkeypatch.setattr(clinical, 'retrieve', lambda query: {'references': [source], 'unavailable': [], 'notice': 'limited'})
    requests = []
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,limit):return json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'items':[]})}]}}]}).encode()
    def urlopen(request, **kwargs):
        requests.append(json.loads(request.data));return Response()
    monkeypatch.setattr(transport, 'urlopen', urlopen)
    result = clinical.assess({'fields': {'first_name': {'value': 'SYNTHETIC_PRIVATE_NAME', 'quote': 'SYNTHETIC_PRIVATE_NAME'},
        'medications': {'value': 'warfarin', 'quote': 'warfarin'}}})
    assert result['items'] == [] and len(requests) == 1
    assert 'SYNTHETIC_PRIVATE_NAME' not in json.dumps(requests)
    assert 'warfarin' in json.dumps(requests)


def test_live_socket_denies_cross_owner_and_cross_origin(app_client, monkeypatch):
    from starlette.websockets import WebSocketDisconnect
    client, _ = app_client
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
    for patient, origin in ((2, 'http://testserver'), (1, 'https://evil.example')):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/patients/'+str(patient)+'/voice-exam/live', headers={'Origin': origin}):
                pass


def test_live_socket_requires_consent_before_provider_connection(app_client, monkeypatch):
    from starlette.websockets import WebSocketDisconnect
    client, _ = app_client
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
    with client.websocket_connect('/patients/1/voice-exam/live', headers={'Origin': 'http://testserver'}) as socket:
        socket.send_json({'type': 'start', 'consent': False})
        with pytest.raises(WebSocketDisconnect):socket.receive_json()


def test_live_proxy_end_to_end_keeps_key_server_side(app_client, monkeypatch):
    from test_voice_exam_live import Provider
    client, _ = app_client
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-server-secret')
    budget = ModuleType('app.provider_budget');budget.reservation = lambda *args: nullcontext()
    monkeypatch.setitem(sys.modules, 'app.provider_budget', budget)
    connections = []
    class Connection:
        async def __aenter__(self):return Provider()
        async def __aexit__(self, *args):pass
    def connect(url, **kwargs):
        connections.append((url, kwargs));return Connection()
    module = ModuleType('websockets.asyncio.client');module.connect = connect
    monkeypatch.setitem(sys.modules, 'websockets.asyncio.client', module)
    with client.websocket_connect('/patients/1/voice-exam/live', headers={'Origin':'http://testserver'}) as socket:
        socket.send_json({'type':'start','consent':True})
        assert socket.receive_json() == {'type':'ready'}
        socket.send_bytes(b'\x00\x00'*1600)
        assert socket.receive_json()['type'] == 'interim'
        socket.send_json({'type':'finish'})
        assert socket.receive_json() == {'type':'final','text':'Soğuk içemiyorum.'}
        assert socket.receive_json() == {'type':'ended','flushed':True}
    assert len(connections) == 1
    url, options = connections[0]
    assert 'key=' not in url and 'synthetic-server-secret' not in url
    assert options['additional_headers']['x-goog-api-key'] == 'synthetic-server-secret'


def test_voice_entry_lists_only_owned_patients_and_escapes_search(app_client, monkeypatch):
    from fastapi.responses import JSONResponse
    from app import main
    client, engine = app_client
    def template(**kwargs):
        context = kwargs['context']
        return JSONResponse({'patients':[row.id for row in context['patients']]})
    monkeypatch.setattr(main, 'templates', SimpleNamespace(TemplateResponse=template), raising=False)
    with Session(engine) as session:
        patient=session.get(Patient,1);patient.first_name='SyntheticName';session.add(patient);session.commit()
    result=client.get('/voice-exams')
    assert result.json()['patients'] == [1]
    assert result.headers['cache-control'] == 'private, no-store'
    assert client.get('/voice-exams',params={'q':'SyntheticName'}).json()['patients'] == [1]
    assert client.get('/voice-exams',params={'q':'%'}).json()['patients'] == []

