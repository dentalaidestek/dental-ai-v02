from test_mobile_chat_actions import chat
from app import main
from sqlmodel import Session,select


def expert(engine):
    with Session(engine) as s:
        s.add(main.ExpertProfile(user_id=2,specialty='Endodonti',institution='Synthetic institution',bio='Synthetic biography',consultation_price=1200,application_status='APPROVED',verification_status='VERIFIED',specialty_verified=True,credential_document_path='PRIVATE-CREDENTIAL.pdf',phone='05551234567',availability='AVAILABLE'))
        s.commit()


def test_native_public_expert_profile_has_web_identity_performance_and_intake(chat):
    client,engine=chat;expert(engine)
    result=client.get('/api/mobile/v1/experts/2')
    assert result.status_code==200,result.text
    data=result.json();assert data['specialty']=='Endodonti' and data['institution']=='Synthetic institution' and data['support_available']
    assert data['consultation_price']==1200 and not data['owned'] and not data['can_publish']
    assert 'phone' not in data and 'PRIVATE-CREDENTIAL' not in str(data)
    client.headers['Authorization']='Bearer token2'
    own=client.get('/api/mobile/v1/experts/2').json();assert own['owned'] and own['can_publish'] and not own['support_available']


def test_native_public_profile_uses_web_verification_and_policy_gates(chat):
    client,engine=chat;expert(engine)
    with Session(engine) as s:
        s.add(main.ExpertPolicyState(expert_user_id=2,new_case_blocked_until=main._utcnow_naive()+main.timedelta(days=1)));s.commit()
    result=client.get('/api/mobile/v1/experts/2');assert result.status_code==200 and not result.json()['support_available']
    with Session(engine) as s:
        p=s.exec(select(main.ExpertProfile).where(main.ExpertProfile.user_id==2)).one();p.specialty_verified=False;s.add(p);s.commit()
    assert client.get('/api/mobile/v1/experts/2').status_code==404
    client.headers.pop('Authorization');assert client.get('/api/mobile/v1/experts/2').status_code==401


def test_blocked_or_inactive_experts_are_not_exposed_by_native_profile(chat):
    client,engine=chat;expert(engine)
    with Session(engine) as s:
        s.add(main.UserBlock(blocker_user_id=2,blocked_user_id=1));s.commit()
    assert client.get('/api/mobile/v1/experts/2').status_code==404
    client.headers['Authorization']='Bearer token3'
    assert client.get('/api/mobile/v1/experts/2').status_code==200
    with Session(engine) as s:
        owner=s.get(main.User,2);owner.is_active=False;s.add(owner);s.commit()
    assert client.get('/api/mobile/v1/experts/2').status_code==404


def test_native_bearer_publication_flow_keeps_duplicate_version_and_owner_guards(chat):
    client,engine=chat;expert(engine);client.headers['Authorization']='Bearer token2';client.headers['X-Dental-Social']='1'
    values={'title':'Synthetic clinical publication','authors':'Synthetic Author','year':2025,'journal':'Synthetic Journal','doi':'10.1000/native-test','url':'https://doi.org/10.1000/native-test','description':'Synthetic abstract'}
    result=client.post('/api/expert-social/publications',json=values);assert result.status_code==200,result.text
    paper=result.json();assert client.post('/api/expert-social/publications',json=values).status_code==409
    path='/api/expert-social/publications/'+str(paper['id'])
    assert client.put(path,json={**values,'version':paper['version']+1}).status_code==409
    updated=client.put(path,json={**values,'version':paper['version'],'description':'Updated abstract'});assert updated.status_code==200,updated.text
    client.headers['Authorization']='Bearer token1'
    assert client.delete(path).status_code==403
    visible=client.get('/api/expert-social/experts/2/publications');assert visible.status_code==200
    client.headers['Authorization']='Bearer token2'
    assert client.delete(path).status_code==200
    assert client.get('/api/expert-social/experts/2/publications').json()['items']==[]


def test_native_profile_stops_offering_new_consultation_at_web_capacity(chat):
    client,engine=chat;expert(engine)
    with Session(engine) as s:
        for ident in range(2,6):
            s.add(main.ConsultationCase(id=ident,requester_user_id=3,expert_user_id=2,specialty='Endodonti',clinical_summary='Synthetic',question='Synthetic',status='ACTIVE',expert_response_deadline=main._utcnow_naive()+main.timedelta(hours=1)))
        s.commit()
    result=client.get('/api/mobile/v1/experts/2')
    assert result.status_code==200,result.text
    assert result.json()['availability']=='AVAILABLE' and not result.json()['support_available']
