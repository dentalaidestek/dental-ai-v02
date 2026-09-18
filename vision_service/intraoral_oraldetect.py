from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class OralDetectError(RuntimeError):
    pass


ORALDETECT_URL = os.getenv("ORALDETECT_URL", "").strip().rstrip("/")
ORALDETECT_API_KEY = os.getenv("ORALDETECT_API_KEY", "").strip()
ORALDETECT_TIMEOUT_SECONDS = float(os.getenv("ORALDETECT_TIMEOUT_SECONDS", "90"))

# OralDetect is the primary engine for intraoral photographs. These labels are
# intentionally separate from the panoramic Vision48 catalog.
DEFAULT_VOCABULARY = [
    "dental caries",
    "dental plaque",
    "severe gingivitis",
    "periodontal pocket",
    "dental abrasion",
    "tooth erosion",
    "dental filling",
    "dental crown restoration",
    "dental restoration",
    "dental implant",
    "missing teeth",
    "retained root",
    "orthodontic bracket",
    "intraoral appliance",
    # Open-vocabulary soft-tissue queries. These are surfaced only as visual
    # candidates and are never promoted to a definitive histopathologic diagnosis.
    "oral ulcer",
    "oral mucosal lesion",
    "white oral lesion",
    "red oral lesion",
]

LABEL_MAP = {
    "dental caries": ("VISIBLE_CARIES", "Görünür çürük"),
    "dental plaque": ("DENTAL_PLAQUE", "Dental plak"),
    "severe gingivitis": ("SEVERE_GINGIVITIS", "Belirgin gingival inflamasyon"),
    "periodontal pocket": ("PERIODONTAL_POCKET", "Periodontal cep bulgusu"),
    "dental abrasion": ("DENTAL_ABRASION", "Diş abrazyonu"),
    "tooth erosion": ("TOOTH_EROSION", "Diş erozyonu"),
    "dental filling": ("DENTAL_FILLING", "Dolgu/restorasyon"),
    "dental crown restoration": ("CROWN_RESTORATION", "Kron restorasyonu"),
    "dental restoration": ("DENTAL_RESTORATION", "Dental restorasyon"),
    "dental implant": ("DENTAL_IMPLANT", "Dental implant"),
    "missing teeth": ("MISSING_TOOTH", "Eksik diş"),
    "retained root": ("RETAINED_ROOT", "Retansiyonlu/kalan kök"),
    "orthodontic bracket": ("ORTHODONTIC_BRACKET", "Ortodontik braket"),
    "intraoral appliance": ("INTRAORAL_APPLIANCE", "Ağız içi aparey"),
    "oral ulcer": ("ORAL_ULCER_CANDIDATE", "Ülseratif lezyon adayı"),
    "oral mucosal lesion": ("ORAL_MUCOSAL_LESION_CANDIDATE", "Oral mukozal lezyon adayı"),
    "white oral lesion": ("WHITE_ORAL_LESION_CANDIDATE", "Beyaz oral lezyon adayı"),
    "red oral lesion": ("RED_ORAL_LESION_CANDIDATE", "Kırmızı oral lezyon adayı"),
}


def configured() -> bool:
    return bool(ORALDETECT_URL)


def _multipart_body(image_path: str, vocabulary: list[str]) -> tuple[bytes, str]:
    boundary = "----DentalAIOralDetectBoundary"
    path = Path(image_path)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    image_bytes = path.read_bytes()

    parts: list[bytes] = []
    def add_field(name: str, value: str):
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])

    add_field("vocabulary", json.dumps(vocabulary, ensure_ascii=False))
    parts.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        image_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _normalize_detection(item: dict[str, Any]) -> dict[str, Any] | None:
    raw_label = str(
        item.get("label")
        or item.get("class_name")
        or item.get("class")
        or item.get("name")
        or ""
    ).strip().casefold()
    if not raw_label:
        return None

    code, label_tr = LABEL_MAP.get(
        raw_label,
        ("OPEN_VOCABULARY_CANDIDATE", raw_label),
    )
    confidence = item.get("confidence", item.get("score", 0.0))
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.0

    bbox = item.get("bbox") or item.get("box")
    if isinstance(bbox, dict):
        if all(k in bbox for k in ("x1", "y1", "x2", "y2")):
            bbox = [bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]]
        elif all(k in bbox for k in ("x", "y", "w", "h")):
            bbox = [bbox["x"], bbox["y"], bbox["x"] + bbox["w"], bbox["y"] + bbox["h"]]
    if not (isinstance(bbox, list) and len(bbox) == 4):
        bbox = None

    candidate_only = raw_label in {
        "oral ulcer",
        "oral mucosal lesion",
        "white oral lesion",
        "red oral lesion",
    }

    return {
        "finding_code": code,
        "label": label_tr,
        "raw_label": raw_label,
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "bbox": bbox,
        "evidence_type": "oraldetect",
        "candidate_only": candidate_only,
        "modality": "INTRAORAL_PHOTO",
    }


def analyze_intraoral(image_path: str, vocabulary: list[str] | None = None) -> dict[str, Any]:
    if not configured():
        raise OralDetectError(
            "OralDetect ana motoru yapılandırılmadı: ORALDETECT_URL eksik."
        )
    path = Path(image_path)
    if not path.is_file():
        raise OralDetectError("Ağız içi görüntü dosyası bulunamadı.")

    vocab = list(vocabulary or DEFAULT_VOCABULARY)
    body, content_type = _multipart_body(str(path), vocab)
    headers = {
        "Content-Type": content_type,
        "Accept": "application/json",
        "User-Agent": "DentalAI-OralDetect-Bridge/1.0",
    }
    if ORALDETECT_API_KEY:
        headers["Authorization"] = f"Bearer {ORALDETECT_API_KEY}"

    request = urllib.request.Request(
        f"{ORALDETECT_URL}/infer",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=ORALDETECT_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-1200:]
        raise OralDetectError(f"OralDetect HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OralDetectError(f"OralDetect erişim/yanıt hatası: {exc}") from exc

    raw_detections = payload.get("detections") if isinstance(payload, dict) else None
    if not isinstance(raw_detections, list):
        raise OralDetectError("OralDetect yanıtında detections listesi yok.")

    findings = []
    for item in raw_detections:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_detection(item)
        if normalized:
            findings.append(normalized)
    findings.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)

    return {
        "ok": True,
        "engine": "oraldetect",
        "engine_role": "primary",
        "modality": "INTRAORAL_PHOTO",
        "findings": findings,
        "finding_count": len(findings),
        "vocabulary": vocab,
        "source": "OralGPT/OralDetect-Family",
        "notes": [
            "OralDetect ağız içi fotoğraf için ana görsel motordur.",
            "Yumuşak doku open-vocabulary çıktıları yalnız görsel adaydır; kesin histopatolojik tanı değildir.",
        ],
    }
