from app.dental_semantics import analyze_dental_text, semantic_overlap_score, retrieval_enrichment_text

q = analyze_dental_text("48 numaralı diş inferior alveolar kanala yakın mı CBCT'de?")
c1 = analyze_dental_text("48 mandibular kanal inferior alveolar sinir CBCT kesitleri")
c2 = analyze_dental_text("11 numaralı dişte mine çürüğü bitewing görüntüsü")
assert "48" in q.tooth_numbers
assert "cbct" in q.imaging_types
assert semantic_overlap_score(q, c1) > semantic_overlap_score(q, c2)

q2 = analyze_dental_text("ANB 6°")
c3 = analyze_dental_text("ANB açısı 2° ± 2° olarak değerlendirilir")
assert "6°" in q2.measurements
assert "anb" in q2.node_ids
assert semantic_overlap_score(q2, c3) > 0

q3 = analyze_dental_text("sondalama derinliği 6 mm")
assert "probing_depth" in q3.node_ids
assert "6 mm" in q3.measurements

print("Dental semantic feature checks: OK")

enriched = retrieval_enrichment_text("Alt çene mandibula SNB açısı 80°")
assert "mandibula" in enriched.casefold()
assert "orthodontics" in enriched.casefold()
assert len(enriched.split()) <= 24


# FDI numbers need dental context; ordinary ages/pages must not become teeth.
assert "24" not in analyze_dental_text("24 yaşında hasta, sayfa 36").tooth_numbers
assert "36" not in analyze_dental_text("24 yaşında hasta, sayfa 36").tooth_numbers
assert "48" in analyze_dental_text("48 numaralı diş mandibular kanala yakın").tooth_numbers


def test_negation_is_clause_local_and_does_not_erase_positive_mentions():
    from app.dental_semantics import analyze_dental_text
    negative = analyze_dental_text("Periapikal lezyon görülmedi.")
    assert "periapical_lesion" in negative.negated_node_ids

    mixed = analyze_dental_text(
        "Başlangıçta periapikal lezyon görülmedi; ancak kontrolde periapikal lezyon saptandı."
    )
    assert "periapical_lesion" in mixed.node_ids
    assert "periapical_lesion" not in mixed.negated_node_ids


def test_fdi_context_does_not_capture_age_or_page_next_to_real_tooth():
    from app.dental_semantics import analyze_dental_text

    mixed = analyze_dental_text("35 yaşındaki hastanın 36 numaralı dişi endodontik olarak değerlendirildi")
    assert "36" in mixed.tooth_numbers
    assert "35" not in mixed.tooth_numbers

    page = analyze_dental_text("sayfa 46: 36 numaralı diş için kök kanal anatomisi")
    assert "36" in page.tooth_numbers
    assert "46" not in page.tooth_numbers


def test_generic_value_parser_positive_and_negative_matrix():
    from app.dental_semantics import extract_value_evidence

    positives = {
        "SNA 82°": "measurement",
        "uzunluk -2.5 mm": "measurement",
        "uzunluk 2,5 mm": "measurement",
        "oran yüzde 20": "percentage",
        "oran yüzde yirmi": "percentage",
        "gonial açı yüz otuz derece": "measurement",
        "normal değeri 82": "value",
        "referans değeri seksen iki": "value",
        "değeri 2 ile 4 mm": "value",
        "yaklaşık 80–84°": "range",
    }
    for text_value, expected_kind in positives.items():
        evidence = extract_value_evidence(text_value)
        assert evidence, text_value
        assert any(item.kind == expected_kind for item in evidence), (text_value, evidence)

    for text_value in (
        "20 hasta incelendi",
        "20 yaşındaki bireyler",
        "sayfa 82",
        "page 36",
        "örneklem 40 kişiden oluştu",
        "36 numaralı diş",
    ):
        assert not extract_value_evidence(text_value), (text_value, extract_value_evidence(text_value))


def test_value_parser_keeps_offsets_for_future_subject_binding():
    from app.dental_semantics import extract_value_evidence
    text_value = "SNA 82° iken SNB 80° olarak ölçülür."
    evidence = extract_value_evidence(text_value)
    assert [item.text for item in evidence] == ["82°", "80°"]
    assert text_value[evidence[0].start:evidence[0].end] == "82°"
    assert text_value[evidence[1].start:evidence[1].end] == "80°"
    assert evidence[0].end < evidence[1].start


def test_value_assertion_distinguishes_reference_observation_and_variability():
    from app.dental_semantics import extract_value_evidence, classify_value_assertion

    cases = (
        ("SNA'nın normal değeri 82°'dir.", "reference"),
        ("SNA genellikle 82° civarındadır.", "reference"),
        ("Bu hastada SNA 86° ölçüldü.", "observation"),
        ("Olgu 3'te SNB 74° saptandı.", "observation"),
        ("Bu örneklemde ortalama ANB 5° bulundu.", "observation"),
        ("ANB değeri hastaya göre 2° ile 7° arasında değişebilir.", "variable"),
        ("SNA kesinlikle 82°'dir.", "asserted"),
        ("SNA 82°.", "unknown"),
    )
    for text_value, expected in cases:
        values = extract_value_evidence(text_value)
        assert values, text_value
        assertion, confidence = classify_value_assertion(text_value, values[0])
        assert assertion == expected, (text_value, assertion, values)
        assert 0.0 < confidence <= 1.0


def test_case_measurements_cannot_masquerade_as_reference_values():
    from app.dental_semantics import extract_value_evidence, classify_value_assertion

    passages = (
        "Hasta A'da SNA 86° ölçüldü.",
        "Hasta B'de SNA 78° ölçüldü.",
        "Kontrol olgusunda SNA 84° saptandı.",
    )
    roles = []
    for passage in passages:
        value = extract_value_evidence(passage)[0]
        roles.append(classify_value_assertion(passage, value)[0])
    assert roles == ["observation", "observation", "observation"]
    assert "reference" not in roles

def test_value_binding_keeps_subjects_separate_and_ambiguity_unbound():
    from app.dental_semantics import bind_value_evidence
    bound = bind_value_evidence("SNA 82° iken SNB 80° olarak ölçülür.")
    assert len(bound) == 2
    assert bound[0].subject_node_id == "sna"
    assert bound[1].subject_node_id == "snb"
    ambiguous = bind_value_evidence("SNA ve SNB için değer 81° olarak verildi.")
    assert ambiguous
    assert ambiguous[0].subject_node_id is None

def test_observation_binding_never_becomes_reference_by_proximity():
    from app.dental_semantics import bind_value_evidence
    bound = bind_value_evidence("Bu hastada SNA 86° ölçüldü.")
    assert bound
    assert bound[0].subject_node_id == "sna"
    assert bound[0].assertion == "observation"

def test_real_note_gonial_values_keep_age_context():
    from app.dental_semantics import bind_value_evidence
    a = bind_value_evidence("Gonial açı yeni doğmuş bebeklerde oldukça büyüktür (180 dereceye yakın).")
    b = bind_value_evidence("Bebeklik döneminde normal kabul edilen bu açı değeri yaşın ilerlemesine, büyüme ve gelişime bağlı olarak küçülür ve ortalama 130 dereceye iner.")
    assert a and b
    assert "newborn" in a[0].qualifiers
    assert "infant" in b[0].qualifiers
    assert "growth" in b[0].qualifiers
    assert a[0].value.text != b[0].value.text

def test_real_note_fetal_measurements_are_conditioned_observations():
    from app.dental_semantics import bind_value_evidence
    source = "49 mm fetüste vertikal çap 1 mm; 160 mm fetüste vertikal çap 3,5 mm; 216 mm fetüste vertikal çap 7,5 mm."
    values = bind_value_evidence(source)
    measured = [item for item in values if item.value.text in {'1 mm', '3,5 mm', '7,5 mm'}]
    assert len(measured) == 3
    assert all("fetal" in item.qualifiers for item in measured)

def test_chunk_metadata_persists_value_context_not_consensus():
    from pathlib import Path
    source = Path("app/study_index_worker.py").read_text(encoding="utf-8")
    assert '"qualifiers": item.qualifiers' in source
    assert '"context": item.context_text' in source
    assert '"consensus"' not in source.split("def _chunk_slice", 1)[1]
