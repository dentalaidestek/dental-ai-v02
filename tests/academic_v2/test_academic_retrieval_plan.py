from __future__ import annotations

from app.academic_retrieval_plan import (
    AcademicRetrievalPlan, ComparisonRequirement, NeedGroup, RetrievalNeed, ValueConstraint,
)


def _raises(message, fn):
    try:
        fn()
    except ValueError as exc:
        assert message in str(exc), str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_subject_facets_remain_bound_to_their_subjects():
    plan = AcademicRetrievalPlan(
        original_query="A'nın tanısı ve tedavisi ile B'nin komplikasyonlarını karşılaştır.",
        answer_operation="compare",
        needs=(
            RetrievalNeed("a-diagnosis", subject_terms=("A",), facet="diagnosis"),
            RetrievalNeed("a-treatment", subject_terms=("A",), facet="treatment"),
            RetrievalNeed("b-complication", subject_terms=("B",), facet="complication"),
        ),
        comparisons=(ComparisonRequirement(
            ("a-diagnosis", "a-treatment", "b-complication"),
            ("diagnosis", "treatment", "complication"),
        ),),
    )
    assert [(n.subject_terms, n.facet) for n in plan.required_needs] == [
        (("A",), "diagnosis"), (("A",), "treatment"), (("B",), "complication"),
    ]


def test_historical_question_can_feed_later_note_retrieval():
    plan = AcademicRetrievalPlan(
        original_query="Geçen yıl apeksifikasyonda ne sorulduğuna bak, nottan o yerleri özetle.",
        answer_operation="summarize",
        needs=(
            RetrievalNeed("past-pattern", subject_terms=("apeksifikasyon",), facet="tested_concept", sources=("past_questions",)),
            RetrievalNeed("note-evidence", subject_terms=("apeksifikasyon",), facet="study_evidence", sources=("notes",), depends_on=("past-pattern",)),
        ),
    )
    assert plan.required_sources == ("past_questions", "notes")
    assert plan.needs[1].depends_on == ("past-pattern",)


def test_relation_accepts_text_target_but_rejects_missing_target():
    need = RetrievalNeed(
        "relation", subject_terms=("mandibular kanal",), facet="anatomy",
        relation="anatomical_relation", target_subject_terms=("üçüncü molar",),
    )
    assert need.target_subject_terms == ("üçüncü molar",)
    _raises("relation requires a target subject", lambda: RetrievalNeed(
        "bad-relation", subject_terms=("mandibular kanal",), facet="anatomy",
        relation="anatomical_relation",
    ))


def test_logic_groups_preserve_or_semantics():
    plan = AcademicRetrievalPlan(
        original_query="Soğuk veya sıcak test bulgusunu nottan bul.",
        needs=(
            RetrievalNeed("cold", subject_terms=("pulpa",), facet="finding", qualifiers=("cold",)),
            RetrievalNeed("heat", subject_terms=("pulpa",), facet="finding", qualifiers=("heat",)),
        ),
        need_groups=(NeedGroup("thermal-test", ("cold", "heat"), mode="any"),),
    )
    assert plan.need_groups[0].mode == "any"


def test_numeric_range_is_structured_and_validated():
    constraint = ValueConstraint("probing_depth", unit="mm", operator="range", value=4, upper_value=6)
    assert constraint.unit == "mm"
    _raises("lower value cannot exceed", lambda: ValueConstraint(
        "bad", operator="range", value=7, upper_value=3,
    ))


def test_dependencies_must_exist_and_be_acyclic():
    _raises("unknown needs", lambda: AcademicRetrievalPlan(
        original_query="x",
        needs=(RetrievalNeed("a", subject_terms=("x",), depends_on=("missing",)),),
    ))
    _raises("acyclic", lambda: AcademicRetrievalPlan(
        original_query="x",
        needs=(
            RetrievalNeed("a", subject_terms=("x",), depends_on=("b",)),
            RetrievalNeed("b", subject_terms=("x",), depends_on=("a",)),
        ),
    ))


def test_comparison_and_groups_cannot_reference_missing_needs():
    need = RetrievalNeed("a", subject_terms=("A",), facet="comparison")
    _raises("comparison references unknown", lambda: AcademicRetrievalPlan(
        original_query="A ile B'yi karşılaştır.", needs=(need,),
        comparisons=(ComparisonRequirement(("a", "b")),),
    ))
    _raises("need group references unknown", lambda: AcademicRetrievalPlan(
        original_query="A veya B", needs=(need,),
        need_groups=(NeedGroup("g", ("a", "b"), "any"),),
    ))


def test_empty_subjectless_and_self_dependent_needs_fail_closed():
    _raises("requires a subject", lambda: RetrievalNeed("bad", facet="diagnosis"))
    _raises("cannot depend on itself", lambda: RetrievalNeed(
        "bad", subject_terms=("x",), depends_on=("bad",),
    ))
    _raises("at least one retrieval need", lambda: AcademicRetrievalPlan(
        original_query="pulpitis nedir", needs=(),
    ))
