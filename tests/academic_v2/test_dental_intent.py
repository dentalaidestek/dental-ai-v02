from app.dental_query_intent import classify_dental_intent

CASES = {
    "ANB normal değeri kaçtır": "value",
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
