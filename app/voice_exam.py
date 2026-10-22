"""Private voice dictation -> editable review -> atomic existing-record updates."""
import base64
import hashlib
import json
import re
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app import voice_exam_core as core

router = APIRouter()
HEADERS = {'Cache-Control': 'private, no-store'}


class _BodyTooLarge(Exception):
    pass


class VoiceBodyLimitMiddleware:
    """Bound raw audio and JSON request bodies before handlers buffer them."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        if scope['type'] != 'http' or scope.get('method') != 'POST' or '/voice-exam/' not in path:
            return await self.app(scope, receive, send)
        limit = core.MAX_AUDIO + 65536 if path.endswith('/audio') else 256000
        size = 0
        started = False

        async def bounded_receive():
            nonlocal size
            message = await receive()
            size += len(message.get('body', b''))
            if size > limit:
                raise _BodyTooLarge()
            return message

        async def tracked_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
            await send(message)

        length = dict(scope.get('headers', [])).get(b'content-length', b'')
        if length.isdigit() and int(length) > limit:
            return await _reply({'ok': False, 'error': 'Muayene aktarımı boyut sınırını aştı.'}, 413)(scope, receive, send)
        try:
            await self.app(scope, bounded_receive, tracked_send)
        except _BodyTooLarge:
            if not started:
                await _reply({'ok': False, 'error': 'Muayene aktarımı boyut sınırını aştı.'}, 413)(scope, receive, send)


def _reply(data, status=200):
    return JSONResponse(data, status_code=status, headers=HEADERS)


def _user(request):
    from app import main
    if request.method != 'GET':
        from urllib.parse import urlsplit
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return None
        origin = request.headers.get('origin')
        if origin and (urlsplit(origin).scheme, urlsplit(origin).netloc) != (request.url.scheme, request.url.netloc):
            return None
    user = main.get_current_user(request)
    return user if user and user.is_active and user.role in {'DOCTOR', 'ADMIN'} else None


def _owned(session, main, user, ident, *, lock=False):
    statement = select(main.Patient).where(main.Patient.id == ident, main.Patient.owner_user_id == user.id)
    return session.exec(statement.with_for_update() if lock else statement).first()


def _fingerprint(session, main, patient):
    base = core.revision(patient)
    teeth = session.exec(select(main.ToothStatus).where(main.ToothStatus.patient_id == patient.id)
        .order_by(main.ToothStatus.tooth_number)).all()
    latest = session.exec(select(main.Analysis.id).where(main.Analysis.patient_id == patient.id)
        .order_by(main.Analysis.id.desc()).limit(1)).first()
    if not teeth and latest is None:
        return base
    return hashlib.sha256(json.dumps([base, latest, [(t.tooth_number, t.status, t.note) for t in teeth]],
                                    ensure_ascii=False, default=str).encode()).hexdigest()


def _access(request, patient_id):
    from app import main
    if not core.enabled():
        return None, None, _reply({'ok': False, 'error': 'Sesli muayene henüz etkin değil.'}, 503)
    user = _user(request)
    if not user:
        return None, None, _reply({'ok': False}, 401)
    with Session(main.engine) as session:
        patient = _owned(session, main, user, patient_id)
        if not patient:
            return None, None, _reply({'ok': False}, 404)
        fingerprint = _fingerprint(session, main, patient)
    return user, fingerprint, None


@router.get('/voice-exams/device-check')
def device_check(request: Request):
    from app import main
    user = _user(request)
    if not user:
        return RedirectResponse('/login?next=%2Fvoice-exams%2Fdevice-check', status_code=303)
    response = main.templates.TemplateResponse(request=request, name='voice_exam_device_check.html', context={'user': user})
    response.headers.update(HEADERS)
    return response


@router.get('/voice-exams')
def voice_entry(request: Request, q: str = ''):
    from app import main
    user = _user(request)
    if not user:
        return RedirectResponse('/login?next=%2Fvoice-exams', status_code=303)
    if not core.enabled():
        return _reply({'ok': False, 'error': 'Sesli muayene henüz etkin değil.'}, 503)
    query = q.strip()[:100]
    with Session(main.engine) as session:
        statement = select(main.Patient).where(main.Patient.owner_user_id == user.id)
        if query:
            from sqlalchemy import or_
            pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            statement = statement.where(or_(main.Patient.first_name.ilike(pattern, escape='\\'),
                main.Patient.last_name.ilike(pattern, escape='\\'), main.Patient.anonymous_id.ilike(pattern, escape='\\')))
        patients = session.exec(statement.order_by(main.Patient.id.desc()).limit(30)).all()
    response = main.templates.TemplateResponse(request=request, name='voice_exam_entry.html',
        context={'patients': patients, 'q': query, 'user': user})
    response.headers.update(HEADERS)
    return response


@router.get('/voice-exams/{patient_id}/session')
def voice_session(request: Request, patient_id: int):
    from app import main
    user, fingerprint, error = _access(request, patient_id)
    if error is not None:
        return error
    with Session(main.engine) as session:
        patient = _owned(session, main, user, patient_id)
        if not patient:
            return _reply({'ok': False}, 404)
    response = main.templates.TemplateResponse(request=request, name='voice_exam_session.html',
        context={'patient': patient, 'user': user})
    response.headers.update(HEADERS)
    return response


@router.get('/voice-exams/capabilities')
def capabilities(request: Request):
    from app import main
    user = _user(request)
    if not user:
        return _reply({'ok': False}, 401)
    from app.voice_exam_live import live_enabled
    return _reply({'ok': True, 'enabled': core.enabled(), 'live_enabled': live_enabled(), 'max_audio_bytes': core.MAX_AUDIO})


class SourceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=3, max_length=400)


@router.post('/patients/{patient_id}/voice-exam/sources')
def source_references(request: Request, patient_id: int, payload: SourceInput):
    user, fingerprint, error = _access(request, patient_id)
    if error is not None:
        return error
    from app.voice_exam_sources import retrieve
    return _reply({'ok': True, **retrieve(payload.query)})


class ClinicalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    context: dict
    consent: bool = False


class FinalInput(ClinicalInput):
    insights: list[dict] = Field(default_factory=list, max_length=24)
    uncertain: str = Field(default='', max_length=3000)


@router.post('/patients/{patient_id}/voice-exam/finalize')
def final_review(request: Request, patient_id: int, payload: FinalInput):
    user, fingerprint, error = _access(request, patient_id)
    if error is not None:
        return error
    if not payload.consent:
        return _reply({'ok': False, 'error': 'İşleme onayını kontrol et.'}, 400)
    try:
        from app.voice_exam_final import finalize
        return _reply({'ok': True, 'revision': fingerprint,
                       'final': finalize(payload.context, payload.insights, payload.uncertain)})
    except core.VoiceError as exc:
        return _reply({'ok': False, 'error': str(exc)}, 422)


@router.get('/patients/{patient_id}/voice-exam/history')
def reviewed_history(request: Request, patient_id: int):
    """Only explicitly saved voice clinical fields, never arbitrary notes or raw audio."""
    from app import main
    from app.work_jobs import WorkJob
    user, fingerprint, error = _access(request, patient_id)
    if error is not None:
        return error
    labels = {'medical_history': 'Sistemik hastalık / hasta beyanı', 'medications': 'İlaç / hasta beyanı',
              'allergies': 'Alerji / hasta beyanı'}
    fields = {}
    with Session(main.engine) as session:
        # Join prevents scanning the entire patient archive and excludes non-voice records.
        rows = session.exec(select(main.Analysis).join(WorkJob, WorkJob.resource_id == main.Analysis.id)
            .where(main.Analysis.patient_id == patient_id, WorkJob.owner_user_id == user.id,
                   WorkJob.resource_type == 'ANALYSIS', WorkJob.kind == 'VOICE_REVIEW', WorkJob.status == 'DONE')
            .order_by(main.Analysis.id.desc()).limit(12)).all()
        for row in rows:
            for paragraph in (row.clinical_notes or '').split('\n\n'):
                for name, label in labels.items():
                    prefix = label + ': '
                    if name not in fields and paragraph.startswith(prefix):
                        value = paragraph[len(prefix):].strip()
                        if value and len(value) <= 3000:
                            fields[name] = {'value': value, 'quote': value, 'analysis_id': row.id}
    return _reply({'ok': True, 'revision': fingerprint, 'fields': fields,
        'notice': 'Önceki hekim onaylı sesli muayene kayıtlarıdır. Güncel kullanım veya hastalık durumu olarak kabul etmeden hastayla doğrulayın.'})


@router.post('/patients/{patient_id}/voice-exam/clinical')
def clinical_review(request: Request, patient_id: int, payload: ClinicalInput):
    user, fingerprint, error = _access(request, patient_id)
    if error is not None:
        return error
    if not payload.consent:
        return _reply({'ok': False}, 400)
    try:
        from app.voice_exam_clinical import assess
        return _reply({'ok': True, **assess(payload.context)})
    except core.VoiceError as exc:
        return _reply({'ok': False, 'error': str(exc)}, 422)


@router.post('/voice-exams/anonymous')
def anonymous(request: Request):
    from app import main
    if not core.enabled():
        return _reply({'ok': False}, 503)
    user = _user(request)
    if not user:
        return _reply({'ok': False}, 401)
    with Session(main.engine, expire_on_commit=False) as session:
        patient = main.Patient(owner_user_id=user.id, anonymous_id='SES-' + secrets.token_hex(8).upper())
        session.add(patient); session.flush()
        events = main._record_patient_realtime_events(session, patient, 'PATIENT_CREATED')
        session.commit()
    for event in events:
        main.on_loop(main._publish_realtime_event, event)
    return RedirectResponse('/voice-exams/' + str(patient.id) + '/session', status_code=303)


@router.post('/patients/{patient_id}/voice-exam/audio')
async def audio(request: Request, patient_id: int):
    try:
        user, fingerprint, error = await run_in_threadpool(_access, request, patient_id)
        if error is not None:
            return error
        if request.headers.get('x-voice-consent') != 'yes':
            return _reply({'ok': False, 'error': 'Ses aktarımı onayını işaretle.'}, 400)
        # Raw request body avoids UploadFile's temporary-file spooling.
        data = await request.body()
        if request.headers.get('content-type') == 'application/vnd.dentalai.voice-packet':
            if len(data) < 4:
                raise core.VoiceError('Ses paketi doğrulanamadı.')
            size = int.from_bytes(data[:4], 'big')
            if size > core.MAX_CONTEXT or size < 2 or len(data) < 4 + size:
                raise core.VoiceError('Ses paketi bağlamı doğrulanamadı.')
            try:
                context = core.clinical_context(json.loads(data[4:4 + size]))
            except (ValueError, UnicodeError):
                raise core.VoiceError('Görüşme bağlamı doğrulanamadı.') from None
            data = data[4 + size:]
            mime = core.validate_audio(data, request.headers.get('x-voice-mime', ''))
        else:
            # Compatibility for older clients. New clients put larger structured
            # context in a bounded binary body, not privacy-sensitive proxy headers.
            mime = core.validate_audio(data, request.headers.get('content-type', ''))
            encoded = request.headers.get('x-voice-context', '')
            if len(encoded) > 8000:
                raise core.VoiceError('Görüşme bağlamı çok uzun.')
            try:
                context = core.clinical_context(json.loads(base64.b64decode(encoded, validate=True))) if encoded else {}
            except (ValueError, UnicodeError):
                raise core.VoiceError('Görüşme bağlamı doğrulanamadı.') from None
        result = await run_in_threadpool(core.extract, data=data, mime=mime, **({'context': context} if context else {}))
        # Do not include any existing patient identity or clinical history in the provider request.
        return _reply({'ok': True, 'review': result, 'revision': fingerprint})
    except core.VoiceError as exc:
        return _reply({'ok': False, 'error': str(exc)}, 422)


class TextInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    transcript: str = Field(min_length=1, max_length=core.MAX_TRANSCRIPT)
    consent: bool = False
    context: dict = Field(default_factory=dict)


@router.post('/patients/{patient_id}/voice-exam/text')
def text_review(request: Request, patient_id: int, payload: TextInput):
    user, fingerprint, error = _access(request, patient_id)
    if error is not None:
        return error
    if not payload.consent:
        return _reply({'ok': False, 'error': 'Metin aktarımı onayını işaretle.'}, 400)
    try:
        return _reply({'ok': True, 'revision': fingerprint,
                       'review': core.extract(transcript=payload.transcript, **({'context': core.clinical_context(payload.context)} if payload.context else {}))})
    except core.VoiceError as exc:
        return _reply({'ok': False, 'error': str(exc)}, 422)


class ToothChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tooth: str = Field(pattern=r'^(?:[1-4][1-8]|[5-8][1-5])$')
    status: str
    note: str = Field(default='', max_length=2000)


class AppointmentChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=160)
    start_at: str = Field(min_length=16, max_length=32)
    end_at: str = Field(default='', max_length=32)


class ApplyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: str = Field(pattern=r'^[a-f0-9]{32}$')
    revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirmed: bool = False
    fields: dict[str, str] = Field(default_factory=dict, max_length=9)
    teeth: list[ToothChoice] = Field(default_factory=list, max_length=52)
    appointment: AppointmentChoice | None = None


def _reviewed_fields(fields):
    if set(fields) - set(core.FIELDS):
        raise core.VoiceError('Tanımsız hasta alanı.')
    values = {}
    for key, value in fields.items():
        value = core._string(value, 3000)
        if value:
            values[key] = value
    if any(len(values.get(key, '')) > 100 for key in ('first_name', 'last_name')):
        raise core.VoiceError('Hasta adı veya soyadı çok uzun.')
    age = values.get('age')
    if age and (not age.isdecimal() or not 0 <= int(age) <= 120):
        raise core.VoiceError('Yaş 0–120 arasında olmalı.')
    return values


def appointment_conflict(occurrences, start, end=None):
    end = end or start
    for item in occurrences:
        if item.get('status') != 'ACTIVE':
            continue
        other_start = item['start_local']; other_end = item.get('end_local') or other_start
        if (start == other_start or other_start < start < other_end
                or start < other_start < end):
            return True
    return False


@router.post('/patients/{patient_id}/voice-exam/apply')
def apply_review(request: Request, patient_id: int, payload: ApplyInput):
    from app import main
    from app.work_jobs import WorkJob
    if not core.enabled():
        return _reply({'ok': False}, 503)
    user = _user(request)
    if not user:
        return _reply({'ok': False}, 401)
    if not payload.confirmed:
        return _reply({'ok': False, 'error': 'Alanları kontrol edip kaydı onayla.'}, 400)
    try:
        fields = _reviewed_fields(payload.fields)
        if not fields and not payload.teeth and payload.appointment is None:
            raise core.VoiceError('Kaydedilecek en az bir alan seç.')
        if any(item.status not in core.TOOTH_STATES for item in payload.teeth):
            raise core.VoiceError('Diş bulgusu geçersiz.')
        if len({item.tooth for item in payload.teeth}) != len(payload.teeth):
            raise core.VoiceError('Aynı diş için tek bir bulgu seç.')
    except core.VoiceError as exc:
        return _reply({'ok': False, 'error': str(exc)}, 400)
    dedupe = 'voice-review:' + str(user.id) + ':' + payload.request_key
    events = []; schedule = None
    with Session(main.engine, expire_on_commit=False) as session:
        patient = _owned(session, main, user, patient_id, lock=True)
        if not patient:
            return _reply({'ok': False}, 404)
        prior = session.exec(select(WorkJob).where(WorkJob.dedupe_key == dedupe)).first()
        if prior:
            # Same key cannot be rebound to a different patient's analysis.
            analysis = session.get(main.Analysis, prior.resource_id)
            if not analysis or analysis.patient_id != patient_id:
                return _reply({'ok': False}, 409)
            return _reply({'ok': True, 'already_saved': True, 'analysis_id': analysis.id,
                           'patient_url': '/patients/' + str(patient_id)})
        if _fingerprint(session, main, patient) != payload.revision:
            return _reply({'ok': False, 'error': 'Hasta bilgileri değişti. Sayfayı yenileyip yeniden kontrol et.'}, 409)
        if payload.appointment:
            appointment, error = main._validate_schedule_input(
                session, user, 'APPOINTMENT', payload.appointment.title,
                payload.appointment.start_at, payload.appointment.end_at,
                str(patient_id), '', '', 'NONE', None, 'NONE', '')
            if error:
                return _reply({'ok': False, 'error': error}, 400)
            # Serialize voice bookings by owner, then include weekly occurrences
            # in the conflict check using the app's existing calendar expansion.
            session.exec(select(main.User).where(main.User.id == user.id).with_for_update()).first()
            local_start = datetime.fromisoformat(payload.appointment.start_at)
            local_end = datetime.fromisoformat(payload.appointment.end_at) if payload.appointment.end_at else None
            occurrences = main._user_schedule_occurrences(session, user.id,
                local_start - timedelta(days=7), (local_end or local_start) + timedelta(days=1))
            if appointment_conflict(occurrences, local_start, local_end):
                return _reply({'ok': False, 'error': 'Bu zaman programındaki aktif bir kayıtla çakışıyor. Randevu saatini kontrol et.'}, 409)
            schedule = main.ScheduleEvent(owner_user_id=user.id, **appointment)
            session.add(schedule); session.flush()
            main._sync_program_reminder(session, schedule)
            events.append(main._record_program_realtime_event(session, user.id, 'PROGRAM_CREATED', schedule.id))
        labels = {'medical_history': 'Sistemik hastalık / hasta beyanı', 'medications': 'İlaç / hasta beyanı',
                  'allergies': 'Alerji / hasta beyanı', 'clinical_findings': 'Klinik bulgular', 'plan': 'Hekim planı',
                  'chief_complaint': 'Başvuru şikâyeti'}
        notes = '\n\n'.join(labels[key] + ': ' + value for key, value in fields.items() if key in labels)
        for key in ('first_name', 'last_name', 'chief_complaint'):
            if key in fields:
                setattr(patient, key, fields[key])
        if 'age' in fields:
            if patient.birth_date:
                return _reply({'ok': False, 'error': 'Kayıtlı doğum tarihi var. Yaşı hasta bilgileri bölümünden kontrol et.'}, 409)
            patient.age = int(fields['age'])
        for item in payload.teeth:
            tooth = session.exec(select(main.ToothStatus).where(
                main.ToothStatus.patient_id == patient_id, main.ToothStatus.tooth_number == item.tooth)).first()
            if tooth is None:
                tooth = main.ToothStatus(patient_id=patient_id, tooth_number=item.tooth)
            tooth.status = item.status; tooth.note = item.note or None
            tooth.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            session.add(tooth)
            notes += '\n\nHekim tarafından onaylanan diş ' + item.tooth + ': ' + item.status + ' ' + item.note
        analysis = main.Analysis(patient_id=patient_id, status='DRAFT', clinical_notes=notes.strip() or 'Sesli muayene alanları hekim tarafından onaylandı.')
        session.add(analysis); session.flush(); session.add(patient)
        events += main._record_patient_realtime_events(session, patient, 'PATIENT_UPDATED')
        # Audit/idempotency only: no audio or transcript in generic job payloads.
        session.add(WorkJob(owner_user_id=user.id, resource_id=analysis.id, resource_type='ANALYSIS',
            kind='VOICE_REVIEW', source_hash=hashlib.sha256(dedupe.encode()).hexdigest(),
            dedupe_key=dedupe, payload_json='{}', status='DONE', result_ref=str(analysis.id)))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return _reply({'ok': False, 'error': 'Kayıt zaten işleniyor. Aynı kaydı tekrar deneyebilirsin.'}, 409)
    for event in events:
        main.on_loop(main._publish_realtime_event, event)
    if schedule:
        main._wake_program_reminder_worker()
    return _reply({'ok': True, 'analysis_id': analysis.id, 'patient_url': '/patients/' + str(patient_id)})

from app.voice_exam_live import register_live
register_live(router)

