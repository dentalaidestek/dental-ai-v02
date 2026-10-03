from __future__ import annotations

from scripts.generate_academic_retrieval_training import build_training_examples, corpus_report


def test_training_corpus_is_deterministic_and_unique():
    first = build_training_examples()
    second = build_training_examples()
    assert [x.example_id for x in first] == [x.example_id for x in second]
    assert len({x.example_id for x in first}) == len(first)
    assert len({x.utterance.casefold() for x in first}) == len(first)


def test_semantic_families_do_not_leak_across_splits():
    examples = build_training_examples()
    report = corpus_report(examples)
    assert report["family_split_leakage"] == ()
    for family in {x.family for x in examples}:
        assert len({x.split for x in examples if x.family == family}) == 1


def test_asymmetric_family_never_cross_binds_subject_facets():
    rows = [x for x in build_training_examples() if x.family == "two_subject_asymmetric_facets"]
    assert rows
    for row in rows:
        assert len(row.plan.needs) == 2
        left, right = row.plan.needs
        assert left.subject_ids != right.subject_ids
        assert left.facet != right.facet


def test_historical_family_has_directional_source_dependency():
    rows = [x for x in build_training_examples() if x.family == "past_question_to_note_dependency"]
    assert rows
    for row in rows:
        history, notes = row.plan.needs
        assert history.sources == ("past_questions",)
        assert notes.sources == ("notes",)
        assert notes.depends_on == (history.need_id,)
        assert ("student_marking_is_truth", "false") in row.plan.metadata


def test_comparison_family_has_same_dimension_on_both_explicit_sides():
    rows = [x for x in build_training_examples() if x.family == "symmetric_comparison"]
    assert rows
    for row in rows:
        assert row.plan.answer_operation == "compare"
        assert row.plan.comparisons
        left, right = row.plan.needs
        assert left.subject_ids != right.subject_ids
        assert left.facet == right.facet
        assert row.plan.comparisons[0].dimensions == (left.facet,)


def test_training_examples_are_not_live_parser_outputs():
    # Gold plans are constructed from controlled semantics.  The current rule
    # parser is deliberately not called by the generator, preventing today's
    # parser mistakes from becoming tomorrow's training labels.
    import inspect
    import scripts.generate_academic_retrieval_training as generator

    source = inspect.getsource(generator)
    assert "decompose_academic_query" not in source
    assert "build_dental_requirement_plan" not in source


def test_every_declared_split_has_examples():
    report = corpus_report(build_training_examples())
    assert report["by_split"]["train"] > 0
    assert report["by_split"]["validation"] > 0
    assert report["by_split"]["test"] > 0


def test_training_surface_does_not_overlap_frozen_85k_benchmarks():
    from app.dental_knowledge_graph import ALL_NODES
    from tests.academic_v2.test_intent_benchmark_15k import _rows as rows15
    from tests.academic_v2.test_intent_holdout_20k import _rows as rows20, _norm
    from tests.academic_v2.test_utility_holdout_50k import _rows as rows50, _skeleton

    old15 = rows15()
    old20, _ = rows20()
    old50, _, _ = rows50()
    old = (*old15, *old20, *old50)
    old_norm = {_norm(row[0]) for row in old}
    labels = tuple(dict.fromkeys(node.label for node in ALL_NODES))
    old_skeletons = {_skeleton(row[0], labels) for row in old}

    for example in build_training_examples():
        assert _norm(example.utterance) not in old_norm
        # Use every canonical label, not only the example subject, so this test
        # cannot hide overlap by choosing a convenient replacement vocabulary.
        assert _skeleton(example.utterance, labels) not in old_skeletons


def test_negative_fact_and_exclusion_are_distinct_semantics():
    rows = build_training_examples()
    negative = [x for x in rows if x.family == "negative_fact"]
    excluded = [x for x in rows if x.family == "explicit_exclusion"]
    assert negative and excluded
    assert all(x.plan.needs[0].polarity == "negative" for x in negative)
    assert all(x.plan.excluded_facets == ("treatment",) for x in excluded)
    assert all(x.plan.needs[0].polarity == "positive" for x in excluded)


def test_numeric_family_preserves_unit_operator_and_bounds():
    rows = [x for x in build_training_examples() if x.family == "numeric_threshold"]
    assert rows
    constraints = [x.plan.needs[0].value_constraints[0] for x in rows]
    assert all(c.unit == "mm" for c in constraints)
    assert {c.operator for c in constraints} == {"gte", "range"}
    ranged = next(c for c in constraints if c.operator == "range")
    assert ranged.value == 2.0 and ranged.upper_value == 4.0


def test_logical_alternative_is_any_not_all():
    rows = [x for x in build_training_examples() if x.family == "logical_alternative"]
    assert len(rows) == 1
    assert rows[0].plan.need_groups[0].mode == "any"


def test_qualified_family_binds_qualifier_to_its_need():
    rows = [x for x in build_training_examples() if x.family == "qualified_subject"]
    assert rows
    assert all(x.plan.needs[0].qualifiers for x in rows)
