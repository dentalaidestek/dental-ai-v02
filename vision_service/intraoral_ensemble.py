from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class IntraoralEnsembleError(RuntimeError):
    pass


INTRAORAL_ENSEMBLE_URL = os.getenv("INTRAORAL_ENSEMBLE_URL", "").strip().rstrip("/")
INTRAORAL_ENSEMBLE_API_KEY = os.getenv("INTRAORAL_ENSEMBLE_API_KEY", "").strip()
INTRAORAL_ENSEMBLE_TIMEOUT_SECONDS = float(os.getenv("INTRAORAL_ENSEMBLE_TIMEOUT_SECONDS", "90"))

# AlphaDent 9-class/960px is the general intraoral detector.
# Daath is used only as a caries specialist. Raw model labels never reach UI.
ALPHADENT_LABELS = {
    "abrasion": ("DENTAL_ABRASION", "Diş abrazyonu"),
    "filling": ("DENTAL_FILLING", "Dolgu/restorasyon"),
    "crown": ("CROWN_RESTORATION", "Kron restorasyonu"),
    "caries 1 class": ("VISIBLE_CARIES", "Çürük şüphesi"),
    "caries 2 class": ("VISIBLE_CARIES", "Çürük şüphesi"),
    "caries 3 class": ("VISIBLE_CARIES", "Çürük şüphesi"),
    "caries 4 class": ("VISIBLE_CARIES", "Çürük şüphesi"),
    "caries 5 class": ("VISIBLE_CARIES", "Çürük şüphesi"),
    "caries 6 class": ("VISIBLE_CARIES", "Çürük şüphesi"),
}
DAATH_CARIES_LABELS = {"d", "caries", "cavity", "decay", "dental caries"}


def configured() -> bool:
    return bool(INTRAORAL_ENSEMBLE_URL)


def _multipart_body(image_path: str) -> tuple[bytes, str]:
    boundary = "----DentalAIIntraoralEnsembleBoundary"
    path = Path(image_path)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        path.read_bytes(), b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return body, f"multipart/form-data; boundary={boundary}"


def _bbox(item: dict[str, Any]) -> list[float] | None:
    box = item.get("bbox") or item.get("box")
    if isinstance(box, dict):
        if all(k in box for k in ("x1", "y1", "x2", "y2")):
            box = [box["x1"], box["y1"], box["x2"], box["y2"]]
        elif all(k in box for k in ("x", "y", "w", "h")):
            box = [box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"]]
    if not (isinstance(box, list) and len(box) == 4):
        return None
    try:
        return [float(x) for x in box]
    except Exception:
        return None


def _score(item: dict[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(item.get("confidence", item.get("score", 0.0)))))
    except Exception:
        return 0.0


def _iou(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    aa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    bb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = aa + bb - inter
    return inter / union if union > 0 else 0.0


def _raw_label(item: dict[str, Any]) -> str:
    return str(item.get("label") or item.get("class_name") or item.get("class") or item.get("name") or "").strip().casefold()


def _normalize_alpha(item: dict[str, Any]) -> dict[str, Any] | None:
    raw = _raw_label(item)
    mapped = ALPHADENT_LABELS.get(raw)
    if not mapped:
        return None
    code, label = mapped
    return {"finding_code": code, "label": label, "raw_label": raw, "confidence": round(_score(item), 4), "bbox": _bbox(item), "source_motor": "alphadent_9class_960", "candidate_only": False, "modality": "INTRAORAL_PHOTO"}


def _normalize_daath(item: dict[str, Any]) -> dict[str, Any] | None:
    raw = _raw_label(item)
    if raw not in DAATH_CARIES_LABELS:
        return None
    return {"finding_code": "VISIBLE_CARIES", "label": "Çürük şüphesi", "raw_label": raw, "confidence": round(_score(item), 4), "bbox": _bbox(item), "source_motor": "daath_caries", "candidate_only": True, "modality": "INTRAORAL_PHOTO"}


def _merge_caries(alpha: list[dict[str, Any]], daath: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alpha_caries = [x for x in alpha if x["finding_code"] == "VISIBLE_CARIES"]
    other = [x for x in alpha if x["finding_code"] != "VISIBLE_CARIES"]
    used_daath: set[int] = set()
    merged: list[dict[str, Any]] = []

    for a in alpha_caries:
        best_i, best_iou = None, 0.0
        for i, d in enumerate(daath):
            if i in used_daath:
                continue
            overlap = _iou(a.get("bbox"), d.get("bbox"))
            if overlap > best_iou:
                best_i, best_iou = i, overlap
        if best_i is not None and best_iou >= 0.20:
            d = daath[best_i]
            used_daath.add(best_i)
            # Agreement raises confidence without pretending to be a calibrated probability.
            score = min(0.99, max(a["confidence"], d["confidence"]) + 0.08)
            merged.append({**a, "confidence": round(score, 4), "candidate_only": False, "source_motor": "alphadent+daath", "agreement": True, "agreement_iou": round(best_iou, 4)})
        else:
            # AlphaDent is the general detector. Keep its caries candidates at >=0.50.
            if a["confidence"] >= 0.50:
                merged.append(a)

    # Daath-only detections are specialist candidates; suppress weak/likely noisy calls.
    for i, d in enumerate(daath):
        if i not in used_daath and d["confidence"] >= 0.70:
            merged.append(d)

    findings = other + merged
    findings.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
    return findings


def analyze_intraoral_ensemble(image_path: str) -> dict[str, Any]:
    if not configured():
        raise IntraoralEnsembleError("AlphaDent/Daath intraoral motor servisi yapılandırılmadı: INTRAORAL_ENSEMBLE_URL eksik.")
    path = Path(image_path)
    if not path.is_file():
        raise IntraoralEnsembleError("Ağız içi görüntü dosyası bulunamadı.")
    body, content_type = _multipart_body(str(path))
    headers = {"Content-Type": content_type, "Accept": "application/json", "User-Agent": "DentalAI-Intraoral-Ensemble/1.0"}
    if INTRAORAL_ENSEMBLE_API_KEY:
        headers["Authorization"] = f"Bearer {INTRAORAL_ENSEMBLE_API_KEY}"
    req = urllib.request.Request(f"{INTRAORAL_ENSEMBLE_URL}/infer", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=INTRAORAL_ENSEMBLE_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-1200:]
        raise IntraoralEnsembleError(f"Intraoral ensemble HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise IntraoralEnsembleError(f"Intraoral ensemble erişim/yanıt hatası: {exc}") from exc

    if not isinstance(payload, dict):
        raise IntraoralEnsembleError("Intraoral ensemble geçersiz JSON döndürdü.")
    alpha_raw = payload.get("alphadent", [])
    daath_raw = payload.get("daath", [])
    if not isinstance(alpha_raw, list) or not isinstance(daath_raw, list):
        raise IntraoralEnsembleError("Yanıtta alphadent ve daath listeleri gerekli.")
    alpha = [x for item in alpha_raw if isinstance(item, dict) if (x := _normalize_alpha(item))]
    daath = [x for item in daath_raw if isinstance(item, dict) if (x := _normalize_daath(item))]
    findings = _merge_caries(alpha, daath)
    return {"ok": True, "engine": "intraoral_ensemble_v1", "engine_role": "primary", "modality": "INTRAORAL_PHOTO", "findings": findings, "finding_count": len(findings), "motors": ["alphadent_9class_960", "daath_caries"], "notes": ["AlphaDent genel ağız içi aday üreticisidir; Daath çürük uzman motorudur.", "Ham Caries 1-6 ve d etiketleri kullanıcı arayüzüne aktarılmaz.", "Tek motor çıktıları klinik kesin tanı değildir."]}
