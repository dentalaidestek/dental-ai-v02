"""Five simultaneous writers against isolated PostgreSQL and a four-slot pool."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlmodel import Session, create_engine, select
from app import main
from app.expert_social_models import SocialPost, SocialMedia
from test_postgres import pg_engine
from test_orcid_postgres import setup_social, client


@pytest.mark.parametrize('scenario', ['five_experts','same_expert','retry','duplicate','five_images'])
def test_five_post_submissions_do_not_deadlock_duplicate_or_mix_media(pg_engine,monkeypatch,scenario):
    engine=create_engine(pg_engine.url,pool_size=4,max_overflow=0,pool_timeout=5)
    try:
        app=setup_social(engine,monkeypatch)
        with Session(engine) as session:
            for ident in range(2,6):
                session.add(main.User(id=ident,username=f'writer{ident}',display_name=f'Sentetik Uzman {ident}',role='DOCTOR',email_verified_at=main._utcnow_naive()))
            session.flush()
            for ident in range(2,6):
                session.add(main.ExpertProfile(user_id=ident,specialty='Ortodonti',application_status='APPROVED',verification_status='VERIFIED',specialty_verified=True,credential_document_path='private/synthetic',phone='05300000000',availability='AVAILABLE'))
                session.add(main.SessionToken(user_id=ident,token_hash=main.hash_session_token(f'writer{ident}'),expires_at=main._utcnow_naive()+main.timedelta(hours=1)))
            media_ids={}
            if scenario=='five_images':
                for ident in range(1,6):
                    media=SocialMedia(owner_id=ident,reference=f'private/synthetic-{ident}.jpg');session.add(media);session.flush();media_ids[ident]=media.id
            session.commit()
        ready=Barrier(5);shared_key=str(uuid.uuid4())
        def submit(index):
            requester=client(app)
            try:
                ident=index+1 if scenario in ('five_experts','five_images') else 1
                if ident!=1:requester.cookies.set(main.SESSION_COOKIE,f'writer{ident}')
                body={'text':'Bilimsel paylaşım '+('ortak' if scenario in ('retry','duplicate') else str(index)),
                      'idempotency_key':shared_key if scenario=='retry' else str(uuid.uuid4())}
                if scenario=='five_images':body['media_ids']=[media_ids[ident]]
                ready.wait(timeout=5)
                return requester.post('/api/expert-social/posts',json=body)
            finally:requester.close()
        with ThreadPoolExecutor(max_workers=5) as workers:
            results=list(workers.map(submit,range(5)))
        statuses=sorted(r.status_code for r in results)
        assert statuses==([200]+[429]*4 if scenario=='duplicate' else [200]*5),[r.text for r in results]
        expected=1 if scenario in ('retry','duplicate') else 5
        assert len({r.json()['id'] for r in results if r.status_code==200})==expected
        with Session(engine) as session:
            posts=session.exec(select(SocialPost)).all();assert len(posts)==expected
            if scenario=='five_images':
                assert all(p.status=='PENDING' for p in posts)
                for media in session.exec(select(SocialMedia)).all():
                    assert session.get(SocialPost,media.post_id).author_id==media.owner_id
        assert engine.pool.checkedout()==0
    finally:engine.dispose()
