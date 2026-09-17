from __future__ import annotations

import json
import threading
from pathlib import Path


_CACHE: dict[tuple, str] = {}
_LOCK = threading.Lock()
_MAX_CACHE = 32


def _fingerprint(paths: list[str], modality_hint: str = "") -> tuple:
    parts = [("modality_hint", modality_hint.strip().upper())]
    for raw in paths:
        p = Path(raw)
        try:
            stat = p.stat()
            parts.append((str(p.resolve()), stat.st_size, getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))))
        except OSError:
            parts.append((str(p), 0, 0))
    return tuple(parts)


def _slim_result(result: dict) -> dict:
    findings = []
    for item in result.get("findings") or []:
        if not isinstance(item, dict):
            continue
        findings.append(
            {
                "code": item.get("finding_code"),
                "label": item.get("label"),
                "fdi": item.get("fdi"),
                "confidence": item.get("confidence"),
                "measurement": item.get("measurement"),
                "evidence_type": item.get("evidence_type") or "direct",
                "candidate_only": bool(item.get("candidate_only", False)),
            }
        )
    return {
        "engine": result.get("engine"),
        "engine_role": result.get("engine_role"),
        "modality": result.get("modality"),
        "tooth_count": result.get("tooth_count"),
        "unique_fdi_count": result.get("unique_fdi_count"),
        "findings": findings,
    }


def _is_intraoral(modality_hint: str) -> bool:
    hint = (modality_hint or "").upper()
    return any(token in hint for token in ("INTRAORAL", "CLINICAL_PHOTO", "AĞIZ İÇİ", "AGIZ ICI"))


def structured_vision_text(image_paths: list[str] | None, modality_hint: str = "") -> str:
    """Convert dedicated DentalAI motor output to text for the clinical LLM.

    No image bytes are sent to the external clinical LLM. Intraoral photographs
    are routed to OralDetect as the primary image engine. Radiographs continue to
    use the panoramic engine until their own modality-specific routes are added.
    """
    paths = [str(p) for p in (image_paths or []) if p and Path(p).is_file()]
    if not paths:
        return json.dumps({"status": "no_image_motor_context", "findings": []}, ensure_ascii=False)

    intraoral = _is_intraoral(modality_hint)
    mode_key = "INTRAORAL_ORALDETECT" if intraoral else "PANORAMIC_VISION48"
    key = _fingerprint(paths, mode_key)
    with _LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached

    payload = {"status": "ok", "route": mode_key, "images": []}
    try:
        if intraoral:
            from vision_service.intraoral_oraldetect import analyze_intraoral

            # OralDetect is the main/first image motor for intraoral photos. Never
            # fall back to the panoramic motor for this modality.
            for path in paths[:4]:
                result = analyze_intraoral(path)
                payload["images"].append(_slim_result(result))
        else:
            from vision_service.pipeline import analyze_panorama

            for path in paths[:4]:
                result = analyze_panorama(path)
                payload["images"].append(_slim_result(result))
    except Exception as exc:
        payload = {
            "status": "vision_motor_unavailable",
            "route": mode_key,
            "findings": [],
            "error_type": type(exc).__name__,
        }

    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with _LOCK:
        if len(_CACHE) >= _MAX_CACHE:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = text
    return text
