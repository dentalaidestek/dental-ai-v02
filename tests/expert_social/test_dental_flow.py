"""The member discovery feed reuses published expert posts without leaking drafts."""
import uuid
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, select

from app import main
from app.expert_social_models import SocialFollow, SocialPost
from test_api import env

PREFIX = '/api/expert-social/feed/'


def seed(session, author, *, status='PUBLISHED', text='Bilimsel paylaşım'):
    row = SocialPost(author_id=author, text=text, status=status, idempotency_key=str(uuid.uuid4()), request_hash='synthetic')
    session.add(row)
    session.flush()
    return row


def test_discovery_is_member_only_and_never_includes_pending_owner_posts(env):
    client, engine = env
    with Session(engine) as session:
        first = seed(session, 1)
        second = seed(session, 3)
        for status in ('PENDING', 'REJECTED', 'DELETED'):
            seed(session, 1, status=status)
        expected = [second.id, first.id]
        session.commit()
    response = client.get(PREFIX+'discover')
    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()['items']] == expected
    assert response.headers['cache-control'] == 'private, no-store'
    client.cookies.clear()
    assert client.get(PREFIX+'discover').status_code == 401
    client.cookies.set(main.SESSION_COOKIE, 't2')
    with Session(engine) as session:
        viewer = session.get(main.User, 2)
        viewer.is_active = False
        session.add(viewer)
        session.commit()
    assert client.get(PREFIX+'discover').status_code == 401


@pytest.mark.parametrize('mode', ['discover', 'following'])
def test_specialty_filter_and_follow_scope_are_applied_before_pagination(env, mode):
    client, engine = env
    client.cookies.set(main.SESSION_COOKIE, 't2')
    with Session(engine) as session:
        profile = session.exec(select(main.ExpertProfile).where(main.ExpertProfile.user_id == 3)).one()
        profile.specialty = 'Endodonti'
        session.add(profile)
        session.add(SocialFollow(follower_id=2, expert_id=1))
        first = seed(session, 1)
        second = seed(session, 3)
        ids = first.id, second.id
        session.commit()
    all_items = client.get(PREFIX+mode).json()['items']
    assert {row['id'] for row in all_items} == ({*ids} if mode == 'discover' else {ids[0]})
    filtered = client.get(PREFIX+mode, params={'specialty':'Endodonti'}).json()['items']
    assert [row['id'] for row in filtered] == ([ids[1]] if mode == 'discover' else [])
    assert client.get(PREFIX+mode, params={'specialty':'invented-branch'}).status_code == 422


@pytest.mark.parametrize('blocker,blocked', [(1,2),(2,1)])
def test_discovery_hides_both_block_directions(env, blocker, blocked):
    client, engine = env
    client.cookies.set(main.SESSION_COOKIE, 't2')
    with Session(engine) as session:
        seed(session, 1)
        visible = seed(session, 3).id
        session.add(main.UserBlock(blocker_user_id=blocker, blocked_user_id=blocked))
        session.commit()
    assert [row['id'] for row in client.get(PREFIX+'discover').json()['items']] == [visible]


@pytest.mark.parametrize('revocation', ['inactive','student','unverified','missing_document','missing_phone'])
def test_discovery_rechecks_expert_identity_on_every_read(env, revocation):
    client, engine = env
    client.cookies.set(main.SESSION_COOKIE, 't2')
    with Session(engine) as session:
        seed(session, 1)
        session.commit()
    assert len(client.get(PREFIX+'discover').json()['items']) == 1
    with Session(engine) as session:
        user = session.get(main.User, 1)
        profile = session.exec(select(main.ExpertProfile).where(main.ExpertProfile.user_id == 1)).one()
        if revocation == 'inactive': user.is_active = False
        elif revocation == 'student': user.role = 'STUDENT'
        elif revocation == 'unverified': profile.specialty_verified = False
        elif revocation == 'missing_document': profile.credential_document_path = ''
        else: profile.phone = ''
        session.add(user); session.add(profile); session.commit()
    assert client.get(PREFIX+'discover').json()['items'] == []


def test_discovery_cursors_survive_deleted_boundaries_and_enforce_limits(env):
    client, engine = env
    with Session(engine) as session:
        ids = [seed(session, 1).id for _ in range(35)]
        session.commit()
    first = client.get(PREFIX+'discover').json()
    assert [r['id'] for r in first['items']] == ids[::-1][:15]
    boundary = first['next_cursor']
    with Session(engine) as session:
        session.delete(session.get(SocialPost, boundary)); session.commit()
    second = client.get(PREFIX+'discover', params={'before':boundary,'limit':30}).json()
    assert [r['id'] for r in second['items']] == [ident for ident in ids[::-1] if ident < boundary]
    assert second['next_cursor'] is None
    assert client.get(PREFIX+'discover', params={'limit':31}).status_code == 422


def test_feed_metadata_and_query_count_are_batched(env):
    client, engine = env
    client.cookies.set(main.SESSION_COOKIE, 't2')
    with Session(engine) as session:
        session.add(SocialFollow(follower_id=2, expert_id=1))
        for _ in range(30): seed(session, 1)
        seed(session, 3)
        session.commit()
    counts = []
    for limit in (1,30):
        statements = []
        def count(*args): statements.append(args[2])
        event.listen(engine, 'before_cursor_execute', count)
        try: response = client.get(PREFIX+'discover', params={'limit':limit})
        finally: event.remove(engine, 'before_cursor_execute', count)
        assert response.status_code == 200, response.text
        counts.append(len(statements))
        rows = response.json()['items']
        assert all(row['author_specialty'] == 'Ortodonti' for row in rows)
        assert all(row['author_followed'] == (row['author_id'] == 1) for row in rows)
        assert all(row['author_support_available'] is True for row in rows)
    assert max(counts) <= 18, counts
    assert counts[1] <= counts[0] + 1, counts


def test_feed_support_links_obey_availability_and_self(env):
    client, engine = env
    with Session(engine) as session:
        seed(session, 1)
        session.commit()
    assert client.get(PREFIX+'discover').json()['items'][0]['author_support_available'] is False
    client.cookies.set(main.SESSION_COOKIE, 't2')
    assert client.get(PREFIX+'discover').json()['items'][0]['author_support_available'] is True
    with Session(engine) as session:
        profile = session.exec(select(main.ExpertProfile).where(main.ExpertProfile.user_id == 1)).one()
        profile.availability = 'BUSY'; session.add(profile); session.commit()
    assert client.get(PREFIX+'discover').json()['items'][0]['author_support_available'] is False


@pytest.mark.parametrize('restriction', ['capacity', 'policy'])
def test_feed_support_availability_respects_case_capacity_and_policy(env, restriction):
    client, engine = env
    client.cookies.set(main.SESSION_COOKIE, 't2')
    with Session(engine) as session:
        seed(session, 1)
        if restriction == 'capacity':
            for _ in range(5):
                session.add(main.ConsultationCase(requester_user_id=2, expert_user_id=1, specialty='Ortodonti', clinical_summary='Sentetik', question='Sentetik soru', status='ACTIVE', expert_response_deadline=main._utcnow_naive()+timedelta(minutes=10)))
        else:
            session.add(main.ExpertPolicyState(expert_user_id=1, new_case_blocked_until=main._utcnow_naive()+timedelta(days=1)))
        session.commit()
    rows = client.get(PREFIX+'discover').json()['items']
    assert len(rows) == 1 and rows[0]['author_support_available'] is False


def test_dental_flow_page_and_navigation_keep_filter_and_do_not_fetch_on_home(env):
    client = TestClient(main.app)
    assert client.get('/dental-akis').status_code == 401
    client.cookies.set(main.SESSION_COOKIE, 't2')
    response = client.get('/dental-akis', params={'tab':'following','specialty':'Endodonti'})
    assert response.status_code == 200, response.text
    assert '<h1>Dental Akış</h1>' in response.text
    assert 'data-feed-mode="following"' in response.text
    assert 'data-feed-specialty="Endodonti"' in response.text
    assert 'Keşfet' in response.text and 'Takip Ettiklerim' in response.text
    assert 'tab=discover&amp;specialty=Endodonti' in response.text
    assert client.get('/dental-akis', params={'tab':'bogus'}).status_code == 422
    home = client.get('/').text
    assert 'Dental Akış' in home and 'href="/dental-akis"' in home
    assert 'visual-feature-card visual-flow visual-photo-card' in home
    assert '/static/dashboard/mobile/dental_flow.webp' in home
    assert 'width="768" height="576" loading="lazy"' in home
    assert 'data-expert-social' not in home and 'expert-social.js' not in home
