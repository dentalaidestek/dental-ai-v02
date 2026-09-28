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




class StudyIndexPage(SQLModel, table=True):
    """Durable extraction/OCR checkpoint for one source page and generation."""
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    course_id: int = Field(index=True)
    material_id: int = Field(index=True)
    index_version: str = Field(index=True)
    page_number: int = Field(index=True)
    status: str = Field(default="PENDING", index=True)  # PENDING/EXTRACTED/OCR_REQUIRED/OCR_DONE/FAILED
    text_content: Optional[str] = None
    extraction_method: Optional[str] = Field(default=None, index=True)
    content_sha256: Optional[str] = Field(default=None, index=True)
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow_naive, index=True)
    updated_at: datetime = Field(default_factory=utcnow_naive, index=True)


class StudyIndexChunk(SQLModel, table=True):
    """V2 build artifact. BUILDING rows are never queried by live retrieval."""
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    course_id: int = Field(index=True)
    material_id: int = Field(index=True)
    index_version: str = Field(index=True)
    chunk_index: int = Field(index=True)
    page_start: int = Field(index=True)
    page_end: int = Field(index=True)
    section_title: Optional[str] = Field(default=None, index=True)
    content_kind: str = Field(default="TEXT", index=True)
    text_content: str
    text_sha256: str = Field(index=True)
    embedding_provider: Optional[str] = Field(default=None, index=True)
    embedding_model: Optional[str] = Field(default=None, index=True)
    embedding_dimensions: Optional[int] = None
    embedding_json: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow_naive, index=True)
    updated_at: datetime = Field(default_factory=utcnow_naive, index=True)


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





def upsert_page_checkpoint(
    session: Session,
    *,
    owner_user_id: int,
    course_id: int,
    material_id: int,
    index_version: str,
    page_number: int,
    status: str,
    text_content: str | None,
    extraction_method: str | None,
    content_sha256: str | None,
    error: str | None = None,
) -> StudyIndexPage:
    row = session.exec(
        select(StudyIndexPage)
        .where(StudyIndexPage.material_id == material_id)
        .where(StudyIndexPage.index_version == index_version)
        .where(StudyIndexPage.page_number == page_number)
    ).first()
    now = utcnow_naive()
    if row is None:
        row = StudyIndexPage(
            owner_user_id=owner_user_id,
            course_id=course_id,
            material_id=material_id,
            index_version=index_version,
            page_number=page_number,
        )
    row.status = status
    row.text_content = text_content
    row.extraction_method = extraction_method
    row.content_sha256 = content_sha256
    row.error = error
    row.updated_at = now
    session.add(row)
    session.flush()
    return row


def missing_page_numbers(
    session: Session,
    *,
    material_id: int,
    index_version: str,
    page_count: int,
    limit: int,
) -> list[int]:
    # Successful extraction and OCR hand-off are durable checkpoints. FAILED
    # rows stay retryable instead of being silently skipped forever.
    done = set(session.exec(
        select(StudyIndexPage.page_number)
        .where(StudyIndexPage.material_id == material_id)
        .where(StudyIndexPage.index_version == index_version)
        .where(StudyIndexPage.status.in_(["EXTRACTED", "OCR_REQUIRED", "OCR_DONE"]))
    ).all())
    result: list[int] = []
    for page_number in range(1, page_count + 1):
        if page_number not in done:
            result.append(page_number)
            if len(result) >= max(1, limit):
                break
    return result


def pending_embedding_chunks(
    session: Session,
    *,
    material_id: int,
    index_version: str,
    limit: int,
) -> list[StudyIndexChunk]:
    return list(session.exec(
        select(StudyIndexChunk)
        .where(StudyIndexChunk.material_id == material_id)
        .where(StudyIndexChunk.index_version == index_version)
        .where(StudyIndexChunk.embedding_json == None)
        .order_by(StudyIndexChunk.chunk_index.asc())
        .limit(max(1, limit))
    ).all())


def verify_build_complete(
    session: Session,
    *,
    material_id: int,
    index_version: str,
    expected_page_count: int,
) -> tuple[bool, str | None]:
    """Fail closed: publication requires complete pages and embedded chunks."""
    page_rows = session.exec(
        select(StudyIndexPage)
        .where(StudyIndexPage.material_id == material_id)
        .where(StudyIndexPage.index_version == index_version)
    ).all()
    good_pages = {
        row.page_number for row in page_rows
        if row.status in {"EXTRACTED", "OCR_DONE"}
    }
    expected = set(range(1, expected_page_count + 1))
    if good_pages != expected:
        return False, "PAGE_COVERAGE_INCOMPLETE"

    chunks = session.exec(
        select(StudyIndexChunk)
        .where(StudyIndexChunk.material_id == material_id)
        .where(StudyIndexChunk.index_version == index_version)
    ).all()
    if not chunks:
        return False, "NO_CHUNKS"
    if any(not row.embedding_json for row in chunks):
        return False, "EMBEDDINGS_INCOMPLETE"
    if any(row.page_start < 1 or row.page_end < row.page_start or row.page_end > expected_page_count for row in chunks):
        return False, "CHUNK_PAGE_RANGE_INVALID"
    return True, None


def begin_material_build(
    session: Session,
    *,
    material_id: int,
    owner_user_id: int,
    index_version: str,
) -> bool:
    """Reserve a generation for one material before enqueueing its job."""
    result = session.exec(
        text(
            """
            UPDATE studymaterial
            SET building_index_version = :index_version,
                index_status = CASE WHEN active_index_version IS NULL THEN 'PROCESSING' ELSE index_status END,
                index_error = NULL
            WHERE id = :material_id
              AND owner_user_id = :owner_user_id
              AND deleted_at IS NULL
            """
        ),
        params={
            "index_version": index_version,
            "material_id": material_id,
            "owner_user_id": owner_user_id,
        },
    )
    # Keep caller in control of the surrounding upload/rebuild transaction.
    return bool(getattr(result, "rowcount", 0) == 1)


def tombstone_material(
    session: Session,
    *,
    material_id: int,
    owner_user_id: int,
) -> bool:
    """Immediately make a material unpublishable; physical cleanup is later."""
    now = utcnow_naive()
    result = session.exec(
        text(
            """
            UPDATE studymaterial
            SET deleted_at = :now,
                index_status = 'DELETED',
                building_index_version = NULL
            WHERE id = :material_id
              AND owner_user_id = :owner_user_id
              AND deleted_at IS NULL
            """
        ),
        params={"now": now, "material_id": material_id, "owner_user_id": owner_user_id},
    )
    session.exec(
        text(
            """
            UPDATE studyindexjob
            SET status = 'CANCELLED',
                lease_until = NULL,
                lease_token = NULL,
                worker_id = NULL,
                updated_at = :now,
                completed_at = :now
            WHERE material_id = :material_id
              AND owner_user_id = :owner_user_id
              AND status IN ('QUEUED', 'RUNNING')
            """
        ),
        params={"now": now, "material_id": material_id, "owner_user_id": owner_user_id},
    )
    return bool(getattr(result, "rowcount", 0) == 1)


def yield_index_job(
    session: Session,
    *,
    job_id: int,
    lease_token: str,
    worker_id: str,
    stage: str,
    priority: int | None = None,
) -> bool:
    """Commit one bounded work slice and return the durable job to the queue."""
    now = utcnow_naive()
    priority_sql = ", priority = :priority" if priority is not None else ""
    params = {
        "now": now,
        "job_id": job_id,
        "lease_token": lease_token,
        "worker_id": worker_id,
        "stage": stage,
    }
    if priority is not None:
        params["priority"] = priority
    result = session.exec(
        text(
            """
            UPDATE studyindexjob
            SET status = 'QUEUED',
                stage = :stage,
                next_retry_at = NULL,
                lease_until = NULL,
                lease_token = NULL,
                worker_id = NULL,
                updated_at = :now
            """ + priority_sql + """
            WHERE id = :job_id
              AND status = 'RUNNING'
              AND lease_token = :lease_token
              AND worker_id = :worker_id
              AND lease_until IS NOT NULL
              AND lease_until > :now
            """
        ),
        params=params,
    )
    session.commit()
    return bool(getattr(result, "rowcount", 0) == 1)


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
              AND lease_until IS NOT NULL
              AND lease_until > :now
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
              AND lease_until IS NOT NULL
              AND lease_until > :now
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

    # Publication itself verifies the durable artifacts. A caller cannot make a
    # partially extracted/embedded generation visible by skipping worker checks.
    page_stats = session.exec(
        text(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status IN ('EXTRACTED', 'OCR_DONE') THEN 1 ELSE 0 END) AS ready
            FROM studyindexpage
            WHERE material_id = :material_id AND index_version = :index_version
            """
        ),
        params={"material_id": material_id, "index_version": index_version},
    ).first()
    chunk_stats = session.exec(
        text(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN embedding_json IS NOT NULL THEN 1 ELSE 0 END) AS embedded
            FROM studyindexchunk
            WHERE material_id = :material_id AND index_version = :index_version
            """
        ),
        params={"material_id": material_id, "index_version": index_version},
    ).first()
    if (
        not page_stats or int(page_stats[0] or 0) <= 0
        or int(page_stats[0] or 0) != int(page_stats[1] or 0)
        or not chunk_stats or int(chunk_stats[0] or 0) <= 0
        or int(chunk_stats[0] or 0) != int(chunk_stats[1] or 0)
    ):
        session.rollback()
        return False

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
