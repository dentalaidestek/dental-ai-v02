"""Keyed, patient-scoped fingerprints for native clinical-media upload receipts.

The WorkJob source_hash column must not contain an unkeyed fingerprint of a
clinical image. Legacy receipts are upgraded in place without reading or
rewriting the stored image bytes.
"""
from __future__ import annotations

import hmac
import json
import os
import re

KEY_ENV = "PATIENT_MEDIA_RECEIPT_KEY"
FINGERPRINT_VERSION = 1
_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_BATCH_ID = re.compile(r"^[A-Za-z0-9_-]{16,96}$")


class PatientMediaReceiptKeyUnavailable(RuntimeError):
    pass


class PatientMediaReceiptConflict(RuntimeError):
    pass


class PatientMediaReceiptCorrupt(RuntimeError):
    pass


def encryption_key(value: str | None = None) -> bytes:
    """Load a dedicated stable 32-byte key; never fall back to an app secret."""
    raw = (value if value is not None else os.getenv(KEY_ENV, "")).strip()
    if not re.fullmatch(r"[a-fA-F0-9]{64}", raw):
        raise PatientMediaReceiptKeyUnavailable(
            f"{KEY_ENV} must be configured as 64 hexadecimal characters."
        )
    return bytes.fromhex(raw)


def keyed_fingerprint(legacy_digest: str, key: bytes, owner_id: int, patient_id: int) -> str:
    """Domain-separate and scope an existing canonical payload digest."""
    if not isinstance(legacy_digest, str) or not _HEX_DIGEST.fullmatch(legacy_digest):
        raise ValueError("Invalid clinical-media receipt digest.")
    if (not isinstance(key, bytes) or len(key) != 32 or
            not isinstance(owner_id, int) or isinstance(owner_id, bool) or owner_id <= 0 or
            not isinstance(patient_id, int) or isinstance(patient_id, bool) or patient_id <= 0):
        raise ValueError("Invalid clinical-media receipt scope or key.")
    message = f"dental-ai:patient-media:v1:{owner_id}:{patient_id}:{legacy_digest}".encode("ascii")
    return hmac.new(key, message, "sha256").hexdigest()


def _receipt_payload(receipt) -> dict:
    try:
        payload = json.loads(receipt.payload_json or "{}")
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
        patient_id = payload.get("patient_id")
        media_id = payload.get("media_id")
        batch_id = payload.get("batch_id")
        file_bytes = payload.get("file_bytes")
        if (not isinstance(patient_id, int) or isinstance(patient_id, bool) or
                patient_id != int(receipt.resource_id) or
                not isinstance(media_id, int) or isinstance(media_id, bool) or media_id <= 0 or
                not isinstance(batch_id, str) or not _BATCH_ID.fullmatch(batch_id) or
                not isinstance(file_bytes, int) or isinstance(file_bytes, bool) or file_bytes < 1):
            raise ValueError("receipt payload fields are invalid")
        return payload
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PatientMediaReceiptCorrupt("Clinical-media receipt payload is invalid.") from exc


def upgrade_legacy_receipt(
    receipt,
    *,
    digest: str | None,
    legacy_digest: str | None,
    key: bytes,
    owner_id: int,
    patient_id: int,
) -> bool:
    """Verify a replay and upgrade an old unkeyed digest in the same transaction.

    Returns True when the receipt row was upgraded. A status lookup may pass
    digest=None; its authenticated owner/patient/request-key scope still binds
    the row, and the legacy fingerprint can be safely keyed without raw media.
    """
    try:
        if int(receipt.owner_user_id) != owner_id or int(receipt.resource_id) != patient_id:
            raise ValueError("receipt scope mismatch")
    except (TypeError, ValueError, AttributeError) as exc:
        raise PatientMediaReceiptCorrupt("Clinical-media receipt scope is invalid.") from exc

    payload = _receipt_payload(receipt)
    version = payload.get("fingerprint_version")
    if version is None:
        if digest is not None and legacy_digest is None:
            raise PatientMediaReceiptCorrupt("Legacy replay requires its original content fingerprint.")
        old_digest = receipt.source_hash
        if not isinstance(old_digest, str) or not _HEX_DIGEST.fullmatch(old_digest):
            raise PatientMediaReceiptCorrupt("Legacy clinical-media fingerprint is invalid.")
        if legacy_digest is not None and not hmac.compare_digest(old_digest, legacy_digest):
            raise PatientMediaReceiptConflict("This upload key was used for different content.")
        receipt.source_hash = keyed_fingerprint(old_digest, key, owner_id, patient_id)
        payload["fingerprint_version"] = FINGERPRINT_VERSION
        receipt.payload_json = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return True

    if type(version) is not int or version != FINGERPRINT_VERSION:
        raise PatientMediaReceiptCorrupt("Unsupported clinical-media fingerprint version.")
    if not isinstance(receipt.source_hash, str) or not _HEX_DIGEST.fullmatch(receipt.source_hash):
        raise PatientMediaReceiptCorrupt("Keyed clinical-media fingerprint is invalid.")
    if digest is not None and not hmac.compare_digest(receipt.source_hash, digest):
        raise PatientMediaReceiptConflict("This upload key was used for different content.")
    return False
