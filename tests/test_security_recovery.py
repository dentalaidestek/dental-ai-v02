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
    new = main._ensure_email_verification_challenge(session, user)
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
    monkeypatch.setattr(mobile_api, '_LOGIN_FAILURES', {})
    monkeypatch.setattr(main, '_WEB_LOGIN_FAILURES', {})
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
        accepted = main.login_user(request, user.username, 'correct-password', '/patients')
        assert accepted.context['challenge_token'] != old_token
        assert accepted.context['next_url'] == '/patients'
        assert 'set-cookie' not in accepted.headers
    else:
        accepted = mobile_api.mobile_login(mobile_api.LoginRequest(login=user.username, password='correct-password'))
        assert accepted.challenge_token != old_token
        assert accepted.access_token is None
    assert len(sent) == 2
    assert not session.exec(select(main.SessionToken).where(main.SessionToken.user_id == user.id)).all()
