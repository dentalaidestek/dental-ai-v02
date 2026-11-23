"""Durable owner/course-scoped receipts for native Academic material uploads.

The receipt stores only a content digest and the resulting material id. It deliberately
has no foreign key to StudyMaterial so deletion leaves a tombstone and an uncertain
client cannot silently recreate the same upload under the same request key.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class StudyMaterialUploadReceipt(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "course_id",
            "request_key",
            name="uq_studymaterialuploadreceipt_owner_course_key",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    course_id: int = Field(index=True)
    request_key: str = Field(max_length=80)
    payload_hash: str = Field(max_length=64)
    content_sha256: str = Field(max_length=64)
    # Intentionally no FK: a deleted material keeps a durable 410 tombstone.
    material_id: int = Field(index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )


def material_upload_payload_hash(
    *,
    owner_user_id: int,
    course_id: int,
    filename: str,
    mime_type: str,
    size_bytes: int,
    content_sha256: str,
) -> str:
    payload = {
        "version": 1,
        "owner_user_id": int(owner_user_id),
        "course_id": int(course_id),
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": int(size_bytes),
        "content_sha256": content_sha256,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def public_material_upload_receipt(receipt: StudyMaterialUploadReceipt, material: Any) -> dict:
    """Return a minimal receipt; never expose storage paths or provider identifiers."""
    return {
        "course_id": receipt.course_id,
        "request_key": receipt.request_key,
        "material_id": receipt.material_id,
        "name": material.display_name or material.original_filename,
        "mime": material.mime_type,
        "size": material.size_bytes,
        "content_sha256": receipt.content_sha256,
        "payload_hash": receipt.payload_hash,
        "created_at": receipt.created_at.isoformat(),
    }
