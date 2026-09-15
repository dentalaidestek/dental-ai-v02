from __future__ import annotations

import os
import resource
import threading
import time
from pathlib import Path


MODEL_PATH = Path(
    os.getenv(
        "DENTAL_VISION_MODEL_PATH",
        str(
            Path(__file__).resolve().parent.parent
            / "models"
            / "vision"
            / "YOLOv11x-seg.pt"
        ),
    )
).expanduser()

_MODEL = None
_LOCK = threading.Lock()


class VisionError(RuntimeError):
    pass


def _rss_mb() -> float:
    try:
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:
        return -1.0


def _trace(stage: str, **fields) -> None:
    parts = ["[VISION_TRACE]", f"stage={stage}", f"rss_mb={_rss_mb()}"]
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    print(" ".join(parts), flush=True)


def model_available() -> bool:
    return MODEL_PATH.is_file()


def get_model():
    global _MODEL
    _trace("get_model_enter", cached=_MODEL is not None, model_exists=MODEL_PATH.is_file())
    if _MODEL is not None:
        _trace("get_model_cached")
        return _MODEL
    with _LOCK:
        if _MODEL is not None:
            _trace("get_model_cached_after_lock")
            return _MODEL
        if not MODEL_PATH.is_file():
            _trace("model_file_missing")
            raise VisionError(f"Model bulunamadı: {MODEL_PATH}")
        try:
            _trace("torch_import_start")
            t_torch = time.perf_counter()
            import torch
            _trace("torch_import_ok", seconds=round(time.perf_counter() - t_torch, 3), torch_version=torch.__version__)
            _trace("ultralytics_import_start")
            t0 = time.perf_counter()
            from ultralytics import YOLO
            _trace("ultralytics_import_ok", seconds=round(time.perf_counter() - t0, 3))
            _trace("yolo_load_start")
            t1 = time.perf_counter()
            _MODEL = YOLO(str(MODEL_PATH))
            _trace("yolo_load_ok", seconds=round(time.perf_counter() - t1, 3))
        except Exception as exc:
            _trace("yolo_load_error", error_type=type(exc).__name__)
            raise VisionError(f"Model yüklenemedi: {exc}") from exc
        return _MODEL


def _predict(model, source, conf: float, *, imgsz: int = 1280, pass_name: str = "original"):
    _trace("predict_start", imgsz=imgsz, conf=conf, iou=0.45, pass_name=pass_name)
    started = time.perf_counter()
    try:
        result = model.predict(
            source=source,
            imgsz=imgsz,
            conf=conf,
            iou=0.45,
            max_det=80,
            verbose=False,
        )[0]
        box_count = len(result.boxes) if result.boxes is not None else 0
        _trace(
            "predict_ok",
            seconds=round(time.perf_counter() - started, 3),
            boxes=box_count,
            masks=result.masks is not None,
            conf=conf,
            pass_name=pass_name,
        )
        return result
    except Exception as exc:
        _trace(
            "predict_error",
            error_type=type(exc).__name__,
            seconds=round(time.perf_counter() - started, 3),
            conf=conf,
            pass_name=pass_name,
        )
        raise VisionError(f"Analiz başarısız: {exc}") from exc


def _enhanced_sources(image_path: str):
    """Return conservative panoramic enhancements only for zero-detection fallback."""
    try:
        import cv2
        import numpy as np

        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None or img.size == 0:
            return []

        h, w = img.shape[:2]
        # Remove tiny outer borders/labels that can dominate a low-resolution pano,
        # while preserving essentially the entire jaw.
        xpad = max(0, int(w * 0.015))
        ypad = max(0, int(h * 0.015))
        cropped = img[ypad:h-ypad if h-ypad > ypad else h, xpad:w-xpad if w-xpad > xpad else w]

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cropped)
        clahe_bgr = cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR)

        # Mild unsharp masking helps thin tooth boundaries without inventing anatomy.
        blur = cv2.GaussianBlur(clahe, (0, 0), 1.2)
        sharp = cv2.addWeighted(clahe, 1.45, blur, -0.45, 0)
        sharp = cv2.normalize(sharp, None, 0, 255, cv2.NORM_MINMAX)
        sharp_bgr = cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR)

        return [
            ("clahe", clahe_bgr),
            ("clahe_sharp", sharp_bgr),
        ]
    except Exception as exc:
        _trace("enhance_error", error_type=type(exc).__name__)
        return []


def _label_from(names, class_id: int):
    if isinstance(names, dict):
        return names.get(class_id, str(class_id))
    return names[class_id]


def _is_valid_fdi(value) -> bool:
    try:
        n = int(str(value))
    except Exception:
        return False
    return 11 <= n <= 48 and (n // 10) in {1, 2, 3, 4} and 1 <= (n % 10) <= 8


def _extract_teeth(result) -> list[dict]:
    if result.boxes is None:
        return []

    boxes = result.boxes.xyxy.detach().cpu().numpy()
    scores = result.boxes.conf.detach().cpu().numpy()
    classes = result.boxes.cls.detach().cpu().numpy().astype(int)
    names = result.names

    # One FDI number can occasionally be emitted more than once at very low fallback
    # thresholds. Keep only the highest-confidence instance per FDI.
    best: dict[str, dict] = {}
    for box, score, class_id in zip(boxes, scores, classes):
        label = _label_from(names, int(class_id))
        if not _is_valid_fdi(label):
            continue
        fdi = int(str(label))
        item = {
            "fdi": fdi,
            "confidence": round(float(score), 4),
            "bbox": [
                round(float(box[0]), 1),
                round(float(box[1]), 1),
                round(float(box[2]), 1),
                round(float(box[3]), 1),
            ],
        }
        key = str(fdi)
        if key not in best or item["confidence"] > best[key]["confidence"]:
            best[key] = item

    teeth = list(best.values())
    teeth.sort(key=lambda x: str(x["fdi"]))
    return teeth


def analyze(image_path: str) -> dict:
    _trace("analyze_enter")
    model = get_model()

    primary_conf = float(os.getenv("DENTAL_FDI_CONF", "0.40"))
    fallback_conf = float(os.getenv("DENTAL_FDI_FALLBACK_CONF", "0.18"))
    rescue_conf = float(os.getenv("DENTAL_FDI_RESCUE_CONF", "0.08"))

    attempts = []

    # 1) Normal clinical pass.
    result = _predict(model, image_path, primary_conf, imgsz=1280, pass_name="original_primary")
    teeth = _extract_teeth(result)
    attempts.append({"pass": "original_primary", "count": len(teeth), "conf": primary_conf})

    # 2) Lower-confidence original image only if nothing at all was found.
    if not teeth:
        result = _predict(model, image_path, fallback_conf, imgsz=1536, pass_name="original_low_conf")
        teeth = _extract_teeth(result)
        attempts.append({"pass": "original_low_conf", "count": len(teeth), "conf": fallback_conf})

    # 3) Contrast-normalized rescue. This is deliberately used only after two zero passes.
    if not teeth:
        for pass_name, source in _enhanced_sources(image_path):
            result = _predict(model, source, rescue_conf, imgsz=1536, pass_name=pass_name)
            teeth = _extract_teeth(result)
            attempts.append({"pass": pass_name, "count": len(teeth), "conf": rescue_conf})
            if teeth:
                break

    _trace(
        "analyze_complete",
        teeth=len(teeth),
        unique_fdi=len({str(x["fdi"]) for x in teeth}),
        attempts=attempts,
    )

    return {
        "engine": "dental_ai_vision_motor_1",
        "tooth_count": len(teeth),
        "unique_fdi_count": len({str(x["fdi"]) for x in teeth}),
        "has_segmentation": bool(getattr(result, "masks", None) is not None),
        "fdi_attempts": attempts,
        "teeth": teeth,
    }
