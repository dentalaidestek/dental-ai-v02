from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse

from vision_service.anatomy_mesh import AnatomyMeshError, anatomy_obj
from vision_service.model_manifest import model_path
from vision_service.pipeline import _attach_fdi, analyze_panorama

app = FastAPI(title="Dental AI Anatomy 3D Direct FDI Test")
_FDI_MODEL = None


def _get_fdi_model():
    global _FDI_MODEL
    if _FDI_MODEL is None:
        from ultralytics import YOLO
        _FDI_MODEL = YOLO(str(model_path("motor1_fdi")))
    return _FDI_MODEL


def _predict_fdi(image_path: str):
    model = _get_fdi_model()
    # This is the same direct inference path that the first working Kaggle 3D test used.
    passes = (0.40, 0.20, 0.08)
    last = None
    used_conf = passes[-1]
    for conf in passes:
        last = model.predict(source=image_path, imgsz=1280, conf=conf, iou=0.45, verbose=False)[0]
        count = len(last.boxes) if last.boxes is not None else 0
        used_conf = conf
        if count:
            break

    result = last
    teeth = []
    if result is None or result.boxes is None:
        return teeth, used_conf, None

    boxes = result.boxes.xyxy.detach().cpu().numpy()
    scores = result.boxes.conf.detach().cpu().numpy()
    classes = result.boxes.cls.detach().cpu().numpy().astype(int)
    names = result.names
    mask_polys = result.masks.xy if result.masks is not None and result.masks.xy is not None else []

    best_by_fdi = {}
    for i, (box, score, class_id) in enumerate(zip(boxes, scores, classes)):
        label = names.get(int(class_id), str(class_id)) if isinstance(names, dict) else names[int(class_id)]
        try:
            fdi = int(str(label))
        except Exception:
            fdi = str(label)

        poly = []
        if i < len(mask_polys):
            arr = mask_polys[i]
            if arr is not None and len(arr) >= 3:
                step = max(1, len(arr) // 120)
                poly = [[round(float(x), 1), round(float(y), 1)] for x, y in arr[::step]]

        item = {
            "fdi": fdi,
            "confidence": round(float(score), 4),
            "bbox": [round(float(v), 1) for v in box.tolist()],
            "polygon": poly,
        }
        key = str(fdi)
        prev = best_by_fdi.get(key)
        if prev is None or item["confidence"] > prev["confidence"]:
            best_by_fdi[key] = item

    teeth = sorted(best_by_fdi.values(), key=lambda x: str(x["fdi"]))
    return teeth, used_conf, result


@app.get("/", response_class=HTMLResponse)
@app.get("/viewer", response_class=HTMLResponse)
def viewer():
    path = Path(__file__).resolve().parent / "templates" / "viewer_v3.html"
    return HTMLResponse(path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@app.get("/viewer-v3.js", response_class=PlainTextResponse)
def viewer_v3_js():
    path = Path(__file__).resolve().parent / "templates" / "viewer_v3.js"
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.get("/viewer-v3-patch.js", response_class=PlainTextResponse)
def viewer_v3_patch_js():
    path = Path(__file__).resolve().parent / "templates" / "viewer_v3_patch.js"
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.get("/anatomy/tooth/{fdi}.obj", response_class=PlainTextResponse)
def anatomy_tooth(fdi: int):
    try:
        return PlainTextResponse(anatomy_obj(int(fdi)), media_type="text/plain", headers={"Cache-Control": "no-store"})
    except AnatomyMeshError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {"ok": True, "service": "anatomy3d-direct-fdi", "fdi_path": "legacy-direct-yolo"}


@app.post("/analyze")
async def analyze_image(image: UploadFile = File(...)):
    suffix = Path(image.filename or "image.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        raise HTTPException(status_code=400, detail="Desteklenmeyen görüntü formatı.")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(image.file, tmp)
            temp_path = tmp.name

        # First: restore the exact direct FDI path that previously produced 29 teeth.
        teeth, used_conf, raw = _predict_fdi(temp_path)

        # Findings are still produced by the Vision48 pipeline, but they no longer control
        # whether the 3D viewer receives teeth.
        try:
            base = analyze_panorama(temp_path)
        except Exception as exc:
            base = {"findings": [], "helpers": [], "warnings": [{"motor": "pipeline", "message": str(exc)}]}

        for item in list(base.get("findings") or []) + list(base.get("helpers") or []):
            if not item.get("fdi"):
                _attach_fdi(item, teeth)

        base["teeth"] = teeth
        base["tooth_count"] = len(teeth)
        base["unique_fdi_count"] = len({str(t.get("fdi")) for t in teeth})
        base["has_segmentation"] = bool(raw is not None and raw.masks is not None)
        base["fdi_source"] = "legacy_direct_yolo"
        base["fdi_conf_used"] = used_conf

        if not teeth:
            base["fdi_debug"] = {
                "model": model_path("motor1_fdi").name,
                "passes": [0.40, 0.20, 0.08],
                "message": "Direct FDI model returned zero boxes",
            }
        return base
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
