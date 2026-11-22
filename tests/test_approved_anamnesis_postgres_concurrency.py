import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, func, select, text

from app.approved_anamnesis import ApprovedAnamnesis


DATABASE_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="PostgreSQL concurrency service is not configured")


def test_same_patient_approvals_serialize_and_keep_both_analysis_sources():
    engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=0)
    schema = "anamnesis_concurrency_" + uuid.uuid4().hex[:10]
    metadata = MetaData()
    patient = Table(
        "patient", metadata,
        Column("id", Integer, primary_key=True),
        Column("owner_user_id", Integer, nullable=False),
        schema=schema,
    )
    analysis = Table(
        "analysis", metadata,
        Column("id", Integer, primary_key=True),
        Column("patient_id", Integer, nullable=False),
        schema=schema,
    )
    ledger = ApprovedAnamnesis.__table__.to_metadata(metadata, schema=schema)
    first_locked = Event()
    release_first = Event()
    second_backend_pid = Event()
    backend = {}

    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(patient.insert().values(id=1, owner_user_id=9))

    def first_approval():
        with engine.begin() as connection:
            connection.execute(select(patient.c.id).where(patient.c.id == 1).with_for_update()).one()
            first_locked.set()
            if not release_first.wait(15):
                raise TimeoutError("second approval never reached the lock test")
            connection.execute(analysis.insert().values(id=101, patient_id=1))
            connection.execute(ledger.insert().values(
                owner_user_id=9, patient_id=1, field_key="allergies",
                value="İlk onay", analysis_id=101,
            ))

    def second_approval():
        if not first_locked.wait(15):
            raise TimeoutError("first approval did not acquire the patient lock")
        with engine.begin() as connection:
            backend["pid"] = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
            second_backend_pid.set()
            connection.execute(select(patient.c.id).where(patient.c.id == 1).with_for_update()).one()
            connection.execute(analysis.insert().values(id=102, patient_id=1))
            connection.execute(ledger.insert().values(
                owner_user_id=9, patient_id=1, field_key="allergies",
                value="İkinci onay", analysis_id=102,
            ))

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(first_approval)
            second = pool.submit(second_approval)
            assert second_backend_pid.wait(10)
            deadline = time.monotonic() + 10
            blocked = False
            while time.monotonic() < deadline:
                with engine.connect() as connection:
                    blocked = connection.execute(text(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE pid=:pid AND wait_event_type='Lock')"
                    ), {"pid": backend["pid"]}).scalar_one()
                if blocked:
                    break
                time.sleep(0.05)
            assert blocked, "second approval did not wait on the patient row lock"
            release_first.set()
            first.result(timeout=15)
            second.result(timeout=15)

        # Simulate a delayed legacy backfill and a corrupt cross-owner row.
        # The web/native reader must choose by source Analysis identity and still
        # scope by both patient and owner, never by ledger insertion order alone.
        with engine.begin() as connection:
            connection.execute(ledger.insert().values(
                owner_user_id=9, patient_id=1, field_key="allergies",
                value="Gecikmiş eski backfill", analysis_id=100,
            ))
            connection.execute(ledger.insert().values(
                owner_user_id=10, patient_id=1, field_key="allergies",
                value="Başka sahibin kaydı", analysis_id=999,
            ))

        with engine.connect() as connection:
            rows = connection.execute(
                select(ledger.c.value, ledger.c.analysis_id)
                .where(ledger.c.owner_user_id == 9, ledger.c.patient_id == 1,
                       ledger.c.field_key == "allergies")
                .order_by(ledger.c.id)
            ).all()
            latest = (
                select(ledger.c.field_key,
                       func.max(ledger.c.analysis_id).label("latest_analysis_id"))
                .where(ledger.c.owner_user_id == 9, ledger.c.patient_id == 1)
                .group_by(ledger.c.field_key)
                .subquery()
            )
            current = connection.execute(
                select(ledger.c.value, ledger.c.analysis_id)
                .join(latest,
                      (ledger.c.field_key == latest.c.field_key)
                      & (ledger.c.analysis_id == latest.c.latest_analysis_id))
                .where(ledger.c.owner_user_id == 9, ledger.c.patient_id == 1,
                       ledger.c.field_key == "allergies")
            ).one()
        assert rows == [
            ("İlk onay", 101),
            ("İkinci onay", 102),
            ("Gecikmiş eski backfill", 100),
        ]
        assert current == ("İkinci onay", 102)
    finally:
        release_first.set()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
