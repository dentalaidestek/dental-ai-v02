"""Bounded, crash-resumable Academic AI V2 indexing worker.

The web process may enqueue shadow builds behind a default-off feature flag,
but it never imports or runs this worker. Each invocation claims one durable
job and performs one bounded slice. Durable page/chunk artifacts are the
checkpoint; process memory is never authoritative.
"""
from __future__ import annotations
from app.object_cache import scoped as storage_scoped


import hashlib
import gc
from types import SimpleNamespace
import json
import logging
import os
import re
import socket
from datetime import datetime, timedelta, timezone

from pypdf import PdfReader
from sqlmodel import Session, select

from app.object_storage import ensure_local as storage_ensure_local
from app.study_chunking import chunk_dental_page, normalize_extracted_text
from app.dental_semantics import analyze_dental_text, retrieval_enrichment_text
from app.study_index_jobs import (
    StudyIndexChunk,
    StudyIndexJob,
    StudyIndexPage,
    claim_next_index_job,
    defer_index_job,
    mark_index_job_failed,
    missing_page_numbers,
    pending_embedding_chunks,
    provider_circuit_open,
    publish_index_version,
    record_provider_failure,
    record_provider_success,
    restart_build_for_profile_change,
    set_build_identity,
    set_job_resource_class,
    upsert_page_checkpoint,
    verify_build_complete,
    yield_index_job,
)
from app.study_local_ocr import LOCAL_OCR_ENGINE_VERSION, ocr_material_page
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

    # Long PDF text layers can still be unusable when fonts map glyphs to
    # garbage. Detect that without penalizing normal Turkish/Latin dental terms.
    tokens = re.findall(r"\\S+", text)
    if len(tokens) >= 12:
        singletons = sum(1 for token in tokens if len(token.strip(".,;:!?()[]{}")) == 1)
        if singletons / len(tokens) > 0.42:
            return False, "FRAGMENTED_GLYPHS"
        noisy = sum(
            1 for token in tokens
            if len(token) >= 4
            and sum(ch.isalnum() or ch in "-/'’." for ch in token) / len(token) < 0.65
        )
        if noisy / len(tokens) > 0.18:
            return False, "NOISY_TOKENS"

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 8:
        repeated = max((lines.count(line) for line in set(lines)), default=0)
        if repeated / len(lines) > 0.45:
            return False, "REPEATED_GLYPH_LINES"
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
    payload = {
        "schema": "academic-v2-dental-semantics-7",
        "retrieval_profile": "fts-local-v1",
        "chunk_profile": "dental-page-v2-margin-position-safe",
        "embedding_provider": None,
        "embedding_model": None,
        "embedding_dimensions": None,
        "ocr_provider": (os.getenv("STUDY_V2_OCR_PROVIDER") or "local").strip().lower(),
        "ocr_engine": LOCAL_OCR_ENGINE_VERSION,
        "ocr_dpi": _int_env("STUDY_V2_LOCAL_OCR_DPI", 150, 120, 200),
        "ocr_retry_dpi": _int_env("STUDY_V2_LOCAL_OCR_RETRY_DPI", 210, 160, 240),
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
            """ + (" FOR UPDATE" if session.get_bind().dialect.name == "postgresql" else "")
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
    # PdfReader keeps cyclic page/xref graphs. Reclaim the previous bounded
    # slice before opening the document again on memory-limited workers.
    gc.collect()
    reader = PdfReader(str(path))
    try:
        max_pages = _int_env("STUDY_RAG_MAX_PDF_PAGES", 800, 1, 2000)
        if len(reader.pages) > max_pages:
            raise RuntimeError(f"PDF_PAGE_LIMIT:{len(reader.pages)}>{max_pages}")
        batch = _int_env("STUDY_V2_PARSE_BATCH_PAGES", 32, 1, 50)
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
            if not _lease_still_owned(session, job):
                session.rollback()
                return "LEASE_LOST"
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
    finally:
        stream = getattr(reader, "stream", None)
        if stream and hasattr(stream, "close"):
            stream.close()



def _strip_repeated_page_margins(rows: list[StudyIndexPage]) -> dict[int, str]:
    """Remove repeated page furniture only at observed margin line positions."""
    if len(rows) < 3:
        return {int(row.page_number): (row.text_content or "") for row in rows}
    positions: dict[str, set[int]] = {}
    per_page: dict[int, tuple[list[str], set[int]]] = {}
    for row in rows:
        lines = (row.text_content or "").splitlines()
        nonempty = [(idx, line.strip()) for idx, line in enumerate(lines) if line.strip()]
        # Only the outermost non-empty line is page furniture. Treating
        # the first/last two as margins can delete real body text when a short
        # page starts immediately below a repeated title.
        margin = nonempty[:1] + nonempty[-1:]
        margin_indices = {idx for idx, _ in margin}
        per_page[int(row.page_number)] = (lines, margin_indices)
        for _, line in margin:
            key = re.sub(r"\s+", " ", line).casefold()
            if 3 <= len(key) <= 120:
                positions.setdefault(key, set()).add(int(row.page_number))
    threshold = max(3, int(len(rows) * 0.60 + 0.999))
    repeated = {key for key, pages in positions.items() if len(pages) >= threshold}
    cleaned: dict[int, str] = {}
    for page_number, (lines, margin_indices) in per_page.items():
        out: list[str] = []
        for idx, line in enumerate(lines):
            key = re.sub(r"\s+", " ", line.strip()).casefold()
            if idx in margin_indices and key in repeated:
                continue
            out.append(line)
        cleaned[page_number] = normalize_extracted_text("\n".join(out))
    return cleaned

def _chunk_slice(session: Session, job: StudyIndexJob) -> str:
    """Create one bounded chunk batch with O(1) DB round-trips per page batch."""
    batch = _int_env("STUDY_V2_CHUNK_BATCH_PAGES", 32, 1, 100)
    rows = list(session.exec(
        select(StudyIndexPage)
        .where(StudyIndexPage.material_id == job.material_id)
        .where(StudyIndexPage.index_version == job.index_version)
        .where(StudyIndexPage.status.in_(list(TERMINAL_PAGE_STATES)))
        .where(~select(StudyIndexChunk.id).where(
            StudyIndexChunk.material_id == StudyIndexPage.material_id,
            StudyIndexChunk.index_version == StudyIndexPage.index_version,
            StudyIndexChunk.page_start == StudyIndexPage.page_number).exists())
        .order_by(StudyIndexPage.page_number.asc()).limit(batch)
    ).all())
    if not rows:
        return "VERIFY"
    if not _lease_still_owned(session, job):
        session.rollback()
        return "LEASE_LOST"

    pending: list[StudyIndexChunk] = []
    cleaned_page_text = _strip_repeated_page_margins(rows)
    inherited_title: str | None = None
    if rows and rows[0].page_number > 1:
        previous = session.exec(
            select(StudyIndexChunk.section_title)
            .where(StudyIndexChunk.material_id == job.material_id)
            .where(StudyIndexChunk.index_version == job.index_version)
            .where(StudyIndexChunk.page_start < rows[0].page_number)
            .where(StudyIndexChunk.section_title.is_not(None))
            .order_by(StudyIndexChunk.page_start.desc(), StudyIndexChunk.chunk_index.desc())
            .limit(1)
        ).first()
        inherited_title = previous
    for page in rows:
        chunks = chunk_dental_page(
            cleaned_page_text.get(int(page.page_number), page.text_content or ""),
            inherited_section_title=inherited_title,
        )
        explicit_titles = [chunk.section_title for chunk in chunks if chunk.section_title]
        if explicit_titles:
            inherited_title = explicit_titles[-1]
        if not chunks:
            raise RuntimeError(f"NO_CHUNKS_FOR_PAGE:{page.page_number}")
        if len(chunks) >= 1000:
            raise RuntimeError(f"TOO_MANY_CHUNKS_FOR_PAGE:{page.page_number}")
        for local_index, chunk in enumerate(chunks):
            semantic_source = f"{chunk.section_title or ''}\n{chunk.text}"
            features = analyze_dental_text(semantic_source)
            semantic_json = json.dumps({
                "nodes": features.node_ids,
                "specialties": features.specialties,
                "kinds": features.kinds,
                "measurements": features.measurements,
                "teeth": features.tooth_numbers,
                "imaging": features.imaging_types,
                "negated_nodes": features.negated_node_ids,
            }, ensure_ascii=False, separators=(",", ":"))
            pending.append(StudyIndexChunk(
                owner_user_id=job.owner_user_id,
                course_id=job.course_id,
                material_id=job.material_id,
                index_version=job.index_version,
                chunk_index=((page.page_number - 1) * 1000) + local_index,
                page_start=page.page_number,
                page_end=page.page_number,
                section_title=chunk.section_title,
                content_kind=chunk.content_kind,
                text_content=chunk.text,
                text_sha256=_sha256_text(chunk.text),
                retrieval_terms=retrieval_enrichment_text(semantic_source, features=features),
                semantic_json=semantic_json,
            ))

    if not _lease_still_owned(session, job):
        session.rollback()
        return "LEASE_LOST"
    session.add_all(pending)
    session.commit()

    remaining = session.exec(
        select(StudyIndexPage.id)
        .where(StudyIndexPage.material_id == job.material_id)
        .where(StudyIndexPage.index_version == job.index_version)
        .where(StudyIndexPage.status.in_(list(TERMINAL_PAGE_STATES)))
        .where(~select(StudyIndexChunk.id).where(
            StudyIndexChunk.material_id == StudyIndexPage.material_id,
            StudyIndexChunk.index_version == StudyIndexPage.index_version,
            StudyIndexChunk.page_start == StudyIndexPage.page_number).exists())
        .limit(1)
    ).first()
    return "CHUNK" if remaining else "VERIFY"


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
    """Process a bounded batch locally; source pages never leave the service."""
    provider_name = (os.getenv("STUDY_V2_OCR_PROVIDER") or "local").strip().lower()
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
    if provider_name != "local":
        raise RuntimeError(f"UNSUPPORTED_OCR_PROVIDER:{provider_name}")

    # PDFium document parsing is non-trivial on long scanned lecture notes.
    # Reuse one document for the whole bounded OCR slice; ocr_material_page
    # already accepts this handle and will reuse it for a quality retry too.
    pdf_document = None
    if mime_type == "application/pdf":
        import pypdfium2 as pdfium
        pdf_document = pdfium.PdfDocument(str(path))
    try:
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
            session.close()
            result = ocr_material_page(
                path,
                mime_type=mime_type,
                page_number=page.page_number,
                pdf_document=pdf_document,
            )
            if not _lease_still_owned(session, job):
                session.rollback()
                return "LEASE_LOST"
            text = normalize_extracted_text(result.text)
            method = f"LOCAL_OCR:{LOCAL_OCR_ENGINE_VERSION}:CONF_{result.confidence}"
            if result.visual_only:
                # A diagram/blank page can legitimately contain no dependable text.
                # Account for it without inventing clinical content; the immutable
                # source PDF remains the visual evidence for page-aware fallback.
                text = (
                    f"Sayfa {page.page_number}: Güvenilir metin çıkarılamayan görsel, "
                    "şema veya boş sayfa. Özgün kaynak sayfa korunmuştur."
                )
                method = f"LOCAL_OCR_VISUAL_ONLY:{LOCAL_OCR_ENGINE_VERSION}:CONF_{result.confidence}"
            upsert_page_checkpoint(
                session,
                owner_user_id=job.owner_user_id,
                course_id=job.course_id,
                material_id=job.material_id,
                index_version=job.index_version,
                page_number=page.page_number,
                status="OCR_DONE",
                text_content=text,
                extraction_method=method,
                content_sha256=_sha256_text(text),
                error=None,
            )
            session.commit()
    finally:
        if pdf_document is not None:
            pdf_document.close()
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
    from app.study_index_jobs import renew_index_lease
    rows = [SimpleNamespace(**row.model_dump()) for row in rows]
    for row in rows:
        if not renew_index_lease(session, job_id=job.id, lease_token=job.lease_token,
                                 worker_id=job.worker_id,
                                 lease_seconds=_int_env("STUDY_V2_LEASE_SECONDS", 180, 60, 1800)):
            session.rollback()
            return "LEASE_LOST"
        session.close()
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
        record_provider_success(session, provider_key)
        # The external call may outlive our lease. Re-check ownership before
        # persisting its result; otherwise a reclaimed stale worker could write.
        if not _lease_still_owned(session, job):
            session.rollback()
            return "LEASE_LOST"
        live = session.get(StudyIndexChunk, row.id)
        if live is None or live.index_version != job.index_version or live.text_sha256 != row.text_sha256:
            session.rollback()
            return "LEASE_LOST"
        row = live
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


@storage_scoped
def run_one_slice(
    session: Session,
    *,
    identity: str | None = None,
    resource_class: str = "NORMAL",
) -> str:
    """Claim and process at most one bounded unit. Returns a diagnostic state."""
    session.expire_on_commit = False
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

    import threading
    from app.study_index_jobs import renew_index_lease
    stop = threading.Event()
    bind = session.get_bind()
    def renew():
        while not stop.wait(max(10, lease_seconds // 3)):
            try:
                with Session(bind) as heartbeat_session:
                    if not renew_index_lease(heartbeat_session, job_id=job.id,
                            lease_token=job.lease_token, worker_id=job.worker_id,
                            lease_seconds=lease_seconds):
                        return
            except Exception:
                logger.exception("Index heartbeat failed job=%s", job.id)
    thread = threading.Thread(target=renew, daemon=True, name="dental-index-heartbeat")
    thread.start()
    try:
        return _run_claimed_slice(session, job, resource_class)
    finally:
        stop.set()
        thread.join(6)


def _run_claimed_slice(session, job, resource_class):
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

        session.close()
        path = storage_ensure_local(material[3])
        mime_type = material[4] or ""
        stage = (job.stage or "PREPARE").upper()

        # Never mix artifacts generated by two OCR/embedding profiles. This is
        # especially important when migrating a paused remote-OCR generation to
        # local OCR: discard only the unpublished generation and replay it.
        current_fingerprint = _index_fingerprint()
        if stage != "PREPARE" and job.index_fingerprint != current_fingerprint:
            restarted = restart_build_for_profile_change(
                session,
                job_id=job.id,
                lease_token=job.lease_token,
                worker_id=job.worker_id,
            )
            return "RESTARTED:PROFILE_CHANGED" if restarted else "LEASE_LOST"

        # PREPARE establishes immutable identity. Every later slice reuses it;
        # if the R2/local source or indexing configuration changes mid-build,
        # the generation fails instead of mixing incompatible artifacts.
        if stage == "PREPARE":
            expected_pages = len(PdfReader(str(path)).pages) if mime_type == "application/pdf" else 1
            source_sha = _sha256_file(path)
            fingerprint = current_fingerprint
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
                require_embeddings=False,
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
                require_embeddings=False,
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
            defer_index_job(
                session,
                job_id=job.id,
                lease_token=job.lease_token,
                worker_id=job.worker_id,
                reason="OCR_REQUIRED",
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
