from starlette.requests import Request
from app import main


def request(path='/login'):
    return Request({'type': 'http', 'method': 'GET', 'path': path, 'headers': []})


def test_normal_login_has_no_code_renewal_control():
    html = main.login_page(request()).body.decode()
    assert 'type="checkbox"' not in html
    assert 'name="renew_email_code"' not in html
    assert 'Tekrar hoş geldin' in html
    assert 'autocomplete="current-password"' in html


def test_explicit_renewal_requires_login_and_preserves_destination():
    html = main.login_page(request(), next='/patients', renew='1').body.decode()
    assert 'name="renew_email_code" value="1"' in html
    assert 'name="next_url" value="/patients"' in html
    assert 'name="password" required' in html
    assert 'Yeni doğrulama kodu' in html


def test_used_code_shows_login_without_issuing_another_session(monkeypatch, tmp_path):
    from sqlmodel import Session, SQLModel, create_engine
    engine = create_engine('sqlite:///' + str(tmp_path / 'auth.db'))
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    with Session(engine) as session:
        user = main.User(username='synthetic', display_name='Synthetic', email='synthetic@example.test', is_active=True, role='DOCTOR', email_verified_at=main._utcnow_naive())
        session.add(user); session.flush()
        challenge = main.EmailVerificationChallenge(user_id=user.id, public_token='synthetic-challenge', code_hash='destroyed', expires_at=main._utcnow_naive(), verified_at=main._utcnow_naive())
        session.add(challenge); session.commit()
    response = main.verify_email(request('/verify-email'), 'synthetic-challenge', '123456', '/patients')
    assert 'set-cookie' not in response.headers
    assert 'action="/login"' in response.body.decode()
    assert 'E-postanız doğrulandı' in response.body.decode()
    engine.dispose()
