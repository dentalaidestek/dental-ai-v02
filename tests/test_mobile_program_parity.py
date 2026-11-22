import base64
from test_mobile_chat_actions import chat, _SESSION_TOKEN
from app import main,mobile_api
from sqlmodel import Session,select
from sqlalchemy import event as sqlalchemy_event
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
    original_revision=created.json()['event']['revision']
    assert len(original_revision)==64
    invalid=client.put(f'/api/mobile/v1/program/events/{ident}',json={**values,'patient_id':9,'expected_revision':original_revision})
    assert invalid.status_code==400
    edited=client.put(f'/api/mobile/v1/program/events/{ident}',json={**values,'start_at':'2030-01-07T11:00','end_at':'2030-01-07T11:30','reminder_minutes':'NONE','expected_revision':original_revision})
    assert edited.status_code==200,edited.text
    assert edited.json()['event']['start_local']=='2030-01-07T11:00'
    assert edited.json()['event']['reminder_minutes']=='NONE'
    latest_revision=edited.json()['event']['revision']
    assert latest_revision!=original_revision
    stale=client.put(f'/api/mobile/v1/program/events/{ident}',json={**values,'title':'Stale overwrite','expected_revision':original_revision})
    assert stale.status_code==409
    current=client.get(f'/api/mobile/v1/program/events/{ident}').json()['event']
    assert current['title']=='Synthetic visit' and current['revision']==latest_revision
    missing=client.put(f'/api/mobile/v1/program/events/{ident}',json=values)
    assert missing.status_code==422
    copied=client.post(f'/api/mobile/v1/program/events/{ident}/copy',json={'days':['2030-01-08','2030-01-09']})
    assert copied.status_code==200,copied.text
    assert client.post(f'/api/mobile/v1/program/events/{ident}/copy',json={'days':['2030-01-08','2030-01-09']}).status_code==200
    with Session(engine) as s:
        rows=s.exec(select(main.ScheduleEvent).where(main.ScheduleEvent.owner_user_id==1)).all()
        assert len(rows)==3
        copied_rows=[row for row in rows if row.id!=ident]
        assert len(copied_rows)==2
        assert all(len(row.client_request_hash or "")==64 for row in copied_rows)
        assert len({row.client_request_hash for row in copied_rows})==2
        assert all(len(row.client_payload_hash or "")==64 for row in copied_rows)
    assert client.post(f'/api/mobile/v1/program/events/{ident}/complete').status_code==200
    assert client.delete(f'/api/mobile/v1/program/events/{ident}').status_code==200
    deleted=client.get(f'/api/mobile/v1/program/events/{ident}')
    assert deleted.status_code==200 and deleted.json()['event']['status']=='DELETED'


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
    assert response.json()=={'advisory':True,'total':1}
    assert 'items' not in response.json() and 'title' not in response.json()
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
        _decode_program_cursor(cursor,'today',date(2030,1,7),2,main.APP_TIMEZONE,datetime.now(timezone.utc),_SESSION_TOKEN[1])
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



def test_month_calendar_exposes_the_same_first_three_event_markers_as_web(program):
    client,engine=program
    old=datetime(2020,1,1,0,0)
    types=['CLASS','CLINIC','EXAM','APPOINTMENT','TASK']
    with Session(engine) as s:
        for index,event_type in enumerate(types):
            s.add(main.ScheduleEvent(
                id=1000+index,owner_user_id=1,event_type=event_type,
                title='Synthetic month marker',start_at=datetime(2030,1,7,7,index*10),
                created_at=old,updated_at=old,
            ))
        s.commit()
    response=client.get('/api/mobile/v1/program?view=month&day=2030-01-07')
    assert response.status_code==200,response.text
    day=next(item for item in response.json()['days'] if item['date']=='2030-01-07')
    assert day['count']==5
    assert day['event_types']==types[:3]
    assert day['has_more'] is True

def test_program_copy_deduplicates_by_patient_and_event_identity(program):
    client,engine=program
    values={'event_type':'APPOINTMENT','title':'Synthetic shared title','start_at':'2030-01-07T10:00',
            'end_at':'2030-01-07T10:30','patient_id':8,'location':'Clinic','notes':'Synthetic note',
            'reminder_minutes':'30','recurrence_rule':'NONE','request_key':'program-copy-source-000001'}
    created=client.post('/api/mobile/v1/program/events',json=values)
    assert created.status_code==200,created.text
    ident=created.json()['event']['id']
    target_start=datetime(2030,1,8,7,0)
    target_end=datetime(2030,1,8,7,30)
    with Session(engine) as s:
        # Same title and time are not enough to suppress a different event.
        s.add(main.ScheduleEvent(owner_user_id=1,event_type='CLASS',title=values['title'],
            start_at=target_start,end_at=target_end,location='Classroom',notes=''))
        s.add(main.ScheduleEvent(owner_user_id=1,event_type='APPOINTMENT',title=values['title'],
            start_at=target_start,end_at=target_end,patient_id=None,location='Clinic',notes='Synthetic note',
            reminder_minutes=30,notification_enabled=True))
        s.commit()
    copied=client.post(f'/api/mobile/v1/program/events/{ident}/copy',json={'days':['2030-01-08']})
    assert copied.status_code==200,copied.text
    repeated=client.post(f'/api/mobile/v1/program/events/{ident}/copy',json={'days':['2030-01-08']})
    assert repeated.status_code==200,repeated.text
    with Session(engine) as s:
        rows=s.exec(select(main.ScheduleEvent).where(
            main.ScheduleEvent.owner_user_id==1,
            main.ScheduleEvent.start_at==target_start,
            main.ScheduleEvent.title==values['title'],
            main.ScheduleEvent.status!='DELETED',
        )).all()
        assert len(rows)==3
        assert len([row for row in rows if row.event_type=='APPOINTMENT' and row.patient_id==8])==1
        assert len([row for row in rows if row.event_type=='CLASS'])==1
        assert len([row for row in rows if row.event_type=='APPOINTMENT' and row.patient_id is None])==1


def test_deleted_program_event_state_remains_owner_scoped(program):
    client,engine=program
    values={'event_type':'TASK','title':'Synthetic deleted event','start_at':'2030-01-07T10:00',
            'end_at':'','reminder_minutes':'NONE','recurrence_rule':'NONE','request_key':'program-delete-state-0001'}
    created=client.post('/api/mobile/v1/program/events',json=values)
    assert created.status_code==200,created.text
    own_id=created.json()['event']['id']
    with Session(engine) as s:
        s.add(main.ScheduleEvent(id=987,owner_user_id=2,event_type='TASK',title='Other account deleted',
            start_at=datetime(2030,1,7,7,0),status='DELETED'))
        s.commit()
    assert client.delete(f'/api/mobile/v1/program/events/{own_id}').status_code==200
    own=client.get(f'/api/mobile/v1/program/events/{own_id}')
    assert own.status_code==200 and own.json()['event']['status']=='DELETED'
    assert client.get('/api/mobile/v1/program/events/987').status_code==404



def test_program_shared_validator_enforces_web_form_length_limits(program):
    _,engine=program
    with Session(engine) as s:
        user=s.get(main.User,1)
        base=('APPOINTMENT','Synthetic valid title','2030-01-07T10:00','2030-01-07T10:30','8','','','NONE',None,'NONE','')
        values,error=main._validate_schedule_input(s,user,*base[:5],'x'*161,*base[6:])
        assert values is None and error=='Konum en fazla 160 karakter olabilir.'
        values,error=main._validate_schedule_input(s,user,*base[:6],'x'*2001,*base[7:])
        assert values is None and error=='Notlar en fazla 2000 karakter olabilir.'


def test_mobile_program_api_rejects_overlong_location_and_notes(program):
    client,_=program
    values={'event_type':'APPOINTMENT','title':'Synthetic appointment','start_at':'2030-01-07T10:00',
        'end_at':'2030-01-07T10:30','patient_id':8,'reminder_minutes':'NONE','recurrence_rule':'NONE',
        'request_key':'program-length-limit-000001'}
    location=client.post('/api/mobile/v1/program/events',json={**values,'location':'x'*161})
    notes=client.post('/api/mobile/v1/program/events',json={**values,'request_key':'program-length-limit-000002','notes':'x'*2001})
    assert location.status_code==422
    assert notes.status_code==422


def _assert_program_private_no_store(response):
    assert response.headers.get("cache-control") == "private, no-store"
    assert response.headers.get("pragma") == "no-cache"
    assert "authorization" in response.headers.get("vary", "").lower()


def test_mobile_program_routes_prevent_caching_of_account_scoped_calendar_data(program):
    client, _ = program
    values = {
        "event_type": "APPOINTMENT",
        "title": "Synthetic private calendar entry",
        "start_at": "2030-01-07T10:00",
        "end_at": "2030-01-07T10:30",
        "patient_id": 8,
        "reminder_minutes": "NONE",
        "recurrence_rule": "NONE",
        "request_key": "program-private-cache-000001",
    }

    calendar = client.get("/api/mobile/v1/program?view=week&day=2030-01-07")
    assert calendar.status_code == 200, calendar.text
    _assert_program_private_no_store(calendar)

    conflicts = client.post("/api/mobile/v1/program/conflicts", json=values)
    assert conflicts.status_code == 200, conflicts.text
    _assert_program_private_no_store(conflicts)

    created = client.post("/api/mobile/v1/program/events", json=values)
    assert created.status_code == 200, created.text
    _assert_program_private_no_store(created)
    event_id = created.json()["event"]["id"]
    revision = created.json()["event"]["revision"]

    detail = client.get(f"/api/mobile/v1/program/events/{event_id}")
    assert detail.status_code == 200, detail.text
    _assert_program_private_no_store(detail)

    receipt = client.get("/api/mobile/v1/program/mutations/program-private-cache-000001")
    assert receipt.status_code == 200, receipt.text
    _assert_program_private_no_store(receipt)

    edited = client.put(
        f"/api/mobile/v1/program/events/{event_id}",
        json={**values, "title": "Synthetic private calendar entry edited",
              "start_at": "2030-01-07T11:00", "end_at": "2030-01-07T11:30",
              "expected_revision": revision},
    )
    assert edited.status_code == 200, edited.text
    _assert_program_private_no_store(edited)

    copied = client.post(
        f"/api/mobile/v1/program/events/{event_id}/copy",
        json={"days": ["2030-01-08"]},
    )
    assert copied.status_code == 200, copied.text
    _assert_program_private_no_store(copied)

    completed = client.post(f"/api/mobile/v1/program/events/{event_id}/complete")
    assert completed.status_code == 200, completed.text
    _assert_program_private_no_store(completed)

    deleted = client.delete(f"/api/mobile/v1/program/events/{event_id}")
    assert deleted.status_code == 200, deleted.text
    _assert_program_private_no_store(deleted)


def test_program_conflict_advice_skips_patient_detail_hydration(program):
    client, engine = program
    with Session(engine) as session:
        session.add(main.ScheduleEvent(
            id=91,
            owner_user_id=1,
            event_type="APPOINTMENT",
            title="Synthetic patient-linked conflict",
            start_at=datetime(2030, 1, 7, 7, 10),
            end_at=datetime(2030, 1, 7, 7, 25),
            patient_id=8,
        ))
        session.commit()

    patient_selects = []

    def capture_sql(_connection, _cursor, statement, _parameters, _context, _executemany):
        normalized = " ".join(statement.lower().split())
        if " from patient " in normalized or " from patient\n" in normalized:
            patient_selects.append(normalized)

    sqlalchemy_event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        response = client.post(
            "/api/mobile/v1/program/conflicts",
            json={
                "event_type": "TASK",
                "title": "Synthetic conflict check",
                "start_at": "2030-01-07T10:00",
                "end_at": "2030-01-07T10:30",
                "reminder_minutes": "NONE",
                "recurrence_rule": "NONE",
            },
        )
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", capture_sql)

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert patient_selects == []



def test_program_cursor_endpoint_is_private_and_rejects_tampering(program):
    client, engine = program
    with Session(engine) as session:
        for ident in range(1600, 1651):
            session.add(main.ScheduleEvent(
                id=ident,
                owner_user_id=1,
                event_type="TASK",
                title="Synthetic cursor privacy item",
                start_at=datetime(2030, 1, 7, 7, 0),
                created_at=datetime(2020, 1, 1),
                updated_at=datetime(2020, 1, 1),
            ))
        session.commit()

    first = client.get("/api/mobile/v1/program?view=today&day=2030-01-07")
    assert first.status_code == 200, first.text
    assert first.headers.get("cache-control") == "private, no-store"
    assert "authorization" in first.headers.get("vary", "").lower()
    cursor = first.json()["next_cursor"]
    assert isinstance(cursor, str) and cursor

    packed = bytearray(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    packed[-1] ^= 1
    tampered = base64.urlsafe_b64encode(bytes(packed)).decode("ascii").rstrip("=")
    rejected = client.get(
        "/api/mobile/v1/program",
        params={"view": "today", "day": "2030-01-07", "cursor": tampered},
    )
    assert rejected.status_code == 422


def test_program_copy_receipt_rejects_changed_source_payload(program):
    client,engine=program
    values={'event_type':'APPOINTMENT','title':'Synthetic copy receipt','start_at':'2030-01-07T10:00','end_at':'2030-01-07T10:30','patient_id':8,'reminder_minutes':'NONE','recurrence_rule':'NONE','request_key':'program-copy-source-000001'}
    created=client.post('/api/mobile/v1/program/events',json=values)
    assert created.status_code==200,created.text
    ident=created.json()['event']['id']
    revision=created.json()['event']['revision']
    copied=client.post(f'/api/mobile/v1/program/events/{ident}/copy',json={'days':['2030-01-08']})
    assert copied.status_code==200,copied.text
    changed=client.put(f'/api/mobile/v1/program/events/{ident}',json={**values,'title':'Changed source title','expected_revision':revision})
    assert changed.status_code==200,changed.text
    replay=client.post(f'/api/mobile/v1/program/events/{ident}/copy',json={'days':['2030-01-08']})
    assert replay.status_code==409,replay.text
    with Session(engine) as session:
        rows=session.exec(select(main.ScheduleEvent).where(main.ScheduleEvent.owner_user_id==1)).all()
        assert len(rows)==2
        copies=[row for row in rows if row.id!=ident]
        assert len(copies)==1 and copies[0].title=='Synthetic copy receipt'



def test_web_program_edit_rejects_stale_revision_and_preserves_the_local_draft(program):
    client,engine=program
    values={'event_type':'APPOINTMENT','title':'Synthetic web visit','start_at':'2030-01-07T10:00','end_at':'2030-01-07T10:30','patient_id':8,'reminder_minutes':'30','recurrence_rule':'NONE','request_key':'program-web-revision-request-001'}
    created=client.post('/api/mobile/v1/program/events',json=values)
    assert created.status_code==200,created.text
    ident=created.json()['event']['id']
    original_revision=created.json()['event']['revision']

    edit_page=client.get(f'/program/{ident}/edit')
    assert edit_page.status_code==200
    assert edit_page.context['expected_revision']==original_revision
    assert edit_page.context['revision_conflict'] is False

    with Session(engine) as session:
        event=session.get(main.ScheduleEvent,ident)
        event.title='Changed on another device'
        main._touch_schedule_event(event)
        session.add(event)
        session.commit()
        latest_revision=main._schedule_event_revision(event)

    draft={'event_type':'APPOINTMENT','title':'My unsaved local draft','start_at':'2030-01-07T10:00','end_at':'2030-01-07T10:30','patient_id':'8','location':'','notes':'Local-only note','reminder_minutes':'30','recurrence_rule':'NONE','recurrence_until':'','expected_revision':original_revision}
    stale=client.post(f'/program/{ident}/edit',data=draft)
    assert stale.status_code==409
    assert stale.context['revision_conflict'] is True
    assert stale.context['expected_revision']==original_revision
    assert stale.context['initial_title']=='My unsaved local draft'
    assert stale.context['initial_notes']=='Local-only note'

    with Session(engine) as session:
        event=session.get(main.ScheduleEvent,ident)
        assert event.title=='Changed on another device'
        assert main._schedule_event_revision(event)==latest_revision

    current=client.post(f'/program/{ident}/edit',data={**draft,'expected_revision':latest_revision})
    assert current.status_code==303
    with Session(engine) as session:
        event=session.get(main.ScheduleEvent,ident)
        assert event.title=='My unsaved local draft'
        assert event.notes=='Local-only note'


def test_program_revision_advances_after_complete_and_delete(program):
    client,engine=program
    values={'event_type':'TASK','title':'Synthetic revision task','start_at':'2030-01-07T10:00','reminder_minutes':'NONE','recurrence_rule':'NONE','request_key':'program-revision-actions-001'}
    created=client.post('/api/mobile/v1/program/events',json=values)
    assert created.status_code==200,created.text
    ident=created.json()['event']['id']
    first=created.json()['event']['revision']
    assert client.post(f'/api/mobile/v1/program/events/{ident}/complete').status_code==200
    completed=client.get(f'/api/mobile/v1/program/events/{ident}').json()['event']['revision']
    assert completed!=first
    assert client.delete(f'/api/mobile/v1/program/events/{ident}').status_code==200
    deleted=client.get(f'/api/mobile/v1/program/events/{ident}').json()['event']['revision']
    assert deleted!=completed


def test_web_program_edit_form_posts_revision_and_disables_stale_drafts():
    from pathlib import Path

    template=(Path(__file__).resolve().parents[1]/'app/templates/program_form.html').read_text(encoding='utf-8')
    assert 'name="expected_revision"' in template
    assert 'value="{{ expected_revision or \'\' }}"' in template
    assert '{% if revision_conflict %}disabled aria-disabled="true"{% endif %}' in template
    assert 'Güncel kaydı yeniden yükleyin' in template


def test_legacy_mobile_schedule_actions_advance_the_shared_program_revision(program):
    client,_=program
    values={'event_type':'TASK','title':'Synthetic legacy completion','start_at':'2030-01-07T10:00','reminder_minutes':'NONE','recurrence_rule':'NONE','request_key':'program-legacy-complete-001'}
    created=client.post('/api/mobile/v1/program/events',json=values)
    assert created.status_code==200,created.text
    ident=created.json()['event']['id']
    original=created.json()['event']['revision']
    assert client.post(f'/api/mobile/v1/schedule/{ident}/complete').status_code==200
    completed=client.get(f'/api/mobile/v1/program/events/{ident}').json()['event']
    assert completed['status']=='COMPLETED' and completed['revision']!=original

    deleted_values={**values,'title':'Synthetic legacy deletion','request_key':'program-legacy-delete-001'}
    deleted_create=client.post('/api/mobile/v1/program/events',json=deleted_values)
    assert deleted_create.status_code==200,deleted_create.text
    deleted_id=deleted_create.json()['event']['id']
    before_delete=deleted_create.json()['event']['revision']
    assert client.delete(f'/api/mobile/v1/schedule/{deleted_id}').status_code==200
    deleted=client.get(f'/api/mobile/v1/program/events/{deleted_id}').json()['event']
    assert deleted['status']=='DELETED' and deleted['revision']!=before_delete

def test_program_complete_and_delete_reject_other_account_before_web_dispatch(program, monkeypatch):
    client, engine = program
    from app import mobile_program_api

    values = {
        "event_type": "APPOINTMENT",
        "title": "Synthetic owner-isolation visit",
        "start_at": "2030-01-07T10:00",
        "end_at": "2030-01-07T10:30",
        "patient_id": 8,
        "reminder_minutes": "NONE",
        "recurrence_rule": "NONE",
        "request_key": "program-owner-action-000001",
    }
    created = client.post("/api/mobile/v1/program/events", json=values)
    assert created.status_code == 200, created.text
    event_id = created.json()["event"]["id"]
    original_revision = created.json()["event"]["revision"]

    async def unexpected_web_dispatch(*args, **kwargs):
        raise AssertionError("non-owner request reached the web mutation handler")

    monkeypatch.setattr(mobile_program_api, "_invoke", unexpected_web_dispatch)
    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]

    complete = client.post(f"/api/mobile/v1/program/events/{event_id}/complete")
    delete = client.delete(f"/api/mobile/v1/program/events/{event_id}")
    assert complete.status_code == 404
    assert delete.status_code == 404

    with Session(engine) as session:
        stored = session.get(main.ScheduleEvent, event_id)
        assert stored is not None
        assert stored.owner_user_id == 1
        assert stored.status == "ACTIVE"
        assert main._schedule_event_revision(stored) == original_revision

def test_repeated_program_completion_does_not_advance_revision_or_duplicate_reminders(program):
    client, engine = program
    values = {
        "event_type": "APPOINTMENT",
        "title": "Synthetic idempotent completion",
        "start_at": "2030-01-07T10:00",
        "end_at": "2030-01-07T10:30",
        "patient_id": 8,
        "reminder_minutes": "30",
        "recurrence_rule": "NONE",
        "request_key": "program-complete-idempotent-0001",
    }
    created = client.post("/api/mobile/v1/program/events", json=values)
    assert created.status_code == 200, created.text
    event_id = created.json()["event"]["id"]

    first = client.post(f"/api/mobile/v1/program/events/{event_id}/complete")
    assert first.status_code == 200, first.text
    with Session(engine) as session:
        completed = session.get(main.ScheduleEvent, event_id)
        first_revision = main._schedule_event_revision(completed)
        first_updated_at = completed.updated_at
        jobs = session.exec(
            select(main.ProgramReminderJob).where(
                main.ProgramReminderJob.schedule_event_id == event_id
            )
        ).all()
        assert completed.status == "COMPLETED"
        assert len(jobs) == 1
        assert jobs[0].status != "PENDING"

    second = client.post(f"/api/mobile/v1/program/events/{event_id}/complete")
    assert second.status_code == 200, second.text
    with Session(engine) as session:
        completed = session.get(main.ScheduleEvent, event_id)
        second_revision = main._schedule_event_revision(completed)
        second_updated_at = completed.updated_at
        jobs = session.exec(
            select(main.ProgramReminderJob).where(
                main.ProgramReminderJob.schedule_event_id == event_id
            )
        ).all()
        assert completed.status == "COMPLETED"
        assert second_revision == first_revision
        assert second_updated_at == first_updated_at
        assert len(jobs) == 1
