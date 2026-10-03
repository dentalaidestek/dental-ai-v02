"""Semantic retrieval-plan contracts for Academic AI V2.

This module is intentionally side-effect free and is not wired into the live
retrieval path yet.  It defines the supervised target that a future local
sentence-level planner must produce: the exact evidence needs that retrieval
has to satisfy before generation is allowed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SourceKind = Literal["notes", "past_questions"]
NeedPolarity = Literal["positive", "negative"]
NeedPriority = Literal["required", "optional"]
AnswerOperation = Literal[
    "answer", "explain", "summarize", "compare", "evaluate",
    "solve", "generate_questions",
]


@dataclass(frozen=True)
class RetrievalNeed:
    """One independently satisfiable evidence requirement.

    A sentence may create several needs.  Subjects and facets stay bound here,
    preventing a facet found for subject A from satisfying subject B.
    """

    need_id: str
    subject_ids: tuple[str, ...] = ()
    subject_terms: tuple[str, ...] = ()
    facet: str = "general"
    relation: str | None = None
    target_subject_ids: tuple[str, ...] = ()
    qualifiers: tuple[str, ...] = ()
    sources: tuple[SourceKind, ...] = ("notes",)
    polarity: NeedPolarity = "positive"
    priority: NeedPriority = "required"

    def __post_init__(self) -> None:
        if not self.need_id.strip():
            raise ValueError("need_id must not be empty")
        if not self.subject_ids and not self.subject_terms:
            raise ValueError(f"{self.need_id}: a retrieval need requires a subject")
        if not self.facet.strip():
            raise ValueError(f"{self.need_id}: facet must not be empty")
        if not self.sources:
            raise ValueError(f"{self.need_id}: at least one source is required")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError(f"{self.need_id}: duplicate sources are not allowed")
        if self.relation and not self.target_subject_ids:
            raise ValueError(f"{self.need_id}: relation requires a target subject")


@dataclass(frozen=True)
class ComparisonRequirement:
    """A comparison is evidence over explicit sides and explicit dimensions."""

    side_need_ids: tuple[str, ...]
    dimensions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.side_need_ids) < 2:
            raise ValueError("comparison requires at least two side needs")


@dataclass(frozen=True)
class AcademicRetrievalPlan:
    """Sentence-level semantic contract between query understanding and retrieval."""

    original_query: str
    needs: tuple[RetrievalNeed, ...]
    answer_operation: AnswerOperation = "answer"
    comparisons: tuple[ComparisonRequirement, ...] = ()
    excluded_facets: tuple[str, ...] = ()
    output_constraints: tuple[tuple[str, str], ...] = ()
    requires_visual_source: bool = False
    unresolved_references: tuple[str, ...] = ()
    fail_closed: bool = True
    metadata: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.original_query.strip():
            raise ValueError("original_query must not be empty")
        if not self.needs:
            raise ValueError("at least one retrieval need is required")
        ids = [need.need_id for need in self.needs]
        if len(ids) != len(set(ids)):
            raise ValueError("retrieval need ids must be unique")
        known = set(ids)
        for comparison in self.comparisons:
            missing = set(comparison.side_need_ids) - known
            if missing:
                raise ValueError(
                    "comparison references unknown needs: " + ", ".join(sorted(missing))
                )

    @property
    def required_needs(self) -> tuple[RetrievalNeed, ...]:
        return tuple(need for need in self.needs if need.priority == "required")

    @property
    def required_sources(self) -> tuple[SourceKind, ...]:
        ordered: list[SourceKind] = []
        for need in self.required_needs:
            for source in need.sources:
                if source not in ordered:
                    ordered.append(source)
        return tuple(ordered)

    def required_need_ids(self) -> tuple[str, ...]:
        return tuple(need.need_id for need in self.required_needs)
