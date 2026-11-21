"""Atomic upserts and optimistic revisions for current FDI observations."""
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Optional


_FDI_TOOTH_NUMBER = re.compile(r\"^(?:[1-4][1-8]|[5-8][1-5])$\")
_COMMON_SURFACES = frozenset({\"MESIAL\", \"DISTAL\", \"BUCCAL\", \"LINGUAL\"})


def valid_fdi_tooth_number(tooth_number: object) -> bool:
    \"\"\"Return whether a value is a canonical permanent or primary FDI tooth id.\"\"\"
    return isinstance(tooth_number, str) and bool(_FDI_TOOTH_NUMBER.fullmatch(tooth_number))


def applicable_tooth_surfaces(tooth_number: object) -> frozenset[str]:
    \"\"\"Return the five anatomically applicable surfaces for one FDI tooth.\"\"\"
    if not valid_fdi_tooth_number(tooth_number):
        return frozenset()
    axial_surface = \"INCISAL\" if int(tooth_number[1]) <= 3 else \"OCCLUSAL\"
    return _COMMON_SURFACES | {axial_surface}


def is_applicable_tooth_surface(tooth_number: object, surface: object) -> bool:
    \"\"\"Reject impossible incisal/occlusal observations at the API boundary.\"\"\"
    return isinstance(surface, str) and surface in applicable_tooth_surfaces(tooth_number)


def observation_revision(row, *, kind: str, patient_id: int, tooth_number: str,
                         surface: Optional[str] = None) -> str:
    """Return a deterministic revision for one tooth or one surface observation."""
    updated_at = getattr(row, "updated_at", None) if row is not None else None
    payload = {
        "v": 1,
        "kind": kind,
        "patient_id": int(patient_id),
        "tooth_number": str(tooth_number),
        "surface": surface,
        "status": getattr(row, "status", None) if row is not None else None,
        "note": getattr(row, "note", None) if row is not None else None,
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return sha256(b"dai-tooth-observation-v1:" + encoded).hexdigest()


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
