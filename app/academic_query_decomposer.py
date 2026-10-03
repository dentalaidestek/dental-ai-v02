"""Conservative sentence decomposition for Academic AI retrieval planning.

This layer binds explicit subjects to explicit requested facets at clause level.
It augments, rather than replaces, the proven DentalRequirementPlan.  Ambiguous
clauses remain unresolved so downstream retrieval can fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.academic_retrieval_plan import AcademicRetrievalPlan, ComparisonRequirement, RetrievalNeed
from app.dental_knowledge_graph import matched_nodes
from app.dental_query_intent import (
    build_dental_requirement_plan,
    classify_dental_intents,
    query_qualifiers,
)

_CLAUSE_BOUNDARY_RE = re.compile(
    r"\s*(?:[;.!?]+|\b(?:ama|ancak|fakat|oysa|ardından|ardindan|sonra)\b)\s*",
    re.I,
)
_COORDINATOR_RE = re.compile(r"\s*,\s*|\s+ve\s+|\s+ile\s+", re.I)
_COMPARISON_RE = re.compile(r"\b(?:fark|karşılaştır|karsilastir|versus|vs\.?|hangisi daha)\w*\b", re.I)


@dataclass(frozen=True)
class _Mention:
    node_id: str
    label: str
    start: int
    end: int


def _mentions(text: str) -> tuple[_Mention, ...]:
    """Locate only graph-recognized subjects that are explicit in this clause."""
    output: list[_Mention] = []
    occupied: list[tuple[int, int]] = []
    for node in matched_nodes(text):
        candidates = sorted((node.label, *node.aliases), key=len, reverse=True)
        for term in candidates:
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
        intent.name
        for intent in classify_dental_intents(text, limit=6)
        if intent.name not in {"general", "comparison"}
    )


def _local_segments(clause: str) -> tuple[str, ...]:
    """Split coordination only when each side can carry its own semantic role."""
    pieces = tuple(part.strip(" ,") for part in _COORDINATOR_RE.split(clause) if part.strip(" ,"))
    if len(pieces) < 2:
        return (clause.strip(),)
    informative = sum(bool(_mentions(part) or _explicit_facets(part)) for part in pieces)
    return pieces if informative >= 2 else (clause.strip(),)


def decompose_academic_query(query: str) -> AcademicRetrievalPlan:
    """Build subject-bound needs from explicit clause-local evidence.

    No pronoun/coreference guessing is done here.  Follow-up resolution remains
    the responsibility of the existing retrieval flow before this function is
    ever wired live.
    """
    clean = " ".join((query or "").split()).strip()
    legacy = build_dental_requirement_plan(clean)
    needs: list[RetrievalNeed] = []
    unresolved: list[str] = []
    seen: set[tuple] = set()

    clauses = tuple(part for part in _CLAUSE_BOUNDARY_RE.split(clean) if part) or (clean,)
    for clause_index, clause in enumerate(clauses, start=1):
        clause_mentions = _mentions(clause)
        clause_facets = _explicit_facets(clause)
        segments = _local_segments(clause)

        produced_in_clause = 0
        for segment_index, segment in enumerate(segments, start=1):
            mentions = _mentions(segment)
            facets = _explicit_facets(segment)
            if len(mentions) == 1 and facets:
                subject = mentions[0]
                for facet in facets:
                    key = (subject.node_id, facet, query_qualifiers(segment))
                    if key in seen:
                        continue
                    seen.add(key)
                    needs.append(RetrievalNeed(
                        need_id=f"c{clause_index}s{segment_index}-{facet}",
                        subject_ids=(subject.node_id,),
                        subject_terms=(subject.label,),
                        facet=facet,
                        qualifiers=query_qualifiers(segment),
                        polarity="negative" if legacy.asks_negation else "positive",
                    ))
                    produced_in_clause += 1

        if produced_in_clause:
            continue

        # A single explicit subject safely owns all explicit facets in its clause.
        if len(clause_mentions) == 1 and clause_facets:
            subject = clause_mentions[0]
            for facet in clause_facets:
                key = (subject.node_id, facet, query_qualifiers(clause))
                if key in seen:
                    continue
                seen.add(key)
                needs.append(RetrievalNeed(
                    need_id=f"c{clause_index}-{facet}",
                    subject_ids=(subject.node_id,),
                    subject_terms=(subject.label,),
                    facet=facet,
                    qualifiers=query_qualifiers(clause),
                    polarity="negative" if legacy.asks_negation else "positive",
                ))
                produced_in_clause += 1
        elif len(clause_mentions) > 1 and clause_facets:
            # Symmetric comparison wording can safely request the same dimension
            # from each explicit side. Other multi-subject clauses are ambiguous.
            if _COMPARISON_RE.search(clause) and len(clause_facets) == 1:
                facet = clause_facets[0]
                for side_index, subject in enumerate(clause_mentions, start=1):
                    key = (subject.node_id, facet, query_qualifiers(clause))
                    if key in seen:
                        continue
                    seen.add(key)
                    needs.append(RetrievalNeed(
                        need_id=f"c{clause_index}-side{side_index}-{facet}",
                        subject_ids=(subject.node_id,),
                        subject_terms=(subject.label,),
                        facet=facet,
                        qualifiers=query_qualifiers(clause),
                    ))
                    produced_in_clause += 1
            else:
                unresolved.append(f"clause_{clause_index}:subject_facet_binding")

    if not needs:
        # Preserve explicit legacy subjects as unresolved evidence anchors. This
        # never makes an ambiguous query look sufficient.
        for index, (node_id, label) in enumerate(
            zip(legacy.subject_node_ids, legacy.subject_terms), start=1
        ):
            needs.append(RetrievalNeed(
                need_id=f"unresolved-{index}",
                subject_ids=(node_id,),
                subject_terms=(label,),
                facet="general",
                qualifiers=tuple(
                    values for sid, qs in legacy.subject_qualifiers if sid == node_id for values in qs
                ),
            ))
        if not needs and legacy.subject_terms:
            needs.append(RetrievalNeed(
                need_id="unresolved-lexical",
                subject_terms=(legacy.subject_terms[0],),
                facet="general",
                qualifiers=legacy.qualifiers,
            ))
        unresolved.append("sentence_decomposition")

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
