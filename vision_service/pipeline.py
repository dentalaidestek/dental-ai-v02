from __future__ import annotations

import os
import threading
from typing import Any

from vision_service.cv_signals import bbox_iou
from vision_service.derived48 import derive_findings
from vision_service.engine import VisionError, analyze as analyze_fdi
from vision_service.model_manifest import model_path
from vision_service.model_sources import optional_model_path
from vision_service.motors.catalog import FINDING_CATALOG
from vision_service.motors.findings9 import normalize_class as normalize_findings9
from vision_service.motors.impacted_tooth import normalize_class as normalize_impacted
from vision_service.motors.insmile12 import normalize_class as normalize_insmile12
from vision_service.motors.liodon3 import normalize_class as normalize_liodon3
from vision_service.motors.yolo31 import normalize_class as normalize_yolo31
from vision_service.optional_yolo import run_source
from vision_service.readiness import readiness_snapshot
from vision_service.tvem_client import run_sequential as run_tvem


_MODEL_CACHE: dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()
CACHE_LIGHT_MODELS = os.getenv("DENTAL_VISION_CACHE_LIGHT_MODELS", "1").strip() == "1"
PANORAMIC_INTERNAL_CANDIDATE_THRESHOLD = float(os.getenv("PANORAMIC_INTERNAL_CANDIDATE_THRESHOLD", "0.02"))
PANORAMIC_DISPLAY_THRESHOLD = float(os.getenv("PANORAMIC_DISPLAY_THRESHOLD", "0.50"))
PANORAMIC_FUSION_IOU_THRESHOLD = float(os.getenv("PANORAMIC_FUSION_IOU_THRESHOLD", "0.20"))
PANORAMIC_CONTROL_MIN_CONFIDENCE = float(os.getenv("PANORAMIC_CONTROL_MIN_CONFIDENCE", "0.05"))


def _name_for(names, class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    return str(names[class_id])


def _load_release_yolo(model_key: str):
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


def _detector_outputs(*, image_path: str, model_key: str, conf: float, iou: float, imgsz: int, normalizer):
    model = _load_release_yolo(model_key)
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
        raw_class = _name_for(names, int(class_id))
        try:
            mapped = normalizer(raw_class, class_count=class_count)
        except TypeError:
            mapped = normalizer(raw_class)
        base = {
            "confidence": round(float(score), 4),
            "bbox": [round(float(v), 1) for v in box.tolist()],
            "raw_class": raw_class,
            "motor": model_key,
        }
        if mapped.get("type") == "finding" and mapped.get("finding_code") in FINDING_CATALOG:
            code = mapped["finding_code"]
            label, category = FINDING_CATALOG[code]
            findings.append({**base, "finding_code": code, "label": label, "category": category, "evidence_type": "direct"})
        elif mapped.get("type") in {"helper", "auxiliary"} and mapped.get("signal"):
            helpers.append({**base, "signal": mapped["signal"]})
    return findings, helpers


def _bbox_distance(a, b) -> float:
    if not a or not b or len(a) != 4 or len(b) != 4:
        return float("inf")
    ax1, ay1, ax2, ay2 = map(float, a); bx1, by1, bx2, by2 = map(float, b)
    dx = max(bx1-ax2, ax1-bx2, 0.0); dy = max(by1-ay2, ay1-by2, 0.0)
    return (dx*dx + dy*dy) ** 0.5


def _attach_fdi(item: dict, teeth: list[dict]) -> None:
    bbox = item.get("bbox") or []
    if len(bbox) != 4 or not teeth:
        return
    cx = (bbox[0] + bbox[2]) / 2.0; cy = (bbox[1] + bbox[3]) / 2.0
    containing = []
    for tooth in teeth:
        tb = tooth.get("bbox") or []
        if len(tb) != 4:
            continue
        if tb[0] <= cx <= tb[2] and tb[1] <= cy <= tb[3]:
            area = max(1.0, (tb[2]-tb[0])*(tb[3]-tb[1]))
            containing.append((area, tooth))
    if containing:
        item["fdi"] = min(containing, key=lambda x: x[0])[1].get("fdi")
        return
    scored = []
    for tooth in teeth:
        tb = tooth.get("bbox") or []
        if len(tb) == 4:
            score = bbox_iou(bbox, tb)
            distance = _bbox_distance(bbox, tb)
            scored.append((score, -distance, tooth))
    if scored:
        score, neg_distance, tooth = max(scored, key=lambda x: (x[0], x[1]))
        width = max(1.0, float(tooth["bbox"][2])-float(tooth["bbox"][0]))
        if score >= 0.04 or -neg_distance <= width * 0.45:
            item["fdi"] = tooth.get("fdi")


def _normalize_periapical(raw_class: str, **_) -> dict:
    normalized = str(raw_class or "").strip().casefold().replace("_", " ").replace("-", " ")
    if "periapical" in normalized and ("lesion" in normalized or "radioluc" in normalized):
        return {"type": "finding", "finding_code": "PERIAPICAL_RADIOLUCENCY"}
    return {"type": "unknown", "raw_class": str(raw_class or "")}


def _merge_findings(items: list[dict]) -> list[dict]:
    # Preserve spatially distinct findings while suppressing near-identical duplicate
    # predictions from fallback/control motors.
    ordered = sorted(items, key=lambda x: float(x.get("confidence") or 0.0), reverse=True)
    kept: list[dict] = []
    for item in ordered:
        duplicate = False
        for existing in kept:
            if existing.get("finding_code") != item.get("finding_code"):
                continue
            same_fdi = item.get("fdi") is not None and existing.get("fdi") is not None and str(item.get("fdi")) == str(existing.get("fdi"))
            overlap = bbox_iou(item.get("bbox"), existing.get("bbox")) >= 0.35
            if same_fdi or overlap:
                duplicate = True
                # Keep provenance of a supporting control/fallback motor.
                support = existing.setdefault("supporting_motors", [])
                motor = item.get("motor")
                if motor and motor != existing.get("motor") and motor not in support:
                    support.append(motor)
                break
        if not duplicate:
            kept.append(item)
    kept.sort(key=lambda x: (str(x.get("fdi") or "99"), x.get("finding_code") or "", -float(x.get("confidence") or 0.0)))
    return kept


def _control_supports(primary: dict, controls: list[dict]) -> dict | None:
    """Return same-finding spatial support without changing the primary score."""
    matches = [
        item for item in controls
        if item.get("finding_code") == primary.get("finding_code")
        and float(item.get("confidence") or 0.0) >= PANORAMIC_CONTROL_MIN_CONFIDENCE
        and bbox_iou(primary.get("bbox"), item.get("bbox")) >= PANORAMIC_FUSION_IOU_THRESHOLD
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda item: (
            bbox_iou(primary.get("bbox"), item.get("bbox")),
            float(item.get("confidence") or 0.0),
        ),
    )


def analyze_panorama(image_path: str, *, patient_age: int | None = None) -> dict:
    """Run primary panoramic motors first; use control motors only to rescue weak candidates."""
    fdi_result = analyze_fdi(image_path)
    teeth = list(fdi_result.get("teeth") or [])
    helpers: list[dict] = []
    warnings: list[dict] = []
    execution: list[dict] = []

    # Primary motors keep 0.02+ internal candidates. >=0.50 findings bypass
    # control/fusion. Weak candidates are the only direct findings eligible
    # for corroboration by control motors.
    primary: list[dict] = []
    release_jobs = [
        ("findings9", normalize_findings9, PANORAMIC_INTERNAL_CANDIDATE_THRESHOLD, 0.45, 1280),
        ("impacted_tooth", normalize_impacted, PANORAMIC_INTERNAL_CANDIDATE_THRESHOLD, 0.45, 1280),
    ]
    for model_key, normalizer, conf, iou, imgsz in release_jobs:
        try:
            f, h = _detector_outputs(
                image_path=image_path, model_key=model_key, conf=conf,
                iou=iou, imgsz=imgsz, normalizer=normalizer,
            )
            primary.extend(f); helpers.extend(h)
            execution.append({"motor": model_key, "role": "primary", "status": "ok", "findings": len(f), "helpers": len(h)})
        except Exception as exc:
            warnings.append({"motor": model_key, "error_type": type(exc).__name__, "message": str(exc)})
            execution.append({"motor": model_key, "role": "primary", "status": "error"})

    strong = [x for x in primary if float(x.get("confidence") or 0.0) >= PANORAMIC_DISPLAY_THRESHOLD]
    weak = [
        x for x in primary
        if PANORAMIC_INTERNAL_CANDIDATE_THRESHOLD <= float(x.get("confidence") or 0.0) < PANORAMIC_DISPLAY_THRESHOLD
    ]
    weak_codes = {x.get("finding_code") for x in weak}
    controls: list[dict] = []

    # yolo31 and InsMile also provide helper signals consumed by derived48, so
    # they may run for helper extraction. Their DIRECT findings never enter the
    # final result by themselves; they can only corroborate weak primary items.
    helper_control_jobs = [
        ("yolo31", normalize_yolo31, float(os.getenv("DENTAL_YOLO31_CONF", "0.02")), 0.45, 1280),
        ("insmile12", normalize_insmile12, float(os.getenv("DENTAL_INSMILE12_CONF", "0.02")), 0.45, 640),
    ]
    for key, normalizer, conf, iou, imgsz in helper_control_jobs:
        if not optional_model_path(key).is_file():
            execution.append({"motor": key, "role": "helper+weak_control", "status": "not_downloaded"})
            continue
        try:
            f, h = run_source(image_path, key, normalizer, conf=conf, iou=iou, imgsz=imgsz)
            controls.extend(f); helpers.extend(h)
            execution.append({"motor": key, "role": "helper+weak_control", "status": "ok", "findings": len(f), "helpers": len(h)})
        except Exception as exc:
            warnings.append({"motor": key, "error_type": type(exc).__name__, "message": str(exc)})
            execution.append({"motor": key, "role": "helper+weak_control", "status": "error"})

    # Pure direct control motors run only when a weak primary code exists that
    # they can actually corroborate.
    targeted_jobs = [
        ("liodon3", normalize_liodon3, {"CARIES", "PERIAPICAL_RADIOLUCENCY", "IMPACTED_TOOTH"}, float(os.getenv("DENTAL_LIODON3_CONF", "0.02")), 0.35, 640),
        ("panoreader_periapical", _normalize_periapical, {"PERIAPICAL_RADIOLUCENCY"}, float(os.getenv("DENTAL_PERIAPICAL_CONF", "0.02")), 0.45, 1280),
    ]
    for key, normalizer, supported, conf, iou, imgsz in targeted_jobs:
        if not (weak_codes & supported):
            execution.append({"motor": key, "role": "weak_control", "status": "skipped_no_matching_weak_candidate"})
            continue
        if not optional_model_path(key).is_file():
            execution.append({"motor": key, "role": "weak_control", "status": "not_downloaded"})
            continue
        try:
            f, h = run_source(image_path, key, normalizer, conf=conf, iou=iou, imgsz=imgsz)
            controls.extend(f); helpers.extend(h)
            execution.append({"motor": key, "role": "weak_control", "status": "ok", "findings": len(f), "helpers": len(h)})
        except Exception as exc:
            warnings.append({"motor": key, "error_type": type(exc).__name__, "message": str(exc)})
            execution.append({"motor": key, "role": "weak_control", "status": "error"})

    # TVEM still supplies anatomy/bone helper signals needed by derived48.
    # Its disease detections are control evidence only and cannot create a
    # final direct finding without a weak primary candidate at the same site.
    try:
        tvem_findings, tvem_helpers, tvem_warnings = run_tvem(image_path)
        controls.extend(tvem_findings); helpers.extend(tvem_helpers); warnings.extend(tvem_warnings)
        execution.append({"motor": "tvem", "role": "helper+weak_control", "status": "ok" if not tvem_warnings else "partial", "findings": len(tvem_findings), "helpers": len(tvem_helpers)})
    except Exception as exc:
        warnings.append({"motor": "tvem", "error_type": type(exc).__name__, "message": str(exc)})
        execution.append({"motor": "tvem", "role": "helper+weak_control", "status": "error"})

    for item in primary + controls + helpers:
        _attach_fdi(item, teeth)

    rescued: list[dict] = []
    for item in weak:
        support = _control_supports(item, controls)
        if support is None:
            continue
        rescued.append({
            **item,
            "candidate_only": False,
            "display_eligible": True,
            "fusion_supported": True,
            "support_motor": support.get("motor"),
            "support_confidence": support.get("confidence"),
            "support_iou": round(bbox_iou(item.get("bbox"), support.get("bbox")), 4),
        })

    for item in strong:
        item["candidate_only"] = False
        item["display_eligible"] = True
        item["fusion_supported"] = False

    # Derived motors consume only released direct evidence (strong + rescued).
    # Unsupported weak/control pathology detections are deliberately excluded so
    # they cannot be promoted indirectly into a user-visible derived finding.
    evidence_findings = strong + rescued
    derived = derive_findings(image_path, teeth, evidence_findings, helpers, patient_age=patient_age)
    final_findings = _merge_findings(strong + rescued + derived)

    return {
        "engine": "dental_ai_panorama_48_v1",
        "modality": "PANORAMIC",
        "tooth_count": fdi_result.get("tooth_count", len(teeth)),
        "unique_fdi_count": fdi_result.get("unique_fdi_count", len({str(t.get('fdi')) for t in teeth})),
        "has_segmentation": bool(fdi_result.get("has_segmentation")),
        "teeth": teeth,
        "finding_count": len(final_findings),
        "findings": final_findings,
        "internal_candidate_threshold": PANORAMIC_INTERNAL_CANDIDATE_THRESHOLD,
        "display_threshold": PANORAMIC_DISPLAY_THRESHOLD,
        "control_min_confidence": PANORAMIC_CONTROL_MIN_CONFIDENCE,
        "fusion_iou_threshold": PANORAMIC_FUSION_IOU_THRESHOLD,
        "weak_candidate_count": len(weak),
        "rescued_weak_candidate_count": len(rescued),
        "helper_signal_count": len(helpers),
        "helpers": helpers,
        "motor_execution": execution,
        "warnings": warnings,
        "readiness": readiness_snapshot(),
        "fusion_policy": "Strong primary findings bypass controls; only weak primary candidates may be rescued by same-code spatial support with control confidence >=0.05 and IoU >=0.20. Confidence scores are never added or averaged.",
    }
