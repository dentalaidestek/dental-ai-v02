"""Bounded database pools for web and provider-router processes."""
import os
import time
import logging
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlmodel import create_engine


def create_app_engine(url: str, *, role: str = "web", allow_sqlite: bool = False):
    url = url.replace("postgres://", "postgresql://", 1) if url.startswith("postgres://") else url
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        if not allow_sqlite:
            raise RuntimeError("SQLite is restricted to explicit local development")
        return create_engine(url, connect_args={"check_same_thread": False})
    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("Unsupported database backend")
    prefix = f"DENTAL_{role.upper()}_DB"
    pool_size = int(os.getenv(f"{prefix}_POOL_SIZE", "2"))
    pool_timeout = int(os.getenv(f"{prefix}_POOL_TIMEOUT", "20"))
    if not 1 <= pool_timeout <= 60:
        raise RuntimeError(f"{prefix}_POOL_TIMEOUT must be 1..60")
    if not 1 <= pool_size <= 10:
        raise RuntimeError(f"{prefix}_POOL_SIZE must be 1..10")
    engine = create_engine(
        url,
        pool_size=pool_size,
        max_overflow=0,
        pool_timeout=pool_timeout,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 5, "application_name": f"dental-{role}"},
    )
    threshold = int(os.getenv(f"{prefix}_SLOW_CHECKOUT_SECONDS", "10"))
    if threshold > 0:
        log = logging.getLogger(__name__)

        @event.listens_for(engine, "checkout")
        def _checkout(dbapi_connection, record, proxy):
            record.info["checkout_started"] = time.monotonic()

        @event.listens_for(engine, "checkin")
        def _checkin(dbapi_connection, record):
            started = record.info.pop("checkout_started", None)
            if started is not None:
                elapsed = time.monotonic() - started
                if elapsed >= threshold:
                    log.warning("Slow DB connection hold role=%s seconds=%.2f", role, elapsed)
    return engine

