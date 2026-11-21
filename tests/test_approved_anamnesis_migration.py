from types import SimpleNamespace

from sqlalchemy import create_engine, text, select

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

    assert _upgrade_approved_anamnesis_schema(SimpleNamespace(engine=engine)) is True
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT version FROM dental_schema_revision WHERE id=1"
        )).scalar_one() == 21
        rows = connection.execute(select(table)).mappings().all()
        assert len(rows) == 503
        assert rows[0]["owner_user_id"] == 9
        assert rows[0]["patient_id"] == 77
        assert rows[0]["field_key"] == "medical_history"
        assert rows[0]["value"] == "Öykü 1"
        assert rows[0]["analysis_id"] == 1
        assert rows[-1]["analysis_id"] == 503

    # A retry after interruption/redeploy is safe and cannot duplicate records.
    assert _upgrade_approved_anamnesis_schema(SimpleNamespace(engine=engine)) is True
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM approvedanamnesis")).scalar_one() == 503
    engine.dispose()
