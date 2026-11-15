"""Native voice examination adapters reuse the web's ownership and clinical write rules."""
import hashlib
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.voice_exam import ApplyInput, apply_review
from app.mobile_api import _mobile_access_token, _mobile_request
from app.mobile_account_api import _account_user

router = APIRouter(tags=["mobile-voice-workflow"])


class AnonymousVoicePatientInput(BaseModel):
    request_key: str = Field(pattern=r"^[a-f0-9]{32}$")


def _create_anonymous_voice_patient(user_id: int, request_key: str):
    """Mirror the web's anonymous-patient entry, with a per-account retry identity."""
    from app import main as web

    identity = hashlib.sha256(f"{user_id}:{request_key}".encode("utf-8")).hexdigest()[:16].upper()
    anonymous_id = "SES-" + identity
    events = []
    with Session(web.engine, expire_on_commit=False) as session:
        # Serialize retries for this owner on PostgreSQL; the stable anonymous ID
        # makes a lost-response retry resolve to the same patient.
        owner = session.exec(
            select(web.User).where(web.User.id == user_id).with_for_update()
        ).first()
        if not owner or not owner.is_active:
            raise HTTPException(status_code=401, detail="Oturum geçersiz veya süresi dolmuş.")
        patient = session.exec(
            select(web.Patient).where(
                web.Patient.owner_user_id == user_id,
                web.Patient.anonymous_id == anonymous_id,
            )
        ).first()
        created = patient is None
        if created:
            patient = web.Patient(owner_user_id=user_id, anonymous_id=anonymous_id)
            session.add(patient)
            session.flush()
            events = web._record_patient_realtime_events(session, patient, "PATIENT_CREATED")
            session.commit()
        result = {
            "id": patient.id,
            "anonymous_id": patient.anonymous_id,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "phone": patient.phone,
            "birth_date": patient.birth_date,
            "age": patient.age,
            "chief_complaint": patient.chief_complaint,
            "created_at": patient.created_at.isoformat() if patient.created_at else None,
        }
    for event in events:
        web.on_loop(web._publish_realtime_event, event)
    return result, created


@router.post("/voice-exam/anonymous", status_code=201)
async def create_anonymous_voice_patient(
    payload: AnonymousVoicePatientInput,
    response: Response,
    token: str = Depends(_mobile_access_token),
    user=Depends(_account_user),
):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"
    patient, created = await run_in_threadpool(
        _create_anonymous_voice_patient, user.id, payload.request_key
    )
    response.status_code = 201 if created else 200
    return {"ok": True, "patient": patient, "already_created": not created}


@router.post("/patients/{patient_id}/voice-exam/apply")
async def apply_native_review(
    patient_id: int,
    payload: ApplyInput,
    background_tasks: BackgroundTasks,
    response: Response,
    token: str = Depends(_mobile_access_token),
    user=Depends(_account_user),
):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"
    result_response = await run_in_threadpool(
        apply_review, _mobile_request(token), patient_id, payload, background_tasks
    )
    result = json.loads(result_response.body)
    if result_response.status_code >= 400 or result.get("ok") is not True:
        raise HTTPException(
            status_code=result_response.status_code if result_response.status_code >= 400 else 502,
            detail=result.get("error", "Muayene kaydı doğrulanamadı."),
        )
    return result
