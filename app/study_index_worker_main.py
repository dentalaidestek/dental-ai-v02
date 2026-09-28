"""Standalone Academic AI V2 worker process.

Run this as a separate service/process, never inside the web request workers.
It uses its own SQLAlchemy engine/pool so indexing cannot consume the web
service's connection pool.
"""
from __future__ import annotations

import logging
import os
import signal
import time

from sqlalchemy import create_engine
from sqlmodel import Session

# Import models before the loop. Schema creation/migration remains owned by the
# web release/startup path; the worker must not mutate schema at boot.
from app.study_index_jobs import StudyIndexChunk, StudyIndexJob, StudyIndexPage  # noqa: F401
from app.study_index_worker import run_one_slice

logger = logging.getLogger(__name__)
_stop = False


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(value, high))


def _handle_stop(signum, frame) -> None:
    global _stop
    _stop = True


def build_worker_engine():
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("Academic V2 worker requires DATABASE_URL; SQLite is not supported for deployed workers")
    pool_size = _int_env("STUDY_V2_DB_POOL_SIZE", 2, 1, 5)
    return create_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=0,
        pool_pre_ping=True,
        pool_recycle=300,
    )


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    engine = build_worker_engine()
    idle_sleep = _int_env("STUDY_V2_IDLE_SLEEP_SECONDS", 2, 1, 30)
    error_sleep = _int_env("STUDY_V2_ERROR_SLEEP_SECONDS", 5, 1, 60)

    logger.info("Academic V2 index worker started")
    while not _stop:
        try:
            with Session(engine, expire_on_commit=False) as session:
                result = run_one_slice(session)
            if result == "IDLE":
                time.sleep(idle_sleep)
        except Exception:
            # Process stays alive; durable leases/jobs are the recovery source.
            logger.exception("Academic V2 worker loop error")
            time.sleep(error_sleep)

    engine.dispose()
    logger.info("Academic V2 index worker stopped")


if __name__ == "__main__":
    main()
