"""Bounded, crash-resumable Academic AI V2 indexing worker.

This module is intentionally not wired into the live V1 upload path yet.
Each invocation claims one durable job and performs one bounded slice. Durable
page/chunk artifacts are the checkpoint; there is no fragile in-memory cursor.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import socket
from datetime import datetime, timedelta

from pypdf import PdfReader
from sqlmodel import Session, select

from app.object_storage import ensure_local as storage_ensure_local
from app.study_index_jobs import (
    StudyIndexChunk,
    StudyIndexJob,
    StudyIndexPage,
    claim_next_index_job,
    mark_index_job_failed,
    missing_page_numbers,
    pending_embedding_chunks,
    publish_index_version,
    set_job_resource_class,
    upsert_page_checkpoint,
    verify_build_complete,
    yield_index_job,
)
from app.study_provider import (
    StudyProviderError,
    get_embedding_dimensions,
    get_embedding_target,
    get_provider,
)

logger = logging.getLogger(__name__)

TERMINAL_PAGE_STATES = {"EXTRACTED", "OCR_DONE"}


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(value, high))


def worker_id() -> str:
    return (os.getenv("STUDY_INDEX_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}").strip()


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _vector_json(vector: list[float]) -> str:
    return json.dumps([float(item) for item in vector], separators=(",", ":"))


def _material_row(session: Session, material_id: int, owner_user_id: int):
    # Avoid importing app.main here: the worker must not create an import cycle.
    return session.exec(
        __import__("sqlalchemy").text(
            """
            SELECT id, course_id, owner_user_id, file_path, mime_type,
                   display_name, deleted_at, building_index_version
            FROM studymaterial
            WHERE id = :material_id AND owner_user_id = :owner_user_id
            """
        ),
        params={"material_id": material_id, "owner_user_id": owner_user_id},
    ).first()


def _lease_still_owned(session: Session, job: StudyIndexJob) -> bool:
    if job.id is None or not job.lease_token or not job.worker_id:
        return False
    now = datetime.utcnow()
    row = session.exec(
        __import__("sqlalchemy").text(
            """
            SELECT 1 FROM studyindexjob
            WHERE id = :job_id AND status = 'RUNNING'
              AND lease_token = :lease_token AND worker_id = :worker_id
              AND lease_until IS NOT NULL AND lease_until > :now
            """
        ),
        params={
            "job_id": job.id,
            "lease_token": job.lease_token,
            "worker_id": job.worker_id,
            "now": now,
        },
    ).first()
    return bool(row)


def _upsert_chunk(
    session: Session,
    *,
    job: StudyIndexJob,
    chunk_index: int,
    page_number: int,
    text_content: str,
) -> None:
    existing = session.exec(
        select(StudyIndexChunk)
        .where(StudyIndexChunk.material_id == job.material_id)
        .where(StudyIndexChunk.index_version == job.index_version)
        .where(StudyIndexChunk.chunk_index == chunk_index)
    ).first()
    if existing:
        # Immutable generation artifact: a replay must produce the same text.
        if existing.text_sha256 != _sha256_text(text_content):
            raise RuntimeError("INDEX_ARTIFACT_MISMATCH")
        return
    session.add(
        StudyIndexChunk(
            owner_user_id=job.owner_user_id,
            course_id=job.course_id,
            material_id=job.material_id,
            index_version=job.index_version,
            chunk_index=chunk_index,
            page_start=page_number,
            page_end=page_number,
            content_kind="TEXT",
            text_content=text_content,
            text_sha256=_sha256_text(text_content),
        )
    )
    session.flush()


def _extract_pdf_slice(session: Session, job: StudyIndexJob, path) -> str:
    reader = PdfReader(str(path))
    max_pages = _int_env("STUDY_RAG_MAX_PDF_PAGES", 300, 1, 2000)
    if len(reader.pages) > max_pages:
        raise RuntimeError(f"PDF_PAGE_LIMIT:{len(reader.pages)}>{max_pages}")
    batch = _int_env("STUDY_V2_PARSE_BATCH_PAGES", 12, 1, 50)
    missing = missing_page_numbers(
        session,
        material_id=job.material_id,
        index_version=job.index_version,
        page_count=len(reader.pages),
        limit=batch,
    )
    if not missing:
        return "CHUNK"

    for page_number in missing:
        if not _lease_still_owned(session, job):
            session.rollback()
            return "LEASE_LOST"
        text = _normalize_text(reader.pages[page_number - 1].extract_text())
        if not text:
            # OCR is a separate constrained stage. Do not pretend a blank scan
            # is successfully indexed and do not publish around it.
            upsert_page_checkpoint(
                session,
                owner_user_id=job.owner_user_id,
                course_id=job.course_id,
                material_id=job.material_id,
                index_version=job.index_version,
                page_number=page_number,
                status="OCR_REQUIRED",
                text_content=None,
                extraction_method="PDF_TEXT",
                content_sha256=None,
            )
        else:
            digest = _sha256_text(text)
            upsert_page_checkpoint(
                session,
                owner_user_id=job.owner_user_id,
                course_id=job.course_id,
                material_id=job.material_id,
                index_version=job.index_version,
                page_number=page_number,
                status="EXTRACTED",
                text_content=text,
                extraction_method="PDF_TEXT",
                content_sha256=digest,
            )
            # Stage-3 baseline is one durable page chunk. Structure-aware
            # splitting replaces this in the retrieval/chunking phase without
            # weakening crash recovery.
            _upsert_chunk(
                session,
                job=job,
                chunk_index=page_number - 1,
                page_number=page_number,
                text_content=text,
            )
        session.commit()

    remaining = missing_page_numbers(
        session,
        material_id=job.material_id,
        index_version=job.index_version,
        page_count=len(reader.pages),
        limit=1,
    )
    if remaining:
        return "PARSE"
    unresolved = session.exec(
        select(StudyIndexPage)
        .where(StudyIndexPage.material_id == job.material_id)
        .where(StudyIndexPage.index_version == job.index_version)
        .where(StudyIndexPage.status == "OCR_REQUIRED")
    ).first()
    return "OCR" if unresolved else "CHUNK"


def _embed_slice(session: Session, job: StudyIndexJob) -> str:
    batch = _int_env("STUDY_V2_EMBED_BATCH_CHUNKS", 16, 1, 50)
    rows = pending_embedding_chunks(
        session,
        material_id=job.material_id,
        index_version=job.index_version,
        limit=batch,
    )
    if not rows:
        return "VERIFY"
    target = get_embedding_target()
    dimensions = get_embedding_dimensions()
    provider = get_provider(target.provider)
    heartbeat_margin = _int_env("STUDY_V2_HEARTBEAT_MARGIN_SECONDS", 45, 10, 300)
    heartbeat_extend = _int_env("STUDY_V2_LEASE_SECONDS", 180, 60, 1800)

    for row in rows:
        if not _lease_still_owned(session, job):
            session.rollback()
            return "LEASE_LOST"
        # Provider calls can be slower than local parsing. Renew before the
        # call when the lease is close to expiry; ownership token prevents a
        # stale worker from extending somebody else's reclaimed lease.
        if job.lease_until and (job.lease_until - datetime.utcnow()).total_seconds() <= heartbeat_margin:
            from app.study_index_jobs import renew_index_lease
            if not renew_index_lease(
                session,
                job_id=job.id,
                lease_token=job.lease_token,
                worker_id=job.worker_id,
                lease_seconds=heartbeat_extend,
            ):
                session.rollback()
                return "LEASE_LOST"
            job.lease_until = datetime.utcnow() + timedelta(seconds=heartbeat_extend)
        vector = provider.embed_text(
            model=target.model,
            text="Diş hekimliği ders materyalinde arama için bu bölümü temsil et:\n" + row.text_content,
            dimensions=dimensions,
        )
        row.embedding_provider = target.provider
        row.embedding_model = target.model
        row.embedding_dimensions = len(vector)
        row.embedding_json = _vector_json(vector)
        row.updated_at = datetime.utcnow()
        session.add(row)
        session.commit()
    return "EMBED" if pending_embedding_chunks(
        session,
        material_id=job.material_id,
        index_version=job.index_version,
        limit=1,
    ) else "VERIFY"


def run_one_slice(
    session: Session,
    *,
    identity: str | None = None,
    resource_class: str = "NORMAL",
) -> str:
    """Claim and process at most one bounded unit. Returns a diagnostic state."""
    identity = identity or worker_id()
    lease_seconds = _int_env("STUDY_V2_LEASE_SECONDS", 180, 60, 1800)
    job = claim_next_index_job(
        session,
        worker_id=identity,
        lease_seconds=lease_seconds,
        resource_class=resource_class,
    )
    if not job or job.id is None or not job.lease_token or not job.worker_id:
        return "IDLE"

    try:
        material = _material_row(session, job.material_id, job.owner_user_id)
        if not material or material[6] is not None or material[7] != job.index_version:
            # Superseded/deleted jobs must never mutate newer generations.
            mark_index_job_failed(
                session,
                job_id=job.id,
                lease_token=job.lease_token,
                worker_id=job.worker_id,
                error="BUILD_SUPERSEDED_OR_DELETED",
            )
            return "STALE"

        path = storage_ensure_local(material[3])
        mime_type = material[4] or ""
        stage = (job.stage or "PREPARE").upper()

        if stage in {"PREPARE", "PARSE"}:
            if mime_type == "application/pdf":
                next_stage = _extract_pdf_slice(session, job, path)
            else:
                raise RuntimeError(f"UNSUPPORTED_V2_MIME:{mime_type}")
        elif stage == "CHUNK":
            # Page artifacts already create deterministic baseline chunks.
            next_stage = "EMBED"
        elif stage == "EMBED":
            next_stage = _embed_slice(session, job)
        elif stage == "OCR":
            if resource_class != "OCR_HEAVY":
                moved = set_job_resource_class(
                    session,
                    job_id=job.id,
                    lease_token=job.lease_token,
                    worker_id=job.worker_id,
                    resource_class="OCR_HEAVY",
                    stage="OCR",
                )
                return "MOVED:OCR_HEAVY" if moved else "LEASE_LOST"
            # OCR implementation is deliberately fail-closed until its engine
            # is selected/benchmarked. Heavy jobs cannot occupy NORMAL workers.
            next_stage = "OCR_WAIT"
        elif stage == "OCR_WAIT":
            next_stage = "OCR_WAIT"
        elif stage == "VERIFY":
            page_count = len(PdfReader(str(path)).pages) if mime_type == "application/pdf" else 1
            ok, reason = verify_build_complete(
                session,
                material_id=job.material_id,
                index_version=job.index_version,
                expected_page_count=page_count,
            )
            if not ok:
                raise RuntimeError(reason or "BUILD_INCOMPLETE")
            published = publish_index_version(
                session,
                material_id=job.material_id,
                owner_user_id=job.owner_user_id,
                index_version=job.index_version,
                job_id=job.id,
                lease_token=job.lease_token,
                worker_id=job.worker_id,
            )
            return "PUBLISHED" if published else "PUBLISH_REJECTED"
        else:
            raise RuntimeError(f"UNKNOWN_STAGE:{stage}")

        if next_stage == "LEASE_LOST":
            return "LEASE_LOST"
        if next_stage == "OCR_WAIT":
            # Release the lease and back off; no busy-loop while OCR support is
            # intentionally not active yet.
            retry_at = datetime.utcnow() + timedelta(minutes=5)
            mark_index_job_failed(
                session,
                job_id=job.id,
                lease_token=job.lease_token,
                worker_id=job.worker_id,
                error="OCR_REQUIRED",
                retry_at=retry_at,
            )
            return "OCR_WAIT"

        yielded = yield_index_job(
            session,
            job_id=job.id,
            lease_token=job.lease_token,
            worker_id=job.worker_id,
            stage=next_stage,
        )
        return f"YIELDED:{next_stage}" if yielded else "LEASE_LOST"
    except StudyProviderError as exc:
        session.rollback()
        # Transient provider errors do not permanently fail the document.
        retry_at = datetime.utcnow() + timedelta(seconds=60 if exc.retryable else 300)
        mark_index_job_failed(
            session,
            job_id=job.id,
            lease_token=job.lease_token,
            worker_id=job.worker_id,
            error=f"PROVIDER:{exc}",
            retry_at=retry_at,
        )
        return "PROVIDER_RETRY"
    except Exception as exc:
        logger.exception("Academic V2 index slice failed job=%s", job.id)
        session.rollback()
        mark_index_job_failed(
            session,
            job_id=job.id,
            lease_token=job.lease_token,
            worker_id=job.worker_id,
            error=str(exc),
        )
        return "FAILED"
