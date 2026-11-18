"""Durable owner-scoped idempotency receipts for native Academic course creation."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class StudyCourseCreateReceipt(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("owner_user_id", "request_key", name="uq_studycoursecreatereceipt_owner_key"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    request_key: str = Field(max_length=80)
    payload_hash: str = Field(max_length=64)
    # Intentionally no FK: receipt must survive course deletion.
    course_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


def course_payload_hash(*, title: str, description: str) -> str:
    payload = {
        "version": 1,
        "title": " ".join((title or "").strip().split()),
        "description": (description or "").strip(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
