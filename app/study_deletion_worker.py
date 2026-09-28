"""Durable physical erasure worker for Academic AI V2 materials.

The web path must tombstone first. This worker removes derived DB content and
external/local file copies, retrying failures without making deleted content
queryable again.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlmodel import Session, select

from app.object_storage import delete as storage_delete
from app.study_ai import delete_file as delete_provider_file
from app.study_index_jobs import StudyDeletionJob, purge_material_index_artifacts


def run_deletion_slice(session: Session) -> str:
    now = datetime.utcnow()
    job = session.exec(
        select(StudyDeletionJob)
        .where(StudyDeletionJob.status.in_(["QUEUED", "FAILED"]))
        .where((StudyDeletionJob.next_retry_at == None) | (StudyDeletionJob.next_retry_at <= now))
        .order_by(StudyDeletionJob.created_at.asc(), StudyDeletionJob.id.asc())
        .limit(1)
    ).first()
    if not job:
        return "IDLE"

    # A deletion job is valid only for a still-tombstoned material. Never erase
    # a live material if an id were accidentally reused/restored.
    tombstoned = session.exec(
        text("SELECT 1 FROM studymaterial WHERE id=:m AND owner_user_id=:o AND deleted_at IS NOT NULL"),
        params={"m": job.material_id, "o": job.owner_user_id},
    ).first()
    if not tombstoned:
        job.status = "DONE"
        job.completed_at = now
        job.last_error = "SKIPPED_NOT_TOMBSTONED"
        session.add(job)
        session.commit()
        return "SKIPPED"

    job.status = "RUNNING"
    job.attempts += 1
    job.last_error = None
    session.add(job)
    session.commit()

    try:
        # Derived text/embeddings can contain personal data too; purge them,
        # not only the original R2 object.
        purge_material_index_artifacts(
            session, owner_user_id=job.owner_user_id, material_id=job.material_id
        )
        session.commit()
        if job.storage_reference:
            storage_delete(job.storage_reference)
        if job.provider_file_name:
            delete_provider_file(job.provider_file_name)
    except Exception as exc:
        session.rollback()
        fresh = session.get(StudyDeletionJob, job.id)
        fresh.status = "FAILED"
        fresh.last_error = str(exc)[:1000]
        delay = min(3600, 30 * (2 ** min(fresh.attempts, 7)))
        fresh.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
        session.add(fresh)
        session.commit()
        return "RETRY"

    fresh = session.get(StudyDeletionJob, job.id)
    fresh.status = "DONE"
    fresh.next_retry_at = None
    fresh.completed_at = datetime.utcnow()
    session.add(fresh)
    session.commit()
    return "DONE"
