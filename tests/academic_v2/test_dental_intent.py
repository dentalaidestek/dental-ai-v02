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
    assert len(intents) <= 3
