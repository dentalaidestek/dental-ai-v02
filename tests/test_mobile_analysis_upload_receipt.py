import io
from PIL import Image
from sqlmodel import Session,select
from test_mobile_chat_actions import chat
from app import main,mobile_analysis_api,work_jobs


def setup(chat,monkeypatch,tmp_path):
    c,engine=chat;monkeypatch.setattr(mobile_analysis_api,'engine',engine);monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mobile_analysis_api,'storage_persist_file',lambda _:None)
    monkeypatch.setattr(mobile_analysis_api,'classify_dental_image',lambda _:'PERIAPICAL')
    monkeypatch.setattr(work_jobs,'_code_version',lambda:'synthetic-code')
    with Session(engine) as s:
        s.add(main.Patient(id=8,anonymous_id='SYNTHETIC-8',owner_user_id=1));s.add(main.Patient(id=9,anonymous_id='SYNTHETIC-9',owner_user_id=2));s.commit()
    raw=io.BytesIO();Image.new('RGB',(8,8),'white').save(raw,format='PNG')
    return c,engine,raw.getvalue()


def post(c,raw,key='synthetic-upload-key-001',patient='8',note='Synthetic clinical context'):
    return c.post('/api/mobile/v1/analyses',data={'patient_id':patient,'request_key':key,'tooth_number':'36','clinical_notes':note},files={'images':('synthetic.png',raw,'image/png')})


def test_same_upload_key_and_bytes_reuse_committed_analysis_and_job(chat,monkeypatch,tmp_path):
    c,engine,raw=setup(chat,monkeypatch,tmp_path)
    first=post(c,raw);assert first.status_code==200,first.text
    again=post(c,raw);assert again.status_code==200 and again.json()['analysis_id']==first.json()['analysis_id']
    receipt=c.get('/api/mobile/v1/analyses/uploads/receipt?patient_id=8&request_key=synthetic-upload-key-001')
    assert receipt.status_code==200 and receipt.json()['receipt']['analysis_id']==first.json()['analysis_id']
    assert receipt.json()['receipt']['job_id']==first.json()['job_id']
    with Session(engine) as s:
        assert len(s.exec(select(main.Analysis)).all())==1
        assert len(s.exec(select(main.ImageAsset)).all())==1
        assert len(s.exec(select(work_jobs.WorkJob).where(work_jobs.WorkJob.kind=='VISION')).all())==1


def test_reusing_upload_key_with_changed_context_or_bytes_is_conflict(chat,monkeypatch,tmp_path):
    c,engine,raw=setup(chat,monkeypatch,tmp_path);assert post(c,raw).status_code==200
    assert post(c,raw,note='Changed synthetic context').status_code==409
    changed=io.BytesIO();Image.new('RGB',(8,8),'black').save(changed,format='PNG')
    assert post(c,changed.getvalue()).status_code==409
    with Session(engine) as s:assert len(s.exec(select(main.Analysis)).all())==1


def test_upload_receipt_is_patient_owned_and_absent_is_distinct(chat,monkeypatch,tmp_path):
    c,_,raw=setup(chat,monkeypatch,tmp_path);assert post(c,raw).status_code==200
    assert c.get('/api/mobile/v1/analyses/uploads/receipt?patient_id=8&request_key=synthetic-missing-key-001').json()['receipt'] is None
    assert c.get('/api/mobile/v1/analyses/uploads/receipt?patient_id=9&request_key=synthetic-upload-key-001').status_code==404
    c.headers['Authorization']='Bearer token2'
    assert c.get('/api/mobile/v1/analyses/uploads/receipt?patient_id=8&request_key=synthetic-upload-key-001').status_code==404
    assert post(c,raw).status_code==404


def test_receipt_resolves_a_lost_postcommit_publication_response(chat,monkeypatch,tmp_path):
    c,engine,raw=setup(chat,monkeypatch,tmp_path)
    async def fail(*_):raise RuntimeError('synthetic postcommit publication outage')
    monkeypatch.setattr(mobile_analysis_api,'_publish_realtime_event',fail)
    import pytest
    with pytest.raises(RuntimeError):post(c,raw)
    response=c.get('/api/mobile/v1/analyses/uploads/receipt?patient_id=8&request_key=synthetic-upload-key-001')
    assert response.status_code==200 and response.json()['receipt']['analysis_id']>0
    assert post(c,raw).status_code==200


def test_invalid_fdi_key_and_file_do_not_allocate_analysis(chat,monkeypatch,tmp_path):
    c,engine,raw=setup(chat,monkeypatch,tmp_path)
    assert post(c,raw,key='short').status_code==422
    assert c.post('/api/mobile/v1/analyses',data={'patient_id':'8','tooth_number':'59'},files={'images':('synthetic.png',raw,'image/png')}).status_code==422
    assert post(c,b'not an image').status_code==422
    assert c.get('/api/mobile/v1/analyses/uploads/receipt?patient_id=8&request_key=synthetic-upload-key-001').json()['receipt'] is None
    with Session(engine) as s:assert not s.exec(select(main.Analysis)).all()


def test_receipt_survives_normal_job_history_pruning_while_analysis_exists(chat,monkeypatch,tmp_path):
    from datetime import timedelta
    c,engine,raw=setup(chat,monkeypatch,tmp_path);assert post(c,raw).status_code==200
    with Session(engine) as s:
        for row in s.exec(select(work_jobs.WorkJob)).all():row.status='DONE';row.updated_at=work_jobs.now()-timedelta(days=31);s.add(row)
        s.commit()
    work_jobs.prune_history(engine)
    receipt=c.get('/api/mobile/v1/analyses/uploads/receipt?patient_id=8&request_key=synthetic-upload-key-001').json()['receipt']
    assert receipt is not None
    assert post(c,raw).json()['analysis_id']==receipt['analysis_id']
    with Session(engine) as s:assert len(s.exec(select(main.Analysis)).all())==1


def test_deleted_analysis_receipt_remains_prunable(chat,monkeypatch,tmp_path):
    from datetime import timedelta
    c,engine,raw=setup(chat,monkeypatch,tmp_path);result=post(c,raw);assert result.status_code==200
    with Session(engine) as s:
        for row in s.exec(select(work_jobs.WorkJob)).all():row.status='DONE';row.updated_at=work_jobs.now()-timedelta(days=31);s.add(row)
        s.delete(s.get(main.Analysis,result.json()['analysis_id']));s.commit()
    work_jobs.prune_history(engine)
    with Session(engine) as s:assert not s.exec(select(work_jobs.WorkJob)).all()


def test_invalid_second_image_leaves_no_unowned_clinical_file(chat,monkeypatch,tmp_path):
    from pathlib import Path
    c,engine,raw=setup(chat,monkeypatch,tmp_path);persisted=[]
    monkeypatch.setattr(mobile_analysis_api,'storage_persist_file',lambda p:persisted.append(str(p)))
    response=c.post('/api/mobile/v1/analyses',data={'patient_id':'8','request_key':'synthetic-bad-batch-001'},files=[('images',('first.png',raw,'image/png')),('images',('second.png',b'invalid image bytes','image/png'))])
    assert response.status_code==422
    assert persisted==[]
    assert not [p for p in Path('uploads').rglob('*') if p.is_file()]
    with Session(engine) as s:assert not s.exec(select(main.Analysis)).all()


def _saved_media(engine,path,media_id=31,patient_id=8,owner_id=1):
    with Session(engine) as s:
        s.add(main.PatientMedia(
            id=media_id,patient_id=patient_id,owner_user_id=owner_id,
            original_filename=f"saved-{media_id}.png",stored_filename=f"saved-{media_id}.png",
            file_path=str(path),media_type="RADIOGRAPH",
        ))
        s.commit()


def _post_mixed(c,raw,ids,key="synthetic-mixed-upload-001"):
    data={"patient_id":"8","request_key":key,"existing_media_ids":ids,"tooth_number":"36","clinical_notes":"Synthetic mixed context"}
    files=[("images",("new.png",raw,"image/png"))] if raw is not None else None
    return c.post("/api/mobile/v1/analyses",data=data,files=files)


def test_mixed_saved_and_new_media_create_one_owned_analysis_and_idempotent_receipt(chat,monkeypatch,tmp_path):
    from pathlib import Path
    c,engine,raw=setup(chat,monkeypatch,tmp_path)
    saved=tmp_path/"saved.png";saved.write_bytes(raw)
    _saved_media(engine,saved)
    monkeypatch.setattr(mobile_analysis_api,"storage_ensure_local",lambda value:Path(value))
    first=_post_mixed(c,raw,"31")
    assert first.status_code==200,first.text
    again=_post_mixed(c,raw,"31")
    assert again.status_code==200 and again.json()["analysis_id"]==first.json()["analysis_id"]
    with Session(engine) as s:
        analysis=s.get(main.Analysis,first.json()["analysis_id"])
        assets=s.exec(select(main.ImageAsset).where(main.ImageAsset.analysis_id==analysis.id).order_by(main.ImageAsset.id)).all()
        jobs=s.exec(select(work_jobs.WorkJob).where(work_jobs.WorkJob.kind=="VISION")).all()
        receipts=s.exec(select(work_jobs.WorkJob).where(work_jobs.WorkJob.kind=="UPLOAD_RECEIPT")).all()
        assert analysis.patient_id==8 and analysis.tooth_number=="36"
        assert analysis.clinical_notes=="Synthetic mixed context"
        assert [asset.original_filename for asset in assets]==["saved-31.png","new.png"]
        assert len(assets)==2 and all(Path(asset.file_path).is_file() for asset in assets)
        assert len(jobs)==1 and len(receipts)==1
    receipt=c.get("/api/mobile/v1/analyses/uploads/receipt?patient_id=8&request_key=synthetic-mixed-upload-001")
    assert receipt.status_code==200 and receipt.json()["receipt"]["analysis_id"]==first.json()["analysis_id"]


def test_saved_media_only_is_a_valid_analysis_and_changed_saved_ids_conflict(chat,monkeypatch,tmp_path):
    from pathlib import Path
    c,engine,raw=setup(chat,monkeypatch,tmp_path)
    first_path=tmp_path/"saved-31.png";first_path.write_bytes(raw)
    second_path=tmp_path/"saved-32.png";second_path.write_bytes(raw)
    _saved_media(engine,first_path,31)
    _saved_media(engine,second_path,32)
    monkeypatch.setattr(mobile_analysis_api,"storage_ensure_local",lambda value:Path(value))
    first=_post_mixed(c,None,"31","synthetic-saved-only-001")
    assert first.status_code==200,first.text
    changed=_post_mixed(c,None,"32","synthetic-saved-only-001")
    assert changed.status_code==409
    with Session(engine) as s:
        assert len(s.exec(select(main.Analysis)).all())==1
        assert len(s.exec(select(main.ImageAsset)).all())==1


def test_mixed_media_rejects_foreign_duplicate_missing_and_over_limit_ids_before_commit(chat,monkeypatch,tmp_path):
    from pathlib import Path
    c,engine,raw=setup(chat,monkeypatch,tmp_path)
    saved=tmp_path/"saved.png";saved.write_bytes(raw)
    _saved_media(engine,saved,31,8,2)
    monkeypatch.setattr(mobile_analysis_api,"storage_ensure_local",lambda value:Path(value))
    for ids,key in [("31","synthetic-foreign-media-001"),("31,31","synthetic-duplicate-media-01"),("999","synthetic-missing-media-001"),("x","synthetic-malformed-media-01")]:
        response=_post_mixed(c,raw,ids,key)
        assert response.status_code in {404,422},(ids,response.text)
    with Session(engine) as s:
        for media_id in range(40,44):
            s.add(main.PatientMedia(id=media_id,patient_id=8,owner_user_id=1,original_filename=f"{media_id}.png",stored_filename=f"{media_id}.png",file_path=str(saved),media_type="PHOTO"))
        s.commit()
    too_many=_post_mixed(c,raw,"40,41,42,43","synthetic-over-limit-media-01")
    assert too_many.status_code==422
    with Session(engine) as s:
        assert not s.exec(select(main.Analysis)).all()
        assert not s.exec(select(main.ImageAsset)).all()


def test_invalid_saved_media_file_does_not_publish_partial_mixed_batch(chat,monkeypatch,tmp_path):
    from pathlib import Path
    c,engine,raw=setup(chat,monkeypatch,tmp_path);persisted=[]
    saved=tmp_path/"broken.png";saved.write_bytes(b"not an image")
    _saved_media(engine,saved)
    monkeypatch.setattr(mobile_analysis_api,"storage_ensure_local",lambda value:Path(value))
    monkeypatch.setattr(mobile_analysis_api,"storage_persist_file",lambda value:persisted.append(str(value)))
    response=_post_mixed(c,raw,"31","synthetic-broken-saved-media-01")
    assert response.status_code==422
    assert persisted==[]
    with Session(engine) as s:
        assert not s.exec(select(main.Analysis)).all()
        assert not s.exec(select(main.ImageAsset)).all()
