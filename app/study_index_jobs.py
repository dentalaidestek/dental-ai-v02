"""Academic AI V2 durable indexing primitives.

Phase 1 deliberately does not replace the live V1 retrieval/indexer yet.
It introduces the persistence and concurrency contract that the later worker
will use: versioned builds, short leases with ownership tokens, and guarded
atomic publication.

All functions are provider-agnostic and pgvector-independent.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, select


def utcnow_naive() -> datetime:
    return datetime.utcnow()


class StudyIndexJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    course_id: int = Field(index=True)
    material_id: int = Field(index=True)
    index_version: str = Field(index=True)
    status: str = Field(default="QUEUED", index=True)  # QUEUED/RUNNING/DONE/FAILED/CANCELLED
    stage: str = Field(default="PREPARE", index=True)
    priority: int = Field(default=0, index=True)
    attempts: int = 0
    next_retry_at: Optional[datetime] = Field(default=None, index=True)
    lease_until: Optional[datetime] = Field(default=None, index=True)
    lease_token: Optional[str] = Field(default=None, index=True)
    worker_id: Optional[str] = Field(default=None, index=True)
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow_naive, index=True)
    updated_at: datetime = Field(default_factory=utcnow_naive, index=True)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


def new_index_version() -> str:
    # Opaque generation identity: never infer ordering from the value.
    return secrets.token_hex(16)


def new_lease_token() -> str:
    return secrets.token_urlsafe(24)


def enqueue_index_job(
    session: Session,
    *,
    owner_user_id: int,
    course_id: int,
    material_id: int,
    index_version: str,
    priority: int = 0,
) -> StudyIndexJob:
    existing = session.exec(
        select(StudyIndexJob)
        .where(StudyIndexJob.material_id == material_id)
        .where(StudyIndexJob.index_version == index_version)
        .where(StudyIndexJob.status.in_(["QUEUED", "RUNNING"]))
    ).first()
    if existing:
        return existing
    job = StudyIndexJob(
        owner_user_id=owner_user_id,
        course_id=course_id,
        material_id=material_id,
        index_version=index_version,
        priority=priority,
    )
    session.add(job)
    try:
        session.flush()
    except IntegrityError:
        # The DB unique index is the final arbiter if two request processes
        # enqueue the same material generation concurrently.
        session.rollback()
        existing = session.exec(
            select(StudyIndexJob)
            .where(StudyIndexJob.material_id == material_id)
            .where(StudyIndexJob.index_version == index_version)
        ).first()
        if existing:
            return existing
        raise
    return job


def claim_next_index_job(
    session: Session,
    *,
    worker_id: str,
    lease_seconds: int = 120,
) -> StudyIndexJob | None:
    """Claim one eligible job.

    PostgreSQL uses SKIP LOCKED so workers do not block each other. SQLite is
    retained only as a development fallback; production concurrency semantics
    are validated on PostgreSQL.
    """
    now = utcnow_naive()
    lease_until = now + timedelta(seconds=max(30, lease_seconds))
    token = new_lease_token()

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        row = session.exec(
            text(
                """
                SELECT id
                FROM studyindexjob
                WHERE
                    (
                        status = 'QUEUED'
                        AND (next_retry_at IS NULL OR next_retry_at <= :now)
                    )
                    OR (
                        status = 'RUNNING'
                        AND lease_until IS NOT NULL
                        AND lease_until <= :now
                    )
                ORDER BY priority DESC, created_at ASC, id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            ),
            params={"now": now},
        ).first()
        if not row:
            return None
        job_id = int(row[0])
    else:
        candidate = session.exec(
            select(StudyIndexJob)
            .where(
                ((StudyIndexJob.status == "QUEUED") & ((StudyIndexJob.next_retry_at == None) | (StudyIndexJob.next_retry_at <= now)))
                | ((StudyIndexJob.status == "RUNNING") & (StudyIndexJob.lease_until != None) & (StudyIndexJob.lease_until <= now))
            )
            .order_by(StudyIndexJob.priority.desc(), StudyIndexJob.created_at.asc(), StudyIndexJob.id.asc())
        ).first()
        if not candidate or candidate.id is None:
            return None
        job_id = candidate.id

    job = session.get(StudyIndexJob, job_id)
    if not job:
        return None
    job.status = "RUNNING"
    job.worker_id = worker_id
    job.lease_token = token
    job.lease_until = lease_until
    job.attempts += 1
    job.started_at = job.started_at or now
    job.updated_at = now
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def renew_index_lease(
    session: Session,
    *,
    job_id: int,
    lease_token: str,
    worker_id: str,
    lease_seconds: int = 120,
) -> bool:
    """Renew only the lease this exact worker still owns."""
    now = utcnow_naive()
    result = session.exec(
        text(
            """
            UPDATE studyindexjob
            SET lease_until = :lease_until, updated_at = :now
            WHERE id = :job_id
              AND status = 'RUNNING'
              AND lease_token = :lease_token
              AND worker_id = :worker_id
            """
        ),
        params={
            "lease_until": now + timedelta(seconds=max(30, lease_seconds)),
            "now": now,
            "job_id": job_id,
            "lease_token": lease_token,
            "worker_id": worker_id,
        },
    )
    session.commit()
    return bool(getattr(result, "rowcount", 0) == 1)


def mark_index_job_failed(
    session: Session,
    *,
    job_id: int,
    lease_token: str,
    worker_id: str,
    error: str,
    retry_at: datetime | None = None,
) -> bool:
    now = utcnow_naive()
    next_status = "QUEUED" if retry_at is not None else "FAILED"
    result = session.exec(
        text(
            """
            UPDATE studyindexjob
            SET status = :status,
                next_retry_at = :retry_at,
                last_error = :error,
                lease_until = NULL,
                lease_token = NULL,
                worker_id = NULL,
                updated_at = :now
            WHERE id = :job_id
              AND status = 'RUNNING'
              AND lease_token = :lease_token
              AND worker_id = :worker_id
            """
        ),
        params={
            "status": next_status,
            "retry_at": retry_at,
            "error": (error or "")[:2000],
            "now": now,
            "job_id": job_id,
            "lease_token": lease_token,
            "worker_id": worker_id,
        },
    )
    session.commit()
    return bool(getattr(result, "rowcount", 0) == 1)


def publish_index_version(
    session: Session,
    *,
    material_id: int,
    owner_user_id: int,
    index_version: str,
    job_id: int,
    lease_token: str,
    worker_id: str,
) -> bool:
    """Atomically publish a verified build.

    The material row is locked first. Publication fails closed when the
    material was deleted/tombstoned, a newer generation superseded this build,
    or the worker no longer owns the job lease.
    """
    now = utcnow_naive()
    dialect = session.bind.dialect.name if session.bind is not None else ""
    suffix = " FOR UPDATE" if dialect == "postgresql" else ""
    material = session.exec(
        text(
            """
            SELECT id, deleted_at, building_index_version
            FROM studymaterial
            WHERE id = :material_id AND owner_user_id = :owner_user_id
            """ + suffix
        ),
        params={"material_id": material_id, "owner_user_id": owner_user_id},
    ).first()
    if not material:
        session.rollback()
        return False
    if material[1] is not None or material[2] != index_version:
        session.rollback()
        return False

    owned = session.exec(
        text(
            """
            SELECT id
            FROM studyindexjob
            WHERE id = :job_id
              AND material_id = :material_id
              AND index_version = :index_version
              AND status = 'RUNNING'
              AND lease_token = :lease_token
              AND worker_id = :worker_id
              AND lease_until IS NOT NULL
              AND lease_until > :now
            """ + suffix
        ),
        params={
            "job_id": job_id,
            "material_id": material_id,
            "index_version": index_version,
            "lease_token": lease_token,
            "worker_id": worker_id,
            "now": now,
        },
    ).first()
    if not owned:
        session.rollback()
        return False

    # Chunk completeness is verified by the worker before entering this small
    # transaction. This transaction only performs the guarded visibility swap.
    session.exec(
        text(
            """
            UPDATE studymaterial
            SET active_index_version = :index_version,
                building_index_version = NULL,
                index_status = 'READY',
                index_error = NULL
            WHERE id = :material_id
            """
        ),
        params={"index_version": index_version, "material_id": material_id},
    )
    session.exec(
        text(
            """
            UPDATE studyindexjob
            SET status = 'DONE',
                completed_at = :now,
                updated_at = :now,
                lease_until = NULL,
                lease_token = NULL,
                worker_id = NULL
            WHERE id = :job_id
            """
        ),
        params={"now": now, "job_id": job_id},
    )
    session.commit()
    return True
