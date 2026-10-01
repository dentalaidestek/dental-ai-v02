"""Academic AI V2 durable indexing primitives.

Phase 1 deliberately does not replace the live V1 retrieval/indexer yet.
It introduces the persistence and concurrency contract that the later worker
will use: versioned builds, short leases with ownership tokens, and guarded
atomic publication.

All functions are provider-agnostic and pgvector-independent.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, select


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StudyIndexJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    course_id: int = Field(index=True)
    material_id: int = Field(index=True)
    index_version: str = Field(index=True)
    status: str = Field(default="QUEUED", index=True)  # QUEUED/RUNNING/DONE/FAILED/CANCELLED
    stage: str = Field(default="PREPARE", index=True)
    priority: int = Field(default=0, index=True)
    resource_class: str = Field(default="NORMAL", index=True)  # NORMAL/OCR_HEAVY
    attempts: int = 0
    failure_attempts: int = 0
    next_retry_at: Optional[datetime] = Field(default=None, index=True)
    lease_until: Optional[datetime] = Field(default=None, index=True)
    lease_token: Optional[str] = Field(default=None, index=True)
    worker_id: Optional[str] = Field(default=None, index=True)
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow_naive, index=True)
    updated_at: datetime = Field(default_factory=utcnow_naive, index=True)
    first_queued_at: datetime = Field(default_factory=utcnow_naive, index=True)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retire_after: Optional[datetime] = Field(default=None, index=True)
    expected_page_count: Optional[int] = None
    source_sha256: Optional[str] = Field(default=None, index=True)
    index_fingerprint: Optional[str] = Field(default=None, index=True)




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
    retrieval_terms: Optional[str] = None
    semantic_json: Optional[str] = None
    embedding_provider: Optional[str] = Field(default=None, index=True)
    embedding_model: Optional[str] = Field(default=None, index=True)
    embedding_dimensions: Optional[int] = None
    embedding_json: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow_naive, index=True)
    updated_at: datetime = Field(default_factory=utcnow_naive, index=True)




class StudyDeletionJob(SQLModel, table=True):
    """Durable privacy cleanup: DB tombstone is immediate, physical erasure retries."""
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    material_id: int = Field(index=True)
    storage_reference: Optional[str] = None
    provider_file_name: Optional[str] = None
    status: str = Field(default="QUEUED", index=True)  # QUEUED/RUNNING/DONE/FAILED
    attempts: int = 0
    next_retry_at: Optional[datetime] = Field(default=None, index=True)
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow_naive, index=True)
    completed_at: Optional[datetime] = None


class StudyProviderCircuit(SQLModel, table=True):
    """Shared provider outage state so many workers do not create retry storms."""
    provider_key: str = Field(primary_key=True)
    consecutive_failures: int = 0
    open_until: Optional[datetime] = Field(default=None, index=True)
    last_error: Optional[str] = None
    updated_at: datetime = Field(default_factory=utcnow_naive, index=True)


def provider_circuit_open(session: Session, provider_key: str) -> bool:
    row = session.get(StudyProviderCircuit, provider_key)
    return bool(row and row.open_until and row.open_until > utcnow_naive())


def record_provider_success(session: Session, provider_key: str) -> None:
    row = session.get(StudyProviderCircuit, provider_key) or StudyProviderCircuit(provider_key=provider_key)
    row.consecutive_failures = 0
    row.open_until = None
    row.last_error = None
    row.updated_at = utcnow_naive()
    session.add(row)
    session.commit()


def record_provider_failure(
    session: Session,
    provider_key: str,
    *,
    error: str,
    threshold: int = 3,
    open_seconds: int = 120,
) -> datetime | None:
    """Atomically increment shared failure state across concurrent workers."""
    now = utcnow_naive()
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        session.exec(
            text(
                """
                INSERT INTO studyprovidercircuit
                    (provider_key, consecutive_failures, open_until, last_error, updated_at)
                VALUES (:key, 1, NULL, :error, :now)
                ON CONFLICT (provider_key) DO UPDATE
                SET consecutive_failures = studyprovidercircuit.consecutive_failures + 1,
                    last_error = EXCLUDED.last_error,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            params={"key": provider_key, "error": (error or "")[:1000], "now": now},
        )
        session.exec(
            text(
                """
                UPDATE studyprovidercircuit
                SET open_until = :open_until
                WHERE provider_key = :key AND consecutive_failures >= :threshold
                """
            ),
            params={"key": provider_key, "threshold": max(1, threshold),
                    "open_until": now + timedelta(seconds=max(30, open_seconds))},
        )
        session.commit()
        row = session.get(StudyProviderCircuit, provider_key)
        return row.open_until if row else None

    row = session.get(StudyProviderCircuit, provider_key) or StudyProviderCircuit(provider_key=provider_key)
    row.consecutive_failures += 1
    row.last_error = (error or "")[:1000]
    if row.consecutive_failures >= max(1, threshold):
        row.open_until = now + timedelta(seconds=max(30, open_seconds))
    row.updated_at = now
    session.add(row)
    session.commit()
    return row.open_until


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
    resource_class: str = "NORMAL",
) -> StudyIndexJob:
    existing = session.exec(
        select(StudyIndexJob)
        .where(StudyIndexJob.material_id == material_id)
        .where(StudyIndexJob.index_version == index_version)
        .where(StudyIndexJob.status.in_(["QUEUED", "RUNNING"]))
    ).first()
    if existing:
        return existing
    from app.work_jobs import WorkCapacity
    from sqlalchemy import func
    if session.get_bind().dialect.name == "postgresql":
        session.exec(text("SELECT pg_advisory_xact_lock(71048233)"))
    backlog = session.exec(select(func.count()).select_from(StudyIndexJob).where(
        StudyIndexJob.status.in_(["QUEUED", "RUNNING"]))).one()
    if backlog >= int(__import__("os").getenv("STUDY_MAX_PENDING_INDEX_JOBS", "1000")):
        raise WorkCapacity("Academic indexing queue is full; retry later")
    job = StudyIndexJob(
        owner_user_id=owner_user_id,
        course_id=course_id,
        material_id=material_id,
        index_version=index_version,
        priority=priority,
        resource_class=resource_class,
        first_queued_at=utcnow_naive(),
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError:
        # The DB unique index is the final arbiter if two request processes
        # enqueue the same material generation concurrently.
        existing = session.exec(
            select(StudyIndexJob)
            .where(StudyIndexJob.material_id == material_id)
            .where(StudyIndexJob.index_version == index_version)
        ).first()
        if existing:
            return existing
        raise
    return job





def set_build_identity(
    session: Session,
    *,
    job_id: int,
    lease_token: str,
    worker_id: str,
    expected_page_count: int,
    source_sha256: str,
    index_fingerprint: str,
) -> bool:
    """Persist immutable source/config identity once, and reject drift on resume."""
    now = utcnow_naive()
    row = session.exec(
        text(
            """
            SELECT expected_page_count, source_sha256, index_fingerprint
            FROM studyindexjob
            WHERE id=:job_id AND status='RUNNING'
              AND lease_token=:lease_token AND worker_id=:worker_id
              AND lease_until IS NOT NULL AND lease_until > :now
            """
        ),
        params={"job_id": job_id, "lease_token": lease_token, "worker_id": worker_id, "now": now},
    ).first()
    if not row:
        return False
    existing = (row[0], row[1], row[2])
    wanted = (expected_page_count, source_sha256, index_fingerprint)
    if any(value is not None for value in existing) and existing != wanted:
        raise RuntimeError("BUILD_IDENTITY_MISMATCH")
    session.exec(
        text(
            """
            UPDATE studyindexjob
            SET expected_page_count=:pages, source_sha256=:sha,
                index_fingerprint=:fingerprint, updated_at=:now
            WHERE id=:job_id AND lease_token=:lease_token AND worker_id=:worker_id
            """
        ),
        params={"pages": expected_page_count, "sha": source_sha256, "fingerprint": index_fingerprint,
                "now": now, "job_id": job_id, "lease_token": lease_token, "worker_id": worker_id},
    )
    session.commit()
    return True


def restart_build_for_profile_change(
    session: Session,
    *,
    job_id: int,
    lease_token: str,
    worker_id: str,
) -> bool:
    """Discard an unpublished mixed-profile build and restart it safely.

    A deployment can change OCR or embedding configuration while a durable job
    is paused. Reusing its old artifacts would violate generation identity.
    The lease fence makes the cleanup and reset atomic for the current worker.
    """
    now = utcnow_naive()
    owned = session.exec(
        text(
            """
            SELECT material_id, index_version
            FROM studyindexjob
            WHERE id=:job_id AND status='RUNNING'
              AND lease_token=:lease_token AND worker_id=:worker_id
              AND lease_until IS NOT NULL AND lease_until > :now
            """
        ),
        params={
            "job_id": job_id,
            "lease_token": lease_token,
            "worker_id": worker_id,
            "now": now,
        },
    ).first()
    if not owned:
        session.rollback()
        return False
    material_id, index_version = int(owned[0]), str(owned[1])
    current = session.exec(
        text(
            "SELECT 1 FROM studymaterial "
            "WHERE id=:material_id AND deleted_at IS NULL "
            "AND building_index_version=:index_version"
        ),
        params={"material_id": material_id, "index_version": index_version},
    ).first()
    if not current:
        session.rollback()
        return False
    session.exec(
        text("DELETE FROM studyindexchunk WHERE material_id=:m AND index_version=:v"),
        params={"m": material_id, "v": index_version},
    )
    session.exec(
        text("DELETE FROM studyindexpage WHERE material_id=:m AND index_version=:v"),
        params={"m": material_id, "v": index_version},
    )
    result = session.exec(
        text(
            """
            UPDATE studyindexjob
            SET status='QUEUED', stage='PREPARE', resource_class='NORMAL',
                failure_attempts=0, next_retry_at=NULL,
                expected_page_count=NULL, source_sha256=NULL,
                index_fingerprint=NULL, last_error='INDEX_PROFILE_CHANGED',
                lease_until=NULL, lease_token=NULL, worker_id=NULL,
                updated_at=:now
            WHERE id=:job_id AND status='RUNNING'
              AND lease_token=:lease_token AND worker_id=:worker_id
              AND lease_until IS NOT NULL AND lease_until > :now
            """
        ),
        params={
            "job_id": job_id,
            "lease_token": lease_token,
            "worker_id": worker_id,
            "now": now,
        },
    )
    if getattr(result, "rowcount", 0) != 1:
        session.rollback()
        return False
    session.commit()
    return True


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
    require_embeddings: bool = True,
) -> tuple[bool, str | None]:
    """Fail closed: publication requires complete pages/chunks and, when configured, embeddings."""
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
    if require_embeddings and any(not row.embedding_json for row in chunks):
        return False, "EMBEDDINGS_INCOMPLETE"
    if require_embeddings and session.get_bind().dialect.name == "postgresql":
        native_missing = session.exec(
            text(
                "SELECT COUNT(*) FROM studyindexchunk "
                "WHERE material_id=:material_id AND index_version=:index_version "
                "AND embedding_array IS NULL"
            ),
            params={"material_id": material_id, "index_version": index_version},
        ).one()[0]
        if int(native_missing or 0) > 0:
            return False, "NATIVE_EMBEDDINGS_INCOMPLETE"
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



def enqueue_material_deletion(
    session: Session,
    *,
    owner_user_id: int,
    material_id: int,
    storage_reference: str | None,
    provider_file_name: str | None = None,
) -> StudyDeletionJob:
    existing = session.exec(
        select(StudyDeletionJob)
        .where(StudyDeletionJob.owner_user_id == owner_user_id)
        .where(StudyDeletionJob.material_id == material_id)
        .where(StudyDeletionJob.status.in_(["QUEUED", "RUNNING"]))
    ).first()
    if existing:
        return existing
    row = StudyDeletionJob(
        owner_user_id=owner_user_id,
        material_id=material_id,
        storage_reference=storage_reference,
        provider_file_name=provider_file_name,
    )
    session.add(row)
    session.flush()
    return row


def purge_material_index_artifacts(
    session: Session,
    *,
    owner_user_id: int,
    material_id: int,
) -> None:
    """Delete derived V2 content for a tombstoned material; safe to repeat."""
    session.exec(
        text("DELETE FROM studyindexchunk WHERE material_id=:m AND owner_user_id=:o"),
        params={"m": material_id, "o": owner_user_id},
    )
    session.exec(
        text("DELETE FROM studyindexpage WHERE material_id=:m AND owner_user_id=:o"),
        params={"m": material_id, "o": owner_user_id},
    )



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
                failure_attempts = 0,
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




def set_job_resource_class(
    session: Session,
    *,
    job_id: int,
    lease_token: str,
    worker_id: str,
    resource_class: str,
    stage: str,
    retry_at: datetime | None = None,
) -> bool:
    """Move a live job between bounded worker classes without losing progress."""
    now = utcnow_naive()
    result = session.exec(
        text(
            """
            UPDATE studyindexjob
            SET status = 'QUEUED',
                resource_class = :resource_class,
                stage = :stage,
                next_retry_at = :retry_at,
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
            "resource_class": resource_class,
            "stage": stage,
            "retry_at": retry_at,
            "now": now,
            "job_id": job_id,
            "lease_token": lease_token,
            "worker_id": worker_id,
        },
    )
    session.commit()
    return bool(getattr(result, "rowcount", 0) == 1)


def boost_material_job(
    session: Session,
    *,
    owner_user_id: int,
    material_id: int,
    priority: int = 100,
) -> bool:
    """Interactive demand may raise priority, never bypass readiness."""
    result = session.exec(
        text(
            """
            UPDATE studyindexjob
            SET priority = CASE WHEN priority < :priority THEN :priority ELSE priority END,
                updated_at = :now
            WHERE owner_user_id = :owner_user_id
              AND material_id = :material_id
              AND status = 'QUEUED'
            """
        ),
        params={
            "priority": priority,
            "now": utcnow_naive(),
            "owner_user_id": owner_user_id,
            "material_id": material_id,
        },
    )
    session.commit()
    return bool(getattr(result, "rowcount", 0) > 0)


def claim_next_index_job(
    session: Session,
    *,
    worker_id: str,
    lease_seconds: int = 120,
    resource_class: str = "NORMAL",
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
                WHERE resource_class = :resource_class
                  AND (
                    (
                        status = 'QUEUED'
                        AND (next_retry_at IS NULL OR next_retry_at <= :now)
                    )
                    OR (
                        status = 'RUNNING'
                        AND lease_until IS NOT NULL
                        AND lease_until <= :now
                    )
                  )
                ORDER BY
                         -- Aging prevents a steady stream of interactive boosts
                         -- from starving old background work forever.
                         (priority + LEAST(100, FLOOR(EXTRACT(EPOCH FROM (:now - first_queued_at)) / 300))) DESC,
                         CASE WHEN next_retry_at IS NULL THEN created_at ELSE next_retry_at END ASC,
                         created_at ASC, id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            ),
            params={"now": now, "resource_class": resource_class},
        ).first()
        if not row:
            return None
        job_id = int(row[0])
    else:
        candidate = session.exec(
            select(StudyIndexJob)
            .where(StudyIndexJob.resource_class == resource_class)
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
                failure_attempts = failure_attempts + 1,
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


def defer_index_job(
    session: Session,
    *,
    job_id: int,
    lease_token: str,
    worker_id: str,
    reason: str,
    retry_at: datetime,
) -> bool:
    """Release a lease for missing configuration without counting a failure."""
    now = utcnow_naive()
    result = session.exec(
        text(
            """
            UPDATE studyindexjob
            SET status = 'QUEUED',
                next_retry_at = :retry_at,
                last_error = :reason,
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
            "retry_at": retry_at,
            "reason": (reason or "")[:2000],
            "now": now,
            "job_id": job_id,
            "lease_token": lease_token,
            "worker_id": worker_id,
        },
    )
    session.commit()
    return bool(getattr(result, "rowcount", 0) == 1)




def retire_previous_generation(
    session: Session,
    *,
    material_id: int,
    keep_index_version: str,
    grace_seconds: int = 900,
) -> None:
    now = utcnow_naive()
    session.exec(
        text(
            """
            UPDATE studyindexjob
            SET retire_after = :retire_after, updated_at = :now
            WHERE material_id = :material_id
              AND index_version <> :keep_index_version
              AND status = 'DONE' AND retire_after IS NULL
            """
        ),
        params={"retire_after": now + timedelta(seconds=max(60, grace_seconds)),
                "now": now, "material_id": material_id,
                "keep_index_version": keep_index_version},
    )


def cleanup_retired_generations(session: Session, *, limit: int = 10) -> int:
    now = utcnow_naive()
    jobs = list(session.exec(
        select(StudyIndexJob)
        .where(StudyIndexJob.status == "DONE")
        .where(StudyIndexJob.retire_after != None)
        .where(StudyIndexJob.retire_after <= now)
        .order_by(StudyIndexJob.retire_after.asc())
        .limit(max(1, limit))
    ).all())
    cleaned = 0
    for job in jobs:
        active = session.exec(
            text("SELECT 1 FROM studymaterial WHERE id=:m AND deleted_at IS NULL AND active_index_version=:v"),
            params={"m": job.material_id, "v": job.index_version},
        ).first()
        if active:
            job.retire_after = None
            session.add(job)
            continue
        session.exec(text("DELETE FROM studyindexchunk WHERE material_id=:m AND index_version=:v"),
                     params={"m": job.material_id, "v": job.index_version})
        session.exec(text("DELETE FROM studyindexpage WHERE material_id=:m AND index_version=:v"),
                     params={"m": job.material_id, "v": job.index_version})
        job.retire_after = None
        session.add(job)
        cleaned += 1
    session.commit()
    return cleaned


def publish_index_version(
    session: Session,
    *,
    material_id: int,
    owner_user_id: int,
    index_version: str,
    job_id: int,
    lease_token: str,
    worker_id: str,
    require_embeddings: bool = True,
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
    if require_embeddings:
        native_clause = " AND embedding_array IS NOT NULL" if dialect == "postgresql" else ""
        chunk_stats = session.exec(
            text(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN embedding_json IS NOT NULL""" + native_clause + """ THEN 1 ELSE 0 END) AS ready
                FROM studyindexchunk
                WHERE material_id = :material_id AND index_version = :index_version
                """
            ),
            params={"material_id": material_id, "index_version": index_version},
        ).first()
    else:
        chunk_stats = session.exec(
            text(
                "SELECT COUNT(*) AS total, COUNT(*) AS ready FROM studyindexchunk "
                "WHERE material_id=:material_id AND index_version=:index_version"
            ),
            params={"material_id": material_id, "index_version": index_version},
        ).first()
    page_total = int(page_stats[0] or 0) if page_stats else 0
    page_ready = int(page_stats[1] or 0) if page_stats else 0
    if (
        page_total <= 0
        or page_total != page_ready
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
    retire_previous_generation(
        session,
        material_id=material_id,
        keep_index_version=index_version,
        grace_seconds=900,
    )
    session.commit()
    return True
