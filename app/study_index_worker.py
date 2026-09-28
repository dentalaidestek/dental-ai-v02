"""Bounded, crash-resumable Academic AI V2 indexing worker.

The web process may enqueue shadow builds behind a default-off feature flag,
but it never imports or runs this worker. Each invocation claims one durable
job and performs one bounded slice. Durable page/chunk artifacts are the
checkpoint; process memory is never authoritative.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import socket
from datetime import datetime, timedelta, timezone

from pypdf import PdfReader, PdfWriter
from sqlmodel import Session, select

from app.object_storage import ensure_local as storage_ensure_local
from app.study_chunking import chunk_dental_page, normalize_extracted_text
from app.study_index_jobs import (
    StudyIndexChunk,
    StudyIndexJob,
    StudyIndexPage,
    claim_next_index_job,
    mark_index_job_failed,
    missing_page_numbers,
    pending_embedding_chunks,
    provider_circuit_open,
    publish_index_version,
    record_provider_failure,
    record_provider_success,
    set_build_identity,
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


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(value, high))


def worker_id() -> str:
    return (os.getenv("STUDY_INDEX_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}").strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text_quality(text: str) -> tuple[bool, str | None]:
    """Conservative extraction gate: suspicious text goes to OCR, not READY."""
    if not text:
        return False, "EMPTY"
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 24:
        return False, "TOO_SHORT"
    printable = sum(1 for ch in text if ch.isprintable())
    if printable / max(1, len(text)) < 0.97:
        return False, "LOW_PRINTABLE_RATIO"
    alnum = sum(1 for ch in text if ch.isalnum())
    if alnum / max(1, len(compact)) < 0.35:
        return False, "LOW_ALNUM_RATIO"
    replacement = text.count("\ufffd")
    if replacement / max(1, len(text)) > 0.01:
        return False, "DECODE_REPLACEMENTS"
    return True, None


def _vector_json(vector: list[float]) -> str:
    return json.dumps([float(item) for item in vector], separators=(",", ":"))


def _sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _index_fingerprint() -> str:
    target = get_embedding_target()
    payload = {
        "schema": "academic-v2-dental-structure-2",
        "embedding_provider": target.provider,
        "embedding_model": target.model,
        "embedding_dimensions": get_embedding_dimensions(),
        "ocr_provider": (os.getenv("STUDY_V2_OCR_PROVIDER") or "").strip().lower(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


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
    now = _utcnow_naive()
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
    section_title: str | None = None,
    content_kind: str = "TEXT",
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
            section_title=section_title,
            content_kind=content_kind,
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
        text = normalize_extracted_text(reader.pages[page_number - 1].extract_text())
        quality_ok, quality_reason = _text_quality(text)
        if not quality_ok:
            # OCR is a separate constrained stage. Empty or suspiciously
            # garbled extraction is never accepted merely because pypdf
            # returned a non-empty string.
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
                error=f"OCR_REQUIRED:{quality_reason}",
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


def _chunk_slice(session: Session, job: StudyIndexJob) -> str:
    """Create a bounded batch of deterministic, page-addressable chunks."""
    batch = _int_env("STUDY_V2_CHUNK_BATCH_PAGES", 16, 1, 50)
    rows = list(session.exec(
        select(StudyIndexPage)
        .where(StudyIndexPage.material_id == job.material_id)
        .where(StudyIndexPage.index_version == job.index_version)
        .where(StudyIndexPage.status.in_(list(TERMINAL_PAGE_STATES)))
        .order_by(StudyIndexPage.page_number.asc())
    ).all())
    processed = 0
    for page in rows:
        existing = session.exec(
            select(StudyIndexChunk.id)
            .where(StudyIndexChunk.material_id == job.material_id)
            .where(StudyIndexChunk.index_version == job.index_version)
            .where(StudyIndexChunk.page_start == page.page_number)
        ).first()
        if existing:
            continue
        if processed >= batch:
            return "CHUNK"
        if not _lease_still_owned(session, job):
            session.rollback()
            return "LEASE_LOST"
        chunks = chunk_dental_page(page.text_content or "")
        if not chunks:
            raise RuntimeError(f"NO_CHUNKS_FOR_PAGE:{page.page_number}")
        if len(chunks) >= 1000:
            raise RuntimeError(f"TOO_MANY_CHUNKS_FOR_PAGE:{page.page_number}")
        for local_index, chunk in enumerate(chunks):
            _upsert_chunk(
                session,
                job=job,
                chunk_index=((page.page_number - 1) * 1000) + local_index,
                page_number=page.page_number,
                text_content=chunk.text,
                section_title=chunk.section_title,
                content_kind=chunk.content_kind,
            )
        session.commit()
        processed += 1
    return "EMBED"


def _single_page_pdf(path, page_number: int) -> bytes:
    reader = PdfReader(str(path))
    if page_number < 1 or page_number > len(reader.pages):
        raise RuntimeError(f"OCR_PAGE_OUT_OF_RANGE:{page_number}")
    writer = PdfWriter()
    writer.add_page(reader.pages[page_number - 1])
    from io import BytesIO
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _prepare_image_checkpoint(session: Session, job: StudyIndexJob) -> str:
    existing = session.exec(
        select(StudyIndexPage)
        .where(StudyIndexPage.material_id == job.material_id)
        .where(StudyIndexPage.index_version == job.index_version)
        .where(StudyIndexPage.page_number == 1)
    ).first()
    if not existing:
        upsert_page_checkpoint(
            session,
            owner_user_id=job.owner_user_id,
            course_id=job.course_id,
            material_id=job.material_id,
            index_version=job.index_version,
            page_number=1,
            status="OCR_REQUIRED",
            text_content=None,
            extraction_method="IMAGE",
            content_sha256=None,
            error="OCR_REQUIRED:IMAGE_SOURCE",
        )
        session.commit()
    return "OCR"


def _ocr_slice(session: Session, job: StudyIndexJob, path, mime_type: str) -> str:
    """Process a bounded OCR batch through an optional provider.

    OCR is opt-in and fail-closed. The concrete provider is deliberately
    isolated behind this hook so the indexing contract does not depend on one
    OCR vendor. Until configured, pages remain durable OCR_REQUIRED artifacts.
    """
    provider_name = (os.getenv("STUDY_V2_OCR_PROVIDER") or "").strip().lower()
    if not provider_name:
        return "OCR_WAIT"
    batch = _int_env("STUDY_V2_OCR_BATCH_PAGES", 4, 1, 20)
    pages = list(session.exec(
        select(StudyIndexPage)
        .where(StudyIndexPage.material_id == job.material_id)
        .where(StudyIndexPage.index_version == job.index_version)
        .where(StudyIndexPage.status == "OCR_REQUIRED")
        .order_by(StudyIndexPage.page_number.asc())
        .limit(batch)
    ).all())
    if not pages:
        return "CHUNK"
    if provider_name != "gemini":
        # No vendor is silently guessed. Unsupported configuration is a
        # permanent configuration error rather than fabricated OCR output.
        raise RuntimeError(f"UNSUPPORTED_OCR_PROVIDER:{provider_name}")
    provider = get_provider("gemini")
    model = (os.getenv("STUDY_V2_OCR_MODEL") or "gemini-3.8-flash").strip()
    provider_key = f"ocr:gemini:{model}"
    if provider_circuit_open(session, provider_key):
        return "PROVIDER_PAUSED"
    attachment_type = "application/pdf" if mime_type == "application/pdf" else mime_type
    if not provider.supports_generation_attachment(attachment_type):
        raise RuntimeError(f"OCR_PROVIDER_UNSUPPORTED:{attachment_type}")
    for page in pages:
        if not _lease_still_owned(session, job):
            session.rollback()
            return "LEASE_LOST"
        from app.study_index_jobs import renew_index_lease
        if not renew_index_lease(
            session,
            job_id=job.id,
            lease_token=job.lease_token,
            worker_id=job.worker_id,
            lease_seconds=_int_env("STUDY_V2_LEASE_SECONDS", 180, 60, 1800),
        ):
            session.rollback()
            return "LEASE_LOST"
        try:
            text = provider.generate(
                model=model,
                system_prompt=(
                    "Yalnız verilen diş hekimliği ders notu sayfasını eksiksiz yazıya dök. "
                    "Başlıkları, maddeleri ve tablo satırlarını koru. Açıklama veya yorum ekleme."
                ),
                history=[],
                prompt="Bu tek sayfalık PDF'yi OCR gibi aktar.",
                attachments=[{
                    "mime_type": attachment_type,
                    "data": _single_page_pdf(path, page.page_number) if attachment_type == "application/pdf" else path.read_bytes(),
                    "label": f"Kaynak sayfa {page.page_number}",
                }],
                temperature=0.0,
                max_output_tokens=8000,
            )
        except StudyProviderError as exc:
            record_provider_failure(
                session,
                provider_key,
                error=str(exc),
                threshold=_int_env("STUDY_V2_CIRCUIT_FAILURES", 3, 1, 20),
                open_seconds=_int_env("STUDY_V2_CIRCUIT_OPEN_SECONDS", 120, 30, 1800),
            )
            raise
        if not _lease_still_owned(session, job):
            session.rollback()
            return "LEASE_LOST"
        record_provider_success(session, provider_key)
        text = normalize_extracted_text(text)
        quality_ok, reason = _text_quality(text)
        if not quality_ok:
            raise StudyProviderError(f"OCR_QUALITY_REJECTED:{reason}", retryable=True)
        upsert_page_checkpoint(
            session,
            owner_user_id=job.owner_user_id,
            course_id=job.course_id,
            material_id=job.material_id,
            index_version=job.index_version,
            page_number=page.page_number,
            status="OCR_DONE",
            text_content=text,
            extraction_method=f"GEMINI_OCR:{model}",
            content_sha256=_sha256_text(text),
            error=None,
        )
        session.commit()
    remaining = session.exec(
        select(StudyIndexPage.id)
        .where(StudyIndexPage.material_id == job.material_id)
        .where(StudyIndexPage.index_version == job.index_version)
        .where(StudyIndexPage.status == "OCR_REQUIRED")
    ).first()
    return "OCR" if remaining else "CHUNK"


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
    provider_key = f"embedding:{target.provider}:{target.model}"
    if provider_circuit_open(session, provider_key):
        return "PROVIDER_PAUSED"
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
        if job.lease_until and (job.lease_until - _utcnow_naive()).total_seconds() <= heartbeat_margin:
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
            job.lease_until = _utcnow_naive() + timedelta(seconds=heartbeat_extend)
        try:
            vector = provider.embed_text(
                model=target.model,
                text="Diş hekimliği ders materyalinde arama için bu bölümü temsil et:\n" + row.text_content,
                dimensions=dimensions,
            )
        except StudyProviderError as exc:
            threshold = _int_env("STUDY_V2_CIRCUIT_FAILURES", 3, 1, 20)
            open_seconds = _int_env("STUDY_V2_CIRCUIT_OPEN_SECONDS", 120, 30, 1800)
            record_provider_failure(
                session,
                provider_key,
                error=str(exc),
                threshold=threshold,
                open_seconds=open_seconds,
            )
            raise
        # The external call may outlive our lease. Re-check ownership before
        # persisting its result; otherwise a reclaimed stale worker could write.
        if not _lease_still_owned(session, job):
            session.rollback()
            return "LEASE_LOST"
        record_provider_success(session, provider_key)
        vector_json = _vector_json(vector)
        row.embedding_provider = target.provider
        row.embedding_model = target.model
        row.embedding_dimensions = len(vector)
        row.embedding_json = vector_json
        row.updated_at = _utcnow_naive()
        session.add(row)
        session.flush()
        if session.get_bind().dialect.name == "postgresql":
            # Native array is always available and keeps semantic scoring in
            # PostgreSQL. A pgvector column is filled too when the extension is
            # installed; capability setup creates the helper safely.
            from sqlalchemy import text as sql_text
            session.exec(
                sql_text(
                    "UPDATE studyindexchunk SET embedding_array=:vector "
                    "WHERE id=:chunk_id"
                ),
                params={"vector": vector, "chunk_id": row.id},
            )
            session.exec(
                sql_text("SELECT study_v2_sync_pgvector(:chunk_id, :vector_json)"),
                params={"chunk_id": row.id, "vector_json": vector_json},
            )
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

        # PREPARE establishes immutable identity. Every later slice reuses it;
        # if the R2/local source or indexing configuration changes mid-build,
        # the generation fails instead of mixing incompatible artifacts.
        if stage == "PREPARE":
            expected_pages = len(PdfReader(str(path)).pages) if mime_type == "application/pdf" else 1
            source_sha = _sha256_file(path)
            fingerprint = _index_fingerprint()
            if not set_build_identity(
                session,
                job_id=job.id,
                lease_token=job.lease_token,
                worker_id=job.worker_id,
                expected_page_count=expected_pages,
                source_sha256=source_sha,
                index_fingerprint=fingerprint,
            ):
                return "LEASE_LOST"
            job.expected_page_count = expected_pages
            job.source_sha256 = source_sha
            job.index_fingerprint = fingerprint

        if stage in {"PREPARE", "PARSE"}:
            if mime_type == "application/pdf":
                next_stage = _extract_pdf_slice(session, job, path)
            elif mime_type in {"image/jpeg", "image/png", "image/webp"}:
                next_stage = _prepare_image_checkpoint(session, job)
            else:
                raise RuntimeError(f"UNSUPPORTED_V2_MIME:{mime_type}")
        elif stage == "CHUNK":
            next_stage = _chunk_slice(session, job)
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
            next_stage = _ocr_slice(session, job, path, mime_type)
        elif stage == "OCR_WAIT":
            next_stage = "OCR_WAIT"
        elif stage == "VERIFY":
            if not job.expected_page_count or not job.source_sha256 or not job.index_fingerprint:
                raise RuntimeError("BUILD_IDENTITY_MISSING")
            if _sha256_file(path) != job.source_sha256 or _index_fingerprint() != job.index_fingerprint:
                raise RuntimeError("BUILD_IDENTITY_MISMATCH")
            page_count = job.expected_page_count
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
        if next_stage == "PROVIDER_PAUSED":
            retry_at = _utcnow_naive() + timedelta(seconds=_int_env("STUDY_V2_CIRCUIT_OPEN_SECONDS", 120, 30, 1800))
            mark_index_job_failed(
                session,
                job_id=job.id,
                lease_token=job.lease_token,
                worker_id=job.worker_id,
                error="PROVIDER_CIRCUIT_OPEN",
                retry_at=retry_at,
            )
            return "PROVIDER_PAUSED"
        if next_stage == "OCR_WAIT":
            # Release the lease and back off; no busy-loop while OCR support is
            # intentionally not active yet.
            retry_at = _utcnow_naive() + timedelta(minutes=5)
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
        max_attempts = _int_env("STUDY_V2_MAX_ATTEMPTS", 8, 1, 50)
        can_retry = bool(exc.retryable and job.failure_attempts < max_attempts)
        retry_at = _utcnow_naive() + timedelta(seconds=min(1800, 30 * (2 ** min(job.failure_attempts, 6)))) if can_retry else None
        mark_index_job_failed(
            session,
            job_id=job.id,
            lease_token=job.lease_token,
            worker_id=job.worker_id,
            error=f"PROVIDER:{exc}",
            retry_at=retry_at,
        )
        return "PROVIDER_RETRY" if can_retry else "PROVIDER_FAILED"
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
