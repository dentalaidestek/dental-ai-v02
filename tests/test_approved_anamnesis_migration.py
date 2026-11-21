from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text, select, inspect

from app.approved_anamnesis import ApprovedAnamnesis
from app.migrate import _upgrade_approved_anamnesis_schema


def test_revision_21_backfills_all_completed_voice_reviews_in_bounded_pages():
    engine = create_engine("sqlite://")
    table = ApprovedAnamnesis.__table__
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        ))
        connection.execute(text("INSERT INTO dental_schema_revision(id, version) VALUES (1, 20)"))
        connection.execute(text(
            "CREATE TABLE patient (id INTEGER PRIMARY KEY, owner_user_id INTEGER NOT NULL)"
        ))
        connection.execute(text("INSERT INTO patient(id, owner_user_id) VALUES (77, 9), (78, 10)"))
        connection.execute(text(
            "CREATE TABLE analysis (id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL, clinical_notes TEXT)"
        ))
        connection.execute(text(
            "CREATE TABLE workjob (id INTEGER PRIMARY KEY, owner_user_id INTEGER NOT NULL, "
            "resource_id INTEGER NOT NULL, resource_type VARCHAR NOT NULL, kind VARCHAR NOT NULL, status VARCHAR NOT NULL)"
        ))
        for start in range(1, 504, 1):
            connection.execute(text(
                "INSERT INTO analysis(id, patient_id, clinical_notes) VALUES (:id, 77, :notes)"
            ), {"id": start, "notes": "Sistemik hastalık / hasta beyanı: Öykü " + str(start)})
            connection.execute(text(
                "INSERT INTO workjob(id, owner_user_id, resource_id, resource_type, kind, status) "
                "VALUES (:id, 9, :resource_id, 'ANALYSIS', 'VOICE_REVIEW', 'DONE')"
            ), {"id": start, "resource_id": start})
        # A non-voice analysis and a non-approved note must never enter the ledger.
        connection.execute(text(
            "INSERT INTO analysis(id, patient_id, clinical_notes) VALUES (900, 77, 'Alerji: serbest not')"
        ))
        connection.execute(text(
            "INSERT INTO workjob(id, owner_user_id, resource_id, resource_type, kind, status) "
            "VALUES (900, 9, 900, 'ANALYSIS', 'VISION', 'DONE')"
        ))
        # Even a completed voice receipt must not cross a patient ownership boundary.
        connection.execute(text(
            "INSERT INTO analysis(id, patient_id, clinical_notes) VALUES (901, 78, 'Alerji / hasta beyanı: Başka hasta')"
        ))
        connection.execute(text(
            "INSERT INTO workjob(id, owner_user_id, resource_id, resource_type, kind, status) "
            "VALUES (901, 9, 901, 'ANALYSIS', 'VOICE_REVIEW', 'DONE')"
        ))

    assert _upgrade_approved_anamnesis_schema(SimpleNamespace(engine=engine)) is True
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT version FROM dental_schema_revision WHERE id=1"
        )).scalar_one() == 21
        rows = connection.execute(select(table).order_by(table.c.id)).mappings().all()
        assert len(rows) == 503
        assert rows[0]["owner_user_id"] == 9
        assert rows[0]["patient_id"] == 77
        assert rows[0]["field_key"] == "medical_history"
        assert rows[0]["value"] == "Öykü 1"
        assert rows[0]["analysis_id"] == 1
        assert rows[-1]["analysis_id"] == 503
        assert all(row["created_at"] is not None for row in rows)
        indexes = inspect(connection).get_indexes("approvedanamnesis")
        assert any(item["name"] == "ix_approvedanamnesis_owner_patient_field_id" for item in indexes)

    # A retry after interruption/redeploy is safe and cannot duplicate records.
    assert _upgrade_approved_anamnesis_schema(SimpleNamespace(engine=engine)) is True
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM approvedanamnesis")).scalar_one() == 503
    engine.dispose()

def test_fresh_revision_21_database_still_creates_the_ledger():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        ))
        connection.execute(text("INSERT INTO dental_schema_revision(id, version) VALUES (1, 21)"))
        connection.execute(text(
            "CREATE TABLE patient (id INTEGER PRIMARY KEY, owner_user_id INTEGER NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE analysis (id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL, clinical_notes TEXT)"
        ))
        connection.execute(text(
            "CREATE TABLE workjob (id INTEGER PRIMARY KEY, owner_user_id INTEGER NOT NULL, "
            "resource_id INTEGER NOT NULL, resource_type VARCHAR NOT NULL, kind VARCHAR NOT NULL, status VARCHAR NOT NULL)"
        ))
    assert _upgrade_approved_anamnesis_schema(SimpleNamespace(engine=engine)) is True
    with engine.connect() as connection:
        assert "approvedanamnesis" in inspect(connection).get_table_names()
        indexes = inspect(connection).get_indexes("approvedanamnesis")
        assert any(item["name"] == "ix_approvedanamnesis_owner_patient_field_id" for item in indexes)
    engine.dispose()


def test_revision20_existing_ledger_table_is_still_backfilled():
    engine = create_engine("sqlite://")
    table = ApprovedAnamnesis.__table__
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        ))
        connection.execute(text("INSERT INTO dental_schema_revision(id, version) VALUES (1, 20)"))
        connection.execute(text(
            "CREATE TABLE patient (id INTEGER PRIMARY KEY, owner_user_id INTEGER NOT NULL)"
        ))
        connection.execute(text("INSERT INTO patient(id, owner_user_id) VALUES (77, 9)"))
        connection.execute(text(
            "CREATE TABLE analysis (id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL, clinical_notes TEXT)"
        ))
        connection.execute(text(
            "CREATE TABLE workjob (id INTEGER PRIMARY KEY, owner_user_id INTEGER NOT NULL, "
            "resource_id INTEGER NOT NULL, resource_type VARCHAR NOT NULL, kind VARCHAR NOT NULL, status VARCHAR NOT NULL)"
        ))
        table.create(connection, checkfirst=True)
        connection.execute(text(
            "INSERT INTO analysis(id, patient_id, clinical_notes) VALUES "
            "(1, 77, 'Alerji / hasta beyanı: Penisilin beyanı')"
        ))
        connection.execute(text(
            "INSERT INTO workjob(id, owner_user_id, resource_id, resource_type, kind, status) "
            "VALUES (1, 9, 1, 'ANALYSIS', 'VOICE_REVIEW', 'DONE')"
        ))

    assert _upgrade_approved_anamnesis_schema(SimpleNamespace(engine=engine)) is True
    with engine.connect() as connection:
        row = connection.execute(select(table)).mappings().one()
        assert row["analysis_id"] == 1
        assert row["value"] == "Penisilin beyanı"
        assert row["created_at"] is not None
        assert connection.execute(text(
            "SELECT version FROM dental_schema_revision WHERE id=1"
        )).scalar_one() == 21
    engine.dispose()


def test_require_schema_fails_closed_if_revision21_ledger_is_missing():
    from app.migrate import require_schema

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        ))
        connection.execute(text("INSERT INTO dental_schema_revision(id, version) VALUES (1, 21)"))
    with pytest.raises(RuntimeError, match="approved anamnesis ledger"):
        require_schema(engine)
    engine.dispose()


def test_patient_delete_removes_approved_anamnesis_only_after_owner_authorization(monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, select
    from app import main

    assert main.ApprovedAnamnesis is ApprovedAnamnesis
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    main.SQLModel.metadata.create_all(
        engine,
        tables=[main.Patient.__table__, main.PatientProfile.__table__, ApprovedAnamnesis.__table__],
    )
    with Session(engine) as session:
        session.add(main.Patient(id=77, anonymous_id="P-77", owner_user_id=9))
        session.add(ApprovedAnamnesis(
            owner_user_id=9, patient_id=77, field_key="allergies",
            value="Penisilin alerjisi beyanı", analysis_id=9001,
        ))
        session.commit()

    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(
        main, "get_current_user",
        lambda request: SimpleNamespace(id=int(request.headers.get("x-user", "9")), role="DOCTOR"),
    )
    monkeypatch.setattr(main, "_record_patient_realtime_events", lambda *args: [])
    monkeypatch.setattr(main, "on_loop", lambda *args: None)
    app = FastAPI()
    app.add_api_route("/patients/{patient_id}/delete", main.delete_patient, methods=["POST"])

    with TestClient(app) as client:
        denied = client.post("/patients/77/delete", headers={"x-user": "10"}, follow_redirects=False)
        assert denied.status_code == 403
        with Session(engine) as session:
            assert len(session.exec(select(ApprovedAnamnesis)).all()) == 1

        deleted = client.post("/patients/77/delete", headers={"x-user": "9"}, follow_redirects=False)
        assert deleted.status_code == 303

    with Session(engine) as session:
        assert session.get(main.Patient, 77) is None
        assert session.exec(select(ApprovedAnamnesis)).all() == []
    engine.dispose()

def test_require_schema_fails_closed_if_latest_history_index_is_missing():
    from app.migrate import require_schema

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
        ))
        connection.execute(text("INSERT INTO dental_schema_revision(id, version) VALUES (1, 21)"))
        connection.execute(text(
            "CREATE TABLE approvedanamnesis (id INTEGER PRIMARY KEY, owner_user_id INTEGER NOT NULL, "
            "patient_id INTEGER NOT NULL, field_key VARCHAR NOT NULL, value VARCHAR NOT NULL, "
            "analysis_id INTEGER NOT NULL, created_at DATETIME NOT NULL)"
        ))
    with pytest.raises(RuntimeError, match="approved anamnesis query index"):
        require_schema(engine)
    engine.dispose()
