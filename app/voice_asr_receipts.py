"""Encrypted, owner-scoped idempotency receipts for native voice transcription.

Raw audio is never persisted. The receipt stores only an AES-GCM encrypted
transcript/revision for a short recovery window, then a bounded tombstone.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlmodel import Session, select

from app.work_jobs import WorkJob

KIND = "VOICE_ASR_RECEIPT"
RESOURCE_TYPE = "PATIENT"
REQUEST_KEY = re.compile(r"^[A-Za-z0-9_-]{16,96}$")
HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")
RECEIPT_TTL = timedelta(hours=24)
LEASE_SECONDS = 180
MAX_RETRYABLE_ATTEMPTS = 5
TOMBSTONE = '{"v":1,"expired":true}'


class ReceiptKeyUnavailable(RuntimeError):
    pass


class ReceiptConflict(RuntimeError):
    pass


class ReceiptCorrupt(RuntimeError):
    pass


def encryption_key(value: str | None = None) -> bytes:
    """Load the dedicated 32-byte key; never fall back to an unrelated secret."""
    raw = (value if value is not None else os.getenv("VOICE_ASR_RECEIPT_KEY", "")).strip()
    if not re.fullmatch(r"[a-fA-F0-9]{64}", raw):
        raise ReceiptKeyUnavailable(
            "VOICE_ASR_RECEIPT_KEY must be configured as 64 hexadecimal characters."
        )
    return bytes.fromhex(raw)


def receipt_dedupe_key(owner_id: int, patient_id: int, request_key: str) -> str:
    if (not isinstance(owner_id, int) or isinstance(owner_id, bool) or owner_id <= 0 or
            not isinstance(patient_id, int) or isinstance(patient_id, bool) or patient_id <= 0 or
            not isinstance(request_key, str) or not REQUEST_KEY.fullmatch(request_key)):
        raise ValueError("Invalid voice receipt scope or request key.")
    material = "dental-ai:voice-asr:v1:{}:{}:{}".format(owner_id, patient_id, request_key)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def audio_content_digest(mime: str, audio_digest: bytes) -> str:
    if not isinstance(mime, str) or not mime or not isinstance(audio_digest, bytes) or len(audio_digest) != 32:
        raise ValueError("Invalid voice audio digest.")
    return hashlib.sha256(mime.encode("ascii") + b"\0" + audio_digest).hexdigest()


def _stamp(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is not None:
        return current.astimezone(timezone.utc).replace(tzinfo=None)
    return current


def _aad(owner_id: int, patient_id: int, dedupe_key: str, digest: str) -> bytes:
    return "dental-ai:voice-asr:v1:{}:{}:{}:{}".format(
        owner_id, patient_id, dedupe_key, digest
    ).encode("ascii")


def _cipher():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise ReceiptKeyUnavailable("AES-GCM support is unavailable.") from exc
    return AESGCM


def _encrypt_result(key: bytes, owner_id: int, patient_id: int, dedupe_key: str,
                    digest: str, transcript: str, revision: str) -> str:
    if (not isinstance(transcript, str) or not transcript.strip() or len(transcript) > 18000 or
            not isinstance(revision, str) or not HEX_DIGEST.fullmatch(revision)):
        raise ValueError("Invalid voice transcription result.")
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(
        {"v": 1, "transcript": transcript, "revision": revision},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    ciphertext = _cipher()(key).encrypt(
        nonce, plaintext, _aad(owner_id, patient_id, dedupe_key, digest)
    )
    return json.dumps({
        "v": 1,
        "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
        "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
    }, separators=(",", ":"))


def _decrypt_result(key: bytes, owner_id: int, patient_id: int, dedupe_key: str,
                    digest: str, payload_json: str) -> dict:
    try:
        envelope = json.loads(payload_json or "{}")
        if not isinstance(envelope, dict) or envelope.get("v") != 1:
            raise ValueError("invalid envelope")
        nonce = base64.b64decode(envelope["nonce"], altchars=b"-_", validate=True)
        ciphertext = base64.b64decode(envelope["ciphertext"], altchars=b"-_", validate=True)
        if len(nonce) != 12 or not ciphertext:
            raise ValueError("invalid encrypted result")
        plaintext = _cipher()(key).decrypt(
            nonce, ciphertext, _aad(owner_id, patient_id, dedupe_key, digest)
        )
        result = json.loads(plaintext.decode("utf-8"))
        if (not isinstance(result, dict) or result.get("v") != 1 or
                not isinstance(result.get("transcript"), str) or
                not result["transcript"].strip() or len(result["transcript"]) > 18000 or
                not isinstance(result.get("revision"), str) or
                not HEX_DIGEST.fullmatch(result["revision"])):
            raise ValueError("invalid result")
        return {"transcript": result["transcript"], "revision": result["revision"]}
    except Exception as exc:
        raise ReceiptCorrupt("Voice receipt cannot be authenticated.") from exc


def _lock(session: Session, dedupe_key: str) -> None:
    if session.get_bind().dialect.name == "postgresql":
        slot = int.from_bytes(
            hashlib.sha256(("voice-asr-receipt:" + dedupe_key).encode()).digest()[:8],
            "big", signed=True,
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:slot)"), {"slot": slot})


def _claim(row: WorkJob, stamp: datetime) -> str:
    token = secrets.token_hex(32)
    row.status = "PROCESSING"
    row.attempts = int(row.attempts or 0) + 1
    row.lease_token = token
    row.lease_until = stamp + timedelta(seconds=LEASE_SECONDS)
    row.error_code = None
    row.payload_json = "{}"
    row.updated_at = stamp
    return token


def reserve_receipt(session: Session, *, owner_id: int, patient_id: int,
                    request_key: str, digest: str, key: bytes,
                    now: datetime | None = None) -> dict:
    """Atomically replay, reject, or reserve one exact audio segment."""
    if not HEX_DIGEST.fullmatch(digest or ""):
        raise ValueError("Invalid voice audio digest.")
    stamp = _stamp(now)
    dedupe = receipt_dedupe_key(owner_id, patient_id, request_key)
    _lock(session, dedupe)
    row = session.exec(select(WorkJob).where(
        WorkJob.owner_user_id == owner_id,
        WorkJob.resource_id == patient_id,
        WorkJob.resource_type == RESOURCE_TYPE,
        WorkJob.kind == KIND,
        WorkJob.dedupe_key == dedupe,
    )).first()

    if row is None:
        token = secrets.token_hex(32)
        row = WorkJob(
            owner_user_id=owner_id,
            resource_id=patient_id,
            resource_type=RESOURCE_TYPE,
            kind=KIND,
            source_hash=digest,
            dedupe_key=dedupe,
            payload_json="{}",
            status="PROCESSING",
            attempts=1,
            lease_token=token,
            lease_until=stamp + timedelta(seconds=LEASE_SECONDS),
            created_at=stamp,
            updated_at=stamp,
        )
        session.add(row)
        session.flush()
        return {"state": "CLAIMED", "dedupe_key": dedupe, "lease_token": token}

    if row.source_hash != digest:
        raise ReceiptConflict("This voice request key was already used for different audio.")

    created = _stamp(row.created_at)
    if stamp - created >= RECEIPT_TTL:
        row.status = "EXPIRED"
        row.payload_json = TOMBSTONE
        row.lease_token = None
        row.lease_until = None
        row.error_code = "TTL_EXPIRED"
        row.updated_at = stamp
        session.add(row)
        return {"state": "EXPIRED", "dedupe_key": dedupe}

    if row.status == "DONE":
        result = _decrypt_result(key, owner_id, patient_id, dedupe, digest, row.payload_json)
        return {"state": "REPLAY", "dedupe_key": dedupe, **result}

    if row.status == "RETRYABLE":
        if int(row.attempts or 0) >= MAX_RETRYABLE_ATTEMPTS:
            row.status = "FAILED"
            row.payload_json = TOMBSTONE
            row.error_code = "RETRY_LIMIT"
            row.lease_token = None
            row.lease_until = None
            row.updated_at = stamp
            session.add(row)
            return {"state": "UNKNOWN", "dedupe_key": dedupe}
        token = _claim(row, stamp)
        session.add(row)
        return {"state": "CLAIMED", "dedupe_key": dedupe, "lease_token": token}

    if row.status == "PROCESSING":
        lease_until = _stamp(row.lease_until) if row.lease_until else None
        if lease_until and lease_until > stamp:
            return {"state": "PROCESSING", "dedupe_key": dedupe}
        row.status = "FAILED"
        row.payload_json = TOMBSTONE
        row.error_code = "OUTCOME_UNKNOWN"
        row.lease_token = None
        row.lease_until = None
        row.updated_at = stamp
        session.add(row)
        return {"state": "UNKNOWN", "dedupe_key": dedupe}

    if row.status == "EXPIRED":
        return {"state": "EXPIRED", "dedupe_key": dedupe}
    return {"state": "UNKNOWN", "dedupe_key": dedupe}


def complete_receipt(session: Session, *, owner_id: int, patient_id: int,
                     request_key: str, digest: str, lease_token: str,
                     key: bytes, transcript: str, revision: str,
                     now: datetime | None = None) -> bool:
    stamp = _stamp(now)
    dedupe = receipt_dedupe_key(owner_id, patient_id, request_key)
    _lock(session, dedupe)
    row = session.exec(select(WorkJob).where(
        WorkJob.owner_user_id == owner_id,
        WorkJob.resource_id == patient_id,
        WorkJob.resource_type == RESOURCE_TYPE,
        WorkJob.kind == KIND,
        WorkJob.dedupe_key == dedupe,
    ).with_for_update()).first()
    if (not row or row.source_hash != digest or row.status != "PROCESSING" or
            not lease_token or row.lease_token != lease_token or
            not row.lease_until or _stamp(row.lease_until) <= stamp or
            stamp - _stamp(row.created_at) >= RECEIPT_TTL):
        return False
    row.payload_json = _encrypt_result(
        key, owner_id, patient_id, dedupe, digest, transcript, revision
    )
    row.status = "DONE"
    row.lease_token = None
    row.lease_until = None
    row.error_code = None
    row.updated_at = stamp
    session.add(row)
    session.flush()
    return True


def finish_receipt(session: Session, *, owner_id: int, patient_id: int,
                   request_key: str, digest: str, lease_token: str,
                   retryable: bool, now: datetime | None = None) -> bool:
    stamp = _stamp(now)
    dedupe = receipt_dedupe_key(owner_id, patient_id, request_key)
    _lock(session, dedupe)
    row = session.exec(select(WorkJob).where(
        WorkJob.owner_user_id == owner_id,
        WorkJob.resource_id == patient_id,
        WorkJob.resource_type == RESOURCE_TYPE,
        WorkJob.kind == KIND,
        WorkJob.dedupe_key == dedupe,
    ).with_for_update()).first()
    if not row or row.source_hash != digest or row.status != "PROCESSING" or row.lease_token != lease_token:
        return False
    row.status = "RETRYABLE" if retryable else "FAILED"
    row.payload_json = "{}" if retryable else TOMBSTONE
    row.error_code = "NOT_STARTED" if retryable else "OUTCOME_UNKNOWN"
    row.lease_token = None
    row.lease_until = None
    row.updated_at = stamp
    session.add(row)
    session.flush()
    return True


def expire_voice_asr_receipts(session: Session, *, now: datetime | None = None,
                              limit: int = 100) -> dict:
    """Clear encrypted results after 24h and retain only short-lived tombstones."""
    from sqlalchemy import delete, or_

    stamp = _stamp(now)
    cutoff = stamp - RECEIPT_TTL
    completed = session.exec(select(WorkJob).where(
        WorkJob.kind == KIND,
        WorkJob.status == "DONE",
        WorkJob.created_at <= cutoff,
    ).order_by(WorkJob.id).limit(limit)).all()
    for row in completed:
        row.status = "EXPIRED"
        row.payload_json = TOMBSTONE
        row.error_code = "TTL_EXPIRED"
        row.updated_at = stamp
        session.add(row)

    stale = session.exec(select(WorkJob).where(
        WorkJob.kind == KIND,
        WorkJob.status == "PROCESSING",
        or_(WorkJob.lease_until == None, WorkJob.lease_until <= stamp),
    ).order_by(WorkJob.id).limit(limit)).all()
    for row in stale:
        row.status = "FAILED"
        row.payload_json = TOMBSTONE
        row.error_code = "OUTCOME_UNKNOWN"
        row.lease_token = None
        row.lease_until = None
        row.updated_at = stamp
        session.add(row)

    prune_ids = session.exec(select(WorkJob.id).where(
        WorkJob.kind == KIND,
        WorkJob.status.in_(["DONE", "EXPIRED", "FAILED", "RETRYABLE"]),
        WorkJob.updated_at <= stamp - timedelta(days=7),
    ).order_by(WorkJob.id).limit(limit)).all()
    if prune_ids:
        session.exec(delete(WorkJob).where(WorkJob.id.in_(prune_ids)))
    session.flush()
    return {"expired": len(completed), "stale": len(stale), "pruned": len(prune_ids)}
