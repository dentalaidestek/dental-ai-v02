"""Native mobile API for the Android client.

This layer exposes JSON contracts over the existing FastAPI/SQLModel business
data. It deliberately reuses the same session-token records as the web app so
mobile clients do not create a second authentication system.
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
import os
import shutil
import time
import uuid
from collections import deque
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlmodel import Session, func, select
from PIL import Image
from starlette.requests import Request
from fastapi.responses import JSONResponse

from app.auth import create_session_token, hash_session_token, verify_password
from app.auth_rate import LOGIN_WINDOW_SECONDS, LOGIN_MAX_FAILURES, admit as admit_auth_attempt, clear as clear_auth_attempt, bucket_key
from app.main import (
    Analysis,
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
    AdminNotice, StudyCourse, StudyChatMessage,
    ConsultationCase, ConsultationMessage, ExpertProfile, E2EEDeviceKey,
    expert_support_request_create, expert_support_message, study_ai_ask,
    SESSION_COOKIE, storage_persist_file, storage_ensure_local, _record_patient_realtime_events,
    _record_realtime_event, _publish_realtime_event, on_loop,
    _ensure_email_verification_challenge, _verify_email_code,
)

router = APIRouter(prefix="/api/mobile/v1", tags=["mobile"])
bearer = HTTPBearer(auto_error=False)
MOBILE_MAX_IMAGE_BYTES = max(1, int(os.getenv("MOBILE_MAX_IMAGE_BYTES", str(15 * 1024 * 1024))))
MOBILE_MAX_IMAGE_PIXELS = max(1, int(os.getenv("MOBILE_MAX_IMAGE_PIXELS", "40000000")))
MOBILE_MAX_ANALYSIS_BYTES = max(1, int(os.getenv("MOBILE_MAX_ANALYSIS_BYTES", str(15 * 1024 * 1024))))
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


def _copy_validated_image(upload: UploadFile, destination: Path, max_bytes: int) -> None:
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
        with Image.open(destination) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MOBILE_MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=422, detail="Görüntü çözünürlüğü çok büyük.")
            image.verify()
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
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
            .order_by(Patient.created_at.desc())
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


class MobileScheduleCreate(BaseModel):
    event_type: str
    title: str
    start_at: str
    end_at: str = ""
    patient_id: Optional[int] = None
    location: str = ""
    notes: str = ""
    reminder_minutes: int = 30
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
    with Session(engine, expire_on_commit=False) as session:
        values, error = _validate_schedule_input(
            session, user, payload.event_type, payload.title, payload.start_at, payload.end_at,
            str(payload.patient_id or ""), payload.location, payload.notes,
            str(payload.reminder_minutes), "1" if payload.notification_enabled else None,
            payload.recurrence_rule, payload.recurrence_until,
        )
        if error:
            raise HTTPException(status_code=422, detail=error)
        event = ScheduleEvent(owner_user_id=user.id, **values)
        session.add(event)
        session.flush()
        realtime=_record_realtime_event(session,user.id,"PROGRAM_CREATED","schedule_event",event.id,{"event_id":event.id,"status":event.status})
        session.commit(); on_loop(_publish_realtime_event,realtime)
        return {"event": {"id": event.id, "event_type": event.event_type, "title": event.title,
                          "start_at": event.start_at, "end_at": event.end_at, "patient_id": event.patient_id,
                          "location": event.location, "status": event.status}}


@router.post("/patients/{patient_id}/teeth/{tooth_number}")
def mobile_update_tooth(
    patient_id: int,
    tooth_number: str,
    payload: MobileToothUpdate,
    user: User = Depends(_mobile_user),
):
    allowed_statuses = {"HEALTHY","CARIES","FILLING","CROWN","ROOT_CANAL","EXTRACTED","IMPLANT","OTHER"}
    allowed_surfaces = {"OCCLUSAL","INCISAL","MESIAL","DISTAL","BUCCAL","LINGUAL"}
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Geçersiz diş durumu.")
    if payload.surface and payload.surface not in allowed_surfaces:
        raise HTTPException(status_code=422, detail="Geçersiz diş yüzeyi.")
    with Session(engine, expire_on_commit=False) as session:
        patient = session.get(Patient, patient_id)
        if not patient or (user.role != "ADMIN" and patient.owner_user_id != user.id):
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
        if payload.surface:
            surface = session.exec(select(ToothSurfaceStatus).where(
                ToothSurfaceStatus.patient_id == patient_id,
                ToothSurfaceStatus.tooth_number == tooth_number,
                ToothSurfaceStatus.surface == payload.surface,
            )).first()
            if surface:
                surface.status, surface.note, surface.updated_at = payload.status, note, datetime.utcnow()
            else:
                session.add(ToothSurfaceStatus(patient_id=patient_id,tooth_number=tooth_number,surface=payload.surface,status=payload.status,note=note))
        treatment_names = {"CARIES":"Çürük","FILLING":"Dolgu","CROWN":"Kron","ROOT_CANAL":"Kanal Tedavisi","EXTRACTED":"Diş Çekimi","IMPLANT":"İmplant","OTHER":"Diğer"}
        if payload.status in treatment_names:
            treatment_name = treatment_names[payload.status]
            treatment_date = datetime.utcnow().strftime("%Y-%m-%d")
            existing_treatment = session.exec(select(Treatment).where(
                Treatment.patient_id == patient_id,
                Treatment.tooth_number == tooth_number,
                Treatment.treatment_name == treatment_name,
                Treatment.treatment_date == treatment_date,
            )).first()
            if not existing_treatment:
                session.add(Treatment(patient_id=patient_id,tooth_number=tooth_number,treatment_name=treatment_name,treatment_date=treatment_date,doctor_note=note))
        realtime=_record_realtime_event(session,user.id,"TOOTH_UPDATED","patient",patient_id,{"patient_id":patient_id,"tooth_number":tooth_number,"status":payload.status,"surface":payload.surface,"note":note})
        session.commit(); on_loop(_publish_realtime_event,realtime)
        return {"ok": True, "tooth_number": tooth_number, "status": payload.status, "surface": payload.surface}


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
            .order_by(PatientMedia.uploaded_at.desc())
        ).all()

        return {
            "patient": _patient_payload(patient),
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
def mobile_consultations(user:User=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as session:
        cases=session.exec(select(ConsultationCase).where(
            (ConsultationCase.requester_user_id==user.id)|(ConsultationCase.expert_user_id==user.id)
        ).order_by(ConsultationCase.requested_at.desc()).limit(50)).all()
        items=[]
        for c in cases:
            other_id=c.expert_user_id if c.requester_user_id==user.id else c.requester_user_id
            other=session.get(User,other_id)
            last=session.exec(select(ConsultationMessage).where(
                ConsultationMessage.case_id==c.id).order_by(ConsultationMessage.created_at.desc()).limit(1)).first()
            items.append({"id":c.id,"status":c.status,"specialty":c.specialty,"tooth_region":c.tooth_region,
                "question":c.question,"requested_at":c.requested_at,"other_user_id":other_id,
                "other_display_name":other.display_name if other else "Kullanıcı",
                "last_message":last.content if last else None,"last_message_at":last.created_at if last else None})
        return {"items":items}

@router.get("/consultations/{case_id}")
def mobile_consultation(case_id:int,user:User=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as session:
        c=session.get(ConsultationCase,case_id)
        if not c or user.id not in {c.requester_user_id,c.expert_user_id}:
            raise HTTPException(status_code=404,detail="Vaka bulunamadı.")
        msgs=session.exec(select(ConsultationMessage).where(
            ConsultationMessage.case_id==c.id).order_by(ConsultationMessage.created_at.asc())).all()
        return {"case":{"id":c.id,"status":c.status,"specialty":c.specialty,"tooth_region":c.tooth_region,
            "clinical_summary":c.clinical_summary,"requester_opinion":c.requester_opinion,"question":c.question,
            "requested_at":c.requested_at,"expert_user_id":c.expert_user_id,"requester_user_id":c.requester_user_id},
            "messages":[{"id":m.id,"sender_user_id":m.sender_user_id,"message_type":m.message_type,
            "content":m.content,"reply_to_message_id":m.reply_to_message_id,"created_at":m.created_at} for m in msgs]}

@router.get("/academic/courses")
def mobile_academic_courses(user:User=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as session:
        rows=session.exec(select(StudyCourse).where(
            StudyCourse.owner_user_id==user.id).order_by(StudyCourse.created_at.desc()).limit(50)).all()
        return {"items":[{"id":c.id,"title":c.title,"description":getattr(c,"description",None),
            "updated_at":getattr(c,"updated_at",c.created_at),"created_at":c.created_at,"material_count":session.exec(select(func.count()).select_from(StudyMaterial).where(StudyMaterial.course_id==c.id,StudyMaterial.owner_user_id==user.id)).one()} for c in rows]}

@router.get("/academic/courses/{course_id}/messages")
def mobile_academic_messages(course_id:int,user:User=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as session:
        rows=session.exec(select(StudyChatMessage).where(
            StudyChatMessage.course_id==course_id,StudyChatMessage.owner_user_id==user.id
        ).order_by(StudyChatMessage.id.asc()).limit(100)).all()
        return {"items":[{"id":m.id,"role":m.role,"content":m.content,"created_at":m.created_at} for m in rows]}

@router.post("/patients/{patient_id}/media")
async def mobile_patient_media_upload(
    patient_id:int,
    image:UploadFile=File(None),
    file:UploadFile=File(None),
    tooth_number:Optional[str]=Form(None),
    note:Optional[str]=Form(None),
    user:User=Depends(_mobile_user),
):
    image = image or file
    if not image or not image.filename:
        raise HTTPException(status_code=422,detail="Görüntü seçin.")
    ext=Path(image.filename).suffix.lower()
    if ext not in {".jpg",".jpeg",".png",".webp"}:
        raise HTTPException(status_code=422,detail="Desteklenmeyen görüntü formatı.")
    with Session(engine,expire_on_commit=False) as session:
        patient=session.get(Patient,patient_id)
        if not patient or (user.role!="ADMIN" and patient.owner_user_id!=user.id):
            raise HTTPException(status_code=404,detail="Hasta bulunamadı.")
        stored=f"patient_{patient_id}_{uuid.uuid4().hex}{ext}"
        destination=Path("uploads")/"patient-media"/stored
        destination.parent.mkdir(parents=True,exist_ok=True)
        _copy_validated_image(image, destination, MOBILE_MAX_IMAGE_BYTES)
        storage_persist_file(destination)
        media=PatientMedia(patient_id=patient_id,owner_user_id=user.id,
            original_filename=Path(image.filename).name,stored_filename=stored,
            file_path=str(destination),media_type="PHOTO",
            tooth_number=(tooth_number or "").strip() or None,note=(note or "").strip() or None)
        session.add(media);session.flush()
        realtime=_record_realtime_event(session,user.id,"PATIENT_MEDIA_CREATED","patient",patient_id,{"patient_id":patient_id,"media_id":media.id,"filename":media.original_filename})
        session.commit(); on_loop(_publish_realtime_event,realtime)
        return {"media":{"id":media.id,"original_filename":media.original_filename,
            "media_type":media.media_type,"tooth_number":media.tooth_number,
            "note":media.note,"uploaded_at":media.uploaded_at}}

def _mobile_access_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    return credentials.credentials

class MobileConsultationRequest(BaseModel):
    expert_user_id:int
    clinical_summary:str
    requester_opinion:str=""
    question:str
    tooth_region:str=""
    patient_id:Optional[int]=None
    media_ids:str=""
    urgency:str="NORMAL"

@router.post("/consultations")
async def mobile_create_consultation(payload:MobileConsultationRequest,token:str=Depends(_mobile_access_token)):
    response=await expert_support_request_create(_mobile_request(token),payload.expert_user_id,
        payload.clinical_summary,payload.requester_opinion,payload.question,payload.tooth_region,
        payload.patient_id,payload.media_ids,payload.urgency)
    if hasattr(response,"status_code") and response.status_code>=400:
        data=_response_json(response);raise HTTPException(status_code=response.status_code,detail=data.get("error","Danışmanlık oluşturulamadı."))
    location=getattr(response,"headers",{}).get("location")
    return {"ok":True,"case_id":int(location.rsplit("/",1)[-1]) if location else None}

class MobileMessage(BaseModel):
    content:str
    reply_to_message_id:Optional[int]=None
    client_message_id:str=""

@router.post("/consultations/{case_id}/messages")
def mobile_send_consultation_message(case_id:int,payload:MobileMessage,token:str=Depends(_mobile_access_token)):
    response=expert_support_message(_mobile_request(token),case_id,payload.content,
        payload.reply_to_message_id,payload.client_message_id)
    data=_response_json(response)
    if hasattr(response,"status_code") and response.status_code>=400:
        raise HTTPException(status_code=response.status_code,detail=data.get("error","Mesaj gönderilemedi."))
    return data

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
def mobile_patient_media(patient_id:int,user:User=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as session:
        patient=session.get(Patient,patient_id)
        if not patient or (user.role!="ADMIN" and patient.owner_user_id!=user.id):
            raise HTTPException(status_code=404,detail="Hasta bulunamadı.")
        rows=session.exec(select(PatientMedia).where(
            PatientMedia.patient_id==patient_id,PatientMedia.owner_user_id==user.id
        ).order_by(PatientMedia.uploaded_at.desc()).limit(100)).all()
        return {"items":[{"id":m.id,"filename":m.original_filename,"media_type":m.media_type,
            "tooth_number":m.tooth_number,"note":m.note,"uploaded_at":m.uploaded_at,
            "url":f"/patients/{patient_id}/media/{m.id}"} for m in rows]}

@router.get("/patients/{patient_id}/media/{media_id}/file")
def mobile_patient_media_file(patient_id:int,media_id:int,user:User=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as session:
        patient=session.get(Patient,patient_id); media=session.get(PatientMedia,media_id)
        if not patient or not media or media.patient_id!=patient_id or (user.role!="ADMIN" and (patient.owner_user_id!=user.id or media.owner_user_id!=user.id)):
            raise HTTPException(status_code=404,detail="Görüntü bulunamadı.")
        try:path=storage_ensure_local(media.file_path)
        except FileNotFoundError:raise HTTPException(status_code=404,detail="Görüntü dosyası bulunamadı.")
        from fastapi.responses import FileResponse
        mime={"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","webp":"image/webp"}.get(path.suffix.lower().lstrip("."),"application/octet-stream")
        return FileResponse(path,media_type=mime,filename=media.original_filename,headers={"Cache-Control":"private, no-store"})
