"""Additive consultation request receipts; retain hashes rather than clinical text."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class ConsultationRequestReceipt(SQLModel, table=True):
    __table_args__ = (
        Index(
            "uq_consultationrequestreceipt_key", "requester_user_id", "expert_user_id",
            "request_key", unique=True,
        ),
        Index(
            "ix_consultationrequestreceipt_legacy_payload", "requester_user_id",
            "expert_user_id", "payload_hash", "created_at",
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    requester_user_id: int = Field(foreign_key="user.id", ondelete="CASCADE")
    expert_user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    request_key: str = Field(max_length=36)
    payload_hash: str = Field(max_length=64)
    # The baseline case model deliberately has no account foreign keys. Keep this
    # extension independent from baseline table creation/migration order too.
    case_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


def normalize_request_key(value: str) -> str:
    if len(value) > 64:
        raise ValueError("Invalid request key")
    return str(UUID(value.strip()))


def request_payload_hash(*, clinical_summary: str, requester_opinion: str, question: str,
                         tooth_region: str, patient_id: Optional[int], media_ids: list[int],
                         urgency: str) -> str:
    payload = {
        "v": 1,
        "clinical_summary": clinical_summary.strip(),
        "requester_opinion": requester_opinion.strip(),
        "question": question.strip(),
        "tooth_region": tooth_region.strip(),
        "patient_id": patient_id,
        "media_ids": sorted(set(media_ids)),
        "urgency": urgency,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def consultation_expert_is_verified(expert, profile) -> bool:
    return bool(
        expert and expert.is_active and expert.role in {"DOCTOR", "ADMIN"}
        and profile and profile.application_status == "APPROVED"
        and profile.verification_status == "VERIFIED" and profile.specialty_verified
        and profile.credential_document_path and profile.phone
    )


def consultation_capacity_limit(profile) -> int:
    return max(1, min(int(profile.max_active_cases or 5), 5))
