"""Native Dental AI API using the production storage and durable work queue."""
from pathlib import Path
from app.clinical_media import sanitize_clinical_media_image
from app.upload_limits import MAX_ANALYSIS_IMAGE_BYTES, MAX_ANALYSIS_BATCH_BYTES, MAX_CLINICAL_IMAGE_PIXELS
from app.upload_io import validate_upload_batch, validate_path_batch
import json
import hashlib
import re
import os
import shutil
import tempfile
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.main import (
    Analysis, ImageAsset, Patient, PatientMedia, User, engine, MAX_ANALYSIS_IMAGES,
    _enqueue_work, _latest_work,
    classify_dental_image, storage_ensure_local, storage_persist_file,
    _record_realtime_event, _publish_realtime_event, on_loop,
)
from app.mobile_api import _mobile_user
from app.work_jobs import WorkJob
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

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
MOBILE_MAX_ANALYSIS_BYTES = MAX_ANALYSIS_IMAGE_BYTES
MOBILE_MAX_ANALYSIS_BATCH_BYTES = MAX_ANALYSIS_BATCH_BYTES
MOBILE_MAX_ANALYSIS_PIXELS = MAX_CLINICAL_IMAGE_PIXELS

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
        sanitize_clinical_media_image(
            destination,
            destination.suffix.lower(),
            MOBILE_MAX_ANALYSIS_PIXELS,
        )
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except ValueError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Geçersiz veya bozuk görüntü dosyası.") from exc

def _parse_existing_media_ids(raw):
    if raw is None or not raw.strip():
        return []
    parts=[part.strip() for part in raw.split(",")]
    if len(parts)>MAX_ANALYSIS_IMAGES or any(not re.fullmatch(r"[1-9][0-9]*",part) for part in parts):
        raise HTTPException(422,f"Geçerli ve en fazla {MAX_ANALYSIS_IMAGES} kayıtlı klinik görüntü seçin.")
    ids=[int(part) for part in parts]
    if len(set(ids))!=len(ids):
        raise HTTPException(422,"Aynı klinik görüntü birden fazla seçilemez.")
    return ids


def _copy_validated_existing_analysis_image(source: Path, destination: Path) -> None:
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    extension = source.suffix.lower()
    if extension not in allowed or not source.is_file():
        raise HTTPException(404, "Seçilen klinik görüntü dosyası bulunamadı.")
    try:
        total = 0
        with source.open("rb") as incoming, destination.open("wb") as outgoing:
            while True:
                chunk = incoming.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MOBILE_MAX_ANALYSIS_BYTES:
                    raise HTTPException(413, "Kayıtlı klinik görüntü çok büyük.")
                outgoing.write(chunk)
        # Sanitize the analysis copy even when an older archived object predates
        # the shared gallery-upload sanitizer.
        sanitize_clinical_media_image(
            destination,
            extension,
            MOBILE_MAX_ANALYSIS_PIXELS,
        )
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except ValueError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(422, "Kayıtlı klinik görüntü okunamadı veya bozuk.") from exc
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(422, "Kayıtlı klinik görüntü okunamadı veya bozuk.") from exc

def _access(session: Session, user: User, analysis_id: int):
    analysis = session.get(Analysis, analysis_id)
    patient = session.get(Patient, analysis.patient_id) if analysis else None
    if not analysis or not patient or (user.role != "ADMIN" and patient.owner_user_id != user.id):
        raise HTTPException(status_code=404, detail="Analiz bulunamadı.")
    return analysis, patient


def _upload_key(user_id,key):return hashlib.sha256(f'mobile-analysis-upload:{user_id}:{key}'.encode()).hexdigest()


def _upload_digest(patient_id,tooth,notes,images,existing_media_ids=()):
    hashes=[]
    batch_total=0
    for image in images:
        digest=hashlib.sha256();size=0
        try:
            while True:
                chunk=image.file.read(1024*1024)
                if not chunk:break
                size+=len(chunk)
                if size>MOBILE_MAX_ANALYSIS_BYTES:raise HTTPException(413,'Bir görüntü en fazla 25 MiB olabilir.')
                batch_total+=len(chunk)
                if batch_total>MOBILE_MAX_ANALYSIS_BATCH_BYTES:raise HTTPException(413,'Toplam analiz görüntüleri en fazla 80 MiB olabilir.')
                digest.update(chunk)
        finally:image.file.seek(0)
        hashes.append([image.filename,size,digest.hexdigest()])
    payload=[patient_id,(tooth or '').strip(),(notes or '').strip(),hashes]
    # Keep the historical new-file-only digest byte-for-byte compatible so
    # already pending uploads from older app versions remain recoverable.
    if existing_media_ids:
        payload=[patient_id,(tooth or '').strip(),(notes or '').strip(),list(existing_media_ids),hashes]
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest()


def _upload_receipt(session,user,receipt,patient_id):
    analysis,_=_access(session,user,receipt.resource_id)
    if analysis.patient_id!=patient_id:raise HTTPException(404,'Hasta yükleme kaydı bulunamadı.')
    return {'ok':True,'analysis_id':analysis.id,'patient_id':patient_id,'status':analysis.status,'job_id':json.loads(receipt.payload_json)['job_id']}


@router.get('/analyses/uploads/receipt')
def upload_receipt(patient_id:int=Query(...,ge=1),request_key:str=Query(...,pattern=r'^[A-Za-z0-9_-]{16,80}$'),user:User=Depends(_mobile_user)):
    from fastapi.responses import JSONResponse
    with Session(engine) as session:
        patient=session.get(Patient,patient_id)
        if not patient or user.role!='ADMIN' and patient.owner_user_id!=user.id:raise HTTPException(404,'Hasta bulunamadı.')
        row=session.exec(select(WorkJob).where(WorkJob.owner_user_id==user.id,WorkJob.kind=='UPLOAD_RECEIPT',WorkJob.dedupe_key==_upload_key(user.id,request_key))).first()
        return JSONResponse({'receipt':_upload_receipt(session,user,row,patient_id) if row else None},headers={'Cache-Control':'private, no-store','Vary':'Authorization'})


@router.post("/analyses")
async def create_mobile_analysis(
    user: User = Depends(_mobile_user),
    patient_id: int = Form(...),
    tooth_number: Optional[str] = Form(None),
    clinical_notes: Optional[str] = Form(None),
    images: list[UploadFile] = File(default=[]),
    request_key: Optional[str] = Form(None),
    existing_media_ids: Optional[str] = Form(None),
):
    if request_key is not None and not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',request_key):
        raise HTTPException(422,'Geçersiz yükleme anahtarı.')
    teeth=[x.strip() for x in (tooth_number or '').split(',') if x.strip()]
    if len(teeth)>32 or len(set(teeth))!=len(teeth) or any(not re.fullmatch(r'(?:[1-4][1-8]|[5-8][1-5])',x) for x in teeth):
        raise HTTPException(422,'Geçersiz FDI diş numarası.')
    if len(clinical_notes or '')>4000:raise HTTPException(422,'Klinik not en fazla 4000 karakter olabilir.')
    selected_media_ids=_parse_existing_media_ids(existing_media_ids)
    # Never silently discard an unnamed or malformed part of a clinical batch.
    # A partial success could associate the wrong images with a patient analysis.
    if any(not image or not image.filename for image in images):
        raise HTTPException(status_code=422, detail="Her klinik görüntünün dosya adı bulunmalıdır.")
    valid = images
    media_count=len(selected_media_ids)+len(valid)
    has_clinical_context=bool(teeth or (clinical_notes or "").strip())
    if media_count>MAX_ANALYSIS_IMAGES:
        raise HTTPException(status_code=422, detail=f"Kayıtlı ve yeni görüntülerin toplamı en fazla {MAX_ANALYSIS_IMAGES} olabilir.")
    if media_count==0 and not has_clinical_context:
        raise HTTPException(status_code=422, detail="Görüntü olmadan analiz başlatmak için diş numarası veya klinik bilgi girin.")
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    if any(Path(Path(image.filename).name).suffix.lower() not in allowed for image in valid):
        raise HTTPException(status_code=422, detail="Yalnızca JPEG, PNG veya WebP görüntüler yüklenebilir.")

    digest=await run_in_threadpool(_upload_digest,patient_id,tooth_number,clinical_notes,valid,selected_media_ids) if request_key else None
    receipt_key=_upload_key(user.id,request_key) if request_key else None
    with Session(engine, expire_on_commit=False) as session:
        if receipt_key and session.get_bind().dialect.name=='postgresql':
            # Per-request admission lock; do not acquire the owner lock before
            # the canonical queue's global admission lock.
            slot=int.from_bytes(hashlib.sha256(receipt_key.encode()).digest()[:8],byteorder='big',signed=True)
            session.execute(text('SELECT pg_advisory_xact_lock(:slot)'),{'slot':slot})
        patient = session.get(Patient, patient_id)
        if not patient or (user.role != "ADMIN" and patient.owner_user_id != user.id):
            raise HTTPException(status_code=404, detail="Hasta bulunamadı.")

        if receipt_key:
            receipt=session.exec(select(WorkJob).where(WorkJob.dedupe_key==receipt_key,WorkJob.owner_user_id==user.id,WorkJob.kind=='UPLOAD_RECEIPT')).first()
            if receipt:
                if receipt.source_hash!=digest:raise HTTPException(409,'Bu yükleme anahtarı farklı dosya veya klinik bilgiler için kullanılmış.')
                return _upload_receipt(session,user,receipt,patient_id)

        selected_media=[]
        if selected_media_ids:
            rows=session.exec(select(PatientMedia).where(
                PatientMedia.id.in_(selected_media_ids),
                PatientMedia.patient_id==patient_id,
            )).all()
            by_id={row.id:row for row in rows}
            if len(by_id)!=len(selected_media_ids):
                raise HTTPException(404,"Seçilen klinik görüntü bulunamadı.")
            for media_id in selected_media_ids:
                media=by_id.get(media_id)
                if not media or (user.role!="ADMIN" and media.owner_user_id!=user.id):
                    raise HTTPException(404,"Seçilen klinik görüntü bulunamadı.")
                selected_media.append(media)

        # Enforce actual byte counts for both fresh multipart files and saved
        # patient media before creating an Analysis row or staging any bytes.
        new_bytes = validate_upload_batch(
            valid,
            maximum_file=MOBILE_MAX_ANALYSIS_BYTES,
            maximum_total=MOBILE_MAX_ANALYSIS_BATCH_BYTES,
        )
        saved_paths = []
        for media in selected_media:
            try:
                saved_paths.append(Path(await run_in_threadpool(storage_ensure_local, media.file_path)))
            except FileNotFoundError as exc:
                raise HTTPException(404, "Seçilen klinik görüntü dosyası bulunamadı.") from exc
        saved_bytes = validate_path_batch(
            saved_paths,
            maximum_file=MOBILE_MAX_ANALYSIS_BYTES,
            maximum_total=MOBILE_MAX_ANALYSIS_BATCH_BYTES,
        )
        if new_bytes + saved_bytes > MOBILE_MAX_ANALYSIS_BATCH_BYTES:
            raise HTTPException(413, "Kayıtlı ve yeni görüntülerin toplamı en fazla 80 MiB olabilir.")

        analysis = Analysis(
            patient_id=patient_id,
            tooth_number=(tooth_number or "").strip() or None,
            clinical_notes=(clinical_notes or "").strip() or None,
            status="ANALYZING",
        )
        session.add(analysis)
        # Reserve the analysis ID without committing an unusable clinical record.
        # Image validation and work enqueue must succeed before the transaction commits.
        session.flush()
        session.refresh(analysis)

        assets = []
        Path('uploads').mkdir(parents=True,exist_ok=True)
        # Validate every saved and newly picked image before publishing any
        # clinical file or allocating a durable VISION job.
        with tempfile.TemporaryDirectory(prefix='.analysis-stage-',dir='uploads') as staging:
            staged=[]
            for media in selected_media:
                try:
                    source=Path(await run_in_threadpool(storage_ensure_local,media.file_path))
                except FileNotFoundError as exc:
                    raise HTTPException(404,"Seçilen klinik görüntü dosyası bulunamadı.") from exc
                ext=source.suffix.lower()
                stored=f'analysis_{analysis.id}_{uuid.uuid4().hex}{ext}'
                temporary=Path(staging)/stored
                destination=Path('uploads')/stored
                await run_in_threadpool(_copy_validated_existing_analysis_image,source,temporary)
                staged.append((temporary,destination))
                assets.append(ImageAsset(
                    analysis_id=analysis.id,
                    original_filename=Path(media.original_filename).name,
                    stored_filename=stored,
                    file_path=str(destination),
                    image_type=await run_in_threadpool(classify_dental_image,str(temporary)),
                ))
            for image in valid:
                name=Path(image.filename).name
                ext=Path(name).suffix.lower()
                stored=f'analysis_{analysis.id}_{uuid.uuid4().hex}{ext}'
                temporary=Path(staging)/stored
                destination=Path('uploads')/stored
                await run_in_threadpool(_copy_validated_analysis_image,image,temporary)
                staged.append((temporary,destination))
                image_type=await run_in_threadpool(classify_dental_image,str(temporary))
                assets.append(ImageAsset(analysis_id=analysis.id,original_filename=name,stored_filename=stored,file_path=str(destination),image_type=image_type))
            session.add_all(assets)
            session.flush()
            # Reserve canonical queue capacity before any storage publication.
            # Match the canonical web handler: image-backed work uses VISION;
            # clinical-context-only work uses the preliminary analysis queue.
            job=_enqueue_work(session,'VISION' if assets else 'PRELIMINARY','ANALYSIS',analysis.id)
            for temporary,destination in staged:
                shutil.move(str(temporary),str(destination))
                await run_in_threadpool(storage_persist_file,destination)
        if receipt_key:
            session.add(WorkJob(owner_user_id=user.id,resource_id=analysis.id,resource_type='ANALYSIS',kind='UPLOAD_RECEIPT',source_hash=digest,dedupe_key=receipt_key,status='DONE',payload_json=json.dumps({'job_id':job.id})))
        realtime=_record_realtime_event(session,user.id,"ANALYSIS_CREATED","analysis",analysis.id,{"analysis_id":analysis.id,"patient_id":patient_id,"status":analysis.status,"tooth_number":analysis.tooth_number})
        session.commit(); await _publish_realtime_event(realtime)
        return {
            "ok": True,
            "analysis_id": analysis.id,
            "patient_id": patient_id,
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
