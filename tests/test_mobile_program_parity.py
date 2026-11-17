from test_mobile_chat_actions import chat
from app import main,mobile_api
from sqlmodel import Session,select
from datetime import date,datetime,timedelta,timezone
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
    values={'event_type':'APPOINTMENT','title':'Synthetic visit','start_at':'2030-01-07T10:00','end_at':'2030-01-07T10:30','patient_id':8,'reminder_minutes':'30','recurrence_rule':'NONE','request_key':'program-create-request-000001'}
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


def test_program_create_receipt_replays_exact_event_and_rejects_changed_payload(program):
    client,engine=program
    key='program-create-receipt-000001'
    values={'event_type':'APPOINTMENT','title':'Synthetic receipt visit','start_at':'2030-01-07T10:00','end_at':'2030-01-07T10:30','patient_id':8,'reminder_minutes':'30','recurrence_rule':'NONE','request_key':key}
    first=client.post('/api/mobile/v1/program/events',json=values)
    assert first.status_code==200,first.text
    second=client.post('/api/mobile/v1/program/events',json=values)
    assert second.status_code==200,second.text
    assert second.json()['event']['id']==first.json()['event']['id']
    assert client.get(f'/api/mobile/v1/program/mutations/{key}').json()['state']=='FOUND'
    changed=client.post('/api/mobile/v1/program/events',json={**values,'title':'Different appointment'})
    assert changed.status_code==409
    with Session(engine) as s:
        rows=s.exec(select(main.ScheduleEvent).where(main.ScheduleEvent.owner_user_id==1,main.ScheduleEvent.client_request_hash!=None)).all()
        assert len(rows)==1
        assert len(rows[0].client_request_hash)==64 and rows[0].client_request_hash!=key
        assert len(rows[0].client_payload_hash)==64 and values['title'] not in rows[0].client_payload_hash
        jobs=s.exec(select(main.ProgramReminderJob).where(main.ProgramReminderJob.schedule_event_id==rows[0].id)).all()
        assert len(jobs)==1 and jobs[0].status=='PENDING'


def test_program_receipts_are_owner_scoped_and_soft_deleted_keys_do_not_recreate(program):
    client,engine=program
    from app.mobile_api import _program_request_hash
    key='program-owner-scope-request-0001'
    other_hash=_program_request_hash(2,key)
    with Session(engine) as s:
        s.add(main.ScheduleEvent(owner_user_id=2,event_type='PERSONAL',title='Private other event',
            start_at=datetime(2030,1,7,7,0),client_request_hash=other_hash,client_payload_hash='a'*64))
        s.commit()
    assert client.get(f'/api/mobile/v1/program/mutations/{key}').json()=={'state':'NOT_FOUND'}
    values={'event_type':'APPOINTMENT','title':'Synthetic deletable visit','start_at':'2030-01-07T10:00','end_at':'2030-01-07T10:30','patient_id':8,'reminder_minutes':'NONE','recurrence_rule':'NONE','request_key':key}
    created=client.post('/api/mobile/v1/program/events',json=values)
    assert created.status_code==200,created.text
    ident=created.json()['event']['id']
    assert client.delete(f'/api/mobile/v1/program/events/{ident}').status_code==200
    assert client.get(f'/api/mobile/v1/program/mutations/{key}').json()=={'state':'DELETED','event_id':ident}
    assert client.post('/api/mobile/v1/program/events',json=values).status_code==410


def test_program_create_requires_a_valid_request_key(program):
    client,_=program
    values={'event_type':'APPOINTMENT','title':'Synthetic visit','start_at':'2030-01-07T10:00','end_at':'2030-01-07T10:30','patient_id':8,'reminder_minutes':'NONE','recurrence_rule':'NONE'}
    assert client.post('/api/mobile/v1/program/events',json=values).status_code==422
    assert client.post('/api/mobile/v1/program/events',json={**values,'request_key':'short'}).status_code==422


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



def test_program_cursor_pages_are_stable_for_equal_start_times(program):
    client,engine=program
    with Session(engine) as s:
        old=datetime(2020,1,1,0,0)
        for ident in range(400,520):
            s.add(main.ScheduleEvent(
                id=ident,owner_user_id=1,event_type='TASK',title='Synthetic cursor item',
                start_at=datetime(2030,1,7,7,0),created_at=old,updated_at=old,
            ))
        s.commit()

    ids=[]
    cursor=None
    while True:
        params={'view':'today','day':'2030-01-07'}
        if cursor:params['cursor']=cursor
        response=client.get('/api/mobile/v1/program',params=params)
        assert response.status_code==200,response.text
        data=response.json()
        assert data['total']==120
        assert len(data['items'])<=50
        ids.extend(item['event_id'] for item in data['items'])
        cursor=data['next_cursor']
        if cursor is None:break
    assert ids==list(range(400,520))
    assert len(ids)==len(set(ids))


def test_program_cursor_rejects_scope_changes_and_invalidates_mutated_snapshots(program):
    client,engine=program
    old=datetime(2020,1,1,0,0)
    with Session(engine) as s:
        for ident in range(700,780):
            s.add(main.ScheduleEvent(
                id=ident,owner_user_id=1,event_type='TASK',title='Synthetic snapshot item',
                start_at=datetime(2030,1,7,7,0),created_at=old,updated_at=old,
            ))
        s.commit()

    first=client.get('/api/mobile/v1/program?view=today&day=2030-01-07')
    assert first.status_code==200,first.text
    cursor=first.json()['next_cursor']
    assert isinstance(cursor,str) and len(cursor)>=16
    from app.mobile_program_api import _decode_program_cursor
    try:
        _decode_program_cursor(cursor,'today',date(2030,1,7),2,main.APP_TIMEZONE,datetime.now(timezone.utc))
        assert False,'another account must not reuse this cursor'
    except Exception as exc:
        assert getattr(exc,'status_code',None)==422
    assert client.get('/api/mobile/v1/program',params={'view':'month','day':'2030-01-07','cursor':cursor}).status_code==422
    assert client.get('/api/mobile/v1/program',params={'view':'today','day':'2030-01-07','cursor':'not-a-valid-cursor-token'}).status_code==422

    future=datetime.utcnow()+timedelta(minutes=1)
    with Session(engine) as s:
        s.add(main.ScheduleEvent(
            id=900,owner_user_id=1,event_type='TASK',title='Synthetic later insert',
            start_at=datetime(2030,1,7,7,0),created_at=future,updated_at=future,
        ))
        s.commit()
    stale=client.get('/api/mobile/v1/program',params={'view':'today','day':'2030-01-07','cursor':cursor})
    assert stale.status_code==409

    # Move the synthetic insert behind the new watermark so the next assertion
    # isolates an update to an existing event rather than the earlier insert.
    with Session(engine) as s:
        later=s.get(main.ScheduleEvent,900)
        later.created_at=old
        later.updated_at=old
        s.add(later)
        s.commit()
    refreshed=client.get('/api/mobile/v1/program?view=today&day=2030-01-07')
    assert refreshed.status_code==200,refreshed.text
    refreshed_cursor=refreshed.json()['next_cursor']
    with Session(engine) as s:
        changed=s.get(main.ScheduleEvent,750)
        changed.updated_at=datetime.utcnow()+timedelta(minutes=2)
        s.add(changed)
        s.commit()
    stale_edit=client.get('/api/mobile/v1/program',params={'view':'today','day':'2030-01-07','cursor':refreshed_cursor})
    assert stale_edit.status_code==409
