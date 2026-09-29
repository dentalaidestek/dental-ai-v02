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
