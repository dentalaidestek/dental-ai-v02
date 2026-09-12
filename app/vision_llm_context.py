from __future__ import annotations

import json
import threading
from pathlib import Path


_CACHE: dict[tuple, str] = {}
_LOCK = threading.Lock()
_MAX_CACHE = 32


def _fingerprint(paths: list[str]) -> tuple:
    parts = []
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
            }
        )
    return {
        "engine": result.get("engine"),
        "modality": result.get("modality"),
        "tooth_count": result.get("tooth_count"),
        "unique_fdi_count": result.get("unique_fdi_count"),
        "findings": findings,
    }


def structured_vision_text(image_paths: list[str] | None) -> str:
    """Convert local DentalAI motor output to text for the LLM.

    No image bytes are returned or sent to an external model. A path is only read
    locally by the dedicated DentalAI panoramic motors.
    """
    paths = [str(p) for p in (image_paths or []) if p and Path(p).is_file()]
    if not paths:
        return json.dumps({"status": "no_image_motor_context", "findings": []}, ensure_ascii=False)

    key = _fingerprint(paths)
    with _LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached

    payload = {"status": "ok", "images": []}
    try:
        from vision_service.pipeline import analyze_panorama

        # The current diagnostic engine is panoramic. Analyze each local image in
        # isolation; the caller decides which uploaded files are appropriate.
        for path in paths[:4]:
            result = analyze_panorama(path)
            payload["images"].append(_slim_result(result))
    except Exception as exc:
        payload = {
            "status": "vision_motor_unavailable",
            "findings": [],
            "error_type": type(exc).__name__,
        }

    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with _LOCK:
        if len(_CACHE) >= _MAX_CACHE:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = text
    return text
