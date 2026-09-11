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
