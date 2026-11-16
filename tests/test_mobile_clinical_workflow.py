import json
from sqlmodel import Session,select
from test_mobile_chat_actions import chat
from app import main,mobile_analysis_api,work_jobs

RESULT={'status':'INITIAL','most_likely':'Synthetic likely condition','findings':['Synthetic string finding'],'treatment_options':['Synthetic option'],'treatment_cautions':['Synthetic caution'],'preferred_approach':'Synthetic approach','differential':['Synthetic differential'],'recommended_evaluation':['Synthetic exam'],'uncertainty':'Synthetic uncertainty','questions':[{'question':'Synthetic clinical question?','type':'TEXT'}]}

def setup(chat,monkeypatch,tmp_path):
    c,engine=chat;monkeypatch.setattr(mobile_analysis_api,'engine',engine);monkeypatch.setattr(work_jobs,'_code_version',lambda:'synthetic-code')
    path=tmp_path/'result.json';path.write_text(json.dumps({'ai_result':RESULT}))
    with Session(engine) as s:
        s.add(main.Patient(id=1,owner_user_id=1,anonymous_id='SYNTHETIC'))
        s.add(main.Analysis(id=1,patient_id=1,status='AI_ANALYZED',result_path=str(path)));s.commit()
    return c,engine,path


def test_clinical_strings_questions_and_owner(chat,monkeypatch,tmp_path):
    c,_,_=setup(chat,monkeypatch,tmp_path);r=c.get('/api/mobile/v1/analyses/1/clinical');assert r.status_code==200,r.text
    assert r.json()['result']['findings']==RESULT['findings'] and r.json()['result']['questions']==RESULT['questions']
    assert r.json()['patient_anonymous_id']=='SYNTHETIC'
    assert len(r.json()['revision'])==64 and r.headers['cache-control']=='private, no-store'
    c.headers['Authorization']='Bearer token2';assert c.get('/api/mobile/v1/analyses/1/clinical').status_code==404


def test_final_answers_use_web_dedup_and_existing_receipt_after_completion(chat,monkeypatch,tmp_path):
    c,engine,path=setup(chat,monkeypatch,tmp_path);base='/api/mobile/v1/analyses/1';revision=c.get(base+'/clinical').json()['revision']
    assert c.post(base+'/final-review',json={'revision':revision,'answers':{}}).status_code==422
    values={'revision':revision,'answers':{'answer_0':'Synthetic clinician answer'}}
    first=c.post(base+'/final-review',json=values);assert first.status_code==202,first.text
    assert c.post(base+'/final-review',json=values).json()['job']['id']==first.json()['job']['id']
    with Session(engine) as s:
        job=s.get(work_jobs.WorkJob,first.json()['job']['id']);assert job.kind=='FINAL' and json.loads(job.payload_json)==values['answers'];job.status='DONE';s.add(job);s.commit()
    path.write_text(json.dumps({'ai_result':{**RESULT,'status':'FINAL','questions':[]}}))
    assert c.post(base+'/final-review',json=values).json()['job']['id']==first.json()['job']['id']
    with Session(engine) as s:assert len(s.exec(select(work_jobs.WorkJob)).all())==1
    c.headers['Authorization']='Bearer token2';assert c.post(base+'/final-review',json=values).status_code==404


def test_stale_inputs_cannot_start_final_work(chat,monkeypatch,tmp_path):
    c,engine,_=setup(chat,monkeypatch,tmp_path);base='/api/mobile/v1/analyses/1';revision=c.get(base+'/clinical').json()['revision']
    with Session(engine) as s:p=s.get(main.Patient,1);p.chief_complaint='Changed synthetic complaint';s.add(p);s.commit()
    assert c.post(base+'/final-review',json={'revision':revision,'answers':{'answer_0':'Synthetic'}}).status_code==409
    with Session(engine) as s:assert not s.exec(select(work_jobs.WorkJob)).all()


def test_notes_fdi_and_job_controls_are_owned(chat,monkeypatch,tmp_path):
    c,engine,_=setup(chat,monkeypatch,tmp_path);base='/api/mobile/v1/analyses/1'
    assert c.post(base+'/clinical-note',json={'tooth':'59','note':'Synthetic'}).status_code==422
    r=c.post(base+'/clinical-note',json={'tooth':'36','note':'Synthetic clinician note','finding':'Synthetic manual finding'});assert r.status_code==200,r.text
    with Session(engine) as s:assert 'Synthetic manual finding' in s.get(main.Analysis,1).clinical_notes
    assert c.post(base+'/selected-teeth',json={'teeth':['59']}).status_code==422
    r=c.post(base+'/selected-teeth',json={'teeth':['36','46']});assert r.status_code==202,r.text
    job_id=r.json()['job']['id'];assert c.post(base+f'/jobs/{job_id}/cancel').status_code==200
    c.headers['Authorization']='Bearer token2';assert c.post(base+f'/jobs/{job_id}/retry').status_code==404


def test_legacy_result_and_vision_failure_are_visible_without_new_inference(chat,monkeypatch,tmp_path):
    c,engine,path=setup(chat,monkeypatch,tmp_path)
    monkeypatch.setattr(main,'_result_reference',lambda a,guest=False:path)
    with Session(engine) as s:
        a=s.get(main.Analysis,1);a.result_path=None;s.add(a)
        s.add(work_jobs.WorkJob(id=41,owner_user_id=1,resource_id=1,resource_type='ANALYSIS',kind='VISION',source_hash='synthetic',dedupe_key='synthetic-vision',status='FAILED',error_code='PRIVATE_PROVIDER_ERROR'));s.commit()
    r=c.get('/api/mobile/v1/analyses/1/clinical');assert r.status_code==200,r.text
    assert r.json()['result']['findings']==RESULT['findings']
    assert r.json()['job']=={'id':41,'kind':'VISION','status':'FAILED','retryable':True}
    assert 'PRIVATE_PROVIDER_ERROR' not in r.text
    with Session(engine) as s:assert len(s.exec(select(work_jobs.WorkJob)).all())==1


def test_corrupt_saved_result_is_an_error_not_empty_success(chat,monkeypatch,tmp_path):
    c,engine,path=setup(chat,monkeypatch,tmp_path);path.write_text('not-json')
    response=c.get('/api/mobile/v1/analyses/1/clinical');assert response.status_code==502
    assert 'not-json' not in response.text
    with Session(engine) as s:assert not s.exec(select(work_jobs.WorkJob)).all()
