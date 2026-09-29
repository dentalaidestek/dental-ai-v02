"""Durable application consumer; use one process, independently of web workers."""
import asyncio
import json
import logging
import os
import signal
import threading
import time
from contextlib import contextmanager
from sqlmodel import Session
from app.object_cache import scope as storage_scope
from app.work_jobs import WorkCancelled, claim, current_job, finish, guard_publication, heartbeat

logger = logging.getLogger(__name__)


@contextmanager
def keep_lease(engine, job):
    stop = threading.Event()
    def renew():
        while not stop.wait(30):
            try:
                if not heartbeat(engine, job):
                    return
            except Exception:
                logger.exception('work heartbeat failed job_id=%s', job.id)
    thread = threading.Thread(target=renew, daemon=True, name='dental-job-heartbeat')
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(6)


def run_one(engine):
    from app import main as m
    # Service erasure and result cleanup even under continuous clinical load.
    from app.work_jobs import collect_garbage, prune_history
    from app.study_deletion_worker import run_deletion_slice
    collect_garbage(engine)
    prune_history(engine)
    with Session(engine, expire_on_commit=False) as session:
        deletion = run_deletion_slice(session)
    job = claim(engine)
    if job is None:
        return deletion != 'IDLE'
    token = current_job.set(job)
    started = time.monotonic()
    try:
        with keep_lease(engine, job), storage_scope():
            with Session(engine) as session:
                guard_publication(session)
            guest = job.resource_type == 'GUEST'
            if job.kind == 'VISION':
                (m._run_guest_vision if guest else m._run_analysis_vision)(job.resource_id)
            elif job.kind == 'PRELIMINARY':
                (m._run_guest_preliminary_ai if guest else m._run_preliminary_ai)(job.resource_id)
            elif job.kind == 'FINAL':
                (m._run_guest_final_analysis if guest else m._run_final_analysis)(job.resource_id, job.owner_user_id, json.loads(job.payload_json))
            elif job.kind == 'LEGACY_INDEX':
                m._index_study_course_background(job.owner_user_id, job.resource_id)
            else:
                raise WorkCancelled('UNSUPPORTED_JOB')
            finish(engine, job, status='DONE')
    except WorkCancelled as exc:
        finish(engine, job, status='CANCELLED', error_code=str(exc))
    except Exception as exc:
        # Crash/network recovery is bounded. Provider/schema retries remain in
        # their existing adapters. A deterministic AI_ERROR is not retried here.
        finish(engine, job, status='QUEUED' if job.attempts < 3 else 'FAILED', error_code=type(exc).__name__)
        logger.exception('work failed job_id=%s kind=%s', job.id, job.kind)
    finally:
        logger.info('work.finished job_id=%s kind=%s duration_ms=%s', job.id, job.kind, round((time.monotonic()-started)*1000))
        current_job.reset(token)
    return True


async def embedded():
    from app import main
    from anyio import to_thread
    while True:
        try:
            did_work = await to_thread.run_sync(run_one, main.engine)
        except Exception:
            logger.exception('Application queue iteration failed')
            await asyncio.sleep(5)
            continue
        if not did_work:
            await asyncio.sleep(2)


def main():
    from app import main as app_main
    from app.migrate import require_schema
    require_schema(app_main.engine)
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *args: stop.set())
    logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
    while not stop.is_set():
        try:
            if not run_one(app_main.engine):
                stop.wait(2)
        except Exception:
            logger.exception('Application queue iteration failed')
            stop.wait(5)
    app_main.engine.dispose()


if __name__ == '__main__':
    main()
