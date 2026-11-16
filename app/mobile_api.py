"""Native mobile API for the Android client.

This layer exposes JSON contracts over the existing FastAPI/SQLModel business
data. It deliberately reuses the same session-token records as the web app so
mobile clients do not create a second authentication system.
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
import hashlib
import hmac
import logging
import os
import re
import shutil
import time
import threading
import uuid
from collections import deque
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field as RequestField
from sqlmodel import SQLModel, Session, func, select, Field as SQLField
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from app.clinical_media import sanitize_clinical_media_image
from app.upload_limits import (MAX_PATIENT_MEDIA_FILES, MAX_PATIENT_MEDIA_FILE_BYTES, MAX_PATIENT_MEDIA_BATCH_BYTES, MAX_ANALYSIS_IMAGE_BYTES, MAX_ANALYSIS_BATCH_BYTES)
from app.work_jobs import WorkJob
from starlette.requests import Request
from fastapi.responses import JSONResponse

from app.auth import create_session_token, hash_session_token, verify_password
from app.auth_rate import LOGIN_WINDOW_SECONDS, LOGIN_MAX_FAILURES, admit as admit_auth_attempt, clear as clear_auth_attempt, bucket_key
from app.main import (
    Analysis,
    MobilePushDevice,
    ImageAsset,
    PatientProfile,
    DoctorProfile,
    Patient,
    PatientMedia,
    ScheduleEvent,
    SessionToken,
    ToothStatus,
    ToothSurfaceStatus,
    Treatment,
    User,
    EmailVerificationChallenge,
    PROGRAM_EVENT_TYPES,
    _find_duplicate_patient,
    _validate_schedule_input,
    UserAccountMeta,
    engine,
    _run_analysis_vision,
    _run_preliminary_ai,
    classify_dental_image,
    AdminNotice, SupportTicket, SupportTicketMessage, SupportTicketReadState, StudyCourse, StudyMaterial, StudyChatMessage,
    ConsultationCase, ConsultationMessage, ConsultationInboxState, ExpertProfile, E2EEDeviceKey,
    _socket_case_authorized,
    expert_support_request_create, expert_support_message, study_ai_ask,
    SESSION_COOKIE, storage_persist_file, storage_ensure_local, storage_delete, _record_patient_realtime_events,
    _patient_edit_revision,
    _record_realtime_event, _publish_realtime_event, on_loop,
    _support_user_can_reply, _support_unread_count, _mark_support_read, UserReport, _ensure_report_support_tickets,
    _cancel_pending_program_reminders, _resolve_notifications, _record_program_realtime_event, _utcnow_naive,
    _ensure_email_verification_challenge, _verify_email_code,
)

router = APIRouter(prefix="/api/mobile/v1", tags=["mobile"])
bearer = HTTPBearer(auto_error=False)
MOBILE_MAX_IMAGE_BYTES = max(1, int(os.getenv("MOBILE_MAX_IMAGE_BYTES", str(15 * 1024 * 1024))))
MOBILE_MAX_IMAGE_PIXELS = max(1, int(os.getenv("MOBILE_MAX_IMAGE_PIXELS", "40000000")))
# These two values are protocol constants shared with web and native clients.
MOBILE_MAX_ANALYSIS_BYTES = MAX_ANALYSIS_IMAGE_BYTES
MOBILE_MAX_PATIENT_MEDIA_BYTES = MAX_PATIENT_MEDIA_FILE_BYTES
_PATIENT_MEDIA_REQUEST_KEY = re.compile(r"^[A-Za-z0-9_-]{16,96}$")
_PATIENT_MEDIA_BATCH_ID = re.compile(r"^[A-Za-z0-9_-]{16,96}$")
# Bound in-memory audio buffering and provider work per web process.
_mobile_voice_audio_slots = threading.BoundedSemaphore(2)
LOGIN_RATE_WINDOW_SECONDS = LOGIN_WINDOW_SECONDS
LOGIN_RATE_MAX_FAILURES = LOGIN_MAX_FAILURES


def _check_login_rate(login: str) -> None:
    admit_auth_attempt(engine, "login", login,
        limit=LOGIN_RATE_MAX_FAILURES, window=LOGIN_RATE_WINDOW_SECONDS)


def _record_login_failure(login: str) -> None:
    # Counted at admission, before password hashing, across all instances.
    pass


def _clear_login_failures(login: str) -> None:
    clear_auth_attempt(engine, bucket_key("login", login))


def _copy_validated_image(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    total = 0
    try:
        with destination.open("wb") as out:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail="Görüntü dosyası çok büyük.")
                out.write(chunk)
        sanitize_clinical_media_image(
            destination,
            destination.suffix.lower(),
            MOBILE_MAX_IMAGE_PIXELS,
        )
        # Return the original streamed byte count; sanitization may change file size.
        return total
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except ValueError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Geçersiz veya bozuk görüntü dosyası.") from exc

class LoginRequest(BaseModel):
    login: str
    password: str
    renew_email_code: bool = False

class EmailVerifyRequest(BaseModel):
    challenge_token: str
    code: str


class E2EEDeviceKeyRequest(BaseModel):
    device_id: str
    public_key: str
    algorithm: str = "X25519"
    key_version: str = "v1"


class MobileToken(BaseModel):
    access_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_at: datetime
    challenge_token: Optional[str] = None


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Oturum geçersiz veya süresi dolmuş.")


def _mobile_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    token_hash = hash_session_token(credentials.credentials)
    with Session(engine, expire_on_commit=False) as session:
        session_token = session.exec(
            select(SessionToken).where(SessionToken.token_hash == token_hash)
        ).first()

        if not session_token:
            raise _unauthorized()

        if session_token.expires_at <= datetime.utcnow():
            session.delete(session_token)
            session.commit()
            raise _unauthorized()

        user = session.get(User, session_token.user_id)
        if not user or not user.is_active or not user.email_verified_at:
            raise _unauthorized()
        return user


def _user_payload(session: Session, user: User) -> dict:
    profile = session.exec(
        select(DoctorProfile).where(DoctorProfile.user_id == user.id)
    ).first()
    meta = session.exec(
        select(UserAccountMeta).where(UserAccountMeta.user_id == user.id)
    ).first()
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "professional_title": meta.professional_title if meta else None,
        "specialty": profile.specialty if profile else None,
        "university": profile.university if profile else None,
    }


def _patient_payload(patient: Patient) -> dict:
    return {
        "id": patient.id,
        "anonymous_id": patient.anonymous_id,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "phone": patient.phone,
        "birth_date": patient.birth_date,
        "age": patient.age,
        "chief_complaint": patient.chief_complaint,
        "created_at": patient.created_at,
    }


@router.put("/e2ee/device")
def register_e2ee_device(payload: E2EEDeviceKeyRequest, user: User = Depends(_mobile_user)):
    device_id = payload.device_id.strip()[:128]
    public_key = payload.public_key.strip().lower()
    algorithm = payload.algorithm.strip().upper()
    key_version = payload.key_version.strip()[:32]
    if len(device_id) < 8 or len(public_key) != 64 or algorithm != "X25519" or key_version != "v1":
        raise HTTPException(status_code=422, detail="Geçersiz E2EE cihaz anahtarı.")
    try:
        bytes.fromhex(public_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Geçersiz E2EE açık anahtarı.") from exc
    with Session(engine, expire_on_commit=False) as session:
        row = session.exec(select(E2EEDeviceKey).where(E2EEDeviceKey.device_id == device_id)).first()
        if row and row.user_id != user.id:
            raise HTTPException(status_code=409, detail="Cihaz kimliği başka bir hesaba bağlı.")
        if row:
            if row.revoked_at is not None:
                raise HTTPException(status_code=409, detail="İptal edilmiş E2EE cihazı yeniden etkinleştirilemez; yeni bir cihaz kimliği oluşturun.")
            row.public_key = public_key
            row.algorithm = algorithm
            row.key_version = key_version
            session.add(row)
        else:
            row = E2EEDeviceKey(user_id=user.id, device_id=device_id, public_key=public_key, algorithm=algorithm, key_version=key_version)
            session.add(row)
        session.commit()
    return {"ok": True, "device_id": device_id, "public_key": public_key, "algorithm": algorithm, "key_version": key_version}


def _e2ee_peer_allowed(session: Session, user_id: int, peer_user_id: int) -> bool:
    if user_id == peer_user_id:
        return True
    return session.exec(
        select(ConsultationCase).where(
            ((ConsultationCase.requester_user_id == user_id) & (ConsultationCase.expert_user_id == peer_user_id)) |
            ((ConsultationCase.expert_user_id == user_id) & (ConsultationCase.requester_user_id == peer_user_id))
        )
    ).first() is not None


@router.get("/e2ee/users/{user_id}/keys")
def get_e2ee_user_keys(user_id: int, user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        if not _e2ee_peer_allowed(session, user.id, user_id):
            raise HTTPException(status_code=403, detail="Bu kullanıcının E2EE anahtarlarına erişemezsiniz.")
        rows = session.exec(
            select(E2EEDeviceKey).where(
                E2EEDeviceKey.user_id == user_id,
                E2EEDeviceKey.revoked_at == None,
            ).order_by(E2EEDeviceKey.created_at.desc())
        ).all()
        if not rows:
            raise HTTPException(status_code=404, detail="Kullanıcının aktif E2EE cihaz anahtarı bulunamadı.")
        return {"items": [
            {"device_id": row.device_id, "public_key": row.public_key, "algorithm": row.algorithm, "key_version": row.key_version}
            for row in rows
        ]}


@router.get("/e2ee/users/{user_id}/key")
def get_e2ee_user_key(user_id: int, user: User = Depends(_mobile_user)):
    data = get_e2ee_user_keys(user_id, user)
    return data["items"][0]


@router.delete("/e2ee/device/{device_id}")
def revoke_e2ee_device(device_id: str, user: User = Depends(_mobile_user)):
    device_id = device_id.strip()
    with Session(engine, expire_on_commit=False) as session:
        row = session.exec(
            select(E2EEDeviceKey).where(
                E2EEDeviceKey.device_id == device_id,
                E2EEDeviceKey.user_id == user.id,
            )
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="E2EE cihazı bulunamadı.")
        if row.revoked_at is None:
            row.revoked_at = datetime.utcnow()
            session.add(row)
            session.commit()
    return {"ok": True, "device_id": device_id, "revoked": True}


@router.post("/auth/login", response_model=MobileToken)
def mobile_login(payload: LoginRequest, request: Request = None):
    login = payload.login.strip().lower()
    if request is not None:
        admit_auth_attempt(engine, "login-ip", request.client.host if request.client else "unknown",
            limit=int(os.getenv("AUTH_IP_RATE_MAX_ATTEMPTS", "100")), window=LOGIN_RATE_WINDOW_SECONDS)
    _check_login_rate(login)

    with Session(engine, expire_on_commit=False) as session:
        user = session.exec(
            select(User).where(
                (User.username == login) | (User.email == login)
            )
        ).first()

        if (
            not user
            or not user.is_active
            or not user.password_hash
            or not verify_password(payload.password, user.password_hash)
        ):
            _record_login_failure(login)
            raise HTTPException(
                status_code=401,
                detail="Kullanıcı adı/e-posta veya şifre hatalı.",
            )

        _clear_login_failures(login)
        if not user.email:
            raise HTTPException(status_code=403, detail='EMAIL_REQUIRED')
        if not user.email_verified_at:
            try:
                challenge = _ensure_email_verification_challenge(session, user, renew=payload.renew_email_code)
            except Exception:
                raise HTTPException(status_code=503, detail='EMAIL_VERIFICATION_SEND_FAILED')
            return MobileToken(access_token=None, token_type='Bearer', expires_at=challenge.expires_at, challenge_token=challenge.public_token)
        token = create_session_token()
        expires_at = datetime.utcnow().replace(microsecond=0)
        from datetime import timedelta
        expires_at += timedelta(days=7)

        session.add(
            SessionToken(
                token_hash=hash_session_token(token),
                user_id=user.id,
                expires_at=expires_at,
            )
        )
        session.commit()

    _clear_login_failures(login)
    return MobileToken(access_token=token, expires_at=expires_at)


@router.post('/auth/verify-email')
def mobile_verify_email(payload: EmailVerifyRequest):
    with Session(engine, expire_on_commit=False) as session:
        challenge = session.exec(select(EmailVerificationChallenge).where(EmailVerificationChallenge.public_token == payload.challenge_token)).first()
        user = session.get(User, challenge.user_id) if challenge else None
        if not challenge or not user or not _verify_email_code(session, user, challenge, payload.code):
            raise HTTPException(status_code=400, detail='Kod hatalı, süresi dolmuş veya daha önce kullanılmış.')
        token = create_session_token()
        expires_at = datetime.utcnow().replace(microsecond=0) + timedelta(days=7)
        session.add(SessionToken(token_hash=hash_session_token(token), user_id=user.id, expires_at=expires_at))
        session.commit()
        return MobileToken(access_token=token, expires_at=expires_at)


@router.post("/auth/logout")
def mobile_logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
):
    if credentials and credentials.scheme.lower() == "bearer":
        token_hash = hash_session_token(credentials.credentials)
        with Session(engine, expire_on_commit=False) as session:
            token = session.exec(
                select(SessionToken).where(SessionToken.token_hash == token_hash)
            ).first()
            if token:
                session.delete(token)
                session.commit()
    return {"ok": True}


@router.get("/me")
def mobile_me(user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        return {"user": _user_payload(session, user)}


@router.get("/dashboard")
def mobile_dashboard(user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        patient_query = (
            select(Patient)
            .where(Patient.owner_user_id == user.id)
            .order_by(Patient.created_at.desc())
        )
        recent_patients = [_patient_payload(p) for p in session.exec(patient_query.limit(8)).all()]

        patient_count = session.exec(
            select(func.count()).select_from(Patient).where(Patient.owner_user_id == user.id)
        ).one()
        analysis_count = session.exec(
            select(func.count())
            .select_from(Analysis)
            .join(Patient, Patient.id == Analysis.patient_id)
            .where(Patient.owner_user_id == user.id)
        ).one()

        now = datetime.utcnow()
        upcoming_events = session.exec(
            select(ScheduleEvent)
            .where(
                ScheduleEvent.owner_user_id == user.id,
                ScheduleEvent.status == "ACTIVE",
                ScheduleEvent.start_at >= now,
            )
            .order_by(ScheduleEvent.start_at.asc())
            .limit(8)
        ).all()
        upcoming = [
            {
                "id": e.id,
                "event_type": e.event_type,
                "title": e.title,
                "start_at": e.start_at,
                "end_at": e.end_at,
                "patient_id": e.patient_id,
                "location": e.location,
                "status": e.status,
                "reminder_minutes": e.reminder_minutes,
                "notification_enabled": e.notification_enabled,
            }
            for e in upcoming_events
        ]

        return {
            "user": _user_payload(session, user),
            "stats": {
                "patient_count": int(patient_count),
                "analysis_count": int(analysis_count),
                "upcoming_event_count": len(upcoming),
            },
            "recent_patients": recent_patients,
            "upcoming_events": upcoming,
        }


@router.get("/patients")
def mobile_patients(
    user: User = Depends(_mobile_user),
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    search = " ".join(q.strip().split())
    with Session(engine, expire_on_commit=False) as session:
        query = (
            select(Patient)
            .where(Patient.owner_user_id == user.id)
            .order_by(Patient.created_at.desc(), Patient.id.desc())
        )
        if search:
            pattern = f"%{search}%"
            query = query.where(
                (Patient.first_name.ilike(pattern))
                | (Patient.last_name.ilike(pattern))
                | (Patient.phone.ilike(pattern))
                | (Patient.anonymous_id.ilike(pattern))
            )

        patients = session.exec(query.offset(offset).limit(limit)).all()
        total_query = select(Patient).where(Patient.owner_user_id == user.id)
        if search:
            total_query = total_query.where(
                (Patient.first_name.ilike(pattern))
                | (Patient.last_name.ilike(pattern))
                | (Patient.phone.ilike(pattern))
                | (Patient.anonymous_id.ilike(pattern))
            )
        total = int(session.exec(select(func.count()).select_from(total_query.subquery())).one())

        return {
            "items": [_patient_payload(p) for p in patients],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


class MobilePatientCreate(BaseModel):
    first_name: str
    last_name: str
    birth_date: Optional[str] = None
    phone: Optional[str] = None
    tc_kimlik_no: Optional[str] = None
    address: Optional[str] = None
    chief_complaint: Optional[str] = None
    force_create: bool = False


class MobileToothUpdate(BaseModel):
    status: str
    note: Optional[str] = None
    surface: Optional[str] = None
    surfaces: Optional[list[str]] = None


class MobileSurfaceUpdate(BaseModel):
    status: str
    note: Optional[str] = None


class MobileScheduleCreate(BaseModel):
    event_type: str
    title: str
    start_at: str
    end_at: str = ""
    patient_id: Optional[int] = None
    location: str = ""
    notes: str = ""
    reminder_minutes: Optional[int] = 30
    notification_enabled: bool = True
    recurrence_rule: str = "NONE"
    recurrence_until: str = ""


@router.post("/patients")
def mobile_create_patient(payload: MobilePatientCreate, user: User = Depends(_mobile_user)):
    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()
    phone = payload.phone.strip() if payload.phone else None
    if not first_name or not last_name:
        raise HTTPException(status_code=422, detail="Ad ve soyad zorunludur.")
    if phone and (not phone.isdigit() or len(phone) != 11 or not phone.startswith("05")):
        raise HTTPException(status_code=422, detail="Telefon 05 ile başlamalı ve 11 rakam olmalıdır.")

    calculated_age = None
    if payload.birth_date:
        try:
            birth = datetime.strptime(payload.birth_date, "%Y-%m-%d").date()
            today = datetime.utcnow().date()
            calculated_age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        except ValueError:
            raise HTTPException(status_code=422, detail="Doğum tarihi geçersiz.")

    with Session(engine, expire_on_commit=False) as session:
        duplicate, reason = _find_duplicate_patient(
            session, user.id, first_name, last_name, payload.birth_date, calculated_age, phone
        )
        if duplicate and not payload.force_create:
            raise HTTPException(
                status_code=409,
                detail={"message": "Benzer bir hasta zaten kayıtlı.", "patient_id": duplicate.id, "reason": reason},
            )
        patient = Patient(
            anonymous_id=f"PAT-{__import__('uuid').uuid4().hex[:10].upper()}",
            owner_user_id=user.id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            tc_kimlik_no=payload.tc_kimlik_no.strip() if payload.tc_kimlik_no else None,
            birth_date=payload.birth_date,
            age=calculated_age,
            chief_complaint=payload.chief_complaint.strip() if payload.chief_complaint else None,
        )
        session.add(patient)
        session.flush()
        profile=PatientProfile(patient_id=patient.id, address=payload.address.strip() if payload.address else None)
        session.add(profile); session.flush()
        events=_record_patient_realtime_events(session,patient,"PATIENT_CREATED",profile); session.commit()
    for event in events: on_loop(_publish_realtime_event,event)
    return {"patient": _patient_payload(patient)}


@router.get("/schedule")
def mobile_schedule(user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        events = session.exec(
            select(ScheduleEvent)
            .where(ScheduleEvent.owner_user_id == user.id, ScheduleEvent.status != "DELETED")
            .order_by(ScheduleEvent.start_at.asc())
            .limit(100)
        ).all()
        return {
            "items": [
                {
                    "id": e.id, "event_type": e.event_type, "title": e.title,
                    "start_at": e.start_at, "end_at": e.end_at,
                    "patient_id": e.patient_id, "location": e.location,
                    "notes": e.notes, "status": e.status,
                    "reminder_minutes": e.reminder_minutes,
                    "notification_enabled": e.notification_enabled,
                    "recurrence_rule": e.recurrence_rule,
                }
                for e in events
            ],
            "event_types": PROGRAM_EVENT_TYPES,
        }


@router.post("/schedule")
def mobile_create_schedule(payload: MobileScheduleCreate, user: User = Depends(_mobile_user)):
    from app import main as web
    with Session(engine, expire_on_commit=False) as session:
        values, error = _validate_schedule_input(
            session, user, payload.event_type, payload.title, payload.start_at, payload.end_at,
            str(payload.patient_id or ""), payload.location, payload.notes,
            "NONE" if not payload.notification_enabled or payload.reminder_minutes is None else str(payload.reminder_minutes), "1" if payload.notification_enabled else None,
            payload.recurrence_rule, payload.recurrence_until,
        )
        if error:
            raise HTTPException(status_code=422, detail=error)
        event = ScheduleEvent(owner_user_id=user.id, **values)
        session.add(event)
        session.flush()
        web._sync_program_reminder(session,event)
        realtime_events=web._resolve_notifications(session,user_id=user.id,notice_type="PROGRAM_REMINDER",related_type="schedule_event",related_id=event.id)
        realtime_events.append(web._record_program_realtime_event(session,user.id,"PROGRAM_CREATED",event.id))
        session.commit()
        web._wake_program_reminder_worker()
        for realtime in realtime_events:on_loop(_publish_realtime_event,realtime)
        return {"event": {"id": event.id, "event_type": event.event_type, "title": event.title,
                          "start_at": event.start_at, "end_at": event.end_at, "patient_id": event.patient_id,
                          "location": event.location, "status": event.status}}



@router.post("/schedule/{event_id}/complete")
def mobile_complete_schedule(event_id: int, user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        event = session.get(ScheduleEvent, event_id)
        if not event or event.owner_user_id != user.id or event.status == "DELETED":
            raise HTTPException(status_code=404, detail="Program kaydı bulunamadı.")
        if event.recurrence_rule != "NONE":
            raise HTTPException(status_code=400, detail="Tekrarlanan programı tamamlamak yerine düzenleyin.")
        if event.status == "COMPLETED":
            return {"ok": True, "status": "COMPLETED"}
        event.status = "COMPLETED"
        event.updated_at = _utcnow_naive()
        session.add(event)
        _cancel_pending_program_reminders(session, event.id)
        realtime_events = _resolve_notifications(session, user_id=user.id, notice_type="PROGRAM_REMINDER", related_type="schedule_event", related_id=event.id)
        realtime_events.append(_record_program_realtime_event(session, user.id, "PROGRAM_COMPLETED", event.id))
        session.commit()
    for realtime_event in realtime_events:
        on_loop(_publish_realtime_event, realtime_event)
    return {"ok": True, "status": "COMPLETED"}


@router.delete("/schedule/{event_id}")
def mobile_delete_schedule(event_id: int, user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        event = session.get(ScheduleEvent, event_id)
        if not event or event.owner_user_id != user.id or event.status == "DELETED":
            raise HTTPException(status_code=404, detail="Program kaydı bulunamadı.")
        event.status = "DELETED"
        event.updated_at = datetime.utcnow()
        session.add(event)
        _cancel_pending_program_reminders(session, event.id)
        realtime_events = _resolve_notifications(session, user_id=user.id, notice_type="PROGRAM_REMINDER", related_type="schedule_event", related_id=event.id)
        realtime_events.append(_record_program_realtime_event(session, user.id, "PROGRAM_DELETED", event.id))
        session.commit()
    for realtime_event in realtime_events:
        on_loop(_publish_realtime_event, realtime_event)
    return {"ok": True}



@router.put("/patients/{patient_id}/teeth/{tooth_number}/surfaces/{surface_name}")
def mobile_update_tooth_surface(
    patient_id: int,
    tooth_number: str,
    surface_name: str,
    payload: MobileSurfaceUpdate,
    user: User = Depends(_mobile_user),
):
    """Update one clinical surface without changing the whole-tooth observation."""
    if not _valid_fdi_tooth_number(tooth_number):
        raise HTTPException(status_code=422, detail="Geçersiz FDI diş numarası.")
    if surface_name not in {"OCCLUSAL", "INCISAL", "MESIAL", "DISTAL", "BUCCAL", "LINGUAL"}:
        raise HTTPException(status_code=422, detail="Geçersiz diş yüzeyi.")
    if payload.status not in {"HEALTHY", "CARIES", "FILLING", "CROWN", "ROOT_CANAL", "EXTRACTED", "IMPLANT", "OTHER"}:
        raise HTTPException(status_code=422, detail="Geçersiz diş durumu.")
    if payload.note is not None and len(payload.note) > 2000:
        raise HTTPException(status_code=422, detail="Yüzey notu 2000 karakteri aşamaz.")
    with Session(engine, expire_on_commit=False) as session:
        patient = session.get(Patient, patient_id)
        if not patient or patient.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
        surface = session.exec(select(ToothSurfaceStatus).where(
            ToothSurfaceStatus.patient_id == patient_id,
            ToothSurfaceStatus.tooth_number == tooth_number,
            ToothSurfaceStatus.surface == surface_name,
        )).first()
        note = payload.note.strip() if payload.note else None
        if surface:
            surface.status, surface.note, surface.updated_at = payload.status, note, datetime.utcnow()
        else:
            session.add(ToothSurfaceStatus(patient_id=patient_id, tooth_number=tooth_number,
                surface=surface_name, status=payload.status, note=note))
        realtime = _record_realtime_event(session, user.id, "TOOTH_UPDATED", "patient", patient_id,
            {"patient_id": patient_id, "tooth_number": tooth_number, "surface": surface_name, "surface_status": payload.status})
        session.commit()
        on_loop(_publish_realtime_event, realtime)
        return {"ok": True, "tooth_number": tooth_number, "surface": surface_name, "status": payload.status}


@router.post("/patients/{patient_id}/teeth/{tooth_number}")
def mobile_update_tooth(
    patient_id: int,
    tooth_number: str,
    payload: MobileToothUpdate,
    user: User = Depends(_mobile_user),
):
    if not _valid_fdi_tooth_number(tooth_number):
        raise HTTPException(status_code=422, detail="Geçersiz FDI diş numarası.")
    if payload.note is not None and len(payload.note) > 2000:
        raise HTTPException(status_code=422, detail="Diş notu 2000 karakteri aşamaz.")
    allowed_statuses = {"HEALTHY","CARIES","FILLING","CROWN","ROOT_CANAL","EXTRACTED","IMPLANT","OTHER"}
    allowed_surfaces = {"OCCLUSAL","INCISAL","MESIAL","DISTAL","BUCCAL","LINGUAL"}
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Geçersiz diş durumu.")
    if payload.surface and payload.surface not in allowed_surfaces:
        raise HTTPException(status_code=422, detail="Geçersiz diş yüzeyi.")
    if payload.surfaces is not None and (len(payload.surfaces) > 6 or len(set(payload.surfaces)) != len(payload.surfaces) or any(surface not in allowed_surfaces for surface in payload.surfaces)):
        raise HTTPException(status_code=422, detail="Geçersiz veya tekrarlanan diş yüzeyi.")
    if payload.surface and payload.surfaces is not None:
        raise HTTPException(status_code=422, detail="Tekil ve çoklu yüzey birlikte gönderilemez.")
    requested_surfaces = payload.surfaces if payload.surfaces is not None else ([payload.surface] if payload.surface else [])
    with Session(engine, expire_on_commit=False) as session:
        patient = session.get(Patient, patient_id)
        if not patient or patient.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
        note = payload.note.strip() if payload.note else None
        tooth = session.exec(select(ToothStatus).where(
            ToothStatus.patient_id == patient_id,
            ToothStatus.tooth_number == tooth_number,
        )).first()
        if tooth:
            tooth.status, tooth.note, tooth.updated_at = payload.status, note, datetime.utcnow()
        else:
            session.add(ToothStatus(patient_id=patient_id,tooth_number=tooth_number,status=payload.status,note=note))
        for surface_name in requested_surfaces:
            surface = session.exec(select(ToothSurfaceStatus).where(
                ToothSurfaceStatus.patient_id == patient_id,
                ToothSurfaceStatus.tooth_number == tooth_number,
                ToothSurfaceStatus.surface == surface_name,
            )).first()
            if surface:
                surface.status, surface.note, surface.updated_at = payload.status, note, datetime.utcnow()
            else:
                session.add(ToothSurfaceStatus(patient_id=patient_id,tooth_number=tooth_number,surface=surface_name,status=payload.status,note=note))
        # Tooth chart status describes an observation, not a completed procedure.
        # Completed treatment records must be created via the dedicated treatments API.
        realtime=_record_realtime_event(session,user.id,"TOOTH_UPDATED","patient",patient_id,{"patient_id":patient_id,"tooth_number":tooth_number,"status":payload.status,"surface":payload.surface,"surfaces":requested_surfaces,"note":note})
        session.commit(); on_loop(_publish_realtime_event,realtime)
        return {"ok": True, "tooth_number": tooth_number, "status": payload.status, "surface": payload.surface, "surfaces": requested_surfaces}


class MobilePatientEdit(BaseModel):
    first_name: str
    last_name: str
    phone: Optional[str] = None
    birth_date: Optional[str] = None
    tc_kimlik_no: Optional[str] = None
    address: Optional[str] = None
    chief_complaint: Optional[str] = None
    expected_revision: Optional[str] = None


@router.put("/patients/{patient_id}")
def mobile_edit_patient(patient_id: int, payload: MobilePatientEdit, user: User = Depends(_mobile_user)):
    first_name, last_name = payload.first_name.strip(), payload.last_name.strip()
    phone = payload.phone.strip() if payload.phone else None
    if not first_name or not last_name:
        raise HTTPException(status_code=422, detail="Ad ve soyad zorunludur.")
    if phone and (not phone.isdigit() or len(phone) != 11 or not phone.startswith("05")):
        raise HTTPException(status_code=422, detail="Telefon 05 ile başlamalı ve 11 rakam olmalıdır.")
    if payload.expected_revision is not None and not re.fullmatch(r"[0-9a-f]{64}", payload.expected_revision):
        raise HTTPException(status_code=422, detail="Hasta kayıt sürümü geçersiz.")
    age = None
    if payload.birth_date:
        try:
            birth = datetime.strptime(payload.birth_date, "%Y-%m-%d").date()
            today = _utcnow_naive().date()
            if birth > today:
                raise ValueError()
            age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        except ValueError:
            raise HTTPException(status_code=422, detail="Doğum tarihi geçersiz.")
    with Session(engine, expire_on_commit=False) as session:
        patient_query = select(Patient).where(Patient.id == patient_id)
        if engine.dialect.name == "postgresql":
            patient_query = patient_query.with_for_update()
        patient = session.exec(patient_query).first()
        if not patient or patient.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
        profile = session.exec(select(PatientProfile).where(PatientProfile.patient_id == patient_id)).first()
        if payload.expected_revision is not None and not hmac.compare_digest(
            _patient_edit_revision(patient, profile), payload.expected_revision
        ):
            raise HTTPException(
                status_code=409,
                detail="Hasta bilgileri başka bir oturumda güncellendi. Güncel kaydı yükleyip değişikliklerinizi yeniden uygulayın.",
            )
        patient.first_name, patient.last_name = first_name, last_name
        patient.phone, patient.birth_date, patient.age = phone, payload.birth_date or None, age
        patient.tc_kimlik_no = payload.tc_kimlik_no.strip() if payload.tc_kimlik_no else None
        patient.chief_complaint = payload.chief_complaint.strip() if payload.chief_complaint else None
        if not profile:
            profile = PatientProfile(patient_id=patient_id)
        profile.address = payload.address.strip() if payload.address else None
        session.add(patient)
        session.add(profile)
        events = _record_patient_realtime_events(session, patient, "PATIENT_UPDATED", profile)
        session.commit()
        edit_revision = _patient_edit_revision(patient, profile)
    for event in events:
        on_loop(_publish_realtime_event, event)
    return {"ok": True, "patient": _patient_payload(patient), "edit_revision": edit_revision}


@router.delete("/patients/{patient_id}")
def mobile_delete_patient(patient_id: int, user: User = Depends(_mobile_user)):
    """Mirror the web patient deletion path with owner checks and realtime invalidation."""
    with Session(engine, expire_on_commit=False) as session:
        patient = session.get(Patient, patient_id)
        if not patient or patient.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
        # Never leave clinical history orphaned by deleting a patient with dependent records.
        # Full clinical-data erasure needs a separate audited, transactional workflow.
        dependent_models = (Analysis, Treatment, ToothStatus, ToothSurfaceStatus, PatientMedia, ScheduleEvent, ConsultationCase)
        for model in dependent_models:
            if session.exec(select(model.id).where(model.patient_id == patient_id).limit(1)).first() is not None:
                raise HTTPException(status_code=409, detail="Hastanın ilişkili klinik kayıtları var. Güvenli silme işlemi henüz desteklenmiyor.")
        events = _record_patient_realtime_events(session, patient, "PATIENT_DELETED")
        profile = session.exec(select(PatientProfile).where(PatientProfile.patient_id == patient_id)).first()
        if profile:
            session.delete(profile)
        session.delete(patient)
        session.commit()
    for event in events:
        on_loop(_publish_realtime_event, event)
    return {"ok": True, "patient_id": patient_id}


def _valid_fdi_tooth_number(tooth_number: str) -> bool:
    """FDI two-digit adult (11-48) or primary (51-85) tooth identifiers."""
    return len(tooth_number) == 2 and (
        (tooth_number[0] in "1234" and tooth_number[1] in "12345678")
        or (tooth_number[0] in "5678" and tooth_number[1] in "12345")
    )


class MobileTreatmentCreate(BaseModel):
    treatment_name: str
    tooth_number: Optional[str] = None
    treatment_date: Optional[str] = None
    material: Optional[str] = None
    doctor_note: Optional[str] = None
    result: Optional[str] = None
    request_key: Optional[str] = None
    expected_revision: Optional[str] = None


_TREATMENT_REQUEST_KEY = re.compile(r"^[A-Za-z0-9_-]{16,80}$")
_TREATMENT_REVISION = re.compile(r"^[a-f0-9]{64}$")


def _normalize_treatment_payload(payload: MobileTreatmentCreate) -> dict:
    name = (payload.treatment_name or "").strip()
    if not name or len(name) > 200:
        raise HTTPException(status_code=422, detail="Tedavi adı 1-200 karakter olmalıdır.")
    treatment_date = (payload.treatment_date or "").strip() or None
    if treatment_date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", treatment_date):
            raise HTTPException(status_code=422, detail="Tedavi tarihi YYYY-AA-GG biçiminde olmalıdır.")
        try:
            datetime.strptime(treatment_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Tedavi tarihi YYYY-AA-GG biçiminde olmalıdır.")
    tooth = (payload.tooth_number or "").strip() or None
    if tooth and not _valid_fdi_tooth_number(tooth):
        raise HTTPException(status_code=422, detail="Geçerli FDI diş numarası girin.")
    if payload.expected_revision is not None and not _TREATMENT_REVISION.fullmatch(payload.expected_revision):
        raise HTTPException(status_code=422, detail="Tedavi kayıt sürümü geçersiz.")
    return {
        "treatment_name": name,
        "tooth_number": tooth,
        "treatment_date": treatment_date,
        "material": (payload.material or "").strip()[:500] or None,
        "doctor_note": (payload.doctor_note or "").strip()[:4000] or None,
        "result": (payload.result or "").strip()[:1000] or None,
    }


def _treatment_revision(treatment: Treatment) -> str:
    value = {
        "id": treatment.id,
        "patient_id": treatment.patient_id,
        "treatment_name": treatment.treatment_name,
        "tooth_number": treatment.tooth_number,
        "treatment_date": treatment.treatment_date,
        "material": treatment.material,
        "doctor_note": treatment.doctor_note,
        "result": treatment.result,
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _treatment_receipt_key(user_id: int, patient_id: int, operation: str, treatment_id: Optional[int], request_key: str) -> str:
    if not _TREATMENT_REQUEST_KEY.fullmatch(request_key or ""):
        raise HTTPException(status_code=422, detail="Geçersiz tedavi işlem anahtarı.")
    raw = f"mobile-treatment:{user_id}:{patient_id}:{operation}:{treatment_id or 0}:{request_key}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _treatment_payload_hash(patient_id: int, operation: str, treatment_id: Optional[int], expected_revision: Optional[str], values: dict) -> str:
    payload = [patient_id, operation, treatment_id, expected_revision, values]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _lock_treatment_receipt(session: Session, receipt_key: Optional[str]) -> None:
    if receipt_key and session.get_bind().dialect.name == "postgresql":
        slot = int.from_bytes(hashlib.sha256(("treatment-receipt:" + receipt_key).encode()).digest()[:8], "big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:slot)"), {"slot": slot})


def _existing_treatment_receipt(session: Session, user: User, patient_id: int, receipt_key: str, digest: str):
    receipt = session.exec(select(WorkJob).where(
        WorkJob.owner_user_id == user.id,
        WorkJob.resource_id == patient_id,
        WorkJob.resource_type == "PATIENT",
        WorkJob.kind == "TREATMENT_RECEIPT",
        WorkJob.dedupe_key == receipt_key,
    )).first()
    if receipt is None:
        return None
    if receipt.source_hash != digest:
        raise HTTPException(status_code=409, detail="Bu tedavi işlem anahtarı farklı bilgilerle kullanılmış.")
    try:
        saved = json.loads(receipt.payload_json or "{}")
        treatment_id = int(saved["treatment_id"])
        if int(saved.get("patient_id", 0)) != patient_id:
            raise ValueError("receipt patient mismatch")
        revision = saved["edit_revision"]
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=409, detail="Tedavi işlem fişi doğrulanamadı.")
    treatment = session.get(Treatment, treatment_id)
    if not treatment or treatment.patient_id != patient_id or not _TREATMENT_REVISION.fullmatch(str(revision)):
        raise HTTPException(status_code=409, detail="Önceki tedavi işlemi artık doğrulanamıyor; geçmişi yenileyin.")
    return {"ok": True, "treatment_id": treatment_id, "edit_revision": revision, "operation": saved.get("operation"), "replayed": True}


def _store_treatment_receipt(session: Session, user: User, patient_id: int, treatment: Treatment, receipt_key: Optional[str], digest: Optional[str], operation: str) -> None:
    if not receipt_key or not digest:
        return
    session.add(WorkJob(
        owner_user_id=user.id,
        resource_id=patient_id,
        resource_type="PATIENT",
        kind="TREATMENT_RECEIPT",
        source_hash=digest,
        dedupe_key=receipt_key,
        payload_json=json.dumps({
            "patient_id": patient_id,
            "treatment_id": treatment.id,
            "edit_revision": _treatment_revision(treatment),
            "operation": operation,
        }, sort_keys=True),
        status="DONE",
    ))


@router.post("/patients/{patient_id}/treatments", status_code=201)
def mobile_create_treatment(patient_id: int, payload: MobileTreatmentCreate, user: User = Depends(_mobile_user)):
    values = _normalize_treatment_payload(payload)
    receipt_key = _treatment_receipt_key(user.id, patient_id, "CREATE", None, payload.request_key) if payload.request_key is not None else None
    digest = _treatment_payload_hash(patient_id, "CREATE", None, None, values) if receipt_key else None
    with Session(engine, expire_on_commit=False) as session:
        _lock_treatment_receipt(session, receipt_key)
        patient = session.get(Patient, patient_id)
        if not patient or patient.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
        if receipt_key:
            existing = _existing_treatment_receipt(session, user, patient_id, receipt_key, digest)
            if existing:
                if existing.get("operation") != "CREATE":
                    raise HTTPException(status_code=409, detail="Tedavi işlem fişi farklı bir işleme ait.")
                return existing
        treatment = Treatment(patient_id=patient_id, **values)
        session.add(treatment)
        session.flush()
        revision = _treatment_revision(treatment)
        _store_treatment_receipt(session, user, patient_id, treatment, receipt_key, digest, "CREATE")
        event = _record_realtime_event(session, user.id, "TREATMENT_CREATED", "patient", patient_id,
                                       {"patient_id": patient_id, "treatment_id": treatment.id})
        session.commit()
        treatment_id = treatment.id
    on_loop(_publish_realtime_event, event)
    return {"ok": True, "treatment_id": treatment_id, "edit_revision": revision, "replayed": False}


@router.put("/patients/{patient_id}/treatments/{treatment_id}")
def mobile_update_treatment(patient_id: int, treatment_id: int, payload: MobileTreatmentCreate, user: User = Depends(_mobile_user)):
    values = _normalize_treatment_payload(payload)
    receipt_key = _treatment_receipt_key(user.id, patient_id, "UPDATE", treatment_id, payload.request_key) if payload.request_key is not None else None
    digest = _treatment_payload_hash(patient_id, "UPDATE", treatment_id, payload.expected_revision, values) if receipt_key else None
    with Session(engine, expire_on_commit=False) as session:
        _lock_treatment_receipt(session, receipt_key)
        patient = session.exec(select(Patient).where(Patient.id == patient_id).with_for_update()).first()
        if not patient or patient.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
        if receipt_key:
            existing = _existing_treatment_receipt(session, user, patient_id, receipt_key, digest)
            if existing:
                if existing.get("operation") != "UPDATE" or existing["treatment_id"] != treatment_id:
                    raise HTTPException(status_code=409, detail="Tedavi işlem fişi farklı bir kayda ait.")
                return existing
        treatment = session.exec(select(Treatment).where(
            Treatment.id == treatment_id, Treatment.patient_id == patient_id
        ).with_for_update().execution_options(populate_existing=True)).first()
        if not treatment:
            raise HTTPException(status_code=404, detail="Tedavi bulunamadı.")
        if payload.expected_revision and _treatment_revision(treatment) != payload.expected_revision:
            raise HTTPException(status_code=409, detail="Tedavi başka bir oturumda güncellendi. Güncel geçmişi yükleyip değişikliklerinizi yeniden uygulayın.")
        for key, value in values.items():
            setattr(treatment, key, value)
        session.add(treatment)
        session.flush()
        revision = _treatment_revision(treatment)
        _store_treatment_receipt(session, user, patient_id, treatment, receipt_key, digest, "UPDATE")
        event = _record_realtime_event(session, user.id, "TREATMENT_UPDATED", "patient", patient_id,
                                       {"patient_id": patient_id, "treatment_id": treatment_id})
        session.commit()
    on_loop(_publish_realtime_event, event)
    return {"ok": True, "treatment_id": treatment_id, "edit_revision": revision, "replayed": False}


@router.get("/patients/{patient_id}")
def mobile_patient_detail(
    patient_id: int,
    user: User = Depends(_mobile_user),
):
    with Session(engine, expire_on_commit=False) as session:
        patient = session.get(Patient, patient_id)
        if not patient or patient.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")

        teeth = session.exec(
            select(ToothStatus)
            .where(ToothStatus.patient_id == patient_id)
            .order_by(ToothStatus.tooth_number)
        ).all()
        surfaces = session.exec(
            select(ToothSurfaceStatus)
            .where(ToothSurfaceStatus.patient_id == patient_id)
            .order_by(ToothSurfaceStatus.tooth_number, ToothSurfaceStatus.surface)
        ).all()
        treatments = session.exec(
            select(Treatment)
            .where(Treatment.patient_id == patient_id)
            .order_by(Treatment.created_at.desc())
        ).all()
        media = session.exec(
            select(PatientMedia)
            .where(
                (PatientMedia.patient_id == patient_id)
                & (PatientMedia.owner_user_id == user.id)
            )
            .order_by(PatientMedia.id.desc())
            .limit(20)
        ).all()

        profile = session.exec(select(PatientProfile).where(PatientProfile.patient_id == patient_id)).first()
        return {
            "patient": {**_patient_payload(patient), "tc_kimlik_no": patient.tc_kimlik_no, "address": profile.address if profile else None},
            "edit_revision": _patient_edit_revision(patient, profile),
            "teeth": [
                {
                    "id": t.id,
                    "tooth_number": t.tooth_number,
                    "status": t.status,
                    "note": t.note,
                    "updated_at": t.updated_at,
                }
                for t in teeth
            ],
            "surfaces": [
                {
                    "id": s.id,
                    "tooth_number": s.tooth_number,
                    "surface": s.surface,
                    "status": s.status,
                    "note": s.note,
                    "updated_at": s.updated_at,
                }
                for s in surfaces
            ],
            "treatments": [
                {
                    "id": t.id,
                    "tooth_number": t.tooth_number,
                    "treatment_name": t.treatment_name,
                    "treatment_date": t.treatment_date,
                    "material": t.material,
                    "doctor_note": t.doctor_note,
                    "result": t.result,
                    "edit_revision": _treatment_revision(t),
                    "analysis_id": t.analysis_id,
                    "created_at": t.created_at,
                }
                for t in treatments
            ],
            "media": [
                {
                    "id": m.id,
                    "original_filename": m.original_filename,
                    "media_type": m.media_type,
                    "tooth_number": m.tooth_number,
                    "note": m.note,
                    "uploaded_at": m.uploaded_at,
                }
                for m in media
            ],
        }


@router.get("/patients/{patient_id}/tooth-chart/focus")
def mobile_patient_tooth_chart_focus(
    patient_id: int,
    user: User = Depends(_mobile_user),
):
    """Return the same latest-analysis tooth that the web chart opens initially.

    Kept separate from patient detail so ordinary profile reads do not pay for
    this chart-only query.
    """
    valid_tooth_numbers = (
        "18", "17", "16", "15", "14", "13", "12", "11",
        "21", "22", "23", "24", "25", "26", "27", "28",
        "48", "47", "46", "45", "44", "43", "42", "41",
        "31", "32", "33", "34", "35", "36", "37", "38",
        "55", "54", "53", "52", "51", "61", "62", "63", "64", "65",
        "85", "84", "83", "82", "81", "71", "72", "73", "74", "75",
    )
    with Session(engine, expire_on_commit=False) as session:
        patient = session.get(Patient, patient_id)
        if not patient or patient.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
        latest_tooth = session.exec(
            select(Analysis.tooth_number)
            .where(
                Analysis.patient_id == patient_id,
                Analysis.status.in_(["AI_ANALYZED", "AI_FINAL", "VISION_READY"]),
                Analysis.tooth_number.in_(valid_tooth_numbers),
            )
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .limit(1)
        ).first()
        return {"latest_analysis_tooth": latest_tooth}


# Native feature adapters. These reuse the production handlers where possible.
def _mobile_request(token: str, method: str = "POST", path: str = "/api/mobile/v1") -> Request:
    return Request({
        "type": "http", "http_version": "1.1", "method": method, "scheme": "https",
        "path": path, "raw_path": path.encode(), "query_string": b"",
        "headers": [(b"cookie", f"{SESSION_COOKIE}={token}".encode()),
                    (b"accept", b"application/json"), (b"x-requested-with", b"XMLHttpRequest")],
        "client": ("mobile", 0), "server": ("dentalai.tr", 443),
    })

def _response_json(response):
    if isinstance(response, JSONResponse):
        try:
            return json.loads(response.body.decode("utf-8"))
        except Exception:
            return {"ok": False, "error": "Sunucu yanıtı okunamadı."}
    return response

class MobilePushRegistration(BaseModel):
    device_id: str
    expo_push_token: str
    platform: str


@router.post("/push/devices")
def register_mobile_push_device(payload: MobilePushRegistration, user: User = Depends(_mobile_user)):
    device_id = payload.device_id.strip()
    token = payload.expo_push_token.strip()
    platform = payload.platform.strip().lower()
    if not (1 <= len(device_id) <= 128) or platform not in {"android", "ios"}:
        raise HTTPException(status_code=422, detail="Geçersiz cihaz bilgisi.")
    if len(token) > 256 or not (token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")) or not token.endswith("]"):
        raise HTTPException(status_code=422, detail="Geçersiz Expo push token.")
    with Session(engine, expire_on_commit=False) as session:
        # Reject cross-account token conflicts; a client-supplied device ID is not proof of ownership.
        other_owner = session.exec(select(MobilePushDevice).where(
            MobilePushDevice.expo_push_token == token,
            MobilePushDevice.user_id != user.id,
        )).first()
        if other_owner:
            raise HTTPException(status_code=409, detail="Cihaz bildirimi önceki hesaptan kaldırılmalı.")
        previous = session.exec(select(MobilePushDevice).where(
            (MobilePushDevice.user_id == user.id) & (
                (MobilePushDevice.device_id == device_id) | (MobilePushDevice.expo_push_token == token)
            )
        )).all()
        for item in previous:
            session.delete(item)
        session.flush()
        session.add(MobilePushDevice(user_id=user.id, device_id=device_id,
                                     expo_push_token=token, platform=platform))
        session.commit()
    return {"ok": True}


@router.delete("/push/devices/{device_id}")
def unregister_mobile_push_device(device_id: str, user: User = Depends(_mobile_user)):
    if len(device_id) > 128:
        raise HTTPException(status_code=422, detail="Geçersiz cihaz.")
    with Session(engine, expire_on_commit=False) as session:
        for item in session.exec(select(MobilePushDevice).where(
            MobilePushDevice.user_id == user.id, MobilePushDevice.device_id == device_id
        )).all():
            session.delete(item)
        session.commit()
    return {"ok": True}


@router.get("/notifications")
def mobile_notifications(user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        rows = session.exec(select(AdminNotice).where(
            AdminNotice.user_id == user.id, AdminNotice.status == "ACTIVE"
        ).order_by(AdminNotice.created_at.desc()).limit(20)).all()
        return {"unread_count": sum(not n.is_read for n in rows), "unread": sum(not n.is_read for n in rows),
                "notifications": [{"id":n.id,"title":n.title,"message":n.message,
                "notice_type":n.notice_type,"target_url":n.target_url,
                "is_read":bool(n.is_read),"read_at":n.read_at,"created_at":n.created_at} for n in rows],
                "items": [{"id":n.id,"title":n.title,"message":n.message,
                "notice_type":n.notice_type,"target_url":n.target_url,
                "read_at":n.read_at,"created_at":n.created_at} for n in rows]}

@router.post("/notifications/{notice_id}/read")
def mobile_notification_read(notice_id:int,user:User=Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        n=session.get(AdminNotice,notice_id)
        if not n or n.user_id!=user.id or n.status!="ACTIVE":
            raise HTTPException(status_code=404,detail="Bildirim bulunamadı.")
        n.is_read=True;n.read_at=datetime.utcnow();session.add(n);session.commit()
        return {"ok":True}

@router.get("/consultations/experts")
def mobile_experts(user:User=Depends(_mobile_user),specialty:str=Query("",max_length=100),available:bool=False):
    with Session(engine,expire_on_commit=False) as session:
        q=select(ExpertProfile).where(
            ExpertProfile.user_id!=user.id,ExpertProfile.application_status=="APPROVED",
            ExpertProfile.verification_status=="VERIFIED",ExpertProfile.specialty_verified==True,
            ExpertProfile.credential_document_path!=None,ExpertProfile.phone!=None)
        if specialty:q=q.where(ExpertProfile.specialty==specialty)
        if available:q=q.where(ExpertProfile.availability=="AVAILABLE")
        rows=session.exec(q.order_by(ExpertProfile.updated_at.desc()).limit(50)).all()
        items=[]
        for p in rows:
            u=session.get(User,p.user_id)
            if u: items.append({"id":u.id,"display_name":u.display_name,"specialty":p.specialty,
                "academic_title":p.academic_title,"institution":p.institution,
                "availability":p.availability,"consultation_price":p.consultation_price})
        return {"items":items}

@router.get("/consultations")
def mobile_consultations(user:User=Depends(_mobile_user), before:Optional[int]=Query(None,ge=1)):
    with Session(engine,expire_on_commit=False) as session:
        scope=(ConsultationCase.requester_user_id==user.id)|(ConsultationCase.expert_user_id==user.id)
        query=select(ConsultationCase).where(scope)
        hidden = select(ConsultationInboxState.case_id).where(
            ConsultationInboxState.user_id == user.id, ConsultationInboxState.deleted_at != None)
        query = query.where(~ConsultationCase.id.in_(hidden))
        if before is not None:
            anchor=select(ConsultationCase.requested_at).where(ConsultationCase.id==before,scope).scalar_subquery()
            query=query.where((ConsultationCase.requested_at<anchor)|((ConsultationCase.requested_at==anchor)&(ConsultationCase.id<before)))
        page=session.exec(query.order_by(ConsultationCase.requested_at.desc(),ConsultationCase.id.desc()).limit(51)).all()
        cases=page[:50]
        case_ids=[c.id for c in cases]
        other_ids={c.expert_user_id if c.requester_user_id==user.id else c.requester_user_id for c in cases}
        peers={u.id:u for u in session.exec(select(User).where(User.id.in_(other_ids))).all()} if other_ids else {}
        inbox_states={state.case_id:state for state in session.exec(select(ConsultationInboxState).where(
            ConsultationInboxState.case_id.in_(case_ids),ConsultationInboxState.user_id==user.id
        )).all()} if case_ids else {}
        last_by_case={}
        if case_ids:
            ranked=select(ConsultationMessage.id,func.row_number().over(
                partition_by=ConsultationMessage.case_id,
                order_by=(ConsultationMessage.created_at.desc(),ConsultationMessage.id.desc())
            ).label("position")).where(ConsultationMessage.case_id.in_(case_ids)).subquery()
            latest=session.exec(select(ConsultationMessage).join(ranked,ranked.c.id==ConsultationMessage.id).where(ranked.c.position==1)).all()
            last_by_case={message.case_id:message for message in latest}
        unread_by_case={}
        if case_ids:
            read_boundary={cid:(inbox_states[cid].last_read_at if cid in inbox_states else None) for cid in case_ids}
            for cid in case_ids:
                boundary=read_boundary[cid]
                if boundary is None:
                    continue
                unread_by_case[cid]=0
            # Cases never opened have no read cursor: all peer messages are unread.
            never_read=[cid for cid in case_ids if read_boundary[cid] is None]
            if never_read:
                new_rows=session.exec(select(ConsultationMessage.case_id,func.count(ConsultationMessage.id)).where(
                    ConsultationMessage.case_id.in_(never_read),ConsultationMessage.sender_user_id!=user.id
                ).group_by(ConsultationMessage.case_id)).all()
                unread_by_case.update({cid:int(count) for cid,count in new_rows})
            # One grouped query for cases with an existing read cursor.
            active_ids=[cid for cid in case_ids if read_boundary[cid] is not None]
            if active_ids:
                unread_rows=session.exec(select(ConsultationMessage.case_id,func.count(ConsultationMessage.id)).where(
                    ConsultationMessage.case_id.in_(active_ids),
                    ConsultationMessage.sender_user_id!=user.id,
                    ConsultationMessage.created_at>func.coalesce(
                        select(ConsultationInboxState.last_read_at).where(
                            ConsultationInboxState.case_id==ConsultationMessage.case_id,
                            ConsultationInboxState.user_id==user.id
                        ).scalar_subquery(),ConsultationMessage.created_at
                    )
                ).group_by(ConsultationMessage.case_id)).all()
                unread_by_case.update({cid:int(count) for cid,count in unread_rows})
        items=[]
        for c in cases:
            other_id=c.expert_user_id if c.requester_user_id==user.id else c.requester_user_id
            other=peers.get(other_id)
            last=None if c.messages_deleted_at is not None else last_by_case.get(c.id)
            items.append({"id":c.id,"status":c.status,"specialty":c.specialty,"tooth_region":c.tooth_region,
                "question":c.question,"requested_at":c.requested_at,"other_user_id":other_id,
                "other_display_name":other.display_name if other else "Kullanıcı",
                "last_message":last.content if last else None,"last_message_at":last.created_at if last else None,
                "messages_deleted_at":c.messages_deleted_at,"unread_count":0 if c.messages_deleted_at is not None else unread_by_case.get(c.id,0)})
        return {"items":items,"next_before":cases[-1].id if len(page)>50 else None}

@router.get("/consultations/{case_id}")
def mobile_consultation(case_id:int,before:Optional[int]=Query(None,ge=1),limit:int=Query(100,ge=1,le=100),user:User=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as session:
        c=session.get(ConsultationCase,case_id)
        if not c or user.id not in {c.requester_user_id,c.expert_user_id}:
            raise HTTPException(status_code=404,detail="Vaka bulunamadı.")
        if c.messages_deleted_at is not None:
            return {"next_before":None,"case":{"id":c.id,"status":c.status,"specialty":c.specialty,
                "messages_deleted_at":c.messages_deleted_at,"expert_user_id":c.expert_user_id,
                "requester_user_id":c.requester_user_id},"messages":[]}
        query=select(ConsultationMessage).where(ConsultationMessage.case_id==c.id)
        if before is not None:
            query=query.where(ConsultationMessage.id<before)
        page=session.exec(query.order_by(ConsultationMessage.id.desc()).limit(limit+1)).all()
        msgs=list(reversed(page[:limit]))
        next_before=msgs[0].id if len(page)>limit and msgs else None
        return {"next_before":next_before,"case":{"id":c.id,"status":c.status,"specialty":c.specialty,"tooth_region":c.tooth_region,
            "messages_deleted_at":c.messages_deleted_at,"expert_response_deadline":c.expert_response_deadline,
            "requester_decision_deadline":c.requester_decision_deadline,"consultation_start_deadline":c.consultation_start_deadline,
            "clinical_summary":c.clinical_summary,"requester_opinion":c.requester_opinion,"question":c.question,
            "requested_at":c.requested_at,"expert_user_id":c.expert_user_id,"requester_user_id":c.requester_user_id,**_mobile_chat_context(session,c,user)},
            "messages":[{"id":m.id,"sender_user_id":m.sender_user_id,"message_type":m.message_type,
            "content":m.content,"reply_to_message_id":m.reply_to_message_id,"created_at":m.created_at,"has_media":bool(m.media_path)} for m in msgs]}

class MobileConsultationReadRequest(BaseModel):
    through_id: int


@router.post("/consultations/{case_id}/read")
def mobile_consultation_mark_read(case_id:int, body:MobileConsultationReadRequest,
                                  background_tasks:BackgroundTasks,user:User=Depends(_mobile_user)):
    if body.through_id <= 0:
        raise HTTPException(status_code=422,detail="Geçersiz mesaj kimliği.")
    # Reuse the web read-receipt implementation so both clients share one cursor.
    receipt=_socket_case_authorized(user.id,case_id,mark_read=True,through_id=body.through_id)
    if not receipt:
        raise HTTPException(status_code=404,detail="Görüşme bulunamadı.")
    for event in receipt["events"]:
        background_tasks.add_task(_publish_realtime_event,event)
    return {"ok":True,"through_id":receipt["through_id"],"at":receipt["at"]}


@router.get("/academic/courses")
def mobile_academic_courses(user:User=Depends(_mobile_user), before:Optional[int]=Query(None,ge=1)):
    with Session(engine,expire_on_commit=False) as session:
        query=select(StudyCourse).where(StudyCourse.owner_user_id==user.id)
        if before is not None:
            anchor=select(StudyCourse.created_at).where(StudyCourse.id==before,StudyCourse.owner_user_id==user.id).scalar_subquery()
            query=query.where((StudyCourse.created_at<anchor)|((StudyCourse.created_at==anchor)&(StudyCourse.id<before)))
        page=session.exec(query.order_by(StudyCourse.created_at.desc(),StudyCourse.id.desc()).limit(51)).all()
        rows=page[:50]
        course_ids=[c.id for c in rows]
        counts=dict(session.exec(select(StudyMaterial.course_id,func.count(StudyMaterial.id)).where(
            StudyMaterial.course_id.in_(course_ids),StudyMaterial.owner_user_id==user.id
        ).group_by(StudyMaterial.course_id)).all()) if course_ids else {}
        return {"items":[{"id":c.id,"title":c.title,"description":getattr(c,"description",None),
            "updated_at":getattr(c,"updated_at",c.created_at),"created_at":c.created_at,"material_count":counts.get(c.id,0)} for c in rows],"next_before":rows[-1].id if len(page)>50 else None}

@router.get("/academic/courses/{course_id}/messages")
def mobile_academic_messages(course_id:int,user:User=Depends(_mobile_user), before:Optional[int]=Query(None,ge=1)):
    with Session(engine,expire_on_commit=False) as session:
        course=session.get(StudyCourse,course_id)
        if not course or course.owner_user_id!=user.id:
            raise HTTPException(status_code=404,detail="Ders bulunamadı.")
        query=select(StudyChatMessage).where(StudyChatMessage.course_id==course_id,StudyChatMessage.owner_user_id==user.id)
        if before is not None:
            query=query.where(StudyChatMessage.id<before)
        page=session.exec(query.order_by(StudyChatMessage.id.desc()).limit(101)).all()
        rows=page[:100]
        return {"items":[{"id":m.id,"role":m.role,"content":m.content,"created_at":m.created_at} for m in reversed(rows)],"next_before":rows[-1].id if len(page)>100 else None}

_PATIENT_MEDIA_RECEIPT_KIND = "PATIENT_MEDIA_RECEIPT"


def _patient_media_receipt_key(user_id: int, patient_id: int, request_key: str) -> str:
    if not _PATIENT_MEDIA_REQUEST_KEY.fullmatch(request_key or ""):
        raise HTTPException(status_code=422, detail="Geçersiz klinik görüntü işlem anahtarı.")
    return hashlib.sha256(
        f"mobile-patient-media:{user_id}:{patient_id}:{request_key}".encode()
    ).hexdigest()


def _patient_media_payload_hash(file_hash: str, media_type: str, tooth_number: Optional[str],
                                note: Optional[str], original_name: str) -> str:
    payload = [file_hash, media_type, tooth_number, note, original_name]
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode()).hexdigest()


def _lock_patient_media_receipt(session: Session, receipt_key: Optional[str]) -> None:
    if receipt_key and session.get_bind().dialect.name == "postgresql":
        slot = int.from_bytes(
            hashlib.sha256(("patient-media-receipt:" + receipt_key).encode()).digest()[:8],
            "big", signed=True,
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:slot)"), {"slot": slot})


def _patient_media_result(media: PatientMedia, replayed: bool = False) -> dict:
    return {
        "media": {
            "id": media.id,
            "original_filename": media.original_filename,
            "media_type": media.media_type,
            "tooth_number": media.tooth_number,
            "note": media.note,
            "uploaded_at": media.uploaded_at,
        },
        "replayed": replayed,
    }


def _find_patient_media_receipt(session: Session, user: User, patient_id: int,
                                receipt_key: str, digest: Optional[str] = None,
                                legacy_digest: Optional[str] = None, key: Optional[bytes] = None):
    from app.patient_media_receipts import (
        PatientMediaReceiptConflict, PatientMediaReceiptCorrupt, upgrade_legacy_receipt,
    )

    receipt = session.exec(select(WorkJob).where(
        WorkJob.owner_user_id == user.id,
        WorkJob.resource_id == patient_id,
        WorkJob.resource_type == "PATIENT",
        WorkJob.kind == _PATIENT_MEDIA_RECEIPT_KIND,
        WorkJob.dedupe_key == receipt_key,
    )).first()
    if receipt is None:
        return None
    if key is None:
        raise HTTPException(status_code=503, detail="Klinik görüntü yükleme kurtarma anahtarı yapılandırılmamış.")
    try:
        upgraded = upgrade_legacy_receipt(
            receipt, digest=digest, legacy_digest=legacy_digest, key=key,
            owner_id=user.id, patient_id=patient_id,
        )
    except PatientMediaReceiptConflict as exc:
        raise HTTPException(status_code=409, detail="Bu klinik görüntü işlem anahtarı farklı bir dosya veya bilgilerle kullanılmış.") from exc
    except PatientMediaReceiptCorrupt as exc:
        raise HTTPException(status_code=409, detail="Klinik görüntü işlem fişi doğrulanamadı.") from exc
    if upgraded:
        session.add(receipt)
    try:
        saved = json.loads(receipt.payload_json or "{}")
        media_id = int(saved["media_id"])
        if int(saved.get("patient_id", 0)) != patient_id:
            raise ValueError("receipt patient mismatch")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=409, detail="Klinik görüntü işlem fişi doğrulanamadı.")
    media = session.get(PatientMedia, media_id)
    if not media or media.patient_id != patient_id or media.owner_user_id != user.id:
        raise HTTPException(status_code=409, detail="Önceki klinik görüntü kaydı artık galeride yok. Yeni bir işlem anahtarıyla yeniden seçin.")
    return _patient_media_result(media, replayed=True)


def _store_patient_media_receipt(session: Session, user: User, patient_id: int,
                                 media: PatientMedia, receipt_key: str, digest: str,
                                 batch_id: str, file_bytes: int) -> None:
    session.add(WorkJob(
        owner_user_id=user.id,
        resource_id=patient_id,
        resource_type="PATIENT",
        kind=_PATIENT_MEDIA_RECEIPT_KIND,
        source_hash=digest,
        dedupe_key=receipt_key,
        result_ref=batch_id,
        payload_json=json.dumps({
            "patient_id": patient_id, "media_id": media.id,
            "batch_id": batch_id, "file_bytes": file_bytes,
            "fingerprint_version": 1,
        }, sort_keys=True),
        status="DONE",
    ))


def _patient_media_batch_usage(session: Session, user: User, patient_id: int,
                               batch_id: str) -> tuple[int, int]:
    """Read persisted per-file receipts for this patient-scoped upload batch.

    The caller holds the patient row lock, serializing quota admission across
    concurrent uploads for the same patient on PostgreSQL. Replayed receipts
    are returned before this function and therefore never count twice.
    """
    receipts = session.exec(select(WorkJob).where(
        WorkJob.owner_user_id == user.id,
        WorkJob.resource_id == patient_id,
        WorkJob.resource_type == "PATIENT",
        WorkJob.kind == _PATIENT_MEDIA_RECEIPT_KIND,
        WorkJob.result_ref == batch_id,
    )).all()
    total_bytes = 0
    for receipt in receipts:
        try:
            payload = json.loads(receipt.payload_json or "{}")
            if not isinstance(payload, dict):
                raise ValueError("invalid patient media batch payload")
            file_bytes = payload.get("file_bytes")
            if (payload.get("batch_id") != batch_id or
                    payload.get("patient_id") != patient_id or
                    not isinstance(file_bytes, int) or isinstance(file_bytes, bool) or
                    file_bytes < 1 or file_bytes > MAX_PATIENT_MEDIA_FILE_BYTES):
                raise ValueError("invalid patient media batch receipt")
        except (TypeError, ValueError, json.JSONDecodeError):
            raise HTTPException(status_code=409, detail="Klinik görüntü yükleme grubu fişi doğrulanamadı.")
        total_bytes += file_bytes
    return len(receipts), total_bytes


@router.post("/patients/{patient_id}/media")
async def mobile_patient_media_upload(
    patient_id: int,
    image: UploadFile = File(None),
    file: UploadFile = File(None),
    tooth_number: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    media_type: str = Form("PHOTO"),
    request_key: str = Form(...),
    batch_id: str = Form(...),
    user: User = Depends(_mobile_user),
):
    media_type = (media_type or "").strip().upper()
    if media_type not in {"PHOTO", "RADIOGRAPH"}:
        raise HTTPException(status_code=422, detail="Geçersiz klinik görüntü türü.")
    tooth = (tooth_number or "").strip() or None
    if tooth and not _valid_fdi_tooth_number(tooth):
        raise HTTPException(status_code=422, detail="Geçerli FDI diş numarası girin.")
    normalized_note = (note or "").strip() or None
    if normalized_note and len(normalized_note) > 2000:
        raise HTTPException(status_code=422, detail="Klinik not 2000 karakteri aşamaz.")
    receipt_key = _patient_media_receipt_key(user.id, patient_id, request_key)
    from app.patient_media_receipts import encryption_key, keyed_fingerprint, PatientMediaReceiptKeyUnavailable
    try:
        fingerprint_key = encryption_key()
    except PatientMediaReceiptKeyUnavailable as exc:
        raise HTTPException(status_code=503, detail="Klinik görüntü yükleme kurtarma anahtarı yapılandırılmamış.") from exc
    if not _PATIENT_MEDIA_BATCH_ID.fullmatch(batch_id or ""):
        raise HTTPException(status_code=422, detail="Geçersiz klinik görüntü yükleme grubu.")
    image = image or file
    if not image or not image.filename:
        raise HTTPException(status_code=422, detail="Görüntü seçin.")
    raw_original_name = Path(image.filename).name
    ext = Path(raw_original_name).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=422, detail="Desteklenmeyen görüntü formatı.")
    original_name = raw_original_name if len(raw_original_name) <= 255 else raw_original_name[:255 - len(ext)] + ext

    stored = f"patient_{patient_id}_{uuid.uuid4().hex}{ext}"
    destination = Path("uploads") / "patient-media" / stored
    destination.parent.mkdir(parents=True, exist_ok=True)
    persisted = False
    digest = None
    legacy_digest = None
    try:
        file_bytes = _copy_validated_image(image, destination, MOBILE_MAX_PATIENT_MEDIA_BYTES)
        file_digest = hashlib.sha256()
        with destination.open("rb") as saved_file:
            while True:
                chunk = saved_file.read(1024 * 1024)
                if not chunk:
                    break
                file_digest.update(chunk)
        legacy_digest = _patient_media_payload_hash(file_digest.hexdigest(), media_type, tooth, normalized_note, original_name)
        digest = keyed_fingerprint(legacy_digest, fingerprint_key, user.id, patient_id)
        with Session(engine, expire_on_commit=False) as session:
            patient = session.exec(select(Patient).where(
                Patient.id == patient_id, Patient.owner_user_id == user.id
            ).with_for_update()).first()
            if not patient:
                raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
            _lock_patient_media_receipt(session, receipt_key)
            if receipt_key:
                existing = _find_patient_media_receipt(
                    session, user, patient_id, receipt_key, digest,
                    legacy_digest=legacy_digest, key=fingerprint_key,
                )
                if existing:
                    session.commit()
                    destination.unlink(missing_ok=True)
                    return JSONResponse(existing, headers={"Cache-Control": "private, no-store"})
            # The locked patient row makes this cross-request counter atomic across workers.
            batch_count, batch_bytes = _patient_media_batch_usage(session, user, patient_id, batch_id)
            if batch_count >= MAX_PATIENT_MEDIA_FILES:
                raise HTTPException(status_code=413, detail=f"Bir klinik arşiv yükleme grubunda en fazla {MAX_PATIENT_MEDIA_FILES} görüntü olabilir.")
            if batch_bytes + file_bytes > MAX_PATIENT_MEDIA_BATCH_BYTES:
                raise HTTPException(status_code=413, detail="Bir klinik arşiv yükleme grubunun toplamı 96 MiB sınırını aşamaz.")
            persisted = True
            storage_persist_file(destination)
            media = PatientMedia(
                patient_id=patient_id,
                owner_user_id=user.id,
                original_filename=original_name,
                stored_filename=stored,
                file_path=str(destination),
                media_type=media_type,
                tooth_number=tooth,
                note=normalized_note,
            )
            session.add(media)
            session.flush()
            _store_patient_media_receipt(session, user, patient_id, media, receipt_key, digest, batch_id, file_bytes)
            realtime = _record_realtime_event(
                session, user.id, "PATIENT_MEDIA_CREATED", "patient", patient_id,
                {"patient_id": patient_id, "media_id": media.id, "filename": media.original_filename},
            )
            session.commit()
            result = _patient_media_result(media, replayed=False)
    except IntegrityError:
        try:
            if persisted:
                storage_delete(str(destination))
        except Exception:
            logging.exception("Failed to clean duplicate clinical media object: %s", destination)
        destination.unlink(missing_ok=True)
        if receipt_key and digest:
            with Session(engine, expire_on_commit=False) as session:
                patient = session.exec(select(Patient).where(
                    Patient.id == patient_id, Patient.owner_user_id == user.id
                )).first()
                if patient:
                    existing = _find_patient_media_receipt(
                        session, user, patient_id, receipt_key, digest,
                        legacy_digest=legacy_digest, key=fingerprint_key,
                    )
                    if existing:
                        session.commit()
                        return JSONResponse(existing, headers={"Cache-Control": "private, no-store"})
        raise HTTPException(status_code=409, detail="Klinik görüntü işlemi aynı anda tamamlandı. Galeriyi yenileyip işlem fişini doğrulayın.")
    except Exception:
        try:
            if persisted:
                storage_delete(str(destination))
        except Exception:
            logging.exception("Failed to clean orphan clinical media upload: %s", destination)
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            logging.exception("Failed to clean local clinical media upload: %s", destination)
        raise
    await _publish_realtime_event(realtime)
    return JSONResponse(result, headers={"Cache-Control": "private, no-store"})


@router.get("/patients/{patient_id}/media/uploads/{request_key}")
def mobile_patient_media_upload_status(
    patient_id: int,
    request_key: str,
    user: User = Depends(_mobile_user),
):
    receipt_key = _patient_media_receipt_key(user.id, patient_id, request_key)
    from app.patient_media_receipts import encryption_key, PatientMediaReceiptKeyUnavailable
    try:
        fingerprint_key = encryption_key()
    except PatientMediaReceiptKeyUnavailable as exc:
        raise HTTPException(status_code=503, detail="Klinik görüntü yükleme kurtarma anahtarı yapılandırılmamış.") from exc
    with Session(engine, expire_on_commit=False) as session:
        patient = session.exec(select(Patient).where(
            Patient.id == patient_id, Patient.owner_user_id == user.id
        )).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
        existing = _find_patient_media_receipt(
            session, user, patient_id, receipt_key, key=fingerprint_key,
        )
        session.commit()
        return JSONResponse(
            {"found": existing is not None, "media": existing["media"] if existing else None},
            headers={"Cache-Control": "private, no-store"},
        )

def _mobile_access_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    return credentials.credentials

class MobileConsultationRequest(BaseModel):
    expert_user_id: int = RequestField(gt=0)
    clinical_summary: str = RequestField(min_length=1)
    requester_opinion: str = ""
    question: str = RequestField(min_length=1)
    tooth_region: str = ""
    patient_id: Optional[int] = RequestField(default=None, gt=0)
    media_ids: str = ""
    urgency: str = "NORMAL"
    request_key: str = RequestField(default="", max_length=96)

@router.post("/consultations")
async def mobile_create_consultation(payload:MobileConsultationRequest,token:str=Depends(_mobile_access_token),user:User=Depends(_mobile_user)):
    from app import main as web
    if not payload.clinical_summary.strip() or not payload.question.strip():
        raise HTTPException(status_code=422,detail="Klinik bilgi ve uzmana sorunuz zorunlu.")
    # Reject an invalid selection rather than claiming that silently dropped
    # media was shared. Existing receipts still go through the web hash check.
    with Session(engine,expire_on_commit=False) as session:
        receipt=session.exec(select(web.ConsultationRequestReceipt).where(
            web.ConsultationRequestReceipt.requester_user_id==user.id,
            web.ConsultationRequestReceipt.expert_user_id==payload.expert_user_id,
            web.ConsultationRequestReceipt.request_key==payload.request_key)).first() if payload.request_key else None
        if payload.patient_id and not receipt:
            patient=session.get(Patient,payload.patient_id)
            if not patient or patient.owner_user_id!=user.id:
                raise HTTPException(status_code=403,detail="Hasta kaydına erişim yok.")
        if payload.media_ids and not receipt:
            try: ids={int(part.strip()) for part in payload.media_ids.split(",") if part.strip()}
            except (ValueError,TypeError): raise HTTPException(status_code=422,detail="Görüntü seçimi geçersiz.")
            if not payload.patient_id or not ids or any(item<=0 for item in ids):
                raise HTTPException(status_code=422,detail="Görüntüler için geçerli bir hasta seçin.")
            owned=session.exec(select(PatientMedia.id).where(PatientMedia.id.in_(ids),
                PatientMedia.patient_id==payload.patient_id,PatientMedia.owner_user_id==user.id)).all()
            if set(owned)!=ids:
                raise HTTPException(status_code=403,detail="Seçili görüntülerden biri bu hastaya ait değil veya artık erişilemiyor.")
    response=await expert_support_request_create(_mobile_request(token),payload.expert_user_id,
        payload.clinical_summary,payload.requester_opinion,payload.question,payload.tooth_region,
        payload.patient_id,payload.media_ids,payload.urgency,payload.request_key)
    status=getattr(response,"status_code",200)
    location=getattr(response,"headers",{}).get("location","")
    if location.startswith("/login"): raise _unauthorized()
    if status>=400:
        data=_response_json(response)
        detail=(data.get("error") or data.get("detail")) if isinstance(data,dict) else None
        if not isinstance(detail,str):
            raw=getattr(response,"body",b"").decode("utf-8",errors="replace")
            detail=raw[:300] if "<" not in raw else "Danışmanlık talebi oluşturulamadı."
        raise HTTPException(status_code=status,detail=detail)
    import re
    match=re.fullmatch(r"/expert-support/cases/([1-9][0-9]*)",location)
    if status not in (302,303) or not match:
        raise HTTPException(status_code=502,detail="Talep kaydı doğrulanamadı. Aynı talep anahtarıyla durumunu kontrol edin.")
    return {"ok":True,"case_id":int(match.group(1))}

class MobileMessage(BaseModel):
    content:str
    reply_to_message_id:Optional[int]=None
    client_message_id:str=""

@router.post("/consultations/{case_id}/messages")
async def mobile_send_consultation_message(case_id:int,payload:MobileMessage,token:str=Depends(_mobile_access_token)):
    response=await expert_support_message(_mobile_request(token),case_id,payload.content,
        payload.reply_to_message_id,payload.client_message_id)
    data=_response_json(response)
    if hasattr(response,"status_code") and response.status_code>=400:
        raise HTTPException(status_code=response.status_code,detail=data.get("error","Mesaj gönderilemedi."))
    return data

class MobileSupportMutationReceipt(SQLModel, table=True):
    """Durable per-user idempotency receipt for native support mutations."""
    receipt_key: str = SQLField(primary_key=True, max_length=180)
    user_id: int = SQLField(index=True)
    operation: str
    payload_hash: str
    ticket_id: int = SQLField(index=True)
    message_id: Optional[int] = None
    created_at: datetime = SQLField(default_factory=datetime.utcnow, index=True)


class MobileSupportCreate(BaseModel):
    subject: str
    message: str
    request_key: str
    case_id: Optional[int] = None


class MobileSupportReply(BaseModel):
    message: str
    request_key: str


def _support_receipt_key(user_id: int, operation: str, request_key: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,96}", request_key or ""):
        raise HTTPException(status_code=422, detail="Geçersiz destek işlem anahtarı.")
    return hashlib.sha256(f"{user_id}:{operation}:{request_key}".encode()).hexdigest()


def _support_mutation_replay(session: Session, key: str, user_id: int, operation: str, payload_hash: str):
    receipt = session.get(MobileSupportMutationReceipt, key)
    if not receipt:
        return None
    if receipt.user_id != user_id or receipt.operation != operation or not hmac.compare_digest(receipt.payload_hash, payload_hash):
        raise HTTPException(status_code=409, detail="Bu işlem anahtarı farklı bir destek işlemi için kullanılmış.")
    return receipt


@router.get("/support/tickets")
def mobile_support_tickets(before_id: Optional[int] = Query(None, ge=1), limit: int = Query(50, ge=1, le=100), token: str = Depends(_mobile_access_token), user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        query = select(SupportTicket).where(SupportTicket.user_id == user.id, SupportTicket.source_type == "SUPPORT")
        if before_id is not None:
            query = query.where(SupportTicket.id < before_id)
        tickets = session.exec(query.order_by(SupportTicket.id.desc()).limit(limit + 1)).all()
        has_more = len(tickets) > limit
        tickets = tickets[:limit]
        items = []
        for ticket in tickets:
            latest = session.exec(select(SupportTicketMessage).where(
                SupportTicketMessage.ticket_id == ticket.id
            ).order_by(SupportTicketMessage.id.desc()).limit(1)).first()
            items.append({
                "id": ticket.id, "subject": ticket.subject, "initial_message": ticket.message,
                "status": ticket.status, "created_at": ticket.created_at.isoformat(),
                "updated_at": ticket.updated_at.isoformat(),
                "last_message": latest.message if latest else ticket.message,
                "unread_count": _support_unread_count(session, ticket.id, "USER"),
                "can_reply": _support_user_can_reply(session, ticket),
            })
        return {"items": items, "total": len(items), "has_more": has_more, "next_before_id": tickets[-1].id if has_more and tickets else None}


@router.get("/support/reports")
def mobile_support_reports(token: str = Depends(_mobile_access_token), user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        reports = session.exec(select(UserReport).where(UserReport.reporter_user_id == user.id).order_by(UserReport.id.desc()).limit(100)).all()
        linked = _ensure_report_support_tickets(session, reports)
        items = []
        for report in reports:
            ticket = linked.get(report.id)
            items.append({"id": report.id, "case_id": report.case_id, "reason": report.reason, "detail": report.detail or "", "status": report.status, "created_at": report.created_at.isoformat(), "ticket_id": ticket.id if ticket else None, "unread_count": _support_unread_count(session, ticket.id, "USER") if ticket else 0})
        return {"items": items, "total": len(items)}


@router.get("/support/conversation-options")
def mobile_support_conversation_options(token: str = Depends(_mobile_access_token), user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        cases = session.exec(select(ConsultationCase).where(
            (ConsultationCase.requester_user_id == user.id) | (ConsultationCase.expert_user_id == user.id)
        ).order_by(ConsultationCase.requested_at.desc()).limit(100)).all()
        items = []
        for case in cases:
            has_message = session.exec(select(ConsultationMessage.id).where(ConsultationMessage.case_id == case.id).limit(1)).first() is not None
            if not has_message and not (case.requester_user_id == user.id and datetime.utcnow() > case.expert_response_deadline):
                continue
            other_id = case.expert_user_id if case.requester_user_id == user.id else case.requester_user_id
            other = session.get(User, other_id)
            items.append({"id": case.id, "other_display_name": other.display_name if other else "Kullanıcı", "status": case.status})
        return {"items": items}


@router.post("/support/tickets")
def mobile_support_create(payload: MobileSupportCreate, token: str = Depends(_mobile_access_token), user: User = Depends(_mobile_user)):
    subject = payload.subject.strip()
    message = payload.message.strip()
    if not subject or len(subject) > 160 or not message or len(message) > 4000:
        raise HTTPException(status_code=422, detail="Konu (1–160) ve açıklama (1–4000 karakter) zorunludur.")
    linked_case_id = None
    if payload.case_id is not None:
        with Session(engine, expire_on_commit=False) as check_session:
            case = check_session.get(ConsultationCase, payload.case_id)
            if not case or user.id not in {case.requester_user_id, case.expert_user_id}:
                raise HTTPException(status_code=403, detail="Bu konuşmayı destek talebine bağlama yetkiniz yok.")
            has_message = check_session.exec(select(ConsultationMessage.id).where(ConsultationMessage.case_id == case.id).limit(1)).first() is not None
            if not has_message and not (case.requester_user_id == user.id and datetime.utcnow() > case.expert_response_deadline):
                raise HTTPException(status_code=403, detail="Bu konuşma henüz destek talebine bağlanamaz.")
            linked_case_id = case.id
    key = _support_receipt_key(user.id, "CREATE", payload.request_key)
    digest = hashlib.sha256(json.dumps({"subject": subject, "message": message, "case_id": linked_case_id}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    with Session(engine, expire_on_commit=False) as session:
        replay = _support_mutation_replay(session, key, user.id, "CREATE", digest)
        if replay:
            return {"ok": True, "ticket_id": replay.ticket_id, "status": "REPLAYED", "replayed": True}
        ticket = SupportTicket(user_id=user.id, subject=subject, message=message, case_id=linked_case_id, source_type="SUPPORT")
        session.add(ticket)
        session.flush()
        session.add(MobileSupportMutationReceipt(receipt_key=key, user_id=user.id, operation="CREATE", payload_hash=digest, ticket_id=ticket.id))
        admins = session.exec(select(User).where(User.role == "ADMIN", User.is_active == True)).all()
        events = [_record_realtime_event(session, admin.id, "SUPPORT_TICKET_CREATED", "support_ticket", ticket.id,
            {"ticket_id": ticket.id, "user_id": user.id, "subject": ticket.subject, "status": "OPEN", "requires_fragment": True}) for admin in admins]
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            replay = _support_mutation_replay(session, key, user.id, "CREATE", digest)
            if replay:
                return {"ok": True, "ticket_id": replay.ticket_id, "status": "REPLAYED", "replayed": True}
            raise HTTPException(status_code=409, detail="Destek talebi sonucu doğrulanamadı; aynı işlem anahtarıyla tekrar deneyin.")
    for event in events:
        on_loop(_publish_realtime_event, event)
    return {"ok": True, "ticket_id": ticket.id, "status": ticket.status, "replayed": False}


def _mobile_support_ticket_owned(session: Session, ticket: SupportTicket, user_id: int) -> bool:
    if ticket.user_id != user_id:
        return False
    if ticket.source_type == "SUPPORT":
        return True
    if ticket.source_type == "REPORT" and ticket.source_id is not None:
        report = session.get(UserReport, ticket.source_id)
        return bool(report and report.reporter_user_id == user_id)
    return False


@router.get("/support/tickets/{ticket_id}")
def mobile_support_ticket_detail(ticket_id: int, before_id: Optional[int] = None, token: str = Depends(_mobile_access_token), user: User = Depends(_mobile_user)):
    if ticket_id <= 0 or (before_id is not None and before_id <= 0):
        raise HTTPException(status_code=422, detail="Geçersiz destek talebi veya sayfa kimliği.")
    with Session(engine, expire_on_commit=False) as session:
        ticket = session.get(SupportTicket, ticket_id)
        if not ticket or not _mobile_support_ticket_owned(session, ticket, user.id):
            raise HTTPException(status_code=404, detail="Destek talebi bulunamadı.")
        query = select(SupportTicketMessage).where(SupportTicketMessage.ticket_id == ticket.id)
        if before_id is not None:
            query = query.where(SupportTicketMessage.id < before_id)
        rows = session.exec(query.order_by(SupportTicketMessage.id.desc()).limit(21)).all()
        has_more = len(rows) > 20
        rows = list(reversed(rows[:20]))
        return {
            "ticket": {"id": ticket.id, "subject": ticket.subject, "initial_message": ticket.message,
                "status": ticket.status, "created_at": ticket.created_at.isoformat(),
                "updated_at": ticket.updated_at.isoformat(), "can_reply": _support_user_can_reply(session, ticket)},
            "messages": [{"id": m.id, "sender_role": m.sender_role, "message": m.message, "created_at": m.created_at.isoformat()} for m in rows],
            "has_more": has_more, "next_before_id": rows[0].id if has_more and rows else None,
            "unread_count": _support_unread_count(session, ticket.id, "USER"),
        }


@router.post("/support/tickets/{ticket_id}/read")
def mobile_support_ticket_read(ticket_id: int, through_message_id: Optional[int] = None, token: str = Depends(_mobile_access_token), user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        ticket = session.get(SupportTicket, ticket_id)
        if not ticket or not _mobile_support_ticket_owned(session, ticket, user.id):
            raise HTTPException(status_code=404, detail="Destek talebi bulunamadı.")
        remaining = _mark_support_read(session, ticket.id, "USER", through_message_id)
        session.commit()
        return {"ok": True, "ticket_id": ticket_id, "unread_count": remaining}


@router.post("/support/tickets/{ticket_id}/reply")
def mobile_support_ticket_reply(ticket_id: int, payload: MobileSupportReply, token: str = Depends(_mobile_access_token), user: User = Depends(_mobile_user)):
    message = payload.message.strip()
    if not message or len(message) > 4000:
        raise HTTPException(status_code=422, detail="Yanıt 1–4000 karakter olmalıdır.")
    key = _support_receipt_key(user.id, f"REPLY:{ticket_id}", payload.request_key)
    digest = hashlib.sha256(message.encode()).hexdigest()
    events = []
    with Session(engine, expire_on_commit=False) as session:
        replay = _support_mutation_replay(session, key, user.id, f"REPLY:{ticket_id}", digest)
        if replay:
            return {"ok": True, "ticket_id": ticket_id, "message_id": replay.message_id, "status": "REPLAYED", "replayed": True}
        ticket = session.exec(select(SupportTicket).where(SupportTicket.id == ticket_id).with_for_update()).first()
        if not ticket or not _mobile_support_ticket_owned(session, ticket, user.id):
            raise HTTPException(status_code=404, detail="Destek talebi bulunamadı.")
        if ticket.status == "CLOSED" or not _support_user_can_reply(session, ticket):
            raise HTTPException(status_code=409, detail="Destek ekibinin yeni yanıtını bekleyin veya yeni bir talep oluşturun.")
        row = SupportTicketMessage(ticket_id=ticket.id, sender_user_id=user.id, sender_role="USER", message=message)
        session.add(row)
        session.flush()
        ticket.status = "USER_REPLIED"
        ticket.updated_at = datetime.utcnow()
        session.add(ticket)
        session.add(MobileSupportMutationReceipt(receipt_key=key, user_id=user.id, operation=f"REPLY:{ticket_id}", payload_hash=digest, ticket_id=ticket.id, message_id=row.id))
        admins = session.exec(select(User).where(User.role == "ADMIN", User.is_active == True)).all()
        events = [_record_realtime_event(session, admin.id, "SUPPORT_MESSAGE_CREATED", "support_ticket_message", row.id,
            {"ticket_id": ticket.id, "message_id": row.id, "sender_role": "USER", "status": ticket.status}) for admin in admins]
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            replay = _support_mutation_replay(session, key, user.id, f"REPLY:{ticket_id}", digest)
            if replay:
                return {"ok": True, "ticket_id": ticket_id, "message_id": replay.message_id, "status": "REPLAYED", "replayed": True}
            raise HTTPException(status_code=409, detail="Yanıt sonucu doğrulanamadı; aynı işlem anahtarıyla tekrar deneyin.")
    for event in events:
        on_loop(_publish_realtime_event, event)
    return {"ok": True, "ticket_id": ticket_id, "message_id": row.id, "status": "USER_REPLIED", "replayed": False}


class MobileAcademicAsk(BaseModel):
    message:str

@router.post("/academic/courses/{course_id}/ask")
def mobile_academic_ask(course_id:int,payload:MobileAcademicAsk,background_tasks:BackgroundTasks,token:str=Depends(_mobile_access_token),user:User=Depends(_mobile_user)):
    response=study_ai_ask(_mobile_request(token,"POST",f"/notes/courses/{course_id}/ai/ask"),
        course_id,background_tasks,payload.message)
    data=_response_json(response)
    if hasattr(response,"status_code") and response.status_code>=400:
        raise HTTPException(status_code=response.status_code,detail=data.get("error","Akademik AI yanıt veremedi."))
    with Session(engine,expire_on_commit=False) as session:
        course=session.get(StudyCourse,course_id)
        if course and course.owner_user_id==user.id:
            event=_record_realtime_event(session,user.id,"ACADEMIC_MESSAGE_CREATED","study_course",course_id,{"course_id":course_id})
            session.commit()
            on_loop(_publish_realtime_event,event)
    return data
@router.get("/experts")
def mobile_experts_alias(user:User=Depends(_mobile_user),q:str=Query("",max_length=120)):
    with Session(engine,expire_on_commit=False) as session:
        profiles=session.exec(select(ExpertProfile).where(
            ExpertProfile.user_id!=user.id,ExpertProfile.application_status=="APPROVED",
            ExpertProfile.verification_status=="VERIFIED",ExpertProfile.specialty_verified==True,
            ExpertProfile.credential_document_path!=None,ExpertProfile.phone!=None
        ).order_by(ExpertProfile.updated_at.desc()).limit(50)).all()
        items=[]
        needle=q.strip().casefold()
        for p in profiles:
            u=session.get(User,p.user_id)
            if not u: continue
            hay=" ".join(filter(None,[u.display_name,p.specialty,p.institution,p.academic_title])).casefold()
            if needle and needle not in hay: continue
            items.append({"user_id":u.id,"id":u.id,"display_name":u.display_name,"specialty":p.specialty,
                "academic_title":p.academic_title,"institution":p.institution,
                "availability":p.availability,"consultation_price":p.consultation_price,
                "bio":getattr(p,"bio",None),"rating_avg":None,"review_count":0})
        return {"items":items}

@router.get("/patients/{patient_id}/media")
def mobile_patient_media(patient_id: int, before: Optional[int] = Query(None, ge=1), limit: int = Query(40, ge=1, le=100), user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        patient = session.get(Patient, patient_id)
        if not patient or patient.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
        query = select(PatientMedia).where(PatientMedia.patient_id == patient_id, PatientMedia.owner_user_id == user.id)
        if before is not None:
            query = query.where(PatientMedia.id < before)
        rows = session.exec(query.order_by(PatientMedia.id.desc()).limit(limit + 1)).all()
        has_more = len(rows) > limit
        page = rows[:limit]
        return {"items": [{"id": m.id, "filename": m.original_filename, "media_type": m.media_type,
            "tooth_number": m.tooth_number, "note": m.note, "uploaded_at": m.uploaded_at,
            "url": f"/api/mobile/v1/patients/{patient_id}/media/{m.id}/file"} for m in page],
            "next_before": page[-1].id if has_more and page else None}


@router.delete("/patients/{patient_id}/media/{media_id}")
def mobile_delete_patient_media(patient_id: int, media_id: int, user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        patient = session.get(Patient, patient_id)
        media = session.get(PatientMedia, media_id)
        if not patient or not media or media.patient_id != patient_id or patient.owner_user_id != user.id or media.owner_user_id != user.id:
            raise HTTPException(status_code=404, detail="Klinik görüntü bulunamadı.")
        file_path = media.file_path
        session.delete(media)
        event = _record_realtime_event(session, user.id, "PATIENT_MEDIA_DELETED", "patient", patient_id, {"patient_id": patient_id, "media_id": media_id})
        session.commit()
    on_loop(_publish_realtime_event, event)
    # Database commit precedes object deletion, matching the web route.
    cleanup_pending = False
    try:
        storage_delete(file_path)
    except Exception:
        # The database deletion already committed: do not report a false API failure.
        # Operators must reconcile orphaned storage objects from server logs.
        import logging
        logging.getLogger(__name__).exception("Patient media storage cleanup failed for media_id=%s", media_id)
        cleanup_pending = True
    return {"ok": True, "media_id": media_id, "storage_cleanup_pending": cleanup_pending}


@router.get("/patients/{patient_id}/media/{media_id}/file")
def mobile_patient_media_file(patient_id:int,media_id:int,user:User=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as session:
        patient=session.get(Patient,patient_id); media=session.get(PatientMedia,media_id)
        if not patient or not media or media.patient_id!=patient_id or patient.owner_user_id!=user.id or media.owner_user_id!=user.id:
            raise HTTPException(status_code=404,detail="Görüntü bulunamadı.")
        try:path=storage_ensure_local(media.file_path)
        except FileNotFoundError:raise HTTPException(status_code=404,detail="Görüntü dosyası bulunamadı.")
        from fastapi.responses import FileResponse
        mime={"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","webp":"image/webp"}.get(path.suffix.lower().lstrip("."),"application/octet-stream")
        return FileResponse(path,media_type=mime,filename=media.original_filename,headers={"Cache-Control":"private, no-store"})

async def _invoke_patient_web(handler, request, *args):
    response = await handler(request, *args) if _chat_inspect.iscoroutinefunction(handler) else await _chat_offload(handler, request, *args)
    if response.status_code >= 400:
        raw = getattr(response, "body", b"").decode("utf-8", errors="replace")
        raise HTTPException(status_code=response.status_code, detail=raw[:300] if "<" not in raw else "Hasta işlemi tamamlanamadı.")
    return response

class MobileSelectedMediaAnalysis(BaseModel):
    media_ids: list[int]
    tooth_number: Optional[str] = RequestField(default=None, max_length=10)
    clinical_notes: Optional[str] = RequestField(default=None, max_length=4000)

@router.post("/patients/{patient_id}/media/analyze")
async def mobile_analyze_patient_media(patient_id:int, payload:MobileSelectedMediaAnalysis, token:str=Depends(_mobile_access_token), user:User=Depends(_mobile_user)):
    from app import main as web
    from fastapi import BackgroundTasks
    import re
    ids=payload.media_ids
    if not 1 <= len(ids) <= web.MAX_ANALYSIS_IMAGES or any(i <= 0 for i in ids) or len(set(ids)) != len(ids):
        raise HTTPException(status_code=422,detail=f"1 ile {web.MAX_ANALYSIS_IMAGES} arasında farklı klinik görüntü seçin.")
    with Session(engine) as session:
        patient=session.get(Patient,patient_id)
        if not patient or patient.owner_user_id != user.id:
            raise HTTPException(status_code=404,detail="Hasta bulunamadı.")
        for ident in ids:
            media=session.get(PatientMedia,ident)
            if not media or media.patient_id != patient_id or media.owner_user_id != user.id:
                raise HTTPException(status_code=404,detail="Klinik görüntü bulunamadı.")
    tooth_number=(payload.tooth_number or "").strip() or None
    clinical_notes=(payload.clinical_notes or "").strip() or None
    response=await _invoke_patient_web(web.create_analysis,_mobile_request(token),patient_id,BackgroundTasks(),tooth_number,clinical_notes,None,','.join(map(str,ids)),[])
    match=re.fullmatch(r"/analysis/([1-9][0-9]*)(?:/viewer)?",str(response.headers.get('location','')))
    if response.status_code not in (302,303) or not match:
        raise HTTPException(status_code=502,detail="Analiz kaydı doğrulanamadı. Yeniden göndermeden önce analiz geçmişini kontrol edin.")
    return {"ok":True,"analysis_id":int(match.group(1))}

@router.delete("/patients/{patient_id}/media")
async def mobile_delete_all_patient_media(patient_id:int, token:str=Depends(_mobile_access_token), user:User=Depends(_mobile_user)):
    from app import main as web
    with Session(engine,expire_on_commit=False) as session:
        patient=session.get(Patient,patient_id)
        if not patient or patient.owner_user_id != user.id:
            raise HTTPException(status_code=404,detail="Hasta bulunamadı.")
    response=await _invoke_patient_web(web.delete_all_patient_media,_mobile_request(token),patient_id)
    if response.status_code not in (302,303):
        raise HTTPException(status_code=502,detail="Silme işlemi doğrulanamadı. Galeriyi yenileyin.")
    with Session(engine,expire_on_commit=False) as session:
        event=_record_realtime_event(session,user.id,"PATIENT_MEDIA_DELETED","patient",patient_id,{"patient_id":patient_id,"all":True})
        session.commit()
    await _publish_realtime_event(event)
    return {"ok":True}



# Native voice-exam adapter: reuse the existing web clinical engines, not their
# cookie-authenticated route handlers. No transcript or raw audio is persisted.
class MobileVoiceTextRequest(BaseModel):
    transcript: str
    consent: bool = False

class MobileVoiceFinalRequest(BaseModel):
    context: dict
    consent: bool = False
    insights: list[dict] = []
    uncertain: str = ""
    conversation_text: str = ""

def _mobile_voice_patient(user: User, patient_id: int):
    if user.role not in {"DOCTOR", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Sesli muayene yetkisi yok.")
    with Session(engine) as session:
        patient = session.exec(select(Patient).where(
            Patient.id == patient_id, Patient.owner_user_id == user.id
        )).first()
        if patient is None:
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
        from app import voice_exam
        return voice_exam._fingerprint(session, __import__("app.main", fromlist=["Patient"]), patient)

@router.post("/patients/{patient_id}/voice-exam/text")
def mobile_voice_text(patient_id: int, payload: MobileVoiceTextRequest, user: User = Depends(_mobile_user)):
    from app.voice_exam import core
    if not core.enabled():
        raise HTTPException(status_code=503, detail="Sesli muayene etkin değil.")
    revision = _mobile_voice_patient(user, patient_id)
    if not payload.consent:
        raise HTTPException(status_code=400, detail="Veri işleme onayı gerekli.")
    if not payload.transcript.strip() or len(payload.transcript) > core.MAX_TRANSCRIPT:
        raise HTTPException(status_code=422, detail="Muayene metni geçersiz.")
    try:
        return {"ok": True, "revision": revision, "review": core.extract(transcript=payload.transcript)}
    except core.VoiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/patients/{patient_id}/voice-exam/finalize")
def mobile_voice_finalize(patient_id: int, payload: MobileVoiceFinalRequest, user: User = Depends(_mobile_user)):
    from app.voice_exam import core
    from app.voice_exam_final import finalize
    if not core.enabled():
        raise HTTPException(status_code=503, detail="Sesli muayene etkin değil.")
    _mobile_voice_patient(user, patient_id)
    if not payload.consent:
        raise HTTPException(status_code=400, detail="Veri işleme onayı gerekli.")
    try:
        return {"ok": True, "final": finalize(payload.context, payload.insights,
            payload.uncertain, conversation_text=payload.conversation_text,
            request_scope=(user.id, patient_id))}
    except (core.VoiceError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/patients/{patient_id}/voice-exam/audio")
async def mobile_voice_audio(request: Request, patient_id: int, user: User = Depends(_mobile_user)):
    """Transcribe one bounded clip with encrypted, owner-scoped idempotency."""
    from app.voice_exam import core
    from app.voice_asr_receipts import (
        ReceiptConflict, ReceiptCorrupt, ReceiptKeyUnavailable, audio_content_digest,
        complete_receipt, encryption_key, finish_receipt, receipt_dedupe_key,
        reserve_receipt,
    )
    from starlette.concurrency import run_in_threadpool

    def reply(status: int, code: str, detail: str):
        return JSONResponse(
            {"ok": False, "code": code, "detail": detail},
            status_code=status,
            headers={"Cache-Control": "private, no-store"},
        )

    if not core.enabled():
        return reply(503, "VOICE_ASR_NOT_READY", "Sesli muayene etkin değil.")
    if request.headers.get("x-voice-consent") != "yes":
        return reply(400, "VOICE_ASR_CONSENT_REQUIRED", "Ses aktarımı için onay gerekli.")
    request_key = request.headers.get("x-voice-request-key", "")
    try:
        receipt_dedupe_key(user.id, patient_id, request_key)
        key = encryption_key()
    except ValueError:
        return reply(422, "VOICE_ASR_INVALID_KEY", "Ses bölümü işlem anahtarı geçersiz.")
    except ReceiptKeyUnavailable:
        return reply(503, "VOICE_ASR_NOT_READY", "Şifreli ses kurtarma anahtarı yapılandırılmamış.")

    revision = await run_in_threadpool(_mobile_voice_patient, user, patient_id)
    max_bytes = core.MAX_AUDIO
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > max_bytes:
        return reply(413, "VOICE_ASR_TOO_LARGE", "Ses kaydı çok büyük.")
    if not _mobile_voice_audio_slots.acquire(blocking=False):
        return reply(429, "VOICE_ASR_RETRYABLE", "Ses aktarımı yoğun. Yerel kaydı koruyup aynı bölümle tekrar deneyin.")

    data = bytearray()
    try:
        size = 0
        audio_hash = hashlib.sha256()
        async for chunk in request.stream():
            if not chunk:
                continue
            size += len(chunk)
            if size > max_bytes:
                return reply(413, "VOICE_ASR_TOO_LARGE", "Ses kaydı çok büyük.")
            data.extend(chunk)
            audio_hash.update(chunk)

        try:
            mime = core.validate_audio(data, request.headers.get("content-type", ""))
            digest = audio_content_digest(mime, audio_hash.digest(), key)
        except (core.VoiceError, ValueError):
            return reply(422, "VOICE_ASR_INVALID_AUDIO", "Ses dosyasının biçimi veya boyutu doğrulanamadı.")

        try:
            with Session(engine, expire_on_commit=False) as session:
                state = reserve_receipt(
                    session, owner_id=user.id, patient_id=patient_id,
                    request_key=request_key, digest=digest, key=key,
                )
                session.commit()
        except ReceiptConflict:
            return reply(409, "VOICE_ASR_KEY_REUSED", "Bu ses bölümünün işlem anahtarı farklı içerikle kullanılmış.")
        except ReceiptCorrupt:
            return reply(409, "VOICE_ASR_RECEIPT_INVALID", "Şifreli ses sonucu doğrulanamadı; kayıt korunuyor.")

        if state["state"] == "REPLAY":
            return JSONResponse(
                {"ok": True, "revision": state["revision"], "transcript": state["transcript"], "replayed": True},
                headers={"Cache-Control": "private, no-store"},
            )
        if state["state"] == "PROCESSING":
            return reply(409, "VOICE_ASR_IN_PROGRESS", "Aynı ses bölümü hâlâ işleniyor. Kaydı koruyup biraz sonra tekrar deneyin.")
        if state["state"] == "EXPIRED":
            return reply(410, "VOICE_ASR_EXPIRED", "Ses sonucu kurtarma süresini aştı. Yeni deneme ayrı bir AI çağrısı oluşturur.")
        if state["state"] != "CLAIMED":
            return reply(409, "VOICE_ASR_OUTCOME_UNKNOWN", "Önceki ses isteğinin sonucu kesinleşmedi. Aynı anahtarla ikinci AI çağrısı yapılmadı.")

        lease_token = state["lease_token"]
        try:
            result = await run_in_threadpool(
                core.extract, data=data, mime=mime, transcription_only=True
            )
            transcript = result.get("transcript") if isinstance(result, dict) else None
            if not isinstance(transcript, str) or not transcript.strip() or len(transcript) > 18000:
                raise ValueError("Invalid transcription response.")
        except core.VoiceBusy:
            with Session(engine, expire_on_commit=False) as session:
                finish_receipt(session, owner_id=user.id, patient_id=patient_id,
                    request_key=request_key, digest=digest, lease_token=lease_token, retryable=True)
                session.commit()
            return reply(429, "VOICE_ASR_RETRYABLE", "Ses çözümleme yoğun. Aynı yerel ses bölümüyle daha sonra tekrar deneyin.")
        except core.VoiceConfigurationError:
            with Session(engine, expire_on_commit=False) as session:
                finish_receipt(session, owner_id=user.id, patient_id=patient_id,
                    request_key=request_key, digest=digest, lease_token=lease_token, retryable=True)
                session.commit()
            return reply(503, "VOICE_ASR_NOT_READY", "Ses çözümleme yapılandırması hazır değil. Yerel kayıt korundu.")
        except Exception:
            with Session(engine, expire_on_commit=False) as session:
                finish_receipt(session, owner_id=user.id, patient_id=patient_id,
                    request_key=request_key, digest=digest, lease_token=lease_token, retryable=False)
                session.commit()
            logging.getLogger(__name__).warning("mobile voice ASR outcome is unknown")
            return reply(502, "VOICE_ASR_OUTCOME_UNKNOWN", "Ses sonucu doğrulanamadı. Aynı anahtarla ikinci AI çağrısı yapılmadı; yerel kayıt korundu.")
        finally:
            data.clear()

        with Session(engine, expire_on_commit=False) as session:
            saved = complete_receipt(
                session, owner_id=user.id, patient_id=patient_id,
                request_key=request_key, digest=digest, lease_token=lease_token,
                key=key, transcript=transcript, revision=revision,
            )
            session.commit()
        if not saved:
            return reply(409, "VOICE_ASR_OUTCOME_UNKNOWN", "Ses sonucu güvenli biçimde kaydedilemedi. Aynı anahtarla ikinci AI çağrısı yapılmadı; yerel kayıt korundu.")
        return JSONResponse(
            {"ok": True, "revision": revision, "transcript": transcript, "replayed": False},
            headers={"Cache-Control": "private, no-store"},
        )
    finally:
        data.clear()
        _mobile_voice_audio_slots.release()


# Native adapters reuse the existing web consultation rules; no second case lifecycle.
from typing import Literal as _ChatLiteral
from pydantic import Field as _ChatField
from fastapi.responses import FileResponse as _ChatFileResponse
from starlette.concurrency import run_in_threadpool as _chat_offload
import inspect as _chat_inspect

class MobileChatAction(BaseModel):
    action: _ChatLiteral["expert-response", "proposal", "complete", "block", "unblock", "report", "delete", "restore", "review"]
    decision: _ChatLiteral["ACCEPT", "REJECT"] = "ACCEPT"
    start_option: _ChatLiteral["NOW", "30M", "1H", "3H", "TODAY"] = "NOW"
    proposal_note: str = _ChatField(default="", max_length=500)
    completion_action: _ChatLiteral["COMPLETE", "CONTINUE", "DISPUTE"] = "COMPLETE"
    reason: _ChatLiteral["HARASSMENT", "PROFANITY", "SPAM", "INAPPROPRIATE", "OTHER"] = "OTHER"
    detail: str = _ChatField(default="", max_length=1000)
    rating: int = _ChatField(default=5, ge=1, le=5)
    comment: str = _ChatField(default="", max_length=2000)

async def _mobile_chat_dispatch(handler, request, *args):
    response = await handler(request, *args) if _chat_inspect.iscoroutinefunction(handler) else await _chat_offload(handler, request, *args)
    status = getattr(response, "status_code", 200)
    location = getattr(response, "headers", {}).get("location", "")
    if location.startswith("/login"):
        raise _unauthorized()
    data = _response_json(response)
    if status >= 400:
        message = data.get("error") or data.get("detail") if isinstance(data, dict) else None
        if not isinstance(message, str):
            raw = getattr(response, "body", b"").decode("utf-8", errors="replace")
            message = raw[:300] if "<" not in raw else "Görüşme işlemi tamamlanamadı."
        raise HTTPException(status_code=status, detail=message)
    if isinstance(data, dict):
        if data.get("ok") is False:
            raise HTTPException(status_code=409, detail=data.get("error") or "İşlem doğrulanamadı.")
        return data
    if 300 <= status < 400:
        return {"ok": True}
    raise HTTPException(status_code=502, detail="İşlem sonucu doğrulanamadı; görüşmeyi yenileyin.")

@router.post("/consultations/{case_id}/actions")
async def mobile_chat_action(case_id: int, payload: MobileChatAction,
                             token: str = Depends(_mobile_access_token),
                             user: User = Depends(_mobile_user)):
    if case_id <= 0:
        raise HTTPException(status_code=422, detail="Geçersiz görüşme.")
    from app import main as web
    request = _mobile_request(token, path=f"/expert-support/cases/{case_id}")
    handlers = {
        "expert-response": (web.expert_support_expert_response, (payload.decision, payload.start_option, payload.proposal_note)),
        "proposal": (web.expert_support_proposal_decision, (payload.decision,)),
        "complete": (web.expert_support_complete, (payload.completion_action,)),
        "block": (web.consultation_block_user, ()),
        "unblock": (web.consultation_unblock_user, ()),
        "report": (web.consultation_report_user, (payload.reason, payload.detail)),
        "delete": (web.consultation_message_delete_for_user, ()),
        "restore": (web.consultation_message_restore_for_user, ()),
        "review": (web.expert_support_review, (payload.rating, payload.comment)),
    }
    handler, args = handlers[payload.action]
    return await _mobile_chat_dispatch(handler, request, case_id, *args)

def _mobile_chat_context(session, case, user):
    from app import main as web
    other_id = case.expert_user_id if user.id == case.requester_user_id else case.requester_user_id
    peer = session.get(User, other_id)
    own = session.exec(select(ConsultationInboxState).where(
        ConsultationInboxState.case_id == case.id, ConsultationInboxState.user_id == user.id)).first()
    other = session.exec(select(ConsultationInboxState).where(
        ConsultationInboxState.case_id == case.id, ConsultationInboxState.user_id == other_id)).first()
    blocked = session.exec(select(web.UserBlock).where(
        web.UserBlock.blocker_user_id == user.id, web.UserBlock.blocked_user_id == other_id)).first()
    review = session.exec(select(web.ExpertReview).where(web.ExpertReview.case_id == case.id)).first()
    now = web._utcnow_naive()
    shared_media = []
    if not case.messages_deleted_at and not (own and own.deleted_at):
        selected = session.exec(select(web.ConsultationCaseMedia, PatientMedia).join(
            PatientMedia, PatientMedia.id == web.ConsultationCaseMedia.patient_media_id).where(
            web.ConsultationCaseMedia.case_id == case.id).order_by(web.ConsultationCaseMedia.id)).all()
        shared_media = [{"id": link.id, "media_type": media.media_type} for link, media in selected]
    return {
        "shared_media": shared_media,
        "other_display_name": peer.display_name if peer else "Kullanıcı",
        "blocked_by_me": blocked is not None, "blocked_either": web._users_blocked(session, user.id, other_id),
        "other_read_at": other.last_read_at if other else None,
        "inbox_deleted": bool(own and own.deleted_at), "recover_until": own.recover_until if own else None,
        "completed_at": case.completed_at, "expert_completed_at": case.expert_completed_at,
        "proposed_start_label": case.proposed_start_label, "expert_proposal_note": case.expert_proposal_note,
        "review_submitted": review is not None,
        "can_report": web._support_case_is_selectable(session, case, user.id, now) and not case.messages_deleted_at and
            (case.status != "COMPLETED" or (user.id == case.requester_user_id and case.completed_at is not None and
             now <= web._consultation_retention_start(case) + timedelta(days=web.CONSULTATION_REPORT_DAYS))),
        "can_dispute": user.id == case.requester_user_id and not case.messages_deleted_at and
            (case.status == "EXPERT_COMPLETED" or (case.status == "COMPLETED" and case.completed_at is not None and
             now <= web._consultation_retention_start(case) + timedelta(days=web.CONSULTATION_REPORT_DAYS))),
    }

@router.get("/messages/deleted")
def mobile_deleted_chats(user: User = Depends(_mobile_user)):
    from app import main as web
    with Session(engine, expire_on_commit=False) as session:
        rows = session.exec(select(ConsultationCase, ConsultationInboxState).join(
            ConsultationInboxState, ConsultationInboxState.case_id == ConsultationCase.id).where(
            ConsultationInboxState.user_id == user.id, ConsultationInboxState.deleted_at != None,
            ConsultationInboxState.recover_until > web._utcnow_naive(),
            ConsultationCase.messages_deleted_at == None,
            (ConsultationCase.requester_user_id == user.id) | (ConsultationCase.expert_user_id == user.id)
        ).order_by(ConsultationInboxState.deleted_at.desc()).limit(50)).all()
        return {"items": [{"id":c.id, "status":c.status, "specialty":c.specialty,
            "recover_until":state.recover_until, "requested_at":c.requested_at} for c,state in rows]}

@router.get("/consultations/{case_id}/attachments/{message_id}")
def mobile_chat_attachment(case_id: int, message_id: int, user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        case = session.get(ConsultationCase, case_id)
        message = session.get(ConsultationMessage, message_id)
        if not case or user.id not in {case.requester_user_id, case.expert_user_id} or case.messages_deleted_at or not message or message.case_id != case_id or not message.media_path:
            raise HTTPException(status_code=404, detail="Ek bulunamadı.")
        state = session.exec(select(ConsultationInboxState).where(
            ConsultationInboxState.case_id == case_id, ConsultationInboxState.user_id == user.id)).first()
        if state and state.deleted_at:
            raise HTTPException(status_code=404, detail="Önce görüşmeyi geri yükleyin.")
        reference = message.media_path
    try:
        path = storage_ensure_local(reference)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Ek bulunamadı.")
    return _ChatFileResponse(path, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

@router.get("/consultations/{case_id}/shared-media/{link_id}")
def mobile_case_shared_media(case_id: int, link_id: int, user: User = Depends(_mobile_user)):
    from app import main as web
    with Session(engine, expire_on_commit=False) as session:
        case = session.get(ConsultationCase, case_id)
        link = session.get(web.ConsultationCaseMedia, link_id)
        if not case or user.id not in {case.requester_user_id, case.expert_user_id} or case.messages_deleted_at or not link or link.case_id != case_id:
            raise HTTPException(status_code=404, detail="Görsel bulunamadı.")
        state = session.exec(select(ConsultationInboxState).where(ConsultationInboxState.case_id == case_id, ConsultationInboxState.user_id == user.id)).first()
        media = session.get(PatientMedia, link.patient_media_id)
        if not media or (state and state.deleted_at):
            raise HTTPException(status_code=404, detail="Görsel bulunamadı.")
        reference = media.file_path
    try:
        path = storage_ensure_local(reference)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Görsel bulunamadı.")
    return _ChatFileResponse(path, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

@router.post("/consultations/{case_id}/attachments")
async def mobile_chat_upload(case_id: int, file: UploadFile = File(...),
                             reply_to_message_id: Optional[int] = Form(None),
                             token: str = Depends(_mobile_access_token),
                             user: User = Depends(_mobile_user)):
    from app import main as web
    # Authorize before touching the payload, then let the existing web handler
    # recheck state/participant permissions under its normal case lock.
    with Session(engine, expire_on_commit=False) as session:
        case = session.get(ConsultationCase, case_id)
        if not case or user.id not in {case.requester_user_id, case.expert_user_id} or case.messages_deleted_at:
            raise HTTPException(status_code=404, detail="Görüşme bulunamadı.")
        if web._users_blocked(session, user.id, case.expert_user_id if user.id == case.requester_user_id else case.requester_user_id):
            raise HTTPException(status_code=403, detail="Engellenen görüşmeye ek gönderilemez.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".pdf", ".m4a", ".mp3", ".wav", ".ogg"}:
        raise HTTPException(status_code=415, detail="Desteklenmeyen ek türü.")
    import tempfile
    from io import BytesIO
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        with tempfile.TemporaryDirectory(prefix="dai-chat-") as directory:
            destination = Path(directory) / ("image" + suffix)
            await _chat_offload(_copy_validated_image, file, destination, min(MOBILE_MAX_IMAGE_BYTES, web.CONSULTATION_UPLOAD_MAX_BYTES))
            raw = await _chat_offload(destination.read_bytes)
    else:
        raw = await _chat_offload(file.file.read, web.CONSULTATION_UPLOAD_MAX_BYTES + 1)
        if not raw or len(raw) > web.CONSULTATION_UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=413, detail="Ek boş veya 25 MB sınırını aşıyor.")
        signatures = {
            ".pdf": raw.startswith(b"%PDF-"),
            ".wav": raw.startswith(b"RIFF") and raw[8:12] == b"WAVE",
            ".ogg": raw.startswith(b"OggS"),
            ".m4a": len(raw) >= 12 and raw[4:8] == b"ftyp",
            ".mp3": raw.startswith(b"ID3") or (len(raw) >= 2 and raw[0] == 255 and raw[1] & 224 == 224),
        }
        if not signatures[suffix]:
            raise HTTPException(status_code=422, detail="Dosya içeriği seçilen ek türüyle eşleşmiyor.")
    clean = UploadFile(filename=Path(file.filename or ("attachment" + suffix)).name,
                       file=BytesIO(raw), headers=file.headers)
    try:
        return await _mobile_chat_dispatch(web.expert_support_media_message,
            _mobile_request(token), case_id, clean, reply_to_message_id, "")
    finally:
        await clean.close()

@router.get("/consultations/request-context/{expert_id}")
def mobile_consultation_request_context(expert_id:int,user:User=Depends(_mobile_user)):
    from app import main as web
    if expert_id<=0 or expert_id==user.id:
        raise HTTPException(status_code=400,detail="Geçerli bir uzman seçin; kendinize vaka gönderemezsiniz.")
    with Session(engine,expire_on_commit=False) as session:
        web._expire_pending_expert_requests(session,expert_id)
        expert=session.get(User,expert_id)
        profile=session.exec(select(ExpertProfile).where(ExpertProfile.user_id==expert_id)).first()
        if not web.consultation_expert_is_verified(expert,profile) or web._users_blocked(session,user.id,expert_id):
            raise HTTPException(status_code=409,detail="Uzman şu anda yeni vaka kabul etmiyor.")
        policy=web._expert_policy_state(session,expert_id)
        if profile.availability!="AVAILABLE" or web._expert_is_blocked(policy) or web._expert_open_case_count(session,expert_id)>=web.consultation_capacity_limit(profile):
            raise HTTPException(status_code=409,detail="Uzman şu anda yeni vaka kabul etmiyor.")
        return {"expert":{"user_id":expert.id,"display_name":expert.display_name,"specialty":profile.specialty,
            "academic_title":profile.academic_title,"consultation_price":profile.consultation_price,
            "availability":profile.availability},"response_minutes":10,
            "urgencies":[{"value":value,"label":label} for value,label in web.CONSULTATION_URGENCIES.items()]}

@router.get("/consultations/request-status/{expert_id}/{request_key}")
def mobile_consultation_request_status(expert_id:int,request_key:str,user:User=Depends(_mobile_user)):
    from app import main as web
    if len(request_key)>96:
        raise HTTPException(status_code=422,detail="Geçersiz talep anahtarı.")
    with Session(engine,expire_on_commit=False) as session:
        receipt=session.exec(select(web.ConsultationRequestReceipt).where(
            web.ConsultationRequestReceipt.requester_user_id==user.id,
            web.ConsultationRequestReceipt.expert_user_id==expert_id,
            web.ConsultationRequestReceipt.request_key==request_key)).first()
        case=session.get(ConsultationCase,receipt.case_id) if receipt else None
        if not case or case.requester_user_id!=user.id or case.expert_user_id!=expert_id:
            return {"found":False}
        return {"found":True,"case_id":case.id,"status":case.status}

# Import after shared native authentication helpers to avoid a circular router setup.
from app.mobile_account_api import router as mobile_account_router
router.include_router(mobile_account_router)

from app.mobile_program_api import router as mobile_program_router
router.include_router(mobile_program_router)

from app.mobile_voice_workflow_api import router as mobile_voice_workflow_router
router.include_router(mobile_voice_workflow_router)

from app.mobile_academic_api import router as mobile_academic_router
router.include_router(mobile_academic_router)

from app.mobile_clinical_api import router as mobile_clinical_router
router.include_router(mobile_clinical_router)
