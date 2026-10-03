from __future__ import annotations

from app.academic_query_decomposer import decompose_academic_query


def _pairs(query):
    plan = decompose_academic_query(query)
    pairs = {(n.subject_ids[0] if n.subject_ids else n.subject_terms[0], n.facet) for n in plan.needs}
    return plan, pairs


def test_single_subject_keeps_multiple_requested_facets():
    plan, pairs = _pairs("İrreversible pulpitisin tanısı, tedavisi ve komplikasyonları nelerdir?")
    assert ("irreversible_pulpitis", "diagnosis") in pairs
    assert ("irreversible_pulpitis", "treatment") in pairs
    assert ("irreversible_pulpitis", "complication") in pairs
    assert not plan.unresolved_references


def test_asymmetric_coordinated_subjects_do_not_cross_bind_facets():
    plan, pairs = _pairs("İrreversible pulpitisin tanısı ve reversible pulpitisin tedavisi")
    assert ("irreversible_pulpitis", "diagnosis") in pairs
    assert ("reversible_pulpitis", "treatment") in pairs
    assert ("irreversible_pulpitis", "treatment") not in pairs
    assert ("reversible_pulpitis", "diagnosis") not in pairs


def test_adversative_clauses_keep_subject_and_facet_local():
    plan, pairs = _pairs("MRONJ bulgularını anlat ama dry socket tedavisini söyle")
    assert ("mronj", "diagnosis") in pairs
    assert ("dry_socket", "treatment") in pairs
    assert ("mronj", "treatment") not in pairs


def test_symmetric_comparison_can_bind_one_dimension_to_both_sides():
    plan, pairs = _pairs("SNA ile SNB normal değerlerini karşılaştır")
    assert ("sna", "value") in pairs
    assert ("snb", "value") in pairs
    assert plan.answer_operation == "compare"
    assert plan.comparisons


def test_ambiguous_multi_subject_multi_facet_sentence_stays_unresolved():
    plan, _ = _pairs("SNA ve SNB için değer ve ölçüm mantığını anlat")
    assert any("subject_facet_binding" in item for item in plan.unresolved_references)


def test_negation_is_clause_local_not_global():
    plan, pairs = _pairs(
        "Bisfosfonatın endikasyonlarını anlat ama kontrendikasyonlarını da söyle"
    )
    indication = [n for n in plan.needs if n.facet == "indication"]
    contraindication = [n for n in plan.needs if n.facet == "contraindication"]
    assert indication and all(n.polarity == "positive" for n in indication)
    # Contraindication is itself a negative applicability facet; polarity only
    # records explicit sentence negation and therefore remains positive here.
    assert contraindication and all(n.polarity == "positive" for n in contraindication)


def test_explicit_negative_direction_stays_local():
    plan, _ = _pairs("Bisfosfonat hangi durumda önerilmez?")
    assert any(n.polarity == "negative" for n in plan.needs)


def test_no_subject_invention_for_pronoun_only_query():
    plan = decompose_academic_query("Bunun tedavisini ve komplikasyonlarını anlat")
    assert plan.unresolved_references
    assert plan.needs[0].subject_terms == ("<unresolved>",)


def test_treatment_named_subject_does_not_become_treatment_request():
    plan, pairs = _pairs("Kanal tedavisi komplikasyonlarını anlat")
    assert any(facet == "complication" for _, facet in pairs)
    assert all(facet != "treatment" for _, facet in pairs)


def test_explicit_anatomical_relation_keeps_both_query_endpoints():
    plan = decompose_academic_query("Mandibular kanal ile üçüncü molar ilişkisini anlat")
    relation_needs = [n for n in plan.needs if n.relation]
    assert relation_needs
    assert all(n.target_subject_ids for n in relation_needs)
    explicit = {sid for n in plan.needs for sid in n.subject_ids}
    assert all(n.target_subject_ids[0] in explicit for n in relation_needs)


def test_graph_does_not_invent_unasked_relation_target():
    plan = decompose_academic_query("Üçüncü moların komplikasyonlarını anlat")
    assert all(not n.relation for n in plan.needs)


def test_qualifier_does_not_jump_between_separate_clauses():
    plan = decompose_academic_query(
        "Akut pulpitis bulgularını anlat ama kronik pulpa nekrozu tedavisini söyle"
    )
    for need in plan.needs:
        if "pulp_necrosis" in need.subject_ids:
            assert "akut" not in need.qualifiers
        if "pulpitis" in need.subject_ids:
            assert "kronik" not in need.qualifiers
