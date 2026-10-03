"""Compatibility bridge from the proven dental parser to semantic retrieval plans.

The bridge is deliberately conservative.  It preserves information already
known by DentalRequirementPlan and refuses to invent subject/facet bindings
that the legacy parser did not establish.
"""
from __future__ import annotations

from app.academic_retrieval_plan import (
    AcademicRetrievalPlan,
    ComparisonRequirement,
    RetrievalNeed,
)
from app.dental_query_intent import DentalRequirementPlan, build_dental_requirement_plan


def _subject_qualifiers(plan: DentalRequirementPlan, node_id: str) -> tuple[str, ...]:
    for subject_id, qualifiers in plan.subject_qualifiers:
        if subject_id == node_id:
            return qualifiers
    return ()


def _subject_pairs(plan: DentalRequirementPlan) -> tuple[tuple[str, str], ...]:
    """Return stable id/label pairs without fabricating missing graph identities."""
    if not plan.subject_node_ids:
        return ()
    labels = plan.subject_terms
    pairs: list[tuple[str, str]] = []
    for index, node_id in enumerate(plan.subject_node_ids):
        label = labels[index] if index < len(labels) else node_id
        pairs.append((node_id, label))
    return tuple(pairs)


def legacy_requirement_to_semantic_plan(
    query: str,
    requirement: DentalRequirementPlan | None = None,
) -> AcademicRetrievalPlan:
    """Loss-minimizing adapter; no new semantic inference is performed here."""
    legacy = requirement or build_dental_requirement_plan(query)
    facets = legacy.requested_facets or ("general",)
    subjects = _subject_pairs(legacy)
    needs: list[RetrievalNeed] = []
    unresolved: list[str] = []

    if subjects:
        # Legacy facets are global.  Binding every facet to every subject would
        # silently invent semantics for asymmetric sentences.  It is safe only
        # for one subject; multi-subject plans stay explicitly unresolved until
        # the sentence-level decomposer assigns the bindings.
        if len(subjects) == 1:
            node_id, label = subjects[0]
            for index, facet in enumerate(facets, start=1):
                needs.append(RetrievalNeed(
                    need_id=f"legacy-{index}",
                    subject_ids=(node_id,),
                    subject_terms=(label,),
                    facet=facet,
                    qualifiers=_subject_qualifiers(legacy, node_id) or legacy.qualifiers,
                    polarity="negative" if legacy.asks_negation else "positive",
                ))
        else:
            unresolved.append("subject_facet_binding")
            for index, (node_id, label) in enumerate(subjects, start=1):
                needs.append(RetrievalNeed(
                    need_id=f"legacy-subject-{index}",
                    subject_ids=(node_id,),
                    subject_terms=(label,),
                    facet="general",
                    qualifiers=_subject_qualifiers(legacy, node_id),
                ))
    elif legacy.subject_terms:
        for index, term in enumerate(legacy.subject_terms, start=1):
            needs.append(RetrievalNeed(
                need_id=f"legacy-lexical-{index}",
                subject_terms=(term,),
                facet=facets[0] if len(facets) == 1 else "general",
                qualifiers=legacy.qualifiers,
                polarity="negative" if legacy.asks_negation else "positive",
            ))
        if len(facets) > 1:
            unresolved.append("lexical_subject_facet_binding")
    else:
        # AcademicRetrievalPlan intentionally cannot contain a subjectless need.
        # Preserve the parser uncertainty as a lexical placeholder and force
        # fail-closed downstream rather than manufacturing a dental entity.
        unresolved.append("subject")
        needs.append(RetrievalNeed(
            need_id="legacy-unresolved",
            subject_terms=("<unresolved>",),
            facet="general",
        ))

    comparisons: tuple[ComparisonRequirement, ...] = ()
    if "comparison" in facets and len(needs) >= 2:
        comparisons = (ComparisonRequirement(
            side_need_ids=tuple(need.need_id for need in needs),
            dimensions=tuple(f for f in facets if f != "comparison"),
        ),)

    return AcademicRetrievalPlan(
        original_query=query,
        needs=tuple(needs),
        answer_operation="compare" if "comparison" in facets else "answer",
        comparisons=comparisons,
        requires_visual_source=legacy.requires_visual_source,
        unresolved_references=tuple(unresolved),
        fail_closed=True,
        metadata=(
            ("origin", "legacy_requirement_adapter"),
            ("legacy_subject_count", str(legacy.subject_count)),
        ),
    )
