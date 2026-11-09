"""Exercise discovery joins, aggregate eligibility and cursors on real PostgreSQL."""
from sqlmodel import Session
from app import main
from app.expert_social_models import SocialFollow
from test_postgres import pg_engine
from test_orcid_postgres import setup_social, client
from test_dental_flow import seed


def test_postgres_discovery_and_enriched_following_share_verified_posts(pg_engine, monkeypatch):
    app = setup_social(pg_engine, monkeypatch)
    main.ConsultationCase.__table__.create(pg_engine, checkfirst=True)
    with Session(pg_engine) as session:
        session.add(main.User(id=2, username='flow-member', role='DOCTOR', display_name='Sentetik Üye', email_verified_at=main._utcnow_naive()))
        session.flush()
        session.add(main.SessionToken(user_id=2, token_hash=main.hash_session_token('flow-token'), expires_at=main._utcnow_naive()+main.timedelta(days=1)))
        session.add(SocialFollow(follower_id=2, expert_id=1))
        for _ in range(3): seed(session, 1)
        seed(session, 1, status='PENDING')
        session.commit()
    requester = client(app)
    requester.cookies.set(main.SESSION_COOKIE, 'flow-token')
    first = requester.get('/api/expert-social/feed/discover', params={'limit':2})
    assert first.status_code == 200, first.text
    rows = first.json()['items']
    assert [row['id'] for row in rows] == [3,2]
    assert all(row['author_followed'] and row['author_support_available'] for row in rows)
    assert requester.get('/api/expert-social/feed/following', params={'details':True, 'specialty':'Ortodonti','limit':2}).json() == first.json()
    second = requester.get('/api/expert-social/feed/discover', params={'before':first.json()['next_cursor']}).json()
    assert [row['id'] for row in second['items']] == [1]
    assert second['next_cursor'] is None
    requester.close()
    assert pg_engine.pool.checkedout() == 0
