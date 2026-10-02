"""Local dental semantic features shared by indexing and retrieval.

No provider calls. Features are evidence-selection metadata, never an answer source.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from app.dental_knowledge_graph import matched_nodes

_VALUE_RE = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?\s*(?:°|mm|cm|%|mg|ml|g|µm|μm)(?!\w)", re.I)

_NUMBER_WORD = r"(?:sıfır|bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on|yirmi|otuz|kırk|elli|altmış|yetmiş|seksen|doksan|yüz)"
_NUMBER_PHRASE = rf"{_NUMBER_WORD}(?:\s+{_NUMBER_WORD}){{0,3}}"
_NUMERIC = r"[+-]?\d+(?:[.,]\d+)?"
_VALUE_UNIT = r"(?:°|mm|cm|%|mg|ml|g|µm|μm|derece|milimetre|santimetre|mikrometre|miligram|mililitre|gram)"
_EXPLICIT_VALUE_LABEL = r"(?:normal\s+değer(?:i)?|referans\s+değer(?:i)?|ortalama(?:\s+değer(?:i)?)?|değer(?:i)?|oran(?:ı)?)"
_VALUE_CANDIDATE_RE = re.compile(
    rf"(?iu)(?:"
    rf"(?P<unit>{_NUMERIC}\s*{_VALUE_UNIT})"
    rf"|(?P<percent>yüzde\s+(?:{_NUMERIC}|{_NUMBER_PHRASE}))"
    rf"|(?P<wordunit>{_NUMBER_PHRASE}\s+(?:derece|milimetre|santimetre|mikrometre))"
    rf"|(?P<label>{_EXPLICIT_VALUE_LABEL}\s*(?:=|:|ise|olarak)?\s*(?:{_NUMERIC}|(?!yüzde\b){_NUMBER_PHRASE}))"
    rf"|(?P<range>(?:{_NUMERIC}|{_NUMBER_PHRASE})\s*(?:[-–—]|ile|ila)\s*(?:{_NUMERIC}|{_NUMBER_PHRASE})(?:\s*{_VALUE_UNIT})?)"
    rf")"
)
_COUNT_UNIT_RE = re.compile(r"(?iu)\b(?:adet\s+)?(?:kök|kanal|tüberkül|cusp|kuspit|diş|yüzey)\b")
_NON_VALUE_CONTEXT_RE = re.compile(
    r"(?iu)\b(?:yaş(?:ında|ındaki)?|sayfa|sf\.?|page|hasta|olgu|vaka|katılımcı|örneklem|denek)\b"
)

@dataclass(frozen=True)
class ValueEvidence:
    text: str
    kind: str
    start: int
    end: int
    confidence: float


_REFERENCE_CUE_RE = re.compile(
    r"(?iu)\b(?:normal|referans|ortalama|genellikle|çoğunlukla|tipik(?: olarak)?|"
    r"beklenen|fizyolojik|standart|ideal|kabul edilen)\b"
)
_OBSERVATION_CUE_RE = re.compile(
    r"(?iu)\b(?:hasta|olgu|vaka|birey|örnek|örneklem|denek|katılımcı|"
    r"ölçüldü|ölçülen|saptandı|bulundu|gözlendi|tespit edildi|bu hastada|bu olguda)\b"
)
_VARIABILITY_CUE_RE = re.compile(
    r"(?iu)\b(?:değişebilir|değişken|arasında değişir|kişiden kişiye|bireysel|"
    r"yaşa göre|cinsiyete göre|vakaya göre|hastaya göre)\b"
)
_STRONG_ASSERTION_RE = re.compile(
    r"(?iu)\b(?:kesinlikle|daima|her zaman|zorunlu olarak|mutlaka)\b"
)

def classify_value_assertion(text: str, evidence: ValueEvidence) -> tuple[str, float]:
    """Classify what a numeric expression claims, not merely that it exists.

    reference: normative/general teaching statement
    observation: patient/sample/example-specific result
    variable: explicitly context-dependent value
    asserted: strong universal wording without a reference cue
    unknown: numeric evidence whose role is not safely inferable locally
    """
    clean = " ".join((text or "").split())
    left = clean[max(0, evidence.start - 96):evidence.start]
    right = clean[evidence.end:min(len(clean), evidence.end + 96)]
    local = f"{left} {evidence.text} {right}"
    if _VARIABILITY_CUE_RE.search(local):
        return "variable", 0.96
    reference = bool(_REFERENCE_CUE_RE.search(local))
    observation = bool(_OBSERVATION_CUE_RE.search(local))
    if reference and not observation:
        return "reference", 0.95
    if observation and not reference:
        return "observation", 0.94
    if reference and observation:
        # "Hastalarda ortalama 4 mm" is population/sample evidence, not a
        # universal reference value unless another passage establishes that.
        return "observation", 0.82
    if _STRONG_ASSERTION_RE.search(local):
        return "asserted", 0.86
    return "unknown", min(0.70, evidence.confidence)

@dataclass(frozen=True)
class BoundValueEvidence:
    value: ValueEvidence
    assertion: str
    assertion_confidence: float
    subject_node_id: str | None
    subject_text: str | None
    binding_confidence: float
    qualifiers: tuple[str, ...] = ()
    context_text: str | None = None

_VALUE_QUALIFIER_PATTERNS = (
    ("newborn", re.compile(r"(?iu)\b(?:yeni\s*doğmuş|yenidoğan|newborn)\w*\b")),
    ("infant", re.compile(r"(?iu)\b(?:bebeklik|bebek)\w*\b")),
    ("child", re.compile(r"(?iu)\b(?:çocuk|çocukluk)\w*\b")),
    ("adult", re.compile(r"(?iu)\b(?:erişkin|yetişkin|adult)\w*\b")),
    ("fetal", re.compile(r"(?iu)\b(?:fetüs|fetus|fetal)\w*\b")),
    ("growth", re.compile(r"(?iu)\b(?:büyüme|gelişim|yaşın ilerlemesi|yaşa bağlı)\b")),
)
_CONTEXT_SIZE_RE = re.compile(r"(?iu)\b\d+(?:[.,]\d+)?\s*mm(?:'lik|lik|lık|luk|lük)?\s+(?:bir\s+)?(?:fetüs|fetus|embriyon)\w*\b")

def _value_context(text: str, evidence: ValueEvidence) -> tuple[tuple[str, ...], str]:
    left = max(0, evidence.start - 120)
    right = min(len(text), evidence.end + 120)
    local = text[left:right]
    qualifiers = [name for name, pattern in _VALUE_QUALIFIER_PATTERNS if pattern.search(local)]
    for match in _CONTEXT_SIZE_RE.finditer(local):
        qualifiers.append("context_size:" + re.sub(r"\s+", " ", match.group(0)).strip())
    return tuple(dict.fromkeys(qualifiers)), local

_LEXICAL_SUBJECT_RE = re.compile(
    r"(?iu)([A-Za-zÇĞİÖŞÜçğıöşü][\wÇĞİÖŞÜçğıöşü-]*(?:\s+[A-Za-zÇĞİÖŞÜçğıöşü][\wÇĞİÖŞÜçğıöşü-]*){0,3})"
)
_SUBJECT_STOPWORDS = {
    "normal", "değer", "değeri", "ortalama", "yaklaşık", "oran", "yüzde", "hasta", "olgu", "vaka",
    "referans", "standart", "ideal", "beklenen", "bulundu", "ölçüldü", "saptandı", "iken", "için",
}

def _lexical_subject_before_value(text: str, evidence: ValueEvidence) -> tuple[str | None, float]:
    left = text[max(0, evidence.start - 96):evidence.start]
    # Prefer the final noun-like phrase before a value, while stripping value/assertion boilerplate.
    candidates = []
    for match in _LEXICAL_SUBJECT_RE.finditer(left):
        phrase = " ".join(match.group(1).split()).strip(" ,;:()")
        words = phrase.casefold().split()
        while words and words[-1] in _SUBJECT_STOPWORDS:
            words.pop()
        if not words:
            continue
        phrase = " ".join(words[-4:])
        if phrase in _SUBJECT_STOPWORDS or len(phrase) < 2:
            continue
        distance = len(left) - match.end()
        candidates.append((max(0.0, 0.72 - distance / 160.0), phrase))
    if not candidates:
        return None, 0.0
    candidates.sort(reverse=True)
    return candidates[0][1], round(candidates[0][0], 4)

def bind_value_evidence(text: str) -> tuple[BoundValueEvidence, ...]:
    """Bind values to nearby subjects conservatively; ambiguity stays unbound."""
    clean = " ".join((text or "").split())
    nodes = matched_nodes(clean)
    mentions: list[tuple[int, int, str, str]] = []
    lowered = clean.casefold()
    for node in nodes:
        aliases = tuple(dict.fromkeys((node.label, *node.aliases)))
        for alias in aliases:
            term = " ".join((alias or "").casefold().split())
            if not term:
                continue
            pattern = re.compile(r"(?<!\w)" + re.escape(term).replace(r"\ ", r"\s+") + r"(?!\w)", re.I)
            for match in pattern.finditer(lowered):
                mentions.append((match.start(), match.end(), node.id, clean[match.start():match.end()]))
    output: list[BoundValueEvidence] = []
    for value in extract_value_evidence(clean):
        assertion, assertion_confidence = classify_value_assertion(clean, value)
        ranked = []
        for start, end, node_id, subject_text in mentions:
            distance = value.start - end if end <= value.start else start - value.end if start >= value.end else 0
            if distance < 0 or distance > 96:
                continue
            between = clean[min(end, value.end):max(start, value.start)]
            clause_break = bool(re.search(r"[.;!?]", between))
            score = max(0.0, 1.0 - (distance / 96.0)) - (0.45 if clause_break else 0.0)
            ranked.append((score, distance, node_id, subject_text))
        ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
        chosen = ranked[0] if ranked and ranked[0][0] >= 0.34 else None
        if chosen and len(ranked) > 1 and ranked[1][0] >= chosen[0] - 0.08 and ranked[1][2] != chosen[2]:
            chosen = None
        qualifiers, context_text = _value_context(clean, value)
        lexical_subject, lexical_confidence = _lexical_subject_before_value(clean, value)
        output.append(BoundValueEvidence(
            value=value, assertion=assertion, assertion_confidence=assertion_confidence,
            subject_node_id=chosen[2] if chosen else None,
            subject_text=chosen[3] if chosen else lexical_subject,
            binding_confidence=round(chosen[0], 4) if chosen else lexical_confidence,
            qualifiers=qualifiers,
            context_text=context_text,
        ))
    return tuple(output)

@dataclass(frozen=True)
class ValueReconciliation:
    status: str
    reference_values: tuple[str, ...]
    observation_values: tuple[str, ...]
    variable_values: tuple[str, ...]
    unknown_values: tuple[str, ...]

def _value_key(value: str) -> str:
    key = " ".join((value or "").casefold().split())
    key = key.replace("derecedir", "°").replace("derece", "°")
    key = key.replace(",", ".")
    key = re.sub(r"(?<=\d)\.0(?=\s*(?:°|mm|cm|%|$))", "", key)
    return re.sub(r"\s+", "", key)

def reconcile_value_evidence(items: tuple[BoundValueEvidence, ...] | list[BoundValueEvidence]) -> ValueReconciliation:
    """Reconcile only comparable contexts; conditioned values remain separate."""
    references, observations, variables, unknowns = [], [], [], []
    reference_groups: dict[tuple[str, ...], dict[str, str]] = {}
    for item in items:
        if item.assertion == "reference":
            references.append(item.value.text)
            subject_key = (item.subject_node_id or item.subject_text or "").casefold().strip()
            group = (subject_key, *tuple(sorted(item.qualifiers)))
            reference_groups.setdefault(group, {})[_value_key(item.value.text)] = item.value.text
        elif item.assertion == "observation":
            observations.append(item.value.text)
        elif item.assertion == "variable":
            variables.append(item.value.text)
        else:
            unknowns.append(item.value.text)
    references = list(dict.fromkeys(references)); observations = list(dict.fromkeys(observations))
    variables = list(dict.fromkeys(variables)); unknowns = list(dict.fromkeys(unknowns))
    comparable_conflict = any(len(values) > 1 for values in reference_groups.values())
    conditioned_reference = len(reference_groups) > 1
    if variables or conditioned_reference:
        status = "conditioned"
    elif comparable_conflict:
        status = "conflict"
    elif references:
        status = "reference_supported"
    elif observations:
        status = "observations_only"
    else:
        status = "insufficient"
    return ValueReconciliation(status, tuple(references), tuple(observations), tuple(variables), tuple(unknowns))

def extract_value_evidence(text: str) -> tuple[ValueEvidence, ...]:
    """Find answer-bearing values without requiring a pre-known dental term."""
    clean = " ".join((text or "").split())
    output: list[ValueEvidence] = []
    for match in _VALUE_CANDIDATE_RE.finditer(clean):
        value = match.group(0).strip()
        left = clean[max(0, match.start() - 32):match.start()]
        # Bare ranges beside age/page/sample language are metadata, not a
        # clinical value. Explicit labels/units remain strong evidence.
        strong = match.lastgroup in {"unit", "percent", "wordunit", "label"}
        if not strong and _NON_VALUE_CONTEXT_RE.search(left):
            continue
        kind = {
            "unit": "measurement", "percent": "percentage",
            "wordunit": "measurement", "label": "value", "range": "range",
        }.get(match.lastgroup or "", "value")
        candidate = ValueEvidence(value, kind, match.start(), match.end(), 0.96 if strong else 0.78)
        overlaps = [item for item in output if not (candidate.end <= item.start or candidate.start >= item.end)]
        if overlaps:
            best = max(tuple(overlaps) + (candidate,), key=lambda item: (item.end - item.start, item.confidence))
            output = [item for item in output if item not in overlaps]
            output.append(best)
        else:
            output.append(candidate)
    output.sort(key=lambda item: (item.start, item.end))
    return tuple(output)

_FDI_RE = re.compile(r"(?<!\d)(?:1[1-8]|2[1-8]|3[1-8]|4[1-8]|5[1-5]|6[1-5]|7[1-5]|8[1-5])(?!\d)")
_TOOTH_CONTEXT_RE = re.compile(r"\b(?:diş|dis|tooth|numara(?:lı)?|no\.?|#)\b", re.I)
_DENTAL_NUMBER_CONTEXT_RE = re.compile(
    r"\b(?:molar|premolar|kanin|kesici|incisor|canine|periodontal|endodont|"
    r"çekim|implant|kök|apikal|furkasyon|oklüz|mandibul|maxill)\w*\b", re.I
)

_NON_TOOTH_NUMBER_SUFFIX_RE = re.compile(r"^\s*(?:yaş(?:ında|ındaki)?|sayfa|sf\.?|page)\b", re.I)
_NON_TOOTH_NUMBER_PREFIX_RE = re.compile(r"(?:sayfa|sf\.?|page)\s*$", re.I)

def _fdi_numbers(text: str) -> tuple[str, ...]:
    matches = list(_FDI_RE.finditer(text))
    if not matches:
        return ()
    # Bare two-digit numbers are common as ages, page numbers and measurements.
    # Accept FDI notation only when the local sentence/window is dentally anchored.
    result: list[str] = []
    for match in matches:
        left = max(0, match.start() - 42)
        right = min(len(text), match.end() + 42)
        window = text[left:right]
        prefix = text[max(0, match.start() - 14):match.start()]
        suffix = text[match.end():min(len(text), match.end() + 18)]
        # Ages/page references can sit in the same sentence as a real tooth
        # number. Dental context must not convert them into FDI identities.
        if (_NON_TOOTH_NUMBER_PREFIX_RE.search(prefix)
                or _NON_TOOTH_NUMBER_SUFFIX_RE.search(suffix)):
            continue
        if _TOOTH_CONTEXT_RE.search(window) or _DENTAL_NUMBER_CONTEXT_RE.search(window):
            result.append(match.group(0))
    return tuple(dict.fromkeys(result))
_IMAGING = (
    ("cbct", re.compile(r"\b(?:CBCT|cone beam|konik ışınlı)\b", re.I)),
    ("panoramic", re.compile(r"\b(?:panoramik|OPG|orthopantomogram)\b", re.I)),
    ("periapical", re.compile(r"\b(?:periapikal|periapical)\b", re.I)),
    ("bitewing", re.compile(r"\b(?:bitewing|bite-wing)\b", re.I)),
    ("cephalometric", re.compile(r"\b(?:sefalometrik|sefalogram|cephalometric)\b", re.I)),
)

@dataclass(frozen=True)
class DentalSemanticFeatures:
    node_ids: tuple[str, ...]
    specialties: tuple[str, ...]
    kinds: tuple[str, ...]
    measurements: tuple[str, ...]
    tooth_numbers: tuple[str, ...]
    imaging_types: tuple[str, ...]
    negated_node_ids: tuple[str, ...] = ()

def analyze_dental_text(text: str) -> DentalSemanticFeatures:
    clean = " ".join((text or "").split())
    nodes = matched_nodes(clean)
    negated: list[str] = []
    lowered = clean.casefold()
    negator = re.compile(
        r"\\b(?:yok|değil|izlenmedi|saptanmadı|görülmedi|bulunmadı|"
        r"without|no|not)\\b",
        re.I,
    )
    for node in nodes:
        mention_states: list[bool] = []
        for alias in (node.label, *node.aliases):
            term = " ".join((alias or "").casefold().split())
            if not term:
                continue
            escaped = re.escape(term).replace(r"\\ ", r"\\s+")
            for match in re.finditer(r"(?<!\\w)" + escaped + r"(?!\\w)", lowered, flags=re.I):
                # Clause-local preceding context: punctuation/conjunctions stop a
                # negator from leaking across unrelated statements.
                before = lowered[max(0, match.start() - 56):match.start()]
                before = re.split(r"[.;!?]|\b(?:ama|ancak|fakat|but|however)\b", before)[-1]
                after = lowered[match.end():min(len(lowered), match.end() + 48)]
                after = re.split(r"[.;!?]|\b(?:ama|ancak|fakat|but|however)\b", after)[0]
                negation_markers = (
                    "yok", "değil", "izlenmedi", "saptanmadı", "görülmedi",
                    "bulunmadı", "without", " no ", " not ",
                )
                local_context = f" {before} {after} "
                mention_states.append(
                    bool(negator.search(before) or negator.search(after))
                    or any(marker in local_context for marker in negation_markers)
                )
        # Mixed positive/negative mentions are not collapsed into a negative
        # concept. Preserve positive evidence unless every mention is negated.
        if mention_states and all(mention_states):
            negated.append(node.id)
    return DentalSemanticFeatures(
        node_ids=tuple(dict.fromkeys(node.id for node in nodes)),
        specialties=tuple(dict.fromkeys(node.specialty for node in nodes if node.specialty != "general")),
        kinds=tuple(dict.fromkeys(node.kind for node in nodes)),
        measurements=tuple(dict.fromkeys(m.group(0).strip() for m in _VALUE_RE.finditer(clean))),
        tooth_numbers=_fdi_numbers(clean),
        imaging_types=tuple(name for name, pattern in _IMAGING if pattern.search(clean)),
        negated_node_ids=tuple(dict.fromkeys(negated)),
    )

def semantic_overlap_score(query: DentalSemanticFeatures, chunk: DentalSemanticFeatures) -> float:
    score = 0.0
    qnodes, cnodes = set(query.node_ids), set(chunk.node_ids)
    # Do not reward a chunk as positive evidence when the queried concept is
    # explicitly negated in that chunk. It may still be useful as contrast.
    positive_cnodes = cnodes - set(chunk.negated_node_ids)
    if qnodes:
        score += 0.55 * (len(qnodes & positive_cnodes) / len(qnodes))
    qspec, cspec = set(query.specialties), set(chunk.specialties)
    if qspec and qspec & cspec:
        score += 0.12
    qkind, ckind = set(query.kinds), set(chunk.kinds)
    if qkind and qkind & ckind:
        score += 0.08
    qteeth, cteeth = set(query.tooth_numbers), set(chunk.tooth_numbers)
    if qteeth:
        score += 0.15 * (len(qteeth & cteeth) / len(qteeth))
    qimg, cimg = set(query.imaging_types), set(chunk.imaging_types)
    if qimg and qimg & cimg:
        score += 0.10
    return min(1.0, score)


def retrieval_enrichment_text(
    text: str, *, features: DentalSemanticFeatures | None = None, max_terms: int = 24
) -> str:
    """Canonical dental terms appended only to the retrieval document.

    Original evidence text remains untouched for citations and generation.
    A precomputed fingerprint avoids re-running semantic analysis while indexing.
    """
    features = features or analyze_dental_text(text)
    node_by_id = {node.id: node for node in matched_nodes(text)}
    nodes = [node_by_id[node_id] for node_id in features.node_ids if node_id in node_by_id]
    terms: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        for value in (node.label, node.specialty, node.kind):
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                terms.append(value)
            if len(terms) >= max_terms:
                return " ".join(terms)
    for value in (*features.imaging_types, *features.tooth_numbers):
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            terms.append(value)
        if len(terms) >= max_terms:
            break
    return " ".join(terms)
