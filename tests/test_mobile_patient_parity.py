from test_mobile_chat_actions import chat, _SESSION_TOKEN
import inspect

from app import main, mobile_analysis_api, mobile_api, mobile_modern_api_v3
from app.work_jobs import WorkJob, prune_history
from sqlmodel import Session, select
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
import io
import json
import pytest


@pytest.fixture(autouse=True)
def _patient_media_receipt_secret(monkeypatch):
    monkeypatch.setenv("PATIENT_MEDIA_RECEIPT_KEY", "11" * 32)


def test_tooth_treatment_history_is_bounded_owner_and_tooth_scoped_with_snapshot_cursor(chat):
    client, engine = chat
    base = datetime(2026, 11, 19, 9, 0, 0)
    with Session(engine) as session:
        session.add_all([
            main.Patient(id=81, anonymous_id="SYNTHETIC-TOOTH-HISTORY-81", owner_user_id=1),
            main.Patient(id=82, anonymous_id="SYNTHETIC-TOOTH-HISTORY-82", owner_user_id=1),
        ])
        session.add_all([
            main.Treatment(
                id=1000 + index, patient_id=81, tooth_number="36",
                treatment_name=f"36 treatment {index}",
                created_at=base + timedelta(minutes=index),
            )
            for index in range(25)
        ])
        session.add_all([
            main.Treatment(
                id=1100 + index, patient_id=81, tooth_number="37",
                treatment_name=f"37 treatment {index}",
                created_at=base + timedelta(minutes=30 + index),
            )
            for index in range(2)
        ])
        session.commit()

    first = client.get("/api/mobile/v1/patients/81/teeth/36/treatments")
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "private, no-store"
    assert len(first.json()["items"]) == 20
    assert all(item["tooth_number"] == "36" for item in first.json()["items"])
    assert first.json()["next_cursor"]

    # A newer write after page one must not leak into the original history snapshot.
    with Session(engine) as session:
        session.add(main.Treatment(
            id=2000, patient_id=81, tooth_number="36",
            treatment_name="newer concurrent treatment",
            created_at=base + timedelta(days=1),
        ))
        session.commit()

    cursor = first.json()["next_cursor"]
    second = client.get(
        "/api/mobile/v1/patients/81/teeth/36/treatments",
        params={"cursor": cursor},
    )
    assert second.status_code == 200, second.text
    assert len(second.json()["items"]) == 5
    assert second.json()["next_cursor"] is None
    assert all(item["tooth_number"] == "36" for item in second.json()["items"])
    all_ids = [item["id"] for item in first.json()["items"] + second.json()["items"]]
    assert len(all_ids) == 25
    assert len(set(all_ids)) == 25
    assert 2000 not in all_ids

    other_tooth = client.get(
        "/api/mobile/v1/patients/81/teeth/37/treatments",
        params={"cursor": cursor},
    )
    assert other_tooth.status_code == 422, other_tooth.text
    other_patient = client.get(
        "/api/mobile/v1/patients/82/teeth/36/treatments",
        params={"cursor": cursor},
    )
    assert other_patient.status_code == 422, other_patient.text
    assert len(client.get("/api/mobile/v1/patients/81/teeth/37/treatments").json()["items"]) == 2
    assert client.get("/api/mobile/v1/patients/81/teeth/19/treatments").status_code == 422

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    assert client.get("/api/mobile/v1/patients/81/teeth/36/treatments").status_code == 404


def test_tooth_chart_initial_focus_matches_web_latest_analysis_and_is_owner_scoped(chat, monkeypatch):
    client, engine = chat
    monkeypatch.setattr(mobile_api, "engine", engine)
    base = datetime(2026, 11, 16, 12, 0, 0)
    with Session(engine) as session:
        session.add_all([
            main.Patient(id=8, anonymous_id="SYNTHETIC-FOCUS-8", owner_user_id=1),
            main.Patient(id=9, anonymous_id="SYNTHETIC-FOCUS-9", owner_user_id=2),
            main.Patient(id=10, anonymous_id="SYNTHETIC-FOCUS-10", owner_user_id=1),
        ])
        session.add_all([
            main.Analysis(id=101, patient_id=8, tooth_number="36", status="AI_ANALYZED", created_at=base),
            main.Analysis(id=102, patient_id=8, tooth_number="55", status="AI_FINAL", created_at=base.replace(minute=1)),
            # Same timestamp is resolved by descending id, matching the web query.
            main.Analysis(id=103, patient_id=8, tooth_number="18", status="VISION_READY", created_at=base.replace(minute=2)),
            main.Analysis(id=107, patient_id=8, tooth_number="44", status="AI_FINAL", created_at=base.replace(minute=2)),
            main.Analysis(id=104, patient_id=8, tooth_number="48", status="DRAFT", created_at=base.replace(minute=3)),
            main.Analysis(id=105, patient_id=8, tooth_number="99", status="AI_FINAL", created_at=base.replace(minute=4)),
            main.Analysis(id=106, patient_id=9, tooth_number="21", status="AI_FINAL", created_at=base.replace(minute=5)),
        ])
        session.commit()

    response = client.get("/api/mobile/v1/patients/8/tooth-chart/focus")
    assert response.status_code == 200, response.text
    assert response.json() == {"latest_analysis_tooth": "44"}

    # An owned patient without an eligible analysis is an explicit empty focus.
    empty = client.get("/api/mobile/v1/patients/10/tooth-chart/focus")
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"latest_analysis_tooth": None}

    # Existing patients belonging to another account remain indistinguishable from missing IDs.
    assert client.get("/api/mobile/v1/patients/9/tooth-chart/focus").status_code == 404
    assert client.get("/api/mobile/v1/patients/999/tooth-chart/focus").status_code == 404


def test_patient_history_filters_tooth_and_marks_only_confirmed_voice_reviews(chat, monkeypatch):
    client, engine = chat
    monkeypatch.setattr(mobile_analysis_api, "engine", engine)
    with Session(engine) as session:
        session.add(main.Patient(id=8, anonymous_id="SYNTHETIC-8", owner_user_id=1))
        session.add(main.Patient(id=9, anonymous_id="SYNTHETIC-9", owner_user_id=2))
        session.add_all([
            main.Analysis(id=11, patient_id=8, tooth_number="36", status="DRAFT"),
            main.Analysis(id=12, patient_id=8, tooth_number="35", status="DRAFT"),
            main.Analysis(id=13, patient_id=9, tooth_number="36", status="DRAFT"),
        ])
        session.add_all([
            WorkJob(
                owner_user_id=1, resource_id=11, resource_type="ANALYSIS",
                kind="VOICE_REVIEW", status="DONE", source_hash="synthetic-hash",
                dedupe_key="synthetic-parity-done", payload_json="{}",
            ),
            WorkJob(
                owner_user_id=1, resource_id=12, resource_type="ANALYSIS",
                kind="VOICE_REVIEW", status="RUNNING", source_hash="synthetic-hash",
                dedupe_key="synthetic-parity-running", payload_json="{}",
            ),
            WorkJob(
                owner_user_id=2, resource_id=13, resource_type="ANALYSIS",
                kind="VOICE_REVIEW", status="DONE", source_hash="synthetic-hash",
                dedupe_key="synthetic-parity-admin", payload_json="{}",
            ),
        ])
        session.commit()

    # The history contract lives in the canonical router. The modern v3
    # adapter must not leave a duplicate GET route; actual app dispatch below
    # verifies that the prefixed URL reaches the canonical JSON contract.
    # Router paths already carry the mounted prefix in FastAPI 0.141;
    # matching the full "/api/mobile/v1/analyses" is the canonical contract.
    canonical_routes = [
        route for route in mobile_analysis_api.router.routes
        if getattr(route, "path", "").rstrip("/") == "/api/mobile/v1/analyses"
        and "GET" in (getattr(route, "methods", set()) or set())
    ]
    shadow_routes = [
        route for route in mobile_modern_api_v3.router.routes
        if getattr(route, "path", "").rstrip("/") == "/api/mobile/v1/analyses"
        and "GET" in (getattr(route, "methods", set()) or set())
    ]
    assert mobile_analysis_api.router.prefix == "/api/mobile/v1"
    assert len(canonical_routes) == 1
    assert canonical_routes[0].endpoint.__module__ == "app.mobile_analysis_api"
    # The v3 surface may expose the same path but only as a thin delegation:
    # its route handler must call the single canonical implementation object,
    # never a parallel clinical logic copy.
    assert getattr(mobile_modern_api_v3, "mobile_analysis_history_impl") is mobile_analysis_api.mobile_analysis_history
    for shadow in shadow_routes:
        assert "mobile_analysis_history_impl" in inspect.getsource(shadow.endpoint)
    filtered = client.get("/api/mobile/v1/analyses?patient_id=8&tooth_number=36")
    assert filtered.status_code == 200, filtered.text
    assert filtered.headers["cache-control"] == "private, no-store"
    assert "authorization" in filtered.headers.get("vary", "").lower()
    assert filtered.json()["total"] == 1
    assert [(item["id"], item["is_voice_review"]) for item in filtered.json()["items"]] == [(11, True)]

    first = client.get("/api/mobile/v1/analyses?patient_id=8&limit=1")
    assert first.status_code == 200, first.text
    assert first.json()["total"] == 2
    assert [(item["id"], item["is_voice_review"]) for item in first.json()["items"]] == [(12, False)]
    assert first.json()["next_before"] == 12

    second = client.get(
        "/api/mobile/v1/analyses",
        params={"patient_id": 8, "limit": 1, "before": first.json()["next_before"]},
    )
    assert second.status_code == 200, second.text
    assert second.json()["total"] == 2
    assert [(item["id"], item["is_voice_review"]) for item in second.json()["items"]] == [(11, True)]
    assert second.json()["next_before"] is None

    # Another clinician cannot enumerate this patient's history.
    assert client.get("/api/mobile/v1/analyses?patient_id=9").status_code == 404
    assert client.get("/api/mobile/v1/analyses?patient_id=8&tooth_number=56").status_code == 422
    assert client.get("/api/mobile/v1/analyses/11").json()["analysis"]["is_voice_review"] is True

    # Web patient_detail permits an admin to inspect an explicitly selected
    # patient. The voice marker must use that patient's owner receipt.
    with Session(engine) as session:
        admin = session.get(main.User, 1)
        admin.role = "ADMIN"
        session.add(admin)
        session.commit()
    admin_response = client.get("/api/mobile/v1/analyses?patient_id=9")
    assert admin_response.status_code == 200, admin_response.text
    assert [(item["id"], item["is_voice_review"]) for item in admin_response.json()["items"]] == [(13, True)]



def test_selected_media_analysis_uses_web_creation_and_rejects_other_owner(chat,monkeypatch,tmp_path):
    client,engine=chat
    main.UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
    monkeypatch.setattr(main,'classify_dental_image',lambda path:'PHOTO')
    monkeypatch.setattr(main,'storage_persist_file',lambda path:None)
    image=tmp_path/'synthetic.png';Image.new('RGB',(8,8),'white').save(image)
    with Session(engine) as s:
        for ident,owner in [(8,1),(9,2)]:
            s.add(main.Patient(id=ident,anonymous_id='SYNTHETIC-'+str(ident),owner_user_id=owner))
            s.add(main.PatientMedia(id=ident,patient_id=ident,owner_user_id=owner,stored_filename='synthetic.png',original_filename='synthetic.png',file_path=str(image)))
        for ident in range(80,85):
            s.add(main.PatientMedia(id=ident,patient_id=8,owner_user_id=1,stored_filename='synthetic.png',original_filename='synthetic.png',file_path=str(image)))
        s.commit()
    assert main.MAX_ANALYSIS_IMAGES==4
    assert client.post('/api/mobile/v1/patients/8/media/analyze',json={'media_ids':[80,81,82,83,84]}).status_code==422
    assert client.post('/api/mobile/v1/patients/8/media/analyze',json={'media_ids':[9]}).status_code==404
    assert client.post('/api/mobile/v1/patients/9/media/analyze',json={'media_ids':[9]}).status_code==404
    assert client.post('/api/mobile/v1/patients/8/media/analyze',json={'media_ids':[8,8]}).status_code==422
    assert client.post('/api/mobile/v1/patients/8/media/analyze',json={'media_ids':[8],'clinical_notes':'x'*4001}).status_code==422
    response=client.post('/api/mobile/v1/patients/8/media/analyze',json={
        'media_ids':[80,81,82,83], 'tooth_number':'36', 'clinical_notes':'Soğukta kısa süreli ağrı.'
    })
    assert response.status_code==200,response.text
    with Session(engine) as s:
        analysis=s.get(main.Analysis,response.json()['analysis_id'])
        assert analysis.patient_id==8
        assert analysis.tooth_number=='36'
        assert analysis.clinical_notes=='Soğukta kısa süreli ağrı.'
        from sqlmodel import select
        assert len(s.exec(select(main.ImageAsset).where(main.ImageAsset.analysis_id==analysis.id)).all())==4
    assert client.delete('/api/mobile/v1/patients/9/media').status_code==404
    assert client.delete('/api/mobile/v1/patients/8/media').status_code==200
    with Session(engine) as s:
        assert s.get(main.PatientMedia,8) is None
        assert s.get(main.PatientMedia,9) is not None

def test_native_uploads_return_confirmed_success_after_persistence(chat,monkeypatch,tmp_path):
    from app import mobile_api
    client,engine=chat;monkeypatch.setattr(mobile_analysis_api,'engine',engine);monkeypatch.setattr(mobile_api,'engine',engine)
    monkeypatch.setattr(main,'classify_dental_image',lambda path:'PHOTO')
    monkeypatch.setattr(mobile_analysis_api,'classify_dental_image',lambda path:'PHOTO')
    monkeypatch.setattr(main,'storage_persist_file',lambda path:None)
    monkeypatch.setattr(mobile_api,'storage_persist_file',lambda path:None)
    monkeypatch.setattr(mobile_analysis_api,'storage_persist_file',lambda path:None)
    monkeypatch.chdir(tmp_path)
    with Session(engine) as s:
        s.add(main.Patient(id=8,anonymous_id='SYNTHETIC-UPLOAD',owner_user_id=1));s.commit()
    raw=io.BytesIO();Image.new('RGB',(8,8),'white').save(raw,format='PNG')
    response=client.post('/api/mobile/v1/patients/8/media',data={'request_key':'synthetic-media-request-0001','batch_id':'synthetic-media-batch-0001','media_type':'PHOTO'},files={'file':('synthetic.png',raw.getvalue(),'image/png')})
    assert response.status_code==200,response.text
    assert response.json()['media']['id']>0
    response=client.post('/api/mobile/v1/analyses',data={'patient_id':'8'},files={'images':('synthetic.png',raw.getvalue(),'image/png')})
    assert response.status_code==200,response.text
    assert response.json()['analysis_id']>0 and response.json()['job_id']>0


def test_native_analysis_upload_failure_does_not_commit_orphan_record(chat, monkeypatch, tmp_path):
    from sqlmodel import select
    client, engine = chat
    monkeypatch.setattr(mobile_analysis_api, 'engine', engine)
    monkeypatch.chdir(tmp_path)
    with Session(engine) as session:
        session.add(main.Patient(id=8, anonymous_id='SYNTHETIC-INVALID', owner_user_id=1))
        session.commit()
    for filename, payload in [('invalid.png', b'not-a-real-image'), ('unsupported.txt', b'not-an-image')]:
        response = client.post('/api/mobile/v1/analyses', data={'patient_id': '8'},
                               files={'images': (filename, payload, 'application/octet-stream')})
        assert response.status_code == 422, response.text
        with Session(engine) as session:
            assert session.exec(select(main.Analysis).where(main.Analysis.patient_id == 8)).all() == []
            assert session.exec(select(main.ImageAsset)).all() == []


def test_native_analysis_rejects_mixed_supported_and_unsupported_uploads(chat, monkeypatch, tmp_path):
    from sqlmodel import select
    client, engine = chat
    monkeypatch.setattr(mobile_analysis_api, 'engine', engine)
    monkeypatch.chdir(tmp_path)
    with Session(engine) as session:
        session.add(main.Patient(id=8, anonymous_id='SYNTHETIC-MIXED', owner_user_id=1))
        session.commit()
    raw = io.BytesIO()
    Image.new('RGB', (8, 8), 'white').save(raw, format='PNG')
    response = client.post('/api/mobile/v1/analyses', data={'patient_id': '8'}, files=[
        ('images', ('valid.png', raw.getvalue(), 'image/png')),
        ('images', ('unsupported.txt', b'invalid', 'text/plain')),
    ])
    assert response.status_code == 422, response.text
    with Session(engine) as session:
        assert session.exec(select(main.Analysis).where(main.Analysis.patient_id == 8)).all() == []
        assert session.exec(select(main.ImageAsset)).all() == []



def test_mobile_patient_edit_revision_rejects_stale_web_or_device_overwrites(chat):
    from pathlib import Path

    client, engine = chat
    with Session(engine) as session:
        session.add(main.Patient(
            id=8, anonymous_id="SYNTHETIC-REVISION", owner_user_id=1,
            first_name="Initial", last_name="Patient", phone="05550000000",
            chief_complaint="Initial complaint",
        ))
        session.add(main.PatientProfile(patient_id=8, address="Initial address"))
        session.commit()

    snapshot = client.get("/api/mobile/v1/patients/8")
    assert snapshot.status_code == 200, snapshot.text
    revision = snapshot.json()["edit_revision"]
    assert len(revision) == 64 and all(char in "0123456789abcdef" for char in revision)

    current_payload = {
        "first_name": "Current",
        "last_name": "Patient",
        "phone": "05550000000",
        "birth_date": "",
        "tc_kimlik_no": "",
        "address": "Updated address",
        "chief_complaint": "Updated complaint",
        "expected_revision": revision,
    }
    updated = client.put("/api/mobile/v1/patients/8", json=current_payload)
    assert updated.status_code == 200, updated.text
    next_revision = updated.json()["edit_revision"]
    assert next_revision != revision

    stale = client.put("/api/mobile/v1/patients/8", json={
        **current_payload,
        "first_name": "Stale overwrite",
    })
    assert stale.status_code == 409, stale.text
    malformed = client.put("/api/mobile/v1/patients/8", json={
        **current_payload,
        "expected_revision": "not-a-revision",
    })
    assert malformed.status_code == 422, malformed.text

    from sqlmodel import select
    with Session(engine) as session:
        patient = session.get(main.Patient, 8)
        profile = session.exec(select(main.PatientProfile).where(main.PatientProfile.patient_id == 8)).first()
        assert patient.first_name == "Current"
        assert patient.chief_complaint == "Updated complaint"
        assert profile.address == "Updated address"

    template = Path("app/templates/patient_detail.html").read_text(encoding="utf-8")
    assert 'name="expected_revision" value="{{ patient_edit_revision }}"' in template


def test_treatment_create_receipt_replays_once_and_is_owner_scoped(chat):
    client, engine = chat
    with Session(engine) as session:
        session.add(main.Patient(id=81, anonymous_id="SYNTHETIC-TREATMENT", owner_user_id=1))
        session.commit()

    payload = {
        "treatment_name": "Kompozit dolgu",
        "tooth_number": "36",
        "treatment_date": "2026-11-16",
        "material": "Kompozit",
        "doctor_note": "Synthetic note",
        "result": "Tamamlandı",
        "request_key": "synthetic-treatment-create-0001",
    }
    first = client.post("/api/mobile/v1/patients/81/treatments", json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["replayed"] is False
    assert len(first.json()["edit_revision"]) == 64

    replay = client.post("/api/mobile/v1/patients/81/treatments", json=payload)
    assert replay.status_code == 201, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["treatment_id"] == first.json()["treatment_id"]

    changed = client.post("/api/mobile/v1/patients/81/treatments", json={
        **payload, "treatment_name": "Farklı işlem",
    })
    assert changed.status_code == 409, changed.text

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    assert client.post("/api/mobile/v1/patients/81/treatments", json=payload).status_code == 404

    with Session(engine) as session:
        rows = session.exec(select(main.Treatment).where(main.Treatment.patient_id == 81)).all()
        receipts = session.exec(select(WorkJob).where(
            WorkJob.kind == "TREATMENT_RECEIPT",
            WorkJob.resource_id == 81,
        )).all()
        assert len(rows) == 1
        assert len(receipts) == 1


def test_treatment_update_uses_revision_and_replays_exact_mutation(chat):
    client, engine = chat
    with Session(engine) as session:
        session.add(main.Patient(id=82, anonymous_id="SYNTHETIC-TREATMENT-UPDATE", owner_user_id=1))
        session.add(main.Treatment(
            id=821, patient_id=82, tooth_number="36", treatment_name="Eski dolgu",
            treatment_date="2026-11-01", material="Kompozit", doctor_note="Old note",
        ))
        session.commit()

    snapshot = client.get("/api/mobile/v1/patients/82")
    assert snapshot.status_code == 200, snapshot.text
    revision = snapshot.json()["treatments"][0]["edit_revision"]
    payload = {
        "treatment_name": "Yenilenen dolgu",
        "tooth_number": "36",
        "treatment_date": "2026-11-16",
        "material": "Yeni kompozit",
        "doctor_note": "Updated synthetic note",
        "result": "Kontrol Gerekli",
        "expected_revision": revision,
        "request_key": "synthetic-treatment-update-0001",
    }
    first = client.put("/api/mobile/v1/patients/82/treatments/821", json=payload)
    assert first.status_code == 200, first.text
    assert first.headers.get("cache-control") == "private, no-store"
    assert first.json()["replayed"] is False
    assert first.json()["edit_revision"] != revision

    replay = client.put("/api/mobile/v1/patients/82/treatments/821", json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["edit_revision"] == first.json()["edit_revision"]

    stale = client.put("/api/mobile/v1/patients/82/treatments/821", json={
        **payload,
        "request_key": "synthetic-treatment-update-0002",
        "treatment_name": "Stale overwrite",
    })
    assert stale.status_code == 409, stale.text

    malformed = client.put("/api/mobile/v1/patients/82/treatments/821", json={
        **payload, "expected_revision": "bad",
        "request_key": "synthetic-treatment-update-0003",
    })
    assert malformed.status_code == 422, malformed.text

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    assert client.put("/api/mobile/v1/patients/82/treatments/821", json=payload).status_code == 404

    with Session(engine) as session:
        treatment = session.get(main.Treatment, 821)
        assert treatment.treatment_name == "Yenilenen dolgu"
        assert treatment.doctor_note == "Updated synthetic note"


def test_treatment_receipts_are_not_pruned_while_patient_exists(chat):
    client, engine = chat
    with Session(engine) as session:
        session.add(main.Patient(id=83, anonymous_id="SYNTHETIC-TREATMENT-RETENTION", owner_user_id=1))
        session.commit()
    response = client.post("/api/mobile/v1/patients/83/treatments", json={
        "treatment_name": "Kontrol", "request_key": "synthetic-treatment-retention-0001",
    })
    assert response.status_code == 201, response.text
    with Session(engine) as session:
        receipt = session.exec(select(WorkJob).where(
            WorkJob.kind == "TREATMENT_RECEIPT", WorkJob.resource_id == 83,
        )).one()
        receipt.updated_at = datetime(2000, 1, 1)
        session.add(receipt)
        session.commit()
    prune_history(engine)
    with Session(engine) as session:
        assert session.exec(select(WorkJob).where(
            WorkJob.kind == "TREATMENT_RECEIPT", WorkJob.resource_id == 83,
        )).first() is not None



def test_mobile_patient_media_upload_receipt_replays_once_and_is_owner_scoped(chat, monkeypatch, tmp_path):
    client, engine = chat
    persisted = []
    async def async_publish(_event):
        return None
    monkeypatch.setattr(mobile_api, "engine", engine)
    monkeypatch.setattr(mobile_api, "storage_persist_file", lambda path: persisted.append(str(path)))
    monkeypatch.setattr(mobile_api, "storage_delete", lambda path: None)
    monkeypatch.setattr(mobile_api, "_publish_realtime_event", async_publish)
    monkeypatch.chdir(tmp_path)

    with Session(engine) as session:
        session.add(main.Patient(id=84, anonymous_id="SYNTHETIC-MEDIA-RECEIPT", owner_user_id=1))
        session.commit()

    raw = io.BytesIO()
    Image.new("RGB", (16, 12), (10, 20, 30)).save(raw, format="PNG")
    payload = raw.getvalue()
    key = "synthetic-media-upload-0001"
    batch_id = "synthetic-media-batch-0001"
    first = client.post("/api/mobile/v1/patients/84/media", data={
        "media_type": "PHOTO", "request_key": key, "batch_id": batch_id,
    }, files={"file": ("synthetic.png", payload, "image/png")})
    assert first.status_code == 200, first.text
    assert first.json()["replayed"] is False
    first_media = first.json()["media"]
    assert isinstance(first_media["uploaded_at"], str)
    assert set(first_media) == {
        "id", "original_filename", "media_type", "tooth_number", "note", "uploaded_at",
    }, "the durable receipt must not expose storage references or fingerprints"

    replay = client.post("/api/mobile/v1/patients/84/media", data={
        "media_type": "PHOTO", "request_key": key,
    }, files={"file": ("synthetic.png", payload, "image/png")})
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["media"]["id"] == first.json()["media"]["id"]
    assert replay.json()["media"]["uploaded_at"] == first_media["uploaded_at"]
    assert len(persisted) == 1, "replayed upload must not persist a second object"

    status = client.get(f"/api/mobile/v1/patients/84/media/uploads/{key}")
    assert status.status_code == 200, status.text
    assert status.headers.get("cache-control") == "private, no-store"
    assert status.json()["found"] is True
    assert status.json()["media"]["id"] == first.json()["media"]["id"]

    changed = io.BytesIO()
    Image.new("RGB", (16, 12), (30, 20, 10)).save(changed, format="PNG")
    conflict = client.post("/api/mobile/v1/patients/84/media", data={
        "media_type": "PHOTO", "request_key": key,
    }, files={"file": ("synthetic.png", changed.getvalue(), "image/png")})
    assert conflict.status_code == 409

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    assert client.get(f"/api/mobile/v1/patients/84/media/uploads/{key}").status_code == 404
    assert client.post("/api/mobile/v1/patients/84/media", data={
        "media_type": "PHOTO", "request_key": key,
    }, files={"file": ("synthetic.png", payload, "image/png")}).status_code == 404

    with Session(engine) as session:
        media = session.exec(select(main.PatientMedia).where(main.PatientMedia.patient_id == 84)).all()
        receipts = session.exec(select(WorkJob).where(
            WorkJob.kind == "PATIENT_MEDIA_RECEIPT",
            WorkJob.resource_id == 84,
        )).all()
        assert len(media) == 1
        assert len(receipts) == 1
        session.delete(media[0])
        session.commit()

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[1]
    deleted_replay = client.post("/api/mobile/v1/patients/84/media", data={
        "media_type": "PHOTO", "request_key": key,
    }, files={"file": ("synthetic.png", payload, "image/png")})
    assert deleted_replay.status_code == 409, "a deleted upload receipt must not resurrect the image"


def test_mobile_patient_media_receipt_fingerprint_is_keyed_and_versioned(chat, monkeypatch, tmp_path):
    import hashlib
    from pathlib import Path
    from app.patient_media_receipts import keyed_fingerprint

    client, engine = chat
    persisted = []
    async def async_publish(_event):
        return None
    monkeypatch.setattr(mobile_api, "engine", engine)
    monkeypatch.setattr(mobile_api, "storage_persist_file", lambda path: persisted.append(str(path)))
    monkeypatch.setattr(mobile_api, "storage_delete", lambda _path: None)
    monkeypatch.setattr(mobile_api, "_publish_realtime_event", async_publish)
    monkeypatch.chdir(tmp_path)
    with Session(engine) as session:
        session.add(main.Patient(id=88, anonymous_id="SYNTHETIC-HMAC-MEDIA", owner_user_id=1))
        session.commit()

    raw = io.BytesIO()
    Image.new("RGB", (16, 12), (14, 28, 42)).save(raw, format="PNG")
    response = client.post("/api/mobile/v1/patients/88/media", data={
        "media_type": "PHOTO", "request_key": "synthetic-media-hmac-0001",
        "batch_id": "synthetic-media-batch-0001",
    }, files={"file": ("synthetic.png", raw.getvalue(), "image/png")})
    assert response.status_code == 200, response.text
    with Session(engine) as session:
        media = session.exec(select(main.PatientMedia).where(main.PatientMedia.patient_id == 88)).one()
        receipt = session.exec(select(WorkJob).where(
            WorkJob.kind == "PATIENT_MEDIA_RECEIPT", WorkJob.resource_id == 88,
        )).one()
        file_hash = hashlib.sha256(Path(media.file_path).read_bytes()).hexdigest()
        legacy = mobile_api._patient_media_payload_hash(file_hash, "PHOTO", None, None, "synthetic.png")
        expected = keyed_fingerprint(legacy, bytes.fromhex("11" * 32), 1, 88)
        payload = json.loads(receipt.payload_json)
        assert receipt.source_hash == expected
        assert receipt.source_hash != legacy
        assert payload["fingerprint_version"] == 1
        assert len(persisted) == 1


def test_mobile_patient_media_receipt_secret_is_required_before_persisting(chat, monkeypatch, tmp_path):
    client, engine = chat
    persisted = []
    monkeypatch.delenv("PATIENT_MEDIA_RECEIPT_KEY", raising=False)
    monkeypatch.setattr(mobile_api, "engine", engine)
    monkeypatch.setattr(mobile_api, "storage_persist_file", lambda path: persisted.append(str(path)))
    monkeypatch.chdir(tmp_path)
    with Session(engine) as session:
        session.add(main.Patient(id=89, anonymous_id="SYNTHETIC-MISSING-HMAC", owner_user_id=1))
        session.commit()

    raw = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(raw, format="PNG")
    response = client.post("/api/mobile/v1/patients/89/media", data={
        "media_type": "PHOTO", "request_key": "synthetic-media-no-key-0001",
        "batch_id": "synthetic-media-batch-0001",
    }, files={"file": ("synthetic.png", raw.getvalue(), "image/png")})
    assert response.status_code == 503
    assert persisted == []
    with Session(engine) as session:
        assert session.exec(select(main.PatientMedia).where(main.PatientMedia.patient_id == 89)).all() == []


def test_legacy_patient_media_receipt_is_upgraded_on_private_status_lookup(chat):
    from app.patient_media_receipts import keyed_fingerprint

    client, engine = chat
    request_key = "legacy-media-request-0001"
    batch_id = "legacy-media-batch-0001"
    legacy_digest = "a" * 64
    with Session(engine) as session:
        session.add(main.Patient(id=90, anonymous_id="SYNTHETIC-LEGACY-MEDIA", owner_user_id=1))
        session.add(main.PatientMedia(
            id=900, patient_id=90, owner_user_id=1,
            stored_filename="legacy.png", original_filename="legacy.png",
            file_path="uploads/patient-media/legacy.png", media_type="PHOTO",
        ))
        session.add(WorkJob(
            owner_user_id=1, resource_id=90, resource_type="PATIENT",
            kind="PATIENT_MEDIA_RECEIPT", source_hash=legacy_digest,
            dedupe_key=mobile_api._patient_media_receipt_key(1, 90, request_key),
            result_ref=batch_id,
            payload_json=json.dumps({
                "patient_id": 90, "media_id": 900, "batch_id": batch_id,
                "file_bytes": 2048,
            }),
            status="DONE",
        ))
        session.commit()

    status = client.get(f"/api/mobile/v1/patients/90/media/uploads/{request_key}")
    assert status.status_code == 200, status.text
    assert status.headers.get("cache-control") == "private, no-store"
    assert status.json()["found"] is True
    with Session(engine) as session:
        receipt = session.exec(select(WorkJob).where(
            WorkJob.kind == "PATIENT_MEDIA_RECEIPT", WorkJob.resource_id == 90,
        )).one()
        assert receipt.source_hash == keyed_fingerprint(
            legacy_digest, bytes.fromhex("11" * 32), 1, 90,
        )
        assert json.loads(receipt.payload_json)["fingerprint_version"] == 1


def test_patient_media_receipts_are_not_pruned_while_patient_exists(chat):
    client, engine = chat
    with Session(engine) as session:
        session.add(main.Patient(id=85, anonymous_id="SYNTHETIC-MEDIA-RETENTION", owner_user_id=1))
        session.add(WorkJob(
            owner_user_id=1,
            resource_id=85,
            resource_type="PATIENT",
            kind="PATIENT_MEDIA_RECEIPT",
            source_hash="a" * 64,
            dedupe_key="b" * 64,
            payload_json='{"patient_id":85,"media_id":850}',
            status="DONE",
            updated_at=datetime(2000, 1, 1),
        ))
        session.commit()
    prune_history(engine)
    with Session(engine) as session:
        assert session.exec(select(WorkJob).where(
            WorkJob.kind == "PATIENT_MEDIA_RECEIPT",
            WorkJob.resource_id == 85,
        )).first() is not None



def test_mobile_patient_media_preserves_extension_and_enforces_web_validation(chat, monkeypatch, tmp_path):
    client, engine = chat
    monkeypatch.setattr(mobile_api, "engine", engine)
    monkeypatch.setattr(mobile_api, "storage_persist_file", lambda _path: None)
    monkeypatch.setattr(mobile_api, "storage_delete", lambda _path: None)
    async def async_publish(_event):
        return None
    monkeypatch.setattr(mobile_api, "_publish_realtime_event", async_publish)
    monkeypatch.chdir(tmp_path)
    with Session(engine) as session:
        session.add(main.Patient(id=86, anonymous_id="SYNTHETIC-MEDIA-VALIDATION", owner_user_id=1))
        session.commit()

    raw = io.BytesIO()
    Image.new("RGB", (16, 12), (12, 24, 36)).save(raw, format="PNG")
    long_name = "x" * 300 + ".png"
    batch_id = "synthetic-media-validation-batch-0001"
    saved = client.post("/api/mobile/v1/patients/86/media", data={
        "media_type": "PHOTO", "request_key": "synthetic-media-long-name-0001", "batch_id": batch_id,
    }, files={"file": (long_name, raw.getvalue(), "image/png")})
    assert saved.status_code == 200, saved.text
    with Session(engine) as session:
        media = session.exec(select(main.PatientMedia).where(main.PatientMedia.patient_id == 86)).one()
        assert len(media.original_filename) == 255
        assert media.original_filename.endswith(".png")

    invalid_tooth = client.post("/api/mobile/v1/patients/86/media", data={
        "media_type": "PHOTO", "tooth_number": "56",
        "request_key": "synthetic-media-invalid-fdi-0001", "batch_id": batch_id,
    }, files={"file": ("synthetic.png", raw.getvalue(), "image/png")})
    assert invalid_tooth.status_code == 422

    monkeypatch.setattr(mobile_api, "MOBILE_MAX_PATIENT_MEDIA_BYTES", 64)
    oversized = client.post("/api/mobile/v1/patients/86/media", data={
        "media_type": "PHOTO", "request_key": "synthetic-media-over-limit-0001", "batch_id": batch_id,
    }, files={"file": ("synthetic.png", raw.getvalue(), "image/png")})
    assert oversized.status_code == 413


def test_web_analysis_selection_and_submission_share_four_image_limit(chat,monkeypatch,tmp_path):
    client,engine=chat
    client.cookies.set(main.SESSION_COOKIE,_SESSION_TOKEN[1])
    main.UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
    image=tmp_path/'synthetic-analysis-limit.png'
    Image.new('RGB',(8,8),'white').save(image)
    with Session(engine) as session:
        session.add(main.Patient(id=80,anonymous_id='SYNTHETIC-LIMIT',owner_user_id=1))
        for media_id in range(801,806):
            session.add(main.PatientMedia(
                id=media_id,patient_id=80,owner_user_id=1,
                original_filename=f'{media_id}.png',stored_filename=f'{media_id}.png',
                file_path=str(image),media_type='RADIOGRAPH',
            ))
        session.commit()

    assert main.MAX_ANALYSIS_IMAGES == 4
    assert main.MAX_PATIENT_MEDIA_UPLOAD_FILES == 12
    profile=client.get('/patients/80')
    assert profile.status_code==200,profile.text
    assert 'const maxAnalysisImages = 4;' in profile.text
    assert 'const maxPatientMediaUploadFiles = 12;' in profile.text
    assert 'Klinik arşive tek seferde en fazla 12 görüntü' in profile.text
    accepted=client.get('/analysis/new/80?media_ids=801,802,803,804')
    assert accepted.status_code==200,accepted.text
    assert '4 / 4 görüntü analiz için seçildi' in accepted.text
    assert 'toplam en fazla 4 görüntü' in accepted.text
    assert 'data-analysis-image-limit="4"' in accepted.text
    assert 'data-existing-image-count="4"' in accepted.text
    assert 'Kayıtlı görüntüler dahil bir analizde en fazla ' in accepted.text

    rejected=client.get('/analysis/new/80?media_ids=801,802,803,804,805')
    assert rejected.status_code==400
    assert 'en fazla 4 kayıtlı görüntü' in rejected.text

    raw=io.BytesIO()
    Image.new('RGB',(8,8),'white').save(raw,format='PNG')
    submitted=client.post(
        '/analysis/new/80',
        data={'existing_media_ids':'801,802,803,804'},
        files=[('images',('extra.png',raw.getvalue(),'image/png'))],
    )
    assert submitted.status_code==400
    assert 'kayıtlı ve yeni görüntülerin toplamı en fazla 4 olabilir' in submitted.text.lower()
    with Session(engine) as session:
        assert not session.exec(select(main.Analysis).where(main.Analysis.patient_id==80)).all()


def test_patient_archive_accepts_twelve_images_and_rejects_thirteen(chat,monkeypatch,tmp_path):
    client,engine=chat
    client.cookies.set(main.SESSION_COOKIE,_SESSION_TOKEN[1])
    upload_dir=tmp_path/'patient-media-uploads'
    upload_dir.mkdir(parents=True,exist_ok=True)
    monkeypatch.setattr(main,'UPLOAD_DIR',upload_dir)
    monkeypatch.setattr(main,'storage_persist_file',lambda _path:None)
    monkeypatch.setattr(main,'storage_delete',lambda _path:None)
    monkeypatch.setattr(main,'sanitize_clinical_media_image',lambda *_args,**_kwargs:None)
    with Session(engine) as session:
        session.add(main.Patient(id=81,anonymous_id='SYNTHETIC-ARCHIVE-BATCH',owner_user_id=1))
        session.commit()
    raw=io.BytesIO()
    Image.new('RGB',(8,8),'white').save(raw,format='PNG')
    payload=raw.getvalue()
    twelve=[('files',(f'archive-{index}.png',payload,'image/png')) for index in range(12)]
    accepted=client.post('/patients/81/media',data={'media_type':'PHOTO'},files=twelve,follow_redirects=False)
    assert accepted.status_code==303,accepted.text
    with Session(engine) as session:
        assert len(session.exec(select(main.PatientMedia).where(main.PatientMedia.patient_id==81)).all())==12
    thirteen=[('files',(f'archive-over-{index}.png',payload,'image/png')) for index in range(13)]
    rejected=client.post('/patients/81/media',data={'media_type':'PHOTO'},files=thirteen,follow_redirects=False)
    assert rejected.status_code==400
    assert 'en fazla 12 görüntü' in rejected.text
    with Session(engine) as session:
        assert len(session.exec(select(main.PatientMedia).where(main.PatientMedia.patient_id==81)).all())==12


def _post_patient_media_batch_file(client, raw, request_key, batch_id, filename='synthetic.png', patient_id=8):
    return client.post(
        f'/api/mobile/v1/patients/{patient_id}/media',
        data={'request_key': request_key, 'batch_id': batch_id, 'media_type': 'PHOTO'},
        files={'file': (filename, raw, 'image/png')},
    )


def test_mobile_patient_media_batch_enforces_aggregate_bytes_across_requests_and_replays(chat, monkeypatch, tmp_path):
    from app import mobile_api
    from app.upload_limits import MAX_PATIENT_MEDIA_BATCH_BYTES
    client, engine = chat
    monkeypatch.setattr(mobile_api, 'engine', engine)
    monkeypatch.setattr(mobile_api, 'storage_persist_file', lambda path: None)
    monkeypatch.chdir(tmp_path)
    raw = io.BytesIO()
    Image.new('RGB', (8, 8), 'white').save(raw, format='PNG')
    payload = raw.getvalue()
    sizes = [10 * 1024 * 1024] * 9 + [7 * 1024 * 1024, 10 * 1024 * 1024]

    def copy_with_declared_stream_size(upload, destination, maximum):
        destination.write_bytes(payload)
        return sizes.pop(0)

    monkeypatch.setattr(mobile_api, '_copy_validated_image', copy_with_declared_stream_size)
    with Session(engine) as session:
        session.add(main.Patient(id=8, anonymous_id='SYNTHETIC-BATCH', owner_user_id=1))
        session.commit()

    batch_id = 'synthetic-clinical-batch-0001'
    for index in range(8):
        response = _post_patient_media_batch_file(
            client, payload, f'synthetic-media-request-{index:04d}', batch_id,
        )
        assert response.status_code == 200, response.text

    replay = _post_patient_media_batch_file(
        client, payload, 'synthetic-media-request-0000', batch_id,
    )
    assert replay.status_code == 200 and replay.json()['replayed'] is True

    ninth = _post_patient_media_batch_file(
        client, payload, 'synthetic-media-request-0008', batch_id,
    )
    assert ninth.status_code == 200, ninth.text

    overflow = _post_patient_media_batch_file(
        client, payload, 'synthetic-media-request-0009', batch_id,
    )
    assert overflow.status_code == 413, overflow.text

    with Session(engine) as session:
        media = session.exec(select(main.PatientMedia).where(main.PatientMedia.patient_id == 8)).all()
        receipts = session.exec(select(WorkJob).where(
            WorkJob.kind == 'PATIENT_MEDIA_RECEIPT',
            WorkJob.resource_type == 'PATIENT',
            WorkJob.resource_id == 8,
            WorkJob.result_ref == batch_id,
        )).all()
        assert len(media) == 9
        assert len(receipts) == 9
        assert sum(json.loads(row.payload_json)['file_bytes'] for row in receipts) == 87 * 1024 * 1024
        assert sum(json.loads(row.payload_json)['file_bytes'] for row in receipts) <= MAX_PATIENT_MEDIA_BATCH_BYTES


def test_mobile_patient_media_batch_enforces_file_count_across_sequential_requests(chat, monkeypatch, tmp_path):
    from app import mobile_api
    from app.upload_limits import MAX_PATIENT_MEDIA_FILES
    client, engine = chat
    monkeypatch.setattr(mobile_api, 'engine', engine)
    monkeypatch.setattr(mobile_api, 'storage_persist_file', lambda path: None)
    monkeypatch.setattr(mobile_api, '_copy_validated_image', lambda upload, destination, maximum: (destination.write_bytes(b'valid-test-image') or 1024))
    monkeypatch.chdir(tmp_path)
    with Session(engine) as session:
        session.add(main.Patient(id=8, anonymous_id='SYNTHETIC-BATCH-COUNT', owner_user_id=1))
        session.commit()

    batch_id = 'synthetic-clinical-batch-count-0001'
    for index in range(MAX_PATIENT_MEDIA_FILES):
        response = _post_patient_media_batch_file(
            client, b'not-used-by-stub', f'synthetic-media-count-{index:04d}', batch_id,
        )
        assert response.status_code == 200, response.text

    rejected = _post_patient_media_batch_file(
        client, b'not-used-by-stub', 'synthetic-media-count-0012', batch_id,
    )
    assert rejected.status_code == 413, rejected.text
    with Session(engine) as session:
        assert len(session.exec(select(main.PatientMedia).where(main.PatientMedia.patient_id == 8)).all()) == MAX_PATIENT_MEDIA_FILES


def test_mobile_patient_media_batch_identity_is_required_before_file_processing(chat, monkeypatch, tmp_path):
    from app import mobile_api
    client, engine = chat
    monkeypatch.setattr(mobile_api, 'engine', engine)
    processed = []
    monkeypatch.setattr(mobile_api, '_copy_validated_image', lambda *args: processed.append(True))
    monkeypatch.chdir(tmp_path)
    with Session(engine) as session:
        session.add(main.Patient(id=8, anonymous_id='SYNTHETIC-BATCH-REQUIRED', owner_user_id=1))
        session.commit()

    response = client.post(
        '/api/mobile/v1/patients/8/media',
        data={'request_key': 'synthetic-media-request-0001'},
        files={'file': ('synthetic.png', b'payload', 'image/png')},
    )
    assert response.status_code == 422
    assert processed == []


def test_mobile_patient_media_batch_quota_is_scoped_to_owner_and_patient(chat, monkeypatch, tmp_path):
    from app import mobile_api
    client, engine = chat
    monkeypatch.setattr(mobile_api, 'engine', engine)
    monkeypatch.setattr(mobile_api, 'storage_persist_file', lambda path: None)
    monkeypatch.chdir(tmp_path)
    raw = io.BytesIO()
    Image.new('RGB', (8, 8), 'white').save(raw, format='PNG')
    payload = raw.getvalue()
    monkeypatch.setattr(
        mobile_api, '_copy_validated_image',
        lambda upload, destination, maximum: (destination.write_bytes(payload) and 10 * 1024 * 1024),
    )
    with Session(engine) as session:
        session.add_all([
            main.Patient(id=8, anonymous_id='SYNTHETIC-SCOPE-8', owner_user_id=1),
            main.Patient(id=9, anonymous_id='SYNTHETIC-SCOPE-9', owner_user_id=1),
            main.Patient(id=10, anonymous_id='SYNTHETIC-SCOPE-10', owner_user_id=2),
        ])
        session.commit()

    batch_id = 'synthetic-shared-batch-0001'
    for patient_id, token in [(8, _SESSION_TOKEN[1]), (9, _SESSION_TOKEN[1]), (10, _SESSION_TOKEN[2])]:
        client.headers['Authorization'] = 'Bearer ' + token
        for index in range(9):
            response = _post_patient_media_batch_file(
                client, payload, f'synthetic-scope-{patient_id}-{index:02d}-key',
                batch_id, patient_id=patient_id,
            )
            assert response.status_code == 200, (patient_id, index, response.text)

    with Session(engine) as session:
        for patient_id in (8, 9, 10):
            assert len(session.exec(select(main.PatientMedia).where(
                main.PatientMedia.patient_id == patient_id,
            )).all()) == 9
        assert len(session.exec(select(WorkJob).where(
            WorkJob.kind == 'PATIENT_MEDIA_RECEIPT',
            WorkJob.result_ref == batch_id,
        )).all()) == 27


def test_mobile_patient_media_batch_fails_closed_on_malformed_receipt(chat, monkeypatch, tmp_path):
    from app import mobile_api
    client, engine = chat
    monkeypatch.setattr(mobile_api, 'engine', engine)
    monkeypatch.setattr(mobile_api, 'storage_persist_file', lambda path: None)
    monkeypatch.setattr(
        mobile_api, '_copy_validated_image',
        lambda upload, destination, maximum: (destination.write_bytes(b'valid-test-image') and 100),
    )
    monkeypatch.chdir(tmp_path)
    batch_id = 'synthetic-malformed-batch-0001'
    with Session(engine) as session:
        session.add(main.Patient(id=8, anonymous_id='SYNTHETIC-MALFORMED-BATCH', owner_user_id=1))
        session.add(WorkJob(
            owner_user_id=1, resource_id=8, resource_type='PATIENT',
            kind='PATIENT_MEDIA_RECEIPT', source_hash='synthetic-malformed',
            dedupe_key='synthetic-malformed-receipt-key', result_ref=batch_id,
            payload_json='[]', status='DONE',
        ))
        session.commit()

    response = _post_patient_media_batch_file(
        client, b'payload', 'synthetic-malformed-new-request-0001', batch_id,
    )
    assert response.status_code == 409, response.text
    with Session(engine) as session:
        assert session.exec(select(main.PatientMedia).where(
            main.PatientMedia.patient_id == 8,
        )).all() == []

def test_mobile_patient_delete_is_owner_scoped_and_refuses_clinical_dependents(chat):
    client, engine = chat
    with Session(engine) as session:
        session.add_all([
            main.Patient(id=8, anonymous_id="SYNTHETIC-DELETE-8", owner_user_id=1),
            main.Patient(id=9, anonymous_id="SYNTHETIC-DELETE-9", owner_user_id=2),
            main.Patient(id=10, anonymous_id="SYNTHETIC-DELETE-10", owner_user_id=1),
            main.Analysis(id=108, patient_id=8, tooth_number="36", status="DRAFT"),
            main.PatientProfile(patient_id=10, address="Synthetic address"),
        ])
        session.commit()

    # The native adapter deliberately refuses to erase a patient while clinical
    # history exists; the UI must not bypass this audited-erasure boundary.
    blocked = client.delete("/api/mobile/v1/patients/8")
    assert blocked.status_code == 409, blocked.text
    assert "Güvenli silme" in blocked.json()["detail"]

    # Another clinician's patient is indistinguishable from a missing record.
    assert client.delete("/api/mobile/v1/patients/9").status_code == 404

    # An owned patient without dependent clinical rows can be deleted normally.
    removed = client.delete("/api/mobile/v1/patients/10")
    assert removed.status_code == 200, removed.text
    with Session(engine) as session:
        assert session.get(main.Patient, 8) is not None
        assert session.get(main.Patient, 9) is not None
        assert session.get(main.Patient, 10) is None
        assert session.exec(
            select(main.PatientProfile).where(main.PatientProfile.patient_id == 10)
        ).first() is None


def test_native_patient_delete_ui_fails_closed_for_unresolved_local_mutations():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    component = (root / "mobile/src/NativePatientProfile.tsx").read_text(encoding="utf-8")
    presentation = (root / "mobile/src/patientProfilePresentation.ts").read_text(encoding="utf-8")
    assert "patientProfileCanDeletePatient(deleteGate.current)" in component
    assert "treatmentIntentReady" in component and "treatmentIntentBlocked" in component
    assert "hasPendingTreatment:pendingTreatment!==null" in component
    assert "profileUncertain" in component and "treatmentUncertain" in component
    assert "const allowed=replay?canResolvePatientDelete:canDeletePatient;" in component
    assert "profileEditReady:!editDraftDirty&&profileConflicts.length===0&&!revisionConflict" in component
    assert "patientProfileEditMatches(patientForm,latestForm)" in component
    assert component.count("if(result.patient.id!==patientId)") == 1
    assert component.count("if(latest.patient.id!==patientId)") == 3
    assert "Sunucudaki profil kaydını karşılaştır" in component
    assert "Kontrol ettim" not in component
    delete_block = component.split("function confirmDelete()", 1)[1].split("const button=", 1)[0]
    assert "if(lock.current||!allowed)" in delete_block
    assert delete_block.count("if(!current()||!focusedRef.current)return;") == 1
    assert "gate.uncertain === false" in presentation
    assert "gate.profileEditReady === true" in presentation
    assert "gate.hasPendingTreatment === false" in presentation

def test_native_tooth_chart_blocks_all_clinical_writes_until_treatment_intent_recovery():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    component = (root / "mobile/src/NativeToothChart.tsx").read_text(encoding="utf-8")
    presentation = (root / "mobile/src/toothChartPresentation.ts").read_text(encoding="utf-8")
    assert "toothChartClinicalMutationBlocked" in component
    assert "hasPendingTreatment:pendingTreatment!==null" in component
    assert component.count("if(clinicalMutationBlocked){setErr(") == 3
    assert "editable={!busy&&!clinicalMutationBlocked} value={note}" in component
    assert "editable={!clinicalMutationBlocked} value={note}" in component
    assert "disabled={treatmentBusy||clinicalMutationBlocked}" in component
    assert component.count("if(result.patient.id!==patientId)") == 2
    assert component.count("if(updated.patient.id!==patientId)") == 4
    assert "disabled={busy||surfaceBusy||treatmentBusy||clinicalMutationBlocked}" in component
    assert "Güvenli tedavi kaydı kontrol ediliyor." in component
    assert "Bekleyen tedavi taslağı okunamadı." in component
    assert "gate.treatmentIntentReady !== true" in presentation
    assert "gate.hasPendingTreatment === true" in presentation
    assert component.count("if(result.patient.id!==patientId)") == 2
    assert component.count("if(updated.patient.id!==patientId)") == 4


def test_mobile_patient_detail_exposes_surface_updated_at_for_history_parity(chat):
    client, engine = chat
    changed_at = datetime(2026, 11, 17, 9, 15, 0)
    with Session(engine) as session:
        session.add(main.Patient(id=8, anonymous_id="SYNTHETIC-SURFACE-HISTORY", owner_user_id=1))
        session.add(main.Patient(id=9, anonymous_id="SYNTHETIC-SURFACE-OTHER", owner_user_id=2))
        session.add(main.ToothSurfaceStatus(
            patient_id=8,
            tooth_number="11",
            surface="MESIAL",
            status="CARIES",
            note="Synthetic surface note",
            updated_at=changed_at,
        ))
        session.add(main.ToothSurfaceStatus(
            patient_id=9,
            tooth_number="11",
            surface="DISTAL",
            status="FILLING",
            note="Other owner record",
            updated_at=changed_at,
        ))
        session.commit()

    own = client.get("/api/mobile/v1/patients/8")
    assert own.status_code == 200, own.text
    surfaces = own.json()["surfaces"]
    assert len(surfaces) == 1
    assert surfaces[0]["tooth_number"] == "11"
    assert surfaces[0]["surface"] == "MESIAL"
    assert surfaces[0]["status"] == "CARIES"
    assert surfaces[0]["note"] == "Synthetic surface note"
    assert datetime.fromisoformat(surfaces[0]["updated_at"]).replace(tzinfo=None) == changed_at

    # The same detail contract must not reveal another owner's surface history.
    assert client.get("/api/mobile/v1/patients/9").status_code == 404


def test_native_patient_media_delete_replay_is_idempotent_and_owner_scoped(chat, monkeypatch):
    client, engine = chat
    deleted_paths = []

    async def async_publish(_event):
        return None

    monkeypatch.setattr(mobile_api, "engine", engine)
    monkeypatch.setattr(mobile_api, "storage_delete", lambda path: deleted_paths.append(path))
    monkeypatch.setattr(mobile_api, "_publish_realtime_event", async_publish)
    with Session(engine) as session:
        session.add_all([
            main.Patient(id=88, anonymous_id="SYNTHETIC-MEDIA-DELETE-88", owner_user_id=1),
            main.Patient(id=89, anonymous_id="SYNTHETIC-MEDIA-DELETE-89", owner_user_id=2),
            main.PatientMedia(
                id=880, patient_id=88, owner_user_id=1, media_type="PHOTO",
                stored_filename="synthetic-880.png", original_filename="synthetic.png",
                file_path="synthetic/private/880.png",
            ),
            main.PatientMedia(
                id=890, patient_id=89, owner_user_id=2, media_type="PHOTO",
                stored_filename="synthetic-890.png", original_filename="synthetic.png",
                file_path="synthetic/private/890.png",
            ),
        ])
        session.commit()

    first = client.delete("/api/mobile/v1/patients/88/media/880")
    assert first.status_code == 200, first.text
    assert first.json() == {
        "ok": True,
        "media_id": 880,
        "already_deleted": False,
        "storage_cleanup_pending": False,
    }

    # Simulates a lost first response followed by the same native retry.
    replay = client.delete("/api/mobile/v1/patients/88/media/880")
    assert replay.status_code == 200, replay.text
    assert replay.json() == {
        "ok": True,
        "media_id": 880,
        "already_deleted": True,
        "storage_cleanup_pending": None,
    }
    assert set(deleted_paths) == {"synthetic/private/880.png", "synthetic/private/880.thumb.jpg"}

    # Existing media from another patient is never treated as an idempotent miss.
    assert client.delete("/api/mobile/v1/patients/88/media/890").status_code == 404
    assert client.delete("/api/mobile/v1/patients/999/media/880").status_code == 404

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    assert client.delete("/api/mobile/v1/patients/88/media/880").status_code == 404
    with Session(engine) as session:
        assert session.get(main.PatientMedia, 880) is None
        assert session.get(main.PatientMedia, 890) is not None

def test_mobile_patient_delete_receipt_replays_after_lost_response_and_is_owner_scoped(chat):
    client, engine = chat
    with Session(engine) as session:
        session.add_all([
            main.Patient(id=111, anonymous_id="SYNTHETIC-DELETE-RECEIPT-111", owner_user_id=1),
            main.Patient(id=112, anonymous_id="SYNTHETIC-DELETE-RECEIPT-112", owner_user_id=1),
        ])
        session.commit()

    request_key = "synthetic-patient-delete-request-0001"
    first = client.delete(f"/api/mobile/v1/patients/111?request_key={request_key}")
    assert first.status_code == 200, first.text
    assert first.json() == {"ok": True, "patient_id": 111, "already_deleted": False}

    # Simulate a response lost after commit: the exact same request is a
    # successful replay and does not publish a second deletion.
    replay = client.delete(f"/api/mobile/v1/patients/111?request_key={request_key}")
    assert replay.status_code == 200, replay.text
    assert replay.json() == {"ok": True, "patient_id": 111, "already_deleted": True}

    # A request key is bound to one account and one patient, not reusable for
    # another deletion target.
    reused = client.delete(f"/api/mobile/v1/patients/112?request_key={request_key}")
    assert reused.status_code == 409, reused.text

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    assert client.delete(f"/api/mobile/v1/patients/111?request_key={request_key}").status_code == 404

    with Session(engine) as session:
        assert session.get(main.Patient, 111) is None
        assert session.get(main.Patient, 112) is not None
        receipts = session.exec(select(WorkJob).where(
            WorkJob.owner_user_id == 1,
            WorkJob.kind == "PATIENT_DELETE_RECEIPT",
            WorkJob.resource_type == "PATIENT",
            WorkJob.resource_id == 111,
        )).all()
        assert len(receipts) == 1
        assert len(receipts[0].source_hash) == 64
        assert len(receipts[0].dedupe_key) == 64
        assert receipts[0].payload_json == "{}"


def test_mobile_patient_delete_receipt_is_not_created_when_clinical_history_blocks_delete(chat):
    client, engine = chat
    with Session(engine) as session:
        session.add(main.Patient(id=113, anonymous_id="SYNTHETIC-DELETE-BLOCKED", owner_user_id=1))
        session.add(main.Analysis(id=1131, patient_id=113, tooth_number="36", status="DRAFT"))
        session.commit()

    request_key = "synthetic-patient-delete-request-0002"
    blocked = client.delete(f"/api/mobile/v1/patients/113?request_key={request_key}")
    assert blocked.status_code == 409, blocked.text
    with Session(engine) as session:
        assert session.exec(select(WorkJob).where(
            WorkJob.owner_user_id == 1,
            WorkJob.kind == "PATIENT_DELETE_RECEIPT",
            WorkJob.resource_id == 113,
        )).first() is None

    # The same key remains usable after the blocking clinical dependency is
    # removed through the test fixture; no failed deletion receipt was committed.
    with Session(engine) as session:
        session.delete(session.get(main.Analysis, 1131))
        session.commit()
    removed = client.delete(f"/api/mobile/v1/patients/113?request_key={request_key}")
    assert removed.status_code == 200, removed.text
    assert removed.json()["already_deleted"] is False


def test_mobile_patient_delete_rejects_malformed_request_key_without_mutation(chat):
    client, engine = chat
    with Session(engine) as session:
        session.add(main.Patient(id=114, anonymous_id="SYNTHETIC-DELETE-KEY", owner_user_id=1))
        session.commit()

    response = client.delete("/api/mobile/v1/patients/114?request_key=short")
    assert response.status_code == 422, response.text
    with Session(engine) as session:
        assert session.get(main.Patient, 114) is not None
        assert session.exec(select(WorkJob).where(
            WorkJob.kind == "PATIENT_DELETE_RECEIPT",
            WorkJob.resource_id == 114,
        )).first() is None

def test_patient_delete_receipt_never_claims_a_restored_patient_was_deleted(chat):
    client, engine = chat
    with Session(engine) as session:
        session.add(main.Patient(id=115, anonymous_id="SYNTHETIC-DELETE-RESTORE", owner_user_id=1))
        session.commit()

    request_key = "synthetic-patient-delete-request-0003"
    first = client.delete(f"/api/mobile/v1/patients/115?request_key={request_key}")
    assert first.status_code == 200, first.text
    with Session(engine) as session:
        session.add(main.Patient(id=115, anonymous_id="SYNTHETIC-DELETE-RESTORE", owner_user_id=1))
        session.commit()

    replay = client.delete(f"/api/mobile/v1/patients/115?request_key={request_key}")
    assert replay.status_code == 409, replay.text


def test_patient_delete_tombstone_is_bounded_by_existing_work_history_retention(chat):
    client, engine = chat
    with Session(engine) as session:
        session.add(main.Patient(id=116, anonymous_id="SYNTHETIC-DELETE-TTL", owner_user_id=1))
        session.commit()

    request_key = "synthetic-patient-delete-request-0004"
    removed = client.delete(f"/api/mobile/v1/patients/116?request_key={request_key}")
    assert removed.status_code == 200, removed.text
    with Session(engine) as session:
        receipt = session.exec(select(WorkJob).where(
            WorkJob.kind == "PATIENT_DELETE_RECEIPT",
            WorkJob.resource_id == 116,
        )).one()
        receipt.updated_at = datetime(2000, 1, 1)
        session.add(receipt)
        session.commit()

    prune_history(engine)
    with Session(engine) as session:
        assert session.exec(select(WorkJob).where(
            WorkJob.kind == "PATIENT_DELETE_RECEIPT",
            WorkJob.resource_id == 116,
        )).first() is None
    # Once the bounded tombstone expires, absence is still represented by 404.
    assert client.delete(f"/api/mobile/v1/patients/116?request_key={request_key}").status_code == 404




def test_patient_treatment_history_is_bounded_snapshot_paginated_and_owner_scoped(chat, monkeypatch):
    client, engine = chat
    monkeypatch.setattr(mobile_api, "engine", engine)
    base = datetime(2026, 11, 18, 12, 0, 0)
    with Session(engine) as session:
        session.add_all([
            main.Patient(id=801, anonymous_id="SYNTHETIC-TREATMENT-PAGE-801", owner_user_id=1),
            main.Patient(id=802, anonymous_id="SYNTHETIC-TREATMENT-PAGE-802", owner_user_id=1),
            main.Patient(id=803, anonymous_id="SYNTHETIC-TREATMENT-PAGE-803", owner_user_id=2),
        ])
        session.flush()
        session.add_all([
            main.Treatment(
                patient_id=801,
                treatment_name=f"Synthetic treatment {index:02d}",
                created_at=base - timedelta(minutes=index // 2),
            )
            for index in range(25)
        ])
        session.commit()
        expected = session.exec(
            select(main.Treatment)
            .where(main.Treatment.patient_id == 801)
            .order_by(main.Treatment.created_at.desc(), main.Treatment.id.desc())
        ).all()
        expected_ids = [row.id for row in expected]

    detail = client.get("/api/mobile/v1/patients/801")
    assert detail.status_code == 200, detail.text
    assert detail.headers["cache-control"] == "private, no-store"
    assert "authorization" in detail.headers.get("vary", "").lower()
    first_body = detail.json()
    assert [row["id"] for row in first_body["treatments"]] == expected_ids[:3]
    cursor = first_body["treatments_next_cursor"]
    assert isinstance(cursor, str) and 24 <= len(cursor) <= 512
    assert "SYNTHETIC" not in cursor

    # A row inserted after page one must not leak into this history snapshot.
    with Session(engine) as session:
        session.add(main.Treatment(
            patient_id=801,
            treatment_name="Synthetic treatment inserted after snapshot",
            created_at=base + timedelta(days=1),
        ))
        session.commit()

    page_one = client.get(f"/api/mobile/v1/patients/801/treatments?cursor={cursor}")
    assert page_one.status_code == 200, page_one.text
    assert page_one.headers["cache-control"] == "private, no-store"
    assert "authorization" in page_one.headers.get("vary", "").lower()
    page_one_body = page_one.json()
    assert [row["id"] for row in page_one_body["items"]] == expected_ids[3:23]
    assert page_one_body["next_cursor"]

    page_two = client.get(
        f"/api/mobile/v1/patients/801/treatments?cursor={page_one_body['next_cursor']}"
    )
    assert page_two.status_code == 200, page_two.text
    assert [row["id"] for row in page_two.json()["items"]] == expected_ids[23:]
    assert page_two.json()["next_cursor"] is None
    combined = [row["id"] for row in first_body["treatments"] + page_one_body["items"] + page_two.json()["items"]]
    assert combined == expected_ids
    assert len(combined) == len(set(combined)) == 25

    assert client.get(f"/api/mobile/v1/patients/802/treatments?cursor={cursor}").status_code == 422
    assert client.get(f"/api/mobile/v1/patients/801/treatments?cursor={cursor}!").status_code == 422
    empty = client.get("/api/mobile/v1/patients/802")
    assert empty.status_code == 200
    assert empty.json()["treatments"] == []
    assert empty.json()["treatments_next_cursor"] is None

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    assert client.get(f"/api/mobile/v1/patients/801/treatments?cursor={cursor}").status_code == 404


def _assert_clinical_private_response(response):
    assert response.headers.get("cache-control") == "private, no-store"
    assert response.headers.get("pragma") == "no-cache"
    assert "authorization" in response.headers.get("vary", "").lower()


def test_mobile_patient_media_responses_are_private_and_owner_scoped(chat, monkeypatch, tmp_path):
    client, engine = chat
    real_path = Path

    # Keep the upload fixture entirely inside pytest's temporary directory.
    monkeypatch.setattr(
        mobile_api,
        "Path",
        lambda value: real_path(value) if real_path(value).is_absolute() else tmp_path / value,
    )
    monkeypatch.setattr(
        mobile_api,
        "storage_ensure_local",
        lambda value: real_path(value) if real_path(value).is_absolute() else tmp_path / value,
    )
    monkeypatch.setattr(mobile_api, "storage_persist_file", lambda _path: None)

    with Session(engine) as session:
        session.add_all([
            main.Patient(id=801, anonymous_id="SYNTHETIC-MEDIA-801", owner_user_id=1),
            main.Patient(id=802, anonymous_id="SYNTHETIC-MEDIA-802", owner_user_id=2),
        ])
        session.commit()

    raw = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(raw, format="PNG")
    request_key = "native-media-request-key-0001"
    batch_id = "native-media-batch-key-0001"
    upload_args = {
        "data": {
            "media_type": "RADIOGRAPH",
            "request_key": request_key,
            "batch_id": batch_id,
        },
        "files": {"file": ("synthetic-clinical.png", raw.getvalue(), "image/png")},
    }

    uploaded = client.post("/api/mobile/v1/patients/801/media", **upload_args)
    assert uploaded.status_code == 200, uploaded.text
    _assert_clinical_private_response(uploaded)
    uploaded_body = uploaded.json()
    assert uploaded_body["replayed"] is False
    media_id = uploaded_body["media"]["id"]

    # A lost response may be replayed with the same key; the acknowledgement
    # contains clinical metadata and must carry the same cache policy.
    replay = client.post("/api/mobile/v1/patients/801/media", **upload_args)
    assert replay.status_code == 200, replay.text
    _assert_clinical_private_response(replay)
    assert replay.json()["replayed"] is True

    with Session(engine) as session:
        session.add(main.PatientMedia(
            patient_id=801,
            owner_user_id=1,
            original_filename="synthetic-older.png",
            stored_filename="synthetic-older.png",
            file_path="uploads/patient-media/synthetic-older.png",
            media_type="PHOTO",
        ))
        session.commit()

    first_page = client.get("/api/mobile/v1/patients/801/media?limit=1")
    assert first_page.status_code == 200, first_page.text
    _assert_clinical_private_response(first_page)
    assert len(first_page.json()["items"]) == 1
    before = first_page.json()["next_before"]
    assert isinstance(before, int) and before > 0

    second_page = client.get(f"/api/mobile/v1/patients/801/media?before={before}&limit=1")
    assert second_page.status_code == 200, second_page.text
    _assert_clinical_private_response(second_page)
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["next_before"] is None

    receipt = client.get(f"/api/mobile/v1/patients/801/media/uploads/{request_key}")
    assert receipt.status_code == 200, receipt.text
    _assert_clinical_private_response(receipt)
    assert receipt.json()["found"] is True
    assert receipt.json()["media"]["id"] == media_id

    image_response = client.get(f"/api/mobile/v1/patients/801/media/{media_id}/file")
    assert image_response.status_code == 200, image_response.text
    _assert_clinical_private_response(image_response)
    assert image_response.headers.get("content-type") == "image/png"
    assert len(image_response.content) > 0

    # The same URLs must not reveal patient media or upload receipts to another account.
    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    assert client.get("/api/mobile/v1/patients/801/media").status_code == 404
    assert client.get(f"/api/mobile/v1/patients/801/media/uploads/{request_key}").status_code == 404
    assert client.get(f"/api/mobile/v1/patients/801/media/{media_id}/file").status_code == 404



@pytest.mark.parametrize("mutation", ["delete_media", "replace_source", "reassign_patient"])
def test_mobile_thumbnail_rechecks_owner_and_exact_source_after_generation(
    chat, monkeypatch, tmp_path, mutation
):
    client, engine = chat
    monkeypatch.setattr(mobile_modern_api_v3, "engine", engine)
    import app.clinical_media_thumbnail as thumbnails

    thumbnail_path = tmp_path / f"{mutation}-thumbnail.jpg"
    Image.new("RGB", (12, 12), "blue").save(thumbnail_path, format="JPEG")
    deleted = []
    source = f"r2://synthetic-private/patient-810/{mutation}.png"

    def generate(reference):
        assert reference == source
        with Session(engine) as session:
            patient = session.get(main.Patient, 810)
            media = session.get(main.PatientMedia, 8101)
            if mutation == "delete_media":
                session.delete(media)
            elif mutation == "replace_source":
                media.file_path = "r2://synthetic-private/patient-810/replacement.png"
            elif mutation == "reassign_patient":
                patient.owner_user_id = 2
            session.commit()
        return thumbnail_path

    monkeypatch.setattr(thumbnails, "ensure_thumbnail", generate)
    monkeypatch.setattr(thumbnails, "delete_thumbnail", lambda reference: deleted.append(reference))

    with Session(engine) as session:
        session.add(main.Patient(id=810, anonymous_id="SYNTHETIC-THUMBNAIL-RACE", owner_user_id=1))
        session.add(main.PatientMedia(
            id=8101,
            patient_id=810,
            owner_user_id=1,
            original_filename="synthetic.png",
            stored_filename="synthetic.png",
            file_path=source,
            media_type="RADIOGRAPH",
        ))
        session.commit()

    response = client.get("/api/mobile/v1/patients/810/media/8101/thumbnail")
    assert response.status_code == 404, response.text
    _assert_clinical_private_response(response)
    assert deleted == [source], "a stale derivative must be deleted using its original source key"



def test_mobile_thumbnail_success_is_private_and_owner_scoped(chat, monkeypatch, tmp_path):
    client, engine = chat
    monkeypatch.setattr(mobile_modern_api_v3, "engine", engine)
    import app.clinical_media_thumbnail as thumbnails

    thumbnail_path = tmp_path / "owner-thumbnail.jpg"
    Image.new("RGB", (16, 12), "green").save(thumbnail_path, format="JPEG")
    monkeypatch.setattr(thumbnails, "ensure_thumbnail", lambda _reference: thumbnail_path)

    with Session(engine) as session:
        session.add(main.Patient(id=811, anonymous_id="SYNTHETIC-THUMBNAIL-OWNER", owner_user_id=1))
        session.add(main.PatientMedia(
            id=8111,
            patient_id=811,
            owner_user_id=1,
            original_filename="synthetic.png",
            stored_filename="synthetic.png",
            file_path="r2://synthetic-private/patient-811/source.png",
            media_type="PHOTO",
        ))
        session.commit()

    response = client.get("/api/mobile/v1/patients/811/media/8111/thumbnail")
    assert response.status_code == 200, response.text
    _assert_clinical_private_response(response)
    assert response.headers.get("content-type") == "image/jpeg"
    assert response.headers.get("content-disposition", "").startswith("inline")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("content-security-policy") == "default-src 'none'; sandbox"
    assert response.content == thumbnail_path.read_bytes()

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    denied = client.get("/api/mobile/v1/patients/811/media/8111/thumbnail")
    assert denied.status_code == 404
    _assert_clinical_private_response(denied)
    assert denied.headers.get("content-type", "").startswith("application/json")


@pytest.mark.parametrize(
    ("failure", "status"),
    [(FileNotFoundError, 404), (ValueError, 415), (RuntimeError, 503)],
)
def test_mobile_thumbnail_generation_errors_are_private_and_do_not_leak_storage_details(
    chat, monkeypatch, failure, status
):
    client, engine = chat
    monkeypatch.setattr(mobile_modern_api_v3, "engine", engine)
    import app.clinical_media_thumbnail as thumbnails

    def fail(_reference):
        raise failure("synthetic-private-r2-object-key")

    monkeypatch.setattr(thumbnails, "ensure_thumbnail", fail)
    with Session(engine) as session:
        session.add(main.Patient(id=812, anonymous_id="SYNTHETIC-THUMBNAIL-ERROR", owner_user_id=1))
        session.add(main.PatientMedia(
            id=8121,
            patient_id=812,
            owner_user_id=1,
            original_filename="synthetic.png",
            stored_filename="synthetic.png",
            file_path="r2://synthetic-private/patient-812/source.png",
            media_type="PHOTO",
        ))
        session.commit()

    response = client.get("/api/mobile/v1/patients/812/media/8121/thumbnail")
    assert response.status_code == status, response.text
    _assert_clinical_private_response(response)
    assert "synthetic-private-r2-object-key" not in response.text
    if status == 503:
        assert response.headers.get("retry-after") == "2"


def test_mobile_patient_directory_search_matches_web_tckn_owner_scope_and_no_store(chat):
    client, engine = chat
    base = datetime(2026, 11, 19, 1, 0, 0)
    with Session(engine) as session:
        session.add_all([
            main.Patient(
                id=901, anonymous_id="PAT-SYNTH-TCKN-901", tc_kimlik_no="11111111111",
                first_name="TCKN", last_name="Search", phone="05551111111",
                owner_user_id=1, created_at=base,
            ),
            main.Patient(
                id=902, anonymous_id="PAT-SYNTH-TCKN-902", tc_kimlik_no="22222222222",
                first_name="TCKN", last_name="Other", phone="05552222222",
                owner_user_id=2, created_at=base,
            ),
            main.Patient(
                id=903, anonymous_id="PAT-SYNTH-DIR-903", first_name="Directory",
                last_name="Yılmaz", phone="05553333333", owner_user_id=1,
                created_at=base,
            ),
            main.Patient(
                id=904, anonymous_id="PAT-SYNTH-DIR-904", first_name="Directory",
                last_name="Aydın", phone="05554444444", owner_user_id=1,
                created_at=base - timedelta(minutes=1),
            ),
        ])
        session.commit()

    # The web search accepts TCKN and keeps the result within the signed-in owner.
    client.cookies.set(main.SESSION_COOKIE, _SESSION_TOKEN[1])
    web = client.get("/patients/search?q=11111111111")
    assert web.status_code == 200, web.text
    assert 'data-patient-id="901"' in web.text
    assert 'data-patient-id="902"' not in web.text

    mobile = client.get("/api/mobile/v1/patients?q=11111111111")
    assert mobile.status_code == 200, mobile.text
    assert mobile.headers.get("cache-control") == "private, no-store"
    assert mobile.headers.get("pragma") == "no-cache"
    assert "authorization" in {
        value.strip().lower() for value in mobile.headers.get("vary", "").split(",")
    }
    payload = mobile.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == [901]
    # TCKN is a search-only field in the directory response, not a list payload field.
    assert "tc_kimlik_no" not in payload["items"][0]

    # Partial TCKN search remains compatible with the web's substring behavior.
    partial = client.get("/api/mobile/v1/patients?q=111111")
    assert [item["id"] for item in partial.json()["items"]] == [901]

    # Another account's TCKN must not be discoverable from this account.
    hidden = client.get("/api/mobile/v1/patients?q=22222222222")
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0
    assert client.get("/api/mobile/v1/patients/902").status_code == 404

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    owned_by_second = client.get("/api/mobile/v1/patients?q=22222222222")
    assert owned_by_second.status_code == 200
    assert [item["id"] for item in owned_by_second.json()["items"]] == [902]

    # Search pages follow the web's surname/name order, not insertion recency.
    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[1]
    ordered = client.get("/api/mobile/v1/patients?q=Directory")
    assert ordered.status_code == 200
    assert [item["id"] for item in ordered.json()["items"]] == [904, 903]


def test_patient_detail_keeps_chart_and_media_queries_out_of_profile_reads(chat, monkeypatch):
    client, engine = chat
    monkeypatch.setattr(mobile_api, "engine", engine)
    with Session(engine) as session:
        session.add(main.Patient(id=880, anonymous_id="SYNTHETIC-LAZY-PROFILE-880", owner_user_id=1))
        session.add(main.ToothStatus(id=8801, patient_id=880, tooth_number="36", status="CARIES"))
        session.add(main.ToothSurfaceStatus(
            id=8802, patient_id=880, tooth_number="36", surface="MESIAL", status="FILLING",
        ))
        session.add(main.PatientMedia(
            id=8803, patient_id=880, owner_user_id=1,
            original_filename="synthetic.png", stored_filename="synthetic.png",
            file_path="/private/synthetic.png", media_type="PHOTO",
        ))
        session.commit()

    profile = client.get("/api/mobile/v1/patients/880", params={"include_chart": "false", "include_media": "false"})
    assert profile.status_code == 200, profile.text
    assert profile.headers["cache-control"] == "private, no-store"
    assert profile.json()["teeth"] == []
    assert profile.json()["surfaces"] == []
    assert profile.json()["media"] == []

    chart = client.get("/api/mobile/v1/patients/880", params={"include_chart": "true", "include_media": "false"})
    assert chart.status_code == 200, chart.text
    assert [item["tooth_number"] for item in chart.json()["teeth"]] == ["36"]
    assert [(item["tooth_number"], item["surface"]) for item in chart.json()["surfaces"]] == [("36", "MESIAL")]
    assert chart.json()["media"] == []

    # Omitting the new query keeps the original response for older native clients.
    legacy = client.get("/api/mobile/v1/patients/880")
    assert legacy.status_code == 200, legacy.text
    assert [item["tooth_number"] for item in legacy.json()["teeth"]] == ["36"]
    assert [(item["tooth_number"], item["surface"]) for item in legacy.json()["surfaces"]] == [("36", "MESIAL")]
    assert [item["id"] for item in legacy.json()["media"]] == [8803]

    media_only = client.get(
        "/api/mobile/v1/patients/880",
        params={"include_chart": "false", "include_media": "true"},
    )
    assert media_only.status_code == 200, media_only.text
    assert media_only.json()["teeth"] == []
    assert media_only.json()["surfaces"] == []
    assert [item["id"] for item in media_only.json()["media"]] == [8803]

    # The profile's gallery remains available through its separate bounded endpoint.
    gallery = client.get("/api/mobile/v1/patients/880/media")
    assert gallery.status_code == 200, gallery.text
    assert [item["id"] for item in gallery.json()["items"]] == [8803]

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    assert client.get("/api/mobile/v1/patients/880").status_code == 404
    assert client.get("/api/mobile/v1/patients/880", params={"include_chart": "true"}).status_code == 404



def test_native_analysis_history_is_patient_tooth_and_cursor_scoped(chat, monkeypatch):
    client, engine = chat
    monkeypatch.setattr(mobile_analysis_api, "engine", engine)
    base = datetime(2026, 11, 20, 8, 0, 0)
    with Session(engine) as session:
        session.add_all([
            main.Patient(id=810, anonymous_id="SYNTHETIC-HISTORY-810", owner_user_id=1),
            main.Patient(id=820, anonymous_id="SYNTHETIC-HISTORY-820", owner_user_id=1),
            main.Patient(id=910, anonymous_id="SYNTHETIC-HISTORY-910", owner_user_id=2),
        ])
        session.add_all([
            main.Analysis(id=101, patient_id=810, tooth_number="36", status="FINAL", created_at=base),
            main.Analysis(id=102, patient_id=810, tooth_number="36", status="AI_ANALYZED", created_at=base + timedelta(minutes=1)),
            main.Analysis(id=103, patient_id=810, tooth_number="37", status="DRAFT", created_at=base + timedelta(minutes=2)),
            main.Analysis(id=201, patient_id=820, tooth_number="11", status="FINAL", created_at=base + timedelta(minutes=3)),
            main.Analysis(id=301, patient_id=910, tooth_number="21", status="FINAL", created_at=base + timedelta(minutes=4)),
        ])
        session.commit()

    first = client.get("/api/mobile/v1/analyses", params={"patient_id": 810, "limit": 2})
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "private, no-store"
    assert [item["id"] for item in first.json()["items"]] == [103, 102]
    assert first.json()["total"] == 3
    assert first.json()["next_before"] == 102

    second = client.get(
        "/api/mobile/v1/analyses",
        params={"patient_id": 810, "limit": 2, "before": first.json()["next_before"]},
    )
    assert second.status_code == 200, second.text
    assert [item["id"] for item in second.json()["items"]] == [101]
    assert second.json()["total"] == 3
    assert second.json()["next_before"] is None

    tooth = client.get(
        "/api/mobile/v1/analyses",
        params={"patient_id": 810, "tooth_number": "36"},
    )
    assert tooth.status_code == 200, tooth.text
    assert [item["id"] for item in tooth.json()["items"]] == [102, 101]
    assert tooth.json()["total"] == 2
    assert all(item["patient_id"] == 810 for item in tooth.json()["items"])

    # A caller cannot use a patient filter to discover another owner's history.
    assert client.get("/api/mobile/v1/analyses", params={"patient_id": 910}).status_code == 404
    assert client.get(
        "/api/mobile/v1/analyses",
        params={"patient_id": 810, "tooth_number": "99"},
    ).status_code == 422
    assert client.get("/api/mobile/v1/analyses", params={"patient_id": -1}).status_code == 422

    # Existing owner-wide callers without patient_id retain their prior contract.
    owner_wide = client.get("/api/mobile/v1/analyses", params={"limit": 50})
    assert owner_wide.status_code == 200, owner_wide.text
    assert [item["id"] for item in owner_wide.json()["items"]] == [201, 103, 102, 101]
    assert owner_wide.json()["total"] == 4


def test_native_analysis_history_stable_cursor_matches_web_order_and_snapshot(chat, monkeypatch):
    client, engine = chat
    monkeypatch.setattr(mobile_analysis_api, "engine", engine)
    base = datetime(2026, 11, 20, 8, 0, 0)
    with Session(engine) as session:
        session.add(main.Patient(
            id=811, anonymous_id="SYNTHETIC-STABLE-HISTORY-811", owner_user_id=1
        ))
        # IDs intentionally run opposite to creation time. Two records share
        # a timestamp so the web's descending ID tie-break is also exercised.
        session.add_all([
            main.Analysis(id=1201, patient_id=811, tooth_number="36", status="FINAL",
                          created_at=base + timedelta(minutes=2)),
            main.Analysis(id=1202, patient_id=811, tooth_number="36", status="FINAL",
                          created_at=base + timedelta(minutes=1)),
            main.Analysis(id=1203, patient_id=811, tooth_number="36", status="FINAL",
                          created_at=base + timedelta(minutes=1)),
            main.Analysis(id=1204, patient_id=811, tooth_number="36", status="FINAL",
                          created_at=base),
        ])
        session.commit()

    first = client.get(
        "/api/mobile/v1/analyses",
        params={"patient_id": 811, "limit": 2, "stable_order": "true"},
    )
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "private, no-store"
    assert [item["id"] for item in first.json()["items"]] == [1201, 1203]
    assert first.json()["total"] == 4
    cursor = first.json()["next_cursor"]
    assert isinstance(cursor, str) and cursor
    assert first.json()["next_before"] is None

    # A newer row inserted after page one must not shift the cursor boundary.
    with Session(engine) as session:
        session.add(main.Analysis(
            id=1205, patient_id=811, tooth_number="11", status="FINAL",
            created_at=base + timedelta(minutes=3),
        ))
        session.commit()

    second = client.get(
        "/api/mobile/v1/analyses",
        params={
            "patient_id": 811,
            "limit": 2,
            "stable_order": "true",
            "before_cursor": cursor,
        },
    )
    assert second.status_code == 200, second.text
    assert [item["id"] for item in second.json()["items"]] == [1202, 1204]
    assert second.json()["next_cursor"] is None
    assert second.json()["next_before"] is None
    assert 1205 not in [item["id"] for item in second.json()["items"]]

    assert client.get(
        "/api/mobile/v1/analyses",
        params={"patient_id": 811, "stable_order": "true", "before_cursor": "!"},
    ).status_code == 422
    assert client.get(
        "/api/mobile/v1/analyses",
        params={
            "patient_id": 811,
            "stable_order": "true",
            "before": 1203,
            "before_cursor": cursor,
        },
    ).status_code == 422
