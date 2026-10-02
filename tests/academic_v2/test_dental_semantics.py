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
