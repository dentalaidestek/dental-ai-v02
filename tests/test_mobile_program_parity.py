from test_mobile_chat_actions import chat
from app import main,mobile_api
from sqlmodel import Session,select
from datetime import datetime
from starlette.responses import Response
import pytest

@pytest.fixture
def program(chat,monkeypatch):
    client,engine=chat
    def render(*args,**kwargs):
        result=Response('',status_code=kwargs.get('status_code',200));result.context=kwargs.get('context') or {};return result
    monkeypatch.setattr(main.templates,'TemplateResponse',render)
    with Session(engine) as s:
        s.add(main.Patient(id=8,owner_user_id=1,anonymous_id='SYNTHETIC-8',first_name='Synthetic'))
        s.add(main.Patient(id=9,owner_user_id=2,anonymous_id='SYNTHETIC-9'))
        s.commit()
    return client,engine

def test_mobile_creation_enqueues_same_reminder_as_web_and_can_disable_it(program):
    client,engine=program
    values={'event_type':'APPOINTMENT','title':'Synthetic appointment','start_at':'2030-01-07T10:00','end_at':'2030-01-07T10:30','patient_id':8,'reminder_minutes':30}
    result=client.post('/api/mobile/v1/schedule',json=values)
    assert result.status_code==200,result.text
    ident=result.json()['event']['id']
    with Session(engine) as s:
        assert s.get(main.ScheduleEvent,ident).start_at==datetime(2030,1,7,7,0)
        jobs=s.exec(select(main.ProgramReminderJob).where(main.ProgramReminderJob.schedule_event_id==ident)).all()
        assert len(jobs)==1 and jobs[0].status=='PENDING'
    disabled=client.post('/api/mobile/v1/schedule',json={**values,'title':'No reminder','notification_enabled':False})
    assert disabled.status_code==200
    with Session(engine) as s:
        disabled_id=disabled.json()['event']['id']
        assert s.get(main.ScheduleEvent,disabled_id).notification_enabled is False
        assert not s.exec(select(main.ProgramReminderJob).where(main.ProgramReminderJob.schedule_event_id==disabled_id)).all()

def test_range_expands_weekly_occurrences_and_does_not_leak_other_accounts(program):
    client,engine=program
    with Session(engine) as s:
        s.add(main.ScheduleEvent(id=11,owner_user_id=1,event_type='APPOINTMENT',title='Synthetic weekly',start_at=datetime(2026,1,5,7,0),end_at=datetime(2026,1,5,7,30),recurrence_rule='WEEKLY',recurrence_until='2030-01-14',patient_id=8))
        s.add(main.ScheduleEvent(id=12,owner_user_id=2,event_type='PERSONAL',title='Private other account',start_at=datetime(2030,1,7,7,0)))
        s.commit()
    response=client.get('/api/mobile/v1/program?view=week&day=2030-01-07')
    assert response.status_code==200,response.text
    data=response.json();assert data['timezone']=='Europe/Istanbul'
    assert len(data['days'])==7 and data['items'][0]['start_local']=='2030-01-07T10:00'
    assert [row['event_id'] for row in data['items']]==[11]
    assert client.get('/api/mobile/v1/program?view=today&day=2030-01-21').json()['items']==[]
    month=client.get('/api/mobile/v1/program?view=month&day=2030-01-07').json()
    assert len(month['days'])==42
    assert client.get('/api/mobile/v1/program/events/12').status_code==404

def test_program_edit_copy_complete_delete_reuse_web_lifecycle(program):
    client,engine=program
    values={'event_type':'APPOINTMENT','title':'Synthetic visit','start_at':'2030-01-07T10:00','end_at':'2030-01-07T10:30','patient_id':8,'reminder_minutes':'30','recurrence_rule':'NONE'}
    created=client.post('/api/mobile/v1/program/events',json=values)
    assert created.status_code==200,created.text
    ident=created.json()['event']['id']
    invalid=client.put(f'/api/mobile/v1/program/events/{ident}',json={**values,'patient_id':9})
    assert invalid.status_code==400
    edited=client.put(f'/api/mobile/v1/program/events/{ident}',json={**values,'start_at':'2030-01-07T11:00','end_at':'2030-01-07T11:30','reminder_minutes':'NONE'})
    assert edited.status_code==200,edited.text
    assert edited.json()['event']['start_local']=='2030-01-07T11:00'
    assert edited.json()['event']['reminder_minutes']=='NONE'
    copied=client.post(f'/api/mobile/v1/program/events/{ident}/copy',json={'days':['2030-01-08','2030-01-09']})
    assert copied.status_code==200,copied.text
    assert client.post(f'/api/mobile/v1/program/events/{ident}/copy',json={'days':['2030-01-08','2030-01-09']}).status_code==200
    with Session(engine) as s:assert len(s.exec(select(main.ScheduleEvent).where(main.ScheduleEvent.owner_user_id==1)).all())==3
    assert client.post(f'/api/mobile/v1/program/events/{ident}/complete').status_code==200
    assert client.delete(f'/api/mobile/v1/program/events/{ident}').status_code==200
    assert client.get(f'/api/mobile/v1/program/events/{ident}').status_code==404

def test_conflict_advice_is_owned_and_supports_recurring_records(program):
    client,engine=program
    with Session(engine) as s:
        s.add(main.ScheduleEvent(id=21,owner_user_id=1,event_type='APPOINTMENT',title='Synthetic overlap',start_at=datetime(2026,1,5,7,0),end_at=datetime(2026,1,5,7,30),recurrence_rule='WEEKLY'))
        s.add(main.ScheduleEvent(id=22,owner_user_id=2,event_type='PERSONAL',title='Private other',start_at=datetime(2030,1,7,7,0),end_at=datetime(2030,1,7,8,0)))
        s.commit()
    values={'event_type':'APPOINTMENT','title':'Synthetic new','start_at':'2030-01-07T10:15','end_at':'2030-01-07T10:45','patient_id':8,'reminder_minutes':'NONE'}
    response=client.post('/api/mobile/v1/program/conflicts',json=values)
    assert response.status_code==200,response.text
    assert response.json()['total']==1 and response.json()['items'][0]['id']==21
    assert client.post('/api/mobile/v1/program/conflicts?exclude_id=22',json=values).status_code==404
    assert client.post('/api/mobile/v1/program/conflicts?exclude_id=21',json=values).json()['total']==0

def test_calendar_pagination_is_not_truncated_by_old_first_hundred_records(program):
    client,engine=program
    with Session(engine) as s:
        for ident in range(1,122):s.add(main.ScheduleEvent(id=ident,owner_user_id=1,event_type='PERSONAL',title='Synthetic old',start_at=datetime(2020,1,1,7,0)))
        for ident in range(200,351):s.add(main.ScheduleEvent(id=ident,owner_user_id=1,event_type='TASK',title='Synthetic current',start_at=datetime(2030,1,7,7,0)))
        s.commit()
    ids=[];offset=0
    while True:
        response=client.get(f'/api/mobile/v1/program?view=today&day=2030-01-07&offset={offset}')
        assert response.status_code==200,response.text
        data=response.json();assert data['total']==151
        assert len(data['items'])<=50
        ids.extend(item['event_id'] for item in data['items'])
        if data['next_offset'] is None:break
        assert data['next_offset']>offset
        offset=data['next_offset']
    assert ids==list(range(200,351))
