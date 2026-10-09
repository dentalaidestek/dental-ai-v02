from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from app import main, migrate

@pytest.fixture
def setup(monkeypatch, tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'email.db'), connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    sent = []
    monkeypatch.setattr(main, 'send_email_verification_code', lambda email, code: sent.append((email, code)))
    with Session(engine) as s:
        user = main.User(username='emailowner', display_name='Owner', role='DOCTOR', email='old@example.test', email_verified_at=main._utcnow_naive(), password_hash=main.hash_password('correct-password'))
        other = main.User(username='otheruser', display_name='Other', role='DOCTOR', email='taken@example.test', email_verified_at=main._utcnow_naive())
        s.add_all([user, other]); s.flush(); uid = user.id
        s.add(main.PasswordResetToken(user_id=uid, token_hash='old-recovery-link', expires_at=main._utcnow_naive() + timedelta(hours=1)))
        for token, owner in [('current', user.id), ('second', user.id), ('other', other.id)]:
            s.add(main.SessionToken(user_id=owner, token_hash=main.hash_session_token(token), expires_at=main._utcnow_naive() + timedelta(days=1)))
        s.commit()
    yield engine, uid, sent
    engine.dispose()

def start(client, email='new@example.test', password='correct-password', **extra):
    return client.post('/account/email', data=dict(new_email=email, password=password, **extra), cookies={main.SESSION_COOKIE: 'current'}, follow_redirects=False)

def confirm(client, code, token='current'):
    return client.post('/account/email/confirm', data={'code': code}, cookies={main.SESSION_COOKIE: token}, follow_redirects=False)

def test_change_requires_password_and_otp_then_revokes_all_owned_sessions(setup):
    engine, uid, sent = setup
    with TestClient(main.app) as client:
        assert start(client, password='wrong').status_code == 400
        assert sent == []
        assert start(client).status_code == 200
        assert start(client).status_code == 200
        assert len(sent) == 1
        with Session(engine) as s:
            assert s.get(main.User, uid).email == 'old@example.test'
            assert s.get(main.EmailChangeChallenge, uid).code_hash != sent[0][1]
        assert confirm(client, sent[0][1], token='other').status_code == 400
        assert confirm(client, sent[0][1], token='second').status_code == 400
        response = confirm(client, sent[0][1])
        assert response.status_code == 303
        assert response.headers['location'] == '/login?email_changed=1'
        assert 'Max-Age=0' in response.headers['set-cookie']
        assert confirm(client, sent[0][1]).headers['location'] == '/login'
        assert 'Yeni adresinizle giriş' in client.get('/login?email_changed=1').text
    with Session(engine) as s:
        assert s.get(main.User, uid).email == 'new@example.test'
        assert s.get(main.User, uid).email_verified_at is not None
        assert s.get(main.EmailChangeChallenge, uid) is None
        assert not s.exec(select(main.SessionToken).where(main.SessionToken.user_id == uid)).all()
        assert not s.exec(select(main.PasswordResetToken).where(main.PasswordResetToken.user_id == uid)).all()
        assert len(s.exec(select(main.SessionToken)).all()) == 1

@pytest.mark.parametrize('email', ['broken', 'old@example.test', 'TAKEN@example.test'])
def test_invalid_or_used_addresses_do_not_send_or_change(setup, email):
    engine, uid, sent = setup
    with TestClient(main.app) as client:
        assert start(client, email=email).status_code == 400
    assert sent == []
    with Session(engine) as s:
        assert s.get(main.User, uid).email == 'old@example.test'

@pytest.mark.parametrize('reason', ['expired', 'attempts', 'password', 'address'])
def test_invalidated_challenge_keeps_old_identity(setup, reason):
    engine, uid, sent = setup
    with TestClient(main.app) as client:
        assert start(client).status_code == 200
        with Session(engine) as s:
            ch = s.get(main.EmailChangeChallenge, uid)
            user = s.get(main.User, uid)
            if reason == 'expired': ch.expires_at = main._utcnow_naive() - timedelta(seconds=1)
            if reason == 'attempts': ch.attempts = 5
            if reason == 'password': user.password_hash = main.hash_password('new-password')
            if reason == 'address': ch.old_email = 'different@example.test'
            s.add_all([ch, user]); s.commit()
        assert confirm(client, sent[0][1]).status_code == 400
    with Session(engine) as s:
        assert s.get(main.User, uid).email == 'old@example.test'

def test_five_wrong_codes_block_correct_code_but_explicit_renewal_recovers(setup):
    engine, uid, sent = setup
    with TestClient(main.app) as client:
        assert start(client).status_code == 200
        wrong = '111111' if sent[0][1] != '111111' else '222222'
        for _ in range(5): assert confirm(client, wrong).status_code == 400
        assert confirm(client, sent[0][1]).status_code == 400
        assert start(client).status_code == 200
        assert len(sent) == 2
        assert confirm(client, sent[1][1]).status_code == 303

def test_delivery_failure_keeps_account_usable(setup, monkeypatch):
    engine, uid, sent = setup
    def fail(*_): raise RuntimeError('provider secret must not appear')
    monkeypatch.setattr(main, 'send_email_verification_code', fail)
    with TestClient(main.app) as client:
        response = start(client)
        assert response.status_code == 503
        assert 'provider secret' not in response.text
        assert client.get('/account', cookies={main.SESSION_COOKIE:'current'}).status_code == 200
    with Session(engine) as s:
        assert s.get(main.User, uid).email == 'old@example.test'
        assert s.get(main.EmailChangeChallenge, uid) is None

def test_cross_site_request_is_rejected_without_mail(setup):
    _, _, sent = setup
    with TestClient(main.app) as client:
        response = client.post('/account/email', data={'new_email': 'new@example.test', 'password': 'correct-password'}, cookies={main.SESSION_COOKIE: 'current'}, headers={'Origin': 'https://attacker.example'})
        assert response.status_code == 403
    assert sent == []

def test_explicit_resend_and_reload_preserve_recovery(setup):
    engine, uid, sent = setup
    with TestClient(main.app) as client:
        assert start(client).status_code == 200
        page = client.get('/account', cookies={main.SESSION_COOKIE: 'current'})
        assert 'action="/account/email/confirm"' in page.text
        assert start(client, renew='1').status_code == 200
        assert len(sent) == 2
        assert confirm(client, sent[1][1]).status_code == 303

def test_address_taken_after_sending_cannot_be_claimed(setup):
    engine, uid, sent = setup
    with TestClient(main.app) as client:
        assert start(client).status_code == 200
        with Session(engine) as s:
            other = s.exec(select(main.User).where(main.User.username == 'otheruser')).one()
            other.email = 'new@example.test'; s.add(other); s.commit()
        assert confirm(client, sent[0][1]).status_code == 400
    with Session(engine) as s:
        assert s.get(main.User, uid).email == 'old@example.test'

def test_gmail_aliases_cannot_claim_another_account_address(setup):
    engine, _, sent = setup
    with Session(engine) as s:
        user = s.exec(select(main.User).where(main.User.username == 'otheruser')).one()
        user.email = 'alice@gmail.com'; s.add(user); s.commit()
    with TestClient(main.app) as client:
        assert start(client, email='a.l.i.c.e+alias@googlemail.com').status_code == 400
    assert sent == []

def test_correct_password_cannot_send_unlimited_codes(setup):
    engine, uid, sent = setup
    with TestClient(main.app) as client:
        for _ in range(3):
            assert start(client, renew='1').status_code == 200
        assert start(client, renew='1').status_code == 429
    assert len(sent) == 3
    with Session(engine) as s:
        assert s.get(main.User, uid).email == 'old@example.test'

def test_revision_ten_migration_creates_challenge_table_repeatably(setup):
    engine, uid, _ = setup
    main.EmailChangeChallenge.__table__.drop(engine)
    migrate.apply(); migrate.apply(); migrate.require_schema(engine)
    with Session(engine) as s:
        assert s.get(main.EmailChangeChallenge, uid) is None
        assert s.get(main.User, uid).email == 'old@example.test'
