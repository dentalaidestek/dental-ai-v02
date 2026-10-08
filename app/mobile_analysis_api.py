"""Native Dental AI endpoints for the Android client."""
from pathlib import Path
import json
import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.main import (
    Analysis, ImageAsset, Patient, User, engine,
    _run_analysis_vision, _run_preliminary_ai, classify_dental_image,
)
from app.mobile_api import _mobile_user, _patient_payload

router = APIRouter(prefix="/api/mobile/v1", tags=["mobile-analysis"])


def _access(session: Session, user: User, analysis_id: int):
    analysis = session.get(Analysis, analysis_id)
    patient = session.get(Patient, analysis.patient_id) if analysis else None
    if not analysis or not patient or (user.role != "ADMIN" and patient.owner_user_id != user.id):
        raise HTTPException(status_code=404, detail="Analiz bulunamadı.")
    return analysis, patient


@router.post("/analyses")
async def create_mobile_analysis(
    background_tasks: BackgroundTasks,
    user: User = Depends(_mobile_user),
    patient_id: int = Form(...),
    tooth_number: Optional[str] = Form(None),
    clinical_notes: Optional[str] = Form(None),
    images: list[UploadFile] = File(default=[]),
):
    with Session(engine, expire_on_commit=False) as session:
        patient = session.get(Patient, patient_id)
        if not patient or (user.role != "ADMIN" and patient.owner_user_id != user.id):
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
        valid = [x for x in images if x and x.filename]
        if not valid or len(valid) > 4:
            raise HTTPException(status_code=422, detail="1 ile 4 arasında görüntü yükleyin.")
        analysis = Analysis(
            patient_id=patient_id,
            tooth_number=(tooth_number or "").strip() or None,
            clinical_notes=(clinical_notes or "").strip() or None,
            status="ANALYZING",
        )
        session.add(analysis)
        session.commit()
        session.refresh(analysis)
        saved = 0
        for image in valid:
            name = Path(image.filename).name
            ext = Path(name).suffix.lower()
            if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            stored = f"analysis_{analysis.id}_{uuid.uuid4().hex}{ext}"
            path = Path("uploads") / stored
            with path.open("wb") as out:
                shutil.copyfileobj(image.file, out)
            session.add(ImageAsset(
                analysis_id=analysis.id,
                original_filename=name,
                stored_filename=stored,
                file_path=str(path),
                image_type=classify_dental_image(str(path)),
            ))
            saved += 1
        if not saved:
            raise HTTPException(status_code=422, detail="Desteklenen görüntü formatı bulunamadı.")
        session.commit()
        analysis_id = analysis.id
    background_tasks.add_task(_run_analysis_vision, analysis_id)
    return {"ok": True, "analysis_id": analysis_id, "status": "ANALYZING"}


@router.get("/analyses/{analysis_id}")
def mobile_analysis(analysis_id: int, user: User = Depends(_mobile_user)):
    with Session(engine, expire_on_commit=False) as session:
        analysis, patient = _access(session, user, analysis_id)
        assets = session.exec(select(ImageAsset).where(ImageAsset.analysis_id == analysis_id).order_by(ImageAsset.id)).all()
        result = None
        result_file = Path(f"uploads/ai_results/{analysis_id}.json")
        if analysis.status == "AI_ANALYZED" and result_file.exists():
            try:
                result = json.loads(result_file.read_text(encoding="utf-8")).get("ai_result")
            except (OSError, ValueError, TypeError):
                result = None
        return {
            "analysis": {
                "id": analysis.id, "patient_id": analysis.patient_id,
                "tooth_number": analysis.tooth_number,
                "clinical_notes": analysis.clinical_notes,
                "status": analysis.status, "created_at": analysis.created_at,
            },
            "patient": _patient_payload(patient),
            "assets": [
                {"id": a.id, "original_filename": a.original_filename,
                 "image_type": a.image_type, "has_vision": bool(a.vision_snapshot_json)}
                for a in assets
            ],
            "ai_result": result,
        }


@router.post("/analyses/{analysis_id}/ai")
def start_mobile_analysis(
    analysis_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(_mobile_user),
):
    with Session(engine, expire_on_commit=False) as session:
        analysis, _ = _access(session, user, analysis_id)
        if analysis.status == "AI_ANALYZING":
            return {"ok": True, "status": analysis.status}
        assets = session.exec(select(ImageAsset).where(ImageAsset.analysis_id == analysis_id)).all()
        if not assets:
            raise HTTPException(status_code=422, detail="Analiz görüntüsü bulunamadı.")
        analysis.status = "AI_ANALYZING"
        session.add(analysis)
        session.commit()
    background_tasks.add_task(_run_preliminary_ai, analysis_id)
    return {"ok": True, "status": "AI_ANALYZING"}


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
        path = Path(asset.file_path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Görüntü dosyası bulunamadı.")
        media_type = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",".webp":"image/webp"}.get(path.suffix.lower(),"application/octet-stream")
        return FileResponse(path, media_type=media_type, filename=asset.original_filename)
