import os
import json
import uuid
from datetime import datetime
from pathlib import Path

import shutil
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
from typing import Optional

from dental_rag.rag import (
    get_relevant_context,
    get_specialty_relevant_context,
)
from dental_rag.specialty_router import classify_specialties

from fastapi import (
    FastAPI,
    Form,
    Request,
    UploadFile,
    File,
    BackgroundTasks,
    Cookie,
)
from fastapi.responses import HTMLResponse, RedirectResponse
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


app = FastAPI(title="DENTAL-AI", version="0.1.0")

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
):
    display_name = display_name.strip()
    email = email.strip().lower()
    username = username.strip().lower()

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

    if not display_name or not email or not username:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Tüm alanları doldurun.",
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

        response = RedirectResponse(
            url="/",
            status_code=303,
        )

        create_user_session(response, user.id)

        return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None},
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
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
def template_user_context(request: Request):
    return {"user": get_current_user(request)}

templates = Jinja2Templates(
    directory=BASE/"templates",
    context_processors=[template_user_context],
)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        patients = s.exec(select(Patient).order_by(Patient.id.desc())).all()
        analyses = s.exec(select(Analysis).order_by(Analysis.id.desc())).all()
        records = s.exec(select(ClinicalRecord)).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "patients": patients,
            "analyses": analyses,
            "records": records
        }
    )


@app.get("/patients/new", response_class=HTMLResponse)
def new_patient(request: Request):
    return templates.TemplateResponse(request=request, name="patient_new.html", context={})

@app.post("/patients/new")
def create_patient(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    birth_date: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    chief_complaint: Optional[str] = Form(None),
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

    # Türkiye telefon numarası doğrulaması
    if phone:
        if not phone.isdigit() or len(phone) != 11 or not phone.startswith("05"):
            return templates.TemplateResponse(
                request=request,
                name="patient_new.html",
                context={
                    "error": "Telefon numarası 05 ile başlamalı ve toplam 11 rakam olmalıdır."
                },
                status_code=400,
            )

    with Session(engine, expire_on_commit=False) as s:
        patient = Patient(
            anonymous_id=f"PAT-{uuid.uuid4().hex[:10].upper()}",
            owner_user_id=user.id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            birth_date=birth_date,
            age=calculated_age,
            chief_complaint=chief_complaint.strip() if chief_complaint else None,
        )

        s.add(patient)
        s.commit()
        s.refresh(patient)

        return RedirectResponse(
            f"/patients/{patient.id}",
            status_code=303
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

        analysis_assets = {}
        for analysis in analyses:
            analysis_assets[analysis.id] = s.exec(
                select(ImageAsset).where(
                    ImageAsset.analysis_id == analysis.id
                )
            ).all()

        return templates.TemplateResponse(
            request=request,
            name="patient_detail.html",
            context={
                "patient": patient,
                "analyses": analyses,
                "treatments": treatments,
                "analysis_assets": analysis_assets,
            },
        )

@app.get("/analysis/new/{patient_id}", response_class=HTMLResponse)
def new_analysis(request: Request, patient_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with Session(engine, expire_on_commit=False) as s:
        patient = s.get(Patient, patient_id)

        if not patient:
            return HTMLResponse("Hasta bulunamadı", status_code=404)

        if user.role != "ADMIN" and patient.owner_user_id != user.id:
            return HTMLResponse("Bu hastaya erişim yetkiniz yok.", status_code=403)
    return templates.TemplateResponse(request=request, name="analysis_new.html", context={"patient": patient})


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


def _run_preliminary_ai(analysis_id: int):
    from app.ai_engine import build_preliminary_prompt, parse_ai_result
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
                image_paths=image_paths
            )

            ai_result = parse_ai_result(ai_text)

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


@app.post("/analysis/new/{patient_id}")
async def create_analysis(
    patient_id: int,
    background_tasks: BackgroundTasks,
    tooth_number: Optional[str] = Form(None),
    clinical_notes: Optional[str] = Form(None),
    images: list[UploadFile] = File(default=[]),
):
    with Session(engine, expire_on_commit=False) as s:

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
    clinical_id: str = Form(...),
    topic: str = Form(...),
    clinical_question: str = Form(...),
    claim: str = Form(...),
    evidence_grade: str = Form("UNASSESSED"),
    consensus_status: str = Form("UNASSESSED"),
    ai_use: str = Form("NOT_DEFINED"),
    safety_notes: Optional[str] = Form(None),
):
    with Session(engine, expire_on_commit=False) as s:
        s.add(ClinicalRecord(
            clinical_id=clinical_id, topic=topic, clinical_question=clinical_question,
            claim=claim, evidence_grade=evidence_grade,
            consensus_status=consensus_status, ai_use=ai_use, safety_notes=safety_notes
        ))
        s.commit()
    return RedirectResponse("/admin", status_code=303)

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
    # BURADA GEMMA ÇALIŞMIYOR.
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

@app.post("/analysis/{analysis_id}/final", response_class=HTMLResponse)
async def final_analysis(
    request: Request,
    analysis_id: int
):

    from app.ai_engine import (
        build_final_prompt,
        parse_ai_result
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
    # SADECE SON AŞAMADA GEMMA ÇALIŞIR
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
            image_paths=image_paths
        )

        ai_result = parse_ai_result(
            ai_text
        )

        # Nihai sonuç
        if isinstance(ai_result, dict):
            # Sadece gerçekten beklenen final JSON'u geldiyse FINAL kabul et.
            required_fields = {
                "most_likely",
                "differential",
                "findings",
                "treatment_options",
                "preferred_approach",
            }

            if required_fields.issubset(ai_result.keys()):
                ai_result["status"] = "FINAL"
            else:
                ai_result["status"] = "AI_INVALID"
                ai_result["error"] = (
                    "Gemma beklenen final JSON formatını üretmedi."
                )

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
        patients = s.exec(
            select(Patient).order_by(Patient.id.desc())
        ).all()

        analyses = s.exec(
            select(Analysis).order_by(Analysis.id.desc())
        ).all()

        records = s.exec(select(ClinicalRecord)).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "patients": patients,
            "analyses": analyses,
            "records": records,
            "ai_question": question,
            "ai_answer": answer,
            "ai_error": error,
        },
    )
