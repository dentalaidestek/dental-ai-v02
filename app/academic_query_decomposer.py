"""Conservative sentence decomposition for Academic AI retrieval planning."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.academic_retrieval_plan import AcademicRetrievalPlan, ComparisonRequirement, RetrievalNeed
from app.dental_query_intent import build_dental_requirement_plan, classify_dental_intents, query_qualifiers

# Discourse boundaries may permit safe subject continuation. Temporal operators
# are deliberately not consumed here: "sonra/ardından" carry meaning and stay
# visible to the fail-closed temporal layer until temporal semantics are modeled.
_CLAUSE_BOUNDARY_RE = re.compile(
    r"\s*(?:[;.!?]+|\b(?:ama|ancak|fakat|oysa)\b)\s*", re.I
)
_COORDINATOR_RE = re.compile(r"\s*,\s*|\s+ve\s+|\s+ile\s+", re.I)
_COMPARISON_RE = re.compile(r"\b(?:fark|karşılaştır|karsilastir|versus|vs\.?|hangisi daha)\w*\b", re.I)
_NEGATIVE_RE = re.compile(
    r"(?iu)\b(?:değil(?:dir)?|olmayan|olmaz|kullanılmaz|uygulanmaz|yapılmaz|"
    r"önerilmez|tercih\s+edilmez|yanlış(?:tır)?)\b"
)

_UNMODELED_OPERATOR_PATTERNS = (
    ("logical_or", re.compile(r"(?iu)\b(?:veya|yahut|ya\s+da)\b")),
    ("explicit_exclusion", re.compile(r"(?iu)\b(?:hariç|dışında|değinme|girme|bahsetme)\b")),
    ("numeric_constraint", re.compile(r"(?iu)(?:\b\d+(?:[.,]\d+)?\s*(?:mm|cm|derece|°|%)\b|[<>]=?|\ben\s+(?:az|çok)\b)")),
    ("source_selection", re.compile(r"(?iu)\b(?:çıkmış|geçmiş)\s+(?:soru|sınav)[a-zçğıöşü]*\b")),
    ("temporal_order", re.compile(r"(?iu)\b(?:önce|sonra|ardından|ardindan|takiben|öncesi|sonrası)\b")),
)


@dataclass(frozen=True)
class _Mention:
    node_id: str
    label: str
    qualifiers: tuple[str, ...] = ()


def _mentions(text: str) -> tuple[_Mention, ...]:
    """Return only subjects with trustworthy explicit spans in this clause.

    The legacy parser may recover a subject through fuzzy typo matching. That is
    useful for retrieval, but unsafe for sentence ownership: a guessed entity
    must not receive a nearby facet/qualifier as if its text span were known.
    """
    from app.dental_knowledge_graph import explicit_node_mentions

    plan = build_dental_requirement_plan(text)
    qualifier_map = {node_id: qualifiers for node_id, qualifiers in plan.subject_qualifiers}
    labels = dict(zip(plan.subject_node_ids, plan.subject_terms))
    explicit_ids = tuple(
        dict.fromkeys(
            node.id for _, _, node in explicit_node_mentions(text)
            if node.id in labels
        )
    )
    return tuple(
        _Mention(node_id, labels[node_id], qualifier_map.get(node_id, ()))
        for node_id in explicit_ids
    )


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
    # Subject-scoped qualifiers are authoritative. Falling back to every
    # qualifier in the clause can attach a modifier to the wrong subject and
    # can turn a negative applicability phrase into a fake subject condition.
    qualifiers = subject.qualifiers
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
    *,
    inherited_subject: _Mention | None = None,
) -> tuple[bool, bool]:
    """Return produced evidence plus whether ownership remains ambiguous.

    A subjectless continuation may inherit exactly one trustworthy subject
    context from the preceding resolved clause. Explicit subjects always win.
    """
    mentions = _mentions(clause)
    facets = _explicit_facets(clause)
    if not mentions and facets and inherited_subject is not None:
        mentions = (inherited_subject,)

    # One explicit subject owns all requested facets in the same clause,
    # including coordinated tails: "pulpitisin tanısı, tedavisi ve komplikasyonu".
    if len(mentions) == 1 and facets:
        produced = False
        for facet in facets:
            produced = _append_need(
                needs, seen, need_id=f"c{clause_index}-{facet}",
                subject=mentions[0], facet=facet, context=clause,
            ) or produced
        return produced, False

    # Symmetric comparison is handled before piece binding so a facet attached
    # to the final side cannot make the first side disappear.
    if len(mentions) > 1 and _COMPARISON_RE.search(clause) and len(facets) == 1:
        produced = False
        facet = facets[0]
        for side_index, subject in enumerate(mentions, start=1):
            produced = _append_need(
                needs, seen, need_id=f"c{clause_index}-side{side_index}-{facet}",
                subject=subject, facet=facet, context=clause,
            ) or produced
        return produced, False

    # Multiple subjects: inspect coordinated pieces.  A piece that explicitly
    # contains both a subject and a facet is safe. Facet-only pieces are not
    # inherited across subjects because that creates false cross-binding.
    produced = False
    clause_need_start = len(needs)
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

    clause_needs = needs[clause_need_start:]
    bound_subjects = {sid for need in clause_needs for sid in need.subject_ids}
    bound_facets = {need.facet for need in clause_needs}
    ambiguous = bool(
        len(mentions) > 1
        and facets
        and (
            not {mention.node_id for mention in mentions}.issubset(bound_subjects)
            or not set(facets).issubset(bound_facets)
        )
    )
    return produced, ambiguous


def decompose_academic_query(query: str) -> AcademicRetrievalPlan:
    """Convert explicit sentence semantics into subject-bound evidence needs.

    This function does not resolve conversational pronouns and does not invent
    missing dental entities. Existing follow-up resolution must run first when
    this layer is eventually connected to live retrieval.
    """
    clean = " ".join((query or "").split()).strip()
    legacy = build_dental_requirement_plan(clean)
    needs: list[RetrievalNeed] = []
    unresolved: list[str] = [
        f"unmodeled:{name}"
        for name, pattern in _UNMODELED_OPERATOR_PATTERNS
        if pattern.search(clean)
    ]
    seen: set[tuple] = set()

    clauses = tuple(part for part in _CLAUSE_BOUNDARY_RE.split(clean) if part) or (clean,)
    continuation_subject: _Mention | None = None
    continuation_safe = False
    for clause_index, clause in enumerate(clauses, start=1):
        explicit_mentions = _mentions(clause)
        # Only a single explicit subject can establish continuation state.
        # Multiple subjects make the antecedent ambiguous; subjectless clauses
        # must then fail closed instead of guessing one of them.
        inherited = continuation_subject if (not explicit_mentions and continuation_safe) else None
        produced, ambiguous = _bind_clause(
            clause, clause_index, needs, seen, inherited_subject=inherited,
        )
        if ambiguous:
            unresolved.append(f"clause_{clause_index}:subject_facet_binding")
        if len(explicit_mentions) == 1:
            continuation_subject = explicit_mentions[0]
            continuation_safe = not ambiguous
        elif len(explicit_mentions) > 1:
            continuation_subject = None
            continuation_safe = False
        # A subjectless clause with an explicit facet still has unresolved
        # ownership unless a safe antecedent was actually inherited.  This
        # check must happen before the produced short-circuit: the legacy
        # lexical fallback may synthesize a pseudo-subject (e.g. "ölçümünü"),
        # causing _bind_clause to report produced evidence even though there is
        # no trustworthy canonical subject span.
        if not explicit_mentions and _explicit_facets(clause) and inherited is None:
            unresolved.append(f"clause_{clause_index}:subject_reference")
        if produced:
            continue
        if len(explicit_mentions) > 1 and _explicit_facets(clause):
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
    explicit_ids = set(legacy.subject_node_ids)
    labels = dict(zip(legacy.subject_node_ids, legacy.subject_terms))
    relation_needs: list[RetrievalNeed] = []
    for source_id, relation, target_id in legacy.explicit_relations:
        if source_id not in explicit_ids or target_id not in explicit_ids:
            continue
        source_need = next((n for n in needs if source_id in n.subject_ids), None)
        target_need = next((n for n in needs if target_id in n.subject_ids), None)
        if source_need is None and not any(source_id in n.subject_ids for n in relation_needs):
            relation_needs.append(RetrievalNeed(
                need_id=f"relation-endpoint-{source_id}",
                subject_ids=(source_id,),
                subject_terms=(labels[source_id],),
                facet="general",
            ))
        if target_need is None and not any(target_id in n.subject_ids for n in relation_needs):
            relation_needs.append(RetrievalNeed(
                need_id=f"relation-endpoint-{target_id}",
                subject_ids=(target_id,),
                subject_terms=(labels[target_id],),
                facet="general",
            ))
        relation_needs.append(RetrievalNeed(
            need_id=f"relation-{source_id}-{relation}-{target_id}",
            subject_ids=(source_id,),
            subject_terms=source_need.subject_terms if source_need else (labels[source_id],),
            facet="anatomy" if relation == "anatomical_relation" else "relation",
            relation=relation,
            target_subject_ids=(target_id,),
            target_subject_terms=target_need.subject_terms if target_need else (labels[target_id],),
        ))
    needs.extend(relation_needs)

    comparisons: tuple[ComparisonRequirement, ...] = ()
    comparison_needs = tuple(
        need for need in needs if need.relation is None and need.facet != "general"
    )
    if _COMPARISON_RE.search(clean) and len(comparison_needs) >= 2:
        comparisons = (ComparisonRequirement(
            tuple(need.need_id for need in comparison_needs),
            tuple(dict.fromkeys(need.facet for need in comparison_needs)),
        ),)

    operation = "compare" if comparisons else "answer"
    comparison_requested = _COMPARISON_RE.search(clean) is not None or any(
        item.name == "comparison" for item in legacy.intents
    )
    if comparison_requested and not comparisons:
        unresolved.append("comparison_sides")

    return AcademicRetrievalPlan(
        original_query=clean,
        needs=tuple(needs),
        answer_operation=operation,
        comparisons=comparisons,
        requires_visual_source=legacy.requires_visual_source,
        unresolved_references=tuple(dict.fromkeys(unresolved)),
        fail_closed=True,
        metadata=(("origin", "sentence_decomposer_v2"),),
    )
