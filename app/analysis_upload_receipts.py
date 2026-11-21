"""Keyed fingerprints for idempotent native AI-analysis upload receipts.

The digest binds an upload key to the exact image/context payload, but the raw
SHA-256 is never persisted. The dedicated clinical-media receipt key is reused
with a separate HMAC domain from patient-gallery receipts.
"""
from __future__ import annotations

import hmac
import json
import re

from app.patient_media_receipts import encryption_key

_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_VERSION = 1


class AnalysisUploadReceiptConflict(ValueError):
    """An idempotency key was reused for a different analysis payload."""


class AnalysisUploadReceiptCorrupt(ValueError):
    """A stored analysis receipt cannot be safely reconciled."""


def keyed_analysis_upload_fingerprint(
    legacy_digest: str,
    key: bytes,
    owner_id: int,
    patient_id: int,
) -> str:
    """Return a domain-separated HMAC scoped to the authenticated owner/patient."""
    if not isinstance(legacy_digest, str) or not _HEX_DIGEST.fullmatch(legacy_digest):
        raise ValueError("Invalid analysis-upload content digest.")
    if (
        not isinstance(key, bytes)
        or len(key) != 32
        or not isinstance(owner_id, int)
        or isinstance(owner_id, bool)
        or owner_id <= 0
        or not isinstance(patient_id, int)
        or isinstance(patient_id, bool)
        or patient_id <= 0
    ):
        raise ValueError("Invalid analysis-upload receipt scope or key.")
    message = (
        f"dental-ai:analysis-upload:v1:{owner_id}:{patient_id}:{legacy_digest}"
    ).encode("ascii")
    return hmac.new(key, message, "sha256").hexdigest()


def _receipt_payload(receipt) -> dict:
    try:
        payload = json.loads(receipt.payload_json or "{}")
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
        job_id = payload.get("job_id")
        if not isinstance(job_id, int) or isinstance(job_id, bool) or job_id <= 0:
            raise ValueError("job_id is invalid")
        return payload
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AnalysisUploadReceiptCorrupt(
            "Analysis-upload receipt payload is invalid."
        ) from exc


def verify_or_upgrade_analysis_upload_receipt(
    receipt,
    *,
    legacy_digest: str | None,
    key: bytes,
    owner_id: int,
    patient_id: int,
) -> bool:
    """Verify a replay or lazily replace a legacy unkeyed digest in-place.

    A status lookup has no image bytes and passes legacy_digest=None. It may
    still upgrade the stored legacy digest because owner, patient and request
    key have already been authenticated by the caller.
    """
    if (
        getattr(receipt, "kind", None) != "UPLOAD_RECEIPT"
        or getattr(receipt, "resource_type", None) != "ANALYSIS"
        or getattr(receipt, "owner_user_id", None) != owner_id
    ):
        raise AnalysisUploadReceiptCorrupt("Analysis-upload receipt scope is invalid.")

    payload = _receipt_payload(receipt)
    stored = receipt.source_hash
    if not isinstance(stored, str) or not _HEX_DIGEST.fullmatch(stored):
        raise AnalysisUploadReceiptCorrupt(
            "Analysis-upload receipt fingerprint is invalid."
        )

    version = payload.get("fingerprint_version")
    if version is None:
        if legacy_digest is not None:
            if not isinstance(legacy_digest, str) or not _HEX_DIGEST.fullmatch(legacy_digest):
                raise AnalysisUploadReceiptCorrupt(
                    "Incoming analysis-upload fingerprint is invalid."
                )
            if not hmac.compare_digest(stored, legacy_digest):
                raise AnalysisUploadReceiptConflict(
                    "This upload key was used for different content."
                )
        receipt.source_hash = keyed_analysis_upload_fingerprint(
            stored, key, owner_id, patient_id
        )
        payload["fingerprint_version"] = _VERSION
        receipt.payload_json = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return True

    if type(version) is not int or version != _VERSION:
        raise AnalysisUploadReceiptCorrupt(
            "Unsupported analysis-upload fingerprint version."
        )
    if legacy_digest is not None:
        expected = keyed_analysis_upload_fingerprint(
            legacy_digest, key, owner_id, patient_id
        )
        if not hmac.compare_digest(stored, expected):
            raise AnalysisUploadReceiptConflict(
                "This upload key was used for different content."
            )
    return False


__all__ = [
    "AnalysisUploadReceiptConflict",
    "AnalysisUploadReceiptCorrupt",
    "encryption_key",
    "keyed_analysis_upload_fingerprint",
    "verify_or_upgrade_analysis_upload_receipt",
]
