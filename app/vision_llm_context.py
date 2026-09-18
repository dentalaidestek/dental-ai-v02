from __future__ import annotations

import json
import threading
import mimetypes
import urllib.error
import urllib.request
import uuid
from pathlib import Path


_CACHE: dict[tuple, dict] = {}
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


def _slim_result(result: dict, *, source_image_id: str | None = None) -> dict:
    def slim_items(items):
        out = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            out.append({
                "finding_code": item.get("finding_code") or item.get("code"),
                "label": item.get("label") or item.get("finding"),
                "tooth_fdi": item.get("tooth_fdi", item.get("fdi", item.get("tooth"))),
                "surface": item.get("surface"),
                "confidence": item.get("confidence", item.get("score")),
                "measurement": item.get("measurement"),
                "evidence_type": item.get("evidence_type") or "direct",
                "candidate_only": bool(item.get("candidate_only", False)),
                "localization_type": item.get("localization_type"),
                "bbox": item.get("bbox"),
                "source_motor": item.get("source_motor"),
                "captured_at": item.get("captured_at"),
                "review_state": item.get("review_state") or "unreviewed",
            })
        return out

    return {
        "ok": result.get("ok", True),
        "engine": result.get("engine"),
        "engine_role": result.get("engine_role"),
        "modality": result.get("modality"),
        "source_image_id": result.get("source_image_id") or source_image_id,
        "tooth_count": result.get("tooth_count"),
        "unique_fdi_count": result.get("unique_fdi_count"),
        "findings": slim_items(result.get("findings")),
        "auxiliary_radiographic_findings": slim_items(result.get("auxiliary_radiographic_findings")),
        "image_level_findings": slim_items(result.get("image_level_findings")),
    }


def _route(modality_hint: str) -> str:
    hint = (modality_hint or "").upper()
    if any(token in hint for token in ("PERIAPICAL", "PERİAPİKAL", "PERIAPİKAL", "PAI")):
        return "PERIAPICAL"
    if "BITEWING" in hint:
        return "BITEWING"
    if any(token in hint for token in ("INTRAORAL", "CLINICAL_PHOTO", "AĞIZ İÇİ", "AGIZ ICI")):
        return "INTRAORAL_PHOTO"
    return "PANORAMIC"


def _modal_infer(path: str, modality: str) -> dict:
    base = __import__("os").getenv("DENTAL_VISION_MODAL_URL", "https://dentalaidestek--dental-ai-inference-api.modal.run").strip().rstrip("/")
    if not base:
        raise RuntimeError("DENTAL_VISION_MODAL_URL yapılandırılmadı.")
    boundary = "----DentalAI" + uuid.uuid4().hex
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    data = Path(path).read_bytes()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{Path(path).name}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{base}/infer?modality={modality}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=float(__import__("os").getenv("DENTAL_VISION_MODAL_TIMEOUT_SECONDS", "120"))) as response:
        return json.loads(response.read().decode("utf-8"))


def _modal_panorama_result(path: str) -> dict:
    from vision_service.cv_signals import bbox_iou
    from vision_service.motors.findings9 import normalize_class as norm9
    from vision_service.motors.impacted_tooth import normalize_class as norm4
    from vision_service.motors.catalog import FINDING_CATALOG

    raw = _modal_infer(path, "panoramic")
    def score(x): return float(x.get("confidence", x.get("score", 0.0)) or 0.0)
    def box(x): return x.get("bbox") or x.get("box")
    def mapped(items, normalizer, motor):
        out=[]
        for item in items or []:
            m=normalizer(str(item.get("label", item.get("class_name", item.get("name","")))))
            code=m.get("finding_code")
            if m.get("type")=="finding" and code in FINDING_CATALOG:
                label, category=FINDING_CATALOG[code]
                out.append({"finding_code":code,"label":label,"category":category,"confidence":round(score(item),4),"bbox":box(item),"motor":motor,"source_motor":motor,"evidence_type":"direct"})
        return out
    primary = mapped(raw.get("findings9"), norm9, "findings9") + mapped(raw.get("oralguard4") or raw.get("impacted"), norm4, "oralguard4")
    strong=[x for x in primary if score(x)>=0.50]
    weak=[x for x in primary if 0.02<=score(x)<0.50]
    rescued=[]
    for item in weak:
        matches=[x for x in primary if x.get("motor")!=item.get("motor") and x.get("finding_code")==item.get("finding_code") and score(x)>=0.05 and bbox_iou(box(item),box(x))>=0.20]
        if matches:
            support=max(matches,key=lambda x:(bbox_iou(box(item),box(x)),score(x)))
            rescued.append({**item,"candidate_only":False,"display_eligible":True,"fusion_supported":True,"support_motor":support.get("motor"),"support_confidence":support.get("confidence"),"support_iou":round(bbox_iou(box(item),box(support)),4)})
    for item in strong:
        item.update({"candidate_only":False,"display_eligible":True,"fusion_supported":False})
    return {"ok":True,"engine":"dental_ai_panorama_modal_v1","modality":"PANORAMIC","findings":strong+rescued,"tooth_count":len(raw.get("fdi") or []),"teeth":raw.get("fdi") or [],"warnings":[]}


def structured_vision_payload(image_paths: list[str] | None, modality_hint: str = "", image_types: list[str] | None = None) -> dict:
    """Run each image through its own dedicated motor family."""
    pairs = [(str(p), (image_types[i] if image_types and i < len(image_types) else modality_hint)) for i, p in enumerate(image_paths or []) if p]
    paths = [p for p, _ in pairs]
    if not paths:
        return {"status": "no_image_motor_context", "route": "NONE", "images": []}

    routes = [_route(hint) for _, hint in pairs]
    route = routes[0] if len(set(routes)) == 1 else "MIXED"
    key = _fingerprint(paths, "|".join(routes))
    with _LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached

    payload = {"status": "ok", "route": route, "images": [], "partial_failures": []}
    for index, (path, hint) in enumerate(pairs[:4]):
        asset_route = _route(hint)
        source_id = f"{asset_route.lower()}:{index + 1}:{Path(path).name}"
        try:
            if asset_route == "INTRAORAL_PHOTO":
                from vision_service.intraoral_ensemble import analyze_intraoral_ensemble, configured as ensemble_configured
                from vision_service.intraoral_oraldetect import analyze_intraoral, configured as oraldetect_configured
                if ensemble_configured():
                    result = analyze_intraoral_ensemble(path)
                elif oraldetect_configured():
                    result = analyze_intraoral(path)
                    result["engine_role"] = "fallback"
                else:
                    raise RuntimeError("Ağız içi motor ailesi yapılandırılmadı.")
            elif asset_route == "PERIAPICAL":
                from vision_service.periapical_pai import analyze_periapical
                result = analyze_periapical(path)
            elif asset_route == "BITEWING":
                from vision_service.bitewing_ensemble import analyze_bitewing
                result = analyze_bitewing(path)
            else:
                result = _modal_panorama_result(path)

            result = dict(result or {})
            result.setdefault("modality", asset_route)
            payload["images"].append(_slim_result(result, source_image_id=source_id))
        except Exception as exc:
            failure = {
                "ok": False,
                "source_image_id": source_id,
                "modality": asset_route,
                "status": "unavailable",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:1200],
                "findings": [],
                "auxiliary_radiographic_findings": [],
                "image_level_findings": [],
            }
            payload["images"].append(failure)
            payload["partial_failures"].append({
                "source_image_id": source_id,
                "modality": asset_route,
                "status": "unavailable",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:1200],
            })

    successful = [x for x in payload["images"] if x.get("ok", True)]
    if not successful:
        payload["status"] = "vision_motor_unavailable"
    elif payload["partial_failures"]:
        payload["status"] = "partial"

    with _LOCK:
        if len(_CACHE) >= _MAX_CACHE:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = payload
    return payload


def structured_vision_text(image_paths: list[str] | None, modality_hint: str = "") -> str:
    """Serialize dedicated motor output for the external clinical LLM; no pixels leave DentalAI."""
    payload = structured_vision_payload(image_paths, modality_hint=modality_hint)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
