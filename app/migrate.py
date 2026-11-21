"""Explicit, serialized release migration: python -m app.migrate.

The existing idempotent baseline DDL is retained; revision 2 adds durable work, provider reservations and immutable analysis-result pointers;
revision 3 adds isolated expert professional-title change reviews; revision 4 adds durable dental semantic chunk metadata; revision 5 adds lazy visual page artifacts; revision 6 adds one-time email verification state; revision 9 adds shared authentication admission counters; revision 10 adds isolated email-change challenges; revision 11 adds consultation chat retention and a committed media-deletion outbox. revision 12 adds private membership-verification records; revision 15 adds native Program idempotency fields; revision 16 adds online owner-scoped Program and reminder queue indexes; revision 17 adds native Academic course-create receipts; revision 18 adds unique tooth-observation indexes; revision 19 adds the patient treatment-history keyset index; revision 20 adds a partial pending-reminder queue index; revision 21 adds the append-only approved anamnesis ledger and legacy backfill. Web/workers only
check the revision in production, avoiding repeated boot-time DDL/backfills.
"""
import logging
from sqlalchemy import text, inspect

logger = logging.getLogger(__name__)

SUPPORT_RECEIPTS_REVISION = 14
PROGRAM_IDEMPOTENCY_REVISION = 15
PROGRAM_QUERY_INDEX_REVISION = 16
ACADEMIC_COURSE_RECEIPT_REVISION = 17
TOOTH_CHART_OBSERVATION_REVISION = 18
TREATMENT_HISTORY_INDEX_REVISION = 19
PROGRAM_REMINDER_PENDING_INDEX_REVISION = 20
APPROVED_ANAMNESIS_REVISION = 21
REVISION = APPROVED_ANAMNESIS_REVISION
PROGRAM_QUERY_INDEX_LOCK = 71048238
TOOTH_CHART_OBSERVATION_LOCK = 71048240
TREATMENT_HISTORY_INDEX_LOCK = 71048241
PROGRAM_REMINDER_PENDING_INDEX_LOCK = 71048242


def _ensure_mobile_push_device_table(engine):
    """Create the additive native push table for databases already at revision 15.

    MobilePushDevice was introduced after the current baseline revision. Existing
    Render databases do not replay init_db(), so the table must be ensured through
    the same small, serialized compatibility path used for admin MFA tables.
    """
    from app import main

    table = main.MobilePushDevice.__table__
    with engine.begin() as connection:
        if engine.dialect.name == 'postgresql':
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text('SELECT pg_advisory_xact_lock(71048235)'))
        table.create(connection, checkfirst=True)
        columns = {column["name"] for column in inspect(connection).get_columns(table.name)}
        if "device_proof_hash" not in columns:
            connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN device_proof_hash VARCHAR"))
        for index in table.indexes:
            index.create(connection, checkfirst=True)


def _ensure_mobile_push_delivery_table(engine):
    """Create the additive Expo ticket/receipt table without changing schema revision."""
    from app import main

    table = main.MobilePushDelivery.__table__
    with engine.begin() as connection:
        if engine.dialect.name == 'postgresql':
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text('SELECT pg_advisory_xact_lock(71048236)'))
        table.create(connection, checkfirst=True)
        for index in table.indexes:
            index.create(connection, checkfirst=True)


def require_schema(engine,*,require_study=False):
    try:
        with engine.connect() as connection:
            revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
    except Exception as exc:
        raise RuntimeError('Run python -m app.migrate before starting this service') from exc
    if revision != REVISION:
        raise RuntimeError(f'Expected schema revision {REVISION}; run python -m app.migrate')
    inspector = inspect(engine)
    if not inspector.has_table("approvedanamnesis"):
        raise RuntimeError("Run python -m app.migrate to create the approved anamnesis ledger")
    approved_indexes = {item.get("name") for item in inspector.get_indexes("approvedanamnesis")}
    if "ix_approvedanamnesis_owner_patient_field_analysis" not in approved_indexes:
        raise RuntimeError("Run python -m app.migrate to install the approved anamnesis query index")
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
    _ensure_mobile_push_device_table(engine)
    _ensure_mobile_push_delivery_table(engine)
    if require_study:
        inspector=inspect(engine)
        if any(not inspector.has_table(table) for table in ('studylearningstate','studyreview','studyattempt','studyrun','studycoursecreatereceipt')):
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
        if revision in (SUPPORT_RECEIPTS_REVISION, PROGRAM_QUERY_INDEX_REVISION, REVISION):
            return True
        if revision not in (10, 11):
            return False
        logger.warning('migration.recent begin=transaction_lock')
        connection.execute(text('SELECT pg_advisory_xact_lock(71048233)'))
        # Re-read after obtaining the lock: another deploy may have finished.
        revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision in (SUPPORT_RECEIPTS_REVISION, PROGRAM_QUERY_INDEX_REVISION, REVISION):
            return True
        if revision not in (10, 11):
            raise RuntimeError('Schema changed during release migration')
        logger.warning('migration.recent begin=retention_columns')
        connection.execute(text('ALTER TABLE consultationcase ADD COLUMN IF NOT EXISTS messages_deleted_at TIMESTAMP'))
        connection.execute(text('ALTER TABLE consultationcase ADD COLUMN IF NOT EXISTS chat_retention_started_at TIMESTAMP'))
        logger.warning('migration.recent begin=private_tables')
        from app.membership_verification import MembershipVerification
        from app.mobile_api import MobileSupportMutationReceipt
        main.ConsultationMediaDeletion.__table__.create(connection, checkfirst=True)
        main.ConsultationMessageReceipt.__table__.create(connection, checkfirst=True)
        MobileSupportMutationReceipt.__table__.create(connection, checkfirst=True)
        MembershipVerification.__table__.create(connection, checkfirst=True)
        _create_study_tables(connection)
        logger.warning('migration.recent begin=retention_backfill')
        main._backfill_legacy_deadline_jobs_if_needed(bind=connection)
        connection.execute(text('UPDATE dental_schema_revision SET version=:version WHERE id=1'), {'version': SUPPORT_RECEIPTS_REVISION})
    logger.warning('migration.recent complete revision=%s', SUPPORT_RECEIPTS_REVISION)
    return True


def _upgrade_support_receipts_schema(main):
    """Add durable idempotency receipts for support tickets and consultation chat."""
    if main.engine.dialect.name != 'postgresql':
        return False
    with main.engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '60s'"))
        if not inspect(connection).has_table('dental_schema_revision'):
            return False
        revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision in (SUPPORT_RECEIPTS_REVISION, PROGRAM_QUERY_INDEX_REVISION, REVISION):
            return True
        if revision not in (12, 13):
            return False
        connection.execute(text('SELECT pg_advisory_xact_lock(71048233)'))
        revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision in (SUPPORT_RECEIPTS_REVISION, PROGRAM_QUERY_INDEX_REVISION, REVISION):
            return True
        if revision not in (12, 13):
            raise RuntimeError('Schema changed during consultation receipt migration')
        if revision == 12:
            from app.mobile_api import MobileSupportMutationReceipt
            MobileSupportMutationReceipt.__table__.create(connection, checkfirst=True)
        main.ConsultationMessageReceipt.__table__.create(connection, checkfirst=True)
        connection.execute(text('UPDATE dental_schema_revision SET version=:version WHERE id=1'), {'version': SUPPORT_RECEIPTS_REVISION})
    logger.warning('migration.consultation_receipts complete revision=%s', SUPPORT_RECEIPTS_REVISION)
    return True



def _upgrade_program_idempotency_schema(main):
    """Add nullable, owner-scoped request fingerprints to native Program events."""
    if main.engine.dialect.name != 'postgresql':
        return False
    with main.engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '60s'"))
        if not inspect(connection).has_table('dental_schema_revision'):
            return False
        revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision in (PROGRAM_IDEMPOTENCY_REVISION, PROGRAM_QUERY_INDEX_REVISION, REVISION):
            return True
        if revision != PROGRAM_IDEMPOTENCY_REVISION - 1:
            return False
        connection.execute(text('SELECT pg_advisory_xact_lock(71048233)'))
        revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision in (PROGRAM_IDEMPOTENCY_REVISION, PROGRAM_QUERY_INDEX_REVISION, REVISION):
            return True
        if revision != PROGRAM_IDEMPOTENCY_REVISION - 1:
            raise RuntimeError('Schema changed during Program idempotency migration')
        if not inspect(connection).has_table('scheduleevent'):
            raise RuntimeError('Program table is missing during idempotency migration')
        connection.execute(text('ALTER TABLE scheduleevent ADD COLUMN IF NOT EXISTS client_request_hash VARCHAR'))
        connection.execute(text('ALTER TABLE scheduleevent ADD COLUMN IF NOT EXISTS client_payload_hash VARCHAR'))
        connection.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduleevent_owner_client_request '
            'ON scheduleevent(owner_user_id, client_request_hash)'
        ))
        connection.execute(
            text('UPDATE dental_schema_revision SET version=:version WHERE id=1'),
            {'version': PROGRAM_IDEMPOTENCY_REVISION},
        )
    logger.warning('migration.program_idempotency complete revision=%s', PROGRAM_IDEMPOTENCY_REVISION)
    return True


def _upgrade_program_query_indexes(main):
    """Create hot-path Program indexes concurrently before advancing revision 16.

    A session advisory lock serializes migration processes while AUTOCOMMIT keeps
    PostgreSQL's CREATE INDEX CONCURRENTLY outside a transaction. An invalid index
    left by an interrupted build is dropped concurrently and rebuilt on retry.
    """
    if main.engine.dialect.name != 'postgresql':
        return False

    index_ddls = (
        ('ix_scheduleevent_owner_start_at',
         'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_scheduleevent_owner_start_at '
         'ON scheduleevent (owner_user_id, start_at)'),
        ('ix_scheduleevent_owner_created_at',
         'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_scheduleevent_owner_created_at '
         'ON scheduleevent (owner_user_id, created_at)'),
        ('ix_scheduleevent_owner_updated_at',
         'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_scheduleevent_owner_updated_at '
         'ON scheduleevent (owner_user_id, updated_at)'),
        ('ix_programreminderjob_status_run_at',
         'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_programreminderjob_status_run_at '
         'ON programreminderjob (status, run_at)'),
        ('ix_programreminderjob_event_status',
         'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_programreminderjob_event_status '
         'ON programreminderjob (schedule_event_id, status)'),
        ('ix_programreminderjob_owner_status',
         'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_programreminderjob_owner_status '
         'ON programreminderjob (owner_user_id, status)'),
    )

    with main.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text("SET lock_timeout = '10s'"))
        connection.execute(text("SET statement_timeout = '10min'"))
        connection.execute(
            text('SELECT pg_advisory_lock(:lock_key)'),
            {'lock_key': PROGRAM_QUERY_INDEX_LOCK},
        )
        try:
            if not inspect(connection).has_table('dental_schema_revision'):
                return False
            revision = connection.execute(
                text('SELECT version FROM dental_schema_revision WHERE id=1')
            ).scalar()
            if revision in (PROGRAM_QUERY_INDEX_REVISION, REVISION):
                return True
            if revision != PROGRAM_IDEMPOTENCY_REVISION:
                return False
            for table in ('scheduleevent', 'programreminderjob'):
                if not inspect(connection).has_table(table):
                    raise RuntimeError(f'Program query index migration requires {table}')

            for index_name, ddl in index_ddls:
                valid = connection.execute(
                    text('SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(:name)'),
                    {'name': index_name},
                ).scalar()
                if valid is False:
                    connection.execute(text(f'DROP INDEX CONCURRENTLY IF EXISTS {index_name}'))
                connection.execute(text(ddl))
                valid = connection.execute(
                    text('SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(:name)'),
                    {'name': index_name},
                ).scalar()
                if valid is not True:
                    raise RuntimeError(f'Program query index {index_name} was not built validly')

            result = connection.execute(
                text('UPDATE dental_schema_revision SET version=:version WHERE id=1 AND version=:prior'),
                {'version': PROGRAM_QUERY_INDEX_REVISION, 'prior': PROGRAM_IDEMPOTENCY_REVISION},
            )
            if result.rowcount != 1:
                current = connection.execute(
                    text('SELECT version FROM dental_schema_revision WHERE id=1')
                ).scalar()
                if current != PROGRAM_QUERY_INDEX_REVISION:
                    raise RuntimeError('Schema changed during Program query index migration')
        finally:
            connection.execute(
                text('SELECT pg_advisory_unlock(:lock_key)'),
                {'lock_key': PROGRAM_QUERY_INDEX_LOCK},
            )

    logger.warning('migration.program_query_indexes complete revision=%s', PROGRAM_QUERY_INDEX_REVISION)
    return True



def _upgrade_academic_course_receipts_schema(main):
    """Create native Academic course receipts and advance schema revision 17."""
    if main.engine.dialect.name != 'postgresql':
        return False
    with main.engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '60s'"))
        if not inspect(connection).has_table('dental_schema_revision'):
            return False
        revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision in (ACADEMIC_COURSE_RECEIPT_REVISION, REVISION):
            return True
        if revision != PROGRAM_QUERY_INDEX_REVISION:
            return False
        connection.execute(text('SELECT pg_advisory_xact_lock(71048239)'))
        revision = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
        if revision in (ACADEMIC_COURSE_RECEIPT_REVISION, REVISION):
            return True
        if revision != PROGRAM_QUERY_INDEX_REVISION:
            raise RuntimeError('Schema changed during Academic course receipt migration')
        from app.academic_course_receipts import StudyCourseCreateReceipt
        table = StudyCourseCreateReceipt.__table__
        table.create(connection, checkfirst=True)
        if not inspect(connection).has_table(table.name):
            raise RuntimeError('Academic course receipt table was not created')
        unique_constraints = inspect(connection).get_unique_constraints(table.name)
        if not any(
            item.get('name') == 'uq_studycoursecreatereceipt_owner_key'
            and item.get('column_names') == ['owner_user_id', 'request_key']
            for item in unique_constraints
        ):
            raise RuntimeError('Academic course receipt unique owner/key constraint is missing')
        result = connection.execute(
            text('UPDATE dental_schema_revision SET version=:version WHERE id=1 AND version=:prior'),
            {'version': ACADEMIC_COURSE_RECEIPT_REVISION, 'prior': PROGRAM_QUERY_INDEX_REVISION},
        )
        if result.rowcount != 1:
            current = connection.execute(text('SELECT version FROM dental_schema_revision WHERE id=1')).scalar()
            if current != ACADEMIC_COURSE_RECEIPT_REVISION:
                raise RuntimeError('Schema changed during Academic course receipt migration')
    logger.warning('migration.academic_course_receipts complete revision=%s', ACADEMIC_COURSE_RECEIPT_REVISION)
    return True




def _upgrade_tooth_chart_observation_indexes(main):
    """Deduplicate current tooth observations and install revision-18 unique indexes."""
    if main.engine.dialect.name not in ("postgresql", "sqlite"):
        return False
    index_specs = (
        ("toothstatus", "patient_id, tooth_number", "uq_toothstatus_patient_tooth"),
        ("toothsurfacestatus", "patient_id, tooth_number, surface", "uq_toothsurfacestatus_patient_tooth_surface"),
    )
    with main.engine.begin() as connection:
        if not inspect(connection).has_table("dental_schema_revision"):
            return False
        for table_name, _columns, _index_name in index_specs:
            if not inspect(connection).has_table(table_name):
                raise RuntimeError(f"Tooth chart migration requires {table_name}")
        revision = connection.execute(text("SELECT version FROM dental_schema_revision WHERE id=1")).scalar()
        if revision in (TOOTH_CHART_OBSERVATION_REVISION, REVISION):
            for table_name, columns, index_name in index_specs:
                indexes = inspect(connection).get_indexes(table_name)
                if not any(item.get("name") == index_name and item.get("unique")
                           and item.get("column_names") == [part.strip() for part in columns.split(",")]
                           for item in indexes):
                    raise RuntimeError(f"Tooth chart unique index {index_name} is missing")
            return True
        if revision != ACADEMIC_COURSE_RECEIPT_REVISION:
            return False
        if main.engine.dialect.name == "postgresql":
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"),
                               {"lock_key": TOOTH_CHART_OBSERVATION_LOCK})
            revision = connection.execute(text("SELECT version FROM dental_schema_revision WHERE id=1")).scalar()
            if revision == TOOTH_CHART_OBSERVATION_REVISION:
                return True
            if revision != ACADEMIC_COURSE_RECEIPT_REVISION:
                raise RuntimeError("Schema changed during tooth chart observation migration")
            connection.execute(text(
                "LOCK TABLE toothstatus, toothsurfacestatus IN SHARE ROW EXCLUSIVE MODE"
            ))
        for table_name, columns, index_name in index_specs:
            connection.execute(text(f"""
                DELETE FROM {table_name}
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY {columns}
                            ORDER BY CASE WHEN updated_at IS NULL THEN 1 ELSE 0 END,
                                     updated_at DESC, id DESC
                        ) AS duplicate_rank
                        FROM {table_name}
                    ) AS ranked
                    WHERE duplicate_rank > 1
                )
            """))
            connection.execute(text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})"
            ))
            indexes = inspect(connection).get_indexes(table_name)
            if not any(item.get("name") == index_name and item.get("unique")
                       and item.get("column_names") == [part.strip() for part in columns.split(",")]
                       for item in indexes):
                raise RuntimeError(f"Tooth chart unique index {index_name} was not created")
        result = connection.execute(text(
            "UPDATE dental_schema_revision SET version=:version WHERE id=1 AND version=:prior"
        ), {"version": TOOTH_CHART_OBSERVATION_REVISION, "prior": ACADEMIC_COURSE_RECEIPT_REVISION})
        if result.rowcount != 1:
            current = connection.execute(text("SELECT version FROM dental_schema_revision WHERE id=1")).scalar()
            if current != TOOTH_CHART_OBSERVATION_REVISION:
                raise RuntimeError("Schema changed during tooth chart observation migration")
    logger.warning("migration.tooth_chart_observation_indexes complete revision=%s",
                   TOOTH_CHART_OBSERVATION_REVISION)
    return True


def _upgrade_treatment_history_index(main):
    """Install the owner/patient ordered treatment-history index and advance revision 19.

    PostgreSQL builds the index concurrently under a session advisory lock. SQLite
    uses a short transactional CREATE INDEX for deterministic local/API tests.
    """
    dialect = main.engine.dialect.name
    if dialect not in ("postgresql", "sqlite"):
        return False
    index_name = "ix_treatment_patient_created_id"
    expected_columns = ["patient_id", "created_at", "id"]

    if dialect == "postgresql":
        with main.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("SET lock_timeout = '10s'"))
            connection.execute(text("SET statement_timeout = '10min'"))
            connection.execute(
                text("SELECT pg_advisory_lock(:lock_key)"),
                {"lock_key": TREATMENT_HISTORY_INDEX_LOCK},
            )
            try:
                if not inspect(connection).has_table("dental_schema_revision"):
                    return False
                if not inspect(connection).has_table("treatment"):
                    raise RuntimeError("Treatment history index migration requires treatment")
                revision = connection.execute(
                    text("SELECT version FROM dental_schema_revision WHERE id=1")
                ).scalar()
                valid = connection.execute(
                    text("SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(:name)"),
                    {"name": index_name},
                ).scalar()
                if revision in (TREATMENT_HISTORY_INDEX_REVISION, REVISION):
                    columns = inspect(connection).get_indexes("treatment")
                    if valid is not True or not any(
                        item.get("name") == index_name and item.get("column_names") == expected_columns
                        for item in columns
                    ):
                        raise RuntimeError("Treatment history index is missing, invalid or has wrong columns at revision 19")
                    return True
                if revision != TOOTH_CHART_OBSERVATION_REVISION:
                    return False
                if valid is False:
                    connection.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}"))
                    valid = None
                if valid is not True:
                    connection.execute(text(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_treatment_patient_created_id "
                        "ON treatment (patient_id, created_at, id)"
                    ))
                valid = connection.execute(
                    text("SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(:name)"),
                    {"name": index_name},
                ).scalar()
                if valid is not True:
                    raise RuntimeError("Treatment history index was not built validly")
                columns = inspect(connection).get_indexes("treatment")
                if not any(item.get("name") == index_name and item.get("column_names") == expected_columns
                           for item in columns):
                    raise RuntimeError("Treatment history index columns do not match the query")
                result = connection.execute(text(
                    "UPDATE dental_schema_revision SET version=:version WHERE id=1 AND version=:prior"
                ), {"version": TREATMENT_HISTORY_INDEX_REVISION,
                    "prior": TOOTH_CHART_OBSERVATION_REVISION})
                if result.rowcount != 1:
                    current = connection.execute(
                        text("SELECT version FROM dental_schema_revision WHERE id=1")
                    ).scalar()
                    if current != TREATMENT_HISTORY_INDEX_REVISION:
                        raise RuntimeError("Schema changed during treatment history index migration")
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": TREATMENT_HISTORY_INDEX_LOCK},
                )
    else:
        with main.engine.begin() as connection:
            if not inspect(connection).has_table("dental_schema_revision"):
                return False
            if not inspect(connection).has_table("treatment"):
                raise RuntimeError("Treatment history index migration requires treatment")
            revision = connection.execute(
                text("SELECT version FROM dental_schema_revision WHERE id=1")
            ).scalar()
            indexes = inspect(connection).get_indexes("treatment")
            present = any(item.get("name") == index_name and item.get("column_names") == expected_columns
                          for item in indexes)
            if revision in (TREATMENT_HISTORY_INDEX_REVISION, REVISION):
                if not present:
                    raise RuntimeError("Treatment history index is missing at revision 19")
                return True
            if revision != TOOTH_CHART_OBSERVATION_REVISION:
                return False
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_treatment_patient_created_id "
                "ON treatment (patient_id, created_at, id)"
            ))
            indexes = inspect(connection).get_indexes("treatment")
            if not any(item.get("name") == index_name and item.get("column_names") == expected_columns
                       for item in indexes):
                raise RuntimeError("Treatment history index columns do not match the query")
            result = connection.execute(text(
                "UPDATE dental_schema_revision SET version=:version WHERE id=1 AND version=:prior"
            ), {"version": TREATMENT_HISTORY_INDEX_REVISION,
                "prior": TOOTH_CHART_OBSERVATION_REVISION})
            if result.rowcount != 1:
                current = connection.execute(
                    text("SELECT version FROM dental_schema_revision WHERE id=1")
                ).scalar()
                if current != TREATMENT_HISTORY_INDEX_REVISION:
                    raise RuntimeError("Schema changed during treatment history index migration")
    logger.warning("migration.treatment_history_index complete revision=%s",
                   TREATMENT_HISTORY_INDEX_REVISION)
    return True




def _program_pending_reminder_index_state(connection, index_name):
    """Return whether a PostgreSQL index is exactly the pending-only run_at index.

    Checking that an index definition merely contains the words STATUS and
    PENDING is insufficient: a predicate such as status IN ('PENDING','FAILED')
    would also pass while retaining terminal jobs in the hot queue.
    """
    row = connection.execute(text(
        "SELECT i.indisvalid, pg_get_expr(i.indpred, i.indrelid), "
        "pg_get_indexdef(i.indexrelid) "
        "FROM pg_index i WHERE i.indexrelid=to_regclass(:name)"
    ), {"name": index_name}).one_or_none()
    if row is None:
        return False, None
    valid, predicate, definition = row
    normalized_predicate = "".join(
        (predicate or "").lower().replace('"', "").split()
    ).replace("(", "").replace(")", "")
    for cast in ("::character varying", "::charactervarying", "::varchar", "::text"):
        normalized_predicate = normalized_predicate.replace(cast, "")
    normalized_definition = "".join(
        (definition or "").lower().replace('"', "").split()
    )
    matches = (
        valid is True
        and normalized_predicate == "status='pending'"
        and "usingbtree(run_at)" in normalized_definition
    )
    return matches, valid


def _upgrade_program_reminder_pending_index(main):
    """Install a compact pending-only due-queue index and advance revision 20.

    The worker claims PENDING reminders ordered by run_at. A broad run_at index
    can walk thousands of old DONE rows before finding a due item when LIMIT is
    present. The partial index contains only claimable rows. PostgreSQL builds it
    concurrently under a session advisory lock; SQLite uses a short transaction.
    """
    dialect = main.engine.dialect.name
    if dialect not in ("postgresql", "sqlite"):
        return False

    index_name = "ix_programreminderjob_pending_run_at"
    legacy_indexes = (
        "ix_programreminderjob_status_run_at",
        "ix_programreminderjob_run_at",
    )

    if dialect == "postgresql":
        with main.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("SET lock_timeout = '10s'"))
            connection.execute(text("SET statement_timeout = '10min'"))
            connection.execute(
                text("SELECT pg_advisory_lock(:lock_key)"),
                {"lock_key": PROGRAM_REMINDER_PENDING_INDEX_LOCK},
            )
            try:
                if not inspect(connection).has_table("dental_schema_revision"):
                    return False
                if not inspect(connection).has_table("programreminderjob"):
                    raise RuntimeError("Program reminder index migration requires programreminderjob")
                revision = connection.execute(
                    text("SELECT version FROM dental_schema_revision WHERE id=1")
                ).scalar()
                if revision not in (TREATMENT_HISTORY_INDEX_REVISION, PROGRAM_REMINDER_PENDING_INDEX_REVISION, REVISION):
                    return False

                expected, valid = _program_pending_reminder_index_state(connection, index_name)
                if not expected:
                    if valid is not None:
                        connection.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}"))
                    connection.execute(text(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_programreminderjob_pending_run_at "
                        "ON programreminderjob (run_at) WHERE status = 'PENDING'"
                    ))

                expected, _ = _program_pending_reminder_index_state(connection, index_name)
                if not expected:
                    raise RuntimeError("Program pending reminder index is missing, invalid or has the wrong predicate")

                # The partial index replaces both broad indexes for the only hot
                # status/run_at paths. Build it first, then remove redundant write cost.
                for legacy_name in legacy_indexes:
                    connection.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {legacy_name}"))

                if revision == TREATMENT_HISTORY_INDEX_REVISION:
                    result = connection.execute(
                        text(
                            "UPDATE dental_schema_revision SET version=:version "
                            "WHERE id=1 AND version=:prior"
                        ),
                        {
                            "version": PROGRAM_REMINDER_PENDING_INDEX_REVISION,
                            "prior": TREATMENT_HISTORY_INDEX_REVISION,
                        },
                    )
                    if result.rowcount != 1:
                        current = connection.execute(
                            text("SELECT version FROM dental_schema_revision WHERE id=1")
                        ).scalar()
                        if current != PROGRAM_REMINDER_PENDING_INDEX_REVISION:
                            raise RuntimeError("Schema changed during Program pending reminder index migration")
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": PROGRAM_REMINDER_PENDING_INDEX_LOCK},
                )
    else:
        with main.engine.begin() as connection:
            if not inspect(connection).has_table("dental_schema_revision"):
                return False
            if not inspect(connection).has_table("programreminderjob"):
                raise RuntimeError("Program reminder index migration requires programreminderjob")
            revision = connection.execute(
                text("SELECT version FROM dental_schema_revision WHERE id=1")
            ).scalar()
            if revision not in (TREATMENT_HISTORY_INDEX_REVISION, PROGRAM_REMINDER_PENDING_INDEX_REVISION, REVISION):
                return False

            definition = connection.execute(
                text("SELECT sql FROM sqlite_master WHERE type='index' AND name=:name"),
                {"name": index_name},
            ).scalar()
            normalized = "".join((definition or "").lower().replace('"', "").split())
            if not (
                "onprogramreminderjob(run_at)" in normalized
                and "wherestatus='pending'" in normalized
            ):
                connection.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_programreminderjob_pending_run_at "
                    "ON programreminderjob (run_at) WHERE status = 'PENDING'"
                ))
            definition = connection.execute(
                text("SELECT sql FROM sqlite_master WHERE type='index' AND name=:name"),
                {"name": index_name},
            ).scalar()
            normalized = "".join((definition or "").lower().replace('"', "").split())
            if not (
                "onprogramreminderjob(run_at)" in normalized
                and "wherestatus='pending'" in normalized
            ):
                raise RuntimeError("SQLite Program pending reminder index is missing or has the wrong predicate")

            for legacy_name in legacy_indexes:
                connection.execute(text(f"DROP INDEX IF EXISTS {legacy_name}"))
            if revision == TREATMENT_HISTORY_INDEX_REVISION:
                result = connection.execute(
                    text(
                        "UPDATE dental_schema_revision SET version=:version "
                        "WHERE id=1 AND version=:prior"
                    ),
                    {
                        "version": PROGRAM_REMINDER_PENDING_INDEX_REVISION,
                        "prior": TREATMENT_HISTORY_INDEX_REVISION,
                    },
                )
                if result.rowcount != 1:
                    current = connection.execute(
                        text("SELECT version FROM dental_schema_revision WHERE id=1")
                    ).scalar()
                    if current != PROGRAM_REMINDER_PENDING_INDEX_REVISION:
                        raise RuntimeError("Schema changed during Program pending reminder index migration")

    logger.warning(
        "migration.program_reminder_pending_index complete revision=%s",
        PROGRAM_REMINDER_PENDING_INDEX_REVISION,
    )
    return True




def _upgrade_approved_anamnesis_schema(main):
    """Create the append-only approved anamnesis ledger and backfill all legacy reviews.

    Backfill is keyset-paged and idempotent. The source Analysis and completed
    VOICE_REVIEW WorkJob remain untouched; the new rows retain their analysis_id.
    """
    if main.engine.dialect.name not in ("postgresql", "sqlite"):
        return False
    from app.approved_anamnesis import ApprovedAnamnesis, parse_approved_fields

    table = ApprovedAnamnesis.__table__
    with main.engine.begin() as connection:
        if main.engine.dialect.name == "postgresql":
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '10min'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(71048243)"))
        if not inspect(connection).has_table("dental_schema_revision"):
            return False
        revision = connection.execute(
            text("SELECT version FROM dental_schema_revision WHERE id=1")
        ).scalar()
        table_exists = inspect(connection).has_table(table.name)
        if revision == APPROVED_ANAMNESIS_REVISION and table_exists:
            for index in table.indexes:
                index.create(connection, checkfirst=True)
            for legacy_index in (
                "ix_approvedanamnesis_owner_patient_field_id",
                "ix_approvedanamnesis_patient_field_id",
                "ix_approvedanamnesis_owner_patient",
                "ix_approvedanamnesis_owner_user_id",
                "ix_approvedanamnesis_patient_id",
                "ix_approvedanamnesis_analysis_id",
                "ix_approvedanamnesis_created_at",
            ):
                connection.execute(text(f"DROP INDEX IF EXISTS {legacy_index}"))
            return True
        # A fresh database starts at the current revision after init_db(); it
        # still needs the additive table created. Existing revision-20 databases
        # are upgraded below and advance to 21 only after the backfill completes.
        if revision not in (PROGRAM_REMINDER_PENDING_INDEX_REVISION, APPROVED_ANAMNESIS_REVISION):
            return False
        for required in ("analysis", "workjob", "patient"):
            if not inspect(connection).has_table(required):
                raise RuntimeError(f"Approved anamnesis migration requires {required}")
        table.create(connection, checkfirst=True)
        for index in table.indexes:
            index.create(connection, checkfirst=True)
        for legacy_index in (
            "ix_approvedanamnesis_owner_patient_field_id",
                "ix_approvedanamnesis_patient_field_id",
            "ix_approvedanamnesis_owner_patient",
            "ix_approvedanamnesis_owner_user_id",
            "ix_approvedanamnesis_patient_id",
            "ix_approvedanamnesis_analysis_id",
            "ix_approvedanamnesis_created_at",
        ):
            connection.execute(text(f"DROP INDEX IF EXISTS {legacy_index}"))

        # Keep memory bounded even for large archives. Each page is ordered by
        # immutable Analysis.id and each legacy analysis/field pair is unique.
        last_id = 0
        insert_sql = text(
            "INSERT INTO approvedanamnesis "
            "(owner_user_id, patient_id, field_key, value, analysis_id, created_at) "
            "VALUES (:owner_user_id, :patient_id, :field_key, :value, :analysis_id, CURRENT_TIMESTAMP) "
            "ON CONFLICT (analysis_id, field_key) DO NOTHING"
        )
        while True:
            page = connection.execute(text(
                "SELECT a.id AS analysis_id, a.patient_id AS patient_id, "
                "w.owner_user_id AS owner_user_id, a.clinical_notes AS clinical_notes "
                "FROM analysis AS a JOIN workjob AS w ON w.resource_id = a.id "
                "JOIN patient AS p ON p.id = a.patient_id AND p.owner_user_id = w.owner_user_id "
                "WHERE a.id > :last_id AND w.resource_type = 'ANALYSIS' "
                "AND w.kind = 'VOICE_REVIEW' AND w.status = 'DONE' "
                "ORDER BY a.id ASC LIMIT 500"
            ), {"last_id": last_id}).mappings().all()
            if not page:
                break
            batch = []
            for source in page:
                for key, value in parse_approved_fields(source["clinical_notes"]).items():
                    batch.append({
                        "owner_user_id": source["owner_user_id"],
                        "patient_id": source["patient_id"],
                        "field_key": key,
                        "value": value,
                        "analysis_id": source["analysis_id"],
                    })
            if batch:
                connection.execute(insert_sql, batch)
            last_id = page[-1]["analysis_id"]

        if revision == PROGRAM_REMINDER_PENDING_INDEX_REVISION:
            result = connection.execute(text(
                "UPDATE dental_schema_revision SET version=:version "
                "WHERE id=1 AND version=:prior"
            ), {"version": APPROVED_ANAMNESIS_REVISION,
                "prior": PROGRAM_REMINDER_PENDING_INDEX_REVISION})
            if result.rowcount != 1:
                current = connection.execute(
                    text("SELECT version FROM dental_schema_revision WHERE id=1")
                ).scalar()
                if current != APPROVED_ANAMNESIS_REVISION:
                    raise RuntimeError("Schema changed during approved anamnesis migration")
    logger.warning("migration.approved_anamnesis complete revision=%s",
                   APPROVED_ANAMNESIS_REVISION)
    return True


def _apply_baseline():
    from app import main
    # Revision 18 enforces one current tooth observation; revision 19 adds the
    # bounded native treatment-history query index.
    if _upgrade_treatment_history_index(main):
        return
    # Revision 20 is a complete baseline. Do not replay the historical init_db
    # DDL when upgrading an already-live database to the additive revision 21.
    if _upgrade_program_reminder_pending_index(main):
        return
    if _upgrade_tooth_chart_observation_indexes(main):
        if not _upgrade_treatment_history_index(main):
            raise RuntimeError("Could not apply treatment history index revision 19")
        return
    _upgrade_learning_schema(main)
    if _upgrade_academic_course_receipts_schema(main):
        if not _upgrade_tooth_chart_observation_indexes(main):
            raise RuntimeError("Could not apply tooth chart observation revision 18")
        if not _upgrade_treatment_history_index(main):
            raise RuntimeError("Could not apply treatment history index revision 19")
        return
    if _upgrade_program_query_indexes(main):
        _upgrade_academic_course_receipts_schema(main)
        if not _upgrade_tooth_chart_observation_indexes(main):
            raise RuntimeError("Could not apply tooth chart observation revision 18")
        if not _upgrade_treatment_history_index(main):
            raise RuntimeError("Could not apply treatment history index revision 19")
        return
    if _upgrade_support_receipts_schema(main):
        _upgrade_program_idempotency_schema(main)
        _upgrade_program_query_indexes(main)
        _upgrade_academic_course_receipts_schema(main)
        if not _upgrade_tooth_chart_observation_indexes(main):
            raise RuntimeError("Could not apply tooth chart observation revision 18")
        if not _upgrade_treatment_history_index(main):
            raise RuntimeError("Could not apply treatment history index revision 19")
        return
    if _upgrade_recent_schema(main):
        _upgrade_program_idempotency_schema(main)
        _upgrade_program_query_indexes(main)
        _upgrade_academic_course_receipts_schema(main)
        if not _upgrade_tooth_chart_observation_indexes(main):
            raise RuntimeError("Could not apply tooth chart observation revision 18")
        if not _upgrade_treatment_history_index(main):
            raise RuntimeError("Could not apply treatment history index revision 19")
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
            connection.execute(text('INSERT INTO dental_schema_revision(id, version) VALUES(1, :version) ON CONFLICT(id) DO UPDATE SET version=excluded.version'), {'version': PROGRAM_REMINDER_PENDING_INDEX_REVISION})
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
    if not _upgrade_program_reminder_pending_index(main):
        raise RuntimeError("Could not apply Program pending reminder index revision 20")
    if not _upgrade_approved_anamnesis_schema(main):
        raise RuntimeError("Could not apply approved anamnesis revision 21")
    from app.expert_social_schema import apply as apply_social_schema
    apply_social_schema(main.engine)


if __name__ == '__main__':
    apply()


