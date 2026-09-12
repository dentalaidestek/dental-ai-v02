from pathlib import Path
import hmac
import os
import shutil
import tempfile

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile

from vision_service.engine import MODEL_PATH, VisionError, model_available
from vision_service.motors.catalog import FINDING_CATALOG
from vision_service.motors.registry48 import MOTOR_SPECS
from vision_service.pipeline import analyze_panorama
from vision_service.readiness import readiness_snapshot

app = FastAPI(title="Dental AI Vision", version="0.2.0-vision48")
VISION_API_KEY = os.getenv("DENTAL_VISION_API_KEY", "").strip()


def require_vision_key(x_vision_key: str | None = Header(default=None, alias="X-Vision-Key")):
    if not VISION_API_KEY:
        raise HTTPException(status_code=503, detail="Vision API güvenlik anahtarı yapılandırılmadı.")
    if not x_vision_key or not hmac.compare_digest(x_vision_key, VISION_API_KEY):
        raise HTTPException(status_code=401, detail="Yetkisiz vision isteği.")


@app.get("/health")
def health():
    ready = readiness_snapshot()
    return {
        "ok": True,
        "service": "dental-ai-vision",
        "engine": "dental_ai_panorama_48_v1",
        "base_model_available": model_available(),
        "base_model_file": MODEL_PATH.name,
        "api_protected": bool(VISION_API_KEY),
        "catalog_total": len(FINDING_CATALOG),
        "implementation_total": ready["implementation_total"],
        "implementation_complete": ready["implementation_complete"],
        "runtime_validation_complete": ready["runtime_validation_complete"],
    }


@app.get("/readiness")
def readiness(_: None = Depends(require_vision_key)):
    return readiness_snapshot()


@app.get("/motor-catalog")
def motor_catalog(_: None = Depends(require_vision_key)):
    return {
        "total": len(MOTOR_SPECS),
        "motors": [
            {
                "code": spec.code,
                "label": FINDING_CATALOG[spec.code][0],
                "category": FINDING_CATALOG[spec.code][1],
                "strategy": spec.strategy,
                "sources": list(spec.sources),
                "description": spec.description,
            }
            for spec in MOTOR_SPECS.values()
        ],
    }


@app.post("/analyze")
async def analyze_image(
    image: UploadFile = File(...),
    _: None = Depends(require_vision_key),
):
    suffix = Path(image.filename or "image.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        raise HTTPException(status_code=400, detail="Desteklenmeyen görüntü formatı.")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(image.file, tmp)
            temp_path = tmp.name
        return analyze_panorama(temp_path)
    except VisionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


@app.get("/diagnostics/runtime/{stage}")
def diagnostics_runtime(stage: str, _: None = Depends(require_vision_key)):
    import subprocess
    import sys

    probes = {
        "torch": """
import resource
print('BEFORE_MB', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, flush=True)
import torch
print('TORCH_OK', torch.__version__, flush=True)
print('AFTER_MB', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, flush=True)
""",
        "ultralytics": """
import resource
print('BEFORE_MB', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, flush=True)
from ultralytics import YOLO
print('ULTRALYTICS_OK', flush=True)
print('AFTER_MB', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, flush=True)
""",
    }
    if stage not in probes:
        raise HTTPException(status_code=400, detail="stage torch veya ultralytics olmalı")
    try:
        p = subprocess.run([sys.executable, "-c", probes[stage]], capture_output=True, text=True, timeout=90)
        return {"stage": stage, "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr[-3000:]}
    except subprocess.TimeoutExpired:
        return {"stage": stage, "timeout": True}
