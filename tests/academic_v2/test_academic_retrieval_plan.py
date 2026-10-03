from __future__ import annotations

import pytest

from app.academic_retrieval_plan import (
    AcademicRetrievalPlan,
    ComparisonRequirement,
    RetrievalNeed,
)


def test_subject_facets_remain_bound_to_their_subjects():
    plan = AcademicRetrievalPlan(
        original_query="A'nın tanısı ve tedavisi ile B'nin komplikasyonlarını karşılaştır.",
        answer_operation="compare",
        needs=(
            RetrievalNeed("a-diagnosis", subject_terms=("A",), facet="diagnosis"),
            RetrievalNeed("a-treatment", subject_terms=("A",), facet="treatment"),
            RetrievalNeed("b-complication", subject_terms=("B",), facet="complication"),
        ),
        comparisons=(
            ComparisonRequirement(
                side_need_ids=("a-diagnosis", "a-treatment", "b-complication"),
                dimensions=("diagnosis", "treatment", "complication"),
            ),
        ),
    )
    assert [(n.subject_terms, n.facet) for n in plan.required_needs] == [
        (("A",), "diagnosis"),
        (("A",), "treatment"),
        (("B",), "complication"),
    ]


def test_past_question_and_note_sources_can_be_separate_needs():
    plan = AcademicRetrievalPlan(
        original_query=(
            "Geçen yıl apeksifikasyonda ne sorulduğuna bak, "
            "sonra nottan o yerleri çalışma özeti yap."
        ),
        answer_operation="summarize",
        needs=(
            RetrievalNeed(
                "past-pattern",
                subject_terms=("apeksifikasyon",),
                facet="tested_concept",
                sources=("past_questions",),
            ),
            RetrievalNeed(
                "note-evidence",
                subject_terms=("apeksifikasyon",),
                facet="study_evidence",
                sources=("notes",),
            ),
        ),
    )
    assert plan.required_sources == ("past_questions", "notes")


def test_relation_needs_require_an_explicit_target():
    with pytest.raises(ValueError, match="relation requires a target subject"):
        RetrievalNeed(
            "relation",
            subject_terms=("mandibular kanal",),
            facet="anatomy",
            relation="anatomical_relation",
        )


def test_comparison_cannot_reference_a_missing_need():
    with pytest.raises(ValueError, match="unknown needs"):
        AcademicRetrievalPlan(
            original_query="A ile B'yi karşılaştır.",
            answer_operation="compare",
            needs=(RetrievalNeed("a", subject_terms=("A",), facet="comparison"),),
            comparisons=(ComparisonRequirement(("a", "b")),),
        )


def test_empty_or_subjectless_needs_fail_closed():
    with pytest.raises(ValueError, match="requires a subject"):
        RetrievalNeed("bad", facet="diagnosis")
    with pytest.raises(ValueError, match="at least one retrieval need"):
        AcademicRetrievalPlan(original_query="pulpitis nedir", needs=())
