"""Atomic, reclaimable erasure claims with no transaction across remote I/O."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, or_, text, update
from sqlmodel import Session, select
from app.object_storage import delete as storage_delete
from app.study_ai import delete_file as delete_provider_file
from app.study_index_jobs import StudyDeletionJob, purge_material_index_artifacts


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _claim(session):
    now = _utcnow_naive()
    # next_retry_at doubles as RUNNING lease expiry; attempts is the fencing
    # generation. This is compatible with deployed tables (no new columns).
    query = select(StudyDeletionJob).where(or_(
        and_(StudyDeletionJob.status.in_(['QUEUED', 'FAILED']),
             or_(StudyDeletionJob.next_retry_at == None, StudyDeletionJob.next_retry_at <= now)),
        and_(StudyDeletionJob.status == 'RUNNING',
             or_(StudyDeletionJob.next_retry_at == None, StudyDeletionJob.next_retry_at <= now)),
    )).order_by(StudyDeletionJob.created_at, StudyDeletionJob.id).limit(1)
    if session.get_bind().dialect.name == 'postgresql':
        query = query.with_for_update(skip_locked=True)
    job = session.exec(query).first()
    if job is None:
        session.rollback()
        return None
    snapshot = job.model_dump()
    attempt = int(job.attempts) + 1
    changed = session.exec(update(StudyDeletionJob).where(
        StudyDeletionJob.id == job.id, StudyDeletionJob.attempts == job.attempts,
        StudyDeletionJob.status == job.status,
    ).values(status='RUNNING', attempts=attempt,
             next_retry_at=now + timedelta(minutes=5), last_error=None))
    session.commit()
    if changed.rowcount != 1:
        return None
    snapshot['attempts'] = attempt
    return snapshot


def _finish(session, job, *, status, error=None):
    now = _utcnow_naive()
    changed = session.exec(update(StudyDeletionJob).where(
        StudyDeletionJob.id == job['id'], StudyDeletionJob.attempts == job['attempts'],
        StudyDeletionJob.status == 'RUNNING', StudyDeletionJob.next_retry_at > now,
    ).values(status=status, last_error=error,
             completed_at=now if status == 'DONE' else None,
             next_retry_at=now + timedelta(seconds=min(3600, 30 * 2**min(job['attempts'], 7))) if status == 'FAILED' else None))
    session.commit()
    return changed.rowcount == 1


def run_deletion_slice(session: Session) -> str:
    job = _claim(session)
    if job is None:
        return 'IDLE'
    try:
        material = session.exec(text(
            'SELECT deleted_at FROM studymaterial WHERE id=:m AND owner_user_id=:o'
        ), params={'m': job['material_id'], 'o': job['owner_user_id']}).first()
        if material is not None and material[0] is None:
            _finish(session, job, status='DONE', error='SKIPPED_LIVE_MATERIAL')
            return 'SKIPPED'
        purge_material_index_artifacts(session, owner_user_id=job['owner_user_id'], material_id=job['material_id'])
        session.commit()
        session.close()
        if job['storage_reference']:
            storage_delete(job['storage_reference'])
        if job['provider_file_name']:
            delete_provider_file(job['provider_file_name'], strict=True)
    except Exception as exc:
        session.rollback()
        _finish(session, job, status='FAILED', error=type(exc).__name__)
        return 'RETRY'
    return 'DONE' if _finish(session, job, status='DONE') else 'LEASE_LOST'
