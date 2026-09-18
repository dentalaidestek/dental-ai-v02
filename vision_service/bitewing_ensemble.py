from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class BitewingEngineError(RuntimeError):
    pass


BITEWING_ENSEMBLE_URL = os.getenv("BITEWING_ENSEMBLE_URL", "").strip().rstrip("/")
BITEWING_ENSEMBLE_API_KEY = os.getenv("BITEWING_ENSEMBLE_API_KEY", "").strip()
BITEWING_ENSEMBLE_TIMEOUT_SECONDS = float(os.getenv("BITEWING_ENSEMBLE_TIMEOUT_SECONDS", "90"))
BITEWING_INTERNAL_CANDIDATE_THRESHOLD = float(os.getenv("BITEWING_INTERNAL_CANDIDATE_THRESHOLD", "0.02"))
BITEWING_DISPLAY_THRESHOLD = float(os.getenv("BITEWING_DISPLAY_THRESHOLD", "0.50"))

MODEL_8024_LABELS = {
    "caries": ("CARIES", "Çürük şüphesi"),
    "crown": ("CROWN", "Kron restorasyonu"),
    "filling": ("FILLING", "Dolgu/restorasyon"),
    "implant": ("IMPLANT", "İmplant"),
    "missing-tooth-between": ("MISSING_TOOTH", "Eksik diş"),
    "missing tooth between": ("MISSING_TOOTH", "Eksik diş"),
    "periapical-lesion": ("PERIAPICAL_RADIOLUCENCY", "Periapikal lezyon şüphesi"),
    "periapical lesion": ("PERIAPICAL_RADIOLUCENCY", "Periapikal lezyon şüphesi"),
    "root piece": ("RESIDUAL_ROOT", "Kök parçası şüphesi"),
    "root-piece": ("RESIDUAL_ROOT", "Kök parçası şüphesi"),
    "root-canal-treatment": ("ROOT_CANAL_TREATED", "Kanal tedavili diş"),
    "root canal treatment": ("ROOT_CANAL_TREATED", "Kanal tedavili diş"),
}


def configured() -> bool:
    return bool(BITEWING_ENSEMBLE_URL)


def _multipart_body(image_path: str):
    boundary = "----DentalAIBitewingBoundary"
    path = Path(image_path)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        path.read_bytes(), b"\r\n", f"--{boundary}--\r\n".encode(),
    ])
    return body, f"multipart/form-data; boundary={boundary}"


def _label(item: dict[str, Any]) -> str:
    return str(item.get("label") or item.get("class_name") or item.get("class") or item.get("name") or "").strip().casefold()


def _score(item: dict[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(item.get("confidence", item.get("score", 0.0)))))
    except Exception:
        return 0.0


def _bbox(item: dict[str, Any]):
    box = item.get("bbox") or item.get("box")
    if isinstance(box, dict):
        if all(k in box for k in ("x1", "y1", "x2", "y2")):
            box = [box["x1"], box["y1"], box["x2"], box["y2"]]
        elif all(k in box for k in ("x", "y", "w", "h")):
            box = [box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"]]
    try:
        return [float(x) for x in box] if isinstance(box, list) and len(box) == 4 else None
    except Exception:
        return None


def _normalize_8024(item: dict[str, Any]):
    raw = _label(item)
    mapped = MODEL_8024_LABELS.get(raw)
    if not mapped:
        return None
    out = {
        "finding_code": mapped[0],
        "label": mapped[1],
        "raw_label": raw,
        "confidence": round(_score(item), 4),
        "bbox": _bbox(item),
        "source_motor": "yolov8_8024_seg",
        "modality": "BITEWING",
        "candidate_only": True,
    }
    mask = item.get("mask") or item.get("polygon") or item.get("segmentation")
    if mask is not None:
        out["segmentation"] = mask
    return out


def _normalize_periodontal(item: dict[str, Any]):
    # The open periodontal study uses a tooth-localization/segmentation stage and
    # a downstream defect-angle classifier. Preserve that distinction: its output
    # must never be presented as a pixel-precise bone-loss lesion mask.
    score = _score(item)
    category = str(item.get("category") or item.get("label") or item.get("class_name") or "intrabony_defect").strip()
    out = {
        "finding_code": "PERIODONTAL_INTRABONY_DEFECT_CANDIDATE",
        "label": "Periodontal kemik içi defekt şüphesi",
        "raw_label": category,
        "confidence": round(score, 4),
        "source_motor": "bitewing_periodontal_defect",
        "modality": "BITEWING",
        "candidate_only": True,
        "localization_type": "tooth_region_plus_classifier",
        "localization_disclaimer": "Bu çıktı periodontal defekt değerlendirme zincirinden gelir; doğrulanmış lezyon sınırı değildir.",
    }
    box = _bbox(item)
    if box:
        out["bbox"] = box
    for key in ("defect_angle_deg", "angle_deg", "angle_class", "tooth_id", "fdi"):
        if item.get(key) is not None:
            out[key] = item[key]
    return out


def analyze_bitewing(image_path: str):
    if not configured():
        raise BitewingEngineError("Bitewing motor servisi yapılandırılmadı: BITEWING_ENSEMBLE_URL eksik.")
    path = Path(image_path)
    if not path.is_file():
        raise BitewingEngineError("Bitewing görüntü dosyası bulunamadı.")

    body, content_type = _multipart_body(str(path))
    headers = {"Content-Type": content_type, "Accept": "application/json", "User-Agent": "DentalAI-Bitewing/1.0"}
    if BITEWING_ENSEMBLE_API_KEY:
        headers["Authorization"] = f"Bearer {BITEWING_ENSEMBLE_API_KEY}"

    try:
        req = urllib.request.Request(f"{BITEWING_ENSEMBLE_URL}/infer", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=BITEWING_ENSEMBLE_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise BitewingEngineError(f"Bitewing inference HTTP {exc.code}: {exc.read().decode(errors='replace')[-1200:]}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BitewingEngineError(f"Bitewing inference erişim/yanıt hatası: {exc}") from exc

    if not isinstance(payload, dict):
        raise BitewingEngineError("Bitewing inference geçersiz JSON döndürdü.")

    raw_8024 = payload.get("model_8024", payload.get("8024", []))
    raw_periodontal = payload.get("periodontal", [])
    if not isinstance(raw_8024, list) or not isinstance(raw_periodontal, list):
        raise BitewingEngineError("Bitewing motor çıktıları liste olmalı.")

    # Keep weak 8024 evidence for later motor/geometry fusion instead of
    # discarding it at ingestion. This is deliberately separate from the UI
    # threshold: low-score candidates are internal evidence only.
    findings = [
        x for item in raw_8024
        if isinstance(item, dict)
        if (x := _normalize_8024(item))
        if x.get("confidence", 0.0) >= BITEWING_INTERNAL_CANDIDATE_THRESHOLD
    ]
    for x in findings:
        x["candidate_only"] = x.get("confidence", 0.0) < BITEWING_DISPLAY_THRESHOLD
        x["display_eligible"] = x.get("confidence", 0.0) >= BITEWING_DISPLAY_THRESHOLD
    periodontal = [x for item in raw_periodontal if isinstance(item, dict) if (x := _normalize_periodontal(item))]
    findings.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    periodontal.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    return {
        "ok": True,
        "engine": "bitewing_8024_periodontal_v1",
        "engine_role": "primary",
        "modality": "BITEWING",
        "findings": findings,
        "finding_count": len(findings),
        "display_findings": [x for x in findings if x.get("display_eligible")],
        "display_finding_count": sum(1 for x in findings if x.get("display_eligible")),
        "internal_candidate_threshold": BITEWING_INTERNAL_CANDIDATE_THRESHOLD,
        "display_threshold": BITEWING_DISPLAY_THRESHOLD,
        "periodontal_candidates": periodontal,
        "motors": ["yolov8_8024_seg", "bitewing_periodontal_defect"],
        "notes": [
            "8024 motoru dental X-ray için yayımlanmıştır; yalnız bitewing ile eğitildiği belgelenmemiştir.",
            "Periodontal motor çıktısı kemik içi defekt değerlendirme adayıdır; piksel düzeyinde kemik kaybı maskesi gibi sunulmaz.",
            "8024 için 0.02 ve üzeri zayıf adaylar fusion için iç kanıt olarak korunur; tek başına kullanıcıya gösterilmez.",
            "Kullanıcı gösterim eşiği 0.50 olarak ayrı tutulur.",
            "Motor güven skorları birbirine eklenmez.",
        ],
    }
