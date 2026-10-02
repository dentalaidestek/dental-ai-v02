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
from app.dental_knowledge_graph import graph_expansion_terms, node_label
from app.dental_query_intent import query_qualifiers, qualifier_present, build_dental_requirement_plan, classify_academic_study_task, classify_dental_study_plan, classify_dental_intents, combined_relation_hints
from app.academic_coverage import CoverageAccumulator, build_coverage_plan, cache_coverage_plan, cached_coverage_plan
from app.dental_semantics import DentalSemanticFeatures, analyze_dental_text, semantic_overlap_score

logger = logging.getLogger(__name__)

_PAGE_PDF_CACHE_LOCK = threading.Lock()
_PAGE_PDF_CACHE: "OrderedDict[tuple[str, int], bytes]" = OrderedDict()
_PAGE_PDF_CACHE_MAX = 24
_PAGE_PDF_MAX_BYTES = 8 * 1024 * 1024

_FOLLOWUP_RE = re.compile(
    r"^(?:peki|tamam|devam|bunu|bunun|burada|onu|onun|o zaman|peki ya|"
    r"ya bunda|ya bunun|bunlarda|bunların|"
    r"daha (?:basit|detaylı)|açıkla|tekrar|\d+\.? soru)",
    re.IGNORECASE,
)
_VISUAL_SOURCE_RE = re.compile(
    r"\b(?:bu|şu)\s+(?:tablo|şekil|grafik|görsel|görüntü|resim|fotoğraf|şema|"
    r"radyografi|röntgen|film|panoramik|OPG|CBCT|periapikal|bitewing|sefalogram)"
    r"|\b(?:tablodaki|şekildeki|grafikteki|görseldeki|görüntüdeki|resimdeki|"
    r"fotoğraftaki|radyografideki|filmdeki)\b"
    r"|\b(?:gösterilen|işaretli|okla\s+gösterilen|görülen)\b"
    r"|\b(?:tablo|şekil|grafik|görsel|görüntü|resim|fotoğraf|radyografi|film)"
    r"(?:de|da)\s+(?:ne|neyi|hangi|nerede)\b",
    re.I,
)

def _requires_visual_source(query: str) -> bool:
    """True only when answering requires inspecting source pixels/layout."""
    return bool(_VISUAL_SOURCE_RE.search(query or ""))

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


@dataclass(frozen=True)
class PastQuestionFingerprint:
    chunk_id: int
    material_id: int
    node_ids: tuple[str, ...]
    intents: tuple[str, ...]
    relation_hints: tuple[str, ...]
    question_format: str

    @property
    def canonical_key(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        # Wording is deliberately excluded: paraphrases of the same dental
        # concept + requested facet should land in the same exam pattern.
        return (self.node_ids, self.intents)


def _question_format(text_value: str) -> str:
    clean = text_value or ""
    if re.search(r"(?mi)^\s*[A-E][.)]\s+", clean):
        return "mcq"
    if re.search(r"(?i)\b(?:doğru|yanlış|true|false)\b", clean):
        return "true_false"
    return "open"


def fingerprint_past_question(row) -> PastQuestionFingerprint:
    body = str(row[7] or "")
    features = analyze_dental_text(body)
    intents = classify_dental_intents(body)
    intent_names = tuple(i.name for i in intents if i.name != "general") or ("general",)
    return PastQuestionFingerprint(
        chunk_id=int(row[0]),
        material_id=int(row[1]),
        node_ids=tuple(sorted(set(features.node_ids))),
        intents=intent_names,
        relation_hints=combined_relation_hints(intents),
        question_format=_question_format(body),
    )


def repeated_question_patterns(rows: list, *, minimum_distinct_questions: int = 2) -> list[dict]:
    """Group paraphrased QUESTION chunks by canonical dental concept + intent.

    A pattern is never called repeated from one question. Distinct chunk ids are
    required; material diversity is reported separately instead of fabricated.
    """
    groups: dict[tuple, list[PastQuestionFingerprint]] = {}
    for row in rows:
        fp = fingerprint_past_question(row)
        # Generic questions without a recognized dental concept are too weak to
        # support a "repeated topic" claim.
        if not fp.node_ids:
            continue
        groups.setdefault(fp.canonical_key, []).append(fp)
    output: list[dict] = []
    for key, items in groups.items():
        chunk_ids = sorted({x.chunk_id for x in items})
        if len(chunk_ids) < max(2, minimum_distinct_questions):
            continue
        output.append({
            "node_ids": key[0],
            "intents": key[1],
            "question_count": len(chunk_ids),
            "material_count": len({x.material_id for x in items}),
            "formats": tuple(sorted({x.question_format for x in items})),
            "chunk_ids": tuple(chunk_ids),
        })
    output.sort(key=lambda x: (-x["question_count"], -x["material_count"], x["node_ids"]))
    return output


@dataclass
class RetrievalResult:
    evidence: list[Evidence] = field(default_factory=list)
    note_context: list[str] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)
    # Deferred visual sources keep retrieval DB-only. Endpoint/generation
    # materializes these after the retrieval transaction is closed.
    visual_sources: list[dict] = field(default_factory=list)
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
    """Resolve dependent turns from prior USER subject identity, never answer prose."""
    clean = re.sub(r"\s+", " ", query or "").strip()
    if not clean or not recent_history or not _FOLLOWUP_RE.search(clean):
        return clean

    # A conversational marker can still introduce a new explicit subject
    # ("peki SNB nedir?"). Explicit current graph identity always wins.
    current_plan = build_dental_requirement_plan(clean)
    if current_plan.subject_node_ids:
        return clean

    # Inspect only a bounded recent window and only USER turns. Assistant
    # answers may mention distractor diagnoses, measurements or treatments and
    # must never become retrieval subject identity.
    for item in reversed(recent_history[-8:]):
        if str(item.get("role") or "").casefold() not in {"user", "human"}:
            continue
        content = re.sub(r"\s+", " ", item.get("content") or "").strip()
        if not content:
            continue
        # A prior dependent USER turn ("peki tedavisi?") does not carry
        # trustworthy standalone subject identity; keep scanning to the last
        # self-contained user turn instead of inheriting its lexical residue.
        if _FOLLOWUP_RE.search(content):
            prior_current = build_dental_requirement_plan(content[:700])
            if not prior_current.subject_node_ids:
                continue
        prior = build_dental_requirement_plan(content[:700])
        if not prior.subject_terms:
            continue
        # Inherit subject + its explicit modifiers only. Prior intent/facet is
        # intentionally discarded; the current turn defines what is requested.
        # Current-turn qualifiers override incompatible inherited axes:
        # "alt sağ ... -> peki üstte?" must not become "alt sağ üst ...".
        current_qualifiers = set(query_qualifiers(clean))
        inherited_qualifiers = list(prior.qualifiers)
        qualifier_axes = (
            {"üst", "alt", "maksiller", "mandibular"},
            {"sağ", "sol"},
            {"anterior", "posterior"},
            {"süt", "daimi"},
            {"akut", "kronik"},
            {"reversible", "irreversible"},
            {"semptomatik", "asemptomatik"},
            {"lokalize", "generalize"},
            {"çocuk", "erişkin"},
        )
        blocked: set[str] = set()
        for axis in qualifier_axes:
            if current_qualifiers.intersection(axis):
                blocked.update(axis)
        inherited_qualifiers = [q for q in inherited_qualifiers if q not in blocked]
        inherited = " ".join(dict.fromkeys((*inherited_qualifiers, *prior.subject_terms))).strip()
        if inherited:
            return f"{inherited} — {clean}"
    return clean


def _extract_single_page_pdf(*, reference: str, page_number: int) -> bytes:
    """Pure storage/PDF phase: no database access and no open DB transaction."""
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
        if len(data) > _PAGE_PDF_MAX_BYTES:
            raise ValueError("visual page artifact exceeds bounded size")
        return data
    finally:
        stream = getattr(reader, "stream", None)
        if stream and hasattr(stream, "close"):
            stream.close()


def materialize_visual_sources(session_factory, result: RetrievalResult) -> None:
    """DB read -> no-DB storage I/O -> short compare-and-set DB write."""
    if not result.visual_sources or not result.evidence_sufficient:
        return
    for source in result.visual_sources[:3]:
        cache_key = (
            f"{source['owner_user_id']}:{source['material_id']}:{source.get('index_version')}:{source.get('reference')}",
            int(source["page_number"]),
        )
        with _PAGE_PDF_CACHE_LOCK:
            cached = _PAGE_PDF_CACHE.get(cache_key)
            if cached is not None:
                _PAGE_PDF_CACHE.move_to_end(cache_key)
        if cached is not None:
            result.attachments.append({
                "mime_type": source["mime_type"], "data": cached,
                "label": f"INTERNAL_SOURCE: {source['display_name']}, sayfa {source['page_number']}",
            })
            continue

        with session_factory() as read_session:
            row = read_session.exec(
                text(
                    "SELECT m.file_path, m.mime_type, m.display_name, m.active_index_version, p.visual_pdf_bytes "
                    "FROM studymaterial m LEFT JOIN studyindexpage p ON "
                    "p.owner_user_id=m.owner_user_id AND p.material_id=m.id "
                    "AND p.index_version=m.active_index_version AND p.page_number=:p "
                    "WHERE m.id=:m AND m.owner_user_id=:o AND m.deleted_at IS NULL"
                ),
                params={"m": source["material_id"], "o": source["owner_user_id"], "p": source["page_number"]},
            ).first()
        if not row:
            continue
        live_version = str(row[3]) if row[3] else None
        if live_version != source.get("index_version"):
            continue
        try:
            if row[4]:
                data = bytes(row[4])
            elif row[1] == "application/pdf":
                if not live_version:
                    continue
                data = _extract_single_page_pdf(reference=row[0], page_number=source["page_number"])
                with session_factory() as write_session:
                    updated = write_session.exec(
                        text(
                            "UPDATE studyindexpage SET visual_pdf_bytes=:data "
                            "WHERE owner_user_id=:o AND material_id=:m AND index_version=:v "
                            "AND page_number=:p AND visual_pdf_bytes IS NULL "
                            "AND EXISTS (SELECT 1 FROM studymaterial sm WHERE sm.id=:m "
                            "AND sm.owner_user_id=:o AND sm.deleted_at IS NULL "
                            "AND sm.active_index_version=:v)"
                        ),
                        params={"data": data, "o": source["owner_user_id"], "m": source["material_id"],
                                "v": live_version, "p": source["page_number"]},
                    )
                    if getattr(updated, "rowcount", 0):
                        write_session.commit()
                    else:
                        write_session.rollback()
            elif str(row[1]).startswith("image/"):
                data = storage_ensure_local(row[0]).read_bytes()
                if len(data) > _PAGE_PDF_MAX_BYTES:
                    continue
            else:
                continue
        except Exception:
            logger.exception("Academic V2 deferred visual source could not be prepared")
            continue
        with _PAGE_PDF_CACHE_LOCK:
            _PAGE_PDF_CACHE[cache_key] = data
            _PAGE_PDF_CACHE.move_to_end(cache_key)
            while len(_PAGE_PDF_CACHE) > _PAGE_PDF_CACHE_MAX:
                _PAGE_PDF_CACHE.popitem(last=False)
        result.attachments.append({
            "mime_type": row[1], "data": data,
            "label": f"INTERNAL_SOURCE: {row[2]}, sayfa {source['page_number']}",
        })
    if not result.attachments:
        result.evidence_sufficient = False
        result.evidence_confidence = 0.0


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
    # websearch_to_tsquery joins bare terms with AND. Generic facet words in the
    # primary query can therefore hide the correct subject chunk when the answer
    # is split across adjacent chunks. Subject retrieval stays precise; facets
    # are enforced by coverage and, if needed, the single bounded rescue.
    facet_noise = {
        term.casefold()
        for values in _FACET_SEARCH_TERMS.values()
        for term in values
    } if "_FACET_SEARCH_TERMS" in globals() else set()
    subject_only = [term for term in original if term.casefold() not in facet_noise]
    if subject_only:
        original = subject_only
    lowered = clean.casefold()
    extras = _concept_alternatives(clean)
    intents = classify_dental_intents(clean)
    for term in graph_expansion_terms(clean, relation_hints=combined_relation_hints(intents)):
        if term.casefold() not in {item.casefold() for item in extras}:
            extras.append(term)
    return original, extras[:16]


_EVIDENCE_FACETS = {
    # These are requirements, not synonym lists. One explicit user intent maps
    # to one canonical coverage facet; related concepts must not become hidden
    # requirements or extra DB probes.
    "diagnosis": ("tanı",),
    "treatment": ("tedavi",),
    "complication": ("komplikasyon",),
    "classification": ("sınıflama",),
    "cause": ("etiyoloji",),
    "measurement": ("ölçüm",),
    "value": ("normal değer",),
    "anatomy": ("anatomi",),
    "visual": ("radyografik bulgu",),
    "comparison": ("fark",),
    "indication": ("endikasyon",),
    "contraindication": ("kontrendikasyon",),
}

_FACET_SEARCH_TERMS = {
    "tanı": ("tanı", "teşhis", "diagnosis", "diagnostic", "test"),
    "tedavi": ("tedavi", "treatment", "terapi", "therapy", "prosedür"),
    "komplikasyon": ("komplikasyon", "complication", "risk", "advers"),
    "sınıflama": ("sınıflama", "classification", "evre", "grade", "kriter"),
    "etiyoloji": ("etiyoloji", "etiology", "neden", "cause", "patogenez"),
    "ölçüm": ("ölçüm", "measurement", "değer", "value", "referans"),
    "normal değer": ("normal değer", "normal value", "referans", "reference"),
    "anatomi": ("anatomi", "anatomy", "komşuluk", "konum"),
    "radyografik bulgu": ("radyografik", "radiographic", "görüntü", "imaging"),
    "fark": ("fark", "difference", "karşılaştır", "compare"),
    "endikasyon": ("endikasyon", "indication", "kullanım"),
    "kontrendikasyon": ("kontrendikasyon", "contraindication", "sakınca"),
}


def _facet_present(facet: str, corpus: str, semantic_kinds: set[str]) -> bool:
    terms = _FACET_SEARCH_TERMS.get(facet, (facet,))
    if any(term.casefold() in corpus for term in terms):
        return True
    return any(term.casefold() in semantic_kinds for term in terms)


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


def _coverage_metadata_page(
    session: Session, *, owner_user_id: int, course_id: int,
    after_id: int = 0, limit: int = 240,
) -> list:
    """Read only lightweight coverage metadata; never chunk text."""
    return list(session.exec(text("""
        SELECT c.id, c.material_id, m.display_name, c.page_start, c.page_end,
               c.section_title, c.content_kind, '' AS text_content,
               NULL::BIGINT, NULL::DOUBLE PRECISION, NULL::BIGINT, NULL::DOUBLE PRECISION,
               1.0::DOUBLE PRECISION, c.chunk_index, c.semantic_json
        FROM studyindexchunk c
        JOIN studymaterial m
          ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
         AND m.active_index_version=c.index_version
         AND m.index_status='READY' AND m.deleted_at IS NULL
        WHERE c.owner_user_id=:owner AND c.course_id=:course
          AND c.id > :after_id AND c.content_kind <> 'QUESTION'
        ORDER BY c.id
        LIMIT :limit
    """), params={
        "owner": owner_user_id, "course": course_id, "after_id": after_id,
        "limit": max(1, min(limit, 400)),
    }).all())


def _course_index_fingerprint(session: Session, *, owner_user_id: int, course_id: int) -> str:
    """Cheap invalidation token from the course's published material generations."""
    row = session.exec(text("""
        SELECT COALESCE(string_agg(
            m.id::text || ':' || COALESCE(m.active_index_version::text, '0'),
            ',' ORDER BY m.id
        ), '')
        FROM studymaterial m
        WHERE m.owner_user_id=:owner AND m.course_id=:course
          AND m.index_status='READY' AND m.deleted_at IS NULL
    """), params={"owner": owner_user_id, "course": course_id}).one()
    return str(row[0] or "")


def get_or_build_coverage_plan(
    session: Session, *, owner_user_id: int, course_id: int,
    requested_count: int, page_size: int = 240,
):
    fingerprint = _course_index_fingerprint(
        session, owner_user_id=owner_user_id, course_id=course_id,
    )
    cached = cached_coverage_plan(owner_user_id, course_id, fingerprint, requested_count)
    if cached is not None:
        return cached

    accumulator = CoverageAccumulator()
    after_id = 0
    bounded_page_size = max(40, min(int(page_size), 400))
    while True:
        page = _coverage_metadata_page(
            session, owner_user_id=owner_user_id, course_id=course_id,
            after_id=after_id, limit=bounded_page_size,
        )
        if not page:
            break
        accumulator.add_rows(page)
        after_id = int(page[-1][0])
        if len(page) < bounded_page_size:
            break
    plan = accumulator.build(requested_count)
    cache_coverage_plan(owner_user_id, course_id, fingerprint, plan)
    return plan


def _coverage_evidence_rows(
    session: Session, *, owner_user_id: int, course_id: int,
    chunk_ids: list[int], limit: int = 24,
) -> list:
    """Hydrate text only for planner-selected chunks."""
    if not chunk_ids:
        return []
    return list(session.exec(text("""
        SELECT c.id, c.material_id, m.display_name, c.page_start, c.page_end,
               c.section_title, c.content_kind, c.text_content,
               NULL::BIGINT, NULL::DOUBLE PRECISION, NULL::BIGINT, NULL::DOUBLE PRECISION,
               1.0::DOUBLE PRECISION, c.chunk_index, c.semantic_json
        FROM studyindexchunk c
        JOIN studymaterial m
          ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
         AND m.active_index_version=c.index_version
         AND m.index_status='READY' AND m.deleted_at IS NULL
        WHERE c.owner_user_id=:owner AND c.course_id=:course
          AND c.id = ANY(CAST(:chunk_ids AS BIGINT[]))
          AND c.content_kind <> 'QUESTION'
        ORDER BY c.material_id, c.page_start, c.chunk_index, c.id
        LIMIT :limit
    """), params={
        "owner": owner_user_id, "course": course_id,
        "chunk_ids": chunk_ids, "limit": max(1, min(limit, 48)),
    }).all())


def _academic_question_rows(
    session: Session, *, owner_user_id: int, course_id: int, limit: int = 32,
) -> list:
    """Bounded QUESTION evidence for academic study tasks; always owner/course scoped."""
    return _question_rows(
        session, owner_user_id=owner_user_id, course_id=course_id,
        limit=max(1, min(limit, 32)), after_cursor=None,
    )


def _note_rows_for_question_patterns(
    session: Session, *, owner_user_id: int, course_id: int,
    question_rows: list, limit: int = 12,
    required_subject_ids: tuple[str, ...] = (),
) -> list:
    """Find factual note evidence for past-question patterns.

    QUESTION chunks define exam style/topic only. They are deliberately excluded
    from this evidence lookup so a past question cannot become its own answer
    source.
    """
    fingerprints = [fingerprint_past_question(row) for row in question_rows]
    node_ids = sorted({node for fp in fingerprints for node in fp.node_ids})
    if required_subject_ids:
        required = set(required_subject_ids)
        node_ids = [node for node in node_ids if node in required]
    if not node_ids:
        return []
    # Canonical node ids are persisted in semantic_json. JSON text matching is
    # bounded here and remains owner/course scoped; this avoids provider calls.
    clauses = " OR ".join(f"c.semantic_json LIKE :n{i}" for i in range(len(node_ids[:12])))
    params = {
        "owner": owner_user_id, "course": course_id,
        "limit": max(1, min(limit, 20)),
        **{f"n{i}": f'%"{node}"%' for i, node in enumerate(node_ids[:12])},
    }
    return list(session.exec(text(f"""
        SELECT c.id, c.material_id, m.display_name, c.page_start, c.page_end,
               c.section_title, c.content_kind, c.text_content,
               NULL::BIGINT, NULL::DOUBLE PRECISION, NULL::BIGINT, NULL::DOUBLE PRECISION,
               1.0::DOUBLE PRECISION, c.chunk_index, c.semantic_json
        FROM studyindexchunk c
        JOIN studymaterial m
          ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
         AND m.active_index_version=c.index_version
         AND m.index_status='READY' AND m.deleted_at IS NULL
        WHERE c.owner_user_id=:owner AND c.course_id=:course
          AND c.content_kind <> 'QUESTION'
          AND c.semantic_json IS NOT NULL
          AND ({clauses})
        ORDER BY c.material_id, c.page_start, c.chunk_index, c.id
        LIMIT :limit
    """), params=params).all())


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
                   c.page_start, c.section_title, s.ord
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
             AND c.section_title IS NOT DISTINCT FROM seeds.section_title
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



def _subject_alignment_score(
    query: str, section: str, body: str, *,
    query_features: DentalSemanticFeatures | None = None,
    row_features: DentalSemanticFeatures | None = None,
) -> float:
    """Local query-subject coverage independent of generic intent words."""
    original, _ = _retrieval_terms(query)
    if not original:
        return 0.0
    haystack = f"{section or ''} {body or ''}".casefold()
    matched = sum(1 for term in original[:6] if _query_term_present(haystack, term))
    lexical = matched / max(1, min(len(original), 6))

    query_features = query_features or analyze_dental_text(query)
    row_features = row_features or analyze_dental_text(f"{section or ''}\n{body or ''}")
    concept = 0.0
    if set(query_features.node_ids).intersection(row_features.node_ids):
        concept += 0.55
    if set(query_features.tooth_numbers).intersection(row_features.tooth_numbers):
        concept += 0.25
    if set(query_features.imaging_types).intersection(row_features.imaging_types):
        concept += 0.20
    return min(1.0, max(lexical, concept))


@storage_scoped
def _rerank_dental_rows(query: str, rows: list, *, limit: int, requirement=None, feature_cache=None, query_features=None) -> list:
    """Rerank a bounded lexical candidate pool with local dental semantics."""
    if not rows:
        return []
    query_features = query_features or analyze_dental_text(query)
    requirement = requirement or build_dental_requirement_plan(query)
    required_qualifiers = set(requirement.qualifiers)
    scored = []
    for position, row in enumerate(rows):
        section = row[5] or ""
        body = row[7] or ""
        # READY chunks normally carry persisted semantic metadata. Parse it
        # once; only legacy/corrupt rows fall back to text analysis.
        features = _row_semantic_features(row, feature_cache)
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
        subject_alignment = _subject_alignment_score(
            query, section, body, query_features=query_features, row_features=features,
        )
        # Evidence must stay anchored to the user's subject. Dental semantics
        # helps aliases/graph concepts; subject alignment prevents a same-
        # specialty but unrelated facet from winning merely for saying
        # "complication", "treatment", etc.
        # Subject identity is a gate, not merely another weak bonus. A row
        # reached through an alias/graph neighbour must not outrank a direct
        # subject hit just because it shares specialty or facet vocabulary.
        direct_subject = subject_alignment >= 0.50
        semantic_subject = semantic >= 0.45
        drift_penalty = 0.22 if not direct_subject and not semantic_subject else 0.0
        row_text_cf = f"{section} {body}".casefold()
        qualifier_hits = sum(1 for item in required_qualifiers if qualifier_present(item, row_text_cf))
        qualifier_score = qualifier_hits / len(required_qualifiers) if required_qualifiers else 1.0
        qualifier_penalty = 0.18 * (1.0 - qualifier_score) if required_qualifiers else 0.0
        # Prefer qualifiers attached to the subject actually present in this
        # evidence row. This avoids rewarding "alt" elsewhere in a comparison
        # when the row is evidence for the "üst" subject. It remains a soft
        # signal because a chunk boundary may separate a modifier from its fact.
        local_pairs = [
            (subject_id, qualifiers)
            for subject_id, qualifiers in requirement.subject_qualifiers
            if subject_id in features.node_ids
        ]
        if local_pairs:
            local_total = sum(len(qualifiers) for _, qualifiers in local_pairs)
            local_hits = sum(
                1 for _, qualifiers in local_pairs for item in qualifiers
                if qualifier_present(item, row_text_cf)
            )
            local_score = local_hits / max(1, local_total)
            qualifier_penalty = max(qualifier_penalty, 0.24 * (1.0 - local_score))
        # Negated facts are useful for a negation-seeking question, but can
        # invert an ordinary positive question. Keep this a bounded rerank
        # signal rather than a hard gate: many exam-style negative questions
        # are answerable from positive source statements.
        query_nodes = set(requirement.subject_node_ids)
        row_negated = set(features.negated_node_ids)
        negation_overlap = bool(query_nodes.intersection(row_negated))
        negation_adjustment = (
            0.06 if requirement.asks_negation and negation_overlap
            else (-0.12 if (not requirement.asks_negation and negation_overlap) else 0.0)
        )
        score = (
            (0.40 * lexical)
            + (0.25 * semantic)
            + (0.30 * subject_alignment)
            + (0.05 * positional)
            - drift_penalty
            - qualifier_penalty
            + negation_adjustment
        )
        scored.append((score, position, row))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [row for _, _, row in scored[:limit]]


_FAST_INTENTS = {"value", "definition", "measurement"}
_MULTI_EVIDENCE_INTENTS = {
    "diagnosis", "treatment", "complication", "classification",
    "cause", "comparison", "visual", "indication", "contraindication",
}


def _needs_multi_evidence(query: str, requirement=None) -> bool:
    requirement = requirement or build_dental_requirement_plan(query)
    intents = requirement.intents
    names = {item.name for item in intents}
    # Multiple explicit subjects always require completeness across subjects,
    # even when each requested fact is individually "fast" (e.g. SNA/SNB/ANB values).
    if requirement.subject_count > 1 or len(requirement.subject_node_ids) > 1:
        return True
    if len(names - {"general"}) > 1:
        return True
    if names and names.issubset(_FAST_INTENTS | {"general"}):
        return False
    return bool(names.intersection(_MULTI_EVIDENCE_INTENTS))


def _coverage_terms(intent_name: str) -> tuple[str, ...]:
    return _EVIDENCE_FACETS.get(intent_name, ())


def _coverage_score(query: str, rows: list, requirement=None, feature_cache=None) -> tuple[float, tuple[str, ...]]:
    """Cheap local coverage signal across every explicitly requested facet."""
    requirement = requirement or build_dental_requirement_plan(query)
    facets = tuple(dict.fromkeys(
        facet for item in requirement.intents for facet in _coverage_terms(item.name)
    ))
    if not facets:
        return (1.0 if rows else 0.0), ()
    corpus = " ".join(f"{row[5] or ''} {row[7] or ''}" for row in rows).casefold()
    semantic_kinds: set[str] = set()
    for row in rows:
        features = _row_semantic_features(row, feature_cache)
        semantic_kinds.update(item.casefold() for item in features.kinds)
    covered: list[str] = []
    for facet in facets:
        if _facet_present(facet, corpus, semantic_kinds):
            covered.append(facet)
    # Kind evidence is only a fallback for the matching intent's own first facet;
    # never let one generic kind satisfy all requirements in a multi-facet query.
    for item in requirement.intents:
        item_facets = _coverage_terms(item.name)
        if not item_facets:
            continue
        if set(k.casefold() for k in item.preferred_kinds).intersection(semantic_kinds):
            if item_facets[0] not in covered:
                covered.append(item_facets[0])
    return len(set(covered)) / max(1, len(facets)), tuple(dict.fromkeys(covered))


@dataclass(frozen=True)
class EvidenceSufficiency:
    sufficient: bool
    confidence: float
    covered_facets: tuple[str, ...]
    missing_facets: tuple[str, ...]


def _row_semantic_features(row, cache: dict[int, DentalSemanticFeatures] | None = None) -> DentalSemanticFeatures:
    row_id = int(row[0]) if row and row[0] is not None else -1
    if cache is not None and row_id in cache:
        return cache[row_id]
    # Indexed semantic metadata is the normal hot path. Re-running the dental
    # matcher for every retrieved chunk wastes CPU and can also make old chunks
    # change meaning after a vocabulary deployment.
    if len(row) > 14 and row[-1]:
        try:
            import json
            meta = json.loads(row[-1])
            features = DentalSemanticFeatures(
                node_ids=tuple(meta.get("nodes") or ()),
                specialties=tuple(meta.get("specialties") or ()),
                kinds=tuple(meta.get("kinds") or ()),
                measurements=tuple(meta.get("measurements") or ()),
                tooth_numbers=tuple(meta.get("teeth") or ()),
                imaging_types=tuple(meta.get("imaging") or ()),
                negated_node_ids=tuple(meta.get("negated_nodes") or ()),
            )
            if cache is not None:
                cache[row_id] = features
            return features
        except (TypeError, ValueError, KeyError):
            pass
    section = row[5] or ""
    body = row[7] or ""
    features = analyze_dental_text(f"{section}\\n{body}")
    if cache is not None:
        cache[row_id] = features
    return features

def _evidence_sufficiency(query: str, rows: list, requirement=None, feature_cache=None, query_features=None) -> EvidenceSufficiency:
    """Decide locally whether evidence is strong enough to spend the one AI call."""
    requirement = requirement or build_dental_requirement_plan(query)
    if not rows:
        missing = tuple(dict.fromkeys(
            facet for item in requirement.intents for facet in _coverage_terms(item.name)
        ))
        return EvidenceSufficiency(False, 0.0, (), missing)
    intent = requirement.intents[0]
    intent_names = {item.name for item in requirement.intents if item.name != "general"}
    qf = query_features or analyze_dental_text(query)
    facets = tuple(dict.fromkeys(
        facet for item in requirement.intents for facet in _coverage_terms(item.name)
    ))
    coverage, covered = _coverage_score(query, rows, requirement=requirement, feature_cache=feature_cache)
    missing = tuple(facet for facet in facets if facet not in covered)

    row_features = [_row_semantic_features(row, feature_cache) for row in rows]
    alignments = sorted(
        (
            _subject_alignment_score(
                query, row[5] or "", row[7] or "",
                query_features=qf, row_features=features,
            )
            for row, features in zip(rows, row_features)
        ),
        reverse=True,
    )
    best_alignment = alignments[0] if alignments else 0.0
    complementary_alignment = alignments[1] if len(alignments) > 1 else 0.0

    evidence_node_ids = {node_id for features in row_features for node_id in features.node_ids}
    # A required subject is complete only when it appears in a row that is also
    # materially aligned to the query. A passing mention in an unrelated chunk
    # must not authorize synthesis for that subject.
    multi_subject_complete = all(
        any(
            node_id in features.node_ids
            and _subject_alignment_score(
                query, row[5] or "", row[7] or "",
                query_features=qf, row_features=features,
            ) >= 0.34
            for row, features in zip(rows, row_features)
        )
        for node_id in requirement.subject_node_ids
    )
    # Bound qualifiers are a collective evidence constraint: each subject that
    # owns explicit modifiers should have at least one evidence row containing
    # both that subject and its modifiers. Keep this soft for ordinary questions
    # but require it for comparisons, where cross-side qualifier leakage changes
    # the meaning of the answer.
    subject_qualifier_complete = True
    for subject_id, qualifiers in requirement.subject_qualifiers:
        if qualifiers and not any(
            subject_id in features.node_ids
            and all(qualifier_present(item, f"{row[5] or ''} {row[7] or ''}") for item in qualifiers)
            for row, features in zip(rows, row_features)
        ):
            subject_qualifier_complete = False
            break
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
    if intent_names.intersection({"value", "measurement"}):
        has_measurement = any(features.measurements for features in row_features)
        # A literal value request ("kaç", "değer", numeric/unit wording) must
        # not authorize generation from a chunk that only names the measure.
        literal_value_request = bool(re.search(
            r"\\b(?:kaç(?:tır)?|değer(?:i|leri)?|normal\\s+değer|ortalama|"
            r"mm|cm|derece|°|yüzde|%)\\b",
            query,
            re.I,
        ))
        if literal_value_request and not has_measurement:
            special_match = 0.0
        else:
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
    if intent_names and intent_names.issubset(_FAST_INTENTS):
        literal_value_missing = (
            bool(intent_names.intersection({"value", "measurement"}))
            and special_match == 0.0
        )
        sufficient = anchored and multi_subject_complete and not literal_value_missing and confidence >= 0.34
    elif facets:
        # Explicit multi-facet requests are a hard completeness contract.
        # Strong subject evidence for one facet must never authorize synthesis
        # of another requested facet that is absent from the user's notes.
        hard_complete = not missing
        comparison_side_complete = True
        if "comparison" in intent_names and requirement.comparison_sides:
            for side_nodes, side_qualifiers in requirement.comparison_sides:
                if side_nodes and not any(
                    bool(set(side_nodes).intersection(features.node_ids))
                    and all(qualifier_present(item, f"{row[5] or ''} {row[7] or ''}") for item in side_qualifiers)
                    for row, features in zip(rows, row_features)
                ):
                    comparison_side_complete = False
                    break
        comparison_complete = (
            subject_qualifier_complete and comparison_side_complete
            if "comparison" in intent_names else True
        )
        sufficient = (
            anchored and hard_complete and multi_subject_complete
            and comparison_complete and confidence >= 0.38
        )
    else:
        sufficient = anchored and multi_subject_complete and confidence >= 0.34

    return EvidenceSufficiency(sufficient, confidence, covered, missing)


def _coverage_select(query: str, rows: list, *, limit: int, requirement=None, feature_cache=None) -> list:
    """Preserve evidence diversity after relevance reranking."""
    if len(rows) <= limit:
        return rows
    requirement = requirement or build_dental_requirement_plan(query)
    facets = tuple(dict.fromkeys(
        facet for item in requirement.intents for facet in _coverage_terms(item.name)
    ))
    selected: list = []
    selected_ids: set[int] = set()
    # Multi-subject questions need diversity before truncation. The primary FTS
    # query may correctly retrieve SNA/SNB/ANB in one DB round-trip, but a pure
    # relevance cut can keep several chunks for one subject and discard another.
    # Reserve one best-ranked evidence row per explicit required subject first.
    for subject_id in requirement.subject_node_ids:
        candidates = []
        for row in rows:
            if int(row[0]) in selected_ids:
                continue
            features = _row_semantic_features(row, feature_cache)
            if subject_id in features.node_ids:
                candidates.append(row)
        if candidates:
            selected.append(candidates[0])
            selected_ids.add(int(candidates[0][0]))
        if len(selected) >= limit:
            return selected
    if not facets:
        for row in rows:
            if int(row[0]) not in selected_ids:
                selected.append(row)
                selected_ids.add(int(row[0]))
            if len(selected) >= limit:
                break
        return selected
    # Then reserve at most one high-ranked chunk for each requested facet,
    # preferring evidence that also remains anchored to the query subject.
    for facet in facets:
        candidates = []
        for row in rows:
            if int(row[0]) in selected_ids:
                continue
            haystack = f"{row[5] or ''} {row[7] or ''}".casefold()
            row_kinds = {item.casefold() for item in _row_semantic_features(row, feature_cache).kinds}
            if _facet_present(facet, haystack, row_kinds):
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
    requirement = build_dental_requirement_plan(resolved)
    query_features = analyze_dental_text(resolved)
    # Request-local semantic memo: bounded by this retrieval's candidate rows,
    # discarded immediately after the request. Avoid repeated JSON parsing/text
    # analysis across rerank, coverage and sufficiency without global RAM state.
    row_feature_cache: dict[int, DentalSemanticFeatures] = {}
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
    course_wide_coverage = bool(
        study_task and study_task.requires_coverage
        and (not requirement.subject_node_ids or re.search(
            r"(?iu)\\b(?:tüm|bütün|tamamı|baştan sona|genel tekrar|notu|notları|dersi|her şeyi|herşeyi)\\b",
            query or "",
        ))
    )
    if course_wide_coverage and not study_question_task and not exhaustive_questions:
        # Broad course-wide summary/explanation/generation must sample the whole published
        # course deterministically instead of collapsing back to a normal top-k
        # lexical query. Metadata scanning is lightweight; only bounded selected
        # representatives are hydrated.
        requested_count = 24
        study_plan = classify_dental_study_plan(query)
        if study_plan and study_plan.count:
            requested_count = min(48, max(8, study_plan.count))
        coverage_plan = get_or_build_coverage_plan(
            session, owner_user_id=owner_user_id, course_id=course_id,
            requested_count=requested_count,
        )
        rows = _coverage_evidence_rows(
            session, owner_user_id=owner_user_id, course_id=course_id,
            chunk_ids=list(coverage_plan.covered_chunk_ids),
            limit=min(48, max(8, requested_count)),
        )
        has_more_questions = False
    elif exhaustive_questions:
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
        # Past questions establish recurrence/style; ordinary note chunks remain
        # the factual source for explanations and newly generated answers.
        question_rows = _academic_question_rows(
            session, owner_user_id=owner_user_id, course_id=course_id, limit=32,
        )
        note_rows = _note_rows_for_question_patterns(
            session, owner_user_id=owner_user_id, course_id=course_id,
            question_rows=question_rows, limit=12,
            required_subject_ids=requirement.subject_node_ids,
        )
        rows = question_rows + note_rows
        has_more_questions = False
    else:
        precise_query = _fts_query(resolved, broad=False)
        # Canonical subject understanding must reach the first DB lookup.
        # This is not graph expansion: only explicitly resolved subject labels
        # are OR-ed with the user's precise lexical form, so typo rescue and
        # curated aliases can recover the right chunk without broadening scope.
        canonical_subjects = []
        for term in requirement.subject_terms:
            normalized = " ".join((term or "").split()).strip()
            if not normalized or len(normalized) > 80:
                continue
            if normalized.casefold() in precise_query.casefold():
                continue
            canonical_subjects.append(normalized)
            if len(canonical_subjects) >= 3:
                break
        if canonical_subjects:
            canonical_query = " OR ".join(
                f'"{term}"' if " " in term else term for term in canonical_subjects
            )
            precise_query = f"{precise_query} OR {canonical_query}"
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
        # Normal QA has one primary retrieval round-trip. Only a complex query
        # with an explicitly missing facet may spend one bounded rescue query.
        # Do not replay the whole question or use graph expansion for rescue:
        # subject identity comes from the user's lexical subject plus curated
        # aliases, while the missing facet contributes only its synonym group.
        candidate_target = max(limit * 4, 24)
        rows = _rerank_dental_rows(resolved, rows, limit=max(limit * 2, 12), requirement=requirement, feature_cache=row_feature_cache, query_features=query_features)
        coverage, covered_facets = _coverage_score(resolved, rows, requirement=requirement, feature_cache=row_feature_cache)
        rescue_query_count = 0
        requested_facets = tuple(dict.fromkeys(
            facet for item in requirement.intents for facet in _coverage_terms(item.name)
        ))
        missing_facets = [facet for facet in requested_facets if facet not in covered_facets]
        evidence_nodes = {
            node_id
            for row in rows
            for node_id in _row_semantic_features(row, row_feature_cache).node_ids
        }
        missing_subject_ids = [
            node_id for node_id in requirement.subject_node_ids
            if node_id not in evidence_nodes
        ]
        needs_rescue = bool(missing_facets or missing_subject_ids)
        if (
            _needs_multi_evidence(resolved, requirement=requirement)
            and needs_rescue
            and len(rows) < candidate_target
        ):
            # Spend at most one rescue on exactly what primary retrieval missed.
            # Missing explicit subjects take priority over already-covered ones;
            # missing facets are appended as strict AND terms when present.
            missing_subject_terms = [
                label for node_id in missing_subject_ids
                if (label := node_label(node_id))
            ]
            subject_terms = missing_subject_terms or list(requirement.subject_terms[:1])
            subject_query = " OR ".join(
                f'"{term}"' if " " in term else term
                for term in subject_terms[:3] if term
            )
            facet_terms = []
            for facet in missing_facets:
                hints = _FACET_SEARCH_TERMS.get(facet, (facet,))
                if hints:
                    term = hints[0]
                    facet_terms.append(f'"{term}"' if " " in term else term)
            if subject_query:
                # websearch_to_tsquery does not provide reliable parenthesized
                # grouping. When a required subject is missing, dedicate the one
                # rescue to subject recovery; final local gates still enforce
                # facets. Facet-only rescue has one subject, so AND semantics are
                # unambiguous.
                rescue_query = (
                    subject_query
                    if missing_subject_ids
                    else " ".join([subject_query, *facet_terms])
                )
                rescue_rows = _fts_rows(
                    session,
                    owner_user_id=owner_user_id,
                    course_id=course_id,
                    lexical_query=rescue_query,
                    query_vector=None,
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                    limit=min(6, max(1, candidate_target - len(rows))),
                )
                rescue_query_count = 1
                seen_ids = {int(row[0]) for row in rows}
                for row in rescue_rows:
                    row_id = int(row[0])
                    if row_id not in seen_ids:
                        rows.append(row)
                        seen_ids.add(row_id)
                # Rescue evidence re-enters the same relevance and coverage
                # gates; it never bypasses subject alignment or sufficiency.
                rows = _rerank_dental_rows(
                    resolved, rows, limit=max(limit * 2, 12),
                    requirement=requirement, feature_cache=row_feature_cache,
                    query_features=query_features,
                )
                coverage, covered_facets = _coverage_score(
                    resolved, rows, requirement=requirement,
                    feature_cache=row_feature_cache,
                )
        logger.info(
            "Academic V2 retrieval DB plan. rescue_queries=%s coverage=%.3f facets=%s",
            rescue_query_count, coverage, ",".join(covered_facets) or "-",
        )
        rows = _coverage_select(resolved, rows, limit=limit, requirement=requirement, feature_cache=row_feature_cache, query_features=query_features)
        primary_ids = [int(row[0]) for row in rows]
        # Keep neighbor seeds subject-diverse. Coverage selection already
        # preserves each required subject; do not throw that work away by
        # seeding adjacency from three rows belonging to the same subject.
        neighbor_seed_ids: list[int] = []
        for subject_id in requirement.subject_node_ids:
            for row in rows:
                if subject_id in _row_semantic_features(row, row_feature_cache).node_ids:
                    row_id = int(row[0])
                    if row_id not in neighbor_seed_ids:
                        neighbor_seed_ids.append(row_id)
                    break
            if len(neighbor_seed_ids) >= 3:
                break
        for row_id in primary_ids:
            if row_id not in neighbor_seed_ids:
                neighbor_seed_ids.append(row_id)
            if len(neighbor_seed_ids) >= 3:
                break
        # Neighbor context is useful for split passages, but it must not be an
        # unconditional extra DB query or cross a section boundary.
        requirement_names = {
            item.name for item in requirement.intents
            if item.name != "general"
        }
        fast_direct = bool(requirement_names) and requirement_names.issubset(_FAST_INTENTS)
        context_target = min(10, limit + 2) if _needs_multi_evidence(resolved, requirement=requirement) else max(4, limit)
        # Fast questions skip the neighbor query only when the selected evidence
        # already passes the same local sufficiency gate used before generation.
        # A hit at a chunk boundary therefore gets bounded adjacent context,
        # while a self-contained definition/value keeps the one-query path.
        provisional = _evidence_sufficiency(resolved, rows, requirement=requirement, feature_cache=row_feature_cache, query_features=query_features)
        neighbor_limit = (
            0
            if provisional.sufficient
            else min(2, max(0, context_target - len(rows)))
        )
        if neighbor_limit:
            neighbor_rows = _neighbor_rows(
                session,
                owner_user_id=owner_user_id,
                course_id=course_id,
                seed_ids=neighbor_seed_ids,
                exclude_ids=primary_ids,
                limit=neighbor_limit,
            )
            if neighbor_rows:
                rows.extend(neighbor_rows)
                # Adjacent context is only a candidate repair. It must re-enter
                # the same canonical relevance/diversity gates before generation.
                rows = _rerank_dental_rows(
                    resolved, rows, limit=max(limit + neighbor_limit, limit),
                    requirement=requirement, feature_cache=row_feature_cache,
                    query_features=query_features,
                )
                rows = _coverage_select(
                    resolved, rows, limit=limit, requirement=requirement,
                    feature_cache=row_feature_cache,
                )
    intent_label = "+".join(item.name for item in requirement.intents) or "general"
    logger.info(
        "Academic V2 retrieval selected. mode=%s intent=%s evidence_rows=%s",
        "coverage" if (course_wide_coverage and not study_question_task and not exhaustive_questions) else ("questions_exhaustive" if exhaustive_questions else ("academic_question_patterns" if study_question_task else "fts")),
        intent_label,
        len(rows),
    )
    result = RetrievalResult(
        resolved_query=resolved,
        retrieval_mode="coverage" if (course_wide_coverage and not study_question_task and not exhaustive_questions) else ("questions_exhaustive" if exhaustive_questions else ("academic_question_patterns" if study_question_task else "fts")),
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

    if course_wide_coverage and not study_question_task and not exhaustive_questions:
        result.evidence_sufficient = bool(result.evidence)
        result.evidence_confidence = 1.0 if result.evidence else 0.0
    elif exhaustive_questions:
        result.evidence_sufficient = bool(result.evidence)
        result.evidence_confidence = 1.0 if result.evidence else 0.0
    elif study_question_task:
        question_evidence = [e for e in result.evidence if e.content_kind == "QUESTION"]
        factual_note_evidence = [e for e in result.evidence if e.content_kind != "QUESTION"]
        # Pattern-only analysis may describe actual past questions, but any task
        # that generates a new factual question/answer must also have note evidence.
        needs_factual_generation = bool(study_task and study_task.generate_new_questions)
        result.evidence_sufficient = bool(question_evidence) and (
            bool(factual_note_evidence) or not needs_factual_generation
        )
        result.evidence_confidence = (
            1.0 if question_evidence and factual_note_evidence
            else 0.72 if question_evidence and not needs_factual_generation
            else 0.0
        )
    else:
        sufficiency = _evidence_sufficiency(resolved, rows, requirement=requirement, feature_cache=row_feature_cache, query_features=query_features)
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
    # Keep retrieval DB-only. True visual source bytes are materialized later,
    # after this retrieval transaction has closed.
    visual_requested = requirement.requires_visual_source
    if visual_requested and result.evidence_sufficient:
        for item in result.evidence:
            key = (item.material_id, item.page_start)
            if key not in visual_pages:
                visual_pages.append(key)
            if len(visual_pages) >= 3:
                break
    if visual_pages:
        material_rows = session.exec(
            text("SELECT id, file_path, mime_type, display_name, active_index_version FROM studymaterial WHERE owner_user_id=:o AND deleted_at IS NULL AND id=ANY(:ids)"),
            params={"o": owner_user_id, "ids": [item[0] for item in visual_pages]},
        ).all()
        materials = {int(row[0]): row for row in material_rows}
        for material_id, page in visual_pages:
            material = materials.get(material_id)
            if not material:
                continue
            result.visual_sources.append({
                "owner_user_id": owner_user_id,
                "material_id": material_id,
                "reference": material[1],
                "mime_type": material[2],
                "display_name": material[3],
                "index_version": str(material[4]) if material[4] else None,
                "page_number": page,
            })
    if visual_requested and result.evidence_sufficient and not result.visual_sources:
        result.evidence_sufficient = False
        result.evidence_confidence = 0.0
    return result
