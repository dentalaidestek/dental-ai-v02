import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app import main, mobile_api

BASE = "/api/mobile/v1"


def _build(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "mobile-dashboard.db"),
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(mobile_api, "engine", engine)
    return TestClient(main.app), engine


def _user_and_token(session, username):
    user = main.User(
        username=username,
        role="DOCTOR",
        display_name=username,
        is_active=True,
        email_verified_at=main._utcnow_naive(),
    )
    session.add(user)
    session.commit()
    token = "dashboard-" + username + "-" + "t" * 24
    session.add(main.SessionToken(
        token_hash=main.hash_session_token(token),
        user_id=user.id,
        expires_at=main._utcnow_naive() + main.timedelta(days=1),
    ))
    session.commit()
    return int(user.id), token


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_dashboard_is_private_owner_scoped_and_returns_only_three_minimal_analyses(
    monkeypatch, tmp_path
):
    client, engine = _build(monkeypatch, tmp_path)
    with Session(engine, expire_on_commit=False) as session:
        owner_id, owner_token = _user_and_token(session, "dashboard-owner")
        other_id, other_token = _user_and_token(session, "dashboard-other")
        owner_patient = main.Patient(
            anonymous_id="PAT-OWNER",
            owner_user_id=owner_id,
            first_name="Owner",
            last_name="Patient",
            tc_kimlik_no="11111111110",
            phone="05550000001",
        )
        other_patient = main.Patient(
            anonymous_id="PAT-OTHER",
            owner_user_id=other_id,
            first_name="Other",
            last_name="Patient",
            tc_kimlik_no="22222222220",
            phone="05550000002",
        )
        session.add_all([owner_patient, other_patient])
        session.commit()
        owner_patient_id = owner_patient.id
        other_patient_id = other_patient.id
        for index in range(20):
            session.add(main.Analysis(
                patient_id=owner_patient_id,
                tooth_number="36",
                clinical_notes="private clinical note " + str(index),
                status="AI_ANALYZED",
            ))
        session.add(main.Analysis(
            patient_id=other_patient_id,
            tooth_number="11",
            clinical_notes="other account clinical note",
            status="AI_ANALYZED",
        ))
        session.commit()

    queries = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda conn, cursor, statement, params, context, many:
            queries.append(statement)
            if statement.lstrip().upper().startswith("SELECT")
            else None,
    )
    response = client.get(
        BASE + "/dashboard",
        headers={"Authorization": "Bearer " + owner_token},
    )
    assert response.status_code == 200, response.text
    assert response.headers.get("cache-control") == "private, no-store"
    assert response.headers.get("pragma") == "no-cache"
    assert "authorization" in response.headers.get("vary", "").lower()

    body = response.json()
    analyses = body["recent_analyses"]
    assert len(analyses) == 3
    assert len({item["id"] for item in analyses}) == 3
    assert all(item["patient_id"] == owner_patient_id for item in analyses)
    assert all(item["patient_name"] == "Owner Patient" for item in analyses)
    assert not any(item["patient_id"] == other_patient_id for item in analyses)
    assert all(
        set(item) == {
            "id", "patient_id", "patient_name", "tooth_number", "status", "created_at"
        }
        for item in analyses
    )
    assert all("clinical_notes" not in item for item in analyses)
    assert all("tc_kimlik_no" not in item and "phone" not in item for item in analyses)
    assert body["dashboard_event"] is None
    assert body["dashboard_event_label"] == "Bugün"
    # A larger account does not turn the dashboard into a per-analysis query loop.
    assert len(queries) <= 12

    other_response = client.get(
        BASE + "/dashboard",
        headers={"Authorization": "Bearer " + other_token},
    )
    assert other_response.status_code == 200
    other_analyses = other_response.json()["recent_analyses"]
    assert len(other_analyses) == 1
    assert other_analyses[0]["patient_id"] == other_patient_id

    unauthenticated = client.get(BASE + "/dashboard")
    assert unauthenticated.status_code == 401
    engine.dispose()
