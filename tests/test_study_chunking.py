from app.study_chunking import chunk_dental_page, normalize_extracted_text


def test_normalization_preserves_structural_lines():
    text = "TEDAVİ\n  Madde   bir  \n\n  Madde iki"
    assert normalize_extracted_text(text) == "TEDAVİ\nMadde   bir\n\nMadde iki"


def test_dental_headings_remain_attached_to_their_content():
    chunks = chunk_dental_page(
        "TANI\nSpontan ağrı ve perküsyon hassasiyeti görülür.\n"
        "TEDAVİ ENDİKASYONLARI\n• Vital pulpa tedavisi\n• Kök kanal tedavisi",
        min_chars=20,
    )
    assert [item.section_title for item in chunks] == ["TANI", "TEDAVİ ENDİKASYONLARI"]
    assert "Spontan ağrı" in chunks[0].text
    assert chunks[1].content_kind == "LIST"


def test_table_like_content_is_marked_for_visual_fallback():
    chunks = chunk_dental_page(
        "SINIFLAMA\nEvre  Klinik bulgu  Radyografik bulgu\nI     Hafif          Koronal üçlü\nII    Orta           Orta üçlü",
        min_chars=20,
    )
    assert chunks[0].content_kind == "TABLE"


def test_long_chunks_are_bounded_with_overlap():
    text = "BULGULAR\n" + "Ağrı bulgusu tekrarlanır. " * 120
    chunks = chunk_dental_page(text, max_chars=500, overlap_chars=50, min_chars=20)
    assert len(chunks) > 2
    assert all(len(item.text) <= 560 for item in chunks)
