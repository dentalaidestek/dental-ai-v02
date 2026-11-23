"""Native social requests share web records without granting web admin MFA."""
from datetime import timedelta
import uuid
import pytest
from sqlmodel import Session, select
from app import main
from app.expert_social_models import SocialAdminStepUpChallenge, SocialAdminStepUpSession
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

@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", "/api/expert-social/moderation", {}),
        ("get", "/api/expert-social/reports", {}),
        ("get", "/api/expert-social/moderation/POST/1", {}),
        ("post", "/api/expert-social/moderation/POST/1", {
            "json": {
                "status": "PUBLISHED",
                "version": 1,
                "reason": "Güvenlik regresyonu",
            },
        }),
    ],
)
def test_native_admin_bearer_cannot_access_any_social_moderation_route(env, method, path, kwargs):
    c, _ = env
    native(c, "t4")
    response = getattr(c, method)(path, **kwargs)
    assert response.status_code == 403, response.text


def test_native_admin_bearer_cannot_reuse_a_verified_browser_cookie(env):
    c, engine = env
    token_hash = main.hash_session_token("t4")
    with Session(engine) as session:
        previous = session.get(main.AdminVerifiedSession, token_hash)
        if previous:
            session.delete(previous)
        admin = session.get(main.User, 4)
        assert admin is not None
        session.add(main.AdminVerifiedSession(token_hash=token_hash, user_id=admin.id))
        session.commit()
    native(c, "t4")
    c.cookies.set(main.SESSION_COOKIE, "t4")
    assert c.get("/api/expert-social/moderation").status_code == 403


def test_web_admin_moderation_still_requires_verified_session(env):
    c, engine = env
    c.headers.pop("Authorization", None)
    c.cookies.clear()
    c.cookies.set(main.SESSION_COOKIE, "t4")
    token_hash = main.hash_session_token("t4")
    with Session(engine) as session:
        previous = session.get(main.AdminVerifiedSession, token_hash)
        if previous:
            session.delete(previous)
        admin = session.get(main.User, 4)
        assert admin is not None
        admin.role = "ADMIN"
        admin.is_active = True
        admin.email = main.ADMIN_FIXED_EMAIL
        admin.email_verified_at = main._utcnow_naive()
        session.add(admin)
        session.commit()
    # get_current_user deliberately treats an admin cookie without a live
    # step-up session as unauthenticated, so the protected route returns 401.
    assert c.get("/api/expert-social/moderation").status_code == 401
    with Session(engine) as session:
        admin = session.get(main.User, 4)
        session.add(main.AdminVerifiedSession(token_hash=token_hash, user_id=admin.id))
        session.commit()
    response = c.get("/api/expert-social/moderation")
    assert response.status_code == 200, response.text

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



def _prepare_native_social_admin(client, engine):
    with Session(engine) as session:
        admin = session.get(main.User, 4)
        assert admin is not None
        admin.role = "ADMIN"
        admin.is_active = True
        admin.email = main.ADMIN_FIXED_EMAIL
        admin.email_verified_at = main._utcnow_naive()
        session.add(admin)
        session_hash = main.hash_session_token("t4")
        challenge = session.get(SocialAdminStepUpChallenge, session_hash)
        if challenge:
            session.delete(challenge)
        for grant in session.exec(
            select(SocialAdminStepUpSession).where(
                SocialAdminStepUpSession.session_hash == session_hash
            )
        ).all():
            session.delete(grant)
        browser = session.get(main.AdminVerifiedSession, session_hash)
        if browser:
            session.delete(browser)
        session.commit()
    native(client, "t4")
    client.headers["X-Dental-Social"] = "1"


def test_native_social_admin_stepup_is_fixed_mailbox_hashed_and_session_scoped(env, monkeypatch):
    client, engine = env
    _prepare_native_social_admin(client, engine)
    delivered = []
    monkeypatch.setattr(
        main,
        "send_email_verification_code",
        lambda recipient, code: delivered.append((recipient, code)),
    )
    begin = client.post("/api/expert-social/admin/step-up")
    assert begin.status_code == 200, begin.text
    assert begin.headers["cache-control"] == "private, no-store"
    assert "Authorization" in begin.headers["vary"]
    assert "X-Dental-Social-Admin-Step-Up" in begin.headers["vary"]
    assert delivered and delivered[0][0] == main.ADMIN_FIXED_EMAIL
    with Session(engine) as session:
        challenge = session.get(
            SocialAdminStepUpChallenge, main.hash_session_token("t4")
        )
        assert challenge is not None
        assert main.verify_password(delivered[0][1], challenge.code_hash)
        assert challenge.code_hash != delivered[0][1]
        assert challenge.attempts == 0
        assert session.get(main.AdminVerifiedSession, main.hash_session_token("t4")) is None

    client.headers.pop("X-Dental-Social-Admin-Step-Up", None)
    verified = client.post(
        "/api/expert-social/admin/step-up/verify",
        json={"code": delivered[0][1]},
    )
    assert verified.status_code == 200, verified.text
    payload = verified.json()
    assert payload["scope"] == "SOCIAL_MODERATION"
    assert payload["expires_in"] == 300
    stepup = payload["token"]
    assert isinstance(stepup, str) and 32 <= len(stepup) <= 256
    assert verified.headers["cache-control"] == "private, no-store"
    assert "Authorization" in verified.headers["vary"]
    assert "X-Dental-Social-Admin-Step-Up" in verified.headers["vary"]

    client.headers["X-Dental-Social-Admin-Step-Up"] = stepup
    assert client.get("/api/expert-social/moderation").status_code == 200

    # A different valid bearer session for the same admin cannot reuse this grant.
    other_token = "t4-other-session"
    with Session(engine) as session:
        session.add(
            main.SessionToken(
                token_hash=main.hash_session_token(other_token),
                user_id=4,
                expires_at=main._utcnow_naive() + timedelta(hours=1),
            )
        )
        session.commit()
    native(client, other_token)
    client.headers["X-Dental-Social-Admin-Step-Up"] = stepup
    assert client.get("/api/expert-social/moderation").status_code == 403

    native(client, "t4")
    client.headers["X-Dental-Social-Admin-Step-Up"] = stepup
    assert client.get("/api/expert-social/moderation").status_code == 200
    revoked = client.post("/api/expert-social/admin/step-up/revoke")
    assert revoked.status_code == 200
    assert revoked.json() == {"ok": True}
    assert client.get("/api/expert-social/moderation").status_code == 403

    replay = client.post(
        "/api/expert-social/admin/step-up/verify",
        json={"code": delivered[0][1]},
    )
    assert replay.status_code == 403


def test_native_social_admin_stepup_cooldown_attempt_limit_and_expiry(env, monkeypatch):
    client, engine = env
    _prepare_native_social_admin(client, engine)
    delivered = []
    monkeypatch.setattr(
        main,
        "send_email_verification_code",
        lambda recipient, code: delivered.append((recipient, code)),
    )
    assert client.post("/api/expert-social/admin/step-up").status_code == 200
    assert client.post("/api/expert-social/admin/step-up").status_code == 429
    wrong_code = "000000" if delivered[0][1] != "000000" else "999999"
    for attempt in range(5):
        response = client.post(
            "/api/expert-social/admin/step-up/verify",
            json={"code": wrong_code},
        )
        assert response.status_code == 401
        if attempt == 0:
            assert response.json()["code"] == "SOCIAL_ADMIN_OTP_INVALID"
    locked = client.post(
        "/api/expert-social/admin/step-up/verify",
        json={"code": delivered[0][1]},
    )
    assert locked.status_code == 403

    # A second independently issued native session can receive a grant.
    other_token = "t4-expiry-session"
    with Session(engine) as session:
        session.add(
            main.SessionToken(
                token_hash=main.hash_session_token(other_token),
                user_id=4,
                expires_at=main._utcnow_naive() + timedelta(hours=1),
            )
        )
        session.commit()
    native(client, other_token)
    assert client.post("/api/expert-social/admin/step-up").status_code == 200
    verified = client.post(
        "/api/expert-social/admin/step-up/verify",
        json={"code": delivered[-1][1]},
    )
    assert verified.status_code == 200, verified.text
    grant_hash = main.hash_session_token(verified.json()["token"])
    with Session(engine) as session:
        grant = session.get(SocialAdminStepUpSession, grant_hash)
        assert grant is not None
        grant.expires_at = main._utcnow_naive() - timedelta(seconds=1)
        session.add(grant)
        session.commit()
    client.headers["X-Dental-Social-Admin-Step-Up"] = verified.json()["token"]
    assert client.get("/api/expert-social/moderation").status_code == 403

def test_native_stepup_issue_prunes_only_bounded_expired_credentials(env, monkeypatch):
    client, engine = env
    _prepare_native_social_admin(client, engine)
    now = main._utcnow_naive()
    with Session(engine) as session:
        for index in range(105):
            session.add(
                SocialAdminStepUpChallenge(
                    session_hash=f"expired-challenge-{index}",
                    user_id=4,
                    code_hash="not-a-live-code",
                    created_at=now - timedelta(minutes=20),
                    expires_at=now - timedelta(minutes=10),
                    attempts=0,
                )
            )
            session.add(
                SocialAdminStepUpSession(
                    token_hash=f"expired-grant-{index}",
                    user_id=4,
                    session_hash=f"old-session-{index}",
                    scope="SOCIAL_MODERATION",
                    expires_at=now - timedelta(minutes=5),
                    created_at=now - timedelta(minutes=6),
                )
            )
        session.add(
            SocialAdminStepUpChallenge(
                session_hash="still-live-challenge",
                user_id=4,
                code_hash="keep",
                created_at=now,
                expires_at=now + timedelta(minutes=5),
                attempts=0,
            )
        )
        session.add(
            SocialAdminStepUpSession(
                token_hash="still-live-grant",
                user_id=4,
                session_hash="other-live-session",
                scope="SOCIAL_MODERATION",
                expires_at=now + timedelta(minutes=2),
                created_at=now,
            )
        )
        session.commit()

    monkeypatch.setattr(main, "send_email_verification_code", lambda *_: None)
    response = client.post("/api/expert-social/admin/step-up")
    assert response.status_code == 200, response.text
    with Session(engine) as session:
        expired_challenges = session.exec(
            select(SocialAdminStepUpChallenge).where(
                SocialAdminStepUpChallenge.expires_at <= main._utcnow_naive()
            )
        ).all()
        expired_grants = session.exec(
            select(SocialAdminStepUpSession).where(
                SocialAdminStepUpSession.expires_at <= main._utcnow_naive()
            )
        ).all()
        assert len(expired_challenges) == 5
        assert len(expired_grants) == 5
        assert session.get(SocialAdminStepUpChallenge, "still-live-challenge") is not None
        assert session.get(SocialAdminStepUpSession, "still-live-grant") is not None

