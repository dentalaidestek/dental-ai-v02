"""Native mobile API for the Android client.

This layer exposes JSON contracts over the existing FastAPI/SQLModel business
data. It deliberately reuses the same session-token records as the web app so
mobile clients do not create a second authentication system.
"""

from datetime import datetime
from pathlib import Path
import json
import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlmodel import Session, func, select

from app.auth import create_session_token, hash_session_token, verify_password
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
    PROGRAM_EVENT_TYPES,
    _find_duplicate_patient,
    _validate_schedule_input,
    UserAccountMeta,
    engine,
    _run_analysis_vision,
    _run_preliminary_ai,
    classify_dental_image,
)

router = APIRouter(prefix="/api/mobile/v1", tags=["mobile"])
bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    login: str
    password: str


class MobileToken(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime


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
        if not user or not user.is_active:
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


@router.post("/auth/login", response_model=MobileToken)
def mobile_login(payload: LoginRequest):
    login = payload.login.strip().lower()

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
            raise HTTPException(
                status_code=401,
                detail="Kullanıcı adı/e-posta veya şifre hatalı.",
            )

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
        session.commit()
        session.refresh(patient)
        session.add(PatientProfile(patient_id=patient.id, address=payload.address.strip() if payload.address else None))
        session.commit()
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
        session.commit()
        session.refresh(event)
        return {"event": {"id": event.id, "event_type": event.event_type, "title": event.title,
                          "start_at": event.start_at, "end_at": event.end_at, "patient_id": event.patient_id,
                          "location": event.location, "status": event.status}}


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
