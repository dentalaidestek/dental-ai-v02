from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from vision_service.motors.catalog import FINDING_CATALOG
from vision_service.motors.tvem import normalize_tvem11, normalize_tvem_anatomy, normalize_tvem_bone_loss


TVEM_URL = os.getenv("TVEM_URL", "").rstrip("/")
TVEM_TIMEOUT = int(os.getenv("TVEM_TIMEOUT_SECONDS", "180"))


def enabled() -> bool:
    return bool(TVEM_URL)


def _post_no_body(path: str) -> dict:
    req = urllib.request.Request(f"{TVEM_URL}{path}", data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=TVEM_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _multipart(image_path: str, confidence: float) -> tuple[bytes, str]:
    boundary = "----DentalAI" + uuid.uuid4().hex
    mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    name = Path(image_path).name
    content = Path(image_path).read_bytes()
    chunks = []

    def add(value: bytes):
        chunks.append(value)

    add(f"--{boundary}\r\n".encode())
    add(f'Content-Disposition: form-data; name="confidence"\r\n\r\n{confidence}\r\n'.encode())
    add(f"--{boundary}\r\n".encode())
    add(f'Content-Disposition: form-data; name="return_vis"\r\n\r\nfalse\r\n'.encode())
    add(f"--{boundary}\r\n".encode())
    add(f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'.encode())
    add(f"Content-Type: {mime}\r\n\r\n".encode())
    add(content)
    add(b"\r\n")
    add(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def _detect(model_name: str, image_path: str, confidence: float) -> dict:
    body, boundary = _multipart(image_path, confidence)
    req = urllib.request.Request(
        f"{TVEM_URL}/detect/{model_name}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TVEM_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_sequential(image_path: str) -> tuple[list[dict], list[dict], list[dict]]:
    if not enabled():
        return [], [], []

    findings: list[dict] = []
    helpers: list[dict] = []
    warnings: list[dict] = []
    jobs = [
        ("11diseases", normalize_tvem11, float(os.getenv("TVEM_11_CONF", "0.30"))),
        ("bone_loss", normalize_tvem_bone_loss, float(os.getenv("TVEM_BONE_CONF", "0.30"))),
        ("mandibular_maxillary", normalize_tvem_anatomy, float(os.getenv("TVEM_ANATOMY_CONF", "0.30"))),
    ]

    for model_name, normalizer, threshold in jobs:
        try:
            _post_no_body(f"/load/{model_name}")
            result = _detect(model_name, image_path, threshold)
            for item in result.get("detections") or []:
                raw = item.get("class_name") or f"class_{item.get('class_id')}"
                mapped = normalizer(str(raw))
                base = {
                    "confidence": float(item.get("confidence") or 0.0),
                    "bbox": [float(v) for v in (item.get("bbox") or [])],
                    "mask_contour": item.get("mask_contour"),
                    "raw_class": str(raw),
                    "motor": f"tvem:{model_name}",
                }
                if mapped.get("type") == "finding" and mapped.get("finding_code") in FINDING_CATALOG:
                    code = mapped["finding_code"]
                    label, category = FINDING_CATALOG[code]
                    findings.append({**base, "finding_code": code, "label": label, "category": category})
                elif mapped.get("type") == "helper" and mapped.get("signal"):
                    helpers.append({**base, "signal": mapped["signal"]})
        except Exception as exc:
            warnings.append({"motor": f"tvem:{model_name}", "error_type": type(exc).__name__, "message": str(exc)})
        finally:
            try:
                _post_no_body(f"/unload/{model_name}")
            except Exception:
                pass

    return findings, helpers, warnings
