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

def test_reconciliation_never_promotes_case_values_to_reference():
    from app.dental_semantics import bind_value_evidence, reconcile_value_evidence
    items = bind_value_evidence("Bu hastada SNA 86° ölçüldü. Olgu B için SNA 78° saptandı.")
    result = reconcile_value_evidence(items)
    assert result.status == "observations_only"
    assert not result.reference_values

def test_reconciliation_normalizes_equivalent_reference_spellings():
    from app.dental_semantics import bind_value_evidence, reconcile_value_evidence
    items = bind_value_evidence("SNA normal değeri 82° dir. SNA referans değeri 82,0 derece olarak kabul edilir.")
    result = reconcile_value_evidence(items)
    assert result.status == "reference_supported"

def test_reconciliation_separates_conditioned_reference_values():
    from app.dental_semantics import bind_value_evidence, reconcile_value_evidence
    a = bind_value_evidence("Gonial açı yenidoğanda normal olarak 180 dereceye yakındır.")
    b = bind_value_evidence("Bebeklikte büyüme ile gonial açı ortalama 130 dereceye iner.")
    result = reconcile_value_evidence(tuple(a) + tuple(b))
    assert result.status == "conditioned"

def test_unknown_lexical_subject_value_binding_is_graph_independent():
    from app.dental_semantics import bind_value_evidence
    items = bind_value_evidence("XYZ indeksi normal değeri 42 derecedir.")
    assert items
    assert items[0].subject_node_id is None
    assert items[0].subject_text
    assert "xyz" in items[0].subject_text.casefold()
    assert items[0].assertion == "reference"

def test_unknown_subject_case_value_stays_observation():
    from app.dental_semantics import bind_value_evidence, reconcile_value_evidence
    items = bind_value_evidence("Bu hastada QRT skoru 17 olarak ölçüldü.")
    assert items
    assert items[0].subject_node_id is None
    assert items[0].assertion == "observation"
    assert reconcile_value_evidence(items).status == "observations_only"


def test_value_pipeline_scenario_family_matrix():
    from app.dental_semantics import bind_value_evidence, extract_value_evidence, reconcile_value_evidence

    positive_values = (
        "X normal değeri 82° dir.",
        "X normal değeri 82,0 derece olarak kabul edilir.",
        "X oranı yüzde 20 dir.",
        "X oranı %20 dir.",
        "X yaklaşık 2–4 mm arasındadır.",
        "X tedavi süresi 7 gün olarak verilir.",
    )
    for source in positive_values:
        assert extract_value_evidence(source), source

    false_numeric_contexts = (
        "5 yaşındaki hasta değerlendirildi.",
        "Çalışmada 90 hasta vardı.",
        "sayfa 36",
        "page 82",
        "36 numaralı diş değerlendirildi.",
    )
    for source in false_numeric_contexts:
        assert not extract_value_evidence(source), source

    known = bind_value_evidence("SNA 82° iken SNB 80° olarak ölçülür.")
    assert [item.subject_node_id for item in known] == ["sna", "snb"]

    unknown = bind_value_evidence("XYZ indeksi normal değeri 42 derecedir.")
    assert unknown and unknown[0].subject_node_id is None
    assert "xyz" in (unknown[0].subject_text or "").casefold()

    observation = bind_value_evidence("Bu hastada QRT skoru 17 olarak ölçüldü.")
    assert observation and observation[0].assertion == "observation"
    assert reconcile_value_evidence(observation).status == "observations_only"

    equivalent = bind_value_evidence(
        "XYZ indeksi normal değeri 82° dir. XYZ indeksi referans değeri 82,0 derece olarak kabul edilir."
    )
    assert reconcile_value_evidence(equivalent).status == "reference_supported"

    conflict = bind_value_evidence(
        "XYZ indeksi normal değeri 82° dir. XYZ indeksi referans değeri 83 derece olarak kabul edilir."
    )
    assert reconcile_value_evidence(conflict).status == "conflict"

    conditioned = (
        bind_value_evidence("Y açısı yenidoğanda normal 180 derecedir.")
        + bind_value_evidence("Y açısı erişkinde normal 130 derecedir.")
    )
    assert reconcile_value_evidence(conditioned).status == "conditioned"
