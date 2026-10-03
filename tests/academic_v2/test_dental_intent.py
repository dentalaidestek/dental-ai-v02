from app.dental_query_intent import classify_dental_intent

CASES = {
    "ANB normal değeri kaçtır": "value",
    "ANB değerleri nelerdir": "value",
    "alt çenenin konumunu hangi açıyla değerlendiririz": "measurement",
    "apikal konstriksiyon nedir": "definition",
    "periodontitis sınıflaması": "classification",
    "implant endikasyonları": "indication",
    "implant kontrendikasyonları": "contraindication",
    "gömülü diş komplikasyonları": "complication",
    "pulpitis bulguları": "diagnosis",
    "CBCT hangi durumda kullanılır": "indication",
    "implant için kontrendikasyonlar": "contraindication",
    "gömülü üçüncü moların komplikasyonları": "complication",
    "radyografik bulgularla tanı nasıl konur": "diagnosis",
    "pulpitis tedavisi": "treatment",
    "inferior alveolar sinir nerede seyreder": "anatomy",
    "panoramik görüntüde ne görülüyor": "visual",
    "SNA ile SNB farkı": "comparison",
    "kök rezorpsiyonu neden olur": "cause",
}
for query, expected in CASES.items():
    got = classify_dental_intent(query).name
    assert got == expected, (query, expected, got)

assert classify_dental_intent("bunu açıklar mısın").name == "general"
print("Dental intent checks: OK")


def test_multi_intent_planner_captures_explicit_combined_requirements():
    from app.dental_query_intent import classify_dental_intents, combined_relation_hints

    intents = classify_dental_intents("irreversible pulpitis tanısı bulguları ve tedavisi")
    names = {intent.name for intent in intents}
    assert "diagnosis" in names
    assert "treatment" in names
    hints = set(combined_relation_hints(intents))
    assert "has_treatment" in hints
    assert "has_clinical_feature" in hints


def test_subject_treatment_phrase_does_not_create_false_treatment_intent():
    from app.dental_query_intent import classify_dental_intents

    intents = classify_dental_intents("kanal tedavisi komplikasyonları nelerdir")
    names = {intent.name for intent in intents}
    assert "complication" in names
    assert "treatment" not in names


def test_multi_intent_plan_is_bounded():
    from app.dental_query_intent import classify_dental_intents

    intents = classify_dental_intents(
        "tanısı bulguları tedavisi komplikasyonları sınıflaması ve nedeni"
    )
    assert len(intents) <= 6


def test_student_study_generation_plan_separates_topic_and_coverage():
    from app.dental_query_intent import classify_dental_study_plan

    topic = classify_dental_study_plan("ANB açısından 20 zor çoktan seçmeli soru hazırla")
    assert topic is not None
    assert topic.mode == "topic"
    assert topic.count == 20
    assert topic.difficulty == "zor"
    assert "mcq" in topic.question_types

    coverage = classify_dental_study_plan(
        "Bu notun tamamındaki bütün sınav noktalarından 80 soru üret"
    )
    assert coverage is not None
    assert coverage.mode == "coverage"
    assert coverage.count == 80
    assert coverage.coverage_required is True


def test_normal_dental_question_is_not_study_generation():
    from app.dental_query_intent import classify_dental_study_plan

    assert classify_dental_study_plan("ANB açısının normal değeri kaçtır?") is None


def test_academic_study_workflows_are_source_bound_and_distinct():
    from app.dental_query_intent import classify_academic_study_task

    repeated = classify_academic_study_task("Hocanın sürekli sorduğu soruları ve konuları ayır")
    assert repeated and repeated.task == "repeated_patterns"
    assert repeated.requires_past_questions and repeated.requires_note_evidence
    assert not repeated.generate_new_questions

    similar = classify_academic_study_task("Çıkmış sorulara benzer 15 soru üret")
    assert similar and similar.task == "similar_questions"
    assert similar.requires_past_questions and similar.requires_note_evidence
    assert similar.generate_new_questions

    explain = classify_academic_study_task("Bu konuyu bana anlat")
    assert explain and explain.task == "explain"
    assert explain.requires_note_evidence and not explain.requires_past_questions

    exam = classify_academic_study_task("Hocanın sorabileceği önemli yerleri çıkar")
    assert exam and exam.task == "exam_points"
    assert exam.requires_note_evidence and exam.requires_coverage


def test_broad_non_question_academic_tasks_require_coverage():
    from app.dental_query_intent import classify_academic_study_task
    summary = classify_academic_study_task("Bu notun tamamını detaylı özetle")
    assert summary and summary.task == "summarize"
    assert summary.requires_coverage and summary.requires_note_evidence
    assert not summary.generate_new_questions

    explain = classify_academic_study_task("Bu konuyu baştan sona detaylı anlat")
    assert explain and explain.task == "explain"
    assert explain.requires_coverage and explain.requires_note_evidence


def test_requirement_plan_separates_subject_from_multiple_facets():
    from app.dental_query_intent import build_dental_requirement_plan
    plan = build_dental_requirement_plan(
        "İrreversible pulpitisin tanısı, klinik bulguları, ayırıcı tanısı ve tedavisi nedir?"
    )
    assert "diagnosis" in plan.requested_facets
    assert "treatment" in plan.requested_facets
    assert "has_treatment" in plan.relation_hints
    assert len(plan.requested_facets) >= 2

def test_requirement_plan_keeps_treatment_subject_from_becoming_requested_treatment():
    from app.dental_query_intent import build_dental_requirement_plan
    plan = build_dental_requirement_plan("Kanal tedavisinin komplikasyonları nelerdir?")
    assert "complication" in plan.requested_facets


def test_unknown_dental_subject_keeps_lexical_anchor():
    from app.dental_query_intent import build_dental_requirement_plan
    plan = build_dental_requirement_plan("Gorlin-Goltz sendromunun klinik bulguları ve tedavisi nelerdir?")
    assert plan.subject_terms
    assert any("gorlin" in term.casefold() for term in plan.subject_terms)
    assert "diagnosis" in plan.requested_facets or "treatment" in plan.requested_facets

def test_many_explicit_facets_are_not_truncated_to_three():
    from app.dental_query_intent import build_dental_requirement_plan
    plan = build_dental_requirement_plan(
        "Lezyonun tanımı, etyolojisi, tanısı, sınıflaması, tedavisi ve komplikasyonları nelerdir?"
    )
    assert len(plan.requested_facets) >= 4


def test_generic_nedir_does_not_create_fake_definition_facet():
    from app.dental_query_intent import build_dental_requirement_plan
    plan = build_dental_requirement_plan("irreversible pulpitisin tanısı ve tedavisi nedir?")
    assert "diagnosis" in plan.requested_facets
    assert "treatment" in plan.requested_facets
    assert "definition" not in plan.requested_facets


def test_exam_salience_intent_generalizes_across_unseen_phrasings():
    from app.dental_query_intent import classify_academic_study_task
    cases = (
        "Değerlendirmede önemli olabilecek başlıkları belirle.",
        "Kritik bilgileri bul ve listele.",
        "Sınavda sorulma olasılığı yüksek konuları göster.",
        "Öncelikli noktaları çıkar.",
        "Hocanın sorabileceği kısımları belirle.",
        "Soru gelme ihtimali yüksek bölümleri bul.",
    )
    for query in cases:
        plan = classify_academic_study_task(query)
        assert plan is not None, query
        assert plan.task == "exam_points", (query, plan)
        assert plan.requires_note_evidence, (query, plan)


def test_recurrence_and_risk_factor_morphology_are_semantic_not_literal():
    from app.dental_query_intent import classify_academic_study_task, build_dental_requirement_plan
    recurrence_cases = (
        "En sık tekrar eden soru konularını çıkar.",
        "Sıkça sorulan konuları bul.",
        "Tekrarlanan soru başlıklarını belirle.",
        "Soru konularından hangileri sık yineleniyor?",
    )
    for query in recurrence_cases:
        plan = classify_academic_study_task(query)
        assert plan is not None, query
        assert plan.task == "repeated_patterns", (query, plan)

    for query in (
        "İmplantın risk faktörlerini açıkla.",
        "MRONJ risk faktörleri nelerdir?",
        "Risk faktörlerini ve komplikasyonları birlikte özetle.",
    ):
        plan = build_dental_requirement_plan(query)
        assert "cause" in plan.requested_facets, (query, plan.requested_facets)


def test_measurement_intent_understands_assessed_structure_morphology():
    from app.dental_query_intent import build_dental_requirement_plan
    cases = (
        "SNA'nın değerlendirdiği yapı nedir?",
        "SNA ve SNB'nin değerlendirdikleri yapıları karşılaştır.",
        "Bu açının değerlendirdiği parametre hangisidir?",
        "Bu ölçümlerin değerlendirdikleri ilişkileri açıkla.",
    )
    for query in cases:
        plan = build_dental_requirement_plan(query)
        assert "measurement" in plan.requested_facets, (query, plan.requested_facets)


def test_value_intent_understands_measurement_change_not_only_literal_numbers():
    from app.dental_query_intent import build_dental_requirement_plan
    cases = (
        "Gonial açı yaşla nasıl değişir?",
        "Bu ölçüm çocukluktan erişkinliğe nasıl değişiyor?",
        "Oranın dönemler arasındaki değişimini açıkla.",
        "Açıdaki artış ve azalışı dönemlere göre anlat.",
    )
    for query in cases:
        plan = build_dental_requirement_plan(query)
        assert "value" in plan.requested_facets, (query, plan.requested_facets)


def test_value_noun_does_not_confuse_degerlendirmek_and_negation_inflects():
    from app.dental_query_intent import classify_dental_intent, build_dental_requirement_plan
    assert classify_dental_intent("alt çenenin konumunu hangi açıyla değerlendiririz").name == "measurement"
    for query in (
        "Kanal tedavisinde kullanılmaması gereken hangisidir?",
        "Bu durumda yapılmaması gereken işlem nedir?",
        "Hangi uygulamadan kaçınılması gerekir?",
    ):
        assert build_dental_requirement_plan(query).asks_negation, query


def test_measurement_intent_tracks_assessment_semantics_across_morphology():
    from app.dental_query_intent import build_dental_requirement_plan
    cases = (
        "Bu ölçümlerin değerlendirdiği yapıları karşılaştır.",
        "Bu açı hangi yapısal ilişkiyi değerlendiriyor?",
        "Ölçümlerin temsil ettiği anatomik ilişkileri açıkla.",
        "Hangi parametre neyi değerlendirir?",
    )
    for query in cases:
        plan = build_dental_requirement_plan(query)
        assert "measurement" in plan.requested_facets, (query, plan.requested_facets)


def test_negative_polarity_understands_wrong_and_not_true_forms():
    from app.dental_query_intent import build_dental_requirement_plan
    for query in (
        "Periodontitis için yanlış olan ifadeyi bul.",
        "Hangisi yanlış?",
        "Doğru olmayan seçeneği işaretle.",
        "Bu konuda doğru değildir denebilecek ifade hangisi?",
    ):
        assert build_dental_requirement_plan(query).asks_negation, query


def test_second_hundred_unseen_academic_questions_route_by_concept():
    """100 fresh phrasings, deliberately separate from the original census."""
    from app.dental_query_intent import classify_academic_study_task, build_dental_requirement_plan

    facet_templates = [
        ("{s} neden gelişir?", "cause"),
        ("{s} için risk oluşturan etkenler nelerdir?", "cause"),
        ("{s} nasıl tedavi edilir?", "treatment"),
        ("{s} yönetiminde ne yapılır?", "treatment"),
        ("{s} hangi komplikasyonlara yol açabilir?", "complication"),
        ("{s} hangi durumlarda uygulanmamalıdır?", "contraindication"),
        ("{s} hangi durumlarda endikedir?", "indication"),
        ("{s} nasıl sınıflandırılır?", "classification"),
        ("{s} tanısında hangi bulgular kullanılır?", "diagnosis"),
        ("{s} anatomik olarak hangi yapılarla ilişkilidir?", "anatomy"),
    ]
    subjects = [
        "perikoronitis", "alveolit", "irreversible pulpitis", "periodontitis",
        "MRONJ", "dental florozis", "MIH", "apikal periodontitis",
        "gömülü üçüncü molar", "inferior alveolar sinir bloğu",
    ]
    cases = []
    for subject, (template, facet) in zip(
        (subjects * 10),
        (facet_templates * 10),
    ):
        cases.append((template.format(s=subject), facet))

    # Make the cross-product deterministic and actually broad rather than
    # pairing the same ten subjects with the same ten intents repeatedly.
    cases = []
    for si, subject in enumerate(subjects):
        for ti, (template, facet) in enumerate(facet_templates):
            rotated_subject = subjects[(si + ti) % len(subjects)]
            cases.append((template.format(s=rotated_subject), facet))

    assert len(cases) == 100
    assert len({q.casefold() for q, _ in cases}) == 100
    failures = []
    for query, expected in cases:
        plan = build_dental_requirement_plan(query)
        if expected not in plan.requested_facets:
            failures.append((query, expected, plan.requested_facets))
    assert not failures, failures


def test_semantic_role_contrasts_prevent_positive_negative_intent_leakage():
    """Intent is determined by the role of a phrase, not a single trigger token."""
    from app.dental_query_intent import build_dental_requirement_plan

    cases = (
        ("Bu durum için risk oluşturan etkenler nelerdir?", {"cause"}, {"complication"}),
        ("Bu işlemin komplikasyon riski nedir?", {"complication"}, {"cause"}),
        ("Hangi koşullarda bu yöntem uygulanabilir?", {"indication"}, set()),
        ("Hangi koşullarda bu yöntem uygulanmamalıdır?", {"contraindication"}, {"indication"}),
        ("Bu skorun referans aralığı nedir?", {"value"}, {"definition"}),
        ("Bu kavram nedir?", {"definition"}, {"value"}),
    )
    for query, required, forbidden in cases:
        facets = set(build_dental_requirement_plan(query).requested_facets)
        assert required.issubset(facets), (query, required, facets)
        assert not forbidden.intersection(facets), (query, forbidden, facets)


def test_large_semantic_intent_pressure_matrix_with_negative_controls():
    """Broad morphology/role pressure: many subjects, phrasings and inverse controls."""
    from app.dental_query_intent import build_dental_requirement_plan

    subjects = (
        "implant", "alveolit", "periodontitis", "pulpitis", "MRONJ",
        "lokal anestezi", "fissür örtücü", "flor uygulaması", "CBCT",
        "gömülü diş", "apikal lezyon", "ortodontik aparey",
    )
    families = (
        ("{s} için risk faktörleri nelerdir?", "cause"),
        ("{s} riskini artıran nedenleri açıkla.", "cause"),
        ("{s} açısından yatkınlaştıran etkenleri say.", "cause"),
        ("{s} hangi nedenlerle gelişir?", "cause"),
        ("{s} hangi durumlarda uygulanır?", "indication"),
        ("{s} hangi koşullarda kullanılabilir?", "indication"),
        ("{s} ne zaman tercih edilir?", "indication"),
        ("{s} endikasyonlarını açıkla.", "indication"),
        ("{s} hangi durumlarda uygulanmamalıdır?", "contraindication"),
        ("{s} hangi koşullarda kullanılmamalı?", "contraindication"),
        ("{s} için kontrendikasyonlar nelerdir?", "contraindication"),
        ("{s} hangi durumda önerilmez?", "contraindication"),
        ("{s} komplikasyonları nelerdir?", "complication"),
        ("{s} için yan etkileri açıkla.", "complication"),
        ("{s} komplikasyon riskini anlat.", "complication"),
        ("{s} sonrası istenmeyen etkiler nelerdir?", "complication"),
        ("{s} normal aralığı nedir?", "value"),
        ("{s} referans aralığı kaçtır?", "value"),
        ("{s} normal değeri nedir?", "value"),
        ("{s} değeri zamanla nasıl değişir?", "value"),
    )
    failures = []
    for subject in subjects:
        for template, expected in families:
            query = template.format(s=subject)
            facets = set(build_dental_requirement_plan(query).requested_facets)
            if expected not in facets:
                failures.append((query, expected, tuple(sorted(facets))))
    assert not failures, failures

    # False-positive controls: neighboring vocabulary must not leak a facet.
    controls = (
        ("Bu kavram nedir?", "value"),
        ("Tedavi sonucunu değerlendir.", "measurement"),
        ("Hastanın genel riskini değerlendir.", "cause"),
        ("Komplikasyonları açıkla.", "cause"),
        ("Risk faktörlerini açıkla.", "complication"),
        ("Bu yöntem uygulanmamalıdır.", "indication"),
        ("Bu yöntem endikedir.", "contraindication"),
        ("Bu yapının anatomik ilişkisini anlat.", "comparison"),
        ("Tanı bulgularını listele.", "treatment"),
        ("Sınıflamayı açıkla.", "diagnosis"),
    )
    leaked = []
    for query, forbidden in controls:
        facets = set(build_dental_requirement_plan(query).requested_facets)
        if forbidden in facets:
            leaked.append((query, forbidden, tuple(sorted(facets))))
    assert not leaked, leaked


def test_risk_semantic_roles_preserve_explicit_facets_and_block_neighbor_leakage():
    """Risk wording is classified by semantic role, including coordinated requests."""
    from app.dental_query_intent import build_dental_requirement_plan

    cases = (
        # Antecedent/cause role: these must not invent an adverse-outcome request.
        ("İmplant için risk faktörleri nelerdir?", {"cause"}, {"complication"}),
        ("MRONJ riskini artıran nedenleri açıkla.", {"cause"}, {"complication"}),
        ("Alveolite yatkınlaştıran etkenleri say.", {"cause"}, {"complication"}),

        # Adverse-outcome role: these must not be reinterpreted as etiology.
        ("İmplant komplikasyonları nelerdir?", {"complication"}, {"cause"}),
        ("İlacın yan etkilerini açıkla.", {"complication"}, {"cause"}),
        ("Bu işlemin komplikasyon riski nedir?", {"complication"}, {"cause"}),

        # Coordinated independent roles: neither explicit request may erase the other.
        ("İmplantın risk faktörleri ve komplikasyonları nelerdir?", {"cause", "complication"}, set()),
        ("MRONJ için yatkınlaştıran etkenleri ve yan etkileri birlikte özetle.", {"cause", "complication"}, set()),
        ("Risk faktörlerini, komplikasyonları ve kontrendikasyonları karşılaştır.", {"cause", "complication", "contraindication"}, set()),
        ("Endikasyonları, kontrendikasyonları, komplikasyonları ve risk faktörlerini özetle.", {"indication", "contraindication", "complication", "cause"}, set()),
    )

    for query, required, forbidden in cases:
        facets = set(build_dental_requirement_plan(query).requested_facets)
        assert required.issubset(facets), (query, required, facets)
        assert not forbidden.intersection(facets), (query, forbidden, facets)


def test_ascii_subject_fallback_is_positive_and_fail_closed():
    from app.dental_knowledge_graph import matched_nodes

    positives = {
        "alt cene nerede bulunur?": "mandible",
        "dis tasi nasil siniflandirilir?": "calculus",
        "sut disi nerede bulunur?": "primary_tooth",
        "alveol kemigi anatomik iliskileri nelerdir?": "alveolar_bone",
    }
    for query, expected in positives.items():
        got = {node.id for node in matched_nodes(query)}
        assert expected in got, (query, got)

    # Orthographic folding is not permission to invent a subject from ordinary
    # language or to fuzzy-match abbreviations.
    for query in (
        "bu konu nasil aciklanir?",
        "risk faktorleri nelerdir?",
        "normal deger kactir?",
        "genel olarak ne yapilir?",
    ):
        assert not [node for node in matched_nodes(query) if node.kind != "imaging"], query


def test_causal_risk_role_survives_orthography_without_complication_leak():
    from app.dental_query_intent import build_dental_requirement_plan

    positives = (
        "bone loss risk faktorleri nelerdir?",
        "oroantral aciklik risk faktorleri ve tedavisi nelerdir?",
        "MRONJ riskini artiran nedenleri acikla.",
        "alveolit icin yatkinlastiran etkenleri say.",
    )
    for query in positives:
        facets = set(build_dental_requirement_plan(query).requested_facets)
        assert "cause" in facets, (query, facets)
        assert "complication" not in facets, (query, facets)

    adverse = (
        "implant komplikasyon riski nedir?",
        "ilacin yan etkileri nelerdir?",
        "istenmeyen etkileri acikla.",
    )
    for query in adverse:
        facets = set(build_dental_requirement_plan(query).requested_facets)
        assert "complication" in facets, (query, facets)
        assert "cause" not in facets, (query, facets)

    combined = set(build_dental_requirement_plan(
        "implant risk faktorleri ve komplikasyonlari nelerdir?"
    ).requested_facets)
    assert {"cause", "complication"}.issubset(combined), combined
