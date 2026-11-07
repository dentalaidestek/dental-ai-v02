"""Social extension migration, independent from worker baseline revision 12."""

from sqlalchemy import inspect, text
from app.expert_social_models import SOCIAL_MODELS

# Index-only additions keep the deployed table contract at revision 2. Older
# builds can restart/roll back safely; this build checks its indexes separately.
SCHEMA_VERSION = 2
REQUIRED_INDEXES = {
    "socialpost": "ix_socialpost_moderation",
    "socialcomment": "ix_socialcomment_moderation",
    "publication": "ix_publication_moderation",
    "doimatch": "ix_doimatch_created_at",
}


def apply(engine):
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SET LOCAL lock_timeout = '10s'"))
            conn.execute(text("SET LOCAL statement_timeout = '60s'"))
            conn.execute(text("SELECT pg_advisory_xact_lock(71048235)"))
        for model in SOCIAL_MODELS:
            model.__table__.create(conn, checkfirst=True)
            # Table.create(checkfirst=True) skips indexes on existing tables.
            # Upgrades must install indexes as well as brand-new tables.
            for index in model.__table__.indexes:
                index.create(conn, checkfirst=True)
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS dental_social_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO dental_social_revision(id,version) VALUES(1,:version) ON CONFLICT(id) DO UPDATE SET version=excluded.version"
            ),
            {"version": SCHEMA_VERSION},
        )


def require_schema(engine):
    try:
        with engine.connect() as conn:
            revision = conn.execute(
                text("SELECT version FROM dental_social_revision WHERE id=1")
            ).scalar()
            inspector = inspect(conn)
            complete = all(inspector.has_table(m.__tablename__) for m in SOCIAL_MODELS)
            indexed = complete and all(
                name in {index["name"] for index in inspector.get_indexes(table)}
                for table, name in REQUIRED_INDEXES.items()
            )
        if revision != SCHEMA_VERSION or not complete or not indexed:
            raise RuntimeError()
    except Exception as exc:
        raise RuntimeError(
            "Social schema is missing; run python -m app.migrate before starting the web service"
        ) from exc
