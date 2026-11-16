from test_mobile_chat_actions import chat
from app import main, mobile_analysis_api, mobile_api
from app.work_jobs import WorkJob, prune_history
from sqlmodel import Session, select
from datetime import datetime
from PIL import Image
import io
import json

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
    assert status.headers.get("cache-control") == "private, no-store"
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
    saved = client.post("/api/mobile/v1/patients/86/media", data={
        "media_type": "PHOTO", "request_key": "synthetic-media-long-name-0001",
    }, files={"file": (long_name, raw.getvalue(), "image/png")})
    assert saved.status_code == 200, saved.text
    with Session(engine) as session:
        media = session.exec(select(main.PatientMedia).where(main.PatientMedia.patient_id == 86)).one()
        assert len(media.original_filename) == 255
        assert media.original_filename.endswith(".png")

    invalid_tooth = client.post("/api/mobile/v1/patients/86/media", data={
        "media_type": "PHOTO", "tooth_number": "56",
        "request_key": "synthetic-media-invalid-fdi-0001",
    }, files={"file": ("synthetic.png", raw.getvalue(), "image/png")})
    assert invalid_tooth.status_code == 422

    monkeypatch.setattr(mobile_api, "MOBILE_MAX_PATIENT_MEDIA_BYTES", 64)
    oversized = client.post("/api/mobile/v1/patients/86/media", data={
        "media_type": "PHOTO", "request_key": "synthetic-media-over-limit-0001",
    }, files={"file": ("synthetic.png", raw.getvalue(), "image/png")})
    assert oversized.status_code == 413


def test_web_analysis_selection_and_submission_share_four_image_limit(chat,monkeypatch,tmp_path):
    client,engine=chat
    client.cookies.set(main.SESSION_COOKIE,'token1')
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
    assert '4 kayıtlı görüntü analiz için seçildi' in accepted.text
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
    assert 'toplam en fazla 4' in submitted.text
    with Session(engine) as session:
        assert not session.exec(select(main.Analysis).where(main.Analysis.patient_id==80)).all()


def test_patient_archive_accepts_twelve_images_and_rejects_thirteen(chat,monkeypatch,tmp_path):
    client,engine=chat
    client.cookies.set(main.SESSION_COOKIE,'token1')
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


def _post_patient_media_batch_file(client, raw, request_key, batch_id, filename='synthetic.png'):
    return client.post(
        '/api/mobile/v1/patients/8/media',
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
