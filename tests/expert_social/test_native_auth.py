"""Native social requests share web records without granting web admin MFA."""
from datetime import timedelta
import uuid
import pytest
from sqlmodel import Session, select
from app import main
from test_api import env

def native(client, token='t1'):
    client.cookies.clear()
    client.headers.pop('Origin', None)
    client.headers['Authorization'] = 'Bearer ' + token

def test_native_post_retry_like_and_thread_share_web_records(env):
    c, engine = env
    native(c)
    body = {'text':'Bilimsel paylaşım', 'idempotency_key':str(uuid.uuid4())}
    first = c.post('/api/expert-social/posts', json=body)
    assert first.status_code == 200, first.text
    ident = first.json()['id']
    assert c.post('/api/expert-social/posts', json=body).json()['id'] == ident
    native(c, 't2')
    url = f'/api/expert-social/posts/{ident}'
    for _ in range(5):
        assert c.put(url+'/like', json={'liked':True}).json()['like_count'] == 1
    comment = c.post(url+'/comments', json={'text':'Teşekkürler', 'idempotency_key':str(uuid.uuid4())})
    assert comment.status_code == 200, comment.text
    c.headers.pop('Authorization')
    c.cookies.set(main.SESSION_COOKIE, 't1')
    assert c.get(url).json()['like_count'] == 1
    assert c.get(url+'/comments', params={'threaded':True}).json()['items'][0]['id'] == comment.json()['id']

@pytest.mark.parametrize('mode', ['expired','revoked','inactive','unverified'])
def test_native_session_validation_is_enforced(env, mode):
    c, engine = env
    with Session(engine) as s:
        token=s.exec(select(main.SessionToken).where(main.SessionToken.user_id == 1)).one()
        user=s.get(main.User,1)
        if mode == 'expired': token.expires_at=main._utcnow_naive()-timedelta(seconds=1); s.add(token)
        if mode == 'revoked': s.delete(token)
        if mode == 'inactive': user.is_active=False; s.add(user)
        if mode == 'unverified': user.email_verified_at=None; s.add(user)
        s.commit()
    native(c)
    assert c.get('/api/expert-social/feed/discover').status_code == 401

def test_native_cannot_bypass_origin_or_use_cookie_as_bearer_fallback(env):
    c,_=env
    c.headers['Authorization']='Bearer invalid'
    assert c.get('/api/expert-social/feed/discover').status_code == 401
    native(c)
    c.headers['Origin']='https://unrelated.example'
    assert c.put('/api/expert-social/experts/3/follow',json={'followed':True}).status_code == 403

def test_native_admin_token_has_no_moderation_authority(env):
    c,_=env
    native(c,'t4')
    assert c.get('/api/expert-social/moderation').status_code == 403

def test_native_profile_photo_preserves_block_and_member_scope(env, monkeypatch, tmp_path):
    c,engine=env
    path=tmp_path/'avatar.jpg';path.write_bytes(b'synthetic-avatar')
    monkeypatch.setattr(main,'storage_ensure_local',lambda _:path)
    with Session(engine) as s:
        user=s.get(main.User,1);user.profile_photo_path='private/avatar.jpg';s.add(user);s.commit()
    native(c,'t2')
    response=c.get('/api/expert-social/experts/1/photo')
    assert response.status_code == 200, response.text
    assert response.content == b'synthetic-avatar'
    assert response.headers['cache-control'] == 'private, no-store'
    with Session(engine) as s:
        s.add(main.UserBlock(blocker_user_id=1,blocked_user_id=2));s.commit()
    assert c.get('/api/expert-social/experts/1/photo').status_code == 404
    c.headers.pop('Authorization')
    assert c.get('/api/expert-social/experts/1/photo').status_code == 401


def test_native_relationship_lists_are_private_even_to_admin(env):
    c,_=env
    native(c,'t2')
    assert c.put('/api/expert-social/experts/1/follow',json={'followed':True}).status_code==200
    assert c.get('/api/expert-social/experts/2/following').json()['items'][0]['user_id']==1
    assert c.get('/api/expert-social/experts/1/followers').status_code==403
    native(c,'t4')
    assert c.get('/api/expert-social/experts/1/followers').status_code==403
    native(c,'t1')
    result=c.get('/api/expert-social/experts/1/followers')
    assert result.status_code==200 and result.json()['items'][0]['user_id']==2
    assert result.headers['cache-control']=='private, no-store'


def test_native_relationship_updates_share_web_state_and_hide_blocked_members(env):
    c,engine=env;native(c,'t2')
    assert c.put('/api/expert-social/experts/1/follow',json={'followed':True}).status_code==200
    c.headers.pop('Authorization');c.cookies.set(main.SESSION_COOKIE,'t1')
    assert c.get('/api/expert-social/experts/1/followers').json()['items'][0]['user_id']==2
    with Session(engine) as s:s.add(main.UserBlock(blocker_user_id=1,blocked_user_id=2));s.commit()
    native(c,'t1');assert c.get('/api/expert-social/experts/1/followers').json()['items']==[]
    native(c,'t2');assert c.get('/api/expert-social/experts/2/following').json()['items']==[]


def test_native_following_hides_expert_when_verification_is_revoked(env):
    c,engine=env;native(c,'t2')
    assert c.put('/api/expert-social/experts/1/follow',json={'followed':True}).status_code==200
    with Session(engine) as s:p=s.exec(select(main.ExpertProfile).where(main.ExpertProfile.user_id==1)).one();p.verification_status='REJECTED';s.add(p);s.commit()
    assert c.get('/api/expert-social/experts/2/following').json()['items']==[]
