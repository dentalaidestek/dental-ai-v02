from test_mobile_chat_actions import chat
from app import main, mobile_analysis_api, mobile_api
from app.work_jobs import WorkJob, prune_history
from sqlmodel import Session, select
from datetime import datetime
from PIL import Image
import io

def test_patient_history_filters_tooth_and_marks_only_confirmed_voice_reviews(chat,monkeypatch):
    client,engine=chat;monkeypatch.setattr(mobile_analysis_api,'engine',engine)
    with Session(engine) as s:
        s.add(main.Patient(id=8,anonymous_id='SYNTHETIC-8',owner_user_id=1))
        s.add(main.Patient(id=9,anonymous_id='SYNTHETIC-9',owner_user_id=2))
        for ident,patient,tooth in [(11,8,'36'),(12,8,'35'),(13,9,'36')]:
            s.add(main.Analysis(id=ident,patient_id=patient,tooth_number=tooth,status='DRAFT'))
        s.add(WorkJob(owner_user_id=1,resource_id=11,resource_type='ANALYSIS',kind='VOICE_REVIEW',status='DONE',source_hash='synthetic-hash',dedupe_key='synthetic-parity',payload_json='{}'))
        s.commit()
    response=client.get('/api/mobile/v1/analyses?patient_id=8&tooth_number=36')
    assert response.status_code==200,response.text
    assert [(r['id'],r['is_voice_review']) for r in response.json()['items']]==[(11,True)]
    assert client.get('/api/mobile/v1/analyses?patient_id=9').status_code==404
    assert client.get('/api/mobile/v1/analyses?patient_id=8&tooth_number=56').status_code==422
    assert client.get('/api/mobile/v1/analyses/11').json()['analysis']['is_voice_review'] is True

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
        s.commit()
    assert client.post('/api/mobile/v1/patients/8/media/analyze',json={'media_ids':[9]}).status_code==404
    assert client.post('/api/mobile/v1/patients/9/media/analyze',json={'media_ids':[9]}).status_code==404
    assert client.post('/api/mobile/v1/patients/8/media/analyze',json={'media_ids':[8,8]}).status_code==422
    assert client.post('/api/mobile/v1/patients/8/media/analyze',json={'media_ids':[8],'clinical_notes':'x'*4001}).status_code==422
    response=client.post('/api/mobile/v1/patients/8/media/analyze',json={
        'media_ids':[8], 'tooth_number':'36', 'clinical_notes':'Soğukta kısa süreli ağrı.'
    })
    assert response.status_code==200,response.text
    with Session(engine) as s:
        analysis=s.get(main.Analysis,response.json()['analysis_id'])
        assert analysis.patient_id==8
        assert analysis.tooth_number=='36'
        assert analysis.clinical_notes=='Soğukta kısa süreli ağrı.'
        from sqlmodel import select
        assert len(s.exec(select(main.ImageAsset).where(main.ImageAsset.analysis_id==analysis.id)).all())==1
    assert client.delete('/api/mobile/v1/patients/9/media').status_code==404
    assert client.delete('/api/mobile/v1/patients/8/media').status_code==200
    with Session(engine) as s:
        assert s.get(main.PatientMedia,8) is None
        assert s.get(main.PatientMedia,9) is not None

def test_native_uploads_return_confirmed_success_after_persistence(chat,monkeypatch,tmp_path):
    from app import mobile_api
    client,engine=chat;monkeypatch.setattr(mobile_analysis_api,'engine',engine)
    monkeypatch.setattr(main,'classify_dental_image',lambda path:'PHOTO')
    monkeypatch.setattr(mobile_analysis_api,'classify_dental_image',lambda path:'PHOTO')
    monkeypatch.setattr(main,'storage_persist_file',lambda path:None)
    monkeypatch.setattr(mobile_api,'storage_persist_file',lambda path:None)
    monkeypatch.setattr(mobile_analysis_api,'storage_persist_file',lambda path:None)
    monkeypatch.chdir(tmp_path)
    with Session(engine) as s:
        s.add(main.Patient(id=8,anonymous_id='SYNTHETIC-UPLOAD',owner_user_id=1));s.commit()
    raw=io.BytesIO();Image.new('RGB',(8,8),'white').save(raw,format='PNG')
    response=client.post('/api/mobile/v1/patients/8/media',files={'file':('synthetic.png',raw.getvalue(),'image/png')})
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

    client.headers["Authorization"] = "Bearer token2"
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

    client.headers["Authorization"] = "Bearer token2"
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
    first = client.post("/api/mobile/v1/patients/84/media", data={
        "media_type": "PHOTO", "request_key": key,
    }, files={"file": ("synthetic.png", payload, "image/png")})
    assert first.status_code == 200, first.text
    assert first.json()["replayed"] is False

    replay = client.post("/api/mobile/v1/patients/84/media", data={
        "media_type": "PHOTO", "request_key": key,
    }, files={"file": ("synthetic.png", payload, "image/png")})
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["media"]["id"] == first.json()["media"]["id"]
    assert len(persisted) == 1, "replayed upload must not persist a second object"

    status = client.get(f"/api/mobile/v1/patients/84/media/uploads/{key}")
    assert status.status_code == 200, status.text
    assert status.json()["found"] is True
    assert status.json()["media"]["id"] == first.json()["media"]["id"]

    changed = io.BytesIO()
    Image.new("RGB", (16, 12), (30, 20, 10)).save(changed, format="PNG")
    conflict = client.post("/api/mobile/v1/patients/84/media", data={
        "media_type": "PHOTO", "request_key": key,
    }, files={"file": ("synthetic.png", changed.getvalue(), "image/png")})
    assert conflict.status_code == 409

    client.headers["Authorization"] = "Bearer token2"
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

    client.headers["Authorization"] = "Bearer token1"
    deleted_replay = client.post("/api/mobile/v1/patients/84/media", data={
        "media_type": "PHOTO", "request_key": key,
    }, files={"file": ("synthetic.png", payload, "image/png")})
    assert deleted_replay.status_code == 409, "a deleted upload receipt must not resurrect the image"


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
