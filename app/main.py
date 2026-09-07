import os
import json
import re
import uuid
import secrets
import urllib.request
import urllib.error
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import shutil
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
from typing import Optional
from zoneinfo import ZoneInfo

from dental_rag.rag import (
    get_relevant_context,
    get_specialty_relevant_context,
)
from dental_rag.specialty_router import classify_specialties

from app.legal_texts import LEGAL_TEXTS, LEGAL_VERSION
from app.study_ai import StudyAIError, ask_rag as ask_study_ai, delete_file as delete_study_ai_file
from app.study_rag import (
    StudyRAGChunk,
    StudyRAGMemory,
    StudyRAGError,
    classify_course_scope,
    delete_course_rag_index,
    delete_course_rag_memory,
    delete_material_rag_index,
    ensure_course_index,
    remember_exchange,
    retrieve_course_context,
)
from fastapi import (
    FastAPI,
    Form,
    Request,
    UploadFile,
    File,
    BackgroundTasks,
    Cookie,
)
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Field, Session, SQLModel, create_engine, select
from starlette.templating import Jinja2Templates

from app.auth import (
    hash_password,
    verify_password,
    create_session_token,
    hash_session_token,
)

BASE = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    engine = create_engine(DATABASE_URL)
else:
    DB_PATH = BASE.parent / "dental_ai.db"
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    role: str
    display_name: str
    password_hash: Optional[str] = None
    email: Optional[str] = Field(default=None, index=True)
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

class DoctorProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, unique=True)
    university: Optional[str] = None
    graduation_status: Optional[str] = None
    graduation_year: Optional[int] = None
    is_specialist: bool = False
    specialty: Optional[str] = None



class UserAccountMeta(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, unique=True)
    professional_title: Optional[str] = None
    username_changed_at: Optional[datetime] = None


class AgreementAcceptance(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    agreement_type: str = Field(index=True)
    agreement_version: str
    accepted_at: datetime = Field(default_factory=datetime.utcnow)



class PatientProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(index=True, unique=True)
    address: Optional[str] = None


class SessionToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token_hash: str = Field(index=True)
    user_id: int = Field(index=True)
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PasswordResetToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    token_hash: str = Field(index=True)
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Patient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    anonymous_id: str = Field(index=True)
    tc_kimlik_no: Optional[str] = Field(default=None, index=True)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    birth_date: Optional[str] = None
    age: Optional[int] = None
    chief_complaint: Optional[str] = None
    owner_user_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Analysis(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(index=True)
    tooth_number: Optional[str] = None
    image_path: Optional[str] = None
    radiograph_path: Optional[str] = None
    clinical_notes: Optional[str] = None
    status: str = "DRAFT"
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ToothStatus(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(index=True)
    tooth_number: str = Field(index=True)
    status: str = "HEALTHY"
    note: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ToothSurfaceStatus(SQLModel, table=True):
    __tablename__ = "toothsurfacestatus"

    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(index=True)
    tooth_number: str = Field(index=True)
    surface: str
    status: str = "HEALTHY"
    note: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Treatment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(index=True)
    tooth_number: Optional[str] = Field(default=None, index=True)
    treatment_name: str
    treatment_date: Optional[str] = None
    material: Optional[str] = None
    doctor_note: Optional[str] = None
    result: Optional[str] = None
    analysis_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ImageAsset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    analysis_id: int = Field(index=True)
    original_filename: str
    stored_filename: str
    file_path: str
    image_type: str = "OTHER"
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class PatientMedia(SQLModel, table=True):
    """Hastaya ait uzun süreli klinik fotoğraf/röntgen arşivi."""
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(index=True)
    owner_user_id: int = Field(index=True)
    original_filename: str
    stored_filename: str = Field(index=True)
    file_path: str
    media_type: str = Field(default="PHOTO", index=True)
    tooth_number: Optional[str] = None
    note: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class GuestAnalysis(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    tooth_number: Optional[str] = None
    clinical_notes: Optional[str] = None
    status: str = "DRAFT"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GuestImageAsset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    guest_analysis_id: int = Field(index=True)
    original_filename: str
    stored_filename: str
    file_path: str
    image_type: str = "OTHER"
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class ClinicalRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    clinical_id: str = Field(index=True)
    topic: str
    clinical_question: str
    claim: str
    evidence_grade: str = "UNASSESSED"
    consensus_status: str = "UNASSESSED"
    ai_use: str = "NOT_DEFINED"
    safety_notes: Optional[str] = None


class StudyCourse(SQLModel, table=True):
    """Kullanıcıya ait akademik ders klasörü."""
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    title: str = Field(index=True)
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class StudyMaterial(SQLModel, table=True):
    """Bir ders altındaki özel PDF veya görsel not dosyası."""
    id: Optional[int] = Field(default=None, primary_key=True)
    course_id: int = Field(index=True)
    owner_user_id: int = Field(index=True)
    original_filename: str
    display_name: str
    stored_filename: str = Field(index=True)
    file_path: str
    material_type: str = Field(index=True)
    mime_type: str
    size_bytes: int
    gemini_file_name: Optional[str] = None
    gemini_file_uri: Optional[str] = None
    gemini_file_expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class StudyChatMessage(SQLModel, table=True):
    """Ders bazlı çok turlu Akademik AI sohbet geçmişi."""
    id: Optional[int] = Field(default=None, primary_key=True)
    course_id: int = Field(index=True)
    owner_user_id: int = Field(index=True)
    role: str = Field(index=True)
    content: str
    source_ids_json: Optional[str] = None
    mode: str = "NOTES_PLUS"
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class ScheduleEvent(SQLModel, table=True):
    """Kullanıcının ders, randevu, görev ve klinik program kayıtları.

    Tarihler UTC olarak saklanır. timezone_name alanı, ileride Android/iOS
    bildirimlerinin doğru yerel saate kurulabilmesi için kayıtla birlikte tutulur.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    event_type: str = Field(index=True)
    title: str
    start_at: datetime = Field(index=True)
    end_at: Optional[datetime] = None
    patient_id: Optional[int] = Field(default=None, index=True)
    location: Optional[str] = None
    notes: Optional[str] = None
    status: str = Field(default="ACTIVE", index=True)
    reminder_minutes: Optional[int] = 30
    notification_enabled: bool = True
    recurrence_rule: str = "NONE"
    recurrence_until: Optional[str] = None
    timezone_name: str = "Europe/Istanbul"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


PROFESSIONAL_TITLES = {
    "Öğrenci",
    "Diş Hekimi",
    "Uzman Diş Hekimi",
    "Asistan / Araştırma Görevlisi",
    "Dr. Öğr. Üyesi",
    "Doç. Dr.",
    "Prof. Dr.",
}

PROGRAM_EVENT_TYPES = {
    "APPOINTMENT": "Hasta / Randevu",
    "CLASS": "Ders",
    "CLINIC": "Klinik / Pratik",
    "EXAM": "Sınav",
    "ASSIGNMENT": "Ödev",
    "THESIS": "Tez",
    "MEETING": "Toplantı",
    "TASK": "Görev",
    "PERSONAL": "Kişisel",
}

PROGRAM_TYPE_ICONS = {
    "APPOINTMENT": "tooth",
    "CLASS": "book",
    "CLINIC": "clinic",
    "EXAM": "exam",
    "ASSIGNMENT": "assignment",
    "THESIS": "thesis",
    "MEETING": "meeting",
    "TASK": "task",
    "PERSONAL": "personal",
}

REMINDER_OPTIONS = {0, 15, 30, 60, 120, 1440}
RECURRENCE_OPTIONS = {"NONE", "WEEKLY"}

try:
    APP_TIMEZONE = ZoneInfo("Europe/Istanbul")
except Exception:
    APP_TIMEZONE = timezone(timedelta(hours=3))


def _local_to_utc(value: str) -> datetime:
    local_dt = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    aware_local = local_dt.replace(tzinfo=APP_TIMEZONE)
    return aware_local.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_to_local(value: Optional[datetime]) -> Optional[datetime]:
    if not value:
        return None
    aware_utc = value.replace(tzinfo=timezone.utc)
    return aware_utc.astimezone(APP_TIMEZONE).replace(tzinfo=None)


def _date_to_local_start(value: date) -> datetime:
    return datetime.combine(value, time.min)


def _date_to_local_end(value: date) -> datetime:
    return datetime.combine(value, time.max)


def _professional_group(title: Optional[str]) -> str:
    if title == "Öğrenci":
        return "STUDENT"
    if title == "Asistan / Araştırma Görevlisi":
        return "ASSISTANT"
    if title in {"Dr. Öğr. Üyesi", "Doç. Dr.", "Prof. Dr."}:
        return "ACADEMIC"
    return "DENTIST"


def _dashboard_actions(title: Optional[str]):
    group = _professional_group(title)
    actions = {
        "new_patient": {"key": "new_patient", "label": "Yeni Hasta", "href": "/patients/new", "hint": "Hasta kaydı oluştur"},
        "ai": {"key": "ai", "label": "Dental AI", "href": "/analysis/new", "hint": "Yeni analiz başlat"},
        "tooth": {"key": "tooth", "label": "Diş Şeması", "href": "/tooth-charts", "hint": "Kayıtlı şemalara ulaş"},
        "program": {"key": "program", "label": "Programım", "href": "/program", "hint": "Ders ve randevular"},
        "appointment": {"key": "appointment", "label": "Randevu Ekle", "href": "/program/new?type=APPOINTMENT", "hint": "Hasta randevusu oluştur"},
        "patients": {"key": "patients", "label": "Hastalar", "href": "/patients", "hint": "Hasta listesini aç"},
        "notes": {"key": "notes", "label": "Notlarım", "href": "/notes", "hint": "Ders notları ve Akademik AI"},
    }
    # Dental AI ana ekranda ayrı, belirgin bir analiz çağrısı olarak gösterilir.
    # Hızlı Başlangıç alanı bu yüzden tamamlayıcı günlük araçlara ayrılır.
    if group == "STUDENT":
        order = ["new_patient", "notes", "patients", "tooth"]
    elif group == "ASSISTANT":
        order = ["program", "patients", "appointment", "tooth"]
    elif group == "ACADEMIC":
        order = ["program", "patients", "appointment", "tooth"]
    else:
        order = ["new_patient", "appointment", "patients", "tooth"]
    return [actions[key] for key in order]


def _dashboard_copy(title: Optional[str]):
    group = _professional_group(title)
    if group == "STUDENT":
        return {"eyebrow": "Öğrenci çalışma alanı", "subtitle": "Derslerinizi, klinik pratiğinizi, hastalarınızı ve Dental AI araçlarını tek yerden takip edin."}
    if group == "ASSISTANT":
        return {"eyebrow": "Asistan çalışma alanı", "subtitle": "Klinik, ders, tez, görev ve hastalarınızı tek akışta yönetin."}
    if group == "ACADEMIC":
        return {"eyebrow": "Akademik çalışma alanı", "subtitle": "Ders, hasta, klinik ve akademik programınızı günlük akışta takip edin."}
    return {"eyebrow": "Klinik çalışma alanı", "subtitle": "Randevularınızı, hastalarınızı ve Dental AI araçlarını hızlıca yönetin."}


def _dashboard_greeting(local_now: datetime) -> str:
    """Ana ekranda kısa, mesleki unvandan bağımsız selamlama üretir."""
    hour = local_now.hour
    if 5 <= hour < 12:
        return "Günaydın"
    if 18 <= hour or hour < 5:
        return "İyi akşamlar"
    return "Merhaba"


def _normalize_patient_name(value: Optional[str]) -> str:
    return " ".join((value or "").strip().casefold().split())


def _normalize_patient_phone(value: Optional[str]) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("90"):
        digits = "0" + digits[2:]
    elif len(digits) == 10 and digits.startswith("5"):
        digits = "0" + digits
    return digits


def _find_duplicate_patient(
    session: Session,
    owner_user_id: int,
    first_name: str,
    last_name: str,
    birth_date: Optional[str],
    age: Optional[int],
    phone: Optional[str],
):
    """Yalnızca aynı hekimin kendi hastaları içinde olası mükerrer kaydı bulur.

    Otomatik birleştirme veya engelleme yapmaz. En güçlü eşleşme kullanıcıya
    gösterilir ve hekim isterse yine de yeni kayıt oluşturabilir.
    """
    candidates = session.exec(
        select(Patient)
        .where(Patient.owner_user_id == owner_user_id)
        .order_by(Patient.id.desc())
    ).all()

    wanted_first = _normalize_patient_name(first_name)
    wanted_last = _normalize_patient_name(last_name)
    wanted_phone = _normalize_patient_phone(phone)
    matches = []

    for patient in candidates:
        score = 0
        reason = None
        existing_phone = _normalize_patient_phone(patient.phone)
        same_name = (
            _normalize_patient_name(patient.first_name) == wanted_first
            and _normalize_patient_name(patient.last_name) == wanted_last
        )

        if wanted_phone and existing_phone and wanted_phone == existing_phone:
            score = 100
            reason = "Telefon numarası eşleşiyor."

        if same_name and birth_date and patient.birth_date == birth_date and score < 98:
            score = 98
            reason = "Ad, soyad ve doğum tarihi eşleşiyor."
        elif same_name and age is not None and patient.age is not None and patient.age == age and score < 85:
            score = 85
            reason = "Ad, soyad ve yaş eşleşiyor."

        if score:
            matches.append((score, patient.id or 0, patient, reason))

    if not matches:
        return None, None

    matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, patient, reason = matches[0]
    return patient, reason


def _event_occurrences(event: ScheduleEvent, range_start: datetime, range_end: datetime):
    """Bir program kaydının belirtilen yerel tarih aralığındaki görünümlerini üretir."""
    anchor_start = _utc_to_local(event.start_at)
    anchor_end = _utc_to_local(event.end_at) if event.end_at else None
    if not anchor_start:
        return []

    duration = (anchor_end - anchor_start) if anchor_end else None
    until_date = None
    if event.recurrence_until:
        try:
            until_date = datetime.strptime(event.recurrence_until, "%Y-%m-%d").date()
        except ValueError:
            until_date = None

    starts = []
    if event.recurrence_rule == "WEEKLY":
        current = anchor_start
        if current < range_start:
            delta_days = (range_start.date() - current.date()).days
            weeks = max(0, delta_days // 7)
            current = current + timedelta(weeks=weeks)
            while current < range_start:
                current += timedelta(weeks=1)
        safety = 0
        while current <= range_end and safety < 60:
            if not until_date or current.date() <= until_date:
                starts.append(current)
            current += timedelta(weeks=1)
            safety += 1
    else:
        if anchor_start <= range_end and (anchor_end or anchor_start) >= range_start:
            starts.append(anchor_start)

    result = []
    for local_start in starts:
        local_end = local_start + duration if duration else None
        result.append({
            "id": event.id,
            "event_type": event.event_type,
            "type_label": PROGRAM_EVENT_TYPES.get(event.event_type, "Program"),
            "icon_key": PROGRAM_TYPE_ICONS.get(event.event_type, "task"),
            "title": event.title,
            "start_local": local_start,
            "end_local": local_end,
            "patient_id": event.patient_id,
            "location": event.location,
            "notes": event.notes,
            "status": event.status,
            "notification_enabled": event.notification_enabled,
            "reminder_minutes": event.reminder_minutes,
            "recurrence_rule": event.recurrence_rule,
            "is_recurring": event.recurrence_rule != "NONE",
        })
    return result


def _user_schedule_occurrences(session: Session, user_id: int, range_start: datetime, range_end: datetime):
    events = session.exec(
        select(ScheduleEvent)
        .where(ScheduleEvent.owner_user_id == user_id)
        .where(ScheduleEvent.status != "DELETED")
        .order_by(ScheduleEvent.start_at)
    ).all()

    occurrences = []
    for event in events:
        occurrences.extend(_event_occurrences(event, range_start, range_end))

    patient_ids = {item["patient_id"] for item in occurrences if item.get("patient_id")}
    patient_map = {}
    if patient_ids:
        patients = session.exec(
            select(Patient)
            .where(Patient.id.in_(patient_ids))
            .where(Patient.owner_user_id == user_id)
        ).all()
        patient_map = {patient.id: patient for patient in patients}

    for item in occurrences:
        patient = patient_map.get(item.get("patient_id"))
        item["patient"] = patient
    return sorted(occurrences, key=lambda item: item["start_local"])


def _program_range(view: str, focus_date: date):
    view = view if view in {"today", "week", "month"} else "week"
    if view == "today":
        start_date = focus_date
        end_date = focus_date
        previous = focus_date - timedelta(days=1)
        following = focus_date + timedelta(days=1)
    elif view == "month":
        start_date = focus_date.replace(day=1)
        if start_date.month == 12:
            next_month = start_date.replace(year=start_date.year + 1, month=1)
        else:
            next_month = start_date.replace(month=start_date.month + 1)
        end_date = next_month - timedelta(days=1)
        previous = (start_date - timedelta(days=1)).replace(day=1)
        following = next_month
    else:
        start_date = focus_date - timedelta(days=focus_date.weekday())
        end_date = start_date + timedelta(days=6)
        previous = focus_date - timedelta(days=7)
        following = focus_date + timedelta(days=7)
    return (
        view,
        _date_to_local_start(start_date),
        _date_to_local_end(end_date),
        previous,
        following,
    )


def _group_program_occurrences(occurrences):
    groups = []
    current = None
    for item in occurrences:
        item_date = item["start_local"].date()
        if current is None or current["date"] != item_date:
            current = {
                "date": item_date,
                "label": item_date.strftime("%d.%m.%Y"),
                "events": [],
            }
            groups.append(current)
        current["events"].append(item)
    return groups


def _owned_patient(session: Session, user: User, patient_id: Optional[int]):
    if not patient_id:
        return None
    patient = session.get(Patient, patient_id)
    if not patient:
        return None
    if user.role != "ADMIN" and patient.owner_user_id != user.id:
        return None
    if user.role == "ADMIN" and patient.owner_user_id not in {None, user.id}:
        return None
    return patient


def _validate_schedule_input(
    session: Session,
    user: User,
    event_type: str,
    title: str,
    start_at: str,
    end_at: str,
    patient_id: str,
    location: str,
    notes: str,
    reminder_minutes: str,
    notification_enabled: Optional[str],
    recurrence_rule: str,
    recurrence_until: str,
):
    event_type = event_type.strip().upper()
    title = title.strip()
    location = location.strip()
    notes = notes.strip()
    recurrence_rule = recurrence_rule.strip().upper() or "NONE"
    recurrence_until = recurrence_until.strip()

    if event_type not in PROGRAM_EVENT_TYPES:
        return None, "Geçerli bir program türü seçin."
    if len(title) < 2 or len(title) > 160:
        return None, "Başlık 2 ile 160 karakter arasında olmalıdır."

    try:
        start_utc = _local_to_utc(start_at)
    except (TypeError, ValueError):
        return None, "Başlangıç tarih ve saatini kontrol edin."

    end_utc = None
    if end_at.strip():
        try:
            end_utc = _local_to_utc(end_at)
        except (TypeError, ValueError):
            return None, "Bitiş tarih ve saatini kontrol edin."
        if end_utc < start_utc:
            return None, "Bitiş saati başlangıç saatinden önce olamaz."

    parsed_patient_id = None
    if patient_id.strip():
        try:
            parsed_patient_id = int(patient_id)
        except ValueError:
            return None, "Hasta seçimini kontrol edin."
        patient = _owned_patient(session, user, parsed_patient_id)
        if not patient:
            return None, "Bu hastayı program kaydına bağlama yetkiniz yok."

    try:
        reminder_value = int(reminder_minutes)
    except (TypeError, ValueError):
        reminder_value = 30
    if reminder_value not in REMINDER_OPTIONS:
        return None, "Hatırlatma süresi geçersiz."

    if recurrence_rule not in RECURRENCE_OPTIONS:
        return None, "Tekrarlama seçeneği geçersiz."

    if recurrence_until:
        try:
            until = datetime.strptime(recurrence_until, "%Y-%m-%d").date()
        except ValueError:
            return None, "Tekrar bitiş tarihini kontrol edin."
        local_start = _utc_to_local(start_utc)
        if local_start and until < local_start.date():
            return None, "Tekrar bitiş tarihi başlangıç tarihinden önce olamaz."
    elif recurrence_rule == "NONE":
        recurrence_until = ""

    return {
        "event_type": event_type,
        "title": title,
        "start_at": start_utc,
        "end_at": end_utc,
        "patient_id": parsed_patient_id,
        "location": location or None,
        "notes": notes or None,
        "reminder_minutes": reminder_value,
        "notification_enabled": bool(notification_enabled),
        "recurrence_rule": recurrence_rule,
        "recurrence_until": recurrence_until or None,
        "timezone_name": "Europe/Istanbul",
    }, None


STUDY_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
STUDY_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
STUDY_MAX_FILE_BYTES = 25 * 1024 * 1024
STUDY_MAX_UPLOAD_COUNT = 12
STUDY_AI_MAX_SOURCES = 20


def _owned_study_course(session: Session, user: User, course_id: int) -> Optional[StudyCourse]:
    course = session.get(StudyCourse, course_id)
    if not course:
        return None
    if user.role != "ADMIN" and course.owner_user_id != user.id:
        return None
    if user.role == "ADMIN" and course.owner_user_id != user.id:
        # Admin olmak kullanıcının özel akademik notlarına otomatik erişim vermez.
        return None
    return course


def _owned_study_material(
    session: Session,
    user: User,
    course_id: int,
    material_id: int,
) -> Optional[StudyMaterial]:
    course = _owned_study_course(session, user, course_id)
    if not course:
        return None
    material = session.get(StudyMaterial, material_id)
    if not material or material.course_id != course_id or material.owner_user_id != user.id:
        return None
    return material


def _study_file_has_valid_signature(path: Path, extension: str) -> bool:
    try:
        with path.open("rb") as source:
            header = source.read(16)
    except OSError:
        return False
    if extension == ".pdf":
        return header.startswith(b"%PDF-")
    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    return False


def _study_mime_type(extension: str) -> Optional[str]:
    return {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(extension)


def _parse_study_material_ids(raw_value: Optional[str]) -> list[int]:
    result: list[int] = []
    for raw in (raw_value or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value > 0 and value not in result:
            result.append(value)
    return result



def init_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as s:
        if not s.exec(select(User)).first():
            s.add(User(username="admin", role="ADMIN", display_name="DENTAL-AI Administrator"))
            s.add(User(username="doctor", role="DOCTOR", display_name="Demo Dentist"))
        if not s.exec(select(ClinicalRecord)).first():
            s.add(ClinicalRecord(
                clinical_id="CARIES-DX",
                topic="Dental Caries",
                clinical_question="How should dental caries be detected and assessed?",
                claim="RESEARCH REQUIRED — no clinical rule is activated yet.",
                safety_notes="Do not use this prototype for clinical diagnosis or treatment."
            ))
        s.commit()



SESSION_COOKIE = "dental_ai_session"
SESSION_DAYS = 7


def get_current_user(request: Request) -> Optional[User]:
    token = request.cookies.get(SESSION_COOKIE)

    if not token:
        return None

    token_hash = hash_session_token(token)

    with Session(engine, expire_on_commit=False) as s:
        session_token = s.exec(
            select(SessionToken).where(
                SessionToken.token_hash == token_hash
            )
        ).first()

        if not session_token:
            return None

        if session_token.expires_at <= datetime.utcnow():
            s.delete(session_token)
            s.commit()
            return None

        user = s.get(User, session_token.user_id)

        if not user or not user.is_active:
            return None

        return user


def create_user_session(response: RedirectResponse, user_id: int) -> None:
    token = create_session_token()

    expires_at = datetime.utcnow().replace(
        microsecond=0
    )

    from datetime import timedelta
    expires_at = expires_at + timedelta(days=SESSION_DAYS)

    session_token = SessionToken(
        token_hash=hash_session_token(token),
        user_id=user_id,
        expires_at=expires_at,
    )

    with Session(engine, expire_on_commit=False) as s:
        s.add(session_token)
        s.commit()

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=False,
    )


def delete_user_session(request: Request) -> None:
    token = request.cookies.get(SESSION_COOKIE)

    if not token:
        return

    token_hash = hash_session_token(token)

    with Session(engine, expire_on_commit=False) as s:
        session_token = s.exec(
            select(SessionToken).where(
                SessionToken.token_hash == token_hash
            )
        ).first()

        if session_token:
            s.delete(session_token)
            s.commit()


def send_brevo_password_reset_email(
    recipient_email: str,
    reset_link: str,
) -> None:
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "destek@dentalai.tr")
    sender_name = os.getenv("BREVO_SENDER_NAME", "DENTAL AI Destek")

    if not api_key:
        raise RuntimeError("BREVO_API_KEY tanımlı değil.")

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email,
        },
        "to": [
            {
                "email": recipient_email,
            }
        ],
        "subject": "DENTAL AI - Şifre Sıfırlama",
        "htmlContent": f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;">
            <h2>🦷 DENTAL AI</h2>
            <p>Şifrenizi sıfırlamak için aşağıdaki butona tıklayın:</p>
            <p>
                <a href="{reset_link}"
                   style="display:inline-block;padding:12px 20px;
                          background:#2563eb;color:#fff;
                          text-decoration:none;border-radius:8px;">
                    Şifremi Sıfırla
                </a>
            </p>
            <p>Bu bağlantı 30 dakika boyunca geçerlidir ve yalnızca bir kez kullanılabilir.</p>
            <p>Eğer bu işlemi siz başlatmadıysanız bu e-postayı dikkate almayın.</p>
        </div>
        """,
        "textContent": (
            "DENTAL AI şifre sıfırlama bağlantınız: "
            + reset_link
            + "\n\nBu bağlantı 30 dakika boyunca geçerlidir ve yalnızca bir kez kullanılabilir."
        ),
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=data,
        method="POST",
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(
                    f"Brevo e-posta gönderimi başarısız: HTTP {response.status}"
                )
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Brevo e-posta gönderimi başarısız: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "Brevo e-posta gönderimi sırasında bağlantı hatası oluştu."
        ) from exc


app = FastAPI(title="DENTAL-AI", version="0.1.0")



@app.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="info_page.html",
        context={
            "page": "about",
            "title": "Hakkında",
        },
    )


@app.get("/legal", response_class=HTMLResponse)
def legal_index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="info_page.html",
        context={
            "page": "legal",
            "title": "Sözleşmeler ve Politikalar",
        },
    )


@app.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="info_page.html",
        context={
            "page": "contact",
            "title": "İletişim",
        },
    )


@app.get("/legal/{document}", response_class=HTMLResponse)
def legal_document(request: Request, document: str):
    legal = LEGAL_TEXTS.get(document)

    if not legal:
        return HTMLResponse(
            "Hukuki metin bulunamadı.",
            status_code=404,
        )

    return templates.TemplateResponse(
        request=request,
        name="legal.html",
        context={
            "title": legal["title"],
            "content": legal["content"],
            "version": LEGAL_VERSION,
        },
    )


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={"error": None},
    )


@app.post("/register")
def register_user(
    request: Request,
    display_name: str = Form(...),
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    university: str = Form(...),
    professional_title: str = Form(...),
    specialty: str = Form(""),
    accept_terms: Optional[str] = Form(None),
    kvkk_informed: Optional[str] = Form(None),
    accept_clinical: Optional[str] = Form(None),
):
    display_name = display_name.strip()
    email = email.strip().lower()
    username = username.strip().lower()
    university = university.strip()
    professional_title = professional_title.strip()
    specialty = specialty.strip()

    if professional_title not in PROFESSIONAL_TITLES:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"error": "Geçerli bir mesleki unvan seçin."},
            status_code=400,
        )

    is_student = professional_title == "Öğrenci"
    is_specialist_bool = professional_title in {
        "Uzman Diş Hekimi", "Dr. Öğr. Üyesi", "Doç. Dr.", "Prof. Dr."
    }
    graduation_status = "Öğrenci" if is_student else "Mezun"

    if is_student:
        specialty = ""

    if not accept_terms or not kvkk_informed or not accept_clinical:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "error": "Üyelik koşulları, KVKK bilgilendirmesi ve klinik kullanım koşulları onaylanmalıdır.",
            },
            status_code=400,
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Şifre en az 8 karakter olmalıdır.",
            },
            status_code=400,
        )

    if len(username) < 8:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Kullanıcı adı en az 8 karakter olmalıdır.",
            },
            status_code=400,
        )

    if not display_name or not email or not username or not university or not professional_title:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Tüm alanları doldurun.",
            },
            status_code=400,
        )

    if is_specialist_bool and not specialty:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Seçtiğiniz unvan için uzmanlık alanını yazmalısınız.",
            },
            status_code=400,
        )

    with Session(engine, expire_on_commit=False) as s:
        existing_username = s.exec(
            select(User).where(User.username == username)
        ).first()

        if existing_username:
            return templates.TemplateResponse(
                request=request,
                name="register.html",
                context={"error": "Bu kullanıcı adı zaten kullanılıyor."},
                status_code=400,
            )

        existing_email = s.exec(
            select(User).where(User.email == email)
        ).first()

        if existing_email:
            return templates.TemplateResponse(
                request=request,
                name="register.html",
                context={"error": "Bu e-posta adresi zaten kayıtlı."},
                status_code=400,
            )

        user = User(
            username=username,
            role="DOCTOR",
            display_name=display_name,
            password_hash=hash_password(password),
            email=email,
            is_active=True,
        )

        s.add(user)
        s.commit()
        s.refresh(user)

        doctor_profile = DoctorProfile(
            user_id=user.id,
            university=university,
            graduation_status=graduation_status,
            graduation_year=None,
            is_specialist=is_specialist_bool,
            specialty=specialty if is_specialist_bool else None,
        )
        s.add(doctor_profile)
        s.add(UserAccountMeta(
            user_id=user.id,
            professional_title=professional_title,
        ))

        agreement_records = [
            AgreementAcceptance(
                user_id=user.id,
                agreement_type="TERMS",
                agreement_version=LEGAL_VERSION,
            ),
            AgreementAcceptance(
                user_id=user.id,
                agreement_type="KVKK_INFORMATION",
                agreement_version=LEGAL_VERSION,
            ),
            AgreementAcceptance(
                user_id=user.id,
                agreement_type="CLINICAL_TERMS",
                agreement_version=LEGAL_VERSION,
            ),
        ]

        for agreement in agreement_records:
            s.add(agreement)

        s.commit()

        response = RedirectResponse(
            url="/",
            status_code=303,
        )

        create_user_session(response, user.id)

        return response


@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request):
    user = get_current_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        doctor_profile = s.exec(
            select(DoctorProfile).where(DoctorProfile.user_id == user.id)
        ).first()
        account_meta = s.exec(
            select(UserAccountMeta).where(UserAccountMeta.user_id == user.id)
        ).first()

    next_username_change_at = None
    if account_meta and account_meta.username_changed_at:
        next_username_change_at = account_meta.username_changed_at + timedelta(days=15)

    return templates.TemplateResponse(
        request=request,
        name="account.html",
        context={
            "user": user,
            "doctor_profile": doctor_profile,
            "account_meta": account_meta,
            "next_username_change_at": next_username_change_at,
            "error": None,
            "success": (
                "Mesleki durumunuz güncellendi. Ana ekran öncelikleriniz yeni durumunuza göre düzenlendi; mevcut kayıtlarınız silinmedi."
                if request.query_params.get("profile_updated") == "1"
                else None
            ),
        },
    )


@app.post("/account/professional-title")
def change_professional_title(
    request: Request,
    professional_title: str = Form(...),
    confirm_change: str = Form(""),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    professional_title = professional_title.strip()
    if professional_title not in PROFESSIONAL_TITLES:
        return HTMLResponse("Geçerli bir mesleki durum seçin.", status_code=400)

    with Session(engine, expire_on_commit=False) as s:
        account_meta = s.exec(
            select(UserAccountMeta).where(UserAccountMeta.user_id == user.id)
        ).first()
        current_title = account_meta.professional_title if account_meta and account_meta.professional_title else None

        # Mesleki durum değişikliği yalnız arayüz önceliklerini değiştirir.
        # Hasta, Notlarım, Akademik AI, Programım veya diğer kullanıcı verileri burada silinmez.
        if current_title and current_title != professional_title and confirm_change != "yes":
            return HTMLResponse("Mesleki durum değişikliği için ikinci onay gereklidir.", status_code=400)

        if not account_meta:
            account_meta = UserAccountMeta(user_id=user.id)

        account_meta.professional_title = professional_title
        s.add(account_meta)

        doctor_profile = s.exec(
            select(DoctorProfile).where(DoctorProfile.user_id == user.id)
        ).first()
        if doctor_profile:
            doctor_profile.graduation_status = (
                "Öğrenci" if professional_title == "Öğrenci" else "Mezun"
            )
            doctor_profile.is_specialist = professional_title in {
                "Uzman Diş Hekimi", "Dr. Öğr. Üyesi", "Doç. Dr.", "Prof. Dr."
            }
            s.add(doctor_profile)

        s.commit()

    return RedirectResponse("/account?profile_updated=1", status_code=303)


@app.post("/account/username", response_class=HTMLResponse)
def change_username(request: Request, username: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    username = username.strip().lower()
    now = datetime.utcnow()

    with Session(engine, expire_on_commit=False) as s:
        db_user = s.get(User, user.id)
        doctor_profile = s.exec(
            select(DoctorProfile).where(DoctorProfile.user_id == user.id)
        ).first()
        account_meta = s.exec(
            select(UserAccountMeta).where(UserAccountMeta.user_id == user.id)
        ).first()

        def render_account(error=None, success=None, status_code=200):
            next_change = None
            if account_meta and account_meta.username_changed_at:
                next_change = account_meta.username_changed_at + timedelta(days=15)
            return templates.TemplateResponse(
                request=request, name="account.html",
                context={
                    "user": db_user or user,
                    "doctor_profile": doctor_profile,
                    "account_meta": account_meta,
                    "next_username_change_at": next_change,
                    "error": error, "success": success,
                },
                status_code=status_code,
            )

        if not db_user:
            return RedirectResponse("/login", status_code=303)
        if len(username) < 8:
            return render_account("Kullanıcı adı en az 8 karakter olmalıdır.", status_code=400)
        if username == db_user.username:
            return render_account("Yeni kullanıcı adı mevcut kullanıcı adınızla aynı.", status_code=400)

        if account_meta and account_meta.username_changed_at:
            next_change = account_meta.username_changed_at + timedelta(days=15)
            if now < next_change:
                return render_account(
                    f"Kullanıcı adınızı tekrar {next_change.strftime('%d.%m.%Y %H:%M')} tarihinden sonra değiştirebilirsiniz.",
                    status_code=429,
                )

        existing = s.exec(select(User).where(User.username == username)).first()
        if existing and existing.id != db_user.id:
            return render_account("Bu kullanıcı adı zaten kullanılıyor.", status_code=400)

        db_user.username = username
        s.add(db_user)
        if not account_meta:
            account_meta = UserAccountMeta(user_id=db_user.id)
        account_meta.username_changed_at = now
        s.add(account_meta)
        s.commit()
        s.refresh(db_user)
        s.refresh(account_meta)

        return render_account(success="Kullanıcı adınız başarıyla değiştirildi. 15 gün boyunca tekrar değiştirilemez.")


@app.post("/account/password", response_class=HTMLResponse)
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    def render_account(error=None, success=None, status_code=200):
        with Session(engine, expire_on_commit=False) as s:
            db_user = s.get(User, user.id) or user
            doctor_profile = s.exec(
                select(DoctorProfile).where(DoctorProfile.user_id == user.id)
            ).first()
            account_meta = s.exec(
                select(UserAccountMeta).where(UserAccountMeta.user_id == user.id)
            ).first()
        next_change = None
        if account_meta and account_meta.username_changed_at:
            next_change = account_meta.username_changed_at + timedelta(days=15)
        return templates.TemplateResponse(
            request=request,
            name="account.html",
            context={
                "user": db_user,
                "doctor_profile": doctor_profile,
                "account_meta": account_meta,
                "next_username_change_at": next_change,
                "error": error,
                "success": success,
            },
            status_code=status_code,
        )

    if not user.password_hash or not verify_password(current_password, user.password_hash):
        return render_account("Mevcut şifreniz hatalı.", status_code=400)
    if len(new_password) < 8:
        return render_account("Yeni şifre en az 8 karakter olmalıdır.", status_code=400)
    if new_password != new_password_confirm:
        return render_account("Yeni şifreler eşleşmiyor.", status_code=400)

    with Session(engine, expire_on_commit=False) as s:
        db_user = s.get(User, user.id)
        if not db_user:
            return RedirectResponse("/login", status_code=303)
        db_user.password_hash = hash_password(new_password)
        s.add(db_user)
        s.commit()

    return render_account(success="Şifreniz başarıyla değiştirildi.")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, reset: str = ""):
    message = (
        "Şifreniz başarıyla değiştirildi. Yeni şifrenizle giriş yapabilirsiniz."
        if reset == "success"
        else None
    )
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "message": message},
    )


@app.post("/login")
def login_user(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    login = login.strip().lower()

    with Session(engine, expire_on_commit=False) as s:
        user = s.exec(
            select(User).where(
                (User.username == login)
                | (User.email == login)
            )
        ).first()

        if (
            not user
            or not user.is_active
            or not user.password_hash
            or not verify_password(password, user.password_hash)
        ):
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={"error": "Kullanıcı adı/e-posta veya şifre hatalı."},
                status_code=401,
            )

        response = RedirectResponse(
            url="/",
            status_code=303,
        )

        create_user_session(response, user.id)

        return response


@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="forgot_password.html",
        context={"error": None, "message": None},
    )


@app.post("/forgot-password")
def forgot_password_request(
    request: Request,
    email: str = Form(...),
):
    email = email.strip().lower()

    generic_message = (
        "Eğer bu e-posta adresi kayıtlıysa, "
        "şifre sıfırlama bağlantısı gönderilecektir."
    )

    with Session(engine, expire_on_commit=False) as s:
        user = s.exec(
            select(User).where(User.email == email)
        ).first()

        if user and user.is_active and user.password_hash:
            now = datetime.utcnow()

            old_tokens = s.exec(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == user.id,
                    PasswordResetToken.used_at == None,
                    PasswordResetToken.expires_at > now,
                )
            ).all()

            for old_token in old_tokens:
                old_token.used_at = now

            raw_token = secrets.token_urlsafe(32)
            token_hash = hash_session_token(raw_token)

            reset_token = PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=now + __import__("datetime").timedelta(minutes=30),
            )

            s.add(reset_token)
            s.commit()

            public_base_url = os.getenv(
                "PUBLIC_BASE_URL",
                str(request.base_url).rstrip("/"),
            ).rstrip("/")

            reset_link = (
                f"{public_base_url}/reset-password"
                f"?token={raw_token}"
            )

            try:
                send_brevo_password_reset_email(
                    recipient_email=user.email,
                    reset_link=reset_link,
                )
            except Exception:
                # Token DB'de kalsa bile kullanıcıya bilgi sızdırmıyoruz.
                # Gerçek hata ayrıntısı kullanıcıya gösterilmez.
                pass

    return templates.TemplateResponse(
        request=request,
        name="forgot_password.html",
        context={
            "error": None,
            "message": generic_message,
        },
    )


@app.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(
    request: Request,
    token: str = "",
):
    token_hash = hash_session_token(token) if token else ""

    valid_token = False

    if token_hash:
        with Session(engine, expire_on_commit=False) as s:
            reset_token = s.exec(
                select(PasswordResetToken).where(
                    PasswordResetToken.token_hash == token_hash,
                    PasswordResetToken.used_at == None,
                    PasswordResetToken.expires_at > datetime.utcnow(),
                )
            ).first()

            valid_token = reset_token is not None

    if not valid_token:
        return templates.TemplateResponse(
            request=request,
            name="reset_password.html",
            context={
                "token": None,
                "error": "Bu şifre sıfırlama bağlantısı geçersiz veya süresi dolmuş.",
                "message": None,
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        request=request,
        name="reset_password.html",
        context={
            "token": token,
            "error": None,
            "message": None,
        },
    )


@app.post("/reset-password")
def reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    token_hash = hash_session_token(token)

    if len(password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="reset_password.html",
            context={
                "token": token,
                "error": "Şifre en az 8 karakter olmalıdır.",
                "message": None,
            },
            status_code=400,
        )

    if password != password_confirm:
        return templates.TemplateResponse(
            request=request,
            name="reset_password.html",
            context={
                "token": token,
                "error": "Şifreler eşleşmiyor.",
                "message": None,
            },
            status_code=400,
        )

    with Session(engine, expire_on_commit=False) as s:
        reset_token = s.exec(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at == None,
                PasswordResetToken.expires_at > datetime.utcnow(),
            )
        ).first()

        if not reset_token:
            return templates.TemplateResponse(
                request=request,
                name="reset_password.html",
                context={
                    "token": None,
                    "error": "Bu şifre sıfırlama bağlantısı geçersiz veya süresi dolmuş.",
                    "message": None,
                },
                status_code=400,
            )

        user = s.get(User, reset_token.user_id)

        if not user or not user.is_active:
            return templates.TemplateResponse(
                request=request,
                name="reset_password.html",
                context={
                    "token": None,
                    "error": "Bu şifre sıfırlama bağlantısı geçersiz.",
                    "message": None,
                },
                status_code=400,
            )

        user.password_hash = hash_password(password)
        reset_token.used_at = datetime.utcnow()

        # Güvenlik: eski oturumları da sonlandır.
        session_tokens = s.exec(
            select(SessionToken).where(
                SessionToken.user_id == user.id
            )
        ).all()

        for session_token in session_tokens:
            s.delete(session_token)

        s.add(user)
        s.add(reset_token)
        s.commit()

    return RedirectResponse(
        url="/login?reset=success",
        status_code=303,
    )


@app.get("/logout")
def logout_user(request: Request):
    delete_user_session(request)

    response = RedirectResponse(
        url="/login",
        status_code=303,
    )

    response.delete_cookie(
        SESSION_COOKIE,
    )

    return response

app.mount("/static", StaticFiles(directory=BASE/"static"), name="static")
@app.get("/uploads/{filename}")
def protected_upload(request: Request, filename: str):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Yetkisiz erişim.", status_code=401)

    safe_name = Path(filename).name
    if safe_name != filename:
        return HTMLResponse("Geçersiz dosya yolu.", status_code=400)

    with Session(engine, expire_on_commit=False) as s:
        asset = s.exec(select(ImageAsset).where(ImageAsset.stored_filename == safe_name)).first()
        if asset:
            analysis = s.get(Analysis, asset.analysis_id)
            patient = s.get(Patient, analysis.patient_id) if analysis else None
            if not analysis or not patient:
                return HTMLResponse("Dosya bulunamadı.", status_code=404)
            if user.role != "ADMIN" and patient.owner_user_id != user.id:
                return HTMLResponse("Bu dosyaya erişim yetkiniz yok.", status_code=403)
            path = Path(asset.file_path)
        else:
            guest_asset = s.exec(
                select(GuestImageAsset).where(GuestImageAsset.stored_filename == safe_name)
            ).first()
            if guest_asset:
                analysis = s.get(GuestAnalysis, guest_asset.guest_analysis_id)
                if not analysis:
                    return HTMLResponse("Dosya bulunamadı.", status_code=404)
                if user.role != "ADMIN" and analysis.owner_user_id != user.id:
                    return HTMLResponse("Bu dosyaya erişim yetkiniz yok.", status_code=403)
                path = Path(guest_asset.file_path)
            else:
                rel = f"uploads/{safe_name}"
                legacy_analysis = s.exec(
                    select(Analysis).where(
                        (Analysis.image_path == rel) | (Analysis.radiograph_path == rel)
                    )
                ).first()
                if not legacy_analysis:
                    return HTMLResponse("Dosya bulunamadı.", status_code=404)
                patient = s.get(Patient, legacy_analysis.patient_id)
                if not patient:
                    return HTMLResponse("Dosya bulunamadı.", status_code=404)
                if user.role != "ADMIN" and patient.owner_user_id != user.id:
                    return HTMLResponse("Bu dosyaya erişim yetkiniz yok.", status_code=403)
                path = UPLOAD_DIR / safe_name

    if not path.is_file():
        return HTMLResponse("Dosya bulunamadı.", status_code=404)
    return FileResponse(path)
def template_user_context(request: Request):
    return {"user": get_current_user(request)}

templates = Jinja2Templates(
    directory=BASE/"templates",
    context_processors=[template_user_context],
)

@app.on_event("startup")
def startup():
    init_db()


@app.get("/notes", response_class=HTMLResponse)
def study_notes_index(request: Request, q: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    query_text = (q or "").strip()
    with Session(engine, expire_on_commit=False) as s:
        course_query = (
            select(StudyCourse)
            .where(StudyCourse.owner_user_id == user.id)
            .order_by(StudyCourse.updated_at.desc())
        )
        if query_text:
            course_query = course_query.where(StudyCourse.title.ilike(f"%{query_text}%"))
        courses = s.exec(course_query).all()
        cards = []
        for course in courses:
            materials = s.exec(
                select(StudyMaterial)
                .where(StudyMaterial.course_id == course.id)
                .where(StudyMaterial.owner_user_id == user.id)
                .order_by(StudyMaterial.created_at.desc())
            ).all()
            cards.append({"course": course, "material_count": len(materials)})

    return templates.TemplateResponse(
        request=request,
        name="notes.html",
        context={"course_cards": cards, "q": query_text},
    )


@app.post("/notes/courses")
def create_study_course(
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    clean_title = " ".join((title or "").strip().split())
    clean_description = (description or "").strip()
    if len(clean_title) < 2 or len(clean_title) > 120:
        return HTMLResponse("Ders adı 2 ile 120 karakter arasında olmalıdır.", status_code=400)
    if len(clean_description) > 500:
        return HTMLResponse("Ders açıklaması en fazla 500 karakter olabilir.", status_code=400)

    course = StudyCourse(
        owner_user_id=user.id,
        title=clean_title,
        description=clean_description or None,
    )
    with Session(engine, expire_on_commit=False) as s:
        s.add(course)
        s.commit()
        s.refresh(course)
    return RedirectResponse(f"/notes/courses/{course.id}", status_code=303)


@app.get("/notes/courses/{course_id}", response_class=HTMLResponse)
def study_course_detail(request: Request, course_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        course = _owned_study_course(s, user, course_id)
        if not course:
            return HTMLResponse("Ders bulunamadı veya erişim yetkiniz yok.", status_code=404)
        materials = s.exec(
            select(StudyMaterial)
            .where(StudyMaterial.course_id == course_id)
            .where(StudyMaterial.owner_user_id == user.id)
            .order_by(StudyMaterial.created_at.desc())
        ).all()
        message_count = len(s.exec(
            select(StudyChatMessage)
            .where(StudyChatMessage.course_id == course_id)
            .where(StudyChatMessage.owner_user_id == user.id)
        ).all())

    return templates.TemplateResponse(
        request=request,
        name="notes_course.html",
        context={"course": course, "materials": materials, "message_count": message_count},
    )


@app.post("/notes/courses/{course_id}/rename")
def rename_study_course(request: Request, course_id: int, title: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    clean_title = " ".join((title or "").strip().split())
    if len(clean_title) < 2 or len(clean_title) > 120:
        return HTMLResponse("Ders adı 2 ile 120 karakter arasında olmalıdır.", status_code=400)
    with Session(engine, expire_on_commit=False) as s:
        course = _owned_study_course(s, user, course_id)
        if not course:
            return HTMLResponse("Ders bulunamadı veya erişim yetkiniz yok.", status_code=404)
        course.title = clean_title
        course.updated_at = datetime.utcnow()
        s.add(course)
        s.commit()
    return RedirectResponse(f"/notes/courses/{course_id}", status_code=303)


@app.post("/notes/courses/{course_id}/delete")
def delete_study_course(request: Request, course_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    local_paths: list[Path] = []
    gemini_names: list[str] = []
    with Session(engine, expire_on_commit=False) as s:
        course = _owned_study_course(s, user, course_id)
        if not course:
            return HTMLResponse("Ders bulunamadı veya erişim yetkiniz yok.", status_code=404)
        materials = s.exec(
            select(StudyMaterial)
            .where(StudyMaterial.course_id == course_id)
            .where(StudyMaterial.owner_user_id == user.id)
        ).all()
        messages = s.exec(
            select(StudyChatMessage)
            .where(StudyChatMessage.course_id == course_id)
            .where(StudyChatMessage.owner_user_id == user.id)
        ).all()
        for material in materials:
            local_paths.append(Path(material.file_path))
            if material.gemini_file_name:
                gemini_names.append(material.gemini_file_name)
            s.delete(material)
        for message in messages:
            s.delete(message)
        delete_course_rag_index(s, owner_user_id=user.id, course_id=course_id)
        s.delete(course)
        s.commit()

    for path in local_paths:
        path.unlink(missing_ok=True)
    for name in gemini_names:
        delete_study_ai_file(name)
    return RedirectResponse("/notes?deleted=1", status_code=303)


@app.post("/notes/courses/{course_id}/materials")
async def upload_study_materials(
    request: Request,
    course_id: int,
    files: list[UploadFile] = File(default=[]),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    selected = [item for item in files if item and item.filename]
    if not selected:
        return HTMLResponse("Yüklenecek PDF veya görsel seçin.", status_code=400)
    if len(selected) > STUDY_MAX_UPLOAD_COUNT:
        return HTMLResponse(f"Tek seferde en fazla {STUDY_MAX_UPLOAD_COUNT} dosya yükleyebilirsiniz.", status_code=400)

    saved_paths: list[Path] = []
    try:
        with Session(engine, expire_on_commit=False) as s:
            course = _owned_study_course(s, user, course_id)
            if not course:
                return HTMLResponse("Ders bulunamadı veya erişim yetkiniz yok.", status_code=404)

            destination_dir = UPLOAD_DIR / "study" / f"user_{user.id}" / f"course_{course_id}"
            destination_dir.mkdir(parents=True, exist_ok=True)
            added = 0
            for upload in selected:
                original_name = Path(upload.filename).name
                extension = Path(original_name).suffix.lower()
                if extension not in STUDY_ALLOWED_EXTENSIONS:
                    continue
                mime_type = _study_mime_type(extension)
                if not mime_type:
                    continue
                stored_name = f"study_{course_id}_{uuid.uuid4().hex}{extension}"
                destination = destination_dir / stored_name
                saved_paths.append(destination)
                total = 0
                with destination.open("wb") as output:
                    while True:
                        chunk = await upload.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > STUDY_MAX_FILE_BYTES:
                            raise ValueError("Bir ders notu dosyası en fazla 25 MB olabilir.")
                        output.write(chunk)
                if not _study_file_has_valid_signature(destination, extension):
                    raise ValueError("Seçilen dosyalardan biri geçerli PDF, JPG, PNG veya WEBP değil.")

                material_type = "PDF" if extension == ".pdf" else "IMAGE"
                s.add(StudyMaterial(
                    course_id=course_id,
                    owner_user_id=user.id,
                    original_filename=original_name,
                    display_name=original_name,
                    stored_filename=stored_name,
                    file_path=str(destination),
                    material_type=material_type,
                    mime_type=mime_type,
                    size_bytes=total,
                ))
                added += 1

            if added == 0:
                return HTMLResponse("Kaydedilecek geçerli PDF veya görsel bulunamadı.", status_code=400)
            course.updated_at = datetime.utcnow()
            s.add(course)
            s.commit()
    except ValueError as exc:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        return HTMLResponse(str(exc), status_code=400)
    except Exception:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise

    return RedirectResponse(f"/notes/courses/{course_id}", status_code=303)


@app.get("/notes/courses/{course_id}/materials/{material_id}/file")
def study_material_file(request: Request, course_id: int, material_id: int):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Yetkisiz erişim.", status_code=401)
    with Session(engine, expire_on_commit=False) as s:
        material = _owned_study_material(s, user, course_id, material_id)
        if not material:
            return HTMLResponse("Not dosyası bulunamadı veya erişim yetkiniz yok.", status_code=404)
        path = Path(material.file_path)
        filename = material.original_filename
        mime_type = material.mime_type
    if not path.is_file():
        return HTMLResponse("Not dosyası sunucuda bulunamadı.", status_code=404)
    return FileResponse(path, media_type=mime_type)


@app.post("/notes/courses/{course_id}/materials/{material_id}/delete")
def delete_study_material(request: Request, course_id: int, material_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    local_path = None
    gemini_name = None
    with Session(engine, expire_on_commit=False) as s:
        material = _owned_study_material(s, user, course_id, material_id)
        if not material:
            return HTMLResponse("Not dosyası bulunamadı veya erişim yetkiniz yok.", status_code=404)
        local_path = Path(material.file_path)
        gemini_name = material.gemini_file_name
        delete_material_rag_index(
            s,
            owner_user_id=user.id,
            course_id=course_id,
            material_id=material_id,
        )
        s.delete(material)
        course = _owned_study_course(s, user, course_id)
        if course:
            course.updated_at = datetime.utcnow()
            s.add(course)
        s.commit()
    if local_path:
        local_path.unlink(missing_ok=True)
    if gemini_name:
        delete_study_ai_file(gemini_name)
    return RedirectResponse(f"/notes/courses/{course_id}", status_code=303)


@app.get("/notes/courses/{course_id}/ai", response_class=HTMLResponse)
def study_ai_page(request: Request, course_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    with Session(engine, expire_on_commit=False) as s:
        course = _owned_study_course(s, user, course_id)
        if not course:
            return HTMLResponse("Ders bulunamadı veya erişim yetkiniz yok.", status_code=404)
        materials = s.exec(
            select(StudyMaterial)
            .where(StudyMaterial.course_id == course_id)
            .where(StudyMaterial.owner_user_id == user.id)
            .order_by(StudyMaterial.created_at.asc())
        ).all()
        messages = s.exec(
            select(StudyChatMessage)
            .where(StudyChatMessage.course_id == course_id)
            .where(StudyChatMessage.owner_user_id == user.id)
            .order_by(StudyChatMessage.id)
        ).all()

    return templates.TemplateResponse(
        request=request,
        name="notes_ai.html",
        context={
            "course": course,
            "material_count": len(materials),
            "messages": messages[-40:],
        },
    )


def _remember_study_exchange_background(
    owner_user_id: int,
    course_id: int,
    user_text: str,
    assistant_text: str,
) -> None:
    """Persist semantic chat memory after the HTTP answer is sent."""
    try:
        with Session(engine, expire_on_commit=False) as session:
            remember_exchange(
                session,
                owner_user_id=owner_user_id,
                course_id=course_id,
                user_text=user_text,
                assistant_text=assistant_text,
            )
    except Exception:
        # Chat rows are already persisted; semantic memory is an optimization.
        return


@app.post("/notes/courses/{course_id}/ai/ask")
def study_ai_ask(
    request: Request,
    course_id: int,
    background_tasks: BackgroundTasks,
    message: str = Form(...),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "Oturumunuz sona ermiş."}, status_code=401)

    clean_message = (message or "").strip()
    if not clean_message:
        return JSONResponse({"ok": False, "error": "Bir soru veya çalışma isteği yazın."}, status_code=400)
    if len(clean_message) > 8000:
        return JSONResponse({"ok": False, "error": "Mesaj en fazla 8000 karakter olabilir."}, status_code=400)

    try:
        with Session(engine, expire_on_commit=False) as s:
            course = _owned_study_course(s, user, course_id)
            if not course:
                return JSONResponse({"ok": False, "error": "Ders bulunamadı veya erişim yetkiniz yok."}, status_code=404)

            materials = s.exec(
                select(StudyMaterial)
                .where(StudyMaterial.course_id == course_id)
                .where(StudyMaterial.owner_user_id == user.id)
                .order_by(StudyMaterial.created_at.asc())
            ).all()
            if not materials:
                return JSONResponse({
                    "ok": False,
                    "error": "Bu derste henüz not bulunmuyor. Önce PDF veya fotoğraf ekleyin.",
                }, status_code=400)

            scope = classify_course_scope(
                course.title,
                [item.original_filename for item in materials],
            )
            if scope == "NON_DENTAL":
                return JSONResponse({
                    "ok": False,
                    "error": "Bu ders Dental AI Akademik'in diş hekimliği çalışma alanı dışında görünüyor.",
                }, status_code=400)

            # Material bytes are indexed once. Unchanged PDFs/images reuse their
            # persistent page embeddings on every later question.
            ensure_course_index(s, materials)

            history_rows = s.exec(
                select(StudyChatMessage)
                .where(StudyChatMessage.course_id == course_id)
                .where(StudyChatMessage.owner_user_id == user.id)
                .order_by(StudyChatMessage.id)
            ).all()
            history = [
                {"role": row.role, "content": row.content}
                for row in history_rows[-8:]
            ]

            rag_result = retrieve_course_context(
                s,
                owner_user_id=user.id,
                course_id=course_id,
                query=clean_message,
                materials=materials,
                recent_history=history,
            )

            answer = ask_study_ai(
                course.title,
                clean_message,
                history,
                rag_result.note_context,
                rag_result.memory_context,
                rag_result.attachments,
            )
            source_json = json.dumps(rag_result.source_material_ids, ensure_ascii=False)

            s.add(StudyChatMessage(
                course_id=course_id,
                owner_user_id=user.id,
                role="USER",
                content=clean_message,
                source_ids_json=source_json,
                mode="RAG_NOTES_ONLY",
            ))
            s.add(StudyChatMessage(
                course_id=course_id,
                owner_user_id=user.id,
                role="ASSISTANT",
                content=answer,
                source_ids_json=source_json,
                mode="RAG_NOTES_ONLY",
            ))
            course.updated_at = datetime.utcnow()
            s.add(course)
            s.commit()

            # Do not make the user wait for a second embedding API call.
            # Semantic memory is persisted after the response is sent.
            background_tasks.add_task(
                _remember_study_exchange_background,
                user.id,
                course_id,
                clean_message,
                answer,
            )
    except StudyRAGError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
    except StudyAIError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)

    return JSONResponse({"ok": True, "answer": answer})


@app.post("/notes/courses/{course_id}/ai/clear")
def clear_study_ai_chat(request: Request, course_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    with Session(engine, expire_on_commit=False) as s:
        course = _owned_study_course(s, user, course_id)
        if not course:
            return HTMLResponse("Ders bulunamadı veya erişim yetkiniz yok.", status_code=404)
        messages = s.exec(
            select(StudyChatMessage)
            .where(StudyChatMessage.course_id == course_id)
            .where(StudyChatMessage.owner_user_id == user.id)
        ).all()
        for item in messages:
            s.delete(item)
        delete_course_rag_memory(s, owner_user_id=user.id, course_id=course_id)
        s.commit()
    return RedirectResponse(f"/notes/courses/{course_id}/ai", status_code=303)


@app.get("/features", response_class=HTMLResponse)
def features_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="features.html",
        context={},
    )


@app.get("/program", response_class=HTMLResponse)
def program_page(
    request: Request,
    view: str = "week",
    day: str = "",
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    today_local = datetime.now(APP_TIMEZONE).date()
    try:
        focus_date = date.fromisoformat(day) if day else today_local
    except ValueError:
        focus_date = today_local

    view, range_start, range_end, previous, following = _program_range(view, focus_date)

    with Session(engine, expire_on_commit=False) as s:
        occurrences = _user_schedule_occurrences(
            s, user.id, range_start, range_end
        )

    return templates.TemplateResponse(
        request=request,
        name="program.html",
        context={
            "view": view,
            "focus_date": focus_date,
            "today_date": today_local,
            "previous_day": previous.isoformat(),
            "next_day": following.isoformat(),
            "groups": _group_program_occurrences(occurrences),
            "event_type_labels": PROGRAM_EVENT_TYPES,
            "saved": request.query_params.get("saved") == "1",
            "deleted": request.query_params.get("deleted") == "1",
            "completed": request.query_params.get("completed") == "1",
        },
    )


@app.get("/program/new", response_class=HTMLResponse)
def program_new_page(
    request: Request,
    type: str = "",
    patient_id: str = "",
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    local_now = datetime.now(APP_TIMEZONE).replace(second=0, microsecond=0)
    rounded_minute = 0 if local_now.minute < 30 else 30
    suggested = local_now.replace(minute=rounded_minute)
    if suggested < local_now:
        suggested += timedelta(minutes=30)

    with Session(engine, expire_on_commit=False) as s:
        patient_query = select(Patient).order_by(Patient.first_name, Patient.last_name)
        if user.role != "ADMIN":
            patient_query = patient_query.where(Patient.owner_user_id == user.id)
        patients = s.exec(patient_query).all()

    initial_type = type.upper() if type.upper() in PROGRAM_EVENT_TYPES else "APPOINTMENT"
    return templates.TemplateResponse(
        request=request,
        name="program_form.html",
        context={
            "mode": "new",
            "event": None,
            "patients": patients,
            "event_types": PROGRAM_EVENT_TYPES,
            "initial_type": initial_type,
            "initial_patient_id": patient_id,
            "initial_start": suggested.strftime("%Y-%m-%dT%H:%M"),
            "initial_end": (suggested + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M"),
            "error": None,
        },
    )


@app.post("/program/new")
def program_create(
    request: Request,
    event_type: str = Form(...),
    title: str = Form(...),
    start_at: str = Form(...),
    end_at: str = Form(""),
    patient_id: str = Form(""),
    location: str = Form(""),
    notes: str = Form(""),
    reminder_minutes: str = Form("30"),
    notification_enabled: Optional[str] = Form(None),
    recurrence_rule: str = Form("NONE"),
    recurrence_until: str = Form(""),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        payload, error = _validate_schedule_input(
            s, user, event_type, title, start_at, end_at, patient_id,
            location, notes, reminder_minutes, notification_enabled,
            recurrence_rule, recurrence_until,
        )
        if error:
            patient_query = select(Patient).order_by(Patient.first_name, Patient.last_name)
            if user.role != "ADMIN":
                patient_query = patient_query.where(Patient.owner_user_id == user.id)
            patients = s.exec(patient_query).all()
            return templates.TemplateResponse(
                request=request,
                name="program_form.html",
                context={
                    "mode": "new",
                    "event": None,
                    "patients": patients,
                    "event_types": PROGRAM_EVENT_TYPES,
                    "initial_type": event_type,
                    "initial_patient_id": patient_id,
                    "initial_start": start_at,
                    "initial_end": end_at,
                    "initial_title": title,
                    "initial_location": location,
                    "initial_notes": notes,
                    "initial_reminder": reminder_minutes,
                    "initial_notification": bool(notification_enabled),
                    "initial_recurrence": recurrence_rule,
                    "initial_recurrence_until": recurrence_until,
                    "error": error,
                },
                status_code=400,
            )

        event = ScheduleEvent(owner_user_id=user.id, **payload)
        s.add(event)
        s.commit()

    return RedirectResponse("/program?saved=1", status_code=303)


@app.get("/program/{event_id}/edit", response_class=HTMLResponse)
def program_edit_page(request: Request, event_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        event = s.get(ScheduleEvent, event_id)
        if not event or event.owner_user_id != user.id or event.status == "DELETED":
            return HTMLResponse("Program kaydı bulunamadı.", status_code=404)
        patient_query = select(Patient).order_by(Patient.first_name, Patient.last_name)
        if user.role != "ADMIN":
            patient_query = patient_query.where(Patient.owner_user_id == user.id)
        patients = s.exec(patient_query).all()
        start_local = _utc_to_local(event.start_at)
        end_local = _utc_to_local(event.end_at)

    return templates.TemplateResponse(
        request=request,
        name="program_form.html",
        context={
            "mode": "edit",
            "event": event,
            "patients": patients,
            "event_types": PROGRAM_EVENT_TYPES,
            "initial_type": event.event_type,
            "initial_patient_id": str(event.patient_id or ""),
            "initial_start": start_local.strftime("%Y-%m-%dT%H:%M") if start_local else "",
            "initial_end": end_local.strftime("%Y-%m-%dT%H:%M") if end_local else "",
            "initial_title": event.title,
            "initial_location": event.location or "",
            "initial_notes": event.notes or "",
            "initial_reminder": str(event.reminder_minutes if event.reminder_minutes is not None else 30),
            "initial_notification": event.notification_enabled,
            "initial_recurrence": event.recurrence_rule,
            "initial_recurrence_until": event.recurrence_until or "",
            "error": None,
        },
    )


@app.post("/program/{event_id}/edit")
def program_edit(
    request: Request,
    event_id: int,
    event_type: str = Form(...),
    title: str = Form(...),
    start_at: str = Form(...),
    end_at: str = Form(""),
    patient_id: str = Form(""),
    location: str = Form(""),
    notes: str = Form(""),
    reminder_minutes: str = Form("30"),
    notification_enabled: Optional[str] = Form(None),
    recurrence_rule: str = Form("NONE"),
    recurrence_until: str = Form(""),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        event = s.get(ScheduleEvent, event_id)
        if not event or event.owner_user_id != user.id or event.status == "DELETED":
            return HTMLResponse("Program kaydı bulunamadı.", status_code=404)

        payload, error = _validate_schedule_input(
            s, user, event_type, title, start_at, end_at, patient_id,
            location, notes, reminder_minutes, notification_enabled,
            recurrence_rule, recurrence_until,
        )
        if error:
            patient_query = select(Patient).order_by(Patient.first_name, Patient.last_name)
            if user.role != "ADMIN":
                patient_query = patient_query.where(Patient.owner_user_id == user.id)
            patients = s.exec(patient_query).all()
            return templates.TemplateResponse(
                request=request,
                name="program_form.html",
                context={
                    "mode": "edit",
                    "event": event,
                    "patients": patients,
                    "event_types": PROGRAM_EVENT_TYPES,
                    "initial_type": event_type,
                    "initial_patient_id": patient_id,
                    "initial_start": start_at,
                    "initial_end": end_at,
                    "initial_title": title,
                    "initial_location": location,
                    "initial_notes": notes,
                    "initial_reminder": reminder_minutes,
                    "initial_notification": bool(notification_enabled),
                    "initial_recurrence": recurrence_rule,
                    "initial_recurrence_until": recurrence_until,
                    "error": error,
                },
                status_code=400,
            )

        for key, value in payload.items():
            setattr(event, key, value)
        event.updated_at = datetime.utcnow()
        s.add(event)
        s.commit()

    return RedirectResponse("/program?saved=1", status_code=303)


@app.post("/program/{event_id}/complete")
def program_complete(request: Request, event_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        event = s.get(ScheduleEvent, event_id)
        if not event or event.owner_user_id != user.id or event.status == "DELETED":
            return HTMLResponse("Program kaydı bulunamadı.", status_code=404)
        if event.recurrence_rule != "NONE":
            return HTMLResponse(
                "Tekrarlanan programın tamamını tamamlandı olarak işaretlemek yerine düzenleyebilirsiniz.",
                status_code=400,
            )
        event.status = "COMPLETED"
        event.updated_at = datetime.utcnow()
        s.add(event)
        s.commit()

    return RedirectResponse("/program?completed=1", status_code=303)


@app.post("/program/{event_id}/delete")
def program_delete(request: Request, event_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        event = s.get(ScheduleEvent, event_id)
        if not event or event.owner_user_id != user.id or event.status == "DELETED":
            return HTMLResponse("Program kaydı bulunamadı.", status_code=404)
        event.status = "DELETED"
        event.updated_at = datetime.utcnow()
        s.add(event)
        s.commit()

    return RedirectResponse("/program?deleted=1", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    local_now = datetime.now(APP_TIMEZONE).replace(tzinfo=None)
    today_start = _date_to_local_start(local_now.date())
    today_end = _date_to_local_end(local_now.date())
    upcoming_end = local_now + timedelta(days=90)

    with Session(engine, expire_on_commit=False) as s:
        patient_query = select(Patient).order_by(Patient.id.desc())
        if user.role != "ADMIN":
            patient_query = patient_query.where(Patient.owner_user_id == user.id)
        patients = s.exec(patient_query).all()

        analysis_query = (
            select(Analysis)
            .join(Patient, Analysis.patient_id == Patient.id)
            .order_by(Analysis.id.desc())
        )
        if user.role != "ADMIN":
            analysis_query = analysis_query.where(Patient.owner_user_id == user.id)
        analyses = s.exec(analysis_query).all()
        records = s.exec(select(ClinicalRecord)).all()

        guest_analyses = s.exec(
            select(GuestAnalysis)
            .where(GuestAnalysis.owner_user_id == user.id)
            .order_by(GuestAnalysis.id.desc())
            .limit(5)
        ).all()

        account_meta = s.exec(
            select(UserAccountMeta).where(UserAccountMeta.user_id == user.id)
        ).first()

        # Ana ekran, bütün günü listelemek yerine yalnızca sıradaki işi gösterir.
        # Önce bugün için henüz bitmemiş/başlamamış kayıt aranır. Bugün yoksa
        # önümüzdeki 90 gün içindeki en yakın aktif kayıt kullanılır.
        today_upcoming_events = _user_schedule_occurrences(
            s, user.id, local_now, today_end
        )
        upcoming_events = _user_schedule_occurrences(
            s, user.id, local_now, upcoming_end
        )

    professional_title = (
        account_meta.professional_title
        if account_meta and account_meta.professional_title
        else "Diş Hekimi"
    )
    today_next_event = next(
        (item for item in today_upcoming_events if item["status"] == "ACTIVE"),
        None,
    )
    next_event = next(
        (item for item in upcoming_events if item["status"] == "ACTIVE"),
        None,
    )
    dashboard_event = today_next_event or next_event
    dashboard_event_label = "Bugün" if today_next_event else "Yaklaşan"

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "patients": patients,
            "analyses": analyses,
            "records": records,
            "guest_analyses": guest_analyses,
            "professional_title": professional_title,
            "professional_group": _professional_group(professional_title),
            "dashboard_copy": _dashboard_copy(professional_title),
            "dashboard_greeting": _dashboard_greeting(local_now),
            "quick_actions": _dashboard_actions(professional_title),
            "dashboard_event": dashboard_event,
            "dashboard_event_label": dashboard_event_label,
            "local_now": local_now,
        }
    )


@app.get("/patients/new", response_class=HTMLResponse)
def new_patient(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="patient_new.html",
        context={"form_data": {}},
    )

@app.post("/patients/new")
def create_patient(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    birth_date: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    tc_kimlik_no: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    chief_complaint: Optional[str] = Form(None),
    force_create: Optional[str] = Form(None),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    first_name = first_name.strip()
    last_name = last_name.strip()

    # Yaşı doğum tarihinden otomatik hesapla
    calculated_age = None
    if birth_date:
        try:
            birth = datetime.strptime(birth_date, "%Y-%m-%d").date()
            today = datetime.utcnow().date()
            calculated_age = today.year - birth.year - (
                (today.month, today.day) < (birth.month, birth.day)
            )
        except ValueError:
            calculated_age = None

    phone = phone.strip() if phone else None
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "birth_date": birth_date or "",
        "phone": phone or "",
        "tc_kimlik_no": tc_kimlik_no.strip() if tc_kimlik_no else "",
        "address": address.strip() if address else "",
        "chief_complaint": chief_complaint.strip() if chief_complaint else "",
    }

    # Türkiye telefon numarası doğrulaması
    if phone:
        if not phone.isdigit() or len(phone) != 11 or not phone.startswith("05"):
            return templates.TemplateResponse(
                request=request,
                name="patient_new.html",
                context={
                    "error": "Telefon numarası 05 ile başlamalı ve toplam 11 rakam olmalıdır.",
                    "form_data": form_data,
                },
                status_code=400,
            )

    with Session(engine, expire_on_commit=False) as s:
        # Mükerrer hasta kontrolü kesinlikle kullanıcının kendi hasta havuzuyla
        # sınırlıdır. Başka hekimin hastası bu uyarıda dahi görünmez.
        duplicate_patient, duplicate_reason = _find_duplicate_patient(
            s,
            user.id,
            first_name,
            last_name,
            birth_date,
            calculated_age,
            phone,
        )
        if duplicate_patient and force_create != "1":
            return templates.TemplateResponse(
                request=request,
                name="patient_new.html",
                context={
                    "duplicate_patient": duplicate_patient,
                    "duplicate_reason": duplicate_reason,
                    "form_data": form_data,
                },
                status_code=409,
            )

        patient = Patient(
            anonymous_id=f"PAT-{uuid.uuid4().hex[:10].upper()}",
            owner_user_id=user.id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            tc_kimlik_no=tc_kimlik_no.strip() if tc_kimlik_no else None,
            birth_date=birth_date,
            age=calculated_age,
            chief_complaint=chief_complaint.strip() if chief_complaint else None,
        )

        s.add(patient)
        s.commit()
        s.refresh(patient)

        patient_profile = PatientProfile(
            patient_id=patient.id,
            address=address.strip() if address else None,
        )
        s.add(patient_profile)
        s.commit()

        if request.query_params.get("next") == "analysis":
            return RedirectResponse(
                f"/analysis/new/{patient.id}",
                status_code=303
            )

        return RedirectResponse(
            f"/patients/{patient.id}",
            status_code=303
        )



@app.get("/tooth-charts", response_class=HTMLResponse)
def browse_tooth_charts(request: Request, q: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    q = q.strip()

    with Session(engine, expire_on_commit=False) as s:
        query = select(Patient)

        # Kullanıcı izolasyonu: normal hekim yalnızca kendi hastalarını görebilir.
        if user.role != "ADMIN":
            query = query.where(Patient.owner_user_id == user.id)

        if q:
            # İsim + soyisim birlikte yazıldığında da çalışması için her kelimeyi
            # ad veya soyad alanlarından birinde arıyoruz.
            for token in q.split():
                pattern = f"%{token}%"
                query = query.where(
                    (Patient.first_name.like(pattern))
                    | (Patient.last_name.like(pattern))
                )
            query = query.order_by(Patient.id.desc()).limit(50)
        else:
            query = query.order_by(Patient.id.desc()).limit(10)

        patients = s.exec(query).all()

    return templates.TemplateResponse(
        request=request,
        name="tooth_chart_browser.html",
        context={
            "patients": patients,
            "q": q,
        },
    )


@app.get("/patients", response_class=HTMLResponse)
def all_patients(request: Request):
    user = get_current_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        query = select(Patient).order_by(Patient.id.desc())

        if user.role != "ADMIN":
            query = query.where(Patient.owner_user_id == user.id)

        patients = s.exec(query).all()

    return templates.TemplateResponse(
        request=request,
        name="patients_all.html",
        context={
            "patients": patients,
        },
    )


@app.get("/patients/search", response_class=HTMLResponse)
def search_patients(request: Request, q: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    q = q.strip()

    with Session(engine, expire_on_commit=False) as s:
        if q:
            pattern = f"%{q}%"
            patients = s.exec(
                select(Patient)
                .where(
                    (
                        (Patient.tc_kimlik_no.like(pattern))
                        | (Patient.first_name.like(pattern))
                        | (Patient.last_name.like(pattern))
                        | (Patient.anonymous_id.like(pattern))
                    )
                    & (
                        (Patient.owner_user_id == user.id)
                        if user.role != "ADMIN"
                        else True
                    )
                )
                .order_by(Patient.last_name, Patient.first_name)
                .limit(50)
            ).all()
        else:
            patients = []

        return templates.TemplateResponse(
            request=request,
            name="patient_search.html",
            context={
                "patients": patients,
                "q": q,
            },
        )

@app.post("/patients/{patient_id}/treatment/new")
def create_treatment(
    request: Request,
    patient_id: int,
    tooth_number: Optional[str] = Form(None),
    treatment_name: str = Form(...),
    treatment_date: Optional[str] = Form(None),
    material: Optional[str] = Form(None),
    doctor_note: Optional[str] = Form(None),
    result: Optional[str] = Form(None),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)

        if not patient:
            return HTMLResponse("Hasta bulunamadı", status_code=404)

        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)

        treatment = Treatment(
            patient_id=patient_id,
            tooth_number=tooth_number.strip() if tooth_number else None,
            treatment_name=treatment_name.strip(),
            treatment_date=treatment_date,
            material=material.strip() if material else None,
            doctor_note=doctor_note.strip() if doctor_note else None,
            result=result,
        )

        s.add(treatment)
        s.commit()

        return RedirectResponse(
            f"/patients/{patient_id}",
            status_code=303
        )

@app.get("/patients/{patient_id}/treatment/new", response_class=HTMLResponse)
def new_treatment(request: Request, patient_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)

        if not patient:
            return HTMLResponse("Hasta bulunamadı", status_code=404)

        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)

        return templates.TemplateResponse(
            request=request,
            name="treatment_new.html",
            context={
                "patient": patient,
            },
        )

@app.post("/patients/{patient_id}/teeth/{tooth_number}")
def update_tooth_status(
    request: Request,
    patient_id: int,
    tooth_number: str,
    status: str = Form(...),
    note: Optional[str] = Form(None),
    surface: Optional[str] = Form(None),
):
    allowed_statuses = {
        "HEALTHY",
        "CARIES",
        "FILLING",
        "CROWN",
        "ROOT_CANAL",
        "EXTRACTED",
        "IMPLANT",
        "OTHER",
    }

    if status not in allowed_statuses:
        return HTMLResponse("Geçersiz diş durumu", status_code=400)

    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)

        if not patient:
            return HTMLResponse("Hasta bulunamadı", status_code=404)

        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)

        # Diş yüzeyi seçildiyse yüzey durumunu kaydet
        allowed_surfaces = {
            "OCCLUSAL",
            "INCISAL",
            "MESIAL",
            "DISTAL",
            "BUCCAL",
            "LINGUAL",
        }

        if surface:
            if surface not in allowed_surfaces:
                return HTMLResponse("Geçersiz diş yüzeyi", status_code=400)

            existing_surface = s.exec(
                select(ToothSurfaceStatus).where(
                    (ToothSurfaceStatus.patient_id == patient_id)
                    & (ToothSurfaceStatus.tooth_number == tooth_number)
                    & (ToothSurfaceStatus.surface == surface)
                )
            ).first()

            if existing_surface:
                existing_surface.status = status
                existing_surface.note = note.strip() if note else None
                existing_surface.updated_at = datetime.utcnow()
            else:
                surface_status = ToothSurfaceStatus(
                    patient_id=patient_id,
                    tooth_number=tooth_number,
                    surface=surface,
                    status=status,
                    note=note.strip() if note else None,
                )
                s.add(surface_status)

        existing = s.exec(
            select(ToothStatus).where(
                (ToothStatus.patient_id == patient_id)
                & (ToothStatus.tooth_number == tooth_number)
            )
        ).first()

        if existing:
            existing.status = status
            existing.note = note.strip() if note else None
            existing.updated_at = datetime.utcnow()
        else:
            tooth = ToothStatus(
                patient_id=patient_id,
                tooth_number=tooth_number,
                status=status,
                note=note.strip() if note else None,
            )
            s.add(tooth)


        # Tedavi geçmişine otomatik kayıt
        treatment_statuses = {
            "CARIES": "Çürük",
            "FILLING": "Dolgu",
            "CROWN": "Kron",
            "ROOT_CANAL": "Kanal Tedavisi",
            "EXTRACTED": "Diş Çekimi",
            "IMPLANT": "İmplant",
            "OTHER": "Diğer",
        }

        treatment_name = treatment_statuses.get(status)

        if treatment_name:
            treatment = Treatment(
                patient_id=patient_id,
                tooth_number=tooth_number,
                treatment_name=treatment_name,
                treatment_date=datetime.utcnow().strftime("%Y-%m-%d"),
                doctor_note=note.strip() if note else None,
            )
            s.add(treatment)

        s.commit()

        return RedirectResponse(
            f"/patients/{patient_id}/teeth",
            status_code=303
        )

@app.get("/patients/{patient_id}/teeth/{tooth_number}/history")
def tooth_history(request: Request, patient_id: int, tooth_number: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)

        if not patient:
            return HTMLResponse("Hasta bulunamadı", status_code=404)

        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)
        treatments = s.exec(
            select(Treatment).where(
                Treatment.patient_id == patient_id,
                Treatment.tooth_number == tooth_number
            )
        ).all()

        analyses = s.exec(
            select(Analysis).where(
                Analysis.patient_id == patient_id,
                Analysis.tooth_number == tooth_number
            )
        ).all()

        surface_statuses = s.exec(
            select(ToothSurfaceStatus).where(
                ToothSurfaceStatus.patient_id == patient_id,
                ToothSurfaceStatus.tooth_number == tooth_number
            )
        ).all()

        surface_names = {
            "OCCLUSAL": "Oklüzal",
            "INCISAL": "İnsizal",
            "MESIAL": "Mesial",
            "DISTAL": "Distal",
            "BUCCAL": "Bukkal / Vestibül",
            "LINGUAL": "Lingual / Palatinal",
        }

        status_names = {
            "HEALTHY": "Sağlıklı",
            "CARIES": "Çürük",
            "FILLING": "Dolgu",
            "CROWN": "Kron",
            "ROOT_CANAL": "Kanal Tedavisi",
            "EXTRACTED": "Çekilmiş",
            "IMPLANT": "İmplant",
            "OTHER": "Diğer",
        }

        return {
            "surface_statuses": [
                {
                    "surface": surface_names.get(s.surface, s.surface),
                    "status": status_names.get(s.status, s.status),
                    "note": s.note or "",
                    "updated_at": s.updated_at.strftime("%d.%m.%Y %H:%M"),
                }
                for s in surface_statuses
            ],
            "treatments": [
                {
                    "name": t.treatment_name,
                    "date": t.treatment_date or "",
                    "material": t.material or "",
                    "result": t.result or "",
                    "note": t.doctor_note or ""
                }
                for t in treatments
            ],
            "analyses": [
                {
                    "id": a.id,
                    "date": a.created_at.strftime("%d.%m.%Y %H:%M"),
                    "status": a.status or "",
                    "notes": a.clinical_notes or ""
                }
                for a in analyses
            ]
        }


@app.get("/patients/{patient_id}/teeth", response_class=HTMLResponse)
def tooth_chart(request: Request, patient_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)

        if not patient:
            return HTMLResponse("Hasta bulunamadı", status_code=404)

        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)

        statuses = s.exec(
            select(ToothStatus).where(
                ToothStatus.patient_id == patient_id
            )
        ).all()

        status_map = {
            item.tooth_number: item.status
            for item in statuses
        }

        # Diş bazlı tedavi geçmişi
        treatments = s.exec(
            select(Treatment).where(
                Treatment.patient_id == patient_id
            )
        ).all()

        treatment_map = {}
        for treatment in treatments:
            treatment_map.setdefault(treatment.tooth_number, []).append(treatment)

        # Diş bazlı analiz geçmişi
        analyses = s.exec(
            select(Analysis).where(
                Analysis.patient_id == patient_id
            )
        ).all()

        analysis_map = {}
        for analysis in analyses:
            analysis_map.setdefault(analysis.tooth_number, []).append(analysis)

        status_info = {
            "HEALTHY": ("Sağlıklı", "healthy"),
            "CARIES": ("Çürük", "caries"),
            "FILLING": ("Dolgu", "filling"),
            "CROWN": ("Kron", "crown"),
            "ROOT_CANAL": ("Kanal", "root-canal"),
            "EXTRACTED": ("Çekilmiş", "extracted"),
            "IMPLANT": ("İmplant", "implant"),
            "OTHER": ("Diğer", "other"),
        }

        def tooth_data(number):
            status = status_map.get(number, "HEALTHY")
            label, css_class = status_info.get(
                status,
                ("Sağlıklı", "healthy")
            )

            return {
                "number": number,
                "status": label,
                "css_class": css_class,
                "treatments": treatment_map.get(number, []),
                "analyses": analysis_map.get(number, []),
            }

        upper_numbers = [
            "18", "17", "16", "15", "14", "13", "12", "11",
            "21", "22", "23", "24", "25", "26", "27", "28"
        ]

        lower_numbers = [
            "48", "47", "46", "45", "44", "43", "42", "41",
            "31", "32", "33", "34", "35", "36", "37", "38"
        ]

        upper_teeth = [tooth_data(n) for n in upper_numbers]
        lower_teeth = [tooth_data(n) for n in lower_numbers]

        return templates.TemplateResponse(
            request=request,
            name="tooth_chart.html",
            context={
                "patient": patient,
                "upper_teeth": upper_teeth,
                "lower_teeth": lower_teeth,
            },
        )

@app.get("/patients/{patient_id}", response_class=HTMLResponse)
def patient_detail(request: Request, patient_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)

        if not patient:
            return HTMLResponse("Hasta bulunamadı", status_code=404)

        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)

        analyses = s.exec(
            select(Analysis).where(
                Analysis.patient_id == patient_id
            ).order_by(Analysis.created_at.desc())
        ).all()

        treatments = s.exec(
            select(Treatment).where(
                Treatment.patient_id == patient_id
            ).order_by(Treatment.created_at.desc())
        ).all()

        patient_profile = s.exec(
            select(PatientProfile).where(
                PatientProfile.patient_id == patient_id
            )
        ).first()

        analysis_assets = {}
        for analysis in analyses:
            analysis_assets[analysis.id] = s.exec(
                select(ImageAsset).where(
                    ImageAsset.analysis_id == analysis.id
                )
            ).all()

        media_owner_id = patient.owner_user_id if patient.owner_user_id is not None else user.id
        patient_media = s.exec(
            select(PatientMedia).where(
                PatientMedia.patient_id == patient_id,
                PatientMedia.owner_user_id == media_owner_id,
            ).order_by(PatientMedia.uploaded_at.desc())
        ).all()

        return templates.TemplateResponse(
            request=request,
            name="patient_detail.html",
            context={
                "patient": patient,
                "patient_profile": patient_profile,
                "analyses": analyses,
                "treatments": treatments,
                "analysis_assets": analysis_assets,
                "patient_media": patient_media,
            },
        )


def _patient_media_has_valid_signature(path: Path, extension: str) -> bool:
    try:
        with path.open("rb") as image_file:
            header = image_file.read(16)
    except OSError:
        return False
    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    return False


def _parse_patient_media_ids(raw_value: Optional[str]) -> list[int]:
    """Comma-separated media ids -> unique positive integer ids, preserving order."""
    values: list[int] = []
    for raw_id in (raw_value or "").split(","):
        raw_id = raw_id.strip()
        if not raw_id:
            continue
        try:
            media_id = int(raw_id)
        except ValueError:
            continue
        if media_id > 0 and media_id not in values:
            values.append(media_id)
    return values


@app.post("/patients/{patient_id}/media")
async def upload_patient_media(
    request: Request,
    patient_id: int,
    media_type: str = Form(...),
    tooth_number: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    normalized_type = (media_type or "").strip().upper()
    if normalized_type not in {"PHOTO", "RADIOGRAPH"}:
        return HTMLResponse("Geçersiz klinik görüntü türü.", status_code=400)

    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    max_bytes = 12 * 1024 * 1024
    saved_paths: list[Path] = []
    selected_files = [upload for upload in files if upload and upload.filename]
    if len(selected_files) > 12:
        return HTMLResponse("Tek seferde en fazla 12 görüntü yükleyebilirsiniz.", status_code=400)

    try:
        with Session(engine, expire_on_commit=False) as s:
            patient = s.get(Patient, patient_id)
            if not patient:
                return HTMLResponse("Hasta bulunamadı", status_code=404)
            if user.role != "ADMIN" and patient.owner_user_id != user.id:
                return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)

            owner_id = patient.owner_user_id if patient.owner_user_id is not None else user.id
            valid_count = 0
            for upload in selected_files:
                original_name = Path(upload.filename).name
                extension = Path(original_name).suffix.lower()
                if extension not in allowed_extensions:
                    continue

                stored_name = f"patient_{patient_id}_{uuid.uuid4().hex}{extension}"
                destination = UPLOAD_DIR / stored_name
                saved_paths.append(destination)
                total = 0
                with destination.open("wb") as buffer:
                    while True:
                        chunk = await upload.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("Bir görüntü en fazla 12 MB olabilir.")
                        buffer.write(chunk)

                if not _patient_media_has_valid_signature(destination, extension):
                    raise ValueError("Seçilen dosyalardan biri geçerli bir JPG, PNG veya WEBP görüntüsü değil.")

                s.add(PatientMedia(
                    patient_id=patient_id,
                    owner_user_id=owner_id,
                    original_filename=original_name,
                    stored_filename=stored_name,
                    file_path=str(destination),
                    media_type=normalized_type,
                    tooth_number=(tooth_number or "").strip() or None,
                    note=(note or "").strip() or None,
                ))
                valid_count += 1

            if valid_count == 0:
                return HTMLResponse("Kaydedilecek geçerli JPG/PNG/WEBP görüntüsü seçilmedi.", status_code=400)
            s.commit()
    except ValueError as exc:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        return HTMLResponse(str(exc), status_code=400)
    except Exception:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise

    return RedirectResponse(f"/patients/{patient_id}#clinical-media", status_code=303)


@app.get("/patients/{patient_id}/media/{media_id}/file")
def patient_media_file(request: Request, patient_id: int, media_id: int):
    user = get_current_user(request)
    if not user:
        return HTMLResponse("Yetkisiz erişim.", status_code=401)

    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)
        media = s.get(PatientMedia, media_id)
        if not patient or not media or media.patient_id != patient_id:
            return HTMLResponse("Klinik görüntü bulunamadı.", status_code=404)
        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)
        if user.role != "ADMIN" and media.owner_user_id != user.id:
            return HTMLResponse("Bu klinik görüntüye erişim yetkiniz yok.", status_code=403)
        path = Path(media.file_path)

    if not path.is_file():
        return HTMLResponse("Klinik görüntü dosyası bulunamadı.", status_code=404)
    return FileResponse(path)


@app.post("/patients/{patient_id}/media/{media_id}/delete")
def delete_patient_media(request: Request, patient_id: int, media_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    file_path = None
    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)
        media = s.get(PatientMedia, media_id)
        if not patient or not media or media.patient_id != patient_id:
            return HTMLResponse("Klinik görüntü bulunamadı.", status_code=404)
        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)
        if user.role != "ADMIN" and media.owner_user_id != user.id:
            return HTMLResponse("Bu klinik görüntüye erişim yetkiniz yok.", status_code=403)
        file_path = Path(media.file_path)
        s.delete(media)
        s.commit()

    if file_path:
        file_path.unlink(missing_ok=True)
    return RedirectResponse(f"/patients/{patient_id}#clinical-media", status_code=303)


@app.post("/patients/{patient_id}/media/delete-all")
def delete_all_patient_media(request: Request, patient_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    file_paths: list[Path] = []
    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)
        if not patient:
            return HTMLResponse("Hasta bulunamadı", status_code=404)
        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)

        media_owner_id = patient.owner_user_id if patient.owner_user_id is not None else user.id
        media_items = s.exec(
            select(PatientMedia).where(
                PatientMedia.patient_id == patient_id,
                PatientMedia.owner_user_id == media_owner_id,
            )
        ).all()
        for media in media_items:
            file_paths.append(Path(media.file_path))
            s.delete(media)
        s.commit()

    for file_path in file_paths:
        file_path.unlink(missing_ok=True)
    return RedirectResponse(f"/patients/{patient_id}#clinical-media", status_code=303)


@app.get("/analyses", response_class=HTMLResponse)
def all_analyses(request: Request):
    user = get_current_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    items = []

    with Session(engine, expire_on_commit=False) as s:
        patient_analyses = s.exec(
            select(Analysis).order_by(Analysis.id.desc())
        ).all()

        for analysis in patient_analyses:
            patient = s.get(Patient, analysis.patient_id)

            if not patient:
                continue

            if user.role != "ADMIN" and patient.owner_user_id != user.id:
                continue

            patient_name = (
                f"{patient.first_name or ''} {patient.last_name or ''}"
            ).strip() or patient.anonymous_id or "Hasta"

            items.append({
                "is_guest": False,
                "patient_name": patient_name,
                "tooth_number": analysis.tooth_number,
                "clinical_notes": analysis.clinical_notes,
                "created_at": analysis.created_at,
                "result_url": f"/analysis/{analysis.id}",
            })

        guest_analyses = s.exec(
            select(GuestAnalysis).order_by(GuestAnalysis.id.desc())
        ).all()

        for analysis in guest_analyses:
            if user.role != "ADMIN" and analysis.owner_user_id != user.id:
                continue

            items.append({
                "is_guest": True,
                "patient_name": "",
                "tooth_number": analysis.tooth_number,
                "clinical_notes": analysis.clinical_notes,
                "created_at": analysis.created_at,
                "result_url": f"/analysis/guest/{analysis.id}",
            })

    items.sort(
        key=lambda x: x["created_at"] or datetime.min,
        reverse=True,
    )

    return templates.TemplateResponse(
        request=request,
        name="analyses_all.html",
        context={
            "analyses": items,
        },
    )


@app.get("/analysis/new", response_class=HTMLResponse)
def analysis_choice(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="analysis_choice.html",
        context={}
    )


@app.get("/analysis/guest/new", response_class=HTMLResponse)
def guest_analysis_new(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="guest_analysis_new.html",
        context={}
    )


@app.get("/analysis/new/{patient_id}", response_class=HTMLResponse)
def new_analysis(
    request: Request,
    patient_id: int,
    media_id: Optional[int] = None,
    media_ids: Optional[str] = None,
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    requested_ids = _parse_patient_media_ids(media_ids)
    if media_id is not None and media_id not in requested_ids:
        requested_ids.insert(0, media_id)
    if len(requested_ids) > 12:
        return HTMLResponse("Tek analizde en fazla 12 kayıtlı görüntü seçebilirsiniz.", status_code=400)

    selected_media: list[PatientMedia] = []
    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)

        if not patient:
            return HTMLResponse("Hasta bulunamadı", status_code=404)

        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)

        for selected_id in requested_ids:
            media = s.get(PatientMedia, selected_id)
            if not media or media.patient_id != patient_id:
                return HTMLResponse("Klinik görüntü bulunamadı.", status_code=404)
            if user.role != "ADMIN" and media.owner_user_id != user.id:
                return HTMLResponse("Bu klinik görüntüye erişim yetkiniz yok.", status_code=403)
            selected_media.append(media)

    return templates.TemplateResponse(
        request=request,
        name="analysis_new.html",
        context={
            "patient": patient,
            "selected_media": selected_media,
            "selected_media_ids": ",".join(str(media.id) for media in selected_media),
        },
    )


def _get_specialty_rag_context(
    patient,
    analysis,
    assets,
    extra_text="",
):
    image_types = [
        asset.image_type
        for asset in assets
        if asset.image_type
    ]

    routing_text = "\n".join(
        x for x in [
            analysis.clinical_notes or "",
            extra_text or "",
        ]
        if x
    )

    router = classify_specialties(
        age=patient.age,
        dentition="",
        tooth_number=analysis.tooth_number or "",
        clinical_notes=routing_text,
        image_types=image_types,
        findings="",
        chief_complaint=patient.chief_complaint or "",
        top_k=5,
    )

    ranked = router.get("ranked_specialties", [])

    specialties = [
        item.get("specialty")
        for item in ranked
        if item.get("specialty")
    ][:5]

    labels = [
        item.get("label")
        for item in ranked
        if item.get("label")
    ][:5]

    rag_query = f"""
Hasta yaşı: {patient.age if patient.age is not None else ""}
Diş: {analysis.tooth_number or ""}
Hasta şikayeti: {patient.chief_complaint or ""}
Klinik bilgi: {analysis.clinical_notes or ""}
Ek hekim bilgisi: {extra_text or ""}
Görüntü tipleri: {", ".join(image_types)}

İlgili dental branşlar:
{", ".join(labels)}

Bu vaka için görüntü bulguları, klinik değerlendirme,
ayırıcı tanı, ek değerlendirme ve tedavi yaklaşımı
açısından en ilgili güncel kanıtları bul.
"""

    context = get_specialty_relevant_context(
        rag_query,
        specialties=specialties,
        top_k=5,
        max_chars=7000,
    )

    return (
        "ROUTER TARAFINDAN SEÇİLEN BRANŞLAR:\n"
        + "\n".join(f"- {label}" for label in labels)
        + "\n\n"
        + context
    )



def _get_guest_specialty_rag_context(
    analysis,
    assets,
    extra_text="",
):
    image_types = [
        asset.image_type
        for asset in assets
        if asset.image_type
    ]

    routing_text = "\n".join(
        x for x in [
            analysis.clinical_notes or "",
            extra_text or "",
        ]
        if x
    )

    router = classify_specialties(
        age=None,
        dentition="",
        tooth_number=analysis.tooth_number or "",
        clinical_notes=routing_text,
        image_types=image_types,
        findings="",
        chief_complaint="",
        top_k=5,
    )

    ranked = router.get("ranked_specialties", [])

    specialties = [
        item.get("specialty")
        for item in ranked
        if item.get("specialty")
    ][:5]

    labels = [
        item.get("label")
        for item in ranked
        if item.get("label")
    ][:5]

    rag_query = f"""
Diş: {analysis.tooth_number or ""}
Klinik bilgi: {analysis.clinical_notes or ""}
Ek hekim bilgisi: {extra_text or ""}
Görüntü tipleri: {", ".join(image_types)}

İlgili dental branşlar:
{", ".join(labels)}

Bu vaka için görüntü bulguları, klinik değerlendirme,
ayırıcı tanı, ek değerlendirme ve tedavi yaklaşımı
açısından en ilgili güncel kanıtları bul.
"""

    context = get_specialty_relevant_context(
        rag_query,
        specialties=specialties,
        top_k=5,
        max_chars=7000,
    )

    return (
        "ROUTER TARAFINDAN SEÇİLEN BRANŞLAR:\n"
        + "\n".join(f"- {label}" for label in labels)
        + "\n\n"
        + context
    )


def _run_guest_preliminary_ai(analysis_id: int):
    from app.ai_engine import (
        PRELIMINARY_RESPONSE_SCHEMA,
        build_preliminary_prompt,
        parse_ai_result,
        validate_preliminary_result,
    )
    from app.ai_provider import ask_ai

    with Session(engine, expire_on_commit=False) as s:
        analysis = s.get(GuestAnalysis, analysis_id)

        if not analysis:
            return

        assets = s.exec(
            select(GuestImageAsset).where(
                GuestImageAsset.guest_analysis_id == analysis_id
            )
        ).all()

        image_paths = [
            asset.file_path
            for asset in assets
            if asset.file_path
        ]

        image_path = image_paths[0] if image_paths else None

        try:
            knowledge_context = _get_guest_specialty_rag_context(
                analysis=analysis,
                assets=assets,
            )

            prompt = build_preliminary_prompt(
                tooth_number=analysis.tooth_number or "",
                clinical_notes=analysis.clinical_notes or "",
                image_path=image_path,
                knowledge_context=knowledge_context,
            )

            ai_text = ask_ai(
                prompt,
                image_paths=image_paths,
                response_schema=PRELIMINARY_RESPONSE_SCHEMA,
            )

            ai_result = validate_preliminary_result(parse_ai_result(ai_text))

            # Geçerli JSON gelse bile beklenen klinik şemaya uymuyorsa 1 kez yeniden dene.
            if ai_result.get("status") == "AI_INVALID":
                ai_text = ask_ai(
                    prompt,
                    image_paths=image_paths,
                    response_schema=PRELIMINARY_RESPONSE_SCHEMA,
                )
                ai_result = validate_preliminary_result(parse_ai_result(ai_text))

        except Exception as e:
            ai_text = ""
            ai_result = {
                "status": "AI_ERROR",
                "error": str(e),
            }

        if isinstance(ai_result, dict):
            questions = ai_result.get("questions")
            if isinstance(questions, list):
                ai_result["questions"] = questions[:5]

        result_dir = Path("uploads/ai_results")
        result_dir.mkdir(parents=True, exist_ok=True)

        result_file = result_dir / f"guest_{analysis_id}.json"

        result_file.write_text(
            json.dumps(
                {
                    "ai_result": ai_result,
                    "ai_text": ai_text,
                    "stage": "PRELIMINARY",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        analysis.status = "AI_ANALYZED"
        s.add(analysis)
        s.commit()


def _run_preliminary_ai(analysis_id: int):
    from app.ai_engine import (
        PRELIMINARY_RESPONSE_SCHEMA,
        build_preliminary_prompt,
        parse_ai_result,
        validate_preliminary_result,
    )
    from app.ai_provider import ask_ai

    with Session(engine, expire_on_commit=False) as s:
        analysis = s.get(Analysis, analysis_id)

        if not analysis:
            return

        assets = s.exec(
            select(ImageAsset).where(
                ImageAsset.analysis_id == analysis_id
            )
        ).all()

        image_paths = [
            asset.file_path
            for asset in assets
            if asset.file_path
        ]

        image_path = image_paths[0] if image_paths else None

        try:
            rag_query = f"""
Diş: {analysis.tooth_number or ""}
Klinik bilgi: {analysis.clinical_notes or ""}
Dental vaka için tanı, ayırıcı tanı, gerekli değerlendirme
ve tedavi yaklaşımını etkileyebilecek güncel kanıtları bul.
"""

            patient = s.get(Patient, analysis.patient_id)
            if not patient:
                raise RuntimeError("Hasta kaydı bulunamadı.")

            knowledge_context = _get_specialty_rag_context(
                patient=patient,
                analysis=analysis,
                assets=assets,
            )

            prompt = build_preliminary_prompt(
                tooth_number=analysis.tooth_number or "",
                clinical_notes=analysis.clinical_notes or "",
                image_path=image_path,
                knowledge_context=knowledge_context
            )

            ai_text = ask_ai(
                prompt,
                image_paths=image_paths,
                response_schema=PRELIMINARY_RESPONSE_SCHEMA,
            )

            ai_result = validate_preliminary_result(parse_ai_result(ai_text))

            if ai_result.get("status") == "AI_INVALID":
                ai_text = ask_ai(
                    prompt,
                    image_paths=image_paths,
                    response_schema=PRELIMINARY_RESPONSE_SCHEMA,
                )
                ai_result = validate_preliminary_result(parse_ai_result(ai_text))

        except Exception as e:
            ai_text = ""
            ai_result = {
                "status": "AI_ERROR",
                "error": str(e)
            }

        if isinstance(ai_result, dict):
            questions = ai_result.get("questions")

            if isinstance(questions, list):
                ai_result["questions"] = questions[:5]

        result_dir = Path("uploads/ai_results")
        result_dir.mkdir(parents=True, exist_ok=True)

        result_file = result_dir / f"{analysis_id}.json"

        result_file.write_text(
            json.dumps(
                {
                    "ai_result": ai_result,
                    "ai_text": ai_text,
                    "stage": "PRELIMINARY"
                },
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        analysis.status = "AI_ANALYZED"
        s.add(analysis)
        s.commit()



@app.post("/analysis/guest/new")
async def create_guest_analysis(
    request: Request,
    background_tasks: BackgroundTasks,
    tooth_number: Optional[str] = Form(None),
    clinical_notes: Optional[str] = Form(None),
    images: list[UploadFile] = File(default=[]),
):
    user = get_current_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        analysis = GuestAnalysis(
            owner_user_id=user.id,
            tooth_number=tooth_number,
            clinical_notes=clinical_notes,
            status="ANALYZING",
        )

        s.add(analysis)
        s.commit()
        s.refresh(analysis)

        allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}

        for image in images:
            if not image or not image.filename:
                continue

            original_name = Path(image.filename).name
            extension = Path(original_name).suffix.lower()

            if extension not in allowed_extensions:
                continue

            stored_name = (
                f"guest_analysis_{analysis.id}_"
                f"{uuid.uuid4().hex}{extension}"
            )

            destination = UPLOAD_DIR / stored_name

            with destination.open("wb") as buffer:
                shutil.copyfileobj(image.file, buffer)

            asset = GuestImageAsset(
                guest_analysis_id=analysis.id,
                original_filename=original_name,
                stored_filename=stored_name,
                file_path=str(destination),
                image_type="OTHER",
            )

            s.add(asset)

        s.commit()

        analysis_id = analysis.id

    background_tasks.add_task(
        _run_guest_preliminary_ai,
        analysis_id,
    )

    return RedirectResponse(
        url=f"/analysis/guest/{analysis_id}",
        status_code=303,
    )


@app.post("/analysis/new/{patient_id}")
async def create_analysis(
    request: Request,
    patient_id: int,
    background_tasks: BackgroundTasks,
    tooth_number: Optional[str] = Form(None),
    clinical_notes: Optional[str] = Form(None),
    existing_media_id: Optional[int] = Form(None),
    existing_media_ids: Optional[str] = Form(None),
    images: list[UploadFile] = File(default=[]),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)
        if not patient:
            return HTMLResponse("Hasta bulunamadı", status_code=404)
        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)

        requested_media_ids = _parse_patient_media_ids(existing_media_ids)
        if existing_media_id is not None and existing_media_id not in requested_media_ids:
            requested_media_ids.insert(0, existing_media_id)
        if len(requested_media_ids) > 12:
            return HTMLResponse("Tek analizde en fazla 12 kayıtlı görüntü seçebilirsiniz.", status_code=400)

        selected_media_items: list[tuple[PatientMedia, Path]] = []
        for selected_id in requested_media_ids:
            media = s.get(PatientMedia, selected_id)
            if not media or media.patient_id != patient_id:
                return HTMLResponse("Klinik görüntü bulunamadı.", status_code=404)
            if user.role != "ADMIN" and media.owner_user_id != user.id:
                return HTMLResponse("Bu klinik görüntüye erişim yetkiniz yok.", status_code=403)
            media_path = Path(media.file_path)
            if media_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"} or not media_path.is_file():
                return HTMLResponse("Seçilen klinik görüntü dosyası bulunamadı.", status_code=404)
            selected_media_items.append((media, media_path))

        analysis = Analysis(
            patient_id=patient_id,
            tooth_number=tooth_number,
            clinical_notes=clinical_notes,
            status="ANALYZING",
        )

        s.add(analysis)
        s.commit()
        s.refresh(analysis)

        allowed_extensions = {
            ".jpg", ".jpeg", ".png", ".webp"
        }

        for selected_media, selected_media_path in selected_media_items:
            source_ext = selected_media_path.suffix.lower()
            stored_name = (
                f"analysis_{analysis.id}_"
                f"{uuid.uuid4().hex}{source_ext}"
            )
            destination = UPLOAD_DIR / stored_name
            shutil.copy2(selected_media_path, destination)
            s.add(ImageAsset(
                analysis_id=analysis.id,
                original_filename=selected_media.original_filename,
                stored_filename=stored_name,
                file_path=str(destination),
                image_type=("RADIOGRAPH" if selected_media.media_type == "RADIOGRAPH" else "OTHER"),
            ))

        for image in images:
            if not image or not image.filename:
                continue

            original_name = Path(image.filename).name
            extension = Path(original_name).suffix.lower()

            if extension not in allowed_extensions:
                continue

            stored_name = (
                f"analysis_{analysis.id}_"
                f"{uuid.uuid4().hex}{extension}"
            )

            destination = UPLOAD_DIR / stored_name

            with destination.open("wb") as buffer:
                shutil.copyfileobj(image.file, buffer)

            asset = ImageAsset(
                analysis_id=analysis.id,
                original_filename=original_name,
                stored_filename=stored_name,
                file_path=str(destination),
                image_type="OTHER",
            )

            s.add(asset)

        s.commit()

        analysis_id = analysis.id

    # Gemma ARTIK sayfayı bekletmiyor.
    background_tasks.add_task(
        _run_preliminary_ai,
        analysis_id
    )

    return RedirectResponse(
        url=f"/analysis/{analysis_id}",
        status_code=303
    )


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role != "ADMIN":
        return HTMLResponse("Bu sayfaya erişim yetkiniz yok.", status_code=403)

    with Session(engine, expire_on_commit=False) as s:
        users = s.exec(select(User)).all()
        patients = s.exec(select(Patient).order_by(Patient.id.desc())).all()
        analyses = s.exec(select(Analysis).order_by(Analysis.id.desc())).all()
        records = s.exec(select(ClinicalRecord).order_by(ClinicalRecord.id.desc())).all()

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "users": users,
            "patients": patients,
            "analyses": analyses,
            "records": records
        }
    )


@app.post("/admin/clinical-record")
def create_clinical_record(
    request: Request,
    clinical_id: str = Form(...),
    topic: str = Form(...),
    clinical_question: str = Form(...),
    claim: str = Form(...),
    evidence_grade: str = Form("UNASSESSED"),
    consensus_status: str = Form("UNASSESSED"),
    ai_use: str = Form("NOT_DEFINED"),
    safety_notes: Optional[str] = Form(None),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role != "ADMIN":
        return HTMLResponse("Bu işlem için yönetici yetkisi gerekiyor.", status_code=403)

    with Session(engine, expire_on_commit=False) as s:
        s.add(ClinicalRecord(
            clinical_id=clinical_id, topic=topic, clinical_question=clinical_question,
            claim=claim, evidence_grade=evidence_grade,
            consensus_status=consensus_status, ai_use=ai_use, safety_notes=safety_notes
        ))
        s.commit()
    return RedirectResponse("/admin", status_code=303)


@app.get("/analysis/guest/{analysis_id}", response_class=HTMLResponse)
def guest_analysis_result(request: Request, analysis_id: int):
    user = get_current_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        analysis = s.get(GuestAnalysis, analysis_id)

        if not analysis:
            return HTMLResponse(
                "Analiz bulunamadı.",
                status_code=404
            )

        if user.role != "ADMIN" and analysis.owner_user_id != user.id:
            return HTMLResponse(
                "Bu analize erişim yetkiniz yok.",
                status_code=403
            )

        dx = s.exec(
            select(ClinicalRecord).where(
                ClinicalRecord.clinical_id == "CARIES-DX"
            )
        ).first()

    result_file = Path(
        f"uploads/ai_results/guest_{analysis_id}.json"
    )

    ai_result = {
        "status": "AI_ANALYZING",
        "error": ""
    }

    ai_text = ""

    if result_file.exists():
        try:
            saved = json.loads(
                result_file.read_text(
                    encoding="utf-8"
                )
            )

            ai_result = saved.get(
                "ai_result",
                ai_result
            )

            ai_text = saved.get(
                "ai_text",
                ""
            )

        except Exception as e:
            ai_result = {
                "status": "AI_ERROR",
                "error": str(e)
            }

    return templates.TemplateResponse(
        request=request,
        name="guest_result.html",
        context={
            "analysis": analysis,
            "patient": None,
            "dx": dx,
            "ai_result": ai_result,
            "ai_text": ai_text
        }
    )


@app.get("/analysis/{analysis_id}", response_class=HTMLResponse)
def analysis_result(request: Request, analysis_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:

        analysis = s.get(Analysis, analysis_id)

        if not analysis:
            return HTMLResponse(
                "Analiz bulunamadı.",
                status_code=404
            )

        patient = s.get(Patient, analysis.patient_id)

        if not patient:
            return HTMLResponse("Hasta bulunamadı.", status_code=404)

        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)

        dx = s.exec(
            select(ClinicalRecord).where(
                ClinicalRecord.clinical_id == "CARIES-DX"
            )
        ).first()

    # -----------------------------------------------------
    # ÖNEMLİ:
    # BURADA GEMINI ÇALIŞMIYOR.
    # Sadece daha önce kaydedilmiş sonucu okuyor.
    # -----------------------------------------------------

    result_file = Path(
        f"uploads/ai_results/{analysis_id}.json"
    )

    ai_result = {
        "status": "AI_ANALYZING",
        "error": ""
    }

    ai_text = ""

    if result_file.exists():

        try:
            saved = json.loads(
                result_file.read_text(
                    encoding="utf-8"
                )
            )

            ai_result = saved.get(
                "ai_result",
                ai_result
            )

            ai_text = saved.get(
                "ai_text",
                ""
            )

        except Exception as e:

            ai_result = {
                "status": "AI_ERROR",
                "error": str(e)
            }

    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "analysis": analysis,
            "patient": patient,
            "dx": dx,
            "ai_result": ai_result,
            "ai_text": ai_text
        }
    )


# ---------------------------------------------------------
# VAR / YOK BİTTİĞİNDE OTOMATİK NİHAİ ANALİZ
# ---------------------------------------------------------


@app.post("/analysis/guest/{analysis_id}/final", response_class=HTMLResponse)
async def guest_final_analysis(
    request: Request,
    analysis_id: int
):
    from app.ai_engine import (
        FINAL_RESPONSE_SCHEMA,
        build_final_prompt,
        parse_ai_result,
        validate_final_result,
    )
    from app.ai_provider import ask_ai

    user = get_current_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        analysis = s.get(
            GuestAnalysis,
            analysis_id
        )

        if not analysis:
            return HTMLResponse(
                "Analiz bulunamadı.",
                status_code=404
            )

        if user.role != "ADMIN" and analysis.owner_user_id != user.id:
            return HTMLResponse(
                "Bu analize erişim yetkiniz yok.",
                status_code=403
            )

        assets = s.exec(
            select(GuestImageAsset).where(
                GuestImageAsset.guest_analysis_id == analysis.id
            )
        ).all()

        image_paths = [
            asset.file_path
            for asset in assets
            if asset.file_path
        ]

        image_path = image_paths[0] if image_paths else None

        form = await request.form()

        answers = {}

        for key, value in form.items():
            if key.startswith("answer_"):
                index = key.replace(
                    "answer_",
                    ""
                )
                answers[index] = str(value)

        try:
            knowledge_context = _get_guest_specialty_rag_context(
                analysis=analysis,
                assets=assets,
                extra_text=f"Hekim cevapları: {answers}",
            )

            prompt = build_final_prompt(
                tooth_number=analysis.tooth_number or "",
                clinical_notes=analysis.clinical_notes or "",
                answers=answers,
                image_path=image_path,
                knowledge_context=knowledge_context,
            )

            ai_text = ask_ai(
                prompt,
                image_paths=image_paths,
                response_schema=FINAL_RESPONSE_SCHEMA,
            )

            ai_result = validate_final_result(parse_ai_result(ai_text))

            if ai_result.get("status") == "AI_INVALID":
                ai_text = ask_ai(
                    prompt,
                    image_paths=image_paths,
                    response_schema=FINAL_RESPONSE_SCHEMA,
                )
                ai_result = validate_final_result(parse_ai_result(ai_text))

        except Exception as e:
            ai_text = ""

            ai_result = {
                "status": "AI_ERROR",
                "error": str(e)
            }

        result_dir = Path(
            "uploads/ai_results"
        )

        result_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        result_file = (
            result_dir /
            f"guest_{analysis_id}.json"
        )

        result_file.write_text(
            json.dumps(
                {
                    "ai_result": ai_result,
                    "ai_text": ai_text,
                    "stage": "FINAL",
                    "answers": answers
                },
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        analysis.status = "AI_FINAL"
        s.add(analysis)
        s.commit()

    return RedirectResponse(
        url=f"/analysis/guest/{analysis_id}",
        status_code=303
    )


@app.post("/analysis/{analysis_id}/final", response_class=HTMLResponse)
async def final_analysis(
    request: Request,
    analysis_id: int
):

    from app.ai_engine import (
        FINAL_RESPONSE_SCHEMA,
        build_final_prompt,
        parse_ai_result,
        validate_final_result,
    )
    from app.ai_provider import ask_ai

    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(
        engine,
        expire_on_commit=False
    ) as s:

        analysis = s.get(
            Analysis,
            analysis_id
        )

        if not analysis:
            return HTMLResponse(
                "Analiz bulunamadı.",
                status_code=404
            )

        patient = s.get(
            Patient,
            analysis.patient_id
        )

        if not patient:
            return HTMLResponse("Hasta bulunamadı.", status_code=404)

        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)

        dx = s.exec(
            select(ClinicalRecord).where(
                ClinicalRecord.clinical_id == "CARIES-DX"
            )
        ).first()

        assets = s.exec(
            select(ImageAsset).where(
                ImageAsset.analysis_id == analysis.id
            )
        ).all()

        image_paths = [
            asset.file_path
            for asset in assets
            if asset.file_path
        ]

        image_path = image_paths[0] if image_paths else None

    # -----------------------------------------------------
    # HEKİM CEVAPLARINI AL
    # -----------------------------------------------------

    form = await request.form()

    answers = {}

    for key, value in form.items():

        if key.startswith("answer_"):
            index = key.replace(
                "answer_",
                ""
            )

            answers[index] = str(value)

    # -----------------------------------------------------
    # SADECE SON AŞAMADA GEMINI ÇALIŞIR
    # -----------------------------------------------------

    try:

        rag_query = f"""
Diş: {analysis.tooth_number or ""}
Klinik bilgi: {analysis.clinical_notes or ""}
Hekim cevapları: {answers}

Dental vaka için nihai klinik karar desteği,
ayırıcı tanı, ek değerlendirme ve tedavi yaklaşımı
için en ilgili kanıtları bul.
"""

        patient = s.get(Patient, analysis.patient_id)
        if not patient:
            raise RuntimeError("Hasta kaydı bulunamadı.")

        knowledge_context = _get_specialty_rag_context(
            patient=patient,
            analysis=analysis,
            assets=assets,
            extra_text=f"Hekim cevapları: {answers}",
        )

        prompt = build_final_prompt(
            tooth_number=analysis.tooth_number or "",
            clinical_notes=analysis.clinical_notes or "",
            answers=answers,
            image_path=image_path,
            knowledge_context=knowledge_context
        )

        ai_text = ask_ai(
            prompt,
            image_paths=image_paths,
            response_schema=FINAL_RESPONSE_SCHEMA,
        )

        ai_result = validate_final_result(parse_ai_result(ai_text))

        if ai_result.get("status") == "AI_INVALID":
            ai_text = ask_ai(
                prompt,
                image_paths=image_paths,
                response_schema=FINAL_RESPONSE_SCHEMA,
            )
            ai_result = validate_final_result(parse_ai_result(ai_text))

    except Exception as e:

        ai_text = ""

        ai_result = {
            "status": "AI_ERROR",
            "error": str(e)
        }

    # -----------------------------------------------------
    # NİHAİ SONUCU KAYDET
    # -----------------------------------------------------

    result_dir = Path(
        "uploads/ai_results"
    )

    result_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    result_file = (
        result_dir /
        f"{analysis_id}.json"
    )

    result_file.write_text(
        json.dumps(
            {
                "ai_result": ai_result,
                "ai_text": ai_text,
                "stage": "FINAL",
                "answers": answers
            },
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    with Session(
        engine,
        expire_on_commit=False
    ) as s:

        analysis = s.get(
            Analysis,
            analysis_id
        )

        if analysis:
            analysis.status = "AI_FINAL"
            s.add(analysis)
            s.commit()

    return RedirectResponse(
        url=f"/analysis/{analysis_id}",
        status_code=303
    )


# -----------------------------------------------------
# DENTAL AI'YE SOR — DOĞRUDAN GEMMA
# -----------------------------------------------------

@app.post("/ai/ask", response_class=HTMLResponse)
def ai_ask(
    request: Request,
    question: str = Form(...),
):
    user = get_current_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    question = question.strip()

    answer = None
    error = None

    if not question:
        error = "Lütfen bir soru yazın."
    else:
        prompt = f"""
Sen DENTAL AI'sın.
Hekimin sorusuna doğrudan Türkçe cevap ver.
Bu bölümde RAG veya harici kaynak kullanma; doğrudan kendi model bilgini kullan.
Cevabı anlaşılır ve klinik olarak temkinli ver.
Gereksiz JSON üretme.
Kesin tanı veya otomatik reçete verme.
Son klinik kararın hekim tarafından verilmesi gerektiğini belirt.

Hekimin sorusu:
{question}
"""

        try:
            from app.ai_provider import ask_ai
            answer = ask_ai(prompt)
        except Exception as e:
            error = str(e)

    with Session(engine, expire_on_commit=False) as s:
        patient_query = select(Patient).order_by(Patient.id.desc())
        if user.role != "ADMIN":
            patient_query = patient_query.where(Patient.owner_user_id == user.id)
        patients = s.exec(patient_query).all()

        analysis_query = (
            select(Analysis)
            .join(Patient, Analysis.patient_id == Patient.id)
            .order_by(Analysis.id.desc())
        )
        if user.role != "ADMIN":
            analysis_query = analysis_query.where(Patient.owner_user_id == user.id)
        analyses = s.exec(analysis_query).all()

        records = s.exec(select(ClinicalRecord)).all()

        guest_analyses = s.exec(
            select(GuestAnalysis)
            .where(GuestAnalysis.owner_user_id == user.id)
            .order_by(GuestAnalysis.id.desc())
            .limit(5)
        ).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "patients": patients,
            "analyses": analyses,
            "records": records,
            "guest_analyses": guest_analyses,
            "ai_question": question,
            "ai_answer": answer,
            "ai_error": error,
        },
    )

# === TEMP_AI_SELFTEST_BEGIN ===
from fastapi import Header as _AIHeader, HTTPException as _AIHTTPException

_AI_SELFTEST_TOKEN = "-z5l9i9bO1xPzQokqenldAq23d6O42zOGy6-MKxlwok"

_AI_SELFTEST_MODELS = {
    "gemini": {
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.5-flash-lite",
    },
    "cohere": {
        "command-a-plus-05-2026",
        "command-a-reasoning-08-2025",
        "command-a-03-2025",
    },
    "groq": {
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "qwen/qwen3.6-27b",
        "llama-3.3-70b-versatile",
    },
    "mistral": {
        "mistral-medium-latest",
        "mistral-small-latest",
    },
    "openrouter": {
        "openrouter/free",
    },
}

@app.post(
    "/__ai-selftest/{provider}/{model:path}",
    include_in_schema=False,
)
def _ai_selftest(
    provider: str,
    model: str,
    x_ai_selftest_token: str | None = _AIHeader(
        default=None,
        alias="X-AI-Selftest-Token",
    ),
):
    import json
    import os
    import secrets
    import socket
    import urllib.error
    import urllib.request

    if not secrets.compare_digest(
        x_ai_selftest_token or "",
        _AI_SELFTEST_TOKEN,
    ):
        raise _AIHTTPException(status_code=404)

    provider = provider.strip().lower()
    model = model.strip()

    if (
        provider not in _AI_SELFTEST_MODELS
        or model not in _AI_SELFTEST_MODELS[provider]
    ):
        raise _AIHTTPException(status_code=404)

    key_env = {
        "gemini": "GEMINI_API_KEY",
        "cohere": "COHERE_API_KEY",
        "groq": "GROQ_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }

    api_key = (os.getenv(key_env[provider]) or "").strip()

    if not api_key:
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "http": None,
            "error": f"{key_env[provider]} YOK",
        }

    prompt = "Sadece TEST_OK yaz."

    if provider == "gemini":
        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{model}:generateContent"
        )
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 32,
            },
        }

    elif provider == "cohere":
        url = "https://api.cohere.com/v2/chat"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0,
            "max_tokens": 32,
        }

    else:
        urls = {
            "groq":
                "https://api.groq.com/openai/v1/chat/completions",
            "mistral":
                "https://api.mistral.ai/v1/chat/completions",
            "openrouter":
                "https://openrouter.ai/api/v1/chat/completions",
        }

        url = urls[provider]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://dentalai.tr"
            headers["X-Title"] = "Dental AI Self Test"

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0,
            "max_tokens": 32,
        }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=100) as response:
            raw = response.read().decode(
                "utf-8",
                errors="replace",
            )

            reply = ""

            try:
                data = json.loads(raw)

                if provider == "gemini":
                    reply = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                    )

                elif provider == "cohere":
                    content = (
                        data.get("message", {})
                        .get("content", [])
                    )
                    reply = " ".join(
                        str(item.get("text", ""))
                        for item in content
                        if isinstance(item, dict)
                    )

                else:
                    reply = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )

            except Exception:
                reply = ""

            return {
                "ok": True,
                "provider": provider,
                "model": model,
                "http": response.status,
                "reply": str(reply).strip()[:100],
            }

    except urllib.error.HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "http": exc.code,
            "error": " ".join(body.split())[:350],
        }

    except (
        urllib.error.URLError,
        TimeoutError,
        socket.timeout,
    ) as exc:
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "http": None,
            "error": type(exc).__name__,
        }

# === TEMP_AI_SELFTEST_END ===

# === TEMP_COHERE_ADAPTER_TEST_BEGIN ===
@app.post(
    "/__ai-selftest-cohere/{model}",
    include_in_schema=False,
)
def _ai_selftest_cohere_adapter(
    model: str,
    x_ai_selftest_token: str | None = _AIHeader(
        default=None,
        alias="X-AI-Selftest-Token",
    ),
):
    import secrets
    from app.study_provider import get_provider, StudyProviderError

    if not secrets.compare_digest(
        x_ai_selftest_token or "",
        _AI_SELFTEST_TOKEN,
    ):
        raise _AIHTTPException(status_code=404)

    allowed = {
        "command-a-plus-05-2026",
        "command-a-reasoning-08-2025",
        "command-a-03-2025",
    }

    if model not in allowed:
        raise _AIHTTPException(status_code=404)

    try:
        provider = get_provider("cohere")

        answer = provider.generate(
            model=model,
            system_prompt="Bu bir teknik bağlantı testidir.",
            history=[],
            prompt="Sadece TEST_OK yaz.",
            attachments=[],
            temperature=0,
            max_output_tokens=2048,
        )

        return {
            "ok": bool(answer and answer.strip()),
            "provider": "cohere",
            "model": model,
            "reply": (answer or "").strip()[:300],
        }

    except StudyProviderError as exc:
        return {
            "ok": False,
            "provider": "cohere",
            "model": model,
            "code": exc.code,
            "retryable": exc.retryable,
            "error": str(exc)[:300],
        }

    except Exception as exc:
        return {
            "ok": False,
            "provider": "cohere",
            "model": model,
            "code": None,
            "error": f"{type(exc).__name__}: {str(exc)[:250]}",
        }

# === TEMP_COHERE_ADAPTER_TEST_END ===

# === TEMP_GROQ_ADAPTER_TEST_BEGIN ===
@app.post(
    "/__ai-selftest-groq/{model:path}",
    include_in_schema=False,
)
def _ai_selftest_groq_adapter(
    model: str,
    x_ai_selftest_token: str | None = _AIHeader(
        default=None,
        alias="X-AI-Selftest-Token",
    ),
):
    import secrets
    from app.study_provider import get_provider, StudyProviderError

    if not secrets.compare_digest(
        x_ai_selftest_token or "",
        _AI_SELFTEST_TOKEN,
    ):
        raise _AIHTTPException(status_code=404)

    allowed = {
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "qwen/qwen3.6-27b",
        "llama-3.3-70b-versatile",
    }

    if model not in allowed:
        raise _AIHTTPException(status_code=404)

    try:
        provider = get_provider("groq")

        answer = provider.generate(
            model=model,
            system_prompt="Bu bir teknik bağlantı testidir.",
            history=[],
            prompt="Sadece TEST_OK yaz.",
            attachments=[],
            temperature=0,
            max_output_tokens=256,
        )

        return {
            "ok": bool(answer and answer.strip()),
            "provider": "groq",
            "model": model,
            "reply": (answer or "").strip()[:300],
        }

    except StudyProviderError as exc:
        return {
            "ok": False,
            "provider": "groq",
            "model": model,
            "code": exc.code,
            "retryable": exc.retryable,
            "error": str(exc)[:300],
        }

    except Exception as exc:
        return {
            "ok": False,
            "provider": "groq",
            "model": model,
            "code": None,
            "error": f"{type(exc).__name__}: {str(exc)[:250]}",
        }

# === TEMP_GROQ_ADAPTER_TEST_END ===

# === TEMP_GROQ_DIRECT_TEST_BEGIN ===
@app.post(
    "/__ai-selftest-groq-direct/{model:path}",
    include_in_schema=False,
)
def _ai_selftest_groq_direct(
    model: str,
    x_ai_selftest_token: str | None = _AIHeader(
        default=None,
        alias="X-AI-Selftest-Token",
    ),
):
    import json
    import secrets
    import urllib.error
    import urllib.request

    from app.study_provider import get_provider

    if not secrets.compare_digest(
        x_ai_selftest_token or "",
        _AI_SELFTEST_TOKEN,
    ):
        raise _AIHTTPException(status_code=404)

    allowed = {
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "qwen/qwen3.6-27b",
        "llama-3.3-70b-versatile",
    }

    if model not in allowed:
        raise _AIHTTPException(status_code=404)

    provider = get_provider("groq")
    provider._require_key()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Bu bir teknik bağlantı testidir.",
            },
            {
                "role": "user",
                "content": "Sadece TEST_OK yaz.",
            },
        ],
        "temperature": 0,
        "max_tokens": 128,
        "stream": False,
    }

    request = urllib.request.Request(
        provider.BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=provider._headers(),
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=100,
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        answer = provider._answer_from_openai_response(result)

        return {
            "ok": True,
            "model": model,
            "http": 200,
            "reply": answer[:200],
        }

    except urllib.error.HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        return {
            "ok": False,
            "model": model,
            "http": exc.code,
            "error": " ".join(body.split())[:400],
        }

    except Exception as exc:
        return {
            "ok": False,
            "model": model,
            "http": None,
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
        }

# === TEMP_GROQ_DIRECT_TEST_END ===

# === TEMP_MISTRAL_DIRECT_TEST_BEGIN ===
@app.post(
    "/__ai-selftest-mistral-direct/{model:path}",
    include_in_schema=False,
)
def _ai_selftest_mistral_direct(
    model: str,
    x_ai_selftest_token: str | None = _AIHeader(
        default=None,
        alias="X-AI-Selftest-Token",
    ),
):
    import json
    import secrets
    import urllib.error
    import urllib.request

    from app.study_provider import get_provider

    if not secrets.compare_digest(
        x_ai_selftest_token or "",
        _AI_SELFTEST_TOKEN,
    ):
        raise _AIHTTPException(status_code=404)

    allowed = {
        "mistral-medium-latest",
        "mistral-small-latest",
    }

    if model not in allowed:
        raise _AIHTTPException(status_code=404)

    provider = get_provider("mistral")
    provider._require_key()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Sadece TEST_OK yaz.",
            }
        ],
        "temperature": 0,
        "max_tokens": 64,
        "stream": False,
    }

    request = urllib.request.Request(
        provider.BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=provider._headers(),
    )

    def safe_limit_headers(headers):
        result = {}
        if not headers:
            return result

        for key, value in headers.items():
            low = key.lower()
            if (
                "ratelimit" in low
                or "rate-limit" in low
                or low == "retry-after"
            ):
                result[key] = value

        return result

    try:
        with urllib.request.urlopen(
            request,
            timeout=100,
        ) as response:
            raw = response.read().decode("utf-8")
            result = json.loads(raw)

            answer = provider._answer_from_openai_response(result)

            return {
                "ok": True,
                "model": model,
                "http": getattr(response, "status", 200),
                "reply": answer[:200],
                "limit_headers": safe_limit_headers(
                    response.headers
                ),
            }

    except urllib.error.HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        return {
            "ok": False,
            "model": model,
            "http": exc.code,
            "error": " ".join(body.split())[:500],
            "limit_headers": safe_limit_headers(
                exc.headers
            ),
        }

    except Exception as exc:
        return {
            "ok": False,
            "model": model,
            "http": None,
            "error": (
                f"{type(exc).__name__}: "
                f"{str(exc)[:300]}"
            ),
            "limit_headers": {},
        }

# === TEMP_MISTRAL_DIRECT_TEST_END ===
