from __future__ import annotations

import threading
from typing import Any, Callable

from vision_service.model_sources import optional_model_path
from vision_service.motors.catalog import FINDING_CATALOG


_CACHE: dict[str, Any] = {}
_LOCK = threading.Lock()


def model_available(key: str) -> bool:
    return optional_model_path(key).is_file()


def _model(key: str):
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    path = optional_model_path(key)
    if not path.is_file():
        return None
    from ultralytics import YOLO
    loaded = YOLO(str(path))
    with _LOCK:
        _CACHE[key] = loaded
    return loaded


def run_source(
    image_path: str,
    key: str,
    normalizer: Callable[..., dict],
    *,
    conf: float = 0.25,
    iou: float = 0.45,
    imgsz: int = 1280,
) -> tuple[list[dict], list[dict]]:
    model = _model(key)
    if model is None:
        return [], []

    result = model.predict(source=image_path, imgsz=imgsz, conf=conf, iou=iou, verbose=False)[0]
    if result.boxes is None:
        return [], []

    boxes = result.boxes.xyxy.detach().cpu().numpy()
    scores = result.boxes.conf.detach().cpu().numpy()
    classes = result.boxes.cls.detach().cpu().numpy().astype(int)
    names = result.names
    class_count = len(names) if hasattr(names, "__len__") else None
    findings: list[dict] = []
    helpers: list[dict] = []

    for box, score, class_id in zip(boxes, scores, classes):
        raw = str(names.get(int(class_id), class_id) if isinstance(names, dict) else names[int(class_id)])
        try:
            mapped = normalizer(raw, class_count=class_count)
        except TypeError:
            mapped = normalizer(raw)
        base = {
            "confidence": round(float(score), 4),
            "bbox": [round(float(v), 1) for v in box.tolist()],
            "raw_class": raw,
            "motor": key,
        }
        if mapped.get("type") == "finding" and mapped.get("finding_code") in FINDING_CATALOG:
            code = mapped["finding_code"]
            label, category = FINDING_CATALOG[code]
            findings.append({**base, "finding_code": code, "label": label, "category": category})
        elif mapped.get("type") == "helper" and mapped.get("signal"):
            helpers.append({**base, "signal": mapped["signal"]})

    return findings, helpers
