"""Durable, clinician-approved anamnesis values with immutable analysis provenance.

Rows are append-only: a new approval adds a new row for the same patient/field.
The latest row is the current approved statement; earlier values remain auditable.
"""
from datetime import datetime

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


HISTORY_LABELS = {
    "family_history": "Aile sağlık öyküsü",
    "materials": "Konuşulan materyaller",
    "dental_history": "Önceki diş tedavileri",
    "oral_habits": "Ağız bakımı ve alışkanlıklar",
    "medical_history": "Sistemik hastalık / hasta beyanı",
    "medications": "İlaç / hasta beyanı",
    "allergies": "Alerji / hasta beyanı",
}


def parse_approved_fields(notes: str | None) -> dict[str, str]:
    """Parse only the explicit, allowlisted fields written by the voice approval flow."""
    values: dict[str, str] = {}
    if not isinstance(notes, str) or not notes:
        return values
    for paragraph in notes.split("\n\n"):
        for key, label in HISTORY_LABELS.items():
            prefix = label + ": "
            if paragraph.startswith(prefix):
                value = paragraph[len(prefix):].strip()
                if value and len(value) <= 3000:
                    values[key] = value
                break
    return values


class ApprovedAnamnesis(SQLModel, table=True):
    """Append-only approved patient anamnesis; no transcript or provider payload."""
    __tablename__ = "approvedanamnesis"
    __table_args__ = (
        UniqueConstraint("analysis_id", "field_key", name="uq_approvedanamnesis_analysis_field"),
        # Covers the owner/patient filter and per-field latest-row grouping in
        # reviewed_history_payload without redundant single-column indexes.
        Index(
            "ix_approvedanamnesis_owner_patient_field_id",
            "owner_user_id", "patient_id", "field_key", "id",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int
    patient_id: int
    field_key: str = Field(max_length=32)
    value: str = Field(max_length=3000)
    analysis_id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
