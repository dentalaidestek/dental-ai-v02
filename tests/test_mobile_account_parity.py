from test_mobile_chat_actions import chat
from app import main
from sqlmodel import Session,select
from starlette.responses import Response
import pytest

@pytest.fixture
def account(chat,monkeypatch):
    client,engine=chat;sent=[]
    monkeypatch.setattr(main,'send_email_verification_code',lambda email,code:sent.append((email,code)))
    def render(*args,**kwargs):
        response=Response('',status_code=kwargs.get('status_code',200));response.context=kwargs.get('context') or (args[1] if len(args)>1 and isinstance(args[1],dict) else {});return response
    monkeypatch.setattr(main.templates,'TemplateResponse',render)
    with Session(engine) as s:
        user=s.get(main.User,1);user.email='synthetic@example.test';user.password_hash=main.hash_password('correct-password');s.add(user);s.commit()
    return client,engine,sent

def test_native_registration_keeps_web_consent_title_and_email_verification_rules(account):
    client,engine,sent=account;client.headers.pop('Authorization')
    values={'legal_version':main.LEGAL_VERSION,'display_name':'Synthetic New','email':'new@example.test','username':'synthetic-new','password':'correct-password','university':'Synthetic University','professional_title':'Öğrenci','specialty':'should be cleared','accept_terms':True,'kvkk_informed':True,'accept_clinical':True}
    assert client.post('/api/mobile/v1/auth/register',json={**values,'accept_terms':False}).status_code==400
    result=client.post('/api/mobile/v1/auth/register',json={**values,'role':'ADMIN'})
    assert result.status_code==200,result.text
    assert result.json()['access_token'] is None and result.json()['challenge_token']
    with Session(engine) as s:
        user=s.exec(select(main.User).where(main.User.username=='synthetic-new')).one()
        assert user.role=='DOCTOR' and user.email_verified_at is None
        assert not s.exec(select(main.SessionToken).where(main.SessionToken.user_id==user.id)).all()
        assert len(s.exec(select(main.AgreementAcceptance).where(main.AgreementAcceptance.user_id==user.id)).all())==3
        assert s.exec(select(main.DoctorProfile).where(main.DoctorProfile.user_id==user.id)).one().specialty is None
    verified=client.post('/api/mobile/v1/auth/verify-email',json={'challenge_token':result.json()['challenge_token'],'code':sent[-1][1]})
    assert verified.status_code==200,verified.text
    assert client.post('/api/mobile/v1/auth/verify-email',json={'challenge_token':result.json()['challenge_token'],'code':sent[-1][1]}).status_code==400

def test_native_account_reuses_name_username_cooldown_and_password_revocation(account):
    client,engine,_=account
    assert client.post('/api/mobile/v1/account/display-name',json={'display_name':'Updated Synthetic'}).status_code==200
    response=client.post('/api/mobile/v1/account/username',json={'username':'changed-user'})
    assert response.status_code==200,response.text
    assert client.post('/api/mobile/v1/account/username',json={'username':'changed-again'}).status_code==429
    data=client.get('/api/mobile/v1/account').json()
    assert data['user']['display_name']=='Updated Synthetic' and data['next_username_change_at']
    assert 'password_hash' not in str(data)
    assert client.post('/api/mobile/v1/account/password',json={'current_password':'bad','new_password':'new-password','new_password_confirm':'new-password'}).status_code==400
    response=client.post('/api/mobile/v1/account/password',json={'current_password':'correct-password','new_password':'new-password','new_password_confirm':'new-password'})
    assert response.status_code==200 and response.json()['requires_login'] is True
    assert client.get('/api/mobile/v1/me').status_code==401

def test_recovery_is_generic_and_reset_revokes_sessions_and_is_single_use(account,monkeypatch):
    client,engine,_=account;links=[]
    monkeypatch.setattr(main,'send_brevo_password_reset_email',lambda **kwargs:links.append(kwargs['reset_link']))
    first=client.post('/api/mobile/v1/auth/forgot-password',json={'email':'synthetic@example.test'})
    missing=client.post('/api/mobile/v1/auth/forgot-password',json={'email':'missing@example.test'})
    assert first.status_code==200 and first.json()==missing.json()
    from urllib.parse import urlparse,parse_qs
    token=parse_qs(urlparse(links[-1]).query)['token'][0]
    values={'token':token,'password':'recovered-password','password_confirm':'recovered-password'}
    assert client.post('/api/mobile/v1/auth/reset-password',json=values).status_code==200
    assert client.post('/api/mobile/v1/auth/reset-password',json=values).status_code==400
    assert client.get('/api/mobile/v1/me').status_code==401

def test_email_change_is_session_bound_and_revokes_access_after_confirmation(account):
    client,engine,sent=account
    response=client.post('/api/mobile/v1/account/email',json={'new_email':'updated@example.test','password':'correct-password'})
    assert response.status_code==200,response.text
    assert response.json()['pending_email']=='updated@example.test'
    client.headers['Authorization']='Bearer token2'
    assert client.post('/api/mobile/v1/account/email/confirm',json={'code':sent[-1][1]}).status_code==400
    client.headers['Authorization']='Bearer token1'
    response=client.post('/api/mobile/v1/account/email/confirm',json={'code':sent[-1][1]})
    assert response.status_code==200,response.text
    assert response.json()['requires_login'] is True
    assert client.get('/api/mobile/v1/me').status_code==401
    with Session(engine) as s:assert s.get(main.User,1).email=='updated@example.test'

def test_admin_email_cannot_change_and_profile_photo_is_private(account):
    client,engine,_=account
    with Session(engine) as s:
        user=s.get(main.User,1);user.role='ADMIN';user.email=main.ADMIN_FIXED_EMAIL;s.add(user);s.commit()
    assert client.get('/api/mobile/v1/account').status_code==403
    with Session(engine) as s:
        s.add(main.AdminVerifiedSession(token_hash=main.hash_session_token('token1'),user_id=1));s.commit()
    assert client.post('/api/mobile/v1/account/email',json={'new_email':'admin-new@example.test','password':'correct-password'}).status_code==403
    assert client.get('/api/mobile/v1/account').json()['email_change_allowed'] is False
    import io,base64
    from PIL import Image
    raw=io.BytesIO();Image.new('RGB',(10,10),'white').save(raw,format='PNG')
    response=client.post('/api/mobile/v1/account/profile-photo',json={'profile_photo_data':'data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode()})
    assert response.status_code==200,response.text
    path=client.get('/api/mobile/v1/account').json()['photo_url']
    response=client.get(path)
    assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
    client.headers['Authorization']='Bearer token2'
    assert client.get(path).status_code==404


def test_native_self_erasure_reuses_web_confirmation_and_revokes_the_session(account):
    client,engine,_=account
    username='chat-user-1'
    assert client.post('/api/mobile/v1/account/delete',json={
        'confirm_username':'different-user','password':'correct-password'
    }).status_code==400
    assert client.post('/api/mobile/v1/account/delete',json={
        'confirm_username':username,'password':'wrong-password'
    }).status_code==403

    response=client.post('/api/mobile/v1/account/delete',json={
        'confirm_username':username,'password':'correct-password'
    })
    assert response.status_code==200,response.text
    assert response.json()=={'ok':True,'requires_login':True}
    assert client.get('/api/mobile/v1/me').status_code==401

    with Session(engine) as s:
        deleted=s.get(main.User,1)
        assert deleted is not None and not deleted.is_active
        assert deleted.display_name=='Silinmiş Kullanıcı'
        assert deleted.email is None and deleted.password_hash is None
        assert not s.exec(select(main.SessionToken).where(main.SessionToken.user_id==1)).all()
        assert not s.exec(select(main.DeletedAccountEmail).where(main.DeletedAccountEmail.deleted_user_id==1)).all()


def test_native_self_erasure_keeps_the_web_admin_exclusion(account):
    client,engine,_=account
    with Session(engine) as s:
        user=s.get(main.User,1)
        user.role='ADMIN'
        s.add(user)
        s.add(main.AdminVerifiedSession(token_hash=main.hash_session_token('token1'),user_id=1))
        s.commit()
    response=client.post('/api/mobile/v1/account/delete',json={
        'confirm_username':'chat-user-1','password':'correct-password'
    })
    assert response.status_code==409,response.text
    with Session(engine) as s:
        user=s.get(main.User,1)
        assert user.is_active and user.email=='synthetic@example.test'
