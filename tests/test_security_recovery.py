import ast
import asyncio
import io
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
from starlette.requests import Request
from starlette.websockets import WebSocket

from app import main
from app.clinical_rag_router import _build_router_prompt


@pytest.fixture
def identity_db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    sent = []
    monkeypatch.setattr(main, 'send_email_verification_code', lambda email, code: sent.append((email, code)))
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username='recovery', email='recovery@example.test', role='DOCTOR', display_name='Recovery', is_active=True, password_hash=main.hash_password('correct-password'))
        session.add(user)
        session.commit()
        session.refresh(user)
        yield session, user, sent
    engine.dispose()


@pytest.mark.parametrize('invalid_kind', ['expired', 'exhausted'])
def test_credentials_can_replace_unusable_challenge_without_replay(identity_db, invalid_kind):
    session, user, sent = identity_db
    old = main._ensure_email_verification_challenge(session, user)
    old_token, old_code = old.public_token, sent[-1][1]
    if invalid_kind == 'expired':
        old.expires_at = main._utcnow_naive() - main.timedelta(seconds=1)
    else:
        old.attempts = 5
    session.add(old)
    session.commit()
    new = main._ensure_email_verification_challenge(session, user, renew=True)
    assert new.public_token != old_token
    assert new.attempts == 0
    assert len(sent) == 2
    assert not main._verify_email_code(session, user, old, old_code)
    assert main._verify_email_code(session, user, new, sent[-1][1])
    assert not main._verify_email_code(session, user, new, sent[-1][1])


def test_valid_challenge_is_reused_without_another_email(identity_db):
    session, user, sent = identity_db
    challenge = main._ensure_email_verification_challenge(session, user)
    again = main._ensure_email_verification_challenge(session, user)
    assert again.public_token == challenge.public_token
    assert len(sent) == 1


@pytest.mark.parametrize('verified', [False, True])
def test_native_socket_requires_same_verification_as_http(identity_db, verified):
    session, user, _ = identity_db
    user.email_verified_at = main._utcnow_naive() if verified else None
    session.add(user)
    session.add(main.SessionToken(user_id=user.id, token_hash=main.hash_session_token('socket-test'), expires_at=main._utcnow_naive() + main.timedelta(days=1)))
    session.commit()
    websocket = WebSocket({'type': 'websocket', 'path': '/ws/sync', 'headers': [(b'authorization', b'Bearer socket-test')]}, receive=None, send=None)
    actual = main._socket_current_user(websocket)
    assert (actual is not None) == verified


@pytest.mark.parametrize('next_url, expected', [('/patients?view=recent', '/patients?view=recent'), ('https://evil.example', '/'), ('//evil.example', '/')])
def test_verification_preserves_only_safe_destination(identity_db, next_url, expected):
    session, user, sent = identity_db
    challenge = main._ensure_email_verification_challenge(session, user)
    response = main.verify_email(Request({'type': 'http', 'method': 'POST', 'path': '/verify-email', 'headers': []}), challenge.public_token, sent[-1][1], next_url)
    assert response.status_code == 303
    assert response.headers['location'] == expected
    assert 'HttpOnly' in response.headers['set-cookie']


def test_prompt_masks_identifiers_and_keeps_clinical_lines():
    prompt = _build_router_prompt(age=32, tooth_number='36', chief_complaint='soğukta ağrı; email: test.patient@example.test', clinical_notes='Hasta\tadı: Test Patient\nPalpasyon hassas değil; 0555 123 45 67', extra_text='TC: 12345678901; Perküsyon pozitif', stored_image_types=[], image_count=0)
    for identifier in ['test.patient@example.test', 'Test Patient', '0555 123 45 67', '12345678901']:
        assert identifier not in prompt
    for clinical in ['soğukta ağrı', 'Palpasyon hassas değil', 'Perküsyon pozitif']:
        assert clinical in prompt
    assert '[REDACTED]' in prompt


@pytest.mark.parametrize('payload, status', [(b'', 400), (b'12345', 413)])
def test_rejected_direct_upload_leaves_no_temporary_file(tmp_path, payload, status):
    # Execute the actual upload handler without importing heavyweight model loaders.
    source = Path('vision_service/anatomy3d_direct_app.py').read_text()
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'analyze_image')
    function.decorator_list = []
    function.args.defaults = []
    for arg in function.args.args:
        arg.annotation = None
    function.returns = None
    globals_ = {'Path': Path, 'tempfile': SimpleNamespace(NamedTemporaryFile=lambda **kwargs: tempfile.NamedTemporaryFile(dir=tmp_path, **kwargs)), 'HTTPException': HTTPException, 'MAX_IMAGE_BYTES': 4}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<upload-handler>', 'exec'), globals_)
    with pytest.raises(HTTPException) as error:
        asyncio.run(globals_['analyze_image'](UploadFile(filename='image.jpg', file=io.BytesIO(payload)), None))
    assert error.value.status_code == status
    assert not list(tmp_path.iterdir())


def test_registration_returns_session_instead_of_name_error(identity_db, monkeypatch):
    session, _, _ = identity_db
    monkeypatch.setattr(main, '_check_registration_rate', lambda request: 'test')
    monkeypatch.setattr(main, '_record_registration_attempt', lambda key: None)
    request = Request({'type': 'http', 'method': 'POST', 'path': '/register', 'headers': []})
    response = main.register_user(request, display_name='New Doctor', email='new@example.test', username='newdoctor', password='correct-password', university='Test University', professional_title='Öğrenci', specialty='', accept_terms='on', kvkk_informed='on', accept_clinical='on')
    assert response.status_code == 303
    assert 'HttpOnly' in response.headers['set-cookie']
    session.expire_all()
    assert session.exec(select(main.User).where(main.User.username == 'newdoctor')).first()


def test_actual_provider_request_masks_identifiers_and_preserves_schema(monkeypatch):
    import json
    from contextlib import nullcontext
    from app import ai_provider
    requests = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return b'{"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}'
    def transport(request, **kwargs):
        requests.append(json.loads(request.data))
        return Response()
    monkeypatch.setattr(ai_provider, 'GEMINI_API_KEY', 'test-key')
    monkeypatch.setattr(ai_provider, 'urlopen', transport)
    monkeypatch.setattr(ai_provider, 'reservation', lambda *args: nullcontext())
    schema = {'type': 'OBJECT', 'properties': {'result': {'type': 'STRING'}}}
    answer = ai_provider.ask_ai('Klinik not: ağrı yok; user@example.test; 0555 123 45 67; 12345678901', response_schema=schema, structured_vision='{"notes":"mail: image@example.test","tooth_fdi":36,"confidence":0.9}')
    assert answer == 'ok'
    payload = requests[0]
    text = payload['contents'][0]['parts'][0]['text']
    for identifier in ('user@example.test', 'image@example.test', '0555 123 45 67', '12345678901'):
        assert identifier not in text
    structured = json.loads(text.split('DENTALAI_STRUCTURED_VISION_OUTPUT:\n', 1)[1])
    assert structured['tooth_fdi'] == 36
    assert structured['confidence'] == 0.9
    assert 'ağrı yok' in text
    assert payload['generationConfig']['responseSchema'] == schema


@pytest.mark.parametrize('client_kind', ['web', 'native'])
def test_login_renews_expired_code_only_after_correct_password(identity_db, monkeypatch, client_kind):
    from app import mobile_api
    session, user, sent = identity_db
    monkeypatch.setattr(mobile_api, 'engine', main.engine)
    old = main._ensure_email_verification_challenge(session, user)
    old_token = old.public_token
    old.expires_at = main._utcnow_naive() - main.timedelta(seconds=1)
    session.add(old)
    session.commit()
    request = Request({'type': 'http', 'method': 'POST', 'path': '/login', 'headers': [], 'client': ('127.0.0.1', 1)})
    if client_kind == 'web':
        denied = main.login_user(request, user.username, 'wrong-password', '/')
        assert denied.status_code == 401
    else:
        with pytest.raises(HTTPException) as error:
            mobile_api.mobile_login(mobile_api.LoginRequest(login=user.username, password='wrong-password'))
        assert error.value.status_code == 401
    assert len(sent) == 1
    if client_kind == 'web':
        accepted = main.login_user(request, user.username, 'correct-password', '/patients', renew_email_code='1')
        assert accepted.context['challenge_token'] != old_token
        assert accepted.context['next_url'] == '/patients'
        assert 'set-cookie' not in accepted.headers
    else:
        accepted = mobile_api.mobile_login(mobile_api.LoginRequest(login=user.username, password='correct-password', renew_email_code=True))
        assert accepted.challenge_token != old_token
        assert accepted.access_token is None
    assert len(sent) == 2
    assert not session.exec(select(main.SessionToken).where(main.SessionToken.user_id == user.id)).all()

@pytest.mark.parametrize('client_kind', ['web', 'native'])
def test_expired_login_does_not_send_code_without_explicit_request(identity_db, monkeypatch, client_kind):
    from app import mobile_api
    session, user, sent = identity_db
    monkeypatch.setattr(mobile_api, 'engine', main.engine)
    old = main._ensure_email_verification_challenge(session, user)
    token = old.public_token
    old.expires_at = main._utcnow_naive() - main.timedelta(seconds=1)
    session.add(old)
    session.commit()
    if client_kind == 'web':
        request = Request({'type': 'http', 'method': 'POST', 'path': '/login', 'headers': [], 'client': ('127.0.0.1', 1)})
        result = main.login_user(request, user.username, 'correct-password', '/')
        assert result.context['challenge_token'] == token
        assert 'set-cookie' not in result.headers
    else:
        result = mobile_api.mobile_login(mobile_api.LoginRequest(login=user.username, password='correct-password'))
        assert result.challenge_token == token
        assert result.access_token is None
    assert len(sent) == 1


def test_mobile_router_has_unique_operation_contracts():
    operations = [(method, route.path) for route in main.app.routes for method in getattr(route, 'methods', ()) if route.path.startswith('/api/mobile/')]
    assert len(operations) == len(set(operations))


def test_web_and_native_share_the_same_principal_rate_bucket(identity_db, monkeypatch):
    from app import mobile_api
    _, user, _ = identity_db
    monkeypatch.setattr(mobile_api, 'engine', main.engine)
    monkeypatch.setattr(mobile_api, 'LOGIN_RATE_MAX_FAILURES', 2)
    monkeypatch.setattr(main, 'WEB_LOGIN_RATE_MAX_FAILURES', 2)
    request = Request({'type': 'http', 'method': 'POST', 'path': '/login', 'headers': [], 'client': ('127.0.0.1', 1)})
    assert main.login_user(request, user.username, 'wrong-password', '/').status_code == 401
    with pytest.raises(HTTPException) as native:
        mobile_api.mobile_login(mobile_api.LoginRequest(login=user.username, password='wrong-password'))
    assert native.value.status_code == 401
    with pytest.raises(HTTPException) as web:
        main.login_user(request, user.username, 'wrong-password', '/')
    assert web.value.status_code == 429


def test_patient_and_durable_event_are_one_transaction(identity_db, monkeypatch):
    from app import mobile_api
    _, user, _ = identity_db
    monkeypatch.setattr(mobile_api, 'engine', main.engine)
    def fail_event(*args):
        raise RuntimeError('synthetic event storage failure')
    monkeypatch.setattr(mobile_api, '_record_patient_realtime_events', fail_event)
    with pytest.raises(RuntimeError):
        mobile_api.mobile_create_patient(mobile_api.MobilePatientCreate(first_name='Synthetic', last_name='Patient'), user)
    with Session(main.engine) as session:
        assert not session.exec(select(main.Patient).where(main.Patient.owner_user_id == user.id)).all()
        assert not session.exec(select(main.PatientProfile)).all()


@pytest.mark.parametrize('payload', [b'<html>not an image</html>', b'GIF89a\x00\x00'])
def test_vision_rejects_spoofed_image_content(payload):
    from vision_service import app as vision
    with pytest.raises(HTTPException) as error:
        with vision._saved_image(UploadFile(io.BytesIO(payload), filename='scan.png'), 'scan.png'):
            pytest.fail('spoofed image accepted')
    assert error.value.status_code == 422


def test_vision_does_not_return_provider_secrets(monkeypatch):
    from vision_service import app as vision
    from PIL import Image
    image = io.BytesIO()
    Image.new('RGB', (2, 2)).save(image, format='PNG')
    def unavailable(_):
        raise vision.VisionError('provider token=secret patient=Synthetic')
    monkeypatch.setattr(vision, 'analyze_panorama', unavailable)
    with pytest.raises(HTTPException) as error:
        vision.analyze_image(UploadFile(io.BytesIO(image.getvalue()), filename='scan.png'))
    assert error.value.status_code == 503
    assert 'secret' not in error.value.detail
    assert 'Synthetic' not in error.value.detail


@pytest.mark.parametrize('error_class', [main.StudyRAGError, main.StudyAIError])
def test_academic_provider_errors_never_echo_secrets(identity_db, monkeypatch, error_class):
    from fastapi import BackgroundTasks
    import json
    _, user, _ = identity_db
    events = []
    monkeypatch.setattr(main, 'get_current_user', lambda request: user)
    monkeypatch.setattr(main, 'begin_trace', lambda *args: 'synthetic-trace')
    monkeypatch.setattr(main, 'trace_event', lambda *args, **kwargs: events.append(kwargs))
    def fail(*args):
        raise error_class('provider token=synthetic-secret patient=Synthetic Patient')
    monkeypatch.setattr(main, '_owned_study_course', fail)
    request = Request({'type': 'http', 'method': 'POST', 'path': '/notes/courses/1/ai/ask', 'headers': []})
    response = main.study_ai_ask(request, 1, BackgroundTasks(), 'synthetic question')
    assert response.status_code == 502
    emitted = response.body.decode() + json.dumps(events)
    assert 'synthetic-secret' not in emitted
    assert 'Synthetic Patient' not in emitted
