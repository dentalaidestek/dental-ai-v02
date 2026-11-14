"""Native Dental AI API using the production storage and durable work queue."""
from pathlib import Path
from PIL import Image
import json
import os
import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.main import (
    Analysis, ImageAsset, Patient, User, engine,
    _enqueue_work, _latest_work,
    classify_dental_image, storage_ensure_local, storage_persist_file,
    _record_realtime_event, _publish_realtime_event, on_loop,
)
from app.mobile_api import _mobile_user
from app.work_jobs import WorkJob

def _voice_review_ids(session, user_id, analysis_ids):
    if not analysis_ids:
        return set()
    return set(session.exec(select(WorkJob.resource_id).where(WorkJob.owner_user_id == user_id, WorkJob.resource_type == "ANALYSIS", WorkJob.resource_id.in_(analysis_ids), WorkJob.kind == "VOICE_REVIEW", WorkJob.status == "DONE")).all())


router = APIRouter(prefix="/api/mobile/v1", tags=["mobile-analysis"])

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
MOBILE_MAX_ANALYSIS_BYTES = max(1, int(os.getenv("MOBILE_MAX_ANALYSIS_BYTES", str(15 * 1024 * 1024))))
MOBILE_MAX_ANALYSIS_PIXELS = max(1, int(os.getenv("MOBILE_MAX_ANALYSIS_PIXELS", "40000000")))

def _copy_validated_analysis_image(upload: UploadFile, destination: Path) -> None:
    total = 0
    try:
        with destination.open("wb") as out:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MOBILE_MAX_ANALYSIS_BYTES:
                    raise HTTPException(status_code=413, detail="Görüntü dosyası çok büyük.")
                out.write(chunk)
        with Image.open(destination) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MOBILE_MAX_ANALYSIS_PIXELS:
                raise HTTPException(status_code=422, detail="Görüntü çözünürlüğü çok büyük.")
            image.verify()
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Geçersiz veya bozuk görüntü dosyası.") from exc


def _access(session: Session, user: User, analysis_id: int):
    analysis = session.get(Analysis, analysis_id)
    patient = session.get(Patient, analysis.patient_id) if analysis else None
    if not analysis or not patient or (user.role != "ADMIN" and patient.owner_user_id != user.id):
        raise HTTPException(status_code=404, detail="Analiz bulunamadı.")
    return analysis, patient


@router.post("/analyses")
async def create_mobile_analysis(
    user: User = Depends(_mobile_user),
    patient_id: int = Form(...),
    tooth_number: Optional[str] = Form(None),
    clinical_notes: Optional[str] = Form(None),
    images: list[UploadFile] = File(default=[]),
):
    valid = [x for x in images if x and x.filename]
    if not valid or len(valid) > 4:
        raise HTTPException(status_code=422, detail="1 ile 4 arasında görüntü yükleyin.")

    with Session(engine, expire_on_commit=False) as session:
        patient = session.get(Patient, patient_id)
        if not patient or (user.role != "ADMIN" and patient.owner_user_id != user.id):
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")

        analysis = Analysis(
            patient_id=patient_id,
            tooth_number=(tooth_number or "").strip() or None,
            clinical_notes=(clinical_notes or "").strip() or None,
            status="ANALYZING",
        )
        session.add(analysis)
        session.commit()
        session.refresh(analysis)

        allowed = {".jpg", ".jpeg", ".png", ".webp"}
        assets = []
        for image in valid:
            name = Path(image.filename).name
            ext = Path(name).suffix.lower()
            if ext not in allowed:
                continue
            stored = f"analysis_{analysis.id}_{uuid.uuid4().hex}{ext}"
            destination = Path("uploads") / stored
            destination.parent.mkdir(parents=True, exist_ok=True)
            _copy_validated_analysis_image(image, destination)
            storage_persist_file(destination)
            assets.append(ImageAsset(
                analysis_id=analysis.id,
                original_filename=name,
                stored_filename=stored,
                file_path=str(destination),
                image_type=classify_dental_image(str(destination)),
            ))

        if not assets:
            session.delete(analysis)
            session.commit()
            raise HTTPException(status_code=422, detail="Desteklenen görüntü formatı bulunamadı.")

        session.add_all(assets)
        session.flush()
        job = _enqueue_work(session, "VISION", "ANALYSIS", analysis.id)
        realtime=_record_realtime_event(session,user.id,"ANALYSIS_CREATED","analysis",analysis.id,{"analysis_id":analysis.id,"patient_id":patient_id,"status":analysis.status,"tooth_number":analysis.tooth_number})
        session.commit(); await _publish_realtime_event(realtime)
        return {
            "ok": True,
            "analysis_id": analysis.id,
            "status": analysis.status,
            "job_id": job.id,
        }


@router.get("/analyses/{analysis_id}")
def mobile_analysis(analysis_id: int, user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        analysis, patient = _access(session, user, analysis_id)
        assets = session.exec(
            select(ImageAsset)
            .where(ImageAsset.analysis_id == analysis_id)
            .order_by(ImageAsset.id)
        ).all()

        result = None
        if analysis.result_path:
            try:
                result_file = storage_ensure_local(analysis.result_path)
                result = json.loads(result_file.read_text(encoding="utf-8")).get("ai_result")
            except (OSError, ValueError, TypeError):
                result = None

        job = _latest_work(session, "ANALYSIS", analysis.id)
        return {
            "analysis": {
                "id": analysis.id,
                "patient_id": analysis.patient_id,
                "tooth_number": analysis.tooth_number,
                "clinical_notes": analysis.clinical_notes,
                "status": analysis.status,
                "created_at": analysis.created_at,
                "is_voice_review": analysis.id in _voice_review_ids(session, patient.owner_user_id, [analysis.id]),
            },
            "patient": _patient_payload(patient),
            "assets": [
                {
                    "id": a.id,
                    "original_filename": a.original_filename,
                    "image_type": a.image_type,
                    "has_vision": bool(a.vision_snapshot_json),
                }
                for a in assets
            ],
            "job": (
                {
                    "id": job.id,
                    "kind": job.kind,
                    "status": job.status,
                    "error_code": job.error_code,
                    "retryable": job.status in {"FAILED", "CANCELLED"},
                }
                if job else None
            ),
            "ai_result": result,
        }


@router.post("/analyses/{analysis_id}/ai")
def start_mobile_analysis(analysis_id: int, user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        analysis, _ = _access(session, user, analysis_id)
        if analysis.status == "AI_ANALYZED":
            return {"ok": True, "status": analysis.status}
        if analysis.status != "VISION_READY":
            raise HTTPException(
                status_code=409,
                detail=f"Görüntü analizi henüz hazır değil: {analysis.status}",
            )
        job = _enqueue_work(session, "PRELIMINARY", "ANALYSIS", analysis_id)
        realtime=_record_realtime_event(session,user.id,"ANALYSIS_UPDATED","analysis",analysis.id,{"analysis_id":analysis.id,"patient_id":analysis.patient_id,"status":analysis.status,"stage":"PRELIMINARY_QUEUED"})
        session.commit(); on_loop(_publish_realtime_event,realtime)
        return {"ok": True, "status": analysis.status, "job_id": job.id}


@router.get("/analyses/{analysis_id}/assets/{asset_id}")
def mobile_analysis_image(
    analysis_id: int,
    asset_id: int,
    user: User = Depends(_mobile_user),
):
    with Session(engine, expire_on_commit=False) as session:
        analysis, _ = _access(session, user, analysis_id)
        asset = session.get(ImageAsset, asset_id)
        if not asset or asset.analysis_id != analysis.id:
            raise HTTPException(status_code=404, detail="Görüntü bulunamadı.")
        try:
            path = storage_ensure_local(asset.file_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Görüntü dosyası bulunamadı.") from exc
        media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, media_type=media_type, filename=asset.original_filename, headers={"Cache-Control": "private, no-store"})

@router.get("/analyses")
def mobile_analysis_history(user: User = Depends(_mobile_user), patient_id: Optional[int] = None, before: Optional[int] = Query(None, ge=1), limit: int = Query(50, ge=1, le=100), tooth_number: Optional[str] = None):
    with Session(engine, expire_on_commit=False) as session:
        q = select(Analysis, Patient).join(Patient, Patient.id == Analysis.patient_id).where(
            Patient.owner_user_id == user.id
        )
        if patient_id is not None:
            patient = session.get(Patient, patient_id)
            if not patient or patient.owner_user_id != user.id:
                raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
            q = q.where(Analysis.patient_id == patient_id)
        if tooth_number is not None:
            import re
            if not re.fullmatch(r"(?:[1-4][1-8]|[5-8][1-5])", tooth_number):
                raise HTTPException(status_code=422, detail="Geçersiz FDI diş numarası.")
            q = q.where(Analysis.tooth_number == tooth_number)
        if before is not None:
            q = q.where(Analysis.id < before)
        rows = session.exec(q.order_by(Analysis.id.desc()).limit(limit + 1)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        voice_ids = _voice_review_ids(session, user.id, [a.id for a, _ in rows])
        return {"total": len(rows), "next_before": rows[-1][0].id if has_more and rows else None, "items": [{
            "id": a.id, "patient_id": a.patient_id, "patient_name": f"{p.first_name or ''} {p.last_name or ''}".strip(),
            "tooth_number": a.tooth_number, "clinical_notes": a.clinical_notes,
            "status": a.status, "created_at": a.created_at, "is_voice_review": a.id in voice_ids
        } for a, p in rows]}
