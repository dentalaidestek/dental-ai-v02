"""Atomic upserts for the current FDI tooth and surface observations."""
from datetime import datetime
from typing import Optional


def _upsert(session, model, conflict_columns, values) -> None:
    table = model.__table__
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError("Unsupported database for atomic tooth observation upsert")
    statement = insert(table).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=[table.c[name] for name in conflict_columns],
        set_={name: values[name] for name in ("status", "note", "updated_at")},
    )
    session.execute(statement)


def upsert_tooth_observation(session, model, patient_id: int, tooth_number: str,
                             status: str, note: Optional[str], updated_at: datetime) -> None:
    """Keep exactly one current observation per patient and FDI tooth."""
    _upsert(session, model, ("patient_id", "tooth_number"), {
        "patient_id": patient_id, "tooth_number": tooth_number,
        "status": status, "note": note, "updated_at": updated_at,
    })


def upsert_tooth_surface_observation(session, model, patient_id: int, tooth_number: str,
                                     surface: str, status: str, note: Optional[str],
                                     updated_at: datetime) -> None:
    """Keep exactly one current observation per patient, FDI tooth and surface."""
    _upsert(session, model, ("patient_id", "tooth_number", "surface"), {
        "patient_id": patient_id, "tooth_number": tooth_number, "surface": surface,
        "status": status, "note": note, "updated_at": updated_at,
    })
