from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse

from vision_service.anatomy_mesh import AnatomyMeshError, anatomy_obj
from vision_service.model_manifest import model_path
from vision_service.motors.findings9 import normalize_class as normalize_findings9
from vision_service.motors.impacted_tooth import normalize_class as normalize_impacted
from vision_service.pipeline import _attach_fdi, _detector_outputs

app = FastAPI(title="Dental AI Anatomy 3D Direct FDI Test")
_FDI_MODEL = None


def _get_fdi_model():
    global _FDI_MODEL
    if _FDI_MODEL is None:
        from ultralytics import YOLO
        _FDI_MODEL = YOLO(str(model_path("motor1_fdi")))
    return _FDI_MODEL


def _fdi_from_label(label):
    s = str(label or "").strip()
    try:
        value = int(s)
        if value // 10 in {1, 2, 3, 4} and 1 <= value % 10 <= 8:
            return value
    except Exception:
        pass
    m = re.search(r"(?<!\d)([1-4][1-8])(?!\d)", s)
    if m:
        return int(m.group(1))
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 2:
        tail = digits[-2:]
        if re.fullmatch(r"[1-4][1-8]", tail):
            return int(tail)
    return None


def _predict_fdi(image_path: str):
    model = _get_fdi_model()
    passes = (0.40, 0.20, 0.08)
    best_by_fdi: dict[str, dict] = {}
    last_result = None
    used_conf = passes[0]

    def add_result(result, conf: float, recovery: bool):
        if result is None or result.boxes is None:
            return
        boxes = result.boxes.xyxy.detach().cpu().numpy()
        scores = result.boxes.conf.detach().cpu().numpy()
        classes = result.boxes.cls.detach().cpu().numpy().astype(int)
        names = result.names
        mask_polys = result.masks.xy if result.masks is not None and result.masks.xy is not None else []
        existing = list(best_by_fdi.values())
        widths = sorted(max(1.0, x["bbox"][2] - x["bbox"][0]) for x in existing)
        heights = sorted(max(1.0, x["bbox"][3] - x["bbox"][1]) for x in existing)
        med_w = widths[len(widths)//2] if widths else None
        med_h = heights[len(heights)//2] if heights else None

        for i, (box, score, class_id) in enumerate(zip(boxes, scores, classes)):
            label = names.get(int(class_id), str(class_id)) if isinstance(names, dict) else names[int(class_id)]
            fdi = _fdi_from_label(label)
            if fdi is None:
                continue
            key = str(fdi)
            if recovery and key in best_by_fdi:
                continue
            x1, y1, x2, y2 = [float(v) for v in box.tolist()]
            w, h = max(1.0, x2-x1), max(1.0, y2-y1)
            if recovery and med_w and med_h:
                if not (0.42*med_w <= w <= 1.95*med_w and 0.42*med_h <= h <= 2.10*med_h):
                    continue
                if float(score) < 0.10:
                    continue
            poly = []
            if i < len(mask_polys):
                arr = mask_polys[i]
                if arr is not None and len(arr) >= 3:
                    step = max(1, len(arr)//120)
                    poly = [[round(float(x), 1), round(float(y), 1)] for x, y in arr[::step]]
            item = {
                "fdi": fdi,
                "confidence": round(float(score), 4),
                "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                "polygon": poly,
                "recovered": bool(recovery),
                "recovery_conf": conf if recovery else None,
            }
            prev = best_by_fdi.get(key)
            if prev is None or item["confidence"] > prev["confidence"]:
                best_by_fdi[key] = item

    for idx, conf in enumerate(passes):
        result = model.predict(source=image_path, imgsz=1280, conf=conf, iou=0.45, verbose=False)[0]
        last_result = result
        used_conf = conf
        add_result(result, conf, recovery=idx > 0)
        if idx == 1 and len(best_by_fdi) >= 27:
            break

    return sorted(best_by_fdi.values(), key=lambda x: str(x["fdi"])), used_conf, last_result


def _run_pinned_findings(image_path: str, teeth: list[dict]):
    """Stable 3D-test path: only the pinned direct detectors, no heavy derived chain."""
    findings = []
    helpers = []
    execution = []
    warnings = []

    jobs = [
        ("findings9", normalize_findings9, 0.28, 0.45, 1280),
        ("impacted_tooth", normalize_impacted, 0.35, 0.45, 1280),
    ]
    for model_key, normalizer, conf, iou, imgsz in jobs:
        try:
            f, h = _detector_outputs(
                image_path=image_path,
                model_key=model_key,
                conf=conf,
                iou=iou,
                imgsz=imgsz,
                normalizer=normalizer,
            )
            findings.extend(f)
            helpers.extend(h)
            execution.append({"motor": model_key, "status": "ok", "conf": conf, "findings": len(f), "helpers": len(h)})
        except Exception as exc:
            warnings.append({"motor": model_key, "error_type": type(exc).__name__, "message": str(exc)})
            execution.append({"motor": model_key, "status": "error", "conf": conf, "error": str(exc)})

    if not any(item.get("motor") == "findings9" for item in findings):
        try:
            f, h = _detector_outputs(
                image_path=image_path,
                model_key="findings9",
                conf=0.18,
                iou=0.45,
                imgsz=1280,
                normalizer=normalize_findings9,
            )
            for item in f:
                item["recovery"] = True
                item["recovery_conf"] = 0.18
            findings.extend(f)
            helpers.extend(h)
            execution.append({"motor": "findings9_recovery", "status": "ok", "conf": 0.18, "findings": len(f), "helpers": len(h)})
        except Exception as exc:
            warnings.append({"motor": "findings9_recovery", "error_type": type(exc).__name__, "message": str(exc)})
            execution.append({"motor": "findings9_recovery", "status": "error", "conf": 0.18, "error": str(exc)})

    for item in findings + helpers:
        _attach_fdi(item, teeth)

    # Conservative duplicate suppression only. Keep spatially separate findings.
    ordered = sorted(findings, key=lambda x: float(x.get("confidence") or 0.0), reverse=True)
    kept = []
    for item in ordered:
        duplicate = False
        for old in kept:
            if old.get("finding_code") != item.get("finding_code"):
                continue
            if item.get("fdi") is not None and old.get("fdi") is not None and str(item.get("fdi")) == str(old.get("fdi")):
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
    kept.sort(key=lambda x: (str(x.get("fdi") or "99"), str(x.get("finding_code") or "")))
    return kept, helpers, execution, warnings


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


@app.get("/viewer-v3-enhance.js", response_class=PlainTextResponse)
def viewer_v3_enhance_js():
    path = Path(__file__).resolve().parent / "templates" / "viewer_v3_enhance.js"
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.get("/viewer-v3-realjaw.js", response_class=PlainTextResponse)
def viewer_v3_realjaw_js():
    path = Path(__file__).resolve().parent / "templates" / "viewer_v3_realjaw.js"
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.get("/viewer-v3-finalfix.js", response_class=PlainTextResponse)
def viewer_v3_finalfix_js():
    path = Path(__file__).resolve().parent / "templates" / "viewer_v3_finalfix.js"
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.get("/anatomy/tooth/{fdi}.obj", response_class=PlainTextResponse)
def anatomy_tooth(fdi: int):
    try:
        return PlainTextResponse(anatomy_obj(int(fdi)), media_type="text/plain", headers={"Cache-Control": "no-store"})
    except AnatomyMeshError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "anatomy3d-direct-fdi",
        "fdi_path": "legacy-direct-yolo",
        "finding_path": "direct-pinned-only",
        "real_jaw_reference": True,
        "fdi_recovery": True,
    }


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

        teeth, used_conf, raw = _predict_fdi(temp_path)
        findings, helpers, execution, warnings = _run_pinned_findings(temp_path, teeth)

        return {
            "engine": "dental_ai_3d_direct_test_v2",
            "modality": "PANORAMIC",
            "teeth": teeth,
            "tooth_count": len(teeth),
            "unique_fdi_count": len({str(t.get("fdi")) for t in teeth}),
            "has_segmentation": bool(raw is not None and raw.masks is not None),
            "fdi_source": "legacy_direct_yolo",
            "fdi_conf_used": used_conf,
            "fdi_recovered_count": sum(1 for t in teeth if t.get("recovered")),
            "findings": findings,
            "finding_count": len(findings),
            "helpers": helpers,
            "helper_signal_count": len(helpers),
            "motor_execution": execution,
            "warnings": warnings,
            "finding_path": "direct-pinned-only",
        }
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
