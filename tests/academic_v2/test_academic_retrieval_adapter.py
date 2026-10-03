from __future__ import annotations

from app.academic_retrieval_adapter import legacy_requirement_to_semantic_plan
from app.dental_query_intent import DentalIntent, DentalRequirementPlan


def _legacy(**overrides):
    values = dict(
        subject_node_ids=("pulpitis",),
        subject_terms=("pulpitis",),
        intents=(DentalIntent("diagnosis", (), ()),),
        requested_facets=("diagnosis",),
        relation_hints=(),
        specialties=("endodontics",),
    )
    values.update(overrides)
    return DentalRequirementPlan(**values)


def test_single_subject_facets_are_safe_to_bind():
    plan = legacy_requirement_to_semantic_plan(
        "Pulpitisin tanı ve tedavisini anlat.",
        _legacy(
            intents=(DentalIntent("diagnosis", (), ()), DentalIntent("treatment", (), ())),
            requested_facets=("diagnosis", "treatment"),
        ),
    )
    assert [(n.subject_ids, n.facet) for n in plan.needs] == [
        (("pulpitis",), "diagnosis"),
        (("pulpitis",), "treatment"),
    ]
    assert not plan.unresolved_references


def test_multi_subject_global_facets_are_not_falsely_cross_bound():
    plan = legacy_requirement_to_semantic_plan(
        "A'nın tanısı ile B'nin tedavisini karşılaştır.",
        _legacy(
            subject_node_ids=("a", "b"),
            subject_terms=("A", "B"),
            intents=(DentalIntent("diagnosis", (), ()), DentalIntent("treatment", (), ())),
            requested_facets=("diagnosis", "treatment"),
            subject_count=2,
        ),
    )
    assert "subject_facet_binding" in plan.unresolved_references
    assert [n.facet for n in plan.needs] == ["general", "general"]


def test_subject_qualifiers_stay_bound_to_the_correct_subject():
    plan = legacy_requirement_to_semantic_plan(
        "Akut pulpitisin tanısı",
        _legacy(
            qualifiers=("akut",),
            subject_qualifiers=(("pulpitis", ("akut",)),),
        ),
    )
    assert plan.needs[0].qualifiers == ("akut",)


def test_negation_and_visual_requirement_survive_adapter():
    plan = legacy_requirement_to_semantic_plan(
        "Bu görüntüde pulpitis için hangisi değildir?",
        _legacy(asks_negation=True, requires_visual_source=True),
    )
    assert plan.needs[0].polarity == "negative"
    assert plan.requires_visual_source is True


def test_unresolved_subject_is_preserved_fail_closed():
    plan = legacy_requirement_to_semantic_plan(
        "Bunun tanısı nedir?",
        _legacy(
            subject_node_ids=(),
            subject_terms=(),
            unresolved_subject=True,
        ),
    )
    assert plan.unresolved_references == ("subject",)
    assert plan.fail_closed is True
    assert plan.needs[0].subject_terms == ("<unresolved>",)
