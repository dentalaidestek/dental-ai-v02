"""Social extension migration, independent from worker baseline revision 12."""

from sqlalchemy import inspect, text
from app.expert_social_models import SOCIAL_MODELS


def apply(engine):
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SET LOCAL lock_timeout = '10s'"))
            conn.execute(text("SET LOCAL statement_timeout = '60s'"))
            conn.execute(text("SELECT pg_advisory_xact_lock(71048235)"))
        for model in SOCIAL_MODELS:
            model.__table__.create(conn, checkfirst=True)
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS dental_social_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO dental_social_revision(id,version) VALUES(1,1) ON CONFLICT(id) DO UPDATE SET version=excluded.version"
            )
        )


def require_schema(engine):
    try:
        with engine.connect() as conn:
            revision = conn.execute(
                text("SELECT version FROM dental_social_revision WHERE id=1")
            ).scalar()
            inspector = inspect(conn)
            complete = all(inspector.has_table(m.__tablename__) for m in SOCIAL_MODELS)
        if revision != 1 or not complete:
            raise RuntimeError()
    except Exception as exc:
        raise RuntimeError(
            "Social schema is missing; run python -m app.migrate before starting the web service"
        ) from exc
