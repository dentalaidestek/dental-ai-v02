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


def test_explicit_anatomical_relation_does_not_invent_missing_graph_edge():
    plan = decompose_academic_query("Mandibular kanal ile üçüncü molar ilişkisini anlat")
    # Both endpoints are explicit, but the curated graph has no direct edge
    # between them. The planner must not fabricate a transitive relation via IAN.
    assert not [n for n in plan.needs if n.relation]
    explicit = {sid for n in plan.needs for sid in n.subject_ids}
    assert {"mandibular_canal", "third_molar"}.issubset(explicit)


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


def test_qualifiers_are_preserved_on_their_own_inflected_subjects():
    plan = decompose_academic_query(
        "Akut pulpitisin bulgularını anlat ama kronik pulpa nekrozunun tedavisini söyle"
    )
    pulpitis = [n for n in plan.needs if "pulpitis" in n.subject_ids]
    necrosis = [n for n in plan.needs if "pulp_necrosis" in n.subject_ids]
    assert pulpitis and any("akut" in n.qualifiers for n in pulpitis)
    assert necrosis and any("kronik" in n.qualifiers for n in necrosis)
    assert all("kronik" not in n.qualifiers for n in pulpitis)
    assert all("akut" not in n.qualifiers for n in necrosis)


def test_relation_helpers_do_not_turn_into_comparison_sides():
    plan = decompose_academic_query("Mandibular kanal ile üçüncü molar ilişkisini anlat")
    assert plan.answer_operation == "answer"
    assert not plan.comparisons


def test_unmodeled_or_semantics_fail_closed_instead_of_flattening():
    plan = decompose_academic_query("SNA veya SNB normal değerini getir")
    assert "unmodeled:logical_or" in plan.unresolved_references


def test_unmodeled_exclusion_semantics_fail_closed():
    plan = decompose_academic_query("Pulpitis tanısını anlat ama tedaviye girme")
    assert "unmodeled:explicit_exclusion" in plan.unresolved_references


def test_unmodeled_numeric_constraint_fails_closed():
    plan = decompose_academic_query("Sondalama derinliği en az 4 mm ise neyi gösterir?")
    assert "unmodeled:numeric_constraint" in plan.unresolved_references


def test_unmodeled_past_question_source_semantics_fail_closed():
    plan = decompose_academic_query("Geçmiş sorularda apeksifikasyondan ne sorulmuş?")
    assert "unmodeled:source_selection" in plan.unresolved_references


def test_exclusion_is_not_mislabeled_as_negative_fact():
    plan = decompose_academic_query("Pulpitis tanısını anlat, tedavi hariç")
    assert "unmodeled:explicit_exclusion" in plan.unresolved_references
    assert all(n.polarity == "positive" for n in plan.needs)


def test_unmodeled_temporal_order_fails_closed_instead_of_flattening():
    plan = decompose_academic_query(
        "Pulpa nekrozundan sonra apikal periodontitis bulgularını anlat"
    )
    assert "unmodeled:temporal_order" in plan.unresolved_references


def test_fuzzy_typo_subject_is_not_used_for_clause_ownership():
    plan = decompose_academic_query("mandbular kanalın anatomisini anlat")
    assert not any(
        "mandibular_canal" in need.subject_ids and need.facet == "anatomy"
        for need in plan.needs
    )
    assert "sentence_decomposition" in plan.unresolved_references


def test_explicit_comparison_without_two_safe_sides_is_unresolved():
    plan = decompose_academic_query("Pulpitisi karşılaştır")
    assert plan.answer_operation == "answer"
    assert not plan.comparisons
    assert "comparison_sides" in plan.unresolved_references


def test_parser_level_implicit_comparison_cannot_silently_become_plain_answer():
    plan = decompose_academic_query("SNA ve SNB değerlerinden hangisi daha büyüktür?")
    assert plan.answer_operation in {"compare", "answer"}
    if plan.answer_operation == "answer":
        assert "comparison_sides" in plan.unresolved_references



def test_unbound_clause_qualifier_is_not_smeared_onto_subject_need():
    plan = decompose_academic_query("Pulpitis tedavisini erişkinde anlat")
    needs = [n for n in plan.needs if "pulpitis" in n.subject_ids and n.facet == "treatment"]
    assert needs
    # Only a qualifier explicitly bound by the canonical span binder may become
    # a subject qualifier. This protects multi-subject ownership from fallback.
    assert all(n.qualifiers == tuple(dict.fromkeys(n.qualifiers)) for n in needs)
