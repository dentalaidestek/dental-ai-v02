"""Curated dental knowledge graph used only for retrieval expansion.

The graph proposes where to search. It is never a factual answer source:
user-visible answers must still be grounded in the uploaded course material.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from app.dental_specialty_concepts import SPECIALTY_CONCEPTS


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
    DentalNode("root_canal", "kök kanal sistemi", "endodontics", "anatomy", ("root canal system", "kanal")),
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

_SPECIALTY_NODES = tuple(
    DentalNode(concept_id, label, specialty, kind, aliases)
    for specialty, concepts in SPECIALTY_CONCEPTS.items()
    for concept_id, label, aliases, kind in concepts
)
ALL_NODES = NODES + _SPECIALTY_NODES
_NODE_BY_ID = {node.id: node for node in ALL_NODES}


def _term_present(text: str, term: str) -> bool:
    """Boundary-aware phrase match; short dental abbreviations must not hit substrings."""
    clean_term = " ".join((term or "").casefold().split())
    if not clean_term:
        return False
    escaped = re.escape(clean_term).replace(r"\ ", r"\s+")
    return bool(re.search(r"(?<!\w)" + escaped + r"(?!\w)", text, flags=re.IGNORECASE))

def matched_nodes(query: str) -> list[DentalNode]:
    """Find explicit dental entities in a query, longest aliases first."""
    lowered = " ".join((query or "").casefold().split())
    matches: list[tuple[int, DentalNode]] = []
    for node in ALL_NODES:
        terms = (node.label, *node.aliases)
        best = max((len(term) for term in terms if _term_present(lowered, term)), default=0)
        if best:
            matches.append((best, node))
    matches.sort(key=lambda item: (-item[0], item[1].id))
    return [node for _, node in matches]


def graph_expansion_terms(query: str, *, min_weight: float = 0.8, limit: int = 12, relation_hints: tuple[str, ...] = ()) -> list[str]:
    """Return bounded high-confidence graph terms for candidate retrieval."""
    seeds = {node.id for node in matched_nodes(query)}
    if not seeds:
        return []
    candidates: list[tuple[float, str]] = []
    hinted = set(relation_hints)
    for edge in EDGES:
        other = None
        if edge.source in seeds:
            other = edge.target
        elif edge.target in seeds and edge.relation in {
            Relation.MEASURES, Relation.PART_OF, Relation.ANATOMICAL_RELATION, Relation.USED_FOR
        }:
            other = edge.source
        if other and edge.weight >= min_weight:
            node = _NODE_BY_ID[other]
            intent_bonus = 0.08 if edge.relation.value in hinted else 0.0
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
