"""Conservative sentence decomposition for Academic AI retrieval planning."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.academic_retrieval_plan import AcademicRetrievalPlan, ComparisonRequirement, RetrievalNeed
from app.dental_knowledge_graph import matched_nodes
from app.dental_query_intent import build_dental_requirement_plan, classify_dental_intents, query_qualifiers

_CLAUSE_BOUNDARY_RE = re.compile(
    r"\s*(?:[;.!?]+|\b(?:ama|ancak|fakat|oysa|ardından|ardindan|sonra)\b)\s*", re.I
)
_COORDINATOR_RE = re.compile(r"\s*,\s*|\s+ve\s+|\s+ile\s+", re.I)
_COMPARISON_RE = re.compile(r"\b(?:fark|karşılaştır|karsilastir|versus|vs\.?|hangisi daha)\w*\b", re.I)
_NEGATIVE_RE = re.compile(
    r"(?iu)\b(?:değil(?:dir)?|olmayan|olmaz|kullanılmaz|uygulanmaz|yapılmaz|"
    r"önerilmez|tercih\s+edilmez|yanlış(?:tır)?|hariç|kontrendike)\b"
)


@dataclass(frozen=True)
class _Mention:
    node_id: str
    label: str
    start: int
    end: int


def _mentions(text: str) -> tuple[_Mention, ...]:
    output: list[_Mention] = []
    occupied: list[tuple[int, int]] = []
    for node in matched_nodes(text):
        for term in sorted((node.label, *node.aliases), key=len, reverse=True):
            clean = " ".join((term or "").split())
            if not clean:
                continue
            pattern = re.escape(clean).replace(r"\ ", r"\s+")
            match = re.search(r"(?<!\w)" + pattern + r"(?!\w)", text, re.I)
            if not match:
                continue
            span = (match.start(), match.end())
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            occupied.append(span)
            output.append(_Mention(node.id, node.label, *span))
            break
    return tuple(sorted(output, key=lambda item: item.start))


def _explicit_facets(text: str) -> tuple[str, ...]:
    return tuple(
        intent.name for intent in classify_dental_intents(text, limit=6)
        if intent.name not in {"general", "comparison"}
    )


def _append_need(
    needs: list[RetrievalNeed],
    seen: set[tuple],
    *,
    need_id: str,
    subject: _Mention,
    facet: str,
    context: str,
) -> bool:
    qualifiers = query_qualifiers(context)
    key = (subject.node_id, facet, qualifiers, bool(_NEGATIVE_RE.search(context)))
    if key in seen:
        return False
    seen.add(key)
    needs.append(RetrievalNeed(
        need_id=need_id,
        subject_ids=(subject.node_id,),
        subject_terms=(subject.label,),
        facet=facet,
        qualifiers=qualifiers,
        polarity="negative" if _NEGATIVE_RE.search(context) else "positive",
    ))
    return True


def _bind_clause(
    clause: str,
    clause_index: int,
    needs: list[RetrievalNeed],
    seen: set[tuple],
) -> bool:
    """Bind only constructions whose ownership is explicit or structurally safe."""
    mentions = _mentions(clause)
    facets = _explicit_facets(clause)

    # One explicit subject owns all requested facets in the same clause,
    # including coordinated tails: "pulpitisin tanısı, tedavisi ve komplikasyonu".
    if len(mentions) == 1 and facets:
        return any(
            _append_need(
                needs, seen, need_id=f"c{clause_index}-{facet}",
                subject=mentions[0], facet=facet, context=clause,
            )
            for facet in facets
        )

    # Multiple subjects: inspect coordinated pieces.  A piece that explicitly
    # contains both a subject and a facet is safe. Facet-only pieces are not
    # inherited across subjects because that creates false cross-binding.
    produced = False
    pieces = tuple(part.strip(" ,") for part in _COORDINATOR_RE.split(clause) if part.strip(" ,"))
    for piece_index, piece in enumerate(pieces, start=1):
        piece_mentions = _mentions(piece)
        piece_facets = _explicit_facets(piece)
        if len(piece_mentions) != 1 or not piece_facets:
            continue
        for facet in piece_facets:
            produced = _append_need(
                needs, seen, need_id=f"c{clause_index}s{piece_index}-{facet}",
                subject=piece_mentions[0], facet=facet, context=piece,
            ) or produced

    if produced:
        return True

    # Symmetric comparison: one explicit dimension applies to every explicit
    # side. This is the only safe automatic cross-subject propagation.
    if len(mentions) > 1 and _COMPARISON_RE.search(clause) and len(facets) == 1:
        facet = facets[0]
        for side_index, subject in enumerate(mentions, start=1):
            produced = _append_need(
                needs, seen, need_id=f"c{clause_index}-side{side_index}-{facet}",
                subject=subject, facet=facet, context=clause,
            ) or produced
    return produced


def decompose_academic_query(query: str) -> AcademicRetrievalPlan:
    """Convert explicit sentence semantics into subject-bound evidence needs.

    This function does not resolve conversational pronouns and does not invent
    missing dental entities. Existing follow-up resolution must run first when
    this layer is eventually connected to live retrieval.
    """
    clean = " ".join((query or "").split()).strip()
    legacy = build_dental_requirement_plan(clean)
    needs: list[RetrievalNeed] = []
    unresolved: list[str] = []
    seen: set[tuple] = set()

    clauses = tuple(part for part in _CLAUSE_BOUNDARY_RE.split(clean) if part) or (clean,)
    for clause_index, clause in enumerate(clauses, start=1):
        if _bind_clause(clause, clause_index, needs, seen):
            continue
        if len(_mentions(clause)) > 1 and _explicit_facets(clause):
            unresolved.append(f"clause_{clause_index}:subject_facet_binding")

    if not needs:
        for index, (node_id, label) in enumerate(zip(legacy.subject_node_ids, legacy.subject_terms), start=1):
            bound = next((qs for sid, qs in legacy.subject_qualifiers if sid == node_id), ())
            needs.append(RetrievalNeed(
                need_id=f"unresolved-{index}",
                subject_ids=(node_id,),
                subject_terms=(label,),
                facet="general",
                qualifiers=bound,
            ))
        if not needs and legacy.subject_terms:
            needs.append(RetrievalNeed(
                need_id="unresolved-lexical",
                subject_terms=(legacy.subject_terms[0],),
                facet="general",
                qualifiers=legacy.qualifiers,
            ))
        if not needs:
            needs.append(RetrievalNeed(
                need_id="unresolved-subject",
                subject_terms=("<unresolved>",),
                facet="general",
            ))
        unresolved.append("sentence_decomposition")

    # Graph relations are retained only when both endpoints are explicit in
    # the user's sentence. Graph knowledge guides search; it is never promoted
    # into a requested fact by this planner.
    explicit_ids = {sid for need in needs for sid in need.subject_ids}
    relation_needs: list[RetrievalNeed] = []
    for source_id, relation, target_id in legacy.explicit_relations:
        if source_id not in explicit_ids or target_id not in explicit_ids:
            continue
        source_need = next((n for n in needs if source_id in n.subject_ids), None)
        target_need = next((n for n in needs if target_id in n.subject_ids), None)
        if source_need is None or target_need is None:
            continue
        relation_needs.append(RetrievalNeed(
            need_id=f"relation-{source_id}-{relation}-{target_id}",
            subject_ids=(source_id,),
            subject_terms=source_need.subject_terms,
            facet="anatomy" if relation == "anatomical_relation" else "relation",
            relation=relation,
            target_subject_ids=(target_id,),
            target_subject_terms=target_need.subject_terms,
        ))
    needs.extend(relation_needs)

    comparisons: tuple[ComparisonRequirement, ...] = ()
    if _COMPARISON_RE.search(clean) and len(needs) >= 2:
        comparisons = (ComparisonRequirement(
            tuple(need.need_id for need in needs),
            tuple(dict.fromkeys(need.facet for need in needs if need.facet != "general")),
        ),)

    return AcademicRetrievalPlan(
        original_query=clean,
        needs=tuple(needs),
        answer_operation="compare" if comparisons else "answer",
        comparisons=comparisons,
        requires_visual_source=legacy.requires_visual_source,
        unresolved_references=tuple(dict.fromkeys(unresolved)),
        fail_closed=True,
        metadata=(("origin", "sentence_decomposer_v1"),),
    )
