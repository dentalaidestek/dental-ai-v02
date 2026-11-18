"""Real PostgreSQL locking tests; set DENTAL_TEST_DATABASE_URL to a disposable DB."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import os
import uuid

import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select
from app import main, work_jobs, provider_budget, mobile_api


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
        assert connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar_one() == 19
        assert connection.execute(text("SELECT to_regclass('uq_scheduleevent_owner_client_request')")).scalar_one() is not None
        assert connection.execute(text("SELECT to_regclass('consultationmessagereceipt')")).scalar_one() is not None
        assert connection.execute(text("SELECT to_regclass('authratebucket')")).scalar_one() is not None
        assert connection.execute(text("SELECT to_regclass('emailchangechallenge')")).scalar_one() is not None



def test_program_idempotency_migration_upgrades_revision14_without_baseline_replay(pg):
    from app import migrate
    engine, _, _ = pg
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'))
        connection.execute(text('INSERT INTO dental_schema_revision VALUES (1,14)'))
        connection.execute(text('DROP INDEX IF EXISTS uq_scheduleevent_owner_client_request'))
        connection.execute(text('ALTER TABLE scheduleevent DROP COLUMN client_request_hash'))
        connection.execute(text('ALTER TABLE scheduleevent DROP COLUMN client_payload_hash'))
    migrate.apply()
    migrate.require_schema(engine)
    with engine.connect() as connection:
        columns={row.column_name for row in connection.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='scheduleevent'"
        ))}
        assert {'client_request_hash','client_payload_hash'} <= columns
        assert connection.execute(text("SELECT to_regclass('uq_scheduleevent_owner_client_request')")).scalar_one() is not None
        assert connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar_one() == 19


def test_program_create_receipt_is_atomic_under_concurrent_postgres_requests(pg, monkeypatch):
    engine, _, resources = pg
    owner_id=resources[0].owner_user_id
    with Session(engine) as session:
        owner=session.get(main.User,owner_id)
    monkeypatch.setattr(mobile_api,'engine',engine)
    monkeypatch.setattr(mobile_api,'on_loop',lambda *args:None)
    monkeypatch.setattr(main,'_wake_program_reminder_worker',lambda:None)
    payload=mobile_api.MobileScheduleCreate(
        event_type='APPOINTMENT',title='Synthetic concurrent appointment',
        start_at='2030-01-07T10:00',end_at='2030-01-07T10:30',
        patient_id=None,reminder_minutes=30,notification_enabled=True,
        recurrence_rule='NONE',request_key='program-postgres-concurrency-0001',
    )
    def create(_):
        return mobile_api.mobile_create_schedule(payload,owner)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(create,range(2)))
    assert results[0]['event']['id']==results[1]['event']['id']
    assert sorted(result['replayed'] for result in results)==[False,True]
    event_id=results[0]['event']['id']
    with Session(engine) as session:
        events=session.exec(select(main.ScheduleEvent).where(
            main.ScheduleEvent.owner_user_id==owner_id,
            main.ScheduleEvent.client_request_hash!=None,
        )).all()
        reminders=session.exec(select(main.ProgramReminderJob).where(
            main.ProgramReminderJob.schedule_event_id==event_id
        )).all()
        assert len(events)==1
        assert len(reminders)==1



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


def test_recent_release_migration_avoids_legacy_session_lock(pg, monkeypatch):
    from app import migrate
    engine, _, _ = pg
    with engine.begin() as c:
        c.execute(text('CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'))
        c.execute(text('INSERT INTO dental_schema_revision VALUES (1, 10)'))
        c.execute(text('DROP TABLE membershipverification'))
        c.execute(text('DROP TABLE consultationmediadeletion'))
        c.execute(text('ALTER TABLE consultationcase DROP COLUMN messages_deleted_at'))
        c.execute(text('ALTER TABLE consultationcase DROP COLUMN chat_retention_started_at'))
    def forbidden():
        raise AssertionError('Recent release must not replay baseline DDL')
    monkeypatch.setattr(main, 'init_db', forbidden)
    # Model a stranded session lock behind a transaction-pooling proxy.
    with engine.connect() as legacy:
        legacy.execute(text('SELECT pg_advisory_lock(71048232)'))
        try:
            migrate.apply()
            migrate.apply()
            migrate.require_schema(engine)
        finally:
            legacy.execute(text('SELECT pg_advisory_unlock(71048232)'))
    with engine.connect() as c:
        assert c.execute(text("SELECT to_regclass('membershipverification')")).scalar()
        assert c.execute(text("SELECT to_regclass('consultationmediadeletion')")).scalar()
        cols = {row[0] for row in c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='consultationcase'"))}
        assert {'messages_deleted_at', 'chat_retention_started_at'} <= cols

def test_consultation_receipt_revision_13_upgrade_on_postgres(pg):
    from app import migrate
    engine, _, _ = pg
    with engine.begin() as connection:
        connection.execute(text('DROP TABLE IF EXISTS consultationmessagereceipt'))
        connection.execute(text('CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'))
        connection.execute(text('INSERT INTO dental_schema_revision VALUES (1,13)'))
    migrate.apply()
    migrate.require_schema(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('consultationmessagereceipt')")).scalar_one() is not None
        assert connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar_one() == 19
        assert connection.execute(text("SELECT to_regclass('uq_scheduleevent_owner_client_request')")).scalar_one() is not None


def test_consultation_receipt_revision_12_creates_both_receipt_tables(pg):
    from app import migrate, mobile_api
    engine, _, _ = pg
    with engine.begin() as connection:
        connection.execute(text('DROP TABLE IF EXISTS consultationmessagereceipt'))
        connection.execute(text('DROP TABLE IF EXISTS studyrun, studyattempt, studyreview, studylearningstate CASCADE'))
        mobile_api.MobileSupportMutationReceipt.__table__.drop(connection, checkfirst=True)
        connection.execute(text('CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'))
        connection.execute(text('INSERT INTO dental_schema_revision VALUES (1,12)'))
    migrate.apply()
    migrate.require_schema(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('consultationmessagereceipt')")).scalar_one() is not None
        assert connection.execute(text("SELECT to_regclass('mobilesupportmutationreceipt')")).scalar_one() is not None
        # The study tables are additive revision-12 objects. The receipt upgrade
        # advances through revisions 14 and 15 to the current revision 19, so they must be created before those bumps.
        for table in ('studylearningstate', 'studyreview', 'studyattempt', 'studyrun'):
            assert connection.execute(text("SELECT to_regclass(:name)"), {'name': table}).scalar_one() is not None
        assert connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar_one() == 19

def test_consultation_message_same_key_replays_once_under_concurrent_postgres_writes(pg, monkeypatch):
    from fastapi.testclient import TestClient
    from app import mobile_api

    engine, _, resources = pg
    monkeypatch.setattr(mobile_api, 'engine', engine)
    requester_id = resources[0].owner_user_id
    now = main._utcnow_naive()
    requester_token = 'pg-consultation-requester-' + uuid.uuid4().hex
    expert_token = 'pg-consultation-expert-' + uuid.uuid4().hex
    with Session(engine, expire_on_commit=False) as session:
        requester = session.get(main.User, requester_id)
        requester.email_verified_at = now
        requester.is_active = True
        session.add(requester)
        expert = main.User(username='pg-expert-' + uuid.uuid4().hex, role='DOCTOR',
                           display_name='Synthetic expert', is_active=True, email_verified_at=now)
        session.add(expert)
        session.flush()
        session.add_all([
            main.SessionToken(user_id=requester_id, token_hash=main.hash_session_token(requester_token),
                              expires_at=now + timedelta(days=1)),
            main.SessionToken(user_id=expert.id, token_hash=main.hash_session_token(expert_token),
                              expires_at=now + timedelta(days=1)),
        ])
        case = main.ConsultationCase(
            requester_user_id=requester_id, expert_user_id=expert.id, specialty='Endodonti',
            clinical_summary='Synthetic clinical summary', question='Synthetic question',
            status='ACTIVE', expert_response_deadline=now + timedelta(hours=1),
        )
        session.add(case)
        session.commit()
        case_id = case.id

    key = 'pg-consultation-same-key-' + uuid.uuid4().hex
    body = {'content': 'Synthetic same-key message', 'client_message_id': key}

    def submit(_):
        client = TestClient(main.app)
        response = client.post(
            f'/api/mobile/v1/consultations/{case_id}/messages',
            headers={'Authorization': 'Bearer ' + requester_token},
            json=body,
        )
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert [status for status, _ in results] == [200, 200]
    message_ids = {payload['message']['id'] for _, payload in results}
    assert len(message_ids) == 1
    assert sorted(bool(payload.get('replayed')) for _, payload in results) == [False, True]

    conflict_client = TestClient(main.app)
    conflict = conflict_client.post(
        f'/api/mobile/v1/consultations/{case_id}/messages',
        headers={'Authorization': 'Bearer ' + requester_token},
        json={'content': 'Different payload', 'client_message_id': key},
    )
    assert conflict.status_code == 409
    with Session(engine) as session:
        messages = session.exec(select(main.ConsultationMessage).where(
            main.ConsultationMessage.case_id == case_id,
            main.ConsultationMessage.sender_user_id == requester_id,
        )).all()
        receipts = session.exec(select(main.ConsultationMessageReceipt).where(
            main.ConsultationMessageReceipt.case_id == case_id,
            main.ConsultationMessageReceipt.sender_user_id == requester_id,
            main.ConsultationMessageReceipt.client_message_id == key,
        )).all()
    assert len(messages) == 1
    assert len(receipts) == 1


def test_mobile_push_reservation_is_idempotent_under_concurrent_postgres_workers(pg):
    from app.mobile_push_receipts import reserve_mobile_push_deliveries
    from threading import Barrier

    engine, _, resources = pg
    user_id = resources[0].owner_user_id
    device_id = str(uuid.uuid4())
    token = "ExpoPushToken[postgresdevice123456]"
    with Session(engine) as session:
        session.add(main.MobilePushDevice(
            user_id=user_id, device_id=device_id, expo_push_token=token,
            platform="android", enabled=True,
        ))
        session.commit()

    candidate = main.MobilePushDevice(
        user_id=user_id, device_id=device_id, expo_push_token=token,
        platform="android", enabled=True,
    )
    barrier = Barrier(2)

    def reserve(_):
        barrier.wait(timeout=5)
        return reserve_mobile_push_deliveries(
            engine, event_id=93001, user_id=user_id, devices=[candidate],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, range(2)))

    assert sum(len(result) for result in results) == 1
    with Session(engine) as session:
        rows = session.exec(select(main.MobilePushDelivery).where(
            main.MobilePushDelivery.event_id == 93001,
            main.MobilePushDelivery.device_id == device_id,
        )).all()
    assert len(rows) == 1
    assert rows[0].user_id == user_id
    assert rows[0].token_fingerprint
    assert rows[0].status == "SENDING"


def test_mobile_push_receipt_claim_uses_postgres_skip_locked(pg, monkeypatch):
    from threading import Event
    import app.mobile_push_receipts as receipts

    engine, _, resources = pg
    user_id = resources[0].owner_user_id
    device_id = str(uuid.uuid4())
    ticket_id = str(uuid.uuid4())
    stamp = main._utcnow_naive()
    with Session(engine) as session:
        session.add(main.MobilePushDelivery(
            event_id=93002, user_id=user_id, device_id=device_id,
            token_fingerprint="f" * 64, ticket_id=ticket_id,
            status="PENDING_RECEIPT", attempts=0,
            next_check_at=stamp - timedelta(minutes=1),
            created_at=stamp - timedelta(minutes=20),
            updated_at=stamp - timedelta(minutes=1),
        ))
        session.commit()

    locked = Event()
    release = Event()
    original_token_hex = receipts.secrets.token_hex

    def pause_after_row_lock(length):
        locked.set()
        if not release.wait(timeout=8):
            raise TimeoutError("test did not release the first receipt claimant")
        return original_token_hex(length)

    monkeypatch.setattr(receipts.secrets, "token_hex", pause_after_row_lock)
    monkeypatch.setattr(receipts, "get_push_receipts", lambda ids: {
        "ok": True, "receipts": {ticket_id: {"status": "ok"}},
    })

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(receipts.poll_due_mobile_push_receipts, engine)
        assert locked.wait(timeout=5)
        second = executor.submit(receipts.poll_due_mobile_push_receipts, engine)
        try:
            # The second worker must skip the row lock rather than wait for the
            # first worker's provider round-trip and then race to claim it.
            assert second.result(timeout=2) == 0
        finally:
            release.set()
        assert first.result(timeout=8) == 1

    with Session(engine) as session:
        row = session.exec(select(main.MobilePushDelivery).where(
            main.MobilePushDelivery.event_id == 93002,
        )).one()
    assert row.status == "PROVIDER_ACCEPTED"
    assert row.attempts == 1
    assert row.lease_token is None and row.lease_until is None


def test_mobile_push_installation_advisory_lock_serializes_account_switches(pg):
    """Two accounts claiming one SecureStore installation cannot race each other."""
    from threading import Event
    from app.mobile_api import _lock_mobile_push_device_identity

    engine, _, _ = pg
    device_id = str(uuid.uuid4())
    first_locked = Event()
    second_started = Event()
    second_locked = Event()
    release_first = Event()

    def first_claim():
        with Session(engine) as session:
            _lock_mobile_push_device_identity(session, device_id)
            first_locked.set()
            if not release_first.wait(timeout=5):
                raise AssertionError("first installation claim was not released")
            session.commit()

    def second_claim():
        if not first_locked.wait(timeout=5):
            raise AssertionError("first installation claim did not acquire its lock")
        second_started.set()
        with Session(engine) as session:
            _lock_mobile_push_device_identity(session, device_id)
            second_locked.set()
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_claim)
        assert first_locked.wait(timeout=5)
        second = executor.submit(second_claim)
        assert second_started.wait(timeout=5)
        assert not second_locked.wait(timeout=0.2)
        release_first.set()
        first.result(timeout=5)
        second.result(timeout=5)

    assert second_locked.is_set()


def test_program_query_index_migration_upgrades_revision15_online(pg):
    from app import migrate
    engine, _, _ = pg
    index_names = (
        'ix_scheduleevent_owner_start_at',
        'ix_scheduleevent_owner_created_at',
        'ix_scheduleevent_owner_updated_at',
        'ix_programreminderjob_status_run_at',
        'ix_programreminderjob_event_status',
        'ix_programreminderjob_owner_status',
        'ix_treatment_patient_created_id',
    )
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE IF NOT EXISTS dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'))
        connection.execute(text('INSERT INTO dental_schema_revision VALUES (1,15) ON CONFLICT(id) DO UPDATE SET version=15'))
        for name in index_names:
            connection.execute(text(f'DROP INDEX IF EXISTS {name}'))
    migrate.apply()
    migrate.require_schema(engine)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar_one() == 19
        for name in index_names:
            assert connection.execute(
                text('SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(:name)'),
                {'name': name},
            ).scalar_one() is True


def _explain_analyze_index_names(connection, statement, params=None):
    result = connection.execute(
        text('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + statement),
        params or {},
    ).scalar_one()
    if isinstance(result, str):
        result = json.loads(result)
    root = result[0]['Plan'] if isinstance(result, list) else result['Plan']
    names = set()
    pending = [root]
    while pending:
        node = pending.pop()
        if node.get('Index Name'):
            names.add(node['Index Name'])
        pending.extend(node.get('Plans') or [])
    return names


def test_program_hot_queries_use_owner_and_due_queue_indexes_at_scale(pg):
    engine, _, _ = pg
    # Synthetic only: 60k distinct accounts plus a deliberately busy account
    # with enough history to make owner-scoped index selection measurable.
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        connection.execute(text("""
            INSERT INTO scheduleevent
                (owner_user_id,event_type,title,start_at,end_at,patient_id,location,notes,
                 status,reminder_minutes,notification_enabled,recurrence_rule,recurrence_until,
                 timezone_name,created_at,updated_at,client_request_hash,client_payload_hash)
            SELECT 100000 + n,'APPOINTMENT','Synthetic scale event',
                   date_trunc('day',timezone('UTC',now())) + ((n % 28) * interval '1 day'),
                   NULL,NULL,NULL,NULL,'ACTIVE',30,true,'NONE',NULL,'Europe/Istanbul',
                   now() - interval '30 days',now() - interval '30 days',NULL,NULL
            FROM generate_series(1,60000) AS n
        """))
        connection.execute(text("""
            INSERT INTO scheduleevent
                (owner_user_id,event_type,title,start_at,end_at,patient_id,location,notes,
                 status,reminder_minutes,notification_enabled,recurrence_rule,recurrence_until,
                 timezone_name,created_at,updated_at,client_request_hash,client_payload_hash)
            SELECT 42,'APPOINTMENT','Synthetic busy-account event',
                   date_trunc('day',timezone('UTC',now())) + ((n % 28) * interval '1 day'),
                   NULL,NULL,NULL,NULL,'ACTIVE',30,true,'NONE',NULL,'Europe/Istanbul',
                   now() - interval '30 days',
                   CASE WHEN n=2000 THEN now() + interval '1 second' ELSE now() - interval '30 days' END,
                   NULL,NULL
            FROM generate_series(1,2000) AS n
        """))
        connection.execute(text("""
            INSERT INTO programreminderjob
                (schedule_event_id,owner_user_id,occurrence_start_at,run_at,reminder_minutes,
                 event_updated_at,dedup_key,status,attempts,last_error,created_at,completed_at)
            SELECT 100000+n,100000+n,now()+interval '2 days',now()+interval '2 days',30,
                   now()-interval '30 days','scale-future-' || n,'PENDING',0,NULL,
                   now()-interval '30 days',NULL
            FROM generate_series(1,60000) AS n
        """))
        connection.execute(text("""
            INSERT INTO programreminderjob
                (schedule_event_id,owner_user_id,occurrence_start_at,run_at,reminder_minutes,
                 event_updated_at,dedup_key,status,attempts,last_error,created_at,completed_at)
            SELECT 900000+n,42,now()-interval '1 hour',now()-interval '30 minutes',30,
                   now()-interval '30 days','scale-due-' || n,'PENDING',0,NULL,
                   now()-interval '30 days',NULL
            FROM generate_series(1,1000) AS n
        """))
        connection.execute(text('ANALYZE scheduleevent'))
        connection.execute(text('ANALYZE programreminderjob'))

    range_plan = _explain_analyze_index_names(
        engine,
        """
        SELECT id FROM scheduleevent
        WHERE owner_user_id=:owner
          AND status <> 'DELETED'
          AND start_at <= :range_end
          AND (recurrence_rule='WEEKLY' OR start_at >= :range_start OR end_at >= :range_start)
          AND (recurrence_rule <> 'WEEKLY' OR recurrence_until IS NULL
               OR recurrence_until='' OR recurrence_until >= :range_date)
        ORDER BY start_at LIMIT 50
        """,
        {
            'owner': 42,
            'range_start': datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
            'range_end': datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
            'range_date': datetime.now(timezone.utc).date().isoformat(),
        },
    )
    snapshot_plan = _explain_analyze_index_names(
        engine,
        """
        SELECT id FROM scheduleevent
        WHERE owner_user_id=:owner
          AND (created_at > :snapshot OR updated_at > :snapshot)
        LIMIT 1
        """,
        {'owner': 42, 'snapshot': datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)},
    )
    reminder_plan = _explain_analyze_index_names(
        engine,
        """
        SELECT id FROM programreminderjob
        WHERE status='PENDING' AND run_at <= now()
        ORDER BY run_at LIMIT 100
        """,
    )
    assert 'ix_scheduleevent_owner_start_at' in range_plan
    assert {'ix_scheduleevent_owner_created_at','ix_scheduleevent_owner_updated_at'} & snapshot_plan
    assert 'ix_programreminderjob_status_run_at' in reminder_plan


def test_treatment_history_index_migration_upgrades_revision18_online(pg):
    from app import migrate
    engine, _, _ = pg
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE IF NOT EXISTS dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'
        ))
        connection.execute(text(
            'INSERT INTO dental_schema_revision VALUES (1,18) ON CONFLICT(id) DO UPDATE SET version=18'
        ))
        connection.execute(text('DROP INDEX IF EXISTS ix_treatment_patient_created_id'))
    migrate.apply()
    migrate.require_schema(engine)
    with engine.connect() as connection:
        assert connection.execute(
            text('SELECT version FROM dental_schema_revision WHERE id=1')
        ).scalar_one() == 19
        assert connection.execute(
            text('SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(:name)'),
            {'name': 'ix_treatment_patient_created_id'},
        ).scalar_one() is True
        index = next(
            item for item in __import__('sqlalchemy').inspect(connection).get_indexes('treatment')
            if item.get('name') == 'ix_treatment_patient_created_id'
        )
        assert index['column_names'] == ['patient_id', 'created_at', 'id']
