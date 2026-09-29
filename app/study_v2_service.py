"""Feature-gated orchestration helpers for a controlled V1/V2 transition."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import text
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


def v2_only_enabled() -> bool:
    """Return whether Academic AI must never enqueue or execute V1 work."""
    return _flag("STUDY_ACADEMIC_V2_ONLY")


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


def enqueue_legacy_material_rows_v2(session: Session, *, limit: int = 100) -> int:
    """Queue legacy uploads without importing the web application's model graph.

    The standalone index worker must stay independent from ``app.main``.  That
    module constructs the FastAPI application, template registry and web DB
    engine, all of which are unnecessary resident memory in a PDF/OCR worker.
    Keep this compatibility backfill on the shared SQL table contract instead.
    """
    if not indexing_enabled():
        return 0
    bounded_limit = max(1, min(int(limit), 1000))
    rows = session.execute(text(
        """
        SELECT id, owner_user_id, course_id, mime_type, deleted_at
        FROM studymaterial
        WHERE deleted_at IS NULL
          AND index_status = 'LEGACY'
          AND active_index_version IS NULL
          AND building_index_version IS NULL
        ORDER BY id
        LIMIT :limit
        """
    ), {"limit": bounded_limit}).mappings().all()
    queued = 0
    for row in rows:
        if enqueue_material_v2(session, SimpleNamespace(**dict(row))):
            queued += 1
    return queued


def reactivate_configured_ocr_jobs(session: Session) -> int:
    """Repair counters polluted by the old configuration-wait behavior.

    This is deliberately guarded by a one-shot operations flag and targets
    only queued/failed OCR-stage jobs after a provider is configured.
    """
    if (
        not indexing_enabled()
        or not (os.getenv("STUDY_V2_OCR_PROVIDER") or "").strip()
        or not _flag("STUDY_V2_REACTIVATE_OCR_ON_STARTUP")
    ):
        return 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = session.exec(text(
        """
        UPDATE studyindexjob
        SET status = 'QUEUED',
            failure_attempts = 0,
            next_retry_at = :now,
            last_error = 'OCR_PROVIDER_REACTIVATED',
            lease_until = NULL,
            lease_token = NULL,
            worker_id = NULL,
            updated_at = :now
        WHERE resource_class = 'OCR_HEAVY'
          AND status IN ('QUEUED', 'FAILED')
          AND stage IN ('OCR', 'OCR_WAIT')
        """
    ), params={"now": now})
    return int(getattr(result, "rowcount", 0) or 0)


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


def legacy_indexing_required() -> bool:
    """Keep V1 until V2 reads are live; shadow indexing is an explicit canary."""
    if v2_only_enabled():
        return False
    return not reads_enabled() or _flag("STUDY_V1_SHADOW_INDEXING")


def validate_configuration() -> None:
    if reads_enabled() and not indexing_enabled():
        raise RuntimeError("STUDY_ACADEMIC_V2_READS requires STUDY_ACADEMIC_V2_INDEXING")
    if v2_only_enabled() and not indexing_enabled():
        raise RuntimeError("STUDY_ACADEMIC_V2_ONLY requires STUDY_ACADEMIC_V2_INDEXING")
    if v2_only_enabled() and not reads_enabled():
        raise RuntimeError("STUDY_ACADEMIC_V2_ONLY requires STUDY_ACADEMIC_V2_READS")
