from types import SimpleNamespace
import re
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from test_mobile_chat_actions import chat
from app import main, mobile_api, migrate


def test_web_and_native_tooth_writes_converge_on_one_owner_scoped_row(chat, monkeypatch):
    client, engine = chat
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(mobile_api, "engine", engine)
    with Session(engine) as session:
        session.add(main.Patient(id=8, anonymous_id="SYNTHETIC-TOOTH-8", owner_user_id=1))
        session.commit()
    web_user = main.User(
        id=1, username="chat-user-1", display_name="Synthetic 1", role="DOCTOR",
        is_active=True, email_verified_at=main._utcnow_naive(),
    )
    monkeypatch.setattr(main, "get_current_user", lambda _request: web_user)
    web = client.post(
        "/patients/8/teeth/36",
        data={"status": "CARIES", "note": "web observation", "surface": "MESIAL"},
        follow_redirects=False,
    )
    assert web.status_code == 303, web.text
    snapshot = client.get("/api/mobile/v1/patients/8")
    assert snapshot.status_code == 200, snapshot.text
    tooth_revision = next(item["revision"] for item in snapshot.json()["teeth"]
                          if item["tooth_number"] == "36")
    surface_revision = next(item["revision"] for item in snapshot.json()["surfaces"]
                            if item["tooth_number"] == "36" and item["surface"] == "MESIAL")
    surface = client.put(
        "/api/mobile/v1/patients/8/teeth/36/surfaces/MESIAL",
        json={"status": "FILLING", "note": "native surface observation",
              "expected_revision": surface_revision},
    )
    assert surface.status_code == 200, surface.text
    tooth = client.post(
        "/api/mobile/v1/patients/8/teeth/36",
        json={"status": "ROOT_CANAL", "note": "native whole-tooth observation",
              "surfaces": ["MESIAL", "DISTAL"], "expected_revision": tooth_revision},
    )
    assert tooth.status_code == 200, tooth.text
    with Session(engine) as session:
        teeth = session.exec(select(main.ToothStatus).where(main.ToothStatus.patient_id == 8)).all()
        surfaces = session.exec(select(main.ToothSurfaceStatus).where(main.ToothSurfaceStatus.patient_id == 8)).all()
        assert len(teeth) == 1 and teeth[0].tooth_number == "36"
        assert teeth[0].status == "ROOT_CANAL"
        assert len(surfaces) == 2
        by_surface = {item.surface: item for item in surfaces}
        assert by_surface["MESIAL"].status == "ROOT_CANAL"
        assert by_surface["DISTAL"].status == "ROOT_CANAL"
        assert by_surface["MESIAL"].note == "native whole-tooth observation"
    client.headers["Authorization"] = "Bearer token3"
    denied = client.put(
        "/api/mobile/v1/patients/8/teeth/36/surfaces/MESIAL",
        json={"status": "HEALTHY", "note": "must not be stored", "expected_revision": None},
    )
    assert denied.status_code == 404


def test_revision_18_deduplicates_legacy_current_state_and_adds_unique_indexes(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "legacy-tooth-chart.db"))
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE dental_schema_revision (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"))
        connection.execute(text("INSERT INTO dental_schema_revision(id, version) VALUES (1, 17)"))
        connection.execute(text("""
            CREATE TABLE toothstatus (
                id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL, tooth_number VARCHAR NOT NULL,
                status VARCHAR NOT NULL, note TEXT, updated_at TIMESTAMP
            )
        """))
        connection.execute(text("""
            CREATE TABLE toothsurfacestatus (
                id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL, tooth_number VARCHAR NOT NULL,
                surface VARCHAR NOT NULL, status VARCHAR NOT NULL, note TEXT, updated_at TIMESTAMP
            )
        """))
        connection.execute(text("""
            INSERT INTO toothstatus(id, patient_id, tooth_number, status, note, updated_at) VALUES
            (1, 8, '36', 'CARIES', 'older', '2026-11-16 09:00:00'),
            (2, 8, '36', 'FILLING', 'newer', '2026-11-17 09:00:00'),
            (3, 9, '36', 'HEALTHY', 'other owner', '2026-11-17 09:00:00')
        """))
        connection.execute(text("""
            INSERT INTO toothsurfacestatus(id, patient_id, tooth_number, surface, status, note, updated_at) VALUES
            (11, 8, '36', 'MESIAL', 'CARIES', 'older', '2026-11-16 09:00:00'),
            (12, 8, '36', 'MESIAL', 'CROWN', 'newer', '2026-11-17 09:00:00'),
            (13, 8, '36', 'DISTAL', 'HEALTHY', NULL, '2026-11-17 09:00:00')
        """))
    assert migrate._upgrade_tooth_chart_observation_indexes(SimpleNamespace(engine=engine)) is True
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version FROM dental_schema_revision WHERE id=1")).scalar_one() == 18
        assert connection.execute(text("SELECT patient_id, tooth_number, status, note FROM toothstatus ORDER BY id")).all() == [
            (8, "36", "FILLING", "newer"), (9, "36", "HEALTHY", "other owner")
        ]
        assert connection.execute(text("SELECT patient_id, tooth_number, surface, status, note FROM toothsurfacestatus ORDER BY id")).all() == [
            (8, "36", "MESIAL", "CROWN", "newer"), (8, "36", "DISTAL", "HEALTHY", None)
        ]
        for table, name, columns in [
            ("toothstatus", "uq_toothstatus_patient_tooth", ["patient_id", "tooth_number"]),
            ("toothsurfacestatus", "uq_toothsurfacestatus_patient_tooth_surface",
             ["patient_id", "tooth_number", "surface"]),
        ]:
            assert any(i["name"] == name and i["unique"] and i["column_names"] == columns
                       for i in inspect(connection).get_indexes(table))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO toothstatus(patient_id,tooth_number,status,updated_at) VALUES (8,'36','OTHER','2026-11-18')"
            ))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO toothsurfacestatus(patient_id,tooth_number,surface,status,updated_at) VALUES (8,'36','MESIAL','OTHER','2026-11-18')"
            ))



def test_native_tooth_and_surface_compare_and_swap_rejects_stale_devices(chat, monkeypatch):
    client, engine = chat
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(mobile_api, "engine", engine)
    with Session(engine) as session:
        session.add(main.Patient(id=18, anonymous_id="SYNTHETIC-CAS-18", owner_user_id=1))
        session.commit()

    snapshot = client.get("/api/mobile/v1/patients/18")
    assert snapshot.status_code == 200, snapshot.text
    tooth_revision = next((item["revision"] for item in snapshot.json()["teeth"]
                           if item["tooth_number"] == "36"), None)
    assert tooth_revision is None

    first = client.post("/api/mobile/v1/patients/18/teeth/36", json={
        "status": "CARIES", "note": "first device", "expected_revision": None,
    })
    assert first.status_code == 200, first.text
    assert len(first.json()["revision"]) == 64

    stale_create = client.post("/api/mobile/v1/patients/18/teeth/36", json={
        "status": "HEALTHY", "note": "stale device", "expected_revision": None,
    })
    assert stale_create.status_code == 409, stale_create.text

    latest = client.get("/api/mobile/v1/patients/18")
    current_revision = next(item["revision"] for item in latest.json()["teeth"]
                            if item["tooth_number"] == "36")
    second = client.post("/api/mobile/v1/patients/18/teeth/36", json={
        "status": "FILLING", "note": "second device", "expected_revision": current_revision,
    })
    assert second.status_code == 200, second.text
    stale_update = client.post("/api/mobile/v1/patients/18/teeth/36", json={
        "status": "HEALTHY", "note": "old snapshot", "expected_revision": current_revision,
    })
    assert stale_update.status_code == 409, stale_update.text

    empty_surface = client.put("/api/mobile/v1/patients/18/teeth/36/surfaces/MESIAL", json={
        "status": "CARIES", "note": "surface first device", "expected_revision": None,
    })
    assert empty_surface.status_code == 200, empty_surface.text
    stale_surface_create = client.put("/api/mobile/v1/patients/18/teeth/36/surfaces/MESIAL", json={
        "status": "HEALTHY", "note": "stale surface device", "expected_revision": None,
    })
    assert stale_surface_create.status_code == 409, stale_surface_create.text

    latest = client.get("/api/mobile/v1/patients/18")
    surface_revision = next(item["revision"] for item in latest.json()["surfaces"]
                            if item["tooth_number"] == "36" and item["surface"] == "MESIAL")
    updated_surface = client.put("/api/mobile/v1/patients/18/teeth/36/surfaces/MESIAL", json={
        "status": "FILLING", "note": "fresh surface edit", "expected_revision": surface_revision,
    })
    assert updated_surface.status_code == 200, updated_surface.text
    stale_surface_update = client.put("/api/mobile/v1/patients/18/teeth/36/surfaces/MESIAL", json={
        "status": "HEALTHY", "note": "old surface snapshot", "expected_revision": surface_revision,
    })
    assert stale_surface_update.status_code == 409, stale_surface_update.text



def test_web_tooth_chart_posts_snapshot_revision_and_rejects_stale_form(chat, monkeypatch):
    client, engine = chat
    monkeypatch.setattr(main, "engine", engine)
    with Session(engine) as session:
        session.add(main.Patient(id=28, anonymous_id="SYNTHETIC-WEB-CAS-28", owner_user_id=1))
        session.commit()
    web_user = main.User(
        id=1, username="chat-user-1", display_name="Synthetic 1", role="DOCTOR",
        is_active=True, email_verified_at=main._utcnow_naive(),
    )
    monkeypatch.setattr(main, "get_current_user", lambda _request: web_user)
    page = client.get("/patients/28/teeth")
    assert page.status_code == 200, page.text
    match = re.search(r'name="expected_revision" id="toothExpectedRevision" value="([a-f0-9]{64})"', page.text)
    assert match, "web chart must bind the selected tooth's snapshot revision"
    revision = match.group(1)
    first = client.post("/patients/28/teeth/36", data={
        "status": "CARIES", "note": "web first", "expected_revision": revision,
    }, follow_redirects=False)
    assert first.status_code == 303, first.text
    stale = client.post("/patients/28/teeth/36", data={
        "status": "HEALTHY", "note": "stale web form", "expected_revision": revision,
    }, follow_redirects=False)
    assert stale.status_code == 409, stale.text
    with Session(engine) as session:
        tooth = session.exec(select(main.ToothStatus).where(
            main.ToothStatus.patient_id == 28, main.ToothStatus.tooth_number == "36"
        )).one()
        assert tooth.status == "CARIES"
