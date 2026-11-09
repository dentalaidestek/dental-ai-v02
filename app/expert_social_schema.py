"""Social extension migration, independent from worker baseline revision 12."""

import logging

from sqlalchemy import inspect, text
from app.expert_social_models import SOCIAL_MODELS

logger = logging.getLogger(__name__)

# Additive tables/indexes preserve the deployed revision-two table contract.
# Older builds can restart/roll back safely; this build checks its additions.
SCHEMA_VERSION = 2
REQUIRED_INDEXES = {
    "socialpost": "ix_socialpost_moderation",
    "socialcomment": "ix_socialcomment_moderation",
    "publication": "ix_publication_moderation",
    "doimatch": "ix_doimatch_created_at",
    "socialmoderationtask": "ix_socialmoderationtask_retry",
    "socialmoderationevent": "ix_socialmoderationevent_target",
    "consultationrequestreceipt": "uq_consultationrequestreceipt_key",
    "socialcommentlike": "ix_socialcommentlike_user_id",
}
# Extra requirements stay additive while retaining the revision-two readiness
# contract expected by older web/worker builds.
REQUIRED_COMMENT_INDEXES = {"socialcomment": "ix_socialcomment_replies"}


def apply(engine):
    logger.warning("social.schema begin version=%s", SCHEMA_VERSION)
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
    # One bounded rollout slice; the existing housekeeping worker continues it.
    # No feed/detail page scans or enqueues historical content.
    from app.expert_social_moderation import backfill_pending

    backfill_pending(engine, limit=60)
    require_schema(engine)
    logger.warning("social.schema ready version=%s comment_likes=true", SCHEMA_VERSION)


def require_schema(engine):
    try:
        with engine.connect() as conn:
            revision = conn.execute(
                text("SELECT version FROM dental_social_revision WHERE id=1")
            ).scalar()
            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            complete = all(m.__tablename__ in tables for m in SOCIAL_MODELS)
            requirements = (*REQUIRED_INDEXES.items(), *REQUIRED_COMMENT_INDEXES.items())
            indexes = inspector.get_multi_indexes(filter_names=list({table for table, _ in requirements})) if complete else {}
            indexed = complete and all(
                name in {index["name"] for index in indexes.get((None, table), [])}
                for table, name in requirements
            )
        if revision != SCHEMA_VERSION or not complete or not indexed:
            raise RuntimeError()
    except Exception as exc:
        raise RuntimeError(
            "Social schema is missing; run python -m app.migrate before starting the web service"
        ) from exc
