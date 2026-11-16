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


def test_native_anonymous_voice_patient_is_private_owned_and_idempotent(chat,monkeypatch):
    client,engine=setup(chat,monkeypatch)
    published=[]
    monkeypatch.setattr(main,'on_loop',lambda callback,*args:published.append((callback,args)))
    path='/api/mobile/v1/voice-exam/anonymous'
    key='e'*32
    first=client.post(path,json={'request_key':key})
    assert first.status_code==201,first.text
    assert first.headers['cache-control']=='private, no-store'
    assert first.headers['vary']=='Authorization'
    payload=first.json()
    assert payload['ok'] is True and payload['already_created'] is False
    assert payload['patient']['anonymous_id'].startswith('SES-')
    assert payload['patient']['first_name'] is None and payload['patient']['last_name'] is None
    repeated=client.post(path,json={'request_key':key})
    assert repeated.status_code==200,repeated.text
    assert repeated.json()['patient']['id']==payload['patient']['id']
    assert repeated.json()['already_created'] is True
    assert len(published)==1
    with Session(engine) as session:
        patient=session.get(main.Patient,payload['patient']['id'])
        assert patient.owner_user_id==1
        assert patient.first_name is None and patient.phone is None
    client.headers['Authorization']='Bearer token2'
    other=client.post(path,json={'request_key':key})
    assert other.status_code==201,other.text
    assert other.json()['patient']['id']!=payload['patient']['id']
    with Session(engine) as session:
        assert session.get(main.Patient,other.json()['patient']['id']).owner_user_id==2
    assert client.post(path,json={'request_key':'not-a-valid-key'}).status_code==422


def test_native_voice_history_returns_only_owned_completed_voice_approvals(chat,monkeypatch):
    client,engine=setup(chat,monkeypatch)
    with Session(engine) as session:
        approved=main.Analysis(
            patient_id=8,
            status='DRAFT',
            clinical_notes='Sistemik hastalık / hasta beyanı: Astım\\n\\nİlaç / hasta beyanı: Düzenli sentetik ilaç\\n\\nAlerji / hasta beyanı: Penisilin beyanı',
        )
        session.add(approved);session.flush()
        session.add(WorkJob(
            owner_user_id=1,resource_id=approved.id,resource_type='ANALYSIS',
            kind='VOICE_REVIEW',status='DONE',source_hash='a'*64,
            dedupe_key='voice-review:1:history-approved',payload_json='{}',result_ref=str(approved.id),
        ))
        non_voice=main.Analysis(patient_id=8,status='DRAFT',clinical_notes='Sistemik hastalık / hasta beyanı: Must not leak')
        session.add(non_voice);session.flush()
        session.add(WorkJob(
            owner_user_id=1,resource_id=non_voice.id,resource_type='ANALYSIS',
            kind='IMAGE_ANALYSIS',status='DONE',source_hash='b'*64,
            dedupe_key='image-analysis:history-excluded',payload_json='{}',result_ref=str(non_voice.id),
        ))
        other_owner=main.Analysis(patient_id=8,status='DRAFT',clinical_notes='İlaç / hasta beyanı: Other owner secret')
        session.add(other_owner);session.flush()
        session.add(WorkJob(
            owner_user_id=2,resource_id=other_owner.id,resource_type='ANALYSIS',
            kind='VOICE_REVIEW',status='DONE',source_hash='c'*64,
            dedupe_key='voice-review:2:history-excluded',payload_json='{}',result_ref=str(other_owner.id),
        ))
        unfinished=main.Analysis(patient_id=8,status='DRAFT',clinical_notes='Alerji / hasta beyanı: Not completed')
        session.add(unfinished);session.flush()
        session.add(WorkJob(
            owner_user_id=1,resource_id=unfinished.id,resource_type='ANALYSIS',
            kind='VOICE_REVIEW',status='RUNNING',source_hash='d'*64,
            dedupe_key='voice-review:1:history-unfinished',payload_json='{}',result_ref=str(unfinished.id),
        ))
        session.commit()

    response=client.get('/api/mobile/v1/patients/8/voice-exam/history')
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='private, no-store'
    assert response.headers['vary']=='Authorization'
    body=response.json()
    assert body['ok'] is True
    assert len(body['revision'])==64
    assert set(body['fields'])=={'medical_history','medications','allergies'}
    assert body['fields']['medical_history']['value']=='Astım'
    assert body['fields']['medications']['analysis_id']==approved.id
    assert 'Must not leak' not in response.text
    assert 'Other owner secret' not in response.text
    assert 'Not completed' not in response.text
    assert 'transcript' not in body and 'audio' not in body

    client.headers['Authorization']='Bearer token2'
    assert client.get('/api/mobile/v1/patients/8/voice-exam/history').status_code==404
    client.headers['Authorization']='Bearer token1'
    assert client.get('/api/mobile/v1/patients/9/voice-exam/history').status_code==404
