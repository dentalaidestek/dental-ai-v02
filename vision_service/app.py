from pathlib import Path
from contextlib import contextmanager, ExitStack
from app.execution import CapacityExceeded, WorkGate
import hmac
import os
import tempfile

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from PIL import Image

from vision_service.anatomy_mesh import AnatomyMeshError, anatomy_obj
from vision_service.bitewing_ensemble import BitewingEngineError, analyze_bitewing, configured as bitewing_configured
from vision_service.engine import MODEL_PATH, VisionError, model_available
from vision_service.intraoral_oraldetect import OralDetectError, analyze_intraoral, configured as oraldetect_configured
from vision_service.intraoral_ensemble import IntraoralEnsembleError, analyze_intraoral_ensemble, configured as intraoral_ensemble_configured
from vision_service.periapical_pai import PeriapicalPAIError, analyze_periapical, configured as periapical_configured
from vision_service.motors.catalog import FINDING_CATALOG
from vision_service.motors.registry48 import MOTOR_SPECS
from vision_service.photo3d import Photo3DError, reconstruct
from vision_service.pipeline import analyze_panorama
from vision_service.readiness import readiness_snapshot

app = FastAPI(title="Dental AI Vision", version="0.10.0-intraoral-photo-viewer")
VISION_API_KEY = os.getenv("DENTAL_VISION_API_KEY", "").strip()

def require_vision_key(x_vision_key: str | None = Header(default=None, alias="X-Vision-Key")):
    if not VISION_API_KEY: raise HTTPException(status_code=503, detail="Vision API güvenlik anahtarı yapılandırılmadı.")
    if not x_vision_key or not hmac.compare_digest(x_vision_key, VISION_API_KEY): raise HTTPException(status_code=401, detail="Yetkisiz vision isteği.")

@app.get("/health")
def health():
    return {"ok": True, "service": "dental-ai-vision"}

