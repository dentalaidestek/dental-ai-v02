"""Bounded database pools for web and provider-router processes."""
import os
from sqlalchemy.engine import make_url
from sqlmodel import create_engine


def create_app_engine(url: str, *, role: str = "web", allow_sqlite: bool = False):
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        if not allow_sqlite:
            raise RuntimeError("SQLite is restricted to explicit local development")
        return create_engine(url, connect_args={"check_same_thread": False})
    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("Unsupported database backend")
    prefix = f"DENTAL_{role.upper()}_DB"
    pool_size = int(os.getenv(f"{prefix}_POOL_SIZE", "2"))
    if not 1 <= pool_size <= 10:
        raise RuntimeError(f"{prefix}_POOL_SIZE must be 1..10")
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=0,
        pool_timeout=5,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 5, "application_name": f"dental-{role}"},
    )
