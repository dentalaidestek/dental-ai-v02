from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class PeriapicalPAIError(RuntimeError):
    pass


PERIAPICAL_INFERENCE_URL = os.getenv("PERIAPICAL_INFERENCE_URL", "").strip().rstrip("/")
PERIAPICAL_INFERENCE_API_KEY = os.getenv("PERIAPICAL_INFERENCE_API_KEY", "").strip()
PERIAPICAL_TIMEOUT_SECONDS = float(os.getenv("PERIAPICAL_TIMEOUT_SECONDS", "90"))

PAI_LABELS = {
    1: "Normal periapikal yapı",
    2: "Kemik yapısında küçük değişiklikler",
    3: "Mineral kaybıyla uyumlu periapikal değişiklik",
    4: "İyi tanımlanmış periapikal radyolüsensi",
    5: "Şiddetli apikal periodontitis bulguları",
}


def configured() -> bool:
    return bool(PERIAPICAL_INFERENCE_URL)


def _multipart_body(image_path: str) -> tuple[bytes, str]:
    boundary = "----DentalAIPeriapicalBoundary"
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


def _clamp_score(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _normalize_pai(payload: dict[str, Any]) -> dict[str, Any]:
    raw_pai = payload.get("pai_score", payload.get("pai", payload.get("class")))
    try:
        pai = int(raw_pai)
    except (TypeError, ValueError) as exc:
        raise PeriapicalPAIError("PAI motoru 1-5 arasında geçerli bir skor döndürmedi.") from exc
    if pai not in PAI_LABELS:
        raise PeriapicalPAIError("PAI motoru 1-5 dışında skor döndürdü.")

    confidence = _clamp_score(payload.get("confidence", payload.get("score", 0.0)))
    probabilities = payload.get("probabilities")
    if not isinstance(probabilities, (list, dict)):
        probabilities = None

    return {
        "finding_code": "APICAL_PERIODONTITIS_PAI",
        "label": PAI_LABELS[pai],
        "pai_score": pai,
        "confidence": round(confidence, 4),
        "probabilities": probabilities,
        "source_motor": payload.get("source_motor", "pai_meets_ai_ensemble"),
        "modality": "PERIAPICAL",
        "candidate_only": True,
        "image_level": True,
        "localization_available": False,
    }


def analyze_periapical(image_path: str) -> dict[str, Any]:
    if not configured():
        raise PeriapicalPAIError("Periapikal inference servisi yapılandırılmadı: PERIAPICAL_INFERENCE_URL eksik.")
    path = Path(image_path)
    if not path.is_file():
        raise PeriapicalPAIError("Periapikal görüntü dosyası bulunamadı.")

    body, content_type = _multipart_body(str(path))
    headers = {
        "Content-Type": content_type,
        "Accept": "application/json",
        "User-Agent": "DentalAI-Periapical/1.0",
    }
    if PERIAPICAL_INFERENCE_API_KEY:
        headers["Authorization"] = f"Bearer {PERIAPICAL_INFERENCE_API_KEY}"

    request = urllib.request.Request(
        f"{PERIAPICAL_INFERENCE_URL}/infer-periapical",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=PERIAPICAL_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[-1200:]
        raise PeriapicalPAIError(f"Periapikal inference HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PeriapicalPAIError(f"Periapikal inference erişim/yanıt hatası: {exc}") from exc

    if not isinstance(payload, dict):
        raise PeriapicalPAIError("Periapikal inference geçersiz JSON döndürdü.")

    pai_payload = payload.get("pai", payload)
    if not isinstance(pai_payload, dict):
        raise PeriapicalPAIError("Periapikal inference PAI çıktısı geçersiz.")
    finding = _normalize_pai(pai_payload)

    auxiliary = payload.get("radiographic_findings", [])
    if not isinstance(auxiliary, list):
        auxiliary = []

    return {
        "ok": True,
        "engine": "periapical_pai_v1",
        "engine_role": "primary_apical_assessment",
        "modality": "PERIAPICAL",
        "pai": finding,
        "findings": [finding],
        "auxiliary_radiographic_findings": auxiliary,
        "motors": payload.get("motors", ["pai_meets_ai"]),
        "notes": [
            "PAI modeli apeks merkezli periapikal değerlendirme için kullanılır.",
            "PAI çıktısı lezyon sınırı değildir; lokalizasyon varmış gibi gösterilmez.",
            "Restorasyon/RCT gibi yardımcı radyografik bulgular PAI skoruna sayısal olarak eklenmez.",
        ],
    }
