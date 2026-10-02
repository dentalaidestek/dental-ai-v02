"""Deterministic dental question intent classification for retrieval planning."""
from __future__ import annotations
from dataclasses import dataclass
import re

@dataclass(frozen=True)
class DentalIntent:
    name: str
    preferred_kinds: tuple[str, ...]
    relation_hints: tuple[str, ...] = ()

_RULES = (
    ("value", re.compile(r"\b(?:kaç|kaçtır|değer(?:i|in|ini|leri|lerin|lerini|ler)?|normal değer(?:i|in|ini|leri|lerin|lerini|ler)?|mm|oran)\b", re.I),
     ("measurement",), ("measures", "assessed_by")),
    ("measurement", re.compile(r"\b(?:hangi açı(?:yla)?|hangi ölçüm|neyle ölç|nasıl ölç|nasıl ölçül|ölçül[a-zçğıöşü]*|ölçüm[a-zçğıöşü]* nasıl|değerlendiril[a-zçğıöşü]*)\b", re.I),
     ("measurement",), ("measures", "assessed_by", "used_for")),
    ("definition", re.compile(r"\b(?:nedir|ne demek|tanımı|tanımla)\b", re.I),
     ("diagnosis", "finding", "anatomy", "measurement", "relation"), ()),
    ("classification", re.compile(r"\b(?:sınıflam[a-zçğıöşü]*|sınıflandır[a-zçğıöşü]*|class|sınıf[a-zçğıöşü]*|evre[a-zçğıöşü]*|stage|grade|derece)\b", re.I),
     ("classification", "diagnosis", "finding"), ("classified_by", "has_stage", "has_grade")),
    ("indication", re.compile(r"\b(?:endikasyon[a-zçğıöşü]*|ne zaman (?:kullan|uygula|yap)[a-zçğıöşü]*|hangi durumda (?:kullan|uygula|yap)[a-zçğıöşü]*|kim(?:ler)?de (?:kullan|uygula|yap)[a-zçğıöşü]*)\b", re.I),
     ("procedure", "material", "imaging"), ("used_for", "has_indication")),
    ("contraindication", re.compile(r"\b(?:kontrendikasyon[a-zçğıöşü]*|kullanılmaz|uygulanmaz|yapılmaz|sakınca|kim(?:ler)?de (?:kullanılmaz|uygulanmaz|yapılmaz)|hangi durumda (?:kullanılmaz|uygulanmaz|yapılmaz))\b", re.I),
     ("procedure", "material"), ("has_contraindication",)),
    ("complication", re.compile(r"\b(?:komplikasyon[a-zçğıöşü]*|risk[a-zçğıöşü]*|zarar|istenmeyen|yan etki)\b", re.I),
     ("finding", "diagnosis", "procedure"), ("has_complication", "leads_to", "associated_with")),
    ("diagnosis", re.compile(r"\b(?:tanı[a-zçğıöşü]*|teşhis[a-zçğıöşü]*|ayırt|ayırıcı|bulgu[a-zçğıöşü]*|semptom[a-zçğıöşü]*|nasıl tanı[a-zçğıöşü]*|nasıl teşhis[a-zçğıöşü]*)\b", re.I),
     ("diagnosis", "finding", "imaging"), ("manifests_as", "has_clinical_feature", "has_radiographic_feature", "differential_with")),
    ("treatment", re.compile(r"\b(?:tedavi[a-zçğıöşü]*|müdahale[a-zçğıöşü]*|yaklaşım[a-zçğıöşü]*|yönetim[a-zçğıöşü]*|ne yapıl[a-zçğıöşü]*|nasıl tedavi[a-zçğıöşü]*)\b", re.I),
     ("procedure", "diagnosis"), ("has_treatment", "treats", "has_procedure", "used_for")),
    ("anatomy", re.compile(r"\b(?:nerede|konum|komşu|ilişki|yakın|geçer|seyreder|anatom)\b", re.I),
     ("anatomy", "relation"), ("anatomical_relation", "part_of")),
    ("visual", re.compile(r"\b(?:radyografi|röntgen|film|görüntü|fotoğraf|panoramik|opg|cbct|periapikal|bitewing|sefalogram|şekil|tablo|grafik)\b", re.I),
     ("imaging", "finding", "anatomy"), ("used_for", "anatomical_relation")),
    ("comparison", re.compile(r"\b(?:fark[a-zçğıöşü]*|karşılaştır[a-zçğıöşü]*|versus|vs\.?|hangisi daha)\b", re.I),
     ("measurement", "diagnosis", "finding", "material", "procedure"), ()),
    ("cause", re.compile(r"\b(?:neden|niçin|sebep[a-zçğıöşü]*|etyoloji[a-zçğıöşü]*|etiyoloji[a-zçğıöşü]*|patogenez[a-zçğıöşü]*|niye|neden olur|neye bağlı)\b", re.I),
     ("diagnosis", "finding"), ("caused_by", "has_mechanism", "has_risk_factor", "associated_with")),
)

def classify_dental_intent(query: str) -> DentalIntent:
    clean = " ".join((query or "").split())
    for name, pattern, kinds, relations in _RULES:
        if pattern.search(clean):
            return DentalIntent(name, kinds, relations)
    return DentalIntent("general", (), ())


def classify_dental_intents(query: str, *, limit: int = 6) -> tuple[DentalIntent, ...]:
    """Return explicit question requirements without turning subject words into intents."""
    clean = " ".join((query or "").split())
    found: list[DentalIntent] = []
    for name, pattern, kinds, relations in _RULES:
        match = pattern.search(clean)
        if not match:
            continue
        # "kanal tedavisi komplikasyonları" names a treatment as the subject;
        # it does not ask for treatment itself. Require treatment wording to
        # behave like a requested facet, unless no stronger requested facet exists.
        if name == "treatment":
            tail = clean[match.end():]
            if re.search(r"^\s+(?:komplikasyon|risk|yan etki|endikasyon|kontrendikasyon)", tail, re.I):
                continue
        found.append(DentalIntent(name, kinds, relations))
        if len(found) >= max(1, min(limit, 6)):
            break
    if found:
        # Imaging words describe a modality/constraint surprisingly often
        # ("CBCT'de mandibular kanal ilişkisi"). When another explicit intent
        # states what is actually asked, visual must not become a second facet
        # that forces unnecessary multi-evidence retrieval or attachments.
        non_visual = [item for item in found if item.name != "visual"]
        if non_visual:
            found = non_visual
        # Generic "nedir/nelerdir" often closes a multi-facet Turkish question
        # ("tanısı ve tedavisi nedir?"). It must not create a fake definition
        # requirement when stronger explicit facets are already present.
        explicit = [item for item in found if item.name != "definition"]
        if explicit:
            found = explicit
        return tuple(found)
    return (DentalIntent("general", (), ()),)


def combined_relation_hints(intents: tuple[DentalIntent, ...], *, limit: int = 10) -> tuple[str, ...]:
    """Bounded union preserving intent priority."""
    result: list[str] = []
    for intent in intents:
        for relation in intent.relation_hints:
            if relation not in result:
                result.append(relation)
            if len(result) >= limit:
                return tuple(result)
    return tuple(result)


@dataclass(frozen=True)
class DentalRequirementPlan:
    subject_node_ids: tuple[str, ...]
    subject_terms: tuple[str, ...]
    intents: tuple[DentalIntent, ...]
    requested_facets: tuple[str, ...]
    relation_hints: tuple[str, ...]
    specialties: tuple[str, ...]
    qualifiers: tuple[str, ...] = ()
    comparison_terms: tuple[str, ...] = ()
    asks_negation: bool = False
    subject_count: int = 0
    unresolved_subject: bool = False
    constraint_node_ids: tuple[str, ...] = ()
    explicit_relations: tuple[tuple[str, str, str], ...] = ()
    subject_qualifiers: tuple[tuple[str, tuple[str, ...]], ...] = ()
    requires_visual_source: bool = False

_SUBJECT_STOP_RE = re.compile(
    r"\\b(?:nedir|nelerdir|kaçtır|hangisi|hangileri|anlat|açıkla|özetle|tanı(?:sı|ları|nı|yı)?|"
    r"tedavi(?:si|leri|sini)?|bulgu(?:su|ları|larını)?|semptom(?:u|ları)?|"
    r"komplikasyon(?:u|ları)?|endikasyon(?:u|ları)?|kontrendikasyon(?:u|ları)?|"
    r"sınıflama(?:sı|ları)?|etyoloji(?:si)?|etiyoloji(?:si)?|patogenez(?:i)?|"
    r"klinik|radyografik|ayırt edici|ayırıcı|değil|değildir|olmayan|olmaz|olmamalı(?:dır)?|"
    r"yapılmaz|kullanılmaz|uygulanmaz|önerilmez|tercih edilmez|kaçınılmalı(?:dır)?|"
    r"hariç|yanlıştır|peki|bunun|onun|bunların|ve|ile|ile birlikte)\\b",
    re.I,
)
_SUBJECT_SUFFIX_RE = re.compile(r"(?iu)(?:nın|nin|nun|nün|ın|in|un|ün)$")

def _lexical_subject_terms(query: str, *, limit: int = 4) -> tuple[str, ...]:
    """Keep unknown dental subjects searchable without inventing graph nodes."""
    clean = re.sub(r"[?,;:()]+", " ", query or "")
    clean = _SUBJECT_STOP_RE.sub(" ", clean)
    tokens = [t.strip(".-") for t in clean.split() if len(t.strip(".-")) >= 2]
    tokens = [_SUBJECT_SUFFIX_RE.sub("", t) for t in tokens]
    tokens = [t for t in tokens if len(t) >= 2]
    if not tokens:
        return ()
    # Preserve phrase order; FTS can still tokenize it. Bounded to avoid turning
    # the entire question into a broad lexical query.
    phrase = " ".join(tokens[:8]).strip()
    return (phrase,) if phrase else ()


_QUALIFIER_PATTERNS = (
    ("maksiller", re.compile(r"\b(?:maksiller|maksilla(?:da|dan|daki|nın|nin)?)\b", re.I)),
    ("mandibular", re.compile(r"\b(?:mandibular|mandibula(?:da|dan|daki|nın|nin)?)\b", re.I)),
    ("üst", re.compile(r"\büst(?:te|ten|teki)?\b", re.I)),
    ("alt", re.compile(r"\balt(?:ta|tan|taki)?\b", re.I)),
    ("sağ", re.compile(r"\bsağ(?:da|dan|daki)?\b", re.I)),
    ("sol", re.compile(r"\bsol(?:da|dan|daki)?\b", re.I)),
    ("anterior", re.compile(r"\banterior(?:da|dan|daki)?\b", re.I)),
    ("posterior", re.compile(r"\bposterior(?:da|dan|daki)?\b", re.I)),
    ("süt", re.compile(r"\bsüt(?:te|ten|teki)?\b", re.I)),
    ("daimi", re.compile(r"\bdaimi\b", re.I)),
    ("primer", re.compile(r"\bprimer\b", re.I)),
    ("sekonder", re.compile(r"\bsekonder\b", re.I)),
    ("akut", re.compile(r"\bakut(?:ta|tan)?\b", re.I)),
    ("kronik", re.compile(r"\bkronik(?:te|ten)?\b", re.I)),
    ("reversible", re.compile(r"\breversible\b", re.I)),
    ("irreversible", re.compile(r"\birreversible\b", re.I)),
    ("semptomatik", re.compile(r"\bsemptomatik\b", re.I)),
    ("asemptomatik", re.compile(r"\basemptomatik\b", re.I)),
    ("lokalize", re.compile(r"\blokalize\b", re.I)),
    ("generalize", re.compile(r"\bgeneralize\b", re.I)),
    ("erken", re.compile(r"\berken\b", re.I)),
    ("geç", re.compile(r"\bgeç\b", re.I)),
    ("çocuk", re.compile(r"\bçocuk(?:ta|tan|larda|larda)?\b", re.I)),
    ("erişkin", re.compile(r"\berişkin(?:de|den|lerde)?\b", re.I)),
)
_QUALIFIER_RE = re.compile(
    r"\b(?:maksiller|mandibular|maksilla|mandibula|üst|alt|sağ|sol|anterior|posterior|"
    r"süt|daimi|primer|sekonder|akut|kronik|reversible|irreversible|semptomatik|"
    r"asemptomatik|lokalize|generalize|erken|geç|çocuk|erişkin)[a-zçğıöşü]{0,5}\b",
    re.I,
)

def query_qualifiers(query: str) -> tuple[str, ...]:
    text = query or ""
    return tuple(name for name, pattern in _QUALIFIER_PATTERNS if pattern.search(text))

def qualifier_present(qualifier: str, text: str) -> bool:
    return any(name == qualifier and pattern.search(text or "") for name, pattern in _QUALIFIER_PATTERNS)

_NEGATION_REQUEST_RE = re.compile(
    r"\\b(?:değil|değildir|olmayan|olmaz|yapılmaz|kullanılmaz|uygulanmaz|"
    r"kontrendike|hariç|yanlıştır|yanlış olan|doğru değildir|hangisi yanlış|"
    r"önerilmez|tercih edilmez|olmamalı(?:dır)?|kaçınılmalı(?:dır)?)\\b",
    re.I,
)
_COMPARISON_SPLIT_RE = re.compile(r"\\s+(?:ile|ve|vs\\.?|versus)\\s+", re.I)


def _query_qualifiers(query: str) -> tuple[str, ...]:
    return query_qualifiers(query)



def _subject_qualifier_bindings(query: str, subject_nodes) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Bind nearby explicit modifiers to explicit subjects without an NLP model."""
    text = query or ""
    mentions: list[tuple[int, int, str]] = []
    for node in subject_nodes:
        terms = sorted((node.label, *node.aliases), key=len, reverse=True)
        for term in terms:
            clean = " ".join((term or "").split())
            if not clean:
                continue
            pattern = re.escape(clean).replace(r"\ ", r"\s+")
            match = re.search(r"(?<!\w)" + pattern + r"(?!\w)", text, re.I)
            if match:
                mentions.append((match.start(), match.end(), node.id))
                break
    if not mentions:
        return ()
    bound: dict[str, list[str]] = {}
    for qualifier, pattern in _QUALIFIER_PATTERNS:
        qmatch = pattern.search(text)
        if not qmatch:
            continue
        candidates: list[tuple[int, str]] = []
        for start, end, node_id in mentions:
            if qmatch.end() <= start:
                distance = start - qmatch.end()
                between = text[qmatch.end():start]
            elif end <= qmatch.start():
                distance = qmatch.start() - end
                between = text[end:qmatch.start()]
            else:
                distance = 0
                between = ""
            if distance > 32 or re.search(r"[;.!?]", between):
                continue
            candidates.append((distance, node_id))
        candidates.sort()
        if not candidates:
            continue
        best_distance = candidates[0][0]
        best_ids = {node_id for distance, node_id in candidates if distance == best_distance}
        if len(best_ids) != 1:
            continue
        node_id = next(iter(best_ids))
        bound.setdefault(node_id, []).append(qualifier)
    return tuple((node_id, tuple(dict.fromkeys(values))) for node_id, values in bound.items())


def _comparison_terms(query: str, intents: tuple[DentalIntent, ...]) -> tuple[str, ...]:
    if not any(intent.name == "comparison" for intent in intents):
        return ()
    clean = re.sub(r"(?i)\\b(?:arasındaki|fark(?:ı|ları)?|karşılaştır[a-zçğıöşü]*|hangisi daha)\\b", " ", query or "")
    parts = [re.sub(r"\\s+", " ", part).strip(" ?.,;:") for part in _COMPARISON_SPLIT_RE.split(clean)]
    return tuple(part for part in parts if len(part) >= 2)[:2]


def build_dental_requirement_plan(query: str) -> DentalRequirementPlan:
    """Separate what the user asks about from which facts they request."""
    from app.dental_knowledge_graph import matched_nodes
    clean = " ".join((query or "").split())
    intents = classify_dental_intents(clean, limit=6)
    nodes = matched_nodes(clean)
    # Imaging entities constrain how/where evidence is interpreted, but they
    # are not normally an independent factual subject. Requiring CBCT/OPG as a
    # second "subject" made otherwise correct evidence fail completeness.
    subject_nodes = tuple(node for node in nodes if node.kind != "imaging")
    constraint_nodes = tuple(node for node in nodes if node.kind == "imaging")
    subject_ids = tuple(dict.fromkeys(node.id for node in subject_nodes))
    subject_terms = tuple(dict.fromkeys(node.label for node in subject_nodes))
    if not subject_terms:
        # If the query is genuinely about the imaging modality itself ("CBCT
        # nedir?"), it remains the subject; otherwise imaging stays a constraint.
        non_visual_intents = {item.name for item in intents if item.name not in {"general", "visual"}}
        if constraint_nodes and non_visual_intents.intersection({"definition", "comparison", "indication", "contraindication"}):
            subject_ids = tuple(dict.fromkeys(node.id for node in constraint_nodes))
            subject_terms = tuple(dict.fromkeys(node.label for node in constraint_nodes))
        else:
            subject_terms = _lexical_subject_terms(clean)
    specialties = tuple(dict.fromkeys(node.specialty for node in nodes if node.specialty != "general"))
    # Preserve only relations whose two endpoints were explicitly mentioned by
    # the user. The graph may explain the connection, but it must never invent
    # an unstated subject/fact for retrieval or generation.
    explicit_ids = {node.id for node in nodes}
    explicit_relations: list[tuple[str, str, str]] = []
    if len(explicit_ids) >= 2:
        from app.dental_knowledge_graph import EDGES
        from app.dental_knowledge_relations import DENTAL_RELATION_EDGES
        for edge in (*EDGES, *DENTAL_RELATION_EDGES):
            if edge.weight < 0.80:
                continue
            if edge.source in explicit_ids and edge.target in explicit_ids:
                explicit_relations.append((edge.source, edge.relation.value, edge.target))
    # Two or more explicit non-imaging subjects plus a comparative operator
    # is a comparison even when the wording does not contain "fark/karşılaştır".
    # Do not treat a plain conjunction ("SNA ve SNB değerleri") as comparison.
    if (
        len(subject_ids) >= 2
        and not any(item.name == "comparison" for item in intents)
        and re.search(r"(?iu)\\b(?:hangisi|hangileri|hangisinde|daha)\\b", clean)
    ):
        comparison_intent = DentalIntent("comparison", (), ("compared_with",))
        intents = tuple((*intents, comparison_intent))[:6]
    comparison_terms = _comparison_terms(clean, intents)
    requires_visual_source = bool(re.search(
        r"(?iu)(?:\\b(?:bu|şu)\\s+(?:radyografi|röntgen|film|görüntü|fotoğraf|şekil|tablo|grafik|cbct|opg)"
        r"|\\b(?:radyografideki|filmdeki|görüntüdeki|şekildeki|tablodaki|grafikteki)\\b"
        r"|\\b(?:gösterilen|işaretli|okla\\s+gösterilen|görülen)\\b"
        r"|\\b(?:radyografi|film|görüntü|şekil|tablo|grafik)(?:de|da)\\s+(?:ne|neyi|hangi|nerede)\\b)",
        clean,
    ))
    facets = tuple(intent.name for intent in intents if intent.name != "general")
    return DentalRequirementPlan(
        subject_node_ids=subject_ids,
        subject_terms=subject_terms,
        intents=intents,
        requested_facets=facets,
        relation_hints=combined_relation_hints(intents, limit=16),
        specialties=specialties,
        qualifiers=_query_qualifiers(clean),
        comparison_terms=comparison_terms,
        asks_negation=bool(_NEGATION_REQUEST_RE.search(clean)),
        subject_count=len(subject_ids) if subject_ids else len(comparison_terms),
        unresolved_subject=not bool(subject_ids or subject_terms),
        constraint_node_ids=tuple(dict.fromkeys(node.id for node in constraint_nodes)),
        explicit_relations=tuple(dict.fromkeys(explicit_relations)),
        subject_qualifiers=_subject_qualifier_bindings(clean, subject_nodes),
        requires_visual_source=requires_visual_source,
    )


_STUDY_GENERATION_RE = re.compile(
    r"\b(?:soru|test|quiz|flashcard|kart|çalışma sorusu|deneme)\b.{0,48}"
    r"\b(?:üret|hazırla|oluştur|çıkar|sor)\b|"
    r"\b(?:üret|hazırla|oluştur|çıkar)\b.{0,48}\b(?:soru|test|quiz|flashcard|kart)\b",
    re.I,
)
_STUDY_COVERAGE_RE = re.compile(
    r"\b(?:tüm|bütün|tamamı|notun tamamı|dersin tamamı|her konu|bütün konu|"
    r"eksiksiz|kapsamlı|sınavlık|sınav noktaları)\b",
    re.I,
)
_STUDY_DIFFICULTY_RE = re.compile(r"\b(?:kolay|orta|zor|çok zor|ayırt edici|klinik|vaka)\b", re.I)
_STUDY_COUNT_RE = re.compile(r"\b(\d{1,3})\s*(?:adet\s*)?(?:soru|test|quiz|flashcard|kart)\b", re.I)


@dataclass(frozen=True)
class DentalStudyPlan:
    mode: str
    count: int | None = None
    difficulty: str | None = None
    question_types: tuple[str, ...] = ()
    coverage_required: bool = False


def classify_dental_study_plan(query: str) -> DentalStudyPlan | None:
    """Detect role-neutral academic generation requests without affecting normal QA."""
    clean = " ".join((query or "").split())
    if not _STUDY_GENERATION_RE.search(clean):
        return None
    count_match = _STUDY_COUNT_RE.search(clean)
    count = min(200, int(count_match.group(1))) if count_match else None
    difficulty_match = _STUDY_DIFFICULTY_RE.search(clean)
    kinds: list[str] = []
    lowered = clean.casefold()
    if any(term in lowered for term in ("çoktan seçmeli", "test", "mcq")):
        kinds.append("mcq")
    if any(term in lowered for term in ("açık uçlu", "klasik")):
        kinds.append("open")
    if any(term in lowered for term in ("doğru yanlış", "doğru/yanlış")):
        kinds.append("true_false")
    if any(term in lowered for term in ("flashcard", "kart")):
        kinds.append("flashcard")
    coverage = bool(_STUDY_COVERAGE_RE.search(clean))
    return DentalStudyPlan(
        mode="coverage" if coverage else "topic",
        count=count,
        difficulty=difficulty_match.group(0).casefold() if difficulty_match else None,
        question_types=tuple(dict.fromkeys(kinds)),
        coverage_required=coverage,
    )


@dataclass(frozen=True)
class AcademicStudyTaskPlan:
    task: str
    requires_past_questions: bool = False
    requires_note_evidence: bool = True
    requires_coverage: bool = False
    generate_new_questions: bool = False


_BROAD_ACADEMIC_RE = re.compile(
    r"\\b(?:tüm|bütün|tamamı|baştan sona|detaylı|kapsamlı|eksiksiz|genel tekrar|"
    r"notu özetle|notları özetle|dersi özetle|konuyu detaylı|bölümü özetle|"
    r"her şeyi|herşeyi)\\b", re.I,
)

_ACADEMIC_STUDY_TASK_RULES = (
    ("repeated_patterns", re.compile(r"\b(?:sürekli|tekrar tekrar|en çok|sık sık)\b.{0,48}\b(?:sor|çıkmış|soru)", re.I), True, True, True, False),
    ("past_exam_patterns", re.compile(r"\b(?:çıkmış|geçmiş)\s+(?:soru|sınav)|\bhoca.{0,32}(?:sormuş|sorduğu)", re.I), True, True, True, False),
    ("similar_questions", re.compile(r"\b(?:benzer|aynı tarz|aynı tip)\b.{0,32}\b(?:soru|test).{0,32}\b(?:üret|hazırla|oluştur|sor)|\b(?:benzeri|benzerini)\b.{0,24}\b(?:üret|hazırla|oluştur)", re.I), True, True, False, True),
    ("exam_points", re.compile(r"\b(?:sorabileceği|sorulabilecek|sınavlık|sınavda çıkabilecek|önemli)\b.{0,40}\b(?:yer|nokta|konu|bilgi|kısım)", re.I), False, True, True, False),
    ("explain", re.compile(r"\b(?:bu kısmı|şu kısmı|bu konuyu|şu konuyu|burayı)\b.{0,24}\b(?:anlat|açıkla|özetle)|\b(?:anlat|açıkla|özetle)\b.{0,24}\b(?:bu kısmı|şu kısmı|bu konuyu|şu konuyu|burayı)", re.I), False, True, False, False),
)


def classify_academic_study_task(query: str) -> AcademicStudyTaskPlan | None:
    """Plan role-neutral academic workflows while keeping factual output source-bound."""
    clean = " ".join((query or "").split())
    for task, pattern, past, notes, coverage, generate in _ACADEMIC_STUDY_TASK_RULES:
        if pattern.search(clean):
            return AcademicStudyTaskPlan(task, past, notes, coverage, generate)
    study = classify_dental_study_plan(clean)
    if study:
        return AcademicStudyTaskPlan(
            "generate_questions",
            False,
            True,
            study.coverage_required,
            True,
        )
    # Broad academic requests share the durable coverage engine regardless of
    # output form; the response contract decides summary/explanation/etc.
    if _BROAD_ACADEMIC_RE.search(clean):
        lowered = clean.casefold()
        task = "summarize" if any(x in lowered for x in ("özet", "özetle")) else "explain"
        return AcademicStudyTaskPlan(task, False, True, True, False)
    return None
