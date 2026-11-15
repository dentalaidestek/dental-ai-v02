from datetime import timedelta
from sqlmodel import Session
from test_mobile_chat_actions import chat
from app import main


def test_native_expert_performance_uses_owned_web_aggregates_and_policy(chat):
    client,engine=chat;now=main._utcnow_naive()
    with Session(engine) as s:
        s.add(main.ExpertProfile(user_id=1,specialty='Endodonti',availability='BUSY'))
        s.add(main.ExpertProfile(user_id=2,specialty='Ortodonti',availability='AVAILABLE'))
        s.add(main.ExpertPolicyState(expert_user_id=1,new_case_blocked_until=now+timedelta(hours=1),block_reason='Synthetic owner-only reason'))
        s.add(main.ConsultationCase(id=5,requester_user_id=2,expert_user_id=1,specialty='Endodonti',clinical_summary='Synthetic',question='Synthetic',status='COMPLETED',requested_at=now-timedelta(minutes=10),proposed_at=now-timedelta(minutes=5),expert_response_deadline=now+timedelta(hours=1)))
        s.add(main.ConsultationEvent(case_id=5,actor_user_id=1,event_type='MISSED_REQUEST_COUNTED',payload_json='{"private":"never serialize raw event data"}'))
        s.commit()
    response=client.get('/api/mobile/v1/account/expert-performance');assert response.status_code==200,response.text
    data=response.json();assert data['owner_id']==1 and data['performance']['completed_count']==1
    assert data['performance']['avg_response_minutes']==5
    assert data['policy']['blocked'] is True and data['policy']['reason']=='Synthetic owner-only reason'
    assert data['events'][0]['event_type']=='MISSED_REQUEST_COUNTED'
    assert 'payload_json' not in response.text and 'never serialize' not in response.text
    assert response.headers['cache-control']=='private, no-store'
    client.headers['Authorization']='Bearer token2';other=client.get('/api/mobile/v1/account/expert-performance').json()
    assert other['owner_id']==2 and other['performance']['completed_count']==0
    assert other['events']==[] and other['policy']['reason'] is None


def test_native_performance_requires_active_owned_profile(chat):
    c,engine=chat
    assert c.get('/api/mobile/v1/account/expert-performance').status_code==404
    c.headers.pop('Authorization');assert c.get('/api/mobile/v1/account/expert-performance').status_code==401
