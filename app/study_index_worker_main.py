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
from app.study_index_jobs import (
    StudyIndexChunk, StudyIndexJob, StudyIndexPage, StudyProviderCircuit,
    cleanup_retired_generations,
)  # noqa: F401
from app.study_index_worker import run_one_slice
from app.study_deletion_worker import run_deletion_slice
from app.study_v2_database import require_worker_capabilities

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
    with Session(engine, expire_on_commit=False) as startup_session:
        capabilities = require_worker_capabilities(startup_session)
        logger.info(
            "Academic V2 database ready fts=%s native_array=%s pgvector=%s",
            capabilities.fts, capabilities.embedding_array, capabilities.pgvector,
        )
    resource_class = (os.getenv("STUDY_V2_RESOURCE_CLASS") or "NORMAL").strip().upper()
    if resource_class not in {"NORMAL", "OCR_HEAVY"}:
        raise RuntimeError(f"Unsupported STUDY_V2_RESOURCE_CLASS: {resource_class}")
    idle_sleep = _int_env("STUDY_V2_IDLE_SLEEP_SECONDS", 2, 1, 30)
    error_sleep = _int_env("STUDY_V2_ERROR_SLEEP_SECONDS", 5, 1, 60)

    logger.info("Academic V2 index worker started resource_class=%s", resource_class)
    gc_every = _int_env("STUDY_V2_GC_EVERY_LOOPS", 60, 10, 3600)
    loops = 0
    while not _stop:
        try:
            with Session(engine, expire_on_commit=False) as session:
                result = run_one_slice(session, resource_class=resource_class)
                loops += 1
                if resource_class == "NORMAL":
                    # Privacy erasure is serviced continuously and is never
                    # blocked behind normal indexing backlog.
                    run_deletion_slice(session)
                    if loops % gc_every == 0:
                        cleanup_retired_generations(session, limit=10)
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
