import json
from sqlmodel import Session,select
from test_mobile_chat_actions import chat, _SESSION_TOKEN
from app import main,mobile_analysis_api,work_jobs


def setup(chat,monkeypatch):
    c,engine=chat;monkeypatch.setattr(mobile_analysis_api,'engine',engine);monkeypatch.setenv('DENTAL_INFERENCE_REVISION','1');monkeypatch.setattr(work_jobs,'_code_version',lambda:'synthetic-code')
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
    c.headers['Authorization']='Bearer ' + _SESSION_TOKEN[2];assert c.get(path).status_code==404
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


def test_mobile_analysis_workspace_returns_only_minimal_patient_context(chat,monkeypatch):
    c,engine=setup(chat,monkeypatch)
    with Session(engine) as s:
        patient=s.get(main.Patient,8)
        patient.first_name='Synthetic'
        patient.last_name='Patient'
        patient.phone='+905550000000'
        patient.birth_date='1990-01-01'
        patient.age=36
        patient.chief_complaint='Synthetic sensitivity complaint'
        s.add(patient);s.commit()
    response=c.get('/api/mobile/v1/analyses/1')
    assert response.status_code==200,response.text
    patient_payload=response.json()['patient']
    assert set(patient_payload)=={'id','anonymous_id','age','chief_complaint'}
    assert patient_payload['anonymous_id']=='SYNTHETIC-VIEWER'
    assert patient_payload['age']==36
    assert patient_payload['chief_complaint']=='Synthetic sensitivity complaint'
    for field in ('first_name','last_name','phone','birth_date','tc_kimlik_no','address','created_at'):
        assert field not in patient_payload


def test_analysis_detail_does_not_read_or_return_duplicate_raw_result(chat,monkeypatch,tmp_path):
    c,engine=setup(chat,monkeypatch)
    result_path=tmp_path/'private-analysis-result.json'
    result_path.write_text(json.dumps({'ai_result':{'private_marker':'Synthetic private result payload'}}))
    with Session(engine) as s:
        analysis=s.get(main.Analysis,1)
        analysis.result_path=str(result_path)
        s.add(analysis);s.commit()
    def forbidden_result_read(_path):
        raise AssertionError('metadata endpoint must not read the clinical result object')
    monkeypatch.setattr(mobile_analysis_api,'storage_ensure_local',forbidden_result_read)
    response=c.get('/api/mobile/v1/analyses/1')
    assert response.status_code==200,response.text
    payload=response.json()
    assert set(payload)=={'analysis','patient','assets','job'}
    assert 'ai_result' not in payload
    assert 'Synthetic private result payload' not in response.text
