"""Local dental semantic features shared by indexing and retrieval.

No provider calls. Features are evidence-selection metadata, never an answer source.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from app.dental_knowledge_graph import matched_nodes

_VALUE_RE = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?\s*(?:°|mm|cm|%|mg|ml|g|µm|μm)\b?", re.I)
_FDI_RE = re.compile(r"(?<!\d)(?:1[1-8]|2[1-8]|3[1-8]|4[1-8]|5[1-5]|6[1-5]|7[1-5]|8[1-5])(?!\d)")
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

def analyze_dental_text(text: str) -> DentalSemanticFeatures:
    clean = " ".join((text or "").split())
    nodes = matched_nodes(clean)
    return DentalSemanticFeatures(
        node_ids=tuple(dict.fromkeys(node.id for node in nodes)),
        specialties=tuple(dict.fromkeys(node.specialty for node in nodes if node.specialty != "general")),
        kinds=tuple(dict.fromkeys(node.kind for node in nodes)),
        measurements=tuple(dict.fromkeys(m.group(0).strip() for m in _VALUE_RE.finditer(clean))),
        tooth_numbers=tuple(dict.fromkeys(m.group(0) for m in _FDI_RE.finditer(clean))),
        imaging_types=tuple(name for name, pattern in _IMAGING if pattern.search(clean)),
    )

def semantic_overlap_score(query: DentalSemanticFeatures, chunk: DentalSemanticFeatures) -> float:
    score = 0.0
    qnodes, cnodes = set(query.node_ids), set(chunk.node_ids)
    if qnodes:
        score += 0.55 * (len(qnodes & cnodes) / len(qnodes))
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


def retrieval_enrichment_text(text: str, *, max_terms: int = 24) -> str:
    """Canonical dental terms appended only to the retrieval document.

    Original evidence text remains untouched for citations and generation.
    """
    features = analyze_dental_text(text)
    nodes = matched_nodes(text)
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
