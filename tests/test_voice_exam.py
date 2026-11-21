import hashlib
import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace, ModuleType
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import registry
from sqlmodel import SQLModel, Field, Session, create_engine, select

from app import voice_exam_core as core
from app import voice_exam as voice
from app.approved_anamnesis import ApprovedAnamnesis
from app.work_jobs import WorkJob as ProductionWorkJob


# Keep lightweight route fixtures out of the production model graph. Full-site
# collection may already have registered tables with these names.
voice_registry = registry()


class VoiceTestModel(SQLModel, registry=voice_registry):
    pass


class WorkJob:
    pass


voice_registry.map_imperatively(WorkJob,
    ProductionWorkJob.__table__.to_metadata(VoiceTestModel.metadata))


class User(VoiceTestModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    role: str = 'DOCTOR'
    is_active: bool = True
    email: str | None = None
    email_verified_at: datetime | None = Field(default_factory=datetime.utcnow)


class SessionToken(VoiceTestModel, table=True):
    token_hash: str = Field(primary_key=True)
    user_id: int
    expires_at: datetime


class AdminVerifiedSession(VoiceTestModel, table=True):
    token_hash: str = Field(primary_key=True)
    user_id: int


class Patient(VoiceTestModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int
    anonymous_id: str = 'ANON'
    first_name: str | None = None
    last_name: str | None = None
    age: int | None = None
    birth_date: str | None = None
    chief_complaint: str | None = None


class Analysis(VoiceTestModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int
    status: str = 'DRAFT'
    clinical_notes: str = ''


class ToothStatus(VoiceTestModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int
    tooth_number: str
    status: str
    note: str | None = None
    updated_at: datetime = Field(default_factory=datetime.now)


class ScheduleEvent(VoiceTestModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int
    patient_id: int
    title: str
    start_at: str


class StudyCourse(VoiceTestModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int
    title: str


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv('VOICE_EXAM_ENABLED', '1')
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    ApprovedAnamnesis.__table__.to_metadata(VoiceTestModel.metadata)
    VoiceTestModel.metadata.create_all(engine)
    monkeypatch.setattr("app.work_jobs.WorkJob", WorkJob)
    main = ModuleType('app.main');main.engine = engine
    main._user_schedule_occurrences = lambda *args: []
    for model in (User, SessionToken, AdminVerifiedSession, Patient, Analysis, ToothStatus, ScheduleEvent, StudyCourse):setattr(main, model.__name__, model)
    main.hash_session_token = lambda token: hashlib.sha256(token.encode('utf-8')).hexdigest()
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


def _bearer_headers(engine, token='native-voice-token', user_id=1, expires_at=None):
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    with Session(engine) as session:
        session.add(SessionToken(token_hash=token_hash, user_id=user_id,
            expires_at=expires_at or datetime.utcnow() + timedelta(days=1)))
        session.commit()
    # The x-login=0 test switch proves that the request succeeds without a web cookie.
    return {'authorization': f'Bearer {token}', 'x-login': '0'}, token_hash


def test_native_bearer_session_can_apply_and_read_only_its_own_approved_anamnesis(app_client):
    client, engine = app_client
    headers, _ = _bearer_headers(engine)
    saved = client.post('/patients/1/voice-exam/apply', headers=headers,
        json=payload(engine, fields={'medical_history': 'Astım beyanı',
                                     'medications': 'Metformin kullandığını belirtti',
                                     'allergies': 'Penisilin alerjisi olmadığını belirtti'}))
    assert saved.status_code == 200
    history = client.get('/patients/1/voice-exam/history', headers=headers)
    assert history.status_code == 200
    assert 'no-store' in history.headers.get('cache-control', '').lower()
    assert set(history.json()['fields']) == {'medical_history', 'medications', 'allergies'}
    assert history.json()['fields']['medical_history']['quote'] == ''
    assert client.get('/patients/2/voice-exam/history', headers=headers).status_code == 404


def test_bearer_voice_identity_never_falls_back_to_a_different_cookie_user(app_client):
    client, engine = app_client
    with Session(engine) as session:
        session.add(User(id=3, role='PATIENT', email_verified_at=datetime.utcnow()))
        session.commit()
    headers, _ = _bearer_headers(engine, 'patient-token', user_id=3)
    # Simulate a browser cookie resolving to doctor #1 while the Authorization
    # header identifies a different, non-clinician account. Bearer must win.
    headers['x-login'] = '1'
    response = client.get('/patients/1/voice-exam/history', headers=headers)
    assert response.status_code == 401, response.text


def test_native_bearer_voice_auth_rejects_unverified_expired_and_non_doctor_sessions(app_client, monkeypatch):
    client, engine = app_client
    main = sys.modules['app.main']
    # Make this an explicitly Bearer-only integration test. A cookie/session
    # stub must not mask which persisted token identity the route evaluates.
    monkeypatch.setattr(main, 'get_current_user', lambda request: None)
    with Session(engine) as session:
        session.add(User(id=3, role='PATIENT', email_verified_at=datetime.utcnow()))
        session.add(User(id=4, role='DOCTOR', email_verified_at=None))
        session.commit()
        assert session.get(User, 3).role == 'PATIENT'
        assert session.get(User, 4).email_verified_at is None
    patient_headers, _ = _bearer_headers(engine, 'patient-token', user_id=3)
    unverified_headers, _ = _bearer_headers(engine, 'unverified-token', user_id=4)
    expired_headers, expired_hash = _bearer_headers(engine, 'expired-token', expires_at=datetime.utcnow()-timedelta(seconds=1))
    for headers in (patient_headers, unverified_headers, expired_headers):
        assert voice._user(SimpleNamespace(method='GET', headers=headers)) is None
        response = client.get('/patients/1/voice-exam/history', headers=headers)
        assert response.status_code == 401, response.text
    with Session(engine) as session:
        assert session.get(SessionToken, expired_hash) is None


def test_native_bearer_session_revocation_takes_effect_without_a_cookie(app_client):
    client, engine = app_client
    headers, token_hash = _bearer_headers(engine, 'revoked-token')
    with Session(engine) as session:
        session.delete(session.get(SessionToken, token_hash))
        session.commit()
    assert client.get('/patients/1/voice-exam/history', headers=headers).status_code == 401


def test_native_bearer_admin_requires_the_existing_second_factor_marker(app_client):
    client, engine = app_client
    with Session(engine) as session:
        session.add(User(id=5, role='ADMIN', email='dentalaidestek@gmail.com',
                         email_verified_at=datetime.utcnow()))
        session.add(Patient(id=3, owner_user_id=5))
        session.commit()
    headers, token_hash = _bearer_headers(engine, 'admin-token', user_id=5)
    assert client.get('/patients/3/voice-exam/history', headers=headers).status_code == 401
    with Session(engine) as session:
        session.add(AdminVerifiedSession(token_hash=token_hash, user_id=5))
        session.commit()
    assert client.get('/patients/3/voice-exam/history', headers=headers).status_code == 200


def test_native_bearer_voice_mutations_keep_cross_site_origin_protection(app_client):
    client, engine = app_client
    headers, _ = _bearer_headers(engine)
    headers = {**headers, 'origin': 'https://foreign.example'}
    assert client.post('/patients/1/voice-exam/apply', headers=headers,
                       json=payload(engine)).status_code == 401


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

def test_reviewed_voice_history_reads_only_explicitly_saved_anamnesis(app_client):
    client, engine = app_client
    approved = {
        'medical_history': 'Olumsuz beyan: sistemik rahatsızlık yok; geçmişte anjiyo öyküsü',
        'medications': 'Metformin kullandığını belirtti; doz doğrulanmadı',
        'allergies': 'Olmadığı belirtildi: Penisilin alerjisi',
        'family_history': 'Annesinde diyabet öyküsü olduğunu belirtti',
    }
    saved = client.post('/patients/1/voice-exam/apply', json=payload(engine, fields=approved))
    assert saved.status_code == 200
    analysis_id = saved.json()['analysis_id']

    history = client.get('/patients/1/voice-exam/history')
    assert history.status_code == 200
    body = history.json()
    assert set(body['fields']) == set(approved)
    for name, value in approved.items():
        assert body['fields'][name]['value'] == value
        assert body['fields'][name]['quote'] == ''
        assert body['fields'][name]['analysis_id'] == analysis_id
    assert 'Güncel kullanım' in body['notice']
    assert client.get('/patients/2/voice-exam/history').status_code == 404
    with Session(engine) as session:
        rows = session.execute(select(ApprovedAnamnesis.__table__)).mappings().all()
        assert len(rows) == len(approved) == 4
        assert {(row['field_key'], row['value']) for row in rows} == set(approved.items())
        assert all(row['owner_user_id'] == 1 and row['patient_id'] == 1 for row in rows)
        assert all(row['analysis_id'] == saved.json()['analysis_id'] for row in rows)


def test_reviewed_history_keeps_old_field_after_more_than_twelve_newer_reviews(app_client):
    client, engine = app_client
    old_value = 'Penisilin alerjisi olduğunu belirtti'
    first = client.post('/patients/1/voice-exam/apply', json=payload(
        engine, request_key='b' * 32, fields={'allergies': old_value}))
    assert first.status_code == 200
    old_analysis_id = first.json()['analysis_id']

    for index in range(12):
        result = client.post('/patients/1/voice-exam/apply', json=payload(
            engine, request_key=f'{index + 1:032x}',
            fields={'medical_history': f'Sistemik öykü güncellemesi {index + 1}'}))
        assert result.status_code == 200

    history = client.get('/patients/1/voice-exam/history')
    assert history.status_code == 200
    fields = history.json()['fields']
    assert fields['allergies']['value'] == old_value
    assert fields['allergies']['analysis_id'] == old_analysis_id
    assert fields['medical_history']['value'] == 'Sistemik öykü güncellemesi 12'
    with Session(engine) as session:
        rows = session.execute(select(ApprovedAnamnesis.__table__)).mappings().all()
        assert len(rows) == 13


def test_reapproving_field_preserves_prior_provenance_and_returns_latest_value(app_client):
    client, engine = app_client
    first = client.post('/patients/1/voice-exam/apply', json=payload(
        engine, request_key='c' * 32, fields={'medications': 'İlaç A kullandığını belirtti'}))
    second = client.post('/patients/1/voice-exam/apply', json=payload(
        engine, request_key='d' * 32, fields={'medications': 'İlaç B kullandığını belirtti'}))
    assert first.status_code == second.status_code == 200
    history = client.get('/patients/1/voice-exam/history').json()['fields']['medications']
    assert history['value'] == 'İlaç B kullandığını belirtti'
    assert history['analysis_id'] == second.json()['analysis_id']
    with Session(engine) as session:
        rows = session.execute(
            select(ApprovedAnamnesis.__table__).where(
                ApprovedAnamnesis.__table__.c.field_key == 'medications'
            ).order_by(ApprovedAnamnesis.__table__.c.id)
        ).mappings().all()
        assert [row['analysis_id'] for row in rows] == [
            first.json()['analysis_id'], second.json()['analysis_id']
        ]


def test_history_uses_source_analysis_order_when_backfill_inserts_older_row_later(app_client):
    client, engine = app_client
    with Session(engine) as session:
        # The newer approval is already in the ledger. A later legacy backfill
        # inserts the older source analysis afterward and therefore gets a
        # larger ledger row ID; source Analysis chronology must still win.
        session.add_all([
            ApprovedAnamnesis(
                owner_user_id=1, patient_id=1, field_key='allergies',
                value='Yeni alerji beyanı', analysis_id=900,
            ),
            ApprovedAnamnesis(
                owner_user_id=1, patient_id=1, field_key='allergies',
                value='Eski alerji beyanı', analysis_id=100,
            ),
        ])
        session.commit()

    history = client.get('/patients/1/voice-exam/history')
    assert history.status_code == 200, history.text
    field = history.json()['fields']['allergies']
    assert field['value'] == 'Yeni alerji beyanı'
    assert field['analysis_id'] == 900
    with Session(engine) as session:
        rows = session.execute(
            select(ApprovedAnamnesis.__table__.c.id, ApprovedAnamnesis.__table__.c.analysis_id)
            .where(ApprovedAnamnesis.__table__.c.field_key == 'allergies')
            .order_by(ApprovedAnamnesis.__table__.c.id)
        ).all()
        assert rows[0][1] == 900 and rows[1][1] == 100
        assert rows[0][0] < rows[1][0]


def test_idempotent_review_does_not_duplicate_approved_anamnesis_rows(app_client):
    client, engine = app_client
    data = payload(engine, request_key='e' * 32, fields={'allergies': 'Alerji yok beyanı'})
    first = client.post('/patients/1/voice-exam/apply', json=data)
    second = client.post('/patients/1/voice-exam/apply', json=data)
    assert first.status_code == second.status_code == 200
    assert second.json()['already_saved'] is True
    with Session(engine) as session:
        rows = session.execute(select(ApprovedAnamnesis.__table__)).mappings().all()
        assert len(rows) == 1



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


def test_audio_transcription_is_separate_and_truncation_stops_understanding(monkeypatch):
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
    monkeypatch.setattr(core, '_understand', lambda text, context: core.normalize({'transcript': text}))
    audio = b'RIFF' + b'\0' * 4 + b'WAVE' + b'\0' * 100
    assert core.extract(data=audio, mime='audio/wav')['transcript']
    assert len(requests) == 1 and requests[0].full_url.startswith('https://generativelanguage.googleapis.com/')
    assert 'synthetic-key' not in requests[0].full_url
    assert 'responseSchema' in json.loads(requests[0].data)['generationConfig']
    Response.finish = 'MAX_TOKENS'
    with pytest.raises(core.VoiceError, match='tamamlanmadı'):core.extract(data=audio, mime='audio/wav')


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
    from app import voice_exam_literature as literature
    monkeypatch.setattr(literature, 'retrieve_literature', lambda *args, **kw: ([], []))
    from app import voice_exam_dergipark as dergipark
    monkeypatch.setattr(dergipark, 'retrieve_dergipark', lambda *args, **kw: ([], []))
    result = sources.retrieve('metformin')
    assert not result['references'] and result['unavailable'] == ['ada-diabetes', 'topic-uncovered:diabetes dental treatment']
    assert result['source_coverage'][0]['status'] == 'uncovered'
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



def test_standalone_session_is_owned_private_and_anonymous_redirects(app_client, monkeypatch):
    from fastapi.responses import JSONResponse
    from app import main
    client, _ = app_client
    def rendered(**kw):
        from sqlalchemy import inspect
        assert inspect(kw['context']['patient']).detached, 'Release DB connection before rendering'
        return JSONResponse({'template': kw['name'], 'patient_id': kw['context']['patient'].id})
    monkeypatch.setattr(main, 'templates', SimpleNamespace(TemplateResponse=rendered), raising=False)
    response = client.get('/voice-exams/1/session')
    assert response.json() == {'template': 'voice_exam_session.html', 'patient_id': 1}
    assert response.headers['cache-control'] == 'private, no-store'
    assert client.get('/voice-exams/2/session').status_code == 404
    result = client.post('/voice-exams/anonymous', follow_redirects=False)
    assert result.headers['location'].startswith('/voice-exams/')
    assert result.headers['location'].endswith('/session')


def test_spoken_appointment_saves_on_agreed_day_for_selected_patient_only_once(app_client):
    from zoneinfo import ZoneInfo
    client, engine = app_client
    start = core.resolve_appointment("Yarın öğleden sonra 3.30'da kontrole gelebilir misiniz?",
        "Yarın 15.30'da gelirim, tamam hocam.", datetime(2026, 10, 23, 12, tzinfo=ZoneInfo('Europe/Istanbul')))
    assert start == '2026-10-24T15:30'
    data = payload(engine, fields={}, appointment={'title': 'Kontrol randevusu', 'start_at': start})
    first = client.post('/patients/1/voice-exam/apply', json=data)
    assert first.status_code == 200
    assert client.post('/patients/1/voice-exam/apply', json=data).status_code == 200
    with Session(engine) as session:
        event = session.exec(select(ScheduleEvent)).one()
        assert (event.patient_id, event.owner_user_id, event.start_at) == (1, 1, '2026-10-24T15:30')




def test_confirmation_response_does_not_wait_for_realtime_delivery(app_client,monkeypatch):
    client,engine=app_client
    main=sys.modules['app.main']
    main._record_patient_realtime_events=lambda *args:['committed-event']
    def blocking_delivery(*args):raise AssertionError('Synchronous notification delivery must not block the saved response')
    main.on_loop=blocking_delivery
    response=client.post('/patients/1/voice-exam/apply',json=payload(engine))
    assert response.status_code==200
    with Session(engine) as s:assert s.get(Analysis,response.json()['analysis_id']) is not None

def test_web_and_native_history_share_the_same_approved_record_contract(app_client):
    client, engine = app_client
    saved = client.post(
        "/patients/1/voice-exam/apply",
        json=payload(engine, request_key="f" * 32, fields={
            "medical_history": "Astım beyanı",
            "medications": "Metformin kullandığını belirtti",
            "allergies": "Penisilin alerjisi olmadığını belirtti",
        }),
    )
    assert saved.status_code == 200

    web_response = client.get("/patients/1/voice-exam/history")
    native_headers, _ = _bearer_headers(engine, token="web-native-parity-token")
    native_response = client.get("/patients/1/voice-exam/history", headers=native_headers)

    assert web_response.status_code == native_response.status_code == 200
    assert native_response.json()["fields"] == web_response.json()["fields"]
    assert native_response.json()["fields"]["medical_history"]["analysis_id"] == saved.json()["analysis_id"]
    assert "no-store" in native_response.headers.get("cache-control", "").lower()


def test_stale_second_approval_cannot_append_over_a_newer_patient_revision(app_client):
    client, engine = app_client
    original = payload(engine, request_key="1" * 32, fields={
        "allergies": "Penisilin alerjisi olduğunu belirtti",
    })
    first = client.post("/patients/1/voice-exam/apply", json=original)
    assert first.status_code == 200

    stale = {
        **original,
        "request_key": "2" * 32,
        "fields": {"allergies": "Alerji yok beyanı"},
    }
    second = client.post("/patients/1/voice-exam/apply", json=stale)
    assert second.status_code == 409

    history = client.get("/patients/1/voice-exam/history")
    assert history.status_code == 200
    assert history.json()["fields"]["allergies"]["value"] == "Penisilin alerjisi olduğunu belirtti"
    with Session(engine) as session:
        rows = session.execute(
            select(ApprovedAnamnesis.__table__).where(
                ApprovedAnamnesis.__table__.c.patient_id == 1,
                ApprovedAnamnesis.__table__.c.field_key == "allergies",
            )
        ).mappings().all()
        assert len(rows) == 1
        assert rows[0]["analysis_id"] == first.json()["analysis_id"]


def test_history_rejects_ledger_rows_with_a_different_owner_id(app_client):
    client, engine = app_client
    with Session(engine) as session:
        session.execute(ApprovedAnamnesis.__table__.insert().values(
            owner_user_id=2,
            patient_id=1,
            field_key="allergies",
            value="Başka hekime ait beyan",
            analysis_id=987654,
        ))
        session.commit()

    history = client.get("/patients/1/voice-exam/history")
    assert history.status_code == 200
    assert history.json()["fields"] == {}
