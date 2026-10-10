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


def test_malformed_metadata_never_creates_a_link_or_crashes():
    seed=row(1,nodes=['anb'])
    for value in ['not json','[]','{"nodes":"anb"}','{"nodes":[null,{},7]}']:
        bad=(*row(2)[:14],value)
        assert source_nodes(bad) == ()
        assert build_course_links([[seed,bad]]).related_ids([seed],16) == []
