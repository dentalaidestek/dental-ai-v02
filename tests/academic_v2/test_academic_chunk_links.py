import json
from app.academic_chunk_links import build_course_links, source_nodes


def row(cid, *, nodes=(), material=1, section=None, kind='TEXT', page=None):
    return (cid, material, 'source', page or cid, page or cid, section, kind,
            'source text', None, None, None, None, 1, cid, json.dumps({'nodes':nodes}))


def test_links_cover_1000_pages_without_first_page_bias():
    rows=[row(i,nodes=['anb']) for i in range(1,1001)]
    index=build_course_links([rows[:400], rows[400:800], rows[800:]])
    ids=index.related_ids([rows[0]],16)
    assert {2,501,1000} <= set(ids)
    assert 1 not in ids and len(ids) == 16


def test_same_concept_links_across_files_but_not_question_options():
    seed=row(1,nodes=['anb'])
    index=build_course_links([[seed,row(2,nodes=['anb'],material=2),
        row(3,nodes=['sna']),row(4,nodes=['anb'],kind='QUESTION')]])
    assert index.related_ids([seed],16) == [2]


def test_heading_continuity_stays_document_scoped_and_does_not_override_concepts():
    seed=row(1,nodes=['anb'],section='Sefalometrik Analiz')
    index=build_course_links([[seed,row(2,section='Sefalometrik Analiz'),
        row(3,nodes=['sna'],section='Sefalometrik Analiz'),
        row(4,section='Sefalometrik Analiz',material=2)]])
    assert index.related_ids([seed],16) == [2]


def test_unknown_concept_can_follow_its_actual_heading():
    seed=row(1,section='Kaynağın özgün başlığı')
    index=build_course_links([[seed,row(990,section=seed[5])]])
    assert index.related_ids([seed],16) == [990]


def test_explicit_heading_request_keeps_different_points_in_its_section():
    seed = row(1, nodes=['pronasale'], section='Deri Tek Noktalar')
    index = build_course_links([[seed,
        row(2, nodes=['labiale'], section=seed[5]),
        row(3, nodes=['pogonion'], section=seed[5]),
        row(4, nodes=['sella'], section='Kemik Tek Noktalar'),
        row(5, nodes=['labiale'], section=seed[5], material=2),
        row(6, nodes=['pronasale'], section='Başka bir bölüm')]])
    assert index.related_ids([seed], 16, section_queries=('Deri Tek Noktalar anlat',)) == [2, 3]
    assert index.related_ids([seed], 16, section_queries=('pronasale',)) == [6]
    assert index.related_ids([seed], 16, section_queries=('tek noktalar',)) == [6]


def test_malformed_metadata_never_creates_a_link_or_crashes():
    seed=row(1,nodes=['anb'])
    for value in ['not json','[]','{"nodes":"anb"}','{"nodes":[null,{},7]}']:
        bad=(*row(2)[:14],value)
        assert source_nodes(bad) == ()
        assert build_course_links([[seed,bad]]).related_ids([seed],16) == []


def test_source_focus_does_not_expand_every_concept_on_a_mixed_page():
    seed = row(1, nodes=['anb', 'sna'], section='Sefalometrik Analiz')
    links = build_course_links([[seed,
        row(2, nodes=['anb'], section='ANB Tanımı', material=2),
        row(3, nodes=['sna'], section=seed[5]),
        row(4, section=seed[5]),
        row(5, section='ANB Tanımı', material=2)]])
    focus = links.focus_nodes('ANB açısı')
    assert focus == {'anb'}
    assert links.related_ids([seed], 16, focus_nodes=focus) == [2]
    definition = row(2, nodes=['anb'], section='ANB Tanımı', material=2)
    assert 5 in links.related_ids([definition], 16, focus_nodes=focus)


def test_heading_path_selects_children_without_crossing_sibling_groups():
    seed = row(1, nodes=['pronasale'], section='Deri Noktaları > Tek Noktalar')
    single = row(2, nodes=['stomion'], section=seed[5])
    paired = row(3, nodes=['tragion'], section='Deri Noktaları > Çift Noktalar')
    bone = row(4, nodes=['basion'], section='Kemik Noktaları > Tek Noktalar')
    links = build_course_links([[seed, single, paired, bone]])
    assert links.related_ids([seed], 16, section_queries=('deri tek noktalar',)) == [2]
    assert set(links.related_ids([seed], 16, section_queries=('deri noktaları',))) == {2, 3}


def test_named_section_selection_uses_text_budget_instead_of_sixteen_chunks(monkeypatch):
    import app.academic_semantic_retrieval as retrieval
    def run(text_size):
        rows = [(*row(i, section='Deri Noktaları > Tek Noktalar')[:7],
                 'deri tek noktalar ' + 'x' * text_size, *row(i)[8:]) for i in range(1, 51)]
        monkeypatch.setattr(retrieval, 'get_course_links', lambda *a, **k: build_course_links([rows]))
        def hydrate(*a, chunk_ids, limit, max_rows, **k):
            assert limit <= max_rows <= 128
            return [r for cid in chunk_ids for r in rows if r[0] == cid][:limit]
        monkeypatch.setattr(retrieval, '_coverage_evidence_rows', hydrate)
        return retrieval._linked_candidates(None, rows[:1], ('deri tek noktalar',),
                                            owner_user_id=17, course_id=23, limit=16)
    assert len(run(200)) == 50
    large = run(5000)
    assert len(large) == 50  # Request-size budgets now split downstream, never discard source rows.


def test_named_section_ignores_outer_document_title_without_losing_parent_qualifier():
    skin=row(1,section='Sefalometrik Noktalar > Deri Noktaları > Tek Noktalar')
    skin2=row(2,section=skin[5])
    bone=row(3,section='Sefalometrik Noktalar > Kemik Noktaları > Tek Noktalar')
    paired=row(4,section='Sefalometrik Noktalar > Deri Noktaları > Çift Noktalar')
    links=build_course_links([[skin,skin2,bone,paired]])
    assert links.named_section_ids('deri tek noktalar')==[1,2]


def test_full_named_section_is_hydrated_in_pages_beyond_128(monkeypatch):
    import app.academic_semantic_retrieval as retrieval
    rows=[row(i,section='Deri Noktaları > Tek Noktalar') for i in range(1,301)]
    monkeypatch.setattr(retrieval,'get_course_links',lambda *a,**k:build_course_links([rows]))
    calls=[]
    def hydrate(*a,chunk_ids,limit,max_rows,**kw):
        calls.append(len(chunk_ids))
        assert limit==len(chunk_ids) and max_rows==128
        return [r for cid in chunk_ids for r in rows if r[0]==cid]
    monkeypatch.setattr(retrieval,'_coverage_evidence_rows',hydrate)
    result=retrieval._linked_candidates(None,rows[:1],('deri tek noktalar',),owner_user_id=17,course_id=23,limit=16)
    assert {r[0] for r in result}==set(range(1,301))
    assert calls==[128,128,44]


def test_named_section_does_not_require_a_lexical_seed(monkeypatch):
    import app.academic_semantic_retrieval as retrieval
    rows=[row(i,section='Deri Noktaları > Tek Noktalar') for i in range(1,6)]
    links=build_course_links([rows])
    monkeypatch.setattr(retrieval,'get_course_links',lambda *a,**k:links)
    monkeypatch.setattr(retrieval,'_coverage_evidence_rows',lambda *a,chunk_ids,**k:[r for r in rows if r[0] in chunk_ids])
    selected=retrieval._linked_candidates(None,[],('deri tek noktalar',),owner_user_id=17,course_id=23,limit=16)
    assert {r[0] for r in selected}=={1,2,3,4,5}
    diagnostics=links.lookup_diagnostics('deri tek noktalar')
    assert diagnostics['nested']==1 and diagnostics['missing_terms']==0
    assert 'deri' not in str(diagnostics)


def test_fragmented_source_headers_restore_missing_page_inheritance_and_siblings():
    def prefix(cid,body,material=1,section=None):
        r=row(cid,material=material,section=section)
        return (*r[:7],body,*r[8:])
    rows=[prefix(1,'SEFALOMETRİK NOKTALAR\nA\n-\nDeri Noktaları\n-\nTek Noktalar'),
          prefix(2,'Pronasale (Prn): Kaynaktaki tanım.'),
          prefix(3,'Sub\n-\nnasale (Sn): Kaynaktaki tanım.',section='Sub-nasale'),
          prefix(4,'Labiale superior (Ls): Kaynaktaki tanım.',section='Labiale superior'),
          prefix(5,'Labiale inferior (Li): Kaynaktaki tanım.',section='Labiale inferior'),
          prefix(6,'Stomion (St): Kaynaktaki tanım.',section='Stomion'),
          prefix(7,'Çift Noktalar\nTragion (Tr): Başka grup.'),
          prefix(8,'Chelion (Ch): Başka grup.'),
          prefix(9,'B\n-\nKemik Noktaları\n-\nTek Noktalar\nSella (S): Başka grup.'),
          prefix(10,'Belgesiz başlangıç.',material=2)]
    links=build_course_links([rows[5:],rows[:5]],repair_headings=True)
    assert links.selected_section_ids(['deri noktaları > tek noktalar'])==[1,2,3,4,5,6]
    assert links.selected_section_ids(['deri noktaları > çift noktalar'])==[7,8]
    assert links.selected_section_ids(['kemik noktaları > tek noktalar'])==[9]
    assert links.rows[10][1]==''


def test_explicit_owned_section_keeps_all_children_without_lexical_queries(monkeypatch):
    import app.academic_semantic_retrieval as retrieval
    rows=[row(i,section='Deri Noktaları > Tek Noktalar') for i in range(1,7)]
    rows.append(row(7,section='Deri Noktaları > Çift Noktalar'))
    monkeypatch.setattr(retrieval,'get_course_links',lambda *a,**k:build_course_links([rows]))
    monkeypatch.setattr(retrieval,'_coverage_evidence_rows',lambda *a,chunk_ids,**k:[r for r in rows if r[0] in chunk_ids])
    selected=retrieval._linked_candidates(None,[],(),owner_user_id=17,course_id=23,limit=16,
        source_sections=('deri noktaları > tek noktalar',))
    assert {r[0] for r in selected}==set(range(1,7))
    assert not build_course_links([rows]).selected_section_ids(['invented heading'])


def test_selected_section_and_unmatched_comparison_subject_both_survive(monkeypatch):
    import app.academic_semantic_retrieval as retrieval
    rows=[row(i,section='Deri Noktaları > Tek Noktalar') for i in range(1,7)]
    other=row(7,section='Başka Konu')
    other=(*other[:7],'ANB tanımı',*other[8:])
    rows.append(other)
    monkeypatch.setattr(retrieval,'get_course_links',lambda *a,**k:build_course_links([rows]))
    monkeypatch.setattr(retrieval,'_coverage_evidence_rows',lambda *a,chunk_ids,**k:[r for r in rows if r[0] in chunk_ids])
    selected=retrieval._linked_candidates(None,[other],('ANB',),owner_user_id=17,course_id=23,limit=16,
        source_sections=('deri noktaları > tek noktalar',))
    assert {r[0] for r in selected}==set(range(1,8))


def test_actual_pdf_fragmented_prefixes_include_every_definition_and_exclude_siblings():
    import json
    from pathlib import Path
    fixture=json.loads(Path('evaluation/academic/cephalometric_legacy_prefixes.json').read_text())
    rows=[]
    for cid,body in enumerate(fixture['legacy_prefixes'],1):
        r=row(cid,section=None)
        rows.append((*r[:7],body,*r[8:]))
    links=build_course_links([rows],repair_headings=True)
    assert links.selected_section_ids(['deri noktaları > tek noktalar'])==[1,2,3,4,5,6]
    assert links.selected_section_ids(['deri noktaları > çift noktalar'])==[1,7,8]


def test_section_hydration_uses_the_same_question_filter_as_lexical_candidates(monkeypatch):
    import app.academic_semantic_retrieval as retrieval
    rows=[row(1,section='Yapısal Değerlendirme'),row(2),row(3,kind='QUESTION')]
    rows=[(*r[:7],'ANB bilgisi',*r[8:]) for r in rows]
    monkeypatch.setattr(retrieval,'get_course_links',lambda *a,**k:build_course_links([rows]))
    monkeypatch.setattr(retrieval,'_coverage_evidence_rows',lambda *a,chunk_ids,**k:
        [r for r in rows if r[0] in chunk_ids and r[6]!='QUESTION'])
    selected=retrieval._linked_candidates(None,rows,('yapısal değerlendirme','ANB'),
        owner_user_id=17,course_id=23,limit=16)
    assert {r[0] for r in selected}=={1,2}


def test_real_missing_section_row_still_fails_closed(monkeypatch):
    import pytest
    import app.academic_semantic_retrieval as retrieval
    rows=[row(1,section='Yapısal Değerlendirme')]
    monkeypatch.setattr(retrieval,'get_course_links',lambda *a,**k:build_course_links([rows]))
    monkeypatch.setattr(retrieval,'_coverage_evidence_rows',lambda *a,**k:[])
    with pytest.raises(ValueError,match='source generation changed'):
        retrieval._linked_candidates(None,rows,('yapısal değerlendirme',),owner_user_id=17,course_id=23,limit=16)


def test_literal_new_parent_overrides_a_stale_inherited_stored_path():
    stale='Kemik Noktaları > Tek Noktalar'
    def source(cid,body):
        r=row(cid,section=stale)
        return (*r[:7],body,*r[8:])
    rows=[source(1,'B - Kemik Noktaları\nTek Noktalar\nBasion (Ba): Tanım.'),
          source(2,'Bolton (Bo): Tanım.'),
          source(3,'C - Deri-Kemik Noktaları\nTek Noktalar\nVertex (V): Tanım.'),
          source(4,'Trichion (Tri): Tanım.')]
    links=build_course_links([rows],repair_headings=True)
    assert links.named_section_ids('kemik tek noktalar')==[1,2]
    assert links.named_section_ids('deri-kemik tek noktalar')==[3,4]
