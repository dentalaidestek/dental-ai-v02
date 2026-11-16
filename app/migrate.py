"""Explicit, serialized release migration: python -m app.migrate.

The existing idempotent baseline DDL is retained; revision 2 adds durable work, provider reservations and immutable analysis-result pointers;
revision 3 adds isolated expert professional-title change reviews; revision 4 adds durable dental semantic chunk metadata; revision 5 adds lazy visual page artifacts; revision 6 adds one-time email verification state; revision 9 adds shared authentication admission counters; revision 10 adds isolated email-change challenges; revision 11 adds consultation chat retention and a committed media-deletion outbox. revision 12 adds private membership-verification records. Web/workers only
check the revision in production, avoiding repeated boot-time DDL/backfills.
"""
import logging
from sqlalchemy import text, inspect

logger = logging.getLogger(__name__)

REVISION = 13


def require_schema(engine,*,require_study=False):
    try:
        with engine.connect() as connection:
            revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
    except Exception as exc:
        raise RuntimeError('Run python -m app.migrate before starting this service') from exc
    if revision != REVISION:
        raise RuntimeError(f'Expected schema revision {REVISION}; run python -m app.migrate')
    # Additive admin MFA tables: the production startup only checks schema revision,
    # so the original init_db() DDL never runs on Render. Serialize this small
    # compatibility migration across concurrent web instances.
    if engine.dialect.name == 'postgresql':
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text('SELECT pg_advisory_xact_lock(71048234)'))
            connection.execute(text('CREATE TABLE IF NOT EXISTS adminloginchallenge (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, token_hash VARCHAR NOT NULL UNIQUE, code_hash VARCHAR NOT NULL, expires_at TIMESTAMP NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, used_at TIMESTAMP)'))
            connection.execute(text('CREATE INDEX IF NOT EXISTS ix_adminloginchallenge_user_id ON adminloginchallenge (user_id)'))
            connection.execute(text('CREATE TABLE IF NOT EXISTS adminverifiedsession (token_hash VARCHAR PRIMARY KEY, user_id INTEGER NOT NULL)'))
            connection.execute(text('CREATE INDEX IF NOT EXISTS ix_adminverifiedsession_user_id ON adminverifiedsession (user_id)'))
    if require_study:
        inspector=inspect(engine)
        if any(not inspector.has_table(table) for table in ('studylearningstate','studyreview','studyattempt','studyrun')):
            raise RuntimeError('Run python -m app.migrate to create the academic study tables')


def _create_study_tables(connection):
    from app.academic_learning import StudyLearningState,StudyReview,StudyAttempt
    from app.academic_study_runs import StudyRun
    for model in (StudyLearningState,StudyReview,StudyAttempt,StudyRun):
        model.__table__.create(connection,checkfirst=True)


def _upgrade_learning_schema(main):
    if main.engine.dialect.name!='postgresql':return False
    with main.engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '60s'"))
        if not inspect(connection).has_table('dental_schema_revision'):return False
        revision=connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision!=12:return False
        connection.execute(text('SELECT pg_advisory_xact_lock(71048233)'))
        revision=connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision!=12:raise RuntimeError('Schema changed during release migration')
        _create_study_tables(connection)
        # These are independent additive tables. Preserve the existing baseline
        # revision so already-deployed external OCR/clinical workers remain compatible.
    return True


def _upgrade_recent_schema(main):
    """Upgrade 10/11 without replaying historical DDL on busy production tables.

    Transaction-scoped locking works with transaction-pooling proxies and cannot
    leave a session advisory lock behind when a web container is replaced.
    """
    if main.engine.dialect.name != 'postgresql':
        return False
    with main.engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '60s'"))
        if not inspect(connection).has_table('dental_schema_revision'):
            return False
        revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        logger.warning('migration.recent revision=%s', revision)
        if revision == REVISION:
            return True
        if revision not in (10, 11):
            return False
        logger.warning('migration.recent begin=transaction_lock')
        connection.execute(text('SELECT pg_advisory_xact_lock(71048233)'))
        # Re-read after obtaining the lock: another deploy may have finished.
        revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision == REVISION:
            return True
        if revision not in (10, 11):
            raise RuntimeError('Schema changed during release migration')
        logger.warning('migration.recent begin=retention_columns')
        connection.execute(text('ALTER TABLE consultationcase ADD COLUMN IF NOT EXISTS messages_deleted_at TIMESTAMP'))
        connection.execute(text('ALTER TABLE consultationcase ADD COLUMN IF NOT EXISTS chat_retention_started_at TIMESTAMP'))
        logger.warning('migration.recent begin=private_tables')
        from app.membership_verification import MembershipVerification
        main.ConsultationMediaDeletion.__table__.create(connection, checkfirst=True)
        MembershipVerification.__table__.create(connection, checkfirst=True)
        _create_study_tables(connection)
        logger.warning('migration.recent begin=retention_backfill')
        main._backfill_legacy_deadline_jobs_if_needed(bind=connection)
        connection.execute(text('UPDATE dental_schema_revision SET version=:version WHERE id=1'), {'version': REVISION})
    logger.warning('migration.recent complete revision=%s', REVISION)
    return True


def _upgrade_support_receipts_schema(main):
    """Add durable idempotency receipts for native support-ticket mutations."""
    if main.engine.dialect.name != 'postgresql':
        return False
    with main.engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '60s'"))
        if not inspect(connection).has_table('dental_schema_revision'):
            return False
        revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision == REVISION:
            return True
        if revision != 12:
            return False
        connection.execute(text('SELECT pg_advisory_xact_lock(71048233)'))
        revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision == REVISION:
            return True
        if revision != 12:
            raise RuntimeError('Schema changed during support receipt migration')
        from app.mobile_api import MobileSupportMutationReceipt
        MobileSupportMutationReceipt.__table__.create(connection, checkfirst=True)
        connection.execute(text('UPDATE dental_schema_revision SET version=:version WHERE id=1'), {'version': REVISION})
    logger.warning('migration.support_receipts complete revision=%s', REVISION)
    return True


def _apply_baseline():
    from app import main
    if _upgrade_learning_schema(main):
        return
    if _upgrade_recent_schema(main):
        return
    # A dedicated migration process owns the advisory lock through all of the
    # historical DDL transactions. It is released even on migration failure.
    lock = None
    try:
        if main.engine.dialect.name == 'postgresql':
            import psycopg2
            args, kwargs = main.engine.dialect.create_connect_args(main.engine.url)
            kwargs.setdefault("connect_timeout", 5)
            lock = psycopg2.connect(*args, **kwargs)
            lock.autocommit = True
            with lock.cursor() as cursor:
                cursor.execute("SET statement_timeout = '60s'")
                cursor.execute('SELECT pg_advisory_lock(71048232)')
        main.init_db()
        from app.work_jobs import WorkJob
        for index in WorkJob.__table__.indexes:
            index.create(main.engine, checkfirst=True)
        with main.engine.begin() as connection:
            if main.engine.dialect.name == "postgresql":
                for ddl in (
                    "ALTER TABLE consultationmessage ADD COLUMN IF NOT EXISTS e2ee_ciphertext TEXT",
                    "ALTER TABLE consultationmessage ADD COLUMN IF NOT EXISTS e2ee_ephemeral_public_key TEXT",
                    "ALTER TABLE consultationmessage ADD COLUMN IF NOT EXISTS e2ee_key_version VARCHAR",
                    "ALTER TABLE supportticketmessage ADD COLUMN IF NOT EXISTS e2ee_ciphertext TEXT",
                    "ALTER TABLE supportticketmessage ADD COLUMN IF NOT EXISTS e2ee_ephemeral_public_key TEXT",
                    "ALTER TABLE supportticketmessage ADD COLUMN IF NOT EXISTS e2ee_key_version VARCHAR",
                    """CREATE TABLE IF NOT EXISTS e2eedevicekey (
                        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        device_id VARCHAR NOT NULL UNIQUE,
                        algorithm VARCHAR NOT NULL DEFAULT 'X25519',
                        public_key TEXT NOT NULL,
                        key_version VARCHAR NOT NULL DEFAULT 'v1',
                        created_at TIMESTAMP NOT NULL,
                        revoked_at TIMESTAMP NULL
                    )""",
                    "CREATE INDEX IF NOT EXISTS ix_e2eedevicekey_user_id ON e2eedevicekey(user_id)",
                    "CREATE INDEX IF NOT EXISTS ix_e2eedevicekey_revoked_at ON e2eedevicekey(revoked_at)",
                ):
                    connection.execute(text(ddl))
            if main.engine.dialect.name == "postgresql":
                connection.execute(text("ALTER TABLE studyindexchunk ADD COLUMN IF NOT EXISTS retrieval_terms TEXT"))
                connection.execute(text("ALTER TABLE studyindexchunk ADD COLUMN IF NOT EXISTS semantic_json TEXT"))
                connection.execute(text("ALTER TABLE studyindexpage ADD COLUMN IF NOT EXISTS visual_pdf_bytes BYTEA"))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_studyindexchunk_dental_fts "
                    "ON studyindexchunk USING GIN "
                    "(to_tsvector('simple', coalesce(section_title,'') || ' ' || "
                    "coalesce(text_content,'') || ' ' || coalesce(retrieval_terms,'')))"
                ))
            for ddl in (
                "CREATE INDEX IF NOT EXISTS ix_realtimeevent_user_cursor ON realtimeevent(user_id, id)",
                "CREATE INDEX IF NOT EXISTS ix_consultationmessage_case_cursor ON consultationmessage(case_id, id)",
                "CREATE INDEX IF NOT EXISTS ix_studychatmessage_recent ON studychatmessage(owner_user_id, course_id, id)",
            ):
                connection.execute(text(ddl))
        main._backfill_legacy_deadline_jobs_if_needed()
        main._backfill_program_reminder_jobs()
        with main.engine.begin() as connection:
            connection.execute(text('CREATE TABLE IF NOT EXISTS dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'))
            connection.execute(text('INSERT INTO dental_schema_revision(id, version) VALUES(1, :version) ON CONFLICT(id) DO UPDATE SET version=excluded.version'), {'version': REVISION})
    finally:
        if lock:
            try:
                with lock.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_unlock(71048232)')
            finally:
                lock.close()


def apply():
    _apply_baseline()
    from app import main
    from app.expert_social_schema import apply as apply_social_schema
    apply_social_schema(main.engine)


if __name__ == '__main__':
    apply()


