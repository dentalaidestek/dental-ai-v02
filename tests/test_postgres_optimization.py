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
        assert connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar_one() == 10
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
