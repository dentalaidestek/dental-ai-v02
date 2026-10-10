"""Real PostgreSQL locking tests; set DENTAL_TEST_DATABASE_URL to a disposable DB."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
import uuid

import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select
from app import main, work_jobs, provider_budget


@pytest.fixture
def pg(monkeypatch):
    url = os.getenv('DENTAL_TEST_DATABASE_URL')
    if not url:
        pytest.skip('DENTAL_TEST_DATABASE_URL is required for PostgreSQL integration')
    admin = create_engine(url)
    schema = 'dental_test_' + uuid.uuid4().hex
    with admin.begin() as c:
        c.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'}, pool_size=6, max_overflow=0)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(provider_budget, '_engine', lambda: engine)
    with Session(engine, expire_on_commit=False) as s:
        owner = main.User(username='synthetic', role='DOCTOR', display_name='Synthetic')
        s.add(owner); s.commit()
        resources = [main.GuestAnalysis(owner_user_id=owner.id) for _ in range(4)]
        s.add_all(resources); s.commit()
        for resource in resources:
            work_jobs.enqueue(s, kind='PRELIMINARY', resource_type='GUEST', resource_id=resource.id)
        s.commit()
    yield engine, schema, resources
    engine.dispose()
    with admin.begin() as c:
        c.execute(text(f'DROP SCHEMA {schema} CASCADE'))
    admin.dispose()


def test_concurrent_claims_and_recovery(pg):
    engine, _, _ = pg
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = list(executor.map(lambda _: work_jobs.claim(engine), range(4)))
    assert len({job.id for job in jobs if job}) == 4
    assert work_jobs.claim(engine) is None
    old = jobs[0]
    with engine.begin() as c:
        c.execute(text('UPDATE workjob SET lease_until=:past WHERE id=:id'), {'past':work_jobs.now()-timedelta(seconds=1), 'id':old.id})
    replacement = work_jobs.claim(engine)
    assert replacement.id == old.id and replacement.lease_token != old.lease_token
    work_jobs.finish(engine, old, status='DONE')
    with Session(engine) as s:
        assert s.get(work_jobs.WorkJob, old.id).status == 'RUNNING'


def test_provider_admission_shared_across_processes(pg):
    import multiprocessing
    engine, _, _ = pg
    context = multiprocessing.get_context('fork')
    queue = context.Queue()
    def attempt():
        # The child must not reuse its parent's live sockets.
        engine.dispose(close=False)
        try:
            with provider_budget.reservation('gemini', 'test', capacity=1):
                queue.put('admitted')
        except provider_budget.ProviderBusy:
            queue.put('busy')
    with provider_budget.reservation('gemini', 'test', capacity=1):
        process = context.Process(target=attempt)
        process.start(); process.join(10)
        assert process.exitcode == 0
        assert queue.get(timeout=2) == 'busy'
    assert engine.pool.checkedout() == 0


def test_listener_real_notify_and_graceful_close(pg):
    from app.realtime_io import PostgresNotices
    engine, _, _ = pg
    channel = 'dental_test_' + uuid.uuid4().hex
    async def run():
        listener = PostgresNotices(engine.url.set(drivername='postgresql').render_as_string(hide_password=False), [channel])
        listener.start()
        try:
            assert None in await asyncio.wait_for(listener.batch(), 8)
            def notify():
                with engine.begin() as c:
                    c.execute(text('SELECT pg_notify(:channel, :payload)'), {'channel': channel, 'payload': '42'})
            await asyncio.to_thread(notify)
            assert (channel, '42') in await asyncio.wait_for(listener.batch(), 5)
        finally:
            await listener.close()
        assert not listener.thread.is_alive()
    asyncio.run(run())


def test_migration_repeat_and_old_result_paths(pg, monkeypatch):
    from app import migrate
    engine, _, resources = pg
    # Simulate the pre-migration tables while preserving an existing analysis.
    with engine.begin() as c:
        c.execute(text('ALTER TABLE analysis DROP COLUMN result_path'))
        c.execute(text('ALTER TABLE guestanalysis DROP COLUMN result_path'))
    monkeypatch.setattr(main, '_backfill_legacy_deadline_jobs_if_needed', lambda: None)
    monkeypatch.setattr(main, '_backfill_program_reminder_jobs', lambda: None)
    migrate.apply()
    migrate.apply()
    migrate.require_schema(engine)
    with Session(engine) as s:
        assert s.get(main.GuestAnalysis, resources[0].id).result_path is None


def test_authentication_admission_is_atomic_on_postgres(pg):
    from app.auth_rate import admit, bucket_key, clear
    from fastapi import HTTPException
    engine, _, _ = pg
    def attempt(_):
        try:
            admit(engine, 'login', 'synthetic-auth-user', limit=8, window=600)
            return 200
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(attempt, range(24)))
    assert statuses.count(200) == 8
    assert statuses.count(429) == 16
    key = bucket_key('login', 'synthetic-auth-user')
    with engine.connect() as conn:
        row = conn.execute(text('SELECT attempts FROM authratebucket WHERE bucket_key=:key'), {'key': key}).one()
        assert row.attempts == 24
    clear(engine, key)
    admit(engine, 'login', 'synthetic-auth-user', limit=8, window=600)


def test_release_migration_preserves_existing_records_and_repeats_on_postgres(pg):
    from app import migrate
    engine, _, resources = pg
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'))
        connection.execute(text('INSERT INTO dental_schema_revision VALUES (1,8)'))
        before = connection.execute(text('SELECT id, username, display_name, role FROM "user" ORDER BY id')).all()
    migrate.apply()
    migrate.require_schema(engine)
    migrate.apply()
    migrate.require_schema(engine)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT id, username, display_name, role FROM "user" ORDER BY id')).all() == before
        assert set(connection.execute(text('SELECT id FROM guestanalysis')).scalars()) == {resource.id for resource in resources}
        assert connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar_one() == 12
        assert connection.execute(text("SELECT to_regclass('authratebucket')")).scalar_one() is not None
        assert connection.execute(text("SELECT to_regclass('emailchangechallenge')")).scalar_one() is not None


def test_email_change_code_is_consumed_once_under_concurrent_confirmation(pg, monkeypatch):
    from starlette.requests import Request
    engine, _, resources = pg
    uid = resources[0].owner_user_id
    with Session(engine) as s:
        user = s.get(main.User, uid)
        user.email = 'old@example.test'
        user.email_verified_at = main._utcnow_naive()
        user.password_hash = 'synthetic-password-verifier'
        s.add(user)
        s.add(main.SessionToken(user_id=uid, token_hash=main.hash_session_token('email-token'), expires_at=main._utcnow_naive() + timedelta(days=1)))
        s.add(main.EmailChangeChallenge(user_id=uid, new_email='new@example.test', old_email=user.email,
            password_snapshot=main.hash_session_token(user.password_hash), session_hash=main.hash_session_token('email-token'),
            code_hash=main.hash_session_token('123456'), expires_at=main._utcnow_naive() + timedelta(minutes=10)))
        s.commit()
    monkeypatch.setattr(main, 'on_loop', lambda *args: None)
    def confirm(_):
        request = Request({'type': 'http', 'method': 'POST', 'path': '/account/email/confirm',
            'scheme': 'https', 'headers': [(b'cookie', f'{main.SESSION_COOKIE}=email-token'.encode())]})
        return main.confirm_email_change.__wrapped__(request, '123456').headers.get('location')
    with ThreadPoolExecutor(max_workers=2) as pool:
        locations = list(pool.map(confirm, range(2)))
    assert locations.count('/login?email_changed=1') == 1
    assert locations.count('/login') == 1
    with Session(engine) as s:
        assert s.get(main.User, uid).email == 'new@example.test'
        assert s.get(main.EmailChangeChallenge, uid) is None
        assert not s.exec(select(main.SessionToken).where(main.SessionToken.user_id == uid)).all()


def test_completed_chat_purge_is_idempotent_under_concurrent_workers(pg):
    engine, _, _ = pg
    now = main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as s:
        case = main.ConsultationCase(requester_user_id=1, expert_user_id=2, specialty='Endodonti', clinical_summary='Synthetic', question='Synthetic', status='COMPLETED', completed_at=now-timedelta(days=7), expert_response_deadline=now)
        s.add(case); s.flush()
        s.add(main.ConsultationMessage(case_id=case.id, sender_user_id=1, content='Synthetic retention check'))
        main._enqueue_chat_retention(s, case); s.commit()
        job_id=s.exec(select(main.ConsultationDeadlineJob.id).where(main.ConsultationDeadlineJob.case_id==case.id,main.ConsultationDeadlineJob.job_type=='CHAT_PURGE')).one()
        case_id=case.id
    def purge(_):
        with Session(engine) as s:
            job=s.get(main.ConsultationDeadlineJob,job_id)
            _,events=main._process_deadline_job(s,job,now)
            s.commit()
            return len(events)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(purge, range(2)))
    assert sorted(results)==[0,2]
    with Session(engine) as s:
        assert s.get(main.ConsultationCase,case_id).messages_deleted_at
        assert not s.exec(select(main.ConsultationMessage).where(main.ConsultationMessage.case_id==case_id)).all()


def test_report_transaction_serializes_with_chat_purge(pg):
    from threading import Event
    engine, _, _ = pg
    now=main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as s:
        case=main.ConsultationCase(requester_user_id=1,expert_user_id=2,specialty='Endodonti',clinical_summary='Synthetic',question='Synthetic',status='COMPLETED',completed_at=now-timedelta(days=7),expert_response_deadline=now)
        s.add(case);s.flush();case_id=case.id
        s.add(main.ConsultationMessage(case_id=case_id,sender_user_id=1,content='Preserve this evidence'))
        main._enqueue_chat_retention(s,case);s.commit()
        job_id=s.exec(select(main.ConsultationDeadlineJob.id).where(main.ConsultationDeadlineJob.case_id==case_id)).one()
    started=Event()
    def purge():
        with Session(engine) as s:
            job=s.get(main.ConsultationDeadlineJob,job_id);started.set()
            result=main._process_deadline_job(s,job,now);s.commit();return result
    with ThreadPoolExecutor(max_workers=1) as executor:
        with Session(engine) as s:
            main._locked_consultation_case(s,case_id)
            future=executor.submit(purge)
            assert started.wait(5)
            s.add(main.UserReport(reporter_user_id=1,reported_user_id=2,case_id=case_id,reason='OTHER',status='CLOSED'))
            s.commit()
        assert future.result(timeout=10)==([],[])
    with Session(engine) as s:
        assert not s.get(main.ConsultationCase,case_id).messages_deleted_at
        assert s.exec(select(main.ConsultationMessage).where(main.ConsultationMessage.case_id==case_id)).one().content=='Preserve this evidence'


def test_retention_migration_preserves_old_messages_and_grants_grace(pg):
    from app import migrate
    engine,_,_=pg;before=main._utcnow_naive()
    with Session(engine,expire_on_commit=False) as s:
        case=main.ConsultationCase(requester_user_id=1,expert_user_id=2,specialty='Endodonti',clinical_summary='Old conversation',question='Question',status='COMPLETED',completed_at=before-timedelta(days=30),expert_response_deadline=before-timedelta(days=31))
        s.add(case);s.flush();case_id=case.id
        s.add(main.ConsultationMessage(case_id=case_id,sender_user_id=1,content='Pre-policy evidence'));s.commit()
    with engine.begin() as c:
        c.execute(text('ALTER TABLE consultationcase DROP COLUMN messages_deleted_at'))
        c.execute(text('ALTER TABLE consultationcase DROP COLUMN chat_retention_started_at'))
        c.execute(text('DROP TABLE consultationmediadeletion'))
    migrate.apply();migrate.require_schema(engine)
    with Session(engine) as s:
        anchor=s.get(main.ConsultationCase,case_id).chat_retention_started_at
        assert anchor>=before
        assert s.exec(select(main.ConsultationMessage).where(main.ConsultationMessage.case_id==case_id)).one().content=='Pre-policy evidence'
        job=s.exec(select(main.ConsultationDeadlineJob).where(main.ConsultationDeadlineJob.case_id==case_id,main.ConsultationDeadlineJob.job_type=='CHAT_PURGE')).one()
        assert job.run_at==anchor+timedelta(days=7)
    migrate.apply()
    with Session(engine) as s:
        assert s.get(main.ConsultationCase,case_id).chat_retention_started_at==anchor
        assert len(s.exec(select(main.ConsultationDeadlineJob).where(main.ConsultationDeadlineJob.case_id==case_id,main.ConsultationDeadlineJob.job_type=='CHAT_PURGE')).all())==1


def test_membership_concurrent_submissions_and_reviews(pg, monkeypatch, tmp_path):
    import io
    from PIL import Image
    from fastapi.testclient import TestClient
    from app.membership_verification import MembershipVerification
    engine, _, resources = pg
    with Session(engine, expire_on_commit=False) as s:
        owner=s.get(main.User,resources[0].owner_user_id)
        admin=main.User(username='member-admin',role='ADMIN',display_name='Admin')
        s.add(admin); s.commit()
    monkeypatch.setattr(main,'get_current_user',lambda request: admin if request.headers.get('x-user')=='admin' else owner)
    monkeypatch.setattr(main,'on_loop',lambda *a,**kw:None)
    monkeypatch.setattr(main,'UPLOAD_DIR',tmp_path)
    # Both external writes finish before either DB transaction: force the race.
    import threading
    barrier=threading.Barrier(2)
    def write(path,data,**kw):
        path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
        barrier.wait(timeout=10)
        return str(path)
    monkeypatch.setattr(main,'storage_write_bytes',write)
    monkeypatch.setattr(main,'storage_delete',lambda path:__import__('pathlib').Path(path).unlink(missing_ok=True))
    buf=io.BytesIO();Image.new('RGB',(12,12)).save(buf,format='PNG')
    # Avoid TestClient context: lifespan may backfill unrelated jobs during races.
    def submit(_):
        client=TestClient(main.app)
        return client.post('/account/verification',data={'document_type':'DIPLOMA','consent':'yes'},files={'document':('doc.png',buf.getvalue(),'image/png')},follow_redirects=False).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(submit,range(2)))
    assert sorted(results)==[303,409]
    with Session(engine) as s:
        rows=s.exec(select(MembershipVerification)).all()
        assert len(rows)==1
        verification_id=rows[0].id
    assert len(list(tmp_path.rglob('*.png')))==1
    def review(_):
        return TestClient(main.app).post(f'/admin/member-verifications/{verification_id}',headers={'x-user':'admin'},data={'decision':'APPROVE','identity_checked':'yes'},follow_redirects=False).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(review,range(2)))
    assert sorted(results)==[303,409]
    with Session(engine) as s:
        assert len(s.exec(select(main.AdminAuditLog).where(main.AdminAuditLog.action=='MEMBERSHIP_VERIFIED')).all())==1


def test_membership_migration_creates_private_table(pg, monkeypatch):
    from app import migrate
    engine,_,_=pg
    with engine.begin() as c:
        c.execute(text('DROP TABLE membershipverification'))
    monkeypatch.setattr(main,'_backfill_legacy_deadline_jobs_if_needed',lambda:None)
    monkeypatch.setattr(main,'_backfill_program_reminder_jobs',lambda:None)
    migrate.apply();migrate.apply();migrate.require_schema(engine)
    with engine.connect() as c:
        assert c.execute(text("SELECT to_regclass('membershipverification')")).scalar()


def test_profile_document_replacements_serialize_without_duplicate_review(pg, monkeypatch, tmp_path):
    import io
    import threading
    from PIL import Image
    from fastapi.testclient import TestClient
    engine,_,resources=pg
    with Session(engine,expire_on_commit=False) as s:
        owner=s.get(main.User,resources[0].owner_user_id)
        s.add(main.UserAccountMeta(user_id=owner.id,professional_title='Uzman Diş Hekimi'))
        profile=main.ExpertProfile(user_id=owner.id,specialty='Endodonti',phone='05000000000',credential_document_path='old.pdf',application_status='APPROVED',verification_status='VERIFIED',specialty_verified=True,availability='AVAILABLE',consultation_price=200,bio='Preserve biography')
        s.add(profile);s.commit();profile_id=profile.id
    monkeypatch.setattr(main,'get_current_user',lambda request:owner)
    monkeypatch.setattr(main,'on_loop',lambda *a,**kw:None)
    monkeypatch.setattr(main,'UPLOAD_DIR',tmp_path)
    barrier=threading.Barrier(2)
    def write(path,data,**kwargs):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        barrier.wait(timeout=10)
        return str(path)
    monkeypatch.setattr(main,'storage_write_bytes',write)
    monkeypatch.setattr(main,'storage_delete',lambda path:__import__('pathlib').Path(path).unlink(missing_ok=True))
    buf=io.BytesIO();Image.new('RGB',(12,12)).save(buf,format='PNG')
    def upload(_):
        return TestClient(main.app).post('/account/documents/expert',files={'credential_document':('replacement.png',buf.getvalue(),'image/png')},follow_redirects=False).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(upload,range(2)))==[303,409]
    assert len(list(tmp_path.rglob('*.png')))==1
    with Session(engine) as s:
        profile=s.get(main.ExpertProfile,profile_id)
        assert profile.application_status=='SUBMITTED' and profile.availability=='PASSIVE'
        assert profile.bio=='Preserve biography' and profile.specialty=='Endodonti'
