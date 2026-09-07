from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from pypdf import PdfReader, PdfWriter
from sqlmodel import Field, Session, SQLModel, select

from app.study_provider import (
    StudyProviderError,
    get_embedding_dimensions,
    get_embedding_target,
    get_provider,
)

logger = logging.getLogger(__name__)


class StudyRAGError(RuntimeError):
    pass


class StudyRAGChunk(SQLModel, table=True):
    """Persistent per-course retrieval unit.

    Embeddings are stored as provider-neutral JSON so SQLite development and
    PostgreSQL production use the same data model. A pgvector/Qdrant/Pinecone
    backend can be added later without changing Academic AI's retrieval contract.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    course_id: int = Field(index=True)
    material_id: int = Field(index=True)
    material_sha256: str = Field(index=True)
    source_name: str
    page_number: Optional[int] = Field(default=None, index=True)
    chunk_index: int = 0
    content_kind: str = Field(index=True)  # PDF_PAGE, IMAGE, TEXT
    text_content: Optional[str] = None
    embedding_provider: str = Field(index=True)
    embedding_model: str = Field(index=True)
    embedding_dimensions: int = 768
    embedding_json: str
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class StudyRAGMemory(SQLModel, table=True):
    """Semantic memory for older exchanges within one user's one course."""

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    course_id: int = Field(index=True)
    user_text: str
    assistant_text: str
    embedding_provider: str = Field(index=True)
    embedding_model: str = Field(index=True)
    embedding_dimensions: int = 768
    embedding_json: str
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


@dataclass
class StudyRAGResult:
    note_context: list[str]
    memory_context: list[str]
    attachments: list[dict]
    source_material_ids: list[int]
    used_semantic_search: bool


DENTAL_TERMS = {
    "dis", "diş", "dental", "odontoloji", "odontology", "stomatoloji",
    "anatomi", "fizyoloji", "histoloji", "embriyoloji", "biyokimya",
    "mikrobiyoloji", "patoloji", "farmakoloji", "genetik", "biyofizik",
    "biyoistatistik", "epidemiyoloji", "ilk yardim", "ilk yardım",
    "deontoloji", "etik", "halk sagligi", "halk sağlığı", "enfeksiyon",
    "restoratif", "endodonti", "endodontics", "periodontoloji",
    "periodontology", "protetik", "protez", "prosthodontics", "pedodonti",
    "pediatrik dis", "ortodonti", "orthodontics", "okluzyon", "oklüzyon",
    "oral diagnoz", "oral radyoloji", "radyoloji", "agiz dis cene",
    "ağız diş çene", "cene cerrahisi", "çene cerrahisi", "oral cerrahi",
    "maksillofasiyal", "temporomandibular", "tme", "implantoloji",
    "anestezi", "lokal anestezi", "dis morfolojisi", "diş morfolojisi",
    "preklinik", "klinik", "karyoloji", "kariyoloji", "gerodontoloji",
    "oral patoloji", "oral medicine", "agiz hastaliklari", "ağız hastalıkları",
    "periodonsiyum", "sefalometri", "malokluzyon", "maloklüzyon",
}

CLEAR_NON_DENTAL_TERMS = {
    "matematik", "geometri", "fizik 1", "fizik 2", "termodinamik",
    "mukavemet", "statik", "dinamik", "makine", "elektrik devreleri",
    "programlama", "algoritma", "yazilim", "yazılım", "veri yapilari",
    "veri yapıları", "muhasebe", "finans", "iktisat", "ekonomi",
    "pazarlama", "isletme", "işletme", "anayasa", "medeni hukuk",
    "ceza hukuku", "sosyoloji", "turk tarihi", "türk tarihi",
    "edebiyat", "cografya", "coğrafya", "ingiliz edebiyati",
    "ingilizce", "turk dili", "türk dili", "ataturk ilkeleri", "atatürk ilkeleri",
    "inşaat", "insaat", "mimarlik", "mimarlık", "harita muhendisligi",
    "harita mühendisliği", "otomotiv", "kimya muhendisligi",
    "kimya mühendisliği",
}

BROAD_COMMAND_TERMS = {
    "ozetle", "özetle", "ozet", "özet", "anlat", "ogret", "öğret",
    "bana ogret", "bana öğret", "soru hazirla", "soru hazırla",
    "sorular hazirla", "sorular hazırla", "sinav", "sınav", "quiz",
    "onemli yerler", "önemli yerler", "kritik yerler", "calistir", "çalıştır",
}

SOURCE_REQUEST_TERMS = {
    "kaynak", "kaynaklar", "hangi not", "hangi dosya", "sayfa", "sayfası",
    "sayfasi", "nerede geçiyor", "nerede geciyor", "alıntı", "alinti",
}

VISUAL_QUERY_TERMS = {
    "görsel", "gorsel", "şema", "sema", "grafik", "tablo", "çizim", "cizim",
    "işaret", "isaret", "resim", "fotoğraf", "fotograf", "şekil", "sekil",
}

STOP_WORDS = {
    "ve", "veya", "ile", "bir", "bu", "su", "şu", "icin", "için",
    "olan", "olarak", "daha", "cok", "çok", "bana", "buradan", "burayi",
    "burayı", "lutfen", "lütfen", "hazirla", "hazırla", "anlat", "ozetle",
    "özetle", "soru", "sorular", "ders", "not", "notlar", "pdf",
}


def _normalize(text: str) -> str:
    value = (text or "").lower()
    replacements = {
        "ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return re.sub(r"[^a-z0-9\s]", " ", value)


def _tokens(text: str) -> set[str]:
    return {
        token for token in _normalize(text).split()
        if len(token) >= 2 and token not in {_normalize(x) for x in STOP_WORDS}
    }


def classify_course_scope(title: str, filenames: list[str] | None = None) -> str:
    """DENTAL, NON_DENTAL or UNKNOWN without consuming an AI request.

    UNKNOWN stays usable because dental faculties have local/elective course
    names that cannot be safely enumerated. Clearly unrelated courses are
    blocked before retrieval/generation.
    """
    text = " ".join([title or "", *(filenames or [])])
    normalized = _normalize(text)
    dental = {_normalize(term) for term in DENTAL_TERMS}
    non_dental = {_normalize(term) for term in CLEAR_NON_DENTAL_TERMS}

    if any(term and term in normalized for term in dental):
        return "DENTAL"
    if any(term and term in normalized for term in non_dental):
        return "NON_DENTAL"
    return "UNKNOWN"


def is_broad_study_request(query: str) -> bool:
    normalized = _normalize(query)
    has_command = any(_normalize(term) in normalized for term in BROAD_COMMAND_TERMS)
    topical = _tokens(query)
    return has_command and len(topical) <= 4


def _wants_source_details(query: str) -> bool:
    normalized = _normalize(query)
    return any(_normalize(term) in normalized for term in SOURCE_REQUEST_TERMS)


def _needs_visual_attachment(query: str) -> bool:
    normalized = _normalize(query)
    return any(_normalize(term) in normalized for term in VISUAL_QUERY_TERMS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _vector_to_json(vector: list[float]) -> str:
    return json.dumps([round(float(value), 7) for value in vector], separators=(",", ":"))


def _vector_from_json(value: str) -> list[float]:
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    try:
        return [float(item) for item in parsed]
    except (TypeError, ValueError):
        return []


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def _lexical_score(query: str, text: str) -> float:
    q = _tokens(query)
    if not q:
        return 0.0
    t = _tokens(text)
    if not t:
        return 0.0
    overlap = len(q.intersection(t))
    return min(1.0, overlap / max(1, min(len(q), 8)))


def _pdf_page_bytes(reader: PdfReader, page_index: int) -> bytes:
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _extract_page_text(page) -> str:
    try:
        text = page.extract_text() or ""
    except Exception:
        return ""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:18000]


def _existing_current_chunks(
    session: Session,
    *,
    owner_user_id: int,
    course_id: int,
    material_id: int,
    material_hash: str,
    provider_name: str,
    model_name: str,
) -> list[StudyRAGChunk]:
    return session.exec(
        select(StudyRAGChunk)
        .where(StudyRAGChunk.owner_user_id == owner_user_id)
        .where(StudyRAGChunk.course_id == course_id)
        .where(StudyRAGChunk.material_id == material_id)
        .where(StudyRAGChunk.material_sha256 == material_hash)
        .where(StudyRAGChunk.embedding_provider == provider_name)
        .where(StudyRAGChunk.embedding_model == model_name)
    ).all()


def ensure_material_index(session: Session, material) -> int:
    """Index a material exactly once per bytes+embedding model combination."""
    if not material.id:
        raise StudyRAGError("Ders notu kaydı tamamlanmamış.")
    path = Path(material.file_path)
    if not path.is_file():
        raise StudyRAGError(f"Not dosyası sunucuda bulunamadı: {material.display_name}")

    target = get_embedding_target()
    dimensions = get_embedding_dimensions()

    # StudyMaterial files are immutable through the application: changing a note
    # creates a new material row. Therefore a ready index for this material/model
    # can be reused without rereading and hashing the entire PDF on every question.
    quick_current = session.exec(
        select(StudyRAGChunk)
        .where(StudyRAGChunk.owner_user_id == material.owner_user_id)
        .where(StudyRAGChunk.course_id == material.course_id)
        .where(StudyRAGChunk.material_id == material.id)
        .where(StudyRAGChunk.embedding_provider == target.provider)
        .where(StudyRAGChunk.embedding_model == target.model)
    ).all()
    if quick_current and path.stat().st_size == material.size_bytes:
        return len(quick_current)

    material_hash = _sha256(path)
    current = _existing_current_chunks(
        session,
        owner_user_id=material.owner_user_id,
        course_id=material.course_id,
        material_id=material.id,
        material_hash=material_hash,
        provider_name=target.provider,
        model_name=target.model,
    )
    if current:
        return len(current)

    try:
        provider = get_provider(target.provider)
    except StudyProviderError as exc:
        raise StudyRAGError(str(exc)) from exc

    pending: list[StudyRAGChunk] = []
    mime_type = material.mime_type

    try:
        if mime_type == "application/pdf":
            reader = PdfReader(str(path))
            max_pages = max(1, int(os.getenv("STUDY_RAG_MAX_PDF_PAGES", "300")))
            if len(reader.pages) > max_pages:
                raise StudyRAGError(
                    f"{material.display_name} {len(reader.pages)} sayfa. Tek PDF için RAG sınırı {max_pages} sayfa."
                )
            for page_index, page in enumerate(reader.pages):
                page_number = page_index + 1
                extracted_text = _extract_page_text(page)
                page_bytes = _pdf_page_bytes(reader, page_index)
                if provider.supports_binary_embedding("application/pdf"):
                    vector = provider.embed_binary(
                        model=target.model,
                        data=page_bytes,
                        mime_type="application/pdf",
                        dimensions=dimensions,
                    )
                    kind = "PDF_PAGE"
                elif extracted_text:
                    vector = provider.embed_text(
                        model=target.model,
                        text=(
                            "Diş hekimliği ders materyalinde arama için bu sayfayı temsil et:\n"
                            + extracted_text
                        ),
                        dimensions=dimensions,
                    )
                    kind = "TEXT"
                else:
                    logger.warning(
                        "RAG provider cannot index visual-only PDF page. provider=%s file=%s page=%s",
                        target.provider,
                        material.display_name,
                        page_number,
                    )
                    continue
                pending.append(StudyRAGChunk(
                    owner_user_id=material.owner_user_id,
                    course_id=material.course_id,
                    material_id=material.id,
                    material_sha256=material_hash,
                    source_name=material.display_name,
                    page_number=page_number,
                    chunk_index=page_index,
                    content_kind=kind,
                    text_content=extracted_text or None,
                    embedding_provider=target.provider,
                    embedding_model=target.model,
                    embedding_dimensions=len(vector),
                    embedding_json=_vector_to_json(vector),
                ))
        elif mime_type and mime_type.startswith("image/"):
            data = path.read_bytes()
            if provider.supports_binary_embedding(mime_type):
                vector = provider.embed_binary(
                    model=target.model,
                    data=data,
                    mime_type=mime_type,
                    dimensions=dimensions,
                )
            else:
                raise StudyRAGError(
                    f"Seçili RAG sağlayıcısı {mime_type} görsellerini indeksleyemiyor."
                )
            pending.append(StudyRAGChunk(
                owner_user_id=material.owner_user_id,
                course_id=material.course_id,
                material_id=material.id,
                material_sha256=material_hash,
                source_name=material.display_name,
                page_number=1,
                chunk_index=0,
                content_kind="IMAGE",
                text_content=None,
                embedding_provider=target.provider,
                embedding_model=target.model,
                embedding_dimensions=len(vector),
                embedding_json=_vector_to_json(vector),
            ))
        else:
            raise StudyRAGError(f"RAG bu dosya türünü desteklemiyor: {material.display_name}")
    except StudyRAGError:
        raise
    except StudyProviderError as exc:
        raise StudyRAGError(str(exc)) from exc
    except Exception as exc:
        logger.exception("Study RAG indexing failed: %s", material.display_name)
        raise StudyRAGError(f"{material.display_name} indekslenirken sorun oluştu.") from exc

    if not pending:
        raise StudyRAGError(f"{material.display_name} içinden indekslenebilir içerik alınamadı.")

    # Replace only after the new complete index is ready. Failed re-indexing never
    # destroys the previous usable index.
    old_rows = session.exec(
        select(StudyRAGChunk)
        .where(StudyRAGChunk.owner_user_id == material.owner_user_id)
        .where(StudyRAGChunk.course_id == material.course_id)
        .where(StudyRAGChunk.material_id == material.id)
    ).all()
    for row in old_rows:
        session.delete(row)
    for row in pending:
        session.add(row)
    session.commit()
    return len(pending)


def ensure_course_index(session: Session, materials: list) -> tuple[int, list[str]]:
    """Ensure every current material has a persistent index.

    One broken/new file does not invalidate already indexed material. If nothing
    in the course can be searched, the caller gets a clear error.
    """
    indexed = 0
    warnings: list[str] = []
    for material in materials:
        try:
            indexed += ensure_material_index(session, material)
        except StudyRAGError as exc:
            warnings.append(str(exc))
            logger.warning("Study RAG material skipped: %s", exc)

    owner = materials[0].owner_user_id if materials else None
    course = materials[0].course_id if materials else None
    target = get_embedding_target()
    if owner is not None and course is not None:
        usable = session.exec(
            select(StudyRAGChunk)
            .where(StudyRAGChunk.owner_user_id == owner)
            .where(StudyRAGChunk.course_id == course)
            .where(StudyRAGChunk.embedding_provider == target.provider)
            .where(StudyRAGChunk.embedding_model == target.model)
        ).all()
        if usable:
            return len(usable), warnings

    if warnings:
        raise StudyRAGError(warnings[0])
    raise StudyRAGError("Bu derste aranabilir bir not indeksi bulunmuyor.")


def course_index_ready(
    session: Session,
    *,
    owner_user_id: int,
    course_id: int,
    materials: list,
) -> bool:
    """Cheap readiness check; never hashes/re-embeds files during a user question."""
    material_ids = {
        int(material.id)
        for material in materials
        if getattr(material, "id", None)
    }
    if not material_ids:
        return False

    target = get_embedding_target()
    raw_indexed_ids = session.exec(
        select(StudyRAGChunk.material_id)
        .where(StudyRAGChunk.owner_user_id == owner_user_id)
        .where(StudyRAGChunk.course_id == course_id)
        .where(StudyRAGChunk.embedding_provider == target.provider)
        .where(StudyRAGChunk.embedding_model == target.model)
    ).all()
    indexed_material_ids: set[int] = set()
    for value in raw_indexed_ids:
        scalar = value[0] if isinstance(value, (tuple, list)) else value
        try:
            indexed_material_ids.add(int(scalar))
        except (TypeError, ValueError):
            continue
    return material_ids.issubset(indexed_material_ids)


def _history_enriched_query(query: str, recent_history: list[dict] | None) -> str:
    current = (query or "").strip()
    if len(_tokens(current)) >= 4 or not recent_history:
        return current
    previous = []
    for item in reversed(recent_history[-6:]):
        text = (item.get("content") or "").strip()
        if not text:
            continue
        previous.append(text[:900])
        if len(previous) >= 2:
            break
    if not previous:
        return current
    return current + "\nÖnceki konuşma bağlamı: " + " | ".join(reversed(previous))


def _rank_chunks(
    rows: list[StudyRAGChunk],
    *,
    query: str,
    query_vector: list[float] | None,
    broad: bool,
    limit: int,
) -> list[StudyRAGChunk]:
    scored: list[tuple[float, StudyRAGChunk]] = []
    for row in rows:
        vector_score = _cosine(query_vector or [], _vector_from_json(row.embedding_json))
        lexical = _lexical_score(query, f"{row.source_name} {row.text_content or ''}")
        score = (0.86 * vector_score + 0.14 * lexical) if query_vector else lexical
        scored.append((score, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    if not broad:
        selected: list[StudyRAGChunk] = []
        page_seen: set[tuple[int, int | None]] = set()
        for _, row in scored:
            key = (row.material_id, row.page_number)
            if key in page_seen:
                continue
            page_seen.add(key)
            selected.append(row)
            if len(selected) >= limit:
                break
        return selected

    # Broad commands like "özetle" or "20 soru hazırla" need coverage, not only
    # the semantically nearest page. Blend high-score pages with evenly-spaced
    # pages from every source.
    selected: list[StudyRAGChunk] = []
    seen_ids: set[int] = set()

    for _, row in scored[: max(limit, 6)]:
        if row.id is not None and row.id not in seen_ids:
            selected.append(row)
            seen_ids.add(row.id)
        if len(selected) >= max(4, limit // 2):
            break

    by_material: dict[int, list[StudyRAGChunk]] = {}
    for row in rows:
        by_material.setdefault(row.material_id, []).append(row)
    for group in by_material.values():
        group.sort(key=lambda row: (row.page_number or 0, row.chunk_index))
        slots = min(4, len(group))
        if slots <= 0:
            continue
        for slot in range(slots):
            index = round(slot * (len(group) - 1) / max(1, slots - 1))
            row = group[index]
            if row.id is not None and row.id not in seen_ids:
                selected.append(row)
                seen_ids.add(row.id)
            if len(selected) >= limit:
                return selected

    for _, row in scored:
        if row.id is not None and row.id not in seen_ids:
            selected.append(row)
            seen_ids.add(row.id)
        if len(selected) >= limit:
            break
    return selected


def _rank_memories(
    rows: list[StudyRAGMemory],
    *,
    query: str,
    query_vector: list[float] | None,
    limit: int = 3,
) -> list[StudyRAGMemory]:
    scored = []
    for row in rows:
        text = f"{row.user_text}\n{row.assistant_text}"
        vector_score = _cosine(query_vector or [], _vector_from_json(row.embedding_json))
        lexical = _lexical_score(query, text)
        score = (0.9 * vector_score + 0.1 * lexical) if query_vector else lexical
        scored.append((score, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [row for score, row in scored[:limit] if score > 0.08 or query_vector]


def _material_map(materials: list) -> dict[int, object]:
    return {material.id: material for material in materials if material.id is not None}


def _page_attachment(material, page_number: int | None, *, show_source: bool = False) -> dict | None:
    path = Path(material.file_path)
    if not path.is_file():
        return None
    if material.mime_type == "application/pdf" and page_number:
        reader = PdfReader(str(path))
        index = page_number - 1
        if index < 0 or index >= len(reader.pages):
            return None
        data = _pdf_page_bytes(reader, index)
        label = (
            f"INTERNAL_SOURCE: {material.display_name} — sayfa {page_number}."
            if show_source
            else "INTERNAL_NOTE_PAGE: Kaynak ayrıntılarını kullanıcı istemedikçe açıklama."
        )
        return {
            "mime_type": "application/pdf",
            "data": data,
            "label": label,
        }
    if material.mime_type and material.mime_type.startswith("image/"):
        label = (
            f"INTERNAL_SOURCE: {material.display_name}."
            if show_source
            else "INTERNAL_NOTE_IMAGE: Kaynak ayrıntılarını kullanıcı istemedikçe açıklama."
        )
        return {
            "mime_type": material.mime_type,
            "data": path.read_bytes(),
            "label": label,
        }
    return None


def retrieve_course_context(

    session: Session,
    *,
    owner_user_id: int,
    course_id: int,
    query: str,
    materials: list,
    recent_history: list[dict] | None = None,
) -> StudyRAGResult:
    target = get_embedding_target()
    try:
        provider = get_provider(target.provider)
    except StudyProviderError as exc:
        raise StudyRAGError(str(exc)) from exc
    dimensions = get_embedding_dimensions()
    enriched_query = _history_enriched_query(query, recent_history)

    query_vector: list[float] | None = None
    try:
        query_vector = provider.embed_text(
            model=target.model,
            text=(
                "Diş hekimliği ders notlarında bu öğrenci isteğini yanıtlamaya en ilgili içeriği bul:\n"
                + enriched_query
            ),
            dimensions=dimensions,
        )
    except StudyProviderError as exc:
        # Retrieval remains available with lexical/diversity fallback if the
        # embedding endpoint is temporarily rate-limited.
        logger.warning("RAG query embedding unavailable; lexical fallback: %s", exc)

    rows = session.exec(
        select(StudyRAGChunk)
        .where(StudyRAGChunk.owner_user_id == owner_user_id)
        .where(StudyRAGChunk.course_id == course_id)
        .where(StudyRAGChunk.embedding_provider == target.provider)
        .where(StudyRAGChunk.embedding_model == target.model)
    ).all()
    if not rows:
        raise StudyRAGError("Bu dersin RAG indeksi henüz hazır değil.")

    broad = is_broad_study_request(query)
    try:
        normal_top_k = int(os.getenv("STUDY_RAG_TOP_K", "6"))
        broad_top_k = int(os.getenv("STUDY_RAG_BROAD_TOP_K", "10"))
        normal_max_attachments = int(os.getenv("STUDY_RAG_MAX_ATTACHMENTS", "1"))
        broad_max_attachments = int(os.getenv("STUDY_RAG_BROAD_MAX_ATTACHMENTS", "2"))
        max_context_chars = int(os.getenv("STUDY_RAG_MAX_CONTEXT_CHARS", "14000"))
    except ValueError:
        normal_top_k, broad_top_k = 6, 10
        normal_max_attachments, broad_max_attachments, max_context_chars = 1, 2, 14000
    limit = broad_top_k if broad else normal_top_k
    max_attachments = broad_max_attachments if broad else normal_max_attachments
    wants_sources = _wants_source_details(query)
    needs_visual = _needs_visual_attachment(query)

    selected = _rank_chunks(
        rows,
        query=enriched_query,
        query_vector=query_vector,
        broad=broad,
        limit=max(3, limit),
    )

    material_lookup = _material_map(materials)
    note_context: list[str] = []
    attachments: list[dict] = []
    total_chars = 0
    source_material_ids: list[int] = []
    attachment_keys: set[tuple[int, int | None]] = set()

    for index, row in enumerate(selected, start=1):
        if row.material_id not in source_material_ids:
            source_material_ids.append(row.material_id)
        if wants_sources:
            label = f"INTERNAL_SOURCE_{index}: {row.source_name}"
            if row.page_number:
                label += f" | sayfa {row.page_number}"
        else:
            label = f"INTERNAL_NOTE_SECTION_{index}"
        if row.text_content:
            block = f"{label}\n{row.text_content}"
            if total_chars + len(block) <= max_context_chars:
                note_context.append(block)
                total_chars += len(block)

        material = material_lookup.get(row.material_id)
        key = (row.material_id, row.page_number)
        if (
            material
            and len(attachments) < max_attachments
            and key not in attachment_keys
            and row.content_kind in {"PDF_PAGE", "IMAGE"}
            and (row.content_kind == "IMAGE" or not row.text_content or needs_visual)
        ):
            try:
                attachment = _page_attachment(material, row.page_number, show_source=wants_sources)
            except Exception:
                logger.exception("Could not build RAG attachment: material=%s page=%s", row.material_id, row.page_number)
                attachment = None
            if attachment:
                attachments.append(attachment)
                attachment_keys.add(key)

    semantic_memory_enabled = (
        os.getenv("STUDY_RAG_SEMANTIC_MEMORY", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    memory_context: list[str] = []
    if semantic_memory_enabled:
        memories = session.exec(
            select(StudyRAGMemory)
            .where(StudyRAGMemory.owner_user_id == owner_user_id)
            .where(StudyRAGMemory.course_id == course_id)
            .where(StudyRAGMemory.embedding_provider == target.provider)
            .where(StudyRAGMemory.embedding_model == target.model)
            .order_by(StudyRAGMemory.id.desc())
        ).all()
        memories = memories[:120]
        selected_memories = _rank_memories(
            memories,
            query=enriched_query,
            query_vector=query_vector,
            limit=2,
        )
        memory_context = [
            "Önceki ilgili çalışma konuşması:\n"
            f"Öğrenci: {row.user_text[:1400]}\n"
            f"Dental AI: {row.assistant_text[:2200]}"
            for row in selected_memories
        ]

    if not note_context and not attachments:
        raise StudyRAGError("Soruyla ilişkilendirilebilecek ders notu bölümü bulunamadı.")

    return StudyRAGResult(
        note_context=note_context,
        memory_context=memory_context,
        attachments=attachments,
        source_material_ids=source_material_ids,
        used_semantic_search=query_vector is not None,
    )


def remember_exchange(
    session: Session,
    *,
    owner_user_id: int,
    course_id: int,
    user_text: str,
    assistant_text: str,
) -> bool:
    """Index one completed exchange once; failure never hides the AI answer."""
    target = get_embedding_target()
    dimensions = get_embedding_dimensions()
    try:
        provider = get_provider(target.provider)
        memory_text = (
            "Diş hekimliği öğrencisinin aynı ders içindeki çalışma konuşması:\n"
            f"Öğrenci: {user_text[:2400]}\n"
            f"Asistan: {assistant_text[:4200]}"
        )
        vector = provider.embed_text(
            model=target.model,
            text=memory_text,
            dimensions=dimensions,
        )
        session.add(StudyRAGMemory(
            owner_user_id=owner_user_id,
            course_id=course_id,
            user_text=user_text[:4000],
            assistant_text=assistant_text[:7000],
            embedding_provider=target.provider,
            embedding_model=target.model,
            embedding_dimensions=len(vector),
            embedding_json=_vector_to_json(vector),
        ))
        session.commit()
    except Exception as exc:
        logger.warning("Study RAG memory indexing skipped: %s", exc)
        return False

    # Keep semantic history useful but bounded. Normal chat rows remain untouched.
    rows = session.exec(
        select(StudyRAGMemory)
        .where(StudyRAGMemory.owner_user_id == owner_user_id)
        .where(StudyRAGMemory.course_id == course_id)
        .order_by(StudyRAGMemory.id.desc())
    ).all()
    for old in rows[300:]:
        session.delete(old)
    if len(rows) > 300:
        session.commit()
    return True


def delete_material_rag_index(session: Session, *, owner_user_id: int, course_id: int, material_id: int) -> None:
    rows = session.exec(
        select(StudyRAGChunk)
        .where(StudyRAGChunk.owner_user_id == owner_user_id)
        .where(StudyRAGChunk.course_id == course_id)
        .where(StudyRAGChunk.material_id == material_id)
    ).all()
    for row in rows:
        session.delete(row)


def delete_course_rag_index(session: Session, *, owner_user_id: int, course_id: int) -> None:
    chunks = session.exec(
        select(StudyRAGChunk)
        .where(StudyRAGChunk.owner_user_id == owner_user_id)
        .where(StudyRAGChunk.course_id == course_id)
    ).all()
    memories = session.exec(
        select(StudyRAGMemory)
        .where(StudyRAGMemory.owner_user_id == owner_user_id)
        .where(StudyRAGMemory.course_id == course_id)
    ).all()
    for row in [*chunks, *memories]:
        session.delete(row)


def delete_course_rag_memory(session: Session, *, owner_user_id: int, course_id: int) -> None:
    rows = session.exec(
        select(StudyRAGMemory)
        .where(StudyRAGMemory.owner_user_id == owner_user_id)
        .where(StudyRAGMemory.course_id == course_id)
    ).all()
    for row in rows:
        session.delete(row)
