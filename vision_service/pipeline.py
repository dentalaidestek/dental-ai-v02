from __future__ import annotations

import os
import threading
from typing import Any

from vision_service.engine import VisionError, analyze as analyze_fdi
from vision_service.model_manifest import model_path
from vision_service.motors.catalog import FINDING_CATALOG
from vision_service.motors.findings9 import normalize_class as normalize_findings9
from vision_service.motors.impacted_tooth import normalize_class as normalize_impacted
from vision_service.readiness import readiness_snapshot


_MODEL_CACHE: dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()
CACHE_LIGHT_MODELS = os.getenv("DENTAL_VISION_CACHE_LIGHT_MODELS", "1").strip() == "1"


def _name_for(names, class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    return str(names[class_id])


def _load_yolo(model_key: str):
    if CACHE_LIGHT_MODELS and model_key in _MODEL_CACHE:
        return _MODEL_CACHE[model_key]

    path = model_path(model_key)
    if not path.is_file():
        raise VisionError(f"Model bulunamadı: {path}")

    from ultralytics import YOLO

    model = YOLO(str(path))
    if CACHE_LIGHT_MODELS:
        with _MODEL_LOCK:
            _MODEL_CACHE[model_key] = model
    return model


def _bbox_iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    denom = area_a + area_b - inter
    return inter / denom if denom > 0 else 0.0


def _attach_fdi(finding: dict, teeth: list[dict]) -> None:
    bbox = finding.get("bbox") or []
    if len(bbox) != 4 or not teeth:
        return

    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0
    containing = []
    for tooth in teeth:
        tb = tooth.get("bbox") or []
        if len(tb) != 4:
            continue
        if tb[0] <= cx <= tb[2] and tb[1] <= cy <= tb[3]:
            area = max(1.0, (tb[2] - tb[0]) * (tb[3] - tb[1]))
            containing.append((area, tooth))

    if containing:
        containing.sort(key=lambda item: item[0])
        finding["fdi"] = containing[0][1].get("fdi")
        return

    scored = []
    for tooth in teeth:
        tb = tooth.get("bbox") or []
        if len(tb) == 4:
            scored.append((_bbox_iou(bbox, tb), tooth))
    if scored:
        score, tooth = max(scored, key=lambda item: item[0])
        if score >= 0.05:
            finding["fdi"] = tooth.get("fdi")


def _detector_findings(
    *,
    image_path: str,
    model_key: str,
    conf: float,
    iou: float,
    imgsz: int,
    normalizer,
) -> list[dict]:
    model = _load_yolo(model_key)
    result = model.predict(
        source=image_path,
        imgsz=imgsz,
        conf=conf,
        iou=iou,
        verbose=False,
    )[0]

    if result.boxes is None:
        return []

    boxes = result.boxes.xyxy.detach().cpu().numpy()
    scores = result.boxes.conf.detach().cpu().numpy()
    classes = result.boxes.cls.detach().cpu().numpy().astype(int)
    names = result.names
    class_count = len(names) if hasattr(names, "__len__") else None
    findings = []

    for box, score, class_id in zip(boxes, scores, classes):
        raw_class = _name_for(names, int(class_id))
        try:
            mapped = normalizer(raw_class, class_count=class_count)
        except TypeError:
            mapped = normalizer(raw_class)
        if mapped.get("type") != "finding":
            continue

        code = mapped["finding_code"]
        if code not in FINDING_CATALOG:
            continue
        label, category = FINDING_CATALOG[code]
        findings.append(
            {
                "finding_code": code,
                "label": label,
                "category": category,
                "confidence": round(float(score), 4),
                "bbox": [round(float(v), 1) for v in box.tolist()],
                "raw_class": raw_class,
                "motor": model_key,
            }
        )

    return findings


def _dedupe(findings: list[dict]) -> list[dict]:
    best: dict[tuple, dict] = {}
    for item in findings:
        key = (item.get("finding_code"), str(item.get("fdi") or ""), item.get("motor"))
        current = best.get(key)
        if current is None or float(item.get("confidence") or 0) > float(current.get("confidence") or 0):
            best[key] = item
    return list(best.values())


def analyze_panorama(image_path: str) -> dict:
    """Run only task-specific panoramic motors. No general multimodal AI is called."""
    fdi_result = analyze_fdi(image_path)
    teeth = list(fdi_result.get("teeth") or [])
    findings: list[dict] = []
    warnings: list[dict] = []

    jobs = [
        ("findings9", normalize_findings9, float(os.getenv("DENTAL_FINDINGS9_CONF", "0.35")), 0.45, 1280),
        ("impacted_tooth", normalize_impacted, float(os.getenv("DENTAL_IMPACTED_CONF", "0.40")), 0.45, 1280),
    ]

    for model_key, normalizer, conf, iou, imgsz in jobs:
        try:
            items = _detector_findings(
                image_path=image_path,
                model_key=model_key,
                conf=conf,
                iou=iou,
                imgsz=imgsz,
                normalizer=normalizer,
            )
            for item in items:
                _attach_fdi(item, teeth)
            findings.extend(items)
        except Exception as exc:
            warnings.append(
                {
                    "motor": model_key,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )

    findings = _dedupe(findings)
    findings.sort(
        key=lambda item: (
            str(item.get("fdi") or "99"),
            item.get("finding_code") or "",
            -float(item.get("confidence") or 0),
        )
    )

    return {
        "engine": "dental_ai_panorama_pipeline_v2",
        "modality": "PANORAMIC",
        "tooth_count": fdi_result.get("tooth_count", len(teeth)),
        "unique_fdi_count": fdi_result.get("unique_fdi_count", len({str(t.get('fdi')) for t in teeth})),
        "has_segmentation": bool(fdi_result.get("has_segmentation")),
        "teeth": teeth,
        "finding_count": len(findings),
        "findings": findings,
        "warnings": warnings,
        "readiness": readiness_snapshot(),
    }
