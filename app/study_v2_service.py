"""Feature-gated orchestration helpers for a controlled V1/V2 transition."""
from __future__ import annotations

import os

from sqlmodel import Session, select

from app.study_index_jobs import begin_material_build, enqueue_index_job, new_index_version


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def indexing_enabled() -> bool:
    return _flag("STUDY_ACADEMIC_V2_INDEXING")


def reads_enabled() -> bool:
    return _flag("STUDY_ACADEMIC_V2_READS")


def streaming_enabled() -> bool:
    return reads_enabled() and _flag("STUDY_ACADEMIC_V2_STREAMING")


def enqueue_material_v2(session: Session, material) -> str | None:
    """Reserve and enqueue exactly one new generation inside caller's tx."""
    if not indexing_enabled() or material.id is None or material.deleted_at is not None:
        return None
    version = new_index_version()
    reserved = begin_material_build(
        session,
        material_id=material.id,
        owner_user_id=material.owner_user_id,
        index_version=version,
    )
    if not reserved:
        return None
    resource_class = "NORMAL" if material.mime_type == "application/pdf" else "OCR_HEAVY"
    enqueue_index_job(
        session,
        owner_user_id=material.owner_user_id,
        course_id=material.course_id,
        material_id=material.id,
        index_version=version,
        resource_class=resource_class,
    )
    return version


def enqueue_legacy_materials_v2(
    session: Session,
    *,
    material_model,
    limit: int = 100,
) -> int:
    """Queue pre-V2 uploads once, without replacing active/building indexes."""
    if not indexing_enabled():
        return 0
    materials = list(session.exec(
        select(material_model)
        .where(material_model.deleted_at == None)
        .where(material_model.index_status == "LEGACY")
        .where(material_model.active_index_version == None)
        .where(material_model.building_index_version == None)
        .order_by(material_model.id)
        .limit(max(1, min(limit, 1000)))
    ).all())
    queued = 0
    for material in materials:
        if enqueue_material_v2(session, material):
            queued += 1
    return queued


def course_v2_ready(session: Session, *, material_model, owner_user_id: int, course_id: int) -> bool:
    rows = list(session.exec(
        select(material_model)
        .where(material_model.owner_user_id == owner_user_id)
        .where(material_model.course_id == course_id)
        .where(material_model.deleted_at == None)
    ).all())
    return bool(rows) and all(
        row.index_status == "READY" and bool(row.active_index_version)
        for row in rows
    )
