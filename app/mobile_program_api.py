"""Native calendar uses the web recurrence, patient and reminder rules."""
import base64
import hashlib
import json
import re
from datetime import date,datetime,timedelta,timezone
from typing import Optional
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlmodel import Session,select
from app.mobile_api import _mobile_user,_mobile_access_token,_mobile_request,MobileScheduleCreate,mobile_create_schedule,_program_request_hash
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

_PROGRAM_CURSOR_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,512}$")
_PROGRAM_CURSOR_TTL = timedelta(minutes=15)


def _program_cursor_owner(user_id: int) -> str:
    # Scope tag only; every page still queries the authenticated owner's rows.
    return hashlib.sha256(f"dental-ai:program-cursor:v1:{int(user_id)}".encode("ascii")).hexdigest()[:24]


def _program_local_start_utc(value: datetime, app_timezone) -> datetime:
    """Interpret naive occurrence datetimes as Istanbul wall time, never host local time."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=app_timezone)
    return value.astimezone(timezone.utc)


def _encode_program_cursor(view: str, focus: date, user_id: int, snapshot_at: datetime, item: dict, app_timezone) -> str:
    payload = {
        "v": 1,
        "view": view,
        "day": focus.isoformat(),
        "owner": _program_cursor_owner(user_id),
        "snapshot": snapshot_at.isoformat(timespec="microseconds"),
        "after": _program_local_start_utc(item["start_local"], app_timezone).isoformat(timespec="microseconds"),
        "id": int(item["id"]),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_program_cursor(cursor: str, view: str, focus: date, user_id: int, app_timezone, now_utc: datetime):
    invalid = HTTPException(status_code=422, detail="Takvim sayfası anahtarı geçersiz. Yenileyin.")
    if not isinstance(cursor, str) or not _PROGRAM_CURSOR_PATTERN.fullmatch(cursor):
        raise invalid
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload = json.loads(raw.decode("utf-8"))
        if type(payload) is not dict or set(payload) != {"v", "view", "day", "owner", "snapshot", "after", "id"}:
            raise ValueError("cursor shape")
        if type(payload["v"]) is not int or payload["v"] != 1:
            raise ValueError("cursor version")
        if payload["view"] != view or payload["day"] != focus.isoformat():
            raise ValueError("cursor calendar scope")
        if payload["owner"] != _program_cursor_owner(user_id):
            raise ValueError("cursor account scope")
        if type(payload["id"]) is not int or payload["id"] <= 0:
            raise ValueError("cursor id")
        if not isinstance(payload["snapshot"], str) or not isinstance(payload["after"], str):
            raise ValueError("cursor timestamps")
        snapshot_at = datetime.fromisoformat(payload["snapshot"])
        after_utc = datetime.fromisoformat(payload["after"])
        if snapshot_at.tzinfo is not None:
            raise ValueError("snapshot must be UTC-naive")
        if after_utc.tzinfo is None or after_utc.utcoffset() != timedelta(0):
            raise ValueError("last occurrence must be UTC-aware")
        now_naive = now_utc.astimezone(timezone.utc).replace(tzinfo=None)
        if snapshot_at > now_naive + timedelta(seconds=30):
            raise ValueError("future snapshot")
        if now_naive - snapshot_at > _PROGRAM_CURSOR_TTL:
            raise HTTPException(status_code=410, detail="Takvim sayfasının süresi doldu. Yenileyin.")
        if after_utc.astimezone(app_timezone).date() != focus:
            raise ValueError("last occurrence outside selected day")
        return snapshot_at, after_utc, payload["id"]
    except HTTPException:
        raise
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise invalid


def _program_snapshot_changed(session, web, user_id: int, snapshot_at: datetime) -> bool:
    changed = session.exec(
        select(web.ScheduleEvent.id)
        .where(web.ScheduleEvent.owner_user_id == user_id)
        .where(web.sa_or(
            web.ScheduleEvent.created_at > snapshot_at,
            web.ScheduleEvent.updated_at > snapshot_at,
        ))
        .limit(1)
    ).first()
    return changed is not None


@router.get('/program')
def program_range(
    view: str = Query('week', pattern='^(today|week|month)$'),
    day: Optional[str] = None,
    offset: int = Query(0, ge=0),
    cursor: Optional[str] = Query(None, max_length=512),
    user=Depends(_mobile_user),
):
    from app import main as web
    today = datetime.now(web.APP_TIMEZONE).date()
    try:
        focus = date.fromisoformat(day) if day else today
    except ValueError:
        raise HTTPException(status_code=422, detail='Geçerli bir takvim günü seçin.')
    if cursor is not None and offset:
        raise HTTPException(status_code=422, detail='Takvim sayfası için tek bir devam anahtarı kullanın.')

    _, start, end, previous, following = web._program_range(view, focus)
    if view == 'month':
        first = focus.replace(day=1)
        grid_start = first - timedelta(days=first.weekday())
        start = web._date_to_local_start(grid_start)
        end = web._date_to_local_end(grid_start + timedelta(days=41))

    now_utc = datetime.now(timezone.utc)
    after_utc = None
    after_id = None
    if cursor is not None:
        snapshot_at, after_utc, after_id = _decode_program_cursor(
            cursor, view, focus, user.id, web.APP_TIMEZONE, now_utc
        )
    else:
        # First-page watermark is naive UTC, matching ScheduleEvent timestamps.
        snapshot_at = now_utc.replace(tzinfo=None) if offset == 0 else None

    with Session(web.engine, expire_on_commit=False) as session:
        if cursor is not None and _program_snapshot_changed(session, web, user.id, snapshot_at):
            raise HTTPException(status_code=409, detail='Takvim bu sırada değişti. Yenileyip tekrar deneyin.')
        if snapshot_at is None:
            occurrences = web._user_schedule_occurrences(session, user.id, start, end)
        else:
            occurrences = web._user_schedule_occurrences(session, user.id, start, end, snapshot_at=snapshot_at)
        # Catch a write racing the occurrence read. A later write is caught by the
        # next cursor request; realtime still triggers a first-page refresh.
        if cursor is not None and _program_snapshot_changed(session, web, user.id, snapshot_at):
            raise HTTPException(status_code=409, detail='Takvim bu sırada değişti. Yenileyip tekrar deneyin.')

    counts = {}
    types_by_day = {}
    for item in occurrences:
        key = item['start_local'].date().isoformat()
        counts[key] = counts.get(key, 0) + 1
        types_by_day.setdefault(key, []).append(item['event_type'])

    def day_markers(day_value: date):
        event_types = types_by_day.get(day_value.isoformat(), [])
        return {'event_types': event_types[:3], 'has_more': len(event_types) > 3}
    if view == 'month':
        days = [
            {
                'date': (grid_start + timedelta(days=i)).isoformat(),
                'label': str((grid_start + timedelta(days=i)).day),
                'in_month': (grid_start + timedelta(days=i)).month == focus.month,
                'count': counts.get((grid_start + timedelta(days=i)).isoformat(), 0),
                **day_markers(grid_start + timedelta(days=i)),
            }
            for i in range(42)
        ]
    else:
        days = [
            {
                'date': item['date'].isoformat(), 'label': item['label'], 'in_month': True,
                'count': counts.get(item['date'].isoformat(), 0), **day_markers(item['date']),
            }
            for item in web._program_week_days(focus)
        ] if view == 'week' else [
            {
                'date': focus.isoformat(), 'label': str(focus.day), 'in_month': True,
                'count': counts.get(focus.isoformat(), 0), **day_markers(focus),
            }
        ]

    selected = sorted(
        [item for item in occurrences if view == 'today' or item['start_local'].date() == focus],
        key=lambda item: (item['start_local'], item['id']),
    )
    total = len(selected)
    if cursor is not None:
        cursor_key = (after_utc, after_id)
        remaining = [
            item for item in selected
            if (_program_local_start_utc(item['start_local'], web.APP_TIMEZONE), item['id']) > cursor_key
        ]
        page = remaining[:50]
        has_more = len(remaining) > len(page)
    else:
        page = selected[offset:offset + 50]
        has_more = offset + len(page) < total

    next_cursor = (
        _encode_program_cursor(view, focus, user.id, snapshot_at, page[-1], web.APP_TIMEZONE)
        if snapshot_at is not None and has_more and page else None
    )
    next_offset = offset + len(page) if cursor is None and has_more else None
    now_local = datetime.now(web.APP_TIMEZONE).replace(second=0, microsecond=0)
    suggested = now_local.replace(minute=0 if now_local.minute < 30 else 30)
    if suggested < now_local:
        suggested += timedelta(minutes=30)
    suggested = datetime.combine(focus, suggested.time())
    return {
        'view': view, 'focus_date': focus.isoformat(), 'today': today.isoformat(),
        'timezone': 'Europe/Istanbul', 'previous_day': previous.isoformat(),
        'next_day': following.isoformat(), 'days': days,
        'items': [
            {'key': f"{item['id']}:{item['start_local'].isoformat()}", 'event_id': item['id'],
             'event_type': item['event_type'], 'title': item['title'], 'status': item['status'],
             'start_local': item['start_local'].strftime('%Y-%m-%dT%H:%M'),
             'end_local': item['end_local'].strftime('%Y-%m-%dT%H:%M') if item['end_local'] else '',
             'patient_id': item['patient'].id if item.get('patient') else None,
             'patient_name': f"{item['patient'].first_name or ''} {item['patient'].last_name or ''}".strip() if item.get('patient') else None,
             'location': item['location'], 'notes': item['notes'],
             'recurrence_rule': item['recurrence_rule']}
            for item in page
        ],
        'total': total, 'next_offset': next_offset, 'next_cursor': next_cursor,
        'copy_days': [{'date': item['date'].isoformat(), 'label': item['label']} for item in web._program_week_days(focus)],
        'month_title': f'{web.PROGRAM_MONTH_NAMES[focus.month - 1]} {focus.year}',
        'event_types': web.PROGRAM_EVENT_TYPES,
        'reminders': ['NONE', *[str(x) for x in sorted(web.REMINDER_OPTIONS)]],
        'recurrences': sorted(web.RECURRENCE_OPTIONS),
        'suggested_start_local': suggested.strftime('%Y-%m-%dT%H:%M'),
        'suggested_end_local': (suggested + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M'),
    }


@router.get('/program/mutations/{request_key}')
def program_mutation(request_key:str,user=Depends(_mobile_user)):
    from app import main as web
    try:
        request_hash=_program_request_hash(user.id,request_key)
    except ValueError as exc:
        raise HTTPException(status_code=422,detail='Program isteği anahtarını kontrol edin.') from exc
    with Session(web.engine,expire_on_commit=False) as session:
        event=session.exec(select(web.ScheduleEvent).where(
            web.ScheduleEvent.owner_user_id==user.id,
            web.ScheduleEvent.client_request_hash==request_hash,
        )).first()
        if not event:return {'state':'NOT_FOUND'}
        if event.status=='DELETED':return {'state':'DELETED','event_id':event.id}
        return {'state':'FOUND','event':_event(session,web,event,user)}


@router.get('/program/events/{event_id}')
def program_event(event_id:int,user=Depends(_mobile_user)):
    from app import main as web
    # Recovery reads must be able to distinguish a soft-deleted event from an
    # event that is still active. Keep the same owner boundary; mutation routes
    # continue to use _owned(), which rejects deleted rows.
    with Session(web.engine,expire_on_commit=False) as session:
        event=session.get(web.ScheduleEvent,event_id)
        if not event or event.owner_user_id!=user.id:
            raise HTTPException(status_code=404,detail='Program kaydı bulunamadı.')
        return {'event':_event(session,web,event,user)}

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
    request_key:Optional[str]=Field(default=None,max_length=96)

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
    if not payload.request_key:
        raise HTTPException(status_code=422,detail='Program isteği anahtarı zorunludur.')
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
