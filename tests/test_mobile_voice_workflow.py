from test_mobile_chat_actions import chat
from app import main,mobile_api,voice_exam
from sqlmodel import Session,select
from app.work_jobs import WorkJob
import io,wave


def setup(chat,monkeypatch):
    client,engine=chat;monkeypatch.setattr(voice_exam.core,'enabled',lambda:True)
    with Session(engine) as s:
        s.add(main.Patient(id=8,anonymous_id='SYNTHETIC-8',owner_user_id=1,first_name='Synthetic'))
        s.add(main.Patient(id=9,anonymous_id='SYNTHETIC-9',owner_user_id=2));s.commit()
    return client,engine


def test_native_voice_apply_requires_consent_revision_and_owner_then_is_idempotent(chat,monkeypatch):
    client,engine=setup(chat,monkeypatch)
    revision=mobile_api._mobile_voice_patient(client_user(engine,1),8)
    values={'request_key':'a'*32,'revision':revision,'confirmed':False,'fields':{'chief_complaint':'Synthetic approved complaint'},'teeth':[{'tooth':'36','status':'CARIES','note':'Clinician approved'}]}
    path='/api/mobile/v1/patients/8/voice-exam/apply'
    assert client.post(path,json=values).status_code==400
    result=client.post(path,json={**values,'confirmed':True});assert result.status_code==200,result.text
    assert result.json()['analysis_id']
    repeated=client.post(path,json={**values,'confirmed':True});assert repeated.status_code==200 and repeated.json()['already_saved']
    with Session(engine) as s:
        assert s.get(main.Patient,8).chief_complaint=='Synthetic approved complaint'
        assert s.exec(select(main.ToothStatus).where(main.ToothStatus.patient_id==8)).one().tooth_number=='36'
        assert len(s.exec(select(WorkJob).where(WorkJob.kind=='VOICE_REVIEW')).all())==1
    client.headers['Authorization']='Bearer token2'
    assert client.post(path,json={**values,'confirmed':True}).status_code==404


def client_user(engine,ident):
    with Session(engine) as s:return s.get(main.User,ident)


def test_native_voice_apply_keeps_web_conflict_and_fdi_guards(chat,monkeypatch):
    client,engine=setup(chat,monkeypatch)
    revision=mobile_api._mobile_voice_patient(client_user(engine,1),8)
    with Session(engine) as s:
        patient=s.get(main.Patient,8);patient.chief_complaint='Changed elsewhere';s.add(patient);s.commit()
    values={'request_key':'b'*32,'revision':revision,'confirmed':True,'fields':{'chief_complaint':'Old draft'}}
    path='/api/mobile/v1/patients/8/voice-exam/apply'
    assert client.post(path,json=values).status_code==409
    assert client.post(path,json={**values,'teeth':[{'tooth':'99','status':'CARIES'}]}).status_code==422
    with Session(engine) as s:assert s.get(main.Patient,8).chief_complaint=='Changed elsewhere'


def test_live_audio_only_transcribes_and_never_writes_patient_or_runs_clinical_inference(chat,monkeypatch):
    client,engine=setup(chat,monkeypatch);calls=[]
    def transcribe(**kwargs):calls.append(kwargs);return {'transcript':'Synthetic dictated speech'}
    monkeypatch.setattr(voice_exam.core,'extract',transcribe)
    raw=io.BytesIO()
    with wave.open(raw,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*800)
    result=client.post('/api/mobile/v1/patients/8/voice-exam/audio',content=raw.getvalue(),headers={'Content-Type':'audio/wav','X-Voice-Consent':'yes'})
    assert result.status_code==200,result.text
    assert result.json()['transcript']=='Synthetic dictated speech' and calls[0]['transcription_only'] is True
    assert client.post('/api/mobile/v1/patients/9/voice-exam/audio',content=raw.getvalue(),headers={'Content-Type':'audio/wav','X-Voice-Consent':'yes'}).status_code==404
    assert len(calls)==1
    with Session(engine) as s:assert not s.exec(select(main.Analysis)).all() and s.get(main.Patient,8).chief_complaint is None


def test_approved_voice_appointment_uses_web_atomic_schedule_and_conflict_rules(chat,monkeypatch):
    client,engine=setup(chat,monkeypatch)
    revision=mobile_api._mobile_voice_patient(client_user(engine,1),8)
    values={'request_key':'c'*32,'revision':revision,'confirmed':True,'fields':{},'teeth':[],'appointment':{'title':'Synthetic approved appointment','start_at':'2030-01-08T09:00','end_at':'2030-01-08T09:30'}}
    path='/api/mobile/v1/patients/8/voice-exam/apply'
    result=client.post(path,json=values);assert result.status_code==200,result.text
    assert client.post(path,json=values).json()['already_saved']
    with Session(engine) as s:
        records=s.exec(select(main.ScheduleEvent).where(main.ScheduleEvent.owner_user_id==1)).all();assert len(records)==1 and records[0].patient_id==8
    changed={**values,'request_key':'d'*32,'revision':mobile_api._mobile_voice_patient(client_user(engine,1),8)}
    assert client.post(path,json=changed).status_code==409
