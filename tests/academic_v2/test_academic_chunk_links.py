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
    assert len(large) < 50
    assert sum(len(r[7]) + len(r[5]) + 160 for r in large) <= 96000
