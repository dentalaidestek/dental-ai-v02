"""PostgreSQL-native hybrid retrieval for Academic AI V2.

Only published generations are visible. Lexical and semantic candidates are
ranked independently in PostgreSQL and combined with reciprocal-rank fusion so
their incomparable raw scores never need brittle hand tuning.
"""
from __future__ import annotations
from app.object_cache import scoped as storage_scoped


import io
import logging
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field

from pypdf import PdfReader, PdfWriter
from sqlalchemy import text
from sqlmodel import Session

from app.object_storage import ensure_local as storage_ensure_local
from app.dental_retrieval_terms import DENTAL_ALIAS_GROUPS
from app.dental_knowledge_graph import graph_expansion_terms
from app.dental_query_intent import classify_dental_intent, classify_dental_intents, combined_relation_hints
from app.dental_semantics import DentalSemanticFeatures, analyze_dental_text, semantic_overlap_score

logger = logging.getLogger(__name__)

_PAGE_PDF_CACHE_LOCK = threading.Lock()
_PAGE_PDF_CACHE: "OrderedDict[tuple[str, int], bytes]" = OrderedDict()
_PAGE_PDF_CACHE_MAX = 24

_FOLLOWUP_RE = re.compile(
    r"^(?:peki|tamam|devam|neden|nasıl|hangisi|bunu|burada|onu|o zaman|"
    r"daha (?:basit|detaylı)|açıkla|tekrar|\d+\.? soru)",
    re.IGNORECASE,
)
_VISUAL_QUERY_RE = re.compile(
    r"\b(?:tablo|tablodaki|şekil|grafik|görsel|görüntü|resim|fotoğraf|şema|"
    r"radyografi|radyografide|röntgen|film|panoramik|OPG|CBCT|periapikal|"
    r"bitewing|sefalometrik|sefalogram)\b", re.I
)
_EXHAUSTIVE_QUESTION_RE = re.compile(r"(?:tüm|bütün|hepsi|tamamı|dosyadaki|pdf.deki).{0,48}(?:soru|test)|(?:soru|test).{0,48}(?:çöz|cevapla|yanıtla)", re.I)


@dataclass(frozen=True)
class Evidence:
    chunk_id: int
    material_id: int
    display_name: str
    page_start: int
    page_end: int
    section_title: str | None
    content_kind: str
    text: str
    lexical_rank: int | None
    semantic_rank: int | None
    hybrid_score: float
    chunk_index: int = 0


@dataclass
class RetrievalResult:
    evidence: list[Evidence] = field(default_factory=list)
    note_context: list[str] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)
    source_material_ids: list[int] = field(default_factory=list)
    resolved_query: str = ""
    used_semantic_search: bool = False
    retrieval_mode: str = "hybrid"
    has_more: bool = False
    evidence_sufficient: bool = False
    evidence_confidence: float = 0.0
    covered_facets: tuple[str, ...] = ()
    missing_facets: tuple[str, ...] = ()


def resolve_followup_query(query: str, recent_history: list[dict] | None) -> str:
    """Add conversational referents only for short/clearly dependent turns."""
    clean = re.sub(r"\s+", " ", query or "").strip()
    if not clean or not recent_history:
        return clean
    # Short does not mean dependent: "SNA nedir?" or "ANB kaçtır?" are
    # self-contained dental questions. Pull history in only when the wording
    # itself contains a conversational referent.
    dependent = bool(_FOLLOWUP_RE.search(clean))
    if not dependent:
        return clean
    previous: list[str] = []
    for item in reversed(recent_history[-6:]):
        content = re.sub(r"\s+", " ", item.get("content") or "").strip()
        if content:
            previous.append(content[:700])
        if len(previous) >= 2:
            break
    if not previous:
        return clean
    return clean + "\nÖnceki bağlam: " + " | ".join(reversed(previous))


def _single_page_pdf(reference: str, page_number: int) -> bytes:
    # Repeated visual questions often hit the same source page. Avoid reparsing
    # a large PDF on every request; keep a small process-local byte cache only.
    cache_key = (str(reference), int(page_number))
    with _PAGE_PDF_CACHE_LOCK:
        cached = _PAGE_PDF_CACHE.get(cache_key)
        if cached is not None:
            _PAGE_PDF_CACHE.move_to_end(cache_key)
            return cached

    path = storage_ensure_local(reference)
    reader = PdfReader(str(path))
    try:
        if page_number < 1 or page_number > len(reader.pages):
            raise ValueError("page outside source")
        writer = PdfWriter()
        writer.add_page(reader.pages[page_number - 1])
        output = io.BytesIO()
        writer.write(output)
        data = output.getvalue()
    finally:
        stream = getattr(reader, "stream", None)
        if stream and hasattr(stream, "close"):
            stream.close()

    with _PAGE_PDF_CACHE_LOCK:
        _PAGE_PDF_CACHE[cache_key] = data
        _PAGE_PDF_CACHE.move_to_end(cache_key)
        while len(_PAGE_PDF_CACHE) > _PAGE_PDF_CACHE_MAX:
            _PAGE_PDF_CACHE.popitem(last=False)
    return data


def _pgvector_available(session: Session, dimensions: int) -> bool:
    if dimensions != 768:
        return False
    row = session.exec(text(
        "SELECT to_regtype('vector') IS NOT NULL AND EXISTS ("
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='studyindexchunk' AND column_name='embedding_vector')"
    )).one()
    return bool(row[0])


_DENTAL_CONCEPT_GROUPS = DENTAL_ALIAS_GROUPS

_DENTAL_NOTATION_RULES = (
    (re.compile(r"\bA\s*[-–]?\s*N\s*[-–]?\s*B\b", re.I), "ANB"),
    (re.compile(r"\bS\s*[-–]?\s*N\s*[-–]?\s*A\b", re.I), "SNA"),
    (re.compile(r"\bS\s*[-–]?\s*N\s*[-–]?\s*B\b", re.I), "SNB"),
    (re.compile(r"\bGo\s*[-–]?\s*Gn\b", re.I), "GoGn"),
)


def _normalize_dental_notation(query: str) -> str:
    clean = re.sub(r"\s+", " ", query or "").strip()
    for pattern, canonical in _DENTAL_NOTATION_RULES:
        clean = pattern.sub(canonical, clean)
    return clean

def _query_term_present(text: str, term: str) -> bool:
    clean_term = " ".join((term or "").casefold().split())
    if not clean_term:
        return False
    words = clean_term.split()
    # Turkish lecture questions naturally inflect long concept words
    # (çene -> çenenin, geriliği -> geriliğini). For multi-word concepts,
    # allow a bounded alphabetic suffix on substantial words while keeping
    # short aliases/abbreviations such as CR, PD, ANB exact.
    if len(words) > 1:
        pieces = []
        for word in words:
            escaped_word = re.escape(word)
            if len(word) >= 4 and word.isalpha():
                escaped_word += r"[a-zçğıöşü]{0,6}"
            pieces.append(escaped_word)
        escaped = r"\s+".join(pieces)
    else:
        escaped = re.escape(clean_term)
    return bool(re.search(r"(?<!\w)" + escaped + r"(?!\w)", text, flags=re.I))


def _concept_alternatives(query: str) -> list[str]:
    lowered = re.sub(r"\s+", " ", query or "").strip().casefold()
    extras: list[str] = []
    for group in _DENTAL_CONCEPT_GROUPS:
        matched = [term for term in group if _query_term_present(lowered, term)]
        if not matched:
            continue
        for term in group:
            if not _query_term_present(lowered, term) and term not in extras:
                extras.append(term)
    return extras

_QUERY_NOISE_RE = re.compile(
    r"\b(?:nedir|ne demek|açıkla|anlat|kaçtır|hangisi|hangileridir|nelerdir|"
    r"nedendir|neden|nasıl|göre|hakkında|bilgi|ver|söyle|ders notunda|notlarda)\b",
    re.I,
)


def _retrieval_terms(query: str) -> tuple[list[str], list[str]]:
    """Return precise source terms and bounded dental alternatives."""
    clean = _normalize_dental_notation(query)
    core = re.sub(_QUERY_NOISE_RE, " ", clean)
    core = re.sub(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü+./'-]+", " ", core)
    core = re.sub(r"\s+", " ", core).strip(" ?.,;:")
    original = [token for token in core.split() if len(token) >= 2][:10]
    lowered = clean.casefold()
    extras = _concept_alternatives(clean)
    intents = classify_dental_intents(clean)
    for term in graph_expansion_terms(clean, relation_hints=combined_relation_hints(intents)):
        if term.casefold() not in {item.casefold() for item in extras}:
            extras.append(term)
    return original, extras[:16]


_EVIDENCE_FACETS = {
    "diagnosis": ("tanı", "klinik bulgu", "radyografik bulgu", "ayırıcı tanı", "test"),
    "treatment": ("tedavi", "prosedür", "endikasyon", "kontrendikasyon", "komplikasyon"),
    "complication": ("komplikasyon", "risk", "neden", "önleme"),
    "classification": ("sınıflama", "evre", "grade", "kriter"),
    "cause": ("etiyoloji", "risk faktörü", "mekanizma", "patogenez"),
    "measurement": ("ölçüm", "referans", "normal değer", "değerlendirme"),
    "value": ("normal değer", "ölçüm", "referans"),
    "anatomy": ("anatomi", "komşuluk", "ilişki", "konum"),
    "visual": ("radyografik bulgu", "görüntü", "şekil", "tablo"),
    "comparison": ("fark", "avantaj", "dezavantaj", "endikasyon"),
    "indication": ("endikasyon", "kullanım", "durum"),
    "contraindication": ("kontrendikasyon", "sakınca", "kullanılmaz"),
}


def _evidence_queries(query: str, *, max_queries: int = 4) -> list[str]:
    """Build a few focused evidence queries instead of one giant OR expression."""
    clean = _normalize_dental_notation(query)
    original, extras = _retrieval_terms(clean)
    intents = classify_dental_intents(clean)
    anchors = original[:5]
    # Prefer canonical multi-word/graph terms, but keep the user's subject words.
    concept_terms = [term for term in extras if len(term) >= 3][:4]
    subject = " ".join(dict.fromkeys(anchors + concept_terms[:1])).strip()
    if not subject:
        subject = clean
    queries: list[str] = []
    # Multi-intent questions share one bounded query budget. Give every explicit
    # requirement one evidence probe before spending remaining probes on depth.
    facet_groups = [_EVIDENCE_FACETS.get(intent.name, ()) for intent in intents]
    for depth in range(max((len(group) for group in facet_groups), default=0)):
        for group in facet_groups:
            if depth >= len(group):
                continue
            facet = group[depth]
            candidate = f'{subject} "{facet}"' if " " in facet else f"{subject} {facet}"
            if candidate not in queries:
                queries.append(candidate)
            if len(queries) >= max_queries:
                return queries
    return queries


def _fts_query(query: str, *, broad: bool = False) -> str:
    original, extras = _retrieval_terms(query)
    terms = original + (extras if broad else [])
    # websearch_to_tsquery supports explicit OR. Quoting keeps multiword dental
    # alternatives such as "root canal" together.
    unique: list[str] = []
    for term in terms:
        if term.casefold() not in {x.casefold() for x in unique}:
            unique.append(term)
    if not unique:
        return re.sub(r"\s+", " ", query or "").strip()
    if broad:
        return " OR ".join(f'"{term}"' if " " in term else term for term in unique)
    return " ".join(unique)


def _fts_rows(
    session: Session,
    *,
    owner_user_id: int,
    course_id: int,
    lexical_query: str,
    query_vector: list[float] | None,
    embedding_provider: str,
    embedding_model: str,
    limit: int,
) -> list:
    candidate_limit = max(20, min(120, limit * 8))
    common = """
        FROM studyindexchunk c
        JOIN studymaterial m
          ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
         AND m.active_index_version=c.index_version
         AND m.index_status='READY' AND m.deleted_at IS NULL
        WHERE c.owner_user_id=:owner AND c.course_id=:course
    """
    if query_vector:
        dimensions = len(query_vector)
        if _pgvector_available(session, dimensions):
            semantic_score = "1 - (c.embedding_vector <=> CAST(:vector_literal AS vector))"
            semantic_where = """
                AND c.embedding_vector IS NOT NULL
                AND c.embedding_provider=:embedding_provider
                AND c.embedding_model=:embedding_model
                AND c.embedding_dimensions=:embedding_dimensions
            """
            vector_params = {"vector_literal": "[" + ",".join(str(float(x)) for x in query_vector) + "]"}
        else:
            semantic_score = """
                (SELECT SUM(e.value*q.value) /
                    NULLIF(SQRT(SUM(e.value*e.value))*SQRT(SUM(q.value*q.value)), 0)
                 FROM unnest(c.embedding_array) WITH ORDINALITY AS e(value, ord)
                 JOIN unnest(CAST(:query_vector AS DOUBLE PRECISION[])) WITH ORDINALITY AS q(value, ord)
                   ON q.ord=e.ord)
            """
            semantic_where = """
                AND c.embedding_array IS NOT NULL
                AND c.embedding_provider=:embedding_provider
                AND c.embedding_model=:embedding_model
                AND c.embedding_dimensions=:embedding_dimensions
            """
            vector_params = {"query_vector": query_vector}
        semantic_cte = f"""
            semantic AS (
                SELECT c.id, {semantic_score} AS raw_score,
                       ROW_NUMBER() OVER (ORDER BY {semantic_score} DESC, c.id) AS rank
                {common} {semantic_where}
                ORDER BY raw_score DESC, c.id
                LIMIT :candidate_limit
            ),
        """
        semantic_union = "UNION SELECT id FROM semantic"
        semantic_columns = "s.rank AS semantic_rank, s.raw_score AS semantic_score,"
        semantic_join = "LEFT JOIN semantic s ON s.id=c.id"
        semantic_fusion = "COALESCE(1.0/(60+s.rank), 0)"
    else:
        semantic_cte = ""
        semantic_union = ""
        semantic_columns = "NULL AS semantic_rank, NULL AS semantic_score,"
        semantic_join = ""
        semantic_fusion = "0"
        vector_params = {}

    sql = f"""
        WITH lexical AS (
            SELECT c.id,
                   (
                     ts_rank_cd(
                       to_tsvector('simple', coalesce(c.section_title, '') || ' ' || c.text_content || ' ' || coalesce(c.retrieval_terms, '')),
                       websearch_to_tsquery('simple', :lexical_query)
                     )
                     + CASE WHEN lower(coalesce(c.section_title,'')) LIKE lower(:title_like) THEN 0.20 ELSE 0 END
                   ) AS raw_score,
                   ROW_NUMBER() OVER (ORDER BY
                     (
                       ts_rank_cd(
                         to_tsvector('simple', coalesce(c.section_title, '') || ' ' || c.text_content || ' ' || coalesce(c.retrieval_terms, '')),
                         websearch_to_tsquery('simple', :lexical_query)
                       )
                       + CASE WHEN lower(coalesce(c.section_title,'')) LIKE lower(:title_like) THEN 0.20 ELSE 0 END
                     ) DESC, c.id) AS rank
            {common}
              AND to_tsvector('simple', coalesce(c.section_title, '') || ' ' || c.text_content || ' ' || coalesce(c.retrieval_terms, ''))
                  @@ websearch_to_tsquery('simple', :lexical_query)
            ORDER BY raw_score DESC, c.id
            LIMIT :candidate_limit
        ),
        {semantic_cte}
        candidates AS (
            SELECT id FROM lexical
            {semantic_union}
        )
        SELECT c.id, c.material_id, m.display_name, c.page_start, c.page_end,
               c.section_title, c.content_kind, c.text_content,
               l.rank AS lexical_rank, l.raw_score AS lexical_score,
               {semantic_columns}
               (COALESCE(1.0/(60+l.rank), 0) + {semantic_fusion}) AS hybrid_score,
               c.chunk_index, c.semantic_json
        FROM candidates x
        JOIN studyindexchunk c ON c.id=x.id
        JOIN studymaterial m ON m.id=c.material_id
        LEFT JOIN lexical l ON l.id=c.id
        {semantic_join}
        ORDER BY hybrid_score DESC, c.page_start ASC, c.id ASC
        LIMIT :limit
    """
    params = {
        "owner": owner_user_id,
        "course": course_id,
        "lexical_query": lexical_query,
        "title_like": "%" + " ".join(_retrieval_terms(lexical_query)[0][:3]) + "%",
        "candidate_limit": candidate_limit,
        "limit": max(1, min(limit, 20)),
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "embedding_dimensions": len(query_vector) if query_vector else 0,
        **vector_params,
    }
    return list(session.exec(text(sql), params=params).all())


def _is_exhaustive_question_request(query: str) -> bool:
    clean = re.sub(r"\s+", " ", query or "").strip()
    return bool(clean and _EXHAUSTIVE_QUESTION_RE.search(clean))


def _continuation_cursor(query: str, recent_history: list[dict] | None) -> tuple[int, int] | None:
    """Read an internal continuation marker from the prior assistant turn only."""
    if not recent_history or not re.match(r"^(?:devam|devam et|kalan(?:ları)?|sonraki(?:ler)?)\b", (query or "").strip(), re.I):
        return None
    last = recent_history[-1]
    if str(last.get("role") or "").upper() != "ASSISTANT":
        return None
    match = re.search(r"<!--ACADEMIC_Q_CURSOR:(\d+):(\d+)-->", last.get("content") or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def _question_rows(
    session: Session, *, owner_user_id: int, course_id: int,
    limit: int = 16, after_cursor: tuple[int, int] | None = None,
) -> list:
    """Return likely question-bearing chunks in source order, not semantic top-k."""
    return list(session.exec(text(
        """
        SELECT c.id, c.material_id, m.display_name, c.page_start, c.page_end,
               c.section_title, c.content_kind, c.text_content,
               NULL::BIGINT AS lexical_rank, NULL::DOUBLE PRECISION AS lexical_score,
               NULL::BIGINT AS semantic_rank, NULL::DOUBLE PRECISION AS semantic_score,
               1.0::DOUBLE PRECISION AS hybrid_score, c.chunk_index
        FROM studyindexchunk c
        JOIN studymaterial m
          ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
         AND m.active_index_version=c.index_version
         AND m.index_status='READY' AND m.deleted_at IS NULL
        WHERE c.owner_user_id=:owner AND c.course_id=:course
          AND (
            :after_material_id IS NULL
            OR c.material_id > :after_material_id
            OR (c.material_id = :after_material_id AND c.chunk_index > :after_chunk_index)
          )
          AND (
            c.content_kind = 'QUESTION'
            OR c.text_content ~* :question_pattern
            OR lower(coalesce(c.section_title, '')) ~ '(soru|test|quiz|değerlendirme)'
          )
        ORDER BY c.material_id, c.page_start, c.chunk_index, c.id
        LIMIT :limit
        """
    ), params={
        "owner": owner_user_id,
        "course": course_id,
        "after_material_id": after_cursor[0] if after_cursor else None,
        "after_chunk_index": after_cursor[1] if after_cursor else None,
        "question_pattern": r"(^|\n)\s*((soru\s*)?[0-9]{1,3}[.)]|[A-E][.)])\s+",
        "limit": max(1, min(limit, 32)) + 1,
    }).all())


def _academic_question_rows(
    session: Session, *, owner_user_id: int, course_id: int, limit: int = 32,
) -> list:
    """Bounded QUESTION evidence for academic study tasks; always owner/course scoped."""
    return _question_rows(
        session, owner_user_id=owner_user_id, course_id=course_id,
        limit=max(1, min(limit, 32)), after_cursor=None,
    )


def _neighbor_rows(
    session: Session,
    *,
    owner_user_id: int,
    course_id: int,
    seed_ids: list[int],
    exclude_ids: list[int],
    limit: int = 4,
) -> list:
    if not seed_ids:
        return []
    return list(session.exec(text(
        """
        WITH seed_order AS (
            SELECT id, ord FROM unnest(CAST(:seed_ids AS BIGINT[])) WITH ORDINALITY AS x(id, ord)
        ), seeds AS (
            SELECT c.id, c.material_id, c.index_version, c.chunk_index,
                   c.page_start, s.ord
            FROM seed_order s JOIN studyindexchunk c ON c.id=s.id
        ), neighbors AS (
            SELECT DISTINCT ON (c.id)
                   c.id, c.material_id, m.display_name, c.page_start, c.page_end,
                   c.section_title, c.content_kind, c.text_content,
                   NULL::BIGINT AS lexical_rank, NULL::DOUBLE PRECISION AS lexical_score,
                   NULL::BIGINT AS semantic_rank, NULL::DOUBLE PRECISION AS semantic_score,
                   (0.001 / seeds.ord)::DOUBLE PRECISION AS hybrid_score,
                   c.chunk_index, c.semantic_json,
                   seeds.ord AS seed_order
            FROM seeds
            JOIN studyindexchunk c
              ON c.material_id=seeds.material_id AND c.index_version=seeds.index_version
             AND (ABS(c.chunk_index-seeds.chunk_index)=1 OR ABS(c.page_start-seeds.page_start)=1)
            JOIN studymaterial m
              ON m.id=c.material_id AND m.owner_user_id=:owner
             AND m.active_index_version=c.index_version
             AND m.index_status='READY' AND m.deleted_at IS NULL
            WHERE c.owner_user_id=:owner AND c.course_id=:course
              AND NOT (c.id = ANY(CAST(:exclude_ids AS BIGINT[])))
            ORDER BY c.id, seeds.ord, ABS(c.page_start-seeds.page_start), ABS(c.chunk_index-seeds.chunk_index)
        )
        SELECT id, material_id, display_name, page_start, page_end, section_title,
               content_kind, text_content, lexical_rank, lexical_score,
               semantic_rank, semantic_score, hybrid_score, chunk_index, semantic_json
        FROM neighbors ORDER BY seed_order, page_start, id LIMIT :limit
        """
    ), params={
        "seed_ids": seed_ids,
        "exclude_ids": exclude_ids or [-1],
        "owner": owner_user_id,
        "course": course_id,
        "limit": max(0, min(limit, 8)),
    }).all())



def _subject_alignment_score(query: str, section: str, body: str) -> float:
    """Local query-subject coverage independent of generic intent words."""
    original, _ = _retrieval_terms(query)
    if not original:
        return 0.0
    haystack = f"{section or ''} {body or ''}".casefold()
    matched = sum(1 for term in original[:6] if _query_term_present(haystack, term))
    lexical = matched / max(1, min(len(original), 6))

    query_features = analyze_dental_text(query)
    row_features = analyze_dental_text(f"{section or ''}\n{body or ''}")
    concept = 0.0
    if set(query_features.node_ids).intersection(row_features.node_ids):
        concept += 0.55
    if set(query_features.tooth_numbers).intersection(row_features.tooth_numbers):
        concept += 0.25
    if set(query_features.imaging_types).intersection(row_features.imaging_types):
        concept += 0.20
    return min(1.0, max(lexical, concept))


@storage_scoped
def _rerank_dental_rows(query: str, rows: list, *, limit: int) -> list:
    """Rerank a bounded lexical candidate pool with local dental semantics."""
    if not rows:
        return []
    query_features = analyze_dental_text(query)
    scored = []
    for position, row in enumerate(rows):
        section = row[5] or ""
        body = row[7] or ""
        features = analyze_dental_text(f"{section}\n{body}")
        # New generations persist the same deterministic fingerprint; legacy
        # rows safely fall back to local text analysis above.
        if len(row) > 13 and row[-1]:
            try:
                import json
                meta = json.loads(row[-1])
                features = type(features)(
                    node_ids=tuple(meta.get("nodes") or ()),
                    specialties=tuple(meta.get("specialties") or ()),
                    kinds=tuple(meta.get("kinds") or ()),
                    measurements=tuple(meta.get("measurements") or ()),
                    tooth_numbers=tuple(meta.get("teeth") or ()),
                    imaging_types=tuple(meta.get("imaging") or ()),
                )
            except (TypeError, ValueError, KeyError):
                pass
        semantic = semantic_overlap_score(query_features, features)
        # Rows can come from several focused DB queries. Their append position is
        # not a relevance signal: a strong complication/diagnosis row may have
        # been discovered by a later facet query. Prefer PostgreSQL's lexical
        # score when present and use position only as a bounded tie/fallback.
        raw_lexical = float(row[9] or 0.0) if len(row) > 9 else 0.0
        lexical = min(1.0, max(0.0, raw_lexical))
        positional = 1.0 / (1.0 + position)
        if lexical <= 0.0:
            lexical = positional * 0.35
        subject_alignment = _subject_alignment_score(query, section, body)
        # Evidence must stay anchored to the user's subject. Dental semantics
        # helps aliases/graph concepts; subject alignment prevents a same-
        # specialty but unrelated facet from winning merely for saying
        # "complication", "treatment", etc.
        score = (
            (0.42 * lexical)
            + (0.33 * semantic)
            + (0.20 * subject_alignment)
            + (0.05 * positional)
        )
        scored.append((score, position, row))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [row for _, _, row in scored[:limit]]


_FAST_INTENTS = {"value", "definition", "measurement"}
_MULTI_EVIDENCE_INTENTS = {
    "diagnosis", "treatment", "complication", "classification",
    "cause", "comparison", "visual", "indication", "contraindication",
}


def _needs_multi_evidence(query: str) -> bool:
    intent = classify_dental_intent(query)
    if intent.name in _FAST_INTENTS:
        return False
    return intent.name in _MULTI_EVIDENCE_INTENTS


def _coverage_terms(intent_name: str) -> tuple[str, ...]:
    return _EVIDENCE_FACETS.get(intent_name, ())


def _coverage_score(query: str, rows: list) -> tuple[float, tuple[str, ...]]:
    """Cheap local sufficiency signal using lexical and persisted dental semantics."""
    intent = classify_dental_intent(query)
    facets = _coverage_terms(intent.name)
    if not facets:
        return (1.0 if rows else 0.0), ()
    corpus = " ".join(f"{row[5] or ''} {row[7] or ''}" for row in rows).casefold()
    semantic_kinds: set[str] = set()
    for row in rows:
        if len(row) > 13 and row[-1]:
            try:
                import json
                meta = json.loads(row[-1])
                semantic_kinds.update(str(item).casefold() for item in (meta.get("kinds") or ()))
            except (TypeError, ValueError, KeyError):
                pass
    covered: list[str] = []
    for facet in facets:
        facet_cf = facet.casefold()
        if facet_cf in corpus or facet_cf in semantic_kinds:
            covered.append(facet)
    # A strong intent-kind match is evidence even when the note uses a synonym
    # such as pulpectomy instead of literally saying "treatment".
    if intent.preferred_kinds and semantic_kinds.intersection(
        item.casefold() for item in intent.preferred_kinds
    ) and facets and facets[0] not in covered:
        covered.append(facets[0])
    return len(covered) / max(1, len(facets)), tuple(covered)


@dataclass(frozen=True)
class EvidenceSufficiency:
    sufficient: bool
    confidence: float
    covered_facets: tuple[str, ...]
    missing_facets: tuple[str, ...]


def _row_semantic_features(row) -> DentalSemanticFeatures:
    section = row[5] or ""
    body = row[7] or ""
    features = analyze_dental_text(f"{section}\n{body}")
    if len(row) > 14 and row[-1]:
        try:
            import json
            meta = json.loads(row[-1])
            return DentalSemanticFeatures(
                node_ids=tuple(meta.get("nodes") or ()),
                specialties=tuple(meta.get("specialties") or ()),
                kinds=tuple(meta.get("kinds") or ()),
                measurements=tuple(meta.get("measurements") or ()),
                tooth_numbers=tuple(meta.get("teeth") or ()),
                imaging_types=tuple(meta.get("imaging") or ()),
            )
        except (TypeError, ValueError, KeyError):
            pass
    return features


def _evidence_sufficiency(query: str, rows: list) -> EvidenceSufficiency:
    """Decide locally whether evidence is strong enough to spend the one AI call."""
    if not rows:
        return EvidenceSufficiency(False, 0.0, (), _coverage_terms(classify_dental_intent(query).name))

    intent = classify_dental_intent(query)
    qf = analyze_dental_text(query)
    facets = _coverage_terms(intent.name)
    coverage, covered = _coverage_score(query, rows)
    missing = tuple(facet for facet in facets if facet not in covered)

    alignments = sorted(
        (_subject_alignment_score(query, row[5] or "", row[7] or "") for row in rows),
        reverse=True,
    )
    best_alignment = alignments[0] if alignments else 0.0
    complementary_alignment = alignments[1] if len(alignments) > 1 else 0.0

    row_features = [_row_semantic_features(row) for row in rows]
    kinds = {item for features in row_features for item in features.kinds}
    intent_kind = 1.0 if set(intent.preferred_kinds).intersection(kinds) else 0.0

    special_match = 1.0
    if qf.tooth_numbers:
        special_match = 1.0 if any(
            set(qf.tooth_numbers).intersection(features.tooth_numbers) for features in row_features
        ) else 0.0
    if qf.imaging_types:
        special_match = min(special_match, 1.0 if any(
            set(qf.imaging_types).intersection(features.imaging_types) for features in row_features
        ) else 0.0)
    if intent.name in {"value", "measurement"}:
        has_measurement = any(features.measurements for features in row_features)
        # Measurement questions can still be answered textually ("SNA açısı")
        # when no numeric value is requested, so this is a confidence component,
        # not an unconditional hard failure.
        special_match = min(special_match, 1.0 if has_measurement else 0.45)

    facet_component = coverage if facets else 1.0
    confidence = min(1.0, (
        0.42 * best_alignment
        + 0.18 * complementary_alignment
        + 0.18 * intent_kind
        + 0.14 * facet_component
        + 0.08 * special_match
    ))

    # Hard anchors: a query with a known dental concept/tooth/image must have
    # at least one subject-aligned evidence row. Generic same-specialty text is
    # not enough to justify generation.
    has_specific_anchor = bool(qf.node_ids or qf.tooth_numbers or qf.imaging_types)
    anchored = best_alignment >= (0.34 if has_specific_anchor else 0.24)
    if intent.name in {"value", "definition", "measurement"}:
        sufficient = anchored and confidence >= 0.34
    elif facets:
        sufficient = anchored and confidence >= 0.38 and (coverage > 0.0 or intent_kind > 0.0)
    else:
        sufficient = anchored and confidence >= 0.34

    return EvidenceSufficiency(sufficient, confidence, covered, missing)


def _coverage_select(query: str, rows: list, *, limit: int) -> list:
    """Preserve evidence diversity after relevance reranking."""
    if len(rows) <= limit:
        return rows
    intent = classify_dental_intent(query)
    facets = _coverage_terms(intent.name)
    if not facets:
        return rows[:limit]
    selected: list = []
    selected_ids: set[int] = set()
    # First reserve at most one high-ranked chunk for each requested facet,
    # preferring evidence that also remains anchored to the query subject.
    for facet in facets:
        facet_cf = facet.casefold()
        candidates = []
        for row in rows:
            if int(row[0]) in selected_ids:
                continue
            haystack = f"{row[5] or ''} {row[7] or ''}".casefold()
            if facet_cf in haystack:
                candidates.append(row)
        if candidates:
            aligned = [
                row for row in candidates
                if _subject_alignment_score(query, row[5] or "", row[7] or "") >= 0.34
            ]
            chosen = (aligned or candidates)[0]
            selected.append(chosen)
            selected_ids.add(int(chosen[0]))
        if len(selected) >= limit:
            return selected
    # Fill remaining slots by global relevance order.
    for row in rows:
        if int(row[0]) not in selected_ids:
            selected.append(row)
            selected_ids.add(int(row[0]))
        if len(selected) >= limit:
            break
    return selected


def retrieve_course_context_v2(
    session: Session,
    *,
    owner_user_id: int,
    course_id: int,
    query: str,
    recent_history: list[dict] | None = None,
    limit: int = 8,
) -> RetrievalResult:
    if session.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Academic V2 hybrid retrieval requires PostgreSQL")
    resolved = resolve_followup_query(query, recent_history)
    # New V2 indexes are intentionally local-FTS. Do not spend an external
    # embedding request per user question when the published generation has no
    # semantic vectors to compare against.
    vector: list[float] | None = None
    # Current V2 retrieval is provider-free. These identity parameters are
    # intentionally blank while query_vector is None; _fts_rows keeps its
    # guarded legacy vector path for old indexed generations only.
    embedding_provider = ""
    embedding_model = ""
    continuation_cursor = _continuation_cursor(query, recent_history)
    study_task = classify_academic_study_task(query)
    exhaustive_questions = _is_exhaustive_question_request(query) or continuation_cursor is not None
    study_question_task = bool(
        study_task and study_task.requires_past_questions and not exhaustive_questions
    )
    if exhaustive_questions:
        question_limit = 16
        question_rows = _question_rows(
            session,
            owner_user_id=owner_user_id,
            course_id=course_id,
            limit=question_limit + 1,
            after_cursor=continuation_cursor,
        )
        # Fetch one sentinel row so continuation is truthful without loading
        # the rest of a large question bank.
        has_more_questions = len(question_rows) > question_limit
        rows = question_rows[:question_limit]
    elif study_question_task:
        # Past-question pattern tasks intentionally inspect QUESTION evidence
        # from this user's course only. They are not the exhaustive solve path
        # and never widen into another user's material.
        rows = _academic_question_rows(
            session, owner_user_id=owner_user_id, course_id=course_id, limit=32,
        )
        has_more_questions = False
    else:
        precise_query = _fts_query(resolved, broad=False)
        rows = _fts_rows(
            session,
            owner_user_id=owner_user_id,
            course_id=course_id,
            lexical_query=precise_query,
            query_vector=vector,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            limit=max(limit * 3, 18),
        )
        # Collect complementary evidence with a few focused facet queries.
        # This reaches distant pages/documents without exploding one giant OR query.
        candidate_target = max(limit * 4, 24)
        seen_ids = {int(row[0]) for row in rows}
        evidence_queries = _evidence_queries(resolved) if _needs_multi_evidence(resolved) else []
        for evidence_query in evidence_queries:
            if len(rows) >= candidate_target:
                break
            facet_rows = _fts_rows(
                session,
                owner_user_id=owner_user_id,
                course_id=course_id,
                lexical_query=evidence_query,
                query_vector=None,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                limit=max(4, min(8, candidate_target - len(rows))),
            )
            for row in facet_rows:
                row_id = int(row[0])
                if row_id not in seen_ids:
                    rows.append(row)
                    seen_ids.add(row_id)
        # If focused plans still found very little, retain one bounded graph/alias
        # fallback for recall. It is no longer the normal expansion path.
        if len(rows) < max(limit, 6):
            broad_query = _fts_query(resolved, broad=True)
            if broad_query and broad_query != precise_query:
                for row in _fts_rows(
                    session,
                    owner_user_id=owner_user_id,
                    course_id=course_id,
                    lexical_query=broad_query,
                    query_vector=None,
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                    limit=min(8, candidate_target - len(rows)),
                ):
                    row_id = int(row[0])
                    if row_id not in seen_ids:
                        rows.append(row)
                        seen_ids.add(row_id)
        rows = _rerank_dental_rows(resolved, rows, limit=max(limit * 2, 12))
        coverage, covered_facets = _coverage_score(resolved, rows)
        # At most one extra local DB query, only for complex questions whose
        # first pass lacks evidence diversity.
        if evidence_queries and coverage < 0.34 and len(rows) < candidate_target:
            missing = [
                facet for facet in _coverage_terms(classify_dental_intent(resolved).name)
                if facet not in covered_facets
            ]
            if missing:
                rescue_query = f'{_fts_query(resolved, broad=False)} "{missing[0]}"'
                for row in _fts_rows(
                    session,
                    owner_user_id=owner_user_id,
                    course_id=course_id,
                    lexical_query=rescue_query,
                    query_vector=None,
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                    limit=min(6, candidate_target - len(rows)),
                ):
                    row_id = int(row[0])
                    if row_id not in seen_ids:
                        rows.append(row)
                        seen_ids.add(row_id)
                rows = _rerank_dental_rows(resolved, rows, limit=max(limit * 2, 12))
        rows = _coverage_select(resolved, rows, limit=limit)
        primary_ids = [int(row[0]) for row in rows]
        rows.extend(_neighbor_rows(
            session,
            owner_user_id=owner_user_id,
            course_id=course_id,
            seed_ids=primary_ids[:4],
            exclude_ids=primary_ids,
            limit=min(4, max(0, 12 - len(rows))),
        ))
    intent = classify_dental_intent(resolved)
    logger.info(
        "Academic V2 retrieval selected. mode=%s intent=%s evidence_rows=%s",
        "questions_exhaustive" if exhaustive_questions else ("academic_question_patterns" if study_question_task else "fts"),
        intent.name,
        len(rows),
    )
    result = RetrievalResult(
        resolved_query=resolved,
        retrieval_mode="questions_exhaustive" if exhaustive_questions else ("academic_question_patterns" if study_question_task else "fts"),
        has_more=bool(exhaustive_questions and has_more_questions),
    )
    for row in rows:
        evidence = Evidence(
            chunk_id=int(row[0]), material_id=int(row[1]), display_name=row[2],
            page_start=int(row[3]), page_end=int(row[4]), section_title=row[5],
            content_kind=row[6], text=row[7],
            lexical_rank=int(row[8]) if row[8] is not None else None,
            semantic_rank=int(row[10]) if row[10] is not None else None,
            hybrid_score=float(row[12] or 0),
            chunk_index=int(row[13]) if len(row) > 13 and row[13] is not None else 0,
        )
        result.evidence.append(evidence)
        if evidence.semantic_rank is not None:
            result.used_semantic_search = True
        result.note_context.append(
            f"[KANIT material_id={evidence.material_id} sayfa={evidence.page_start} "
            f"bölüm={evidence.section_title or '-'} tür={evidence.content_kind}]\n{evidence.text}"
        )
        if evidence.material_id not in result.source_material_ids:
            result.source_material_ids.append(evidence.material_id)

    if exhaustive_questions or study_question_task:
        # Question-source study tasks use actual QUESTION evidence. Source-order
        # solving has continuation; pattern analysis is bounded separately.
        # Each emitted QUESTION chunk is itself an evidence unit.
        result.evidence_sufficient = bool(result.evidence)
        result.evidence_confidence = 1.0 if result.evidence else 0.0
    else:
        sufficiency = _evidence_sufficiency(resolved, rows)
        result.evidence_sufficient = sufficiency.sufficient
        result.evidence_confidence = sufficiency.confidence
        result.covered_facets = sufficiency.covered_facets
        result.missing_facets = sufficiency.missing_facets
        logger.info(
            "Academic V2 evidence sufficiency. sufficient=%s confidence=%.3f covered=%s missing=%s",
            result.evidence_sufficient,
            result.evidence_confidence,
            ",".join(result.covered_facets) or "-",
            ",".join(result.missing_facets) or "-",
        )

    visual_pages: list[tuple[int, int]] = []
    for item in result.evidence:
        if item.content_kind in {"TABLE", "VISUAL"} or _VISUAL_QUERY_RE.search(query or ""):
            key = (item.material_id, item.page_start)
            if key not in visual_pages:
                visual_pages.append(key)
        if len(visual_pages) >= 3:
            break
    if visual_pages:
        material_rows = session.exec(
            text("SELECT id, file_path, mime_type, display_name FROM studymaterial WHERE owner_user_id=:o AND id=ANY(:ids)"),
            params={"o": owner_user_id, "ids": [item[0] for item in visual_pages]},
        ).all()
        materials = {int(row[0]): row for row in material_rows}
        for material_id, page in visual_pages:
            material = materials.get(material_id)
            if not material:
                continue
            try:
                if material[2] == "application/pdf":
                    data = _single_page_pdf(material[1], page)
                elif str(material[2]).startswith("image/"):
                    data = storage_ensure_local(material[1]).read_bytes()
                else:
                    continue
            except Exception:
                logger.exception("Academic V2 visual page could not be prepared")
                continue
            result.attachments.append({
                "mime_type": material[2],
                "data": data,
                "label": f"INTERNAL_SOURCE: {material[3]}, sayfa {page}",
            })
    return result
