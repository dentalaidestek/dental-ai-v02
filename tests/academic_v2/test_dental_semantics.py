from app.dental_semantics import analyze_dental_text, semantic_overlap_score

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
