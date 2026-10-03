"""Curated dental knowledge graph used only for retrieval expansion.

The graph proposes where to search. It is never a factual answer source:
user-visible answers must still be grounded in the uploaded course material.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import functools
import re

from app.dental_specialty_concepts import SPECIALTY_CONCEPTS
from app.dental_specialty_concepts_extended import EXTENDED_SPECIALTY_CONCEPTS


class Relation(str, Enum):
    ALIAS_OF = "alias_of"
    MEASURES = "measures"
    PART_OF = "part_of"
    ANATOMICAL_RELATION = "anatomical_relation"
    USED_FOR = "used_for"
    CLASSIFIED_BY = "classified_by"
    ASSOCIATED_WITH = "associated_with"
    DEFINED_AS = "defined_as"
    HAS_FEATURE = "has_feature"
    CAUSED_BY = "caused_by"
    HAS_MECHANISM = "has_mechanism"
    LEADS_TO = "leads_to"
    MANIFESTS_AS = "manifests_as"
    ASSESSED_BY = "assessed_by"
    HAS_TREATMENT = "has_treatment"
    HAS_INDICATION = "has_indication"
    HAS_CONTRAINDICATION = "has_contraindication"
    HAS_COMPLICATION = "has_complication"
    HAS_PROCEDURE = "has_procedure"
    HAS_MATERIAL = "has_material"
    HAS_RISK_FACTOR = "has_risk_factor"
    HAS_OUTCOME = "has_outcome"
    HAS_PROGNOSIS = "has_prognosis"
    HAS_STAGE = "has_stage"
    HAS_GRADE = "has_grade"
    HAS_RADIOGRAPHIC_FEATURE = "has_radiographic_feature"
    HAS_CLINICAL_FEATURE = "has_clinical_feature"
    DIFFERENTIAL_WITH = "differential_with"
    TREATS = "treats"
    PREVENTS = "prevents"


@dataclass(frozen=True)
class DentalNode:
    id: str
    label: str
    specialty: str
    kind: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class DentalEdge:
    source: str
    relation: Relation
    target: str
    weight: float


NODES = (
    # Shared anatomy / diagnostics
    DentalNode("mandible", "mandibula", "general", "anatomy", ("alt çene", "lower jaw")),
    DentalNode("maxilla", "maksilla", "general", "anatomy", ("üst çene", "upper jaw")),
    DentalNode("cranial_base", "kranial kaide", "orthodontics", "anatomy", ("kafa kaidesi", "cranial base")),
    DentalNode("sagittal_position", "sagittal konum", "orthodontics", "property", ("ön-arka konum", "anteroposterior position")),
    DentalNode("sna", "SNA", "orthodontics", "measurement", ("sella nasion A",)),
    DentalNode("snb", "SNB", "orthodontics", "measurement", ("sella nasion B",)),
    DentalNode("anb", "ANB", "orthodontics", "measurement", ("A-N-B",)),
    DentalNode("wits", "Wits", "orthodontics", "measurement", ("Wits appraisal", "Wits analizi")),
    DentalNode("skeletal_relation", "iskeletsel sagittal ilişki", "orthodontics", "property", ("çeneler arası sagittal ilişki",)),
    DentalNode("malocclusion", "maloklüzyon", "orthodontics", "finding", ("malocclusion",)),

    # Endodontics
    DentalNode("root_canal", "kök kanal sistemi", "endodontics", "anatomy", ("root canal system",)),
    DentalNode("working_length", "çalışma boyu", "endodontics", "measurement", ("working length", "WL")),
    DentalNode("apical_constriction", "apikal konstriksiyon", "endodontics", "anatomy", ("apical constriction", "minor diameter")),
    DentalNode("apical_foramen", "apikal foramen", "endodontics", "anatomy", ("apical foramen", "major diameter")),
    DentalNode("pulpitis", "pulpitis", "endodontics", "diagnosis", ("pulpa iltihabı",)),
    DentalNode("pulp_necrosis", "pulpa nekrozu", "endodontics", "diagnosis", ("pulp necrosis", "necrotic pulp")),

    # Periodontology
    DentalNode("periodontal_pocket", "periodontal cep", "periodontology", "finding", ("periodontal pocket", "cep")),
    DentalNode("probing_depth", "sondalama derinliği", "periodontology", "measurement", ("probing depth", "PD")),
    DentalNode("attachment_loss", "klinik ataşman kaybı", "periodontology", "measurement", ("clinical attachment loss", "CAL")),
    DentalNode("bop", "sondalamada kanama", "periodontology", "finding", ("bleeding on probing", "BOP")),
    DentalNode("alveolar_bone", "alveol kemiği", "periodontology", "anatomy", ("alveolar bone",)),
    DentalNode("bone_loss", "kemik kaybı", "periodontology", "finding", ("bone loss", "alveolar bone loss")),

    # Oral surgery / radiology
    DentalNode("third_molar", "üçüncü molar", "oral_surgery", "anatomy", ("yirmi yaş dişi", "third molar", "wisdom tooth")),
    DentalNode("impaction", "gömülülük", "oral_surgery", "finding", ("gömülü", "impacted", "impaksiyon")),
    DentalNode("ian", "inferior alveolar sinir", "oral_surgery", "anatomy", ("inferior alveolar nerve", "IAN")),
    DentalNode("mandibular_canal", "mandibular kanal", "radiology", "anatomy", ("mandibular canal", "inferior alveolar canal")),
    DentalNode("panoramic", "panoramik radyografi", "radiology", "imaging", ("panoramic radiograph", "OPG", "orthopantomogram")),
    DentalNode("cbct", "CBCT", "radiology", "imaging", ("cone beam computed tomography", "konik ışınlı bilgisayarlı tomografi")),

    # Prosthodontics / occlusion
    DentalNode("vdo", "dikey boyut", "prosthodontics", "measurement", ("vertical dimension", "VDO", "vertical dimension of occlusion")),
    DentalNode("centric_relation", "sentrik ilişki", "prosthodontics", "relation", ("centric relation", "CR")),
    DentalNode("mip", "maksimum interküspidasyon", "prosthodontics", "relation", ("maximum intercuspation", "MIP")),
    DentalNode("occlusion", "oklüzyon", "prosthodontics", "relation", ("occlusion",)),

    # Restorative / cariology / pediatric
    DentalNode("caries", "dental çürük", "restorative", "diagnosis", ("çürük", "karies", "caries", "dental caries")),
    DentalNode("enamel", "mine", "restorative", "tissue", ("enamel",)),
    DentalNode("dentin", "dentin", "restorative", "tissue", ("dentine",)),
    DentalNode("ecc", "erken çocukluk çağı çürüğü", "pediatric_dentistry", "diagnosis", ("early childhood caries", "ECC")),
    DentalNode("primary_tooth", "süt dişi", "pediatric_dentistry", "anatomy", ("primer diş", "primary tooth", "deciduous tooth")),

    # TMD
    DentalNode("tmj", "temporomandibular eklem", "tmd", "anatomy", ("çene eklemi", "TME", "TMJ", "temporomandibular joint")),
    DentalNode("condyle", "kondil", "tmd", "anatomy", ("condyle", "mandibular condyle")),
    DentalNode("articular_disc", "artiküler disk", "tmd", "anatomy", ("articular disc", "eklem diski")),
)

EDGES = (
    DentalEdge("sna", Relation.MEASURES, "maxilla", 1.0),
    DentalEdge("sna", Relation.USED_FOR, "sagittal_position", 1.0),
    DentalEdge("snb", Relation.MEASURES, "mandible", 1.0),
    DentalEdge("snb", Relation.USED_FOR, "sagittal_position", 1.0),
    DentalEdge("sna", Relation.ANATOMICAL_RELATION, "cranial_base", 0.95),
    DentalEdge("snb", Relation.ANATOMICAL_RELATION, "cranial_base", 0.95),
    DentalEdge("anb", Relation.MEASURES, "skeletal_relation", 1.0),
    DentalEdge("wits", Relation.MEASURES, "skeletal_relation", 1.0),
    DentalEdge("malocclusion", Relation.CLASSIFIED_BY, "skeletal_relation", 0.65),

    DentalEdge("working_length", Relation.PART_OF, "root_canal", 0.9),
    DentalEdge("working_length", Relation.ANATOMICAL_RELATION, "apical_constriction", 0.9),
    DentalEdge("apical_constriction", Relation.ANATOMICAL_RELATION, "apical_foramen", 0.8),

    DentalEdge("probing_depth", Relation.MEASURES, "periodontal_pocket", 1.0),
    DentalEdge("attachment_loss", Relation.ASSOCIATED_WITH, "periodontal_pocket", 0.65),
    DentalEdge("bop", Relation.ASSOCIATED_WITH, "periodontal_pocket", 0.65),
    DentalEdge("bone_loss", Relation.ANATOMICAL_RELATION, "alveolar_bone", 0.9),

    DentalEdge("third_molar", Relation.ASSOCIATED_WITH, "impaction", 0.7),
    DentalEdge("third_molar", Relation.ANATOMICAL_RELATION, "ian", 0.8),
    DentalEdge("ian", Relation.ANATOMICAL_RELATION, "mandibular_canal", 1.0),
    DentalEdge("panoramic", Relation.USED_FOR, "third_molar", 0.6),
    DentalEdge("cbct", Relation.USED_FOR, "mandibular_canal", 0.75),

    DentalEdge("centric_relation", Relation.ASSOCIATED_WITH, "occlusion", 0.7),
    DentalEdge("mip", Relation.ASSOCIATED_WITH, "occlusion", 0.7),
    DentalEdge("vdo", Relation.ASSOCIATED_WITH, "occlusion", 0.6),

    DentalEdge("ecc", Relation.ASSOCIATED_WITH, "caries", 0.9),
    DentalEdge("caries", Relation.ANATOMICAL_RELATION, "enamel", 0.6),
    DentalEdge("caries", Relation.ANATOMICAL_RELATION, "dentin", 0.6),

    DentalEdge("condyle", Relation.PART_OF, "tmj", 1.0),
    DentalEdge("articular_disc", Relation.PART_OF, "tmj", 1.0),
)

def _merge_specialty_nodes() -> tuple[DentalNode, ...]:
    """Merge repeated concept ids deterministically instead of silent overwrite."""
    merged: dict[str, DentalNode] = {}
    order: list[str] = []
    for packs in (SPECIALTY_CONCEPTS, EXTENDED_SPECIALTY_CONCEPTS):
        for specialty, concepts in packs.items():
            for concept_id, label, aliases, kind in concepts:
                current = merged.get(concept_id)
                if current is None:
                    merged[concept_id] = DentalNode(concept_id, label, specialty, kind, tuple(aliases))
                    order.append(concept_id)
                    continue
                # Same canonical concept may be enriched by later vocabulary packs,
                # but conflicting specialty/kind definitions are programming errors.
                if current.specialty != specialty or current.kind != kind:
                    raise ValueError(
                        f"Conflicting dental concept {concept_id}: "
                        f"{current.specialty}/{current.kind} vs {specialty}/{kind}"
                    )
                aliases_seen = {current.label.casefold(), *(a.casefold() for a in current.aliases)}
                extra = tuple(
                    term for term in (label, *aliases)
                    if term.casefold() not in aliases_seen
                )
                merged[concept_id] = DentalNode(
                    current.id, current.label, current.specialty, current.kind,
                    current.aliases + extra,
                )
    return tuple(merged[concept_id] for concept_id in order)


_SPECIALTY_NODES = _merge_specialty_nodes()


def _merge_all_nodes() -> tuple[DentalNode, ...]:
    """Core graph ids are canonical; specialty packs may only enrich aliases."""
    merged: dict[str, DentalNode] = {node.id: node for node in NODES}
    order = [node.id for node in NODES]
    for node in _SPECIALTY_NODES:
        current = merged.get(node.id)
        if current is None:
            merged[node.id] = node
            order.append(node.id)
            continue
        aliases_seen = {current.label.casefold(), *(a.casefold() for a in current.aliases)}
        extra = tuple(
            term for term in (node.label, *node.aliases)
            if term.casefold() not in aliases_seen
        )
        merged[node.id] = DentalNode(
            current.id, current.label, current.specialty, current.kind,
            current.aliases + extra,
        )
    return tuple(merged[node_id] for node_id in order)


ALL_NODES = _merge_all_nodes()
if len({node.id for node in ALL_NODES}) != len(ALL_NODES):
    raise ValueError("Duplicate canonical dental node id")
_NODE_BY_ID = {node.id: node for node in ALL_NODES}


def node_label(node_id: str) -> str | None:
    node = _NODE_BY_ID.get(node_id)
    return node.label if node else None


def dental_graph_coverage() -> dict[str, object]:
    """Cheap structural coverage report for every canonical vocabulary node."""
    from app.dental_knowledge_relations import DENTAL_RELATION_EDGES

    all_edges = (*EDGES, *DENTAL_RELATION_EDGES)
    degree = {node.id: 0 for node in ALL_NODES}
    dangling_edges: list[tuple[str, str, str]] = []
    for edge in all_edges:
        if edge.source not in _NODE_BY_ID or edge.target not in _NODE_BY_ID:
            dangling_edges.append((edge.source, edge.relation.value, edge.target))
            continue
        degree[edge.source] += 1
        degree[edge.target] += 1
    orphan_ids = tuple(node_id for node_id, count in degree.items() if count == 0)
    return {
        "node_count": len(ALL_NODES),
        "edge_count": len(all_edges),
        "orphan_ids": orphan_ids,
        "dangling_edges": tuple(dangling_edges),
        "coverage_ratio": (len(ALL_NODES) - len(orphan_ids)) / max(1, len(ALL_NODES)),
    }


def _match_text(text: str) -> str:
    """Casefold while neutralizing Turkish capital İ's combining dot."""
    return " ".join((text or "").casefold().replace("\u0307", "").split())


def _term_present(text: str, term: str) -> bool:
    """Boundary-aware phrase match; short dental abbreviations must not hit substrings."""
    clean_term = _match_text(term)
    if not clean_term:
        return False
    escaped = re.escape(clean_term).replace(r"\ ", r"\s+")
    return bool(re.search(r"(?<!\w)" + escaped + r"(?!\w)", text, flags=re.IGNORECASE))

_AMBIGUOUS_SHORT_TERMS = {"cep", "pd", "cr", "cal", "wl", "mine"}
_DENTAL_CONTEXT_RE = re.compile(
    r"\b(?:diş|dental|periodontal|periodont|endodont|kanal|pulpa|oklüz|protez|"
    r"restoratif|dentin|çene|sefalometr|implant|radyograf|klinik|ataşman|"
    r"sondalama|santral ilişki|çalışma boyu|enamel|tooth|root|pulp)\w*\b", re.I
)

def _alias_pattern(term: str) -> str:
    """Canonical mention pattern shared by graph/semantic subject matching."""
    clean_term = _match_text(term)
    pieces: list[str] = []
    for word in clean_term.split():
        escaped = re.escape(word)
        # Turkish inflection is useful for substantive concept words but unsafe
        # for abbreviations/short aliases (PD, CR, CAL, WL, ANB, mine).
        if len(word) >= 4 and word.isalpha() and word not in _AMBIGUOUS_SHORT_TERMS:
            escaped += r"[a-zçğıöşü]{0,6}"
        pieces.append(escaped)
    return r"\s+".join(pieces)


def _term_context_ok(text: str, start: int, end: int, term: str) -> bool:
    if term.casefold() not in _AMBIGUOUS_SHORT_TERMS:
        return True
    window = text[max(0, start - 56):min(len(text), end + 56)]
    return bool(_DENTAL_CONTEXT_RE.search(window))

def _bounded_edit_distance(left: str, right: str, max_edits: int) -> int | None:
    """Return bounded Levenshtein distance; None means outside the safe radius."""
    if left == right:
        return 0
    if abs(len(left) - len(right)) > max_edits:
        return None
    previous = list(range(len(right) + 1))
    for i, lch in enumerate(left, 1):
        current = [i]
        for j, rch in enumerate(right, 1):
            cost = 0 if lch == rch else 1
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + cost))
        previous = current
    distance = previous[-1]
    return distance if distance <= max_edits else None


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    return _bounded_edit_distance(left, right, 1) is not None


def _safe_token_typo_distance(left: str, right: str) -> int | None:
    # Two edits are allowed only on long, distinctive dental words.  The caller
    # still requires a unique best node, so ambiguity fails closed.
    radius = 2 if min(len(left), len(right)) >= 10 else 1
    return _bounded_edit_distance(left, right, radius)


@functools.lru_cache(maxsize=1)
def _fuzzy_single_alias_buckets() -> dict[tuple[str, int], tuple[tuple[str, DentalNode], ...]]:
    """Pre-index distinctive aliases by first character and length.

    Typo rescue then compares a query token only with plausible aliases instead
    of scanning every graph node/alias and running Levenshtein each time.
    """
    buckets: dict[tuple[str, int], list[tuple[str, DentalNode]]] = {}
    for node in ALL_NODES:
        for term in (node.label, *node.aliases):
            clean = _match_text(term)
            if " " in clean or len(clean) < 7 or not clean.isalpha():
                continue
            buckets.setdefault((clean[0], len(clean)), []).append((clean, node))
    return {key: tuple(value) for key, value in buckets.items()}


@functools.lru_cache(maxsize=1)
def _fuzzy_multiword_aliases() -> tuple[tuple[tuple[str, ...], DentalNode], ...]:
    """Pre-tokenize the bounded 2-4 word phrase candidates once per process."""
    out = []
    for node in ALL_NODES:
        for term in (node.label, *node.aliases):
            words = tuple(re.findall(r"[a-zçğıöşü]{3,}", _match_text(term), flags=re.I))
            if 2 <= len(words) <= 4:
                out.append((words, node))
    return tuple(out)


def _fuzzy_long_alias_nodes(query: str, already: set[str]) -> list[DentalNode]:
    # Never fuzzy-match abbreviations or multiword aliases: one-edit fuzziness
    # there creates dangerous cross-concept seeds. This is only a typo rescue
    # for distinctive alphabetic dental terms such as "pulptis".
    tokens = re.findall(r"[a-zçğıöşü]{7,}", _match_text(query), flags=re.I)
    if not tokens:
        return []
    candidates: list[tuple[int, int, int, DentalNode]] = []
    buckets = _fuzzy_single_alias_buckets()
    for pos, token in enumerate(tokens):
        # Edit distance cannot bridge a length gap larger than the allowed
        # radius.  First-character bucketing removes the vast majority of
        # impossible graph aliases before Levenshtein is evaluated.
        radius = 2 if len(token) >= 10 else 1
        for alias_len in range(max(7, len(token) - radius), len(token) + radius + 1):
            for clean, node in buckets.get((token[0], alias_len), ()):
                if node.id in already:
                    continue
                distance = _safe_token_typo_distance(token, clean)
                if distance is not None:
                    candidates.append((distance, -len(clean), pos, node))
    # Also allow one typo inside a multiword canonical phrase when every
    # other word matches exactly. This keeps "mandbular kanal" recoverable
    # without enabling fuzzy abbreviations or broad phrase guessing.
    query_words = re.findall(r"[a-zçğıöşü]{3,}", _match_text(query), flags=re.I)
    for words, node in _fuzzy_multiword_aliases():
        if node.id in already or len(words) > len(query_words):
            continue
        for start in range(0, len(query_words) - len(words) + 1):
            window = query_words[start:start + len(words)]
            diffs = [i for i, (left, right) in enumerate(zip(window, words)) if left != right]
            if len(diffs) != 1:
                continue
            i = diffs[0]
            if len(words[i]) >= 7 and _edit_distance_at_most_one(window[i], words[i]):
                candidates.append((1, -sum(map(len, words)), start, node))
                break

    # A typo rescue is safe only when the best edit-distance candidate is
    # unambiguous. Equal-strength candidates mean "unknown", not permission to
    # guess a dental subject.
    ordered = sorted(candidates, key=lambda item: (item[0], item[1], item[2], item[3].id))
    if not ordered:
        return []
    best_strength = ordered[0][:3]
    best_nodes = []
    seen_best: set[str] = set()
    for distance, strength_len, position, node in ordered:
        if (distance, strength_len, position) != best_strength:
            break
        if node.id not in seen_best:
            seen_best.add(node.id)
            best_nodes.append(node)
    return best_nodes if len(best_nodes) == 1 else []


@functools.lru_cache(maxsize=1)
def _compiled_mention_patterns() -> tuple:
    """Compile every node/alias mention pattern once per process.

    The graph has more patterns than Python's 512-entry re cache, so compiling
    inside matched_nodes() recompiled hundreds of patterns on every query
    (~97% of query-understanding time). Patterns and flags are unchanged.
    """
    compiled = []
    for node in ALL_NODES:
        for term in (node.label, *node.aliases):
            clean_term = _match_text(term)
            if not clean_term:
                continue
            compiled.append((
                node, clean_term,
                re.compile(r"(?<!\w)" + _alias_pattern(clean_term) + r"(?!\w)", flags=re.I),
            ))
    return tuple(compiled)


_ASCII_FOLD = str.maketrans("çğıöşü", "cgiosu")


@functools.lru_cache(maxsize=1)
def _compiled_folded_patterns() -> tuple:
    """Same patterns as _compiled_mention_patterns, built from ASCII-folded terms."""
    compiled = []
    for node in ALL_NODES:
        for term in (node.label, *node.aliases):
            clean_term = _match_text(term)
            folded = clean_term.translate(_ASCII_FOLD)
            if not clean_term or folded == clean_term:
                continue  # nothing to fold: the exact pass already covered it
            pieces = []
            for word in folded.split():
                escaped = re.escape(word)
                if len(word) >= 4 and word.isalpha() and word not in _AMBIGUOUS_SHORT_TERMS:
                    escaped += r"[a-z]{0,6}"
                pieces.append(escaped)
            compiled.append((node, clean_term, re.compile(
                r"(?<!\w)" + r"\s+".join(pieces) + r"(?!\w)", flags=re.I)))
    return tuple(compiled)


def _ascii_fallback_nodes(lowered: str, already: set[str]) -> list[DentalNode]:
    """Users often type without Turkish letters (\"pulpitis tanisi\", \"cene\").

    Runs only when exact matching found no subject. Offsets are identical because
    the fold is one character to one character.
    """
    folded_text = lowered.translate(_ASCII_FOLD)
    if folded_text == lowered:
        return []
    mentions = []
    for node, clean_term, pattern in _compiled_folded_patterns():
        if node.id in already:
            continue
        for match in pattern.finditer(folded_text):
            if _term_context_ok(lowered, match.start(), match.end(), clean_term):
                mentions.append((match.start(), match.end(), len(clean_term), node))
    mentions.sort(key=lambda item: (-item[2], item[0], item[3].id))
    occupied: list[tuple[int, int]] = []
    out: list[DentalNode] = []
    seen: set[str] = set()
    for start, end, _, node in mentions:
        if any(start < used_end and end > used_start for used_start, used_end in occupied):
            continue
        occupied.append((start, end))
        if node.id not in seen:
            seen.add(node.id)
            out.append(node)
    return out


def matched_nodes(query: str) -> list[DentalNode]:
    """Find explicit entities using longest non-overlapping mentions.

    A shorter alias fully contained by a stronger phrase must not become a
    second graph seed; that is a common source of retrieval drift.
    """
    lowered = _match_text(query)
    mentions: list[tuple[int, int, int, DentalNode]] = []
    for node, clean_term, pattern in _compiled_mention_patterns():
        for match in pattern.finditer(lowered):
            if not _term_context_ok(lowered, match.start(), match.end(), clean_term):
                continue
            mentions.append((match.start(), match.end(), len(clean_term), node))
    mentions.sort(key=lambda item: (-item[2], item[0], item[3].id))
    occupied: list[tuple[int, int]] = []
    selected: list[DentalNode] = []
    seen: set[str] = set()
    for start, end, _, node in mentions:
        if any(start < used_end and end > used_start for used_start, used_end in occupied):
            continue
        occupied.append((start, end))
        if node.id not in seen:
            seen.add(node.id)
            selected.append(node)
    # Typo rescue normally runs only when exact matching found no canonical
    # subject. Imaging-only exact matches are constraints, however, so they must
    # not suppress recovery of one unambiguous long non-imaging subject typo
    # ("CBCT'de mandbular kanal ..."). Abbreviations remain non-fuzzy.
    exact_has_subject = any(node.kind != "imaging" for node in selected)
    if not exact_has_subject:
        folded_hits = _ascii_fallback_nodes(lowered, seen)
        if folded_hits:
            selected.extend(folded_hits)
            seen.update(node.id for node in folded_hits)
            exact_has_subject = any(node.kind != "imaging" for node in selected)
    if not exact_has_subject:
        fuzzy = [
            node for node in _fuzzy_long_alias_nodes(lowered, seen)
            if node.kind != "imaging"
        ]
        if fuzzy:
            selected.extend(fuzzy)
    return selected


def graph_expansion_terms(query: str, *, min_weight: float = 0.8, limit: int = 12, relation_hints: tuple[str, ...] = ()) -> list[str]:
    """Return bounded high-confidence graph terms for candidate retrieval."""
    seeds = {node.id for node in matched_nodes(query)}
    if not seeds:
        return []
    candidates: list[tuple[float, str]] = []
    hinted = set(relation_hints)
    from app.dental_knowledge_relations import DENTAL_RELATION_EDGES
    for edge in (*EDGES, *DENTAL_RELATION_EDGES):
        other = None
        if edge.source in seeds:
            other = edge.target
        elif edge.target in seeds and edge.relation in {
            Relation.MEASURES, Relation.PART_OF, Relation.ANATOMICAL_RELATION, Relation.USED_FOR
        }:
            other = edge.source
        if other and edge.weight >= min_weight:
            # Relation packs may be deployed ahead of their terminology pack.
            # A dangling expansion edge must never crash retrieval; structural
            # coverage reports still expose it for ontology repair.
            node = _NODE_BY_ID.get(other)
            if node is None:
                continue
            relation_matches = edge.relation.value in hinted
            # When the question names a relation (complication, treatment,
            # assessment, etc.), keep unrelated neighbours available only when
            # exceptionally strong; otherwise they dilute the retrieval query.
            if hinted and not relation_matches and edge.weight < 0.95:
                continue
            intent_bonus = 0.12 if relation_matches else 0.0
            score = min(1.0, edge.weight + intent_bonus)
            candidates.append((score, node.label))
            candidates.extend((score - 0.02, alias) for alias in node.aliases[:2])
    seen: set[str] = set()
    result: list[str] = []
    for _, term in sorted(candidates, key=lambda item: (-item[0], item[1].casefold())):
        key = term.casefold()
        if key not in seen and key not in (query or "").casefold():
            seen.add(key)
            result.append(term)
        if len(result) >= limit:
            break
    return result