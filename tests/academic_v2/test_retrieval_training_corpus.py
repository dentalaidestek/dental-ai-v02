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
