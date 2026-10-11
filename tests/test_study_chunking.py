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


def test_slide_heading_paths_continue_until_the_next_group():
    first = chunk_dental_page('A-   Deri Noktaları\n- Tek Noktalar\nPronasale (Prn): Kaynak tanımı.')
    title = first[-1].section_title
    assert title == 'Deri Noktaları > Tek Noktalar'
    following = chunk_dental_page('Stomion (St): Kaynak tanımı.\nN', inherited_section_title=title)
    assert all(c.section_title == title for c in following)
    paired = chunk_dental_page('Çift  Noktalar\nTragion (Tr): Kaynak tanımı.', inherited_section_title=title)
    assert paired[-1].section_title == 'Deri Noktaları > Çift Noktalar'
    bone = chunk_dental_page('B- Kemik Noktaları\nTek Noktalar\nBasion (Ba): Kaynak tanımı.', inherited_section_title=paired[-1].section_title)
    assert bone[-1].section_title == 'Kemik Noktaları > Tek Noktalar'


def test_heading_only_outline_preserves_all_sibling_labels():
    chunks = chunk_dental_page('A- Deri Noktaları\n- Tek Noktalar\n- Çift Noktalar')
    assert [c.section_title for c in chunks] == ['Deri Noktaları', 'Deri Noktaları > Tek Noktalar', 'Deri Noktaları > Çift Noktalar']
