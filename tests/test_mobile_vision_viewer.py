import json
from sqlmodel import Session,select
from test_mobile_chat_actions import chat
from app import main,work_jobs


def setup(chat,monkeypatch):
    c,engine=chat;monkeypatch.setenv('DENTAL_INFERENCE_REVISION','1');monkeypatch.setattr(work_jobs,'_code_version',lambda:'synthetic-code')
    with Session(engine) as s:
        s.add(main.Patient(id=8,owner_user_id=1,anonymous_id='SYNTHETIC-VIEWER'))
        s.add(main.Analysis(id=1,patient_id=8,status='VISION_READY'))
        s.add(main.ImageAsset(id=4,analysis_id=1,original_filename='synthetic.png',stored_filename='synthetic.png',file_path='synthetic.png',image_type='PERIAPICAL',vision_snapshot_json=json.dumps({'_inference_revision':'1','findings':[{'finding_code':'CARIES','confidence':.9,'bbox':[.2,.3,.4,.5]}]})))
        s.commit()
    return c,engine


def test_native_viewer_reads_canonical_owned_snapshot_without_new_inference(chat,monkeypatch):
    c,engine=setup(chat,monkeypatch);path='/api/mobile/v1/analyses/1/assets/4/vision'
    r=c.get(path);assert r.status_code==200,r.text
    assert r.json()['findings'][0]['bbox']==[.2,.3,.4,.5]
    assert r.headers['cache-control']=='private, no-store'
    assert c.get('/api/mobile/v1/analyses/2/assets/4/vision').status_code==404
    c.headers['Authorization']='Bearer token2';assert c.get(path).status_code==404
    with Session(engine) as s:assert not s.exec(select(work_jobs.WorkJob)).all()


def test_missing_viewer_snapshot_recovers_one_canonical_vision_job(chat,monkeypatch):
    c,engine=setup(chat,monkeypatch)
    with Session(engine) as s:a=s.get(main.ImageAsset,4);a.vision_snapshot_json=None;s.add(a);s.commit()
    path='/api/mobile/v1/analyses/1/assets/4/vision'
    first=c.get(path);assert first.status_code==202,first.text
    assert c.get(path).json()['job_id']==first.json()['job_id']
    with Session(engine) as s:assert len(s.exec(select(work_jobs.WorkJob)).all())==1


def test_failed_viewer_job_reports_failure_without_automatic_paid_retry(chat,monkeypatch):
    c,engine=setup(chat,monkeypatch)
    with Session(engine) as s:a=s.get(main.ImageAsset,4);a.vision_snapshot_json=None;s.add(a);s.commit()
    path='/api/mobile/v1/analyses/1/assets/4/vision';ident=c.get(path).json()['job_id']
    with Session(engine) as s:j=s.get(work_jobs.WorkJob,ident);j.status='FAILED';j.error_code='PRIVATE_PROVIDER_ERROR';s.add(j);s.commit()
    r=c.get(path);assert r.status_code==503 and r.json()['job_id']==ident
    assert 'PRIVATE_PROVIDER_ERROR' not in r.text
    with Session(engine) as s:assert len(s.exec(select(work_jobs.WorkJob)).all())==1
