from pathlib import Path
import shutil
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile

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


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "dental-ai-vision",
        "motor": "motor-1",
        "model_available": model_available(),
        "model_file": MODEL_PATH.name,
    }


@app.post("/analyze")
async def analyze_image(image: UploadFile = File(...)):
    suffix = Path(image.filename or "image.jpg").suffix.lower()

    if suffix not in {
        ".jpg", ".jpeg", ".png",
        ".webp", ".bmp", ".tif", ".tiff"
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
