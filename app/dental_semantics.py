"""Local dental semantic features shared by indexing and retrieval.

No provider calls. Features are evidence-selection metadata, never an answer source.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from app.dental_knowledge_graph import matched_nodes

_VALUE_RE = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?\s*(?:°|mm|cm|%|mg|ml|g|µm|μm)(?!\w)", re.I)
_FDI_RE = re.compile(r"(?<!\d)(?:1[1-8]|2[1-8]|3[1-8]|4[1-8]|5[1-5]|6[1-5]|7[1-5]|8[1-5])(?!\d)")
_TOOTH_CONTEXT_RE = re.compile(r"\b(?:diş|dis|tooth|numara(?:lı)?|no\.?|#)\b", re.I)
_DENTAL_NUMBER_CONTEXT_RE = re.compile(
    r"\b(?:molar|premolar|kanin|kesici|incisor|canine|periodontal|endodont|"
    r"çekim|implant|kök|apikal|furkasyon|oklüz|mandibul|maxill)\w*\b", re.I
)

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
                window = lowered[max(0, match.start() - 56):match.start()]
                window = re.split(r"[.;!?]|\\b(?:ama|ancak|fakat|but|however)\\b", window)[-1]
                mention_states.append(bool(negator.search(window)))
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
