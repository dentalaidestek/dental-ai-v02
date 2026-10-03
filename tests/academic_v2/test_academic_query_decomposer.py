from __future__ import annotations

from app.academic_query_decomposer import decompose_academic_query


def _pairs(query):
    plan = decompose_academic_query(query)
    return plan, {(n.subject_ids[0] if n.subject_ids else n.subject_terms[0], n.facet) for n in plan.needs}


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


def test_negative_direction_survives_decomposition():
    plan, pairs = _pairs("Bisfosfonatın hangi durumlarda kullanılması önerilmez?")
    assert any(n.polarity == "negative" for n in plan.needs)
    assert any(facet == "contraindication" for _, facet in pairs)


def test_no_subject_invention_for_pronoun_only_query():
    plan = decompose_academic_query("Bunun tedavisini ve komplikasyonlarını anlat")
    assert plan.unresolved_references
    assert all(
        "<unresolved>" in need.subject_terms or need.subject_terms
        for need in plan.needs
    )


def test_treatment_named_subject_does_not_become_treatment_request():
    plan, pairs = _pairs("Kanal tedavisi komplikasyonlarını anlat")
    assert any(facet == "complication" for _, facet in pairs)
    assert all(facet != "treatment" for _, facet in pairs)
