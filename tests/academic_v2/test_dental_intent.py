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
