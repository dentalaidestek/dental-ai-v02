from pathlib import Path
import hmac
import os
import shutil
import tempfile

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile

from vision_service.engine import (
    MODEL_PATH,
    VisionError,
    analyze,
    model_available,
)

app = FastAPI(
    title="Dental AI Vision",
    version="0.1.0",
)

VISION_API_KEY = os.getenv("DENTAL_VISION_API_KEY", "").strip()


def require_vision_key(
    x_vision_key: str | None = Header(
        default=None,
        alias="X-Vision-Key",
    ),
):
    if not VISION_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Vision API güvenlik anahtarı yapılandırılmadı.",
        )

    if not x_vision_key or not hmac.compare_digest(
        x_vision_key,
        VISION_API_KEY,
    ):
        raise HTTPException(
            status_code=401,
            detail="Yetkisiz vision isteği.",
        )


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "dental-ai-vision",
        "motor": "motor-1",
        "model_available": model_available(),
        "model_file": MODEL_PATH.name,
        "api_protected": bool(VISION_API_KEY),
    }


@app.post("/analyze")
async def analyze_image(
    image: UploadFile = File(...),
    _: None = Depends(require_vision_key),
):
    suffix = Path(
        image.filename or "image.jpg"
    ).suffix.lower()

    if suffix not in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
    }:
        raise HTTPException(
            status_code=400,
            detail="Desteklenmeyen görüntü formatı.",
        )

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix,
        ) as tmp:
            shutil.copyfileobj(image.file, tmp)
            temp_path = tmp.name

        return analyze(temp_path)

    except VisionError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


@app.get("/diagnostics/runtime/{stage}")
def diagnostics_runtime(stage: str):
    import subprocess
    import sys

    probes = {
        "torch": """
import resource
print("BEFORE_MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, flush=True)
import torch
print("TORCH_OK", torch.__version__, flush=True)
print("AFTER_MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, flush=True)
""",
        "ultralytics": """
import resource
print("BEFORE_MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, flush=True)
from ultralytics import YOLO
print("ULTRALYTICS_OK", flush=True)
print("AFTER_MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, flush=True)
""",
    }

    if stage not in probes:
        raise HTTPException(
            status_code=400,
            detail="stage torch veya ultralytics olmalı",
        )

    try:
        p = subprocess.run(
            [sys.executable, "-c", probes[stage]],
            capture_output=True,
            text=True,
            timeout=90,
        )

        return {
            "stage": stage,
            "returncode": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr[-3000:],
        }

    except subprocess.TimeoutExpired:
        return {
            "stage": stage,
            "timeout": True,
        }
