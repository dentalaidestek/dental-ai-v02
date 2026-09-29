"""Explicit, serialized release migration: python -m app.migrate.

The existing idempotent baseline DDL is retained; revision 2 adds durable work,
provider reservations and immutable analysis-result pointers. Web/workers only
check the revision in production, avoiding repeated boot-time DDL/backfills.
"""
from sqlalchemy import text

REVISION = 2


def require_schema(engine):
    try:
        with engine.connect() as connection:
            revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
    except Exception as exc:
        raise RuntimeError('Run python -m app.migrate before starting this service') from exc
    if revision != REVISION:
        raise RuntimeError(f'Expected schema revision {REVISION}; run python -m app.migrate')


def apply():
    from app import main
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
                cursor.execute('SELECT pg_advisory_lock(71048232)')
        main.init_db()
        from app.work_jobs import WorkJob
        for index in WorkJob.__table__.indexes:
            index.create(main.engine, checkfirst=True)
        with main.engine.begin() as connection:
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
            lock.close()


if __name__ == '__main__':
    apply()
