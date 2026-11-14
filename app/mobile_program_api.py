"""Native calendar uses the web recurrence, patient and reminder rules."""
from datetime import date,datetime,timedelta
from typing import Optional
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlmodel import Session
from app.mobile_api import _mobile_user,_mobile_access_token,_mobile_request,MobileScheduleCreate,mobile_create_schedule
from app.mobile_account_api import _invoke

router=APIRouter(tags=['mobile-program'])

def _owned(session,web,user,ident):
    event=session.get(web.ScheduleEvent,ident)
    if not event or event.owner_user_id!=user.id or event.status=='DELETED':raise HTTPException(status_code=404,detail='Program kaydı bulunamadı.')
    return event

def _event(session,web,event,user):
    patient=web._owned_program_patient(session,user,event.patient_id) if event.patient_id else None
    return {'id':event.id,'event_type':event.event_type,'title':event.title,'start_local':web._utc_to_local(event.start_at).strftime('%Y-%m-%dT%H:%M'),'end_local':web._utc_to_local(event.end_at).strftime('%Y-%m-%dT%H:%M') if event.end_at else '',
        'patient_id':patient.id if patient else None,'patient_name':f'{patient.first_name or ""} {patient.last_name or ""}'.strip() if patient else None,
        'location':event.location or '', 'notes':event.notes or '', 'status':event.status,
        'reminder_minutes':str(event.reminder_minutes) if event.notification_enabled and event.reminder_minutes is not None else 'NONE',
        'recurrence_rule':event.recurrence_rule,'recurrence_until':event.recurrence_until or ''}

@router.get('/program')
def program_range(view:str=Query('week',pattern='^(today|week|month)$'),day:Optional[str]=None,offset:int=Query(0,ge=0),user=Depends(_mobile_user)):
    from app import main as web
    today=datetime.now(web.APP_TIMEZONE).date()
    try:focus=date.fromisoformat(day) if day else today
    except ValueError:raise HTTPException(status_code=422,detail='Geçerli bir takvim günü seçin.')
    _,start,end,previous,following=web._program_range(view,focus)
    if view=='month':
        first=focus.replace(day=1);grid_start=first-timedelta(days=first.weekday());start=web._date_to_local_start(grid_start);end=web._date_to_local_end(grid_start+timedelta(days=41))
    with Session(web.engine,expire_on_commit=False) as session:
        occurrences=web._user_schedule_occurrences(session,user.id,start,end)
    counts={}
    for item in occurrences:
        key=item['start_local'].date().isoformat();counts[key]=counts.get(key,0)+1
    if view=='month':days=[{'date':(grid_start+timedelta(days=i)).isoformat(),'label':str((grid_start+timedelta(days=i)).day),'in_month':(grid_start+timedelta(days=i)).month==focus.month,'count':counts.get((grid_start+timedelta(days=i)).isoformat(),0)} for i in range(42)]
    else:days=[{'date':item['date'].isoformat(),'label':item['label'],'in_month':True,'count':counts.get(item['date'].isoformat(),0)} for item in web._program_week_days(focus)] if view=='week' else [{'date':focus.isoformat(),'label':str(focus.day),'in_month':True,'count':counts.get(focus.isoformat(),0)}]
    selected=sorted([item for item in occurrences if view=='today' or item['start_local'].date()==focus],key=lambda item:(item['start_local'],item['id']))
    page=selected[offset:offset+50]
    now=datetime.now(web.APP_TIMEZONE).replace(second=0,microsecond=0)
    suggested=now.replace(minute=0 if now.minute<30 else 30)
    if suggested<now:suggested+=timedelta(minutes=30)
    suggested=datetime.combine(focus,suggested.time())
    return {'view':view,'focus_date':focus.isoformat(),'today':today.isoformat(),'timezone':'Europe/Istanbul','previous_day':previous.isoformat(),'next_day':following.isoformat(),'days':days,
        'items':[{'key':f"{item['id']}:{item['start_local'].isoformat()}",'event_id':item['id'],'event_type':item['event_type'],'title':item['title'],'status':item['status'],'start_local':item['start_local'].strftime('%Y-%m-%dT%H:%M'),'end_local':item['end_local'].strftime('%Y-%m-%dT%H:%M') if item['end_local'] else '',
            'patient_id':item['patient'].id if item.get('patient') else None,'patient_name':f"{item['patient'].first_name or ''} {item['patient'].last_name or ''}".strip() if item.get('patient') else None,
            'location':item['location'],'notes':item['notes'],'recurrence_rule':item['recurrence_rule']} for item in page],
        'total':len(selected),'next_offset':offset+len(page) if offset+len(page)<len(selected) else None,
        'copy_days':[{'date':item['date'].isoformat(),'label':item['label']} for item in web._program_week_days(focus)],'month_title':f'{web.PROGRAM_MONTH_NAMES[focus.month-1]} {focus.year}', 'event_types':web.PROGRAM_EVENT_TYPES,'reminders':['NONE',*[str(x) for x in sorted(web.REMINDER_OPTIONS)]],'recurrences':sorted(web.RECURRENCE_OPTIONS),
        'suggested_start_local':suggested.strftime('%Y-%m-%dT%H:%M'),'suggested_end_local':(suggested+timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M')}

@router.get('/program/events/{event_id}')
def program_event(event_id:int,user=Depends(_mobile_user)):
    from app import main as web
    with Session(web.engine,expire_on_commit=False) as session:return {'event':_event(session,web,_owned(session,web,user,event_id),user)}

class ProgramValues(BaseModel):
    event_type:str=Field(max_length=40)
    title:str=Field(max_length=160)
    start_at:str=Field(max_length=30)
    end_at:str=Field(default='',max_length=30)
    patient_id:Optional[int]=None
    location:str=Field(default='',max_length=1000)
    notes:str=Field(default='',max_length=2000)
    reminder_minutes:str='30'
    recurrence_rule:str='NONE'
    recurrence_until:str=''

@router.post('/program/conflicts')
def program_conflicts(payload:ProgramValues,exclude_id:Optional[int]=Query(None,ge=1),user=Depends(_mobile_user)):
    from app import main as web
    with Session(web.engine,expire_on_commit=False) as session:
        if exclude_id is not None:_owned(session,web,user,exclude_id)
        values,error=web._validate_schedule_input(session,user,payload.event_type,payload.title,payload.start_at,payload.end_at,str(payload.patient_id or ''),payload.location,payload.notes,payload.reminder_minutes,None,payload.recurrence_rule,payload.recurrence_until)
        if error:raise HTTPException(status_code=422,detail=error)
        start=web._utc_to_local(values['start_at']);end=web._utc_to_local(values['end_at']) if values['end_at'] else start+timedelta(minutes=1)
        if end==start:end=start+timedelta(minutes=1)
        occurrences=web._user_schedule_occurrences(session,user.id,web._date_to_local_start(start.date()),web._date_to_local_end(end.date()))
        conflicts=[item for item in occurrences if item['status']=='ACTIVE' and item['id']!=exclude_id and item['start_local']<end and (item['end_local'] or item['start_local']+timedelta(minutes=1))>start]
        return {'advisory':True,'total':len(conflicts),'items':[{'id':item['id'],'title':item['title'],'start_local':item['start_local'].strftime('%Y-%m-%dT%H:%M')} for item in conflicts[:10]]}

@router.post('/program/events')
def create_program_event(payload:ProgramValues,user=Depends(_mobile_user)):
    try:reminder=None if payload.reminder_minutes=='NONE' else int(payload.reminder_minutes)
    except ValueError:raise HTTPException(status_code=422,detail='Hatırlatma seçimini kontrol edin.')
    result=mobile_create_schedule(MobileScheduleCreate(**{**payload.model_dump(),'reminder_minutes':reminder,'notification_enabled':reminder is not None}),user)
    return program_event(result['event']['id'],user)

@router.put('/program/events/{event_id}')
async def edit_program_event(event_id:int,payload:ProgramValues,token:str=Depends(_mobile_access_token),user=Depends(_mobile_user)):
    from app import main as web
    with Session(web.engine) as session:_owned(session,web,user,event_id)
    await _invoke(web.program_edit,_mobile_request(token,path=f'/program/{event_id}/edit'),event_id,payload.event_type,payload.title,payload.start_at,payload.end_at,str(payload.patient_id or ''),payload.location,payload.notes,payload.reminder_minutes,'1' if payload.reminder_minutes!='NONE' else None,payload.recurrence_rule,payload.recurrence_until)
    return program_event(event_id,user)

class CopyDays(BaseModel):days:list[str]=Field(min_length=1,max_length=7)

@router.post('/program/events/{event_id}/copy')
async def copy_program_event(event_id:int,payload:CopyDays,token:str=Depends(_mobile_access_token),user=Depends(_mobile_user)):
    from app import main as web
    with Session(web.engine) as session:_owned(session,web,user,event_id)
    await _invoke(web.program_copy_to_days,_mobile_request(token),event_id,','.join(payload.days))
    return {'ok':True}

@router.post('/program/events/{event_id}/complete')
async def complete_program_event(event_id:int,token:str=Depends(_mobile_access_token),user=Depends(_mobile_user)):
    from app import main as web
    await _invoke(web.program_complete,_mobile_request(token),event_id)
    return {'ok':True}

@router.delete('/program/events/{event_id}')
async def delete_program_event(event_id:int,token:str=Depends(_mobile_access_token),user=Depends(_mobile_user)):
    from app import main as web
    await _invoke(web.program_delete,_mobile_request(token),event_id)
    return {'ok':True}
