"""Semantic retrieval-plan contracts for Academic AI V2.

Side-effect free by design: this is the supervised contract for a future local
sentence-level planner and is not wired into live retrieval until regression
coverage proves compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SourceKind = Literal["notes", "past_questions"]
NeedPolarity = Literal["positive", "negative"]
NeedPriority = Literal["required", "optional"]
LogicMode = Literal["all", "any"]
AnswerOperation = Literal[
    "answer", "explain", "summarize", "compare", "evaluate",
    "solve", "generate_questions",
]


@dataclass(frozen=True)
class ValueConstraint:
    """Structured numeric requirement without turning numbers into free text."""

    name: str
    unit: str | None = None
    operator: Literal["eq", "lt", "lte", "gt", "gte", "range"] = "eq"
    value: float | None = None
    upper_value: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("value constraint name must not be empty")
        if self.operator == "range":
            if self.value is None or self.upper_value is None:
                raise ValueError("range requires lower and upper values")
            if self.value > self.upper_value:
                raise ValueError("range lower value cannot exceed upper value")
        elif self.upper_value is not None:
            raise ValueError("upper_value is valid only for range")


@dataclass(frozen=True)
class RetrievalNeed:
    """One independently satisfiable evidence requirement."""

    need_id: str
    subject_ids: tuple[str, ...] = ()
    subject_terms: tuple[str, ...] = ()
    facet: str = "general"
    relation: str | None = None
    target_subject_ids: tuple[str, ...] = ()
    target_subject_terms: tuple[str, ...] = ()
    qualifiers: tuple[str, ...] = ()
    value_constraints: tuple[ValueConstraint, ...] = ()
    sources: tuple[SourceKind, ...] = ("notes",)
    polarity: NeedPolarity = "positive"
    priority: NeedPriority = "required"
    depends_on: tuple[str, ...] = ()

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
        if self.relation and not (
            self.target_subject_ids or self.target_subject_terms
        ):
            raise ValueError(f"{self.need_id}: relation requires a target subject")
        if self.need_id in self.depends_on:
            raise ValueError(f"{self.need_id}: a need cannot depend on itself")


@dataclass(frozen=True)
class NeedGroup:
    """Logical evidence group for conjunction/disjunction semantics."""

    group_id: str
    need_ids: tuple[str, ...]
    mode: LogicMode = "all"

    def __post_init__(self) -> None:
        if not self.group_id.strip():
            raise ValueError("group_id must not be empty")
        if not self.need_ids:
            raise ValueError(f"{self.group_id}: need group must not be empty")


@dataclass(frozen=True)
class ComparisonRequirement:
    """Comparison over explicit evidence needs and explicit dimensions."""

    side_need_ids: tuple[str, ...]
    dimensions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.side_need_ids) < 2:
            raise ValueError("comparison requires at least two side needs")


@dataclass(frozen=True)
class AcademicRetrievalPlan:
    """Sentence-level contract between query understanding and retrieval."""

    original_query: str
    needs: tuple[RetrievalNeed, ...]
    answer_operation: AnswerOperation = "answer"
    need_groups: tuple[NeedGroup, ...] = ()
    comparisons: tuple[ComparisonRequirement, ...] = ()
    excluded_facets: tuple[str, ...] = ()
    excluded_subject_terms: tuple[str, ...] = ()
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
        for need in self.needs:
            missing = set(need.depends_on) - known
            if missing:
                raise ValueError(
                    f"{need.need_id}: dependency references unknown needs: "
                    + ", ".join(sorted(missing))
                )
        self._validate_dependency_cycles()
        group_ids: set[str] = set()
        for group in self.need_groups:
            if group.group_id in group_ids:
                raise ValueError("need group ids must be unique")
            group_ids.add(group.group_id)
            missing = set(group.need_ids) - known
            if missing:
                raise ValueError(
                    "need group references unknown needs: " + ", ".join(sorted(missing))
                )
        for comparison in self.comparisons:
            missing = set(comparison.side_need_ids) - known
            if missing:
                raise ValueError(
                    "comparison references unknown needs: " + ", ".join(sorted(missing))
                )

    def _validate_dependency_cycles(self) -> None:
        dependencies = {need.need_id: set(need.depends_on) for need in self.needs}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(need_id: str) -> None:
            if need_id in visited:
                return
            if need_id in visiting:
                raise ValueError("retrieval need dependencies must be acyclic")
            visiting.add(need_id)
            for dependency in dependencies[need_id]:
                visit(dependency)
            visiting.remove(need_id)
            visited.add(need_id)

        for need_id in dependencies:
            visit(need_id)

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
