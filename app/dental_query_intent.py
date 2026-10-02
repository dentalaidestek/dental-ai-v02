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
    ("value", re.compile(r"\b(?:kaç|kaçtır|değer(?:i|in|ini|leri|lerin|lerini|ler)?|normal değer(?:i|in|ini|leri|lerin|lerini|ler)?|derece|mm|oran)\b", re.I),
     ("measurement",), ("measures", "assessed_by")),
    ("measurement", re.compile(r"\b(?:hangi açı(?:yla)?|hangi ölçüm|neyle ölç|nasıl ölç|ölçülür|değerlendirilir)\b", re.I),
     ("measurement",), ("measures", "assessed_by", "used_for")),
    ("definition", re.compile(r"\b(?:nedir|ne demek|tanımı|tanımla)\b", re.I),
     ("diagnosis", "finding", "anatomy", "measurement", "relation"), ()),
    ("classification", re.compile(r"\b(?:sınıflam[a-zçğıöşü]*|sınıflandır[a-zçğıöşü]*|class|sınıf[a-zçğıöşü]*|evre[a-zçğıöşü]*|stage|grade|derece)\b", re.I),
     ("classification", "diagnosis", "finding"), ("classified_by", "has_stage", "has_grade")),
    ("indication", re.compile(r"\b(?:endikasyon[a-zçğıöşü]*|ne zaman kullan[a-zçğıöşü]*|hangi durumda kullan[a-zçğıöşü]*)\b", re.I),
     ("procedure", "material", "imaging"), ("used_for", "has_indication")),
    ("contraindication", re.compile(r"\b(?:kontrendikasyon[a-zçğıöşü]*|kullanılmaz|yapılmaz|sakınca)\b", re.I),
     ("procedure", "material"), ("has_contraindication",)),
    ("complication", re.compile(r"\b(?:komplikasyon[a-zçğıöşü]*|risk[a-zçğıöşü]*|zarar|istenmeyen|yan etki)\b", re.I),
     ("finding", "diagnosis", "procedure"), ("has_complication", "leads_to", "associated_with")),
    ("diagnosis", re.compile(r"\b(?:tanı[a-zçğıöşü]*|teşhis[a-zçğıöşü]*|ayırt|ayırıcı|bulgu[a-zçğıöşü]*|semptom[a-zçğıöşü]*)\b", re.I),
     ("diagnosis", "finding", "imaging"), ("manifests_as", "has_clinical_feature", "has_radiographic_feature", "differential_with")),
    ("treatment", re.compile(r"\b(?:tedavi[a-zçğıöşü]*|müdahale[a-zçğıöşü]*|yaklaşım[a-zçğıöşü]*|yönetim[a-zçğıöşü]*)\b", re.I),
     ("procedure", "diagnosis"), ("has_treatment", "treats", "has_procedure", "used_for")),
    ("anatomy", re.compile(r"\b(?:nerede|konum|komşu|ilişki|yakın|geçer|seyreder|anatom)\b", re.I),
     ("anatomy", "relation"), ("anatomical_relation", "part_of")),
    ("visual", re.compile(r"\b(?:radyografi|röntgen|film|görüntü|fotoğraf|panoramik|opg|cbct|periapikal|bitewing|sefalogram|şekil|tablo|grafik)\b", re.I),
     ("imaging", "finding", "anatomy"), ("used_for", "anatomical_relation")),
    ("comparison", re.compile(r"\b(?:fark[a-zçğıöşü]*|karşılaştır[a-zçğıöşü]*|versus|vs\.?|hangisi daha)\b", re.I),
     ("measurement", "diagnosis", "finding", "material", "procedure"), ()),
    ("cause", re.compile(r"\b(?:neden|niçin|sebep|etyoloji|etiyoloji|patogenez)\b", re.I),
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

def build_dental_requirement_plan(query: str) -> DentalRequirementPlan:
    """Separate what the user asks about from which facts they request."""
    from app.dental_knowledge_graph import matched_nodes
    clean = " ".join((query or "").split())
    intents = classify_dental_intents(clean, limit=6)
    nodes = matched_nodes(clean)
    subject_ids = tuple(dict.fromkeys(node.id for node in nodes))
    subject_terms = tuple(dict.fromkeys(node.label for node in nodes))
    specialties = tuple(dict.fromkeys(node.specialty for node in nodes if node.specialty != "general"))
    facets = tuple(intent.name for intent in intents if intent.name != "general")
    return DentalRequirementPlan(
        subject_node_ids=subject_ids,
        subject_terms=subject_terms,
        intents=intents,
        requested_facets=facets,
        relation_hints=combined_relation_hints(intents, limit=16),
        specialties=specialties,
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
    """Detect student study-generation requests without affecting normal QA."""
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
