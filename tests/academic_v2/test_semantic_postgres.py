"""Real PostgreSQL regressions; temporary tables never modify published data."""
import os
import pytest
from sqlalchemy import text
from sqlmodel import Session, create_engine
from app.study_retrieval_v2 import _fts_rows


@pytest.fixture
def db():
    url = os.getenv('ACADEMIC_TEST_DATABASE_URL')
    if not url:
        pytest.skip('ACADEMIC_TEST_DATABASE_URL is required for real PostgreSQL checks')
    engine = create_engine(url)
    with Session(engine) as session:
        session.exec(text('''CREATE TEMP TABLE studymaterial (
            id bigint, owner_user_id bigint, active_index_version text,
            index_status text, deleted_at timestamp, display_name text, course_id bigint DEFAULT 23)'''))
        session.exec(text('''CREATE TEMP TABLE studyindexchunk (
            id bigint, material_id bigint, owner_user_id bigint, course_id bigint,
            index_version text, section_title text, text_content text, retrieval_terms text,
            page_start int, page_end int, content_kind text, chunk_index int, semantic_json text)'''))
        session.exec(text('''CREATE TEMP TABLE studyindexpage (
            owner_user_id bigint,course_id bigint,material_id bigint,index_version text,
            page_number int,extraction_method text,
            text_content text,status text DEFAULT 'EXTRACTED')'''))
        session.exec(text("INSERT INTO studymaterial VALUES (1,17,'v1','READY',NULL,'fixture',23)"))
        from app.academic_chunk_links import _CACHE
        _CACHE.clear()
        yield session
        session.rollback()
    engine.dispose()


def add(db, ident, body, *, material=1, owner=17, course=23, version='v1'):
    db.exec(text('''INSERT INTO studyindexchunk VALUES
        (:id,:material,:owner,:course,:version,NULL,:body,'',:id,:id,'TEXT',:id,NULL)'''),
        params=dict(id=ident,material=material,owner=owner,course=course,version=version,body=body))


def test_question_pages_include_text_siblings_and_continuations_without_foreign_or_stale(db):
    from app.study_retrieval_v2 import _question_rows
    for cid,page,body in [(101,3,'14. Çenelerin açma hareketi?'),(102,3,'OCR bozuk şık'),
                          (103,4,'Temporal gevşemesi'),(104,4,'OCR numaraları kaybolan soru'),
                          (105,9,'Başka ders başlığı')]:
        add(db,cid,body)
        db.exec(text('UPDATE studyindexchunk SET page_start=:p,page_end=:p WHERE id=:id'),params={'p':page,'id':cid})
    add(db,201,'FOREIGN',owner=99)
    db.exec(text("UPDATE studyindexchunk SET content_kind='QUESTION' WHERE id=101"))
    add(db,202,'STALE',version='old')
    db.exec(text('UPDATE studyindexchunk SET page_start=3,page_end=3 WHERE id IN (201,202)'))
    selected=_question_rows(db,owner_user_id=17,course_id=23,limit=32)
    assert [r[0] for r in selected]==[101,102,103,104]
    remaining=_question_rows(db,owner_user_id=17,course_id=23,after_cursor=(1,102),limit=32)
    assert [r[0] for r in remaining]==[103,104]
    from app.study_retrieval_v2 import _question_page_context_rows
    expanded=_question_page_context_rows(db,owner_user_id=17,course_id=23,seeds=[selected[0]])
    assert [r[0] for r in expanded]==[101,102,103,104]


def test_complete_batch_reader_crosses_128_without_foreign_stale_or_question_rows(db):
    from app.academic_source_batches import load_owned_source_rows, partition_source_rows
    db.exec(text('''INSERT INTO studyindexchunk
        SELECT n,1,17,23,'v1','Deri Noktaları > Tek Noktalar','definition','',
               n,n,'TEXT',n,NULL FROM generate_series(1,300) AS n'''))
    add(db,301,'foreign',owner=99)
    add(db,302,'other course',course=99)
    add(db,303,'old version',version='v0')
    add(db,304,'question')
    db.exec(text("UPDATE studyindexchunk SET content_kind='QUESTION' WHERE id=304"))
    rows=list(load_owned_source_rows(db,owner_user_id=17,course_id=23))
    batches=partition_source_rows(rows)
    assert [cid for batch in batches for cid in batch.chunk_ids] == list(range(1,301))


def test_broad_gateway_retrieves_complete_sections_instead_of_coverage_sample(db):
    from app.academic_request_understanding import StudyRequest, UnderstandingResult, retrieve_understood_course_context
    db.exec(text('''INSERT INTO studyindexchunk
        SELECT n,1,17,23,'v1','Sefalometrik Noktalar','definition','',
               n,n,'TEXT',n,NULL FROM generate_series(1,300) AS n'''))
    plan=StudyRequest('Tüm ders notlarını özetle','summarize','course',None,None,'')
    result=retrieve_understood_course_context(db,
        understanding=UnderstandingResult(plan=plan,attempted=True,outcome='interpreted'),
        owner_user_id=17,course_id=23,query='Her konuyu özetle',recent_history=[])
    assert result.retrieval_mode=='source_batch'
    assert not result.source_batches  # Short digital text needs one call, not 19 visual-page batches.
    assert [item.chunk_id for item in result.evidence]==list(range(1,301))
    assert result.source_material_ids==[1]
    assert not result.source_coverage_complete  # Search/index coverage is not proof of response accuracy.


def test_definition_fast_path_uses_real_owned_fts_without_planner(db,monkeypatch):
    from app.academic_request_understanding import understand_study_request, retrieve_understood_course_context
    add(db,1,'ANB açısı sagittal ilişkidir')
    add(db,2,'ANB başka kullanıcı',owner=99)
    monkeypatch.setattr('app.study_provider.GeminiStudyProvider',
                        lambda: pytest.fail('A definition must not make a planner call'))
    monkeypatch.setenv('STUDY_ACADEMIC_LOCAL_ROUTING','1')
    understanding=understand_study_request('ANB nedir?',[])
    result=retrieve_understood_course_context(db,understanding=understanding,
        owner_user_id=17,course_id=23,query='ANB nedir?',recent_history=[])
    assert not understanding.attempted
    assert not result.semantic_planner_attempted
    assert [item.chunk_id for item in result.evidence]==[1]


def test_actual_uploaded_note_selects_all_skin_single_definitions_without_paired_points():
    import json
    from pathlib import Path
    from scripts.evaluate_academic_note_flow import temporary_note_database
    from app.academic_request_understanding import StudyRequest, UnderstandingResult, retrieve_understood_course_context
    from app.academic_chunk_links import planner_source_outline
    url=os.getenv('ACADEMIC_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Dedicated PostgreSQL is required')
    fixture=json.loads((Path(__file__).resolve().parents[2]/'evaluation/academic/cephalometric_text_fixture.json').read_text())
    rows=[tuple(row) for row in fixture['rows']]
    documents={int(k):v for k,v in fixture['documents'].items()}
    with temporary_note_database(url,rows,documents) as session:
        outline=planner_source_outline(session,owner_user_id=17,course_id=23,query='deri tek noktalar')
        assert 'deri noktaları > tek noktalar' in outline['sections']
        plan=StudyRequest('Deri tek noktalarının tüm tanımlarını açıkla','explain','topic',None,None,'',('deri tek noktalar',))
        result=retrieve_understood_course_context(session,
            understanding=UnderstandingResult(plan=plan,attempted=True,outcome='source_replay'),
            owner_user_id=17,course_id=23,query=plan.resolved_query,recent_history=[])
        assert {2,3,4,5,6} <= {item.page_start for item in result.evidence}
        import re
        text=re.sub(r'\s+',' ',' '.join(item.text for item in result.evidence)).casefold()
        for name in ['pronasale','sub-nasale','labiale superior','labiale inferior','stomion']:
            assert name in text
        assert 'tragion' not in text and 'chelion' not in text


def lookup(db, groups=()):
    return _fts_rows(db, owner_user_id=17, course_id=23,
        lexical_query='"hipofiz" OR "tiroid"', query_vector=None,
        embedding_provider='', embedding_model='', limit=20, lexical_groups=groups)


@pytest.mark.parametrize('count',[8,16])
def test_every_allowed_planner_search_reaches_real_postgres(db,count):
    from app.academic_request_understanding import MAX_SOURCE_SEARCHES
    assert count <= MAX_SOURCE_SEARCHES
    groups=tuple('"subject'+str(i)+'"' for i in range(count))
    for i in range(count):
        add(db,i+1,'subject'+str(i))
        add(db,100+i,'subject'+str(i),owner=99)
    selected=lookup(db,groups)
    assert {int(row[0]) for row in selected}==set(range(1,count+1))
    with pytest.raises(ValueError,match='invalid lexical search groups'):
        lookup(db,tuple('"subject"' for _ in range(MAX_SOURCE_SEARCHES+1)))


@pytest.mark.parametrize('scope',['topic','course'])
def test_explicit_visual_request_keeps_owned_active_originals(db,monkeypatch,scope):
    from app.academic_request_understanding import StudyRequest
    from app.academic_semantic_retrieval import retrieve_semantic_context
    add(db,1,'hipofiz'); add(db,2,'hipofiz')
    db.exec(text("ALTER TABLE studymaterial ADD COLUMN file_path text DEFAULT 'private/source.pdf', ADD COLUMN mime_type text DEFAULT 'application/pdf'"))
    db.exec(text("INSERT INTO studyindexpage(owner_user_id,course_id,material_id,index_version,page_number,extraction_method) VALUES (17,23,1,'v1',1,'LOCAL_OCR:test'), (17,23,1,'v1',2,'PDF_TEXT'), (17,23,1,'v0',2,'LOCAL_OCR:old'), (99,23,1,'v1',2,'LOCAL_OCR:foreign'), (17,99,1,'v1',2,'LOCAL_OCR:other-course')"))
    if scope=='course':
        import app.academic_semantic_retrieval as current
        monkeypatch.setattr(current,'get_or_build_coverage_plan',lambda *a,**k:None)
        monkeypatch.setattr(current,'_coverage_hydration_ids',lambda *a,**k:[1,2])
    plan=StudyRequest('Hipofiz görselini anlat','answer',scope,None,None,'',('hipofiz',) if scope=='topic' else (),needs_visual=True)
    result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,query=plan.resolved_query,request_plan=plan)
    assert {(v['material_id'],v['page_number']) for v in result.visual_sources} == {(1,1),(1,2)}
    assert result.visual_sources[0]['index_version']=='v1'
    assert 'OCR KAYNAK UYARISI' in result.note_context[0]
    assert '\n'.join(result.note_context).count('hipofiz') == 1  # Digital page survives; OCR does not compete.
    assert len(result.evidence) == 2
    assert result.source_coverage_complete == (scope=='course')
    if scope=='course':
        # Explicit inspection includes both originals and covers other chunks
        # on those pages; an entirely unselected page remains uncovered.
        add(db,3,'hidden OCR chunk')
        db.exec(text('UPDATE studyindexchunk SET page_start=1,page_end=1 WHERE id=3'))
        result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,query=plan.resolved_query,request_plan=plan)
        assert result.source_coverage_complete
        db.exec(text('UPDATE studyindexchunk SET page_start=2,page_end=2 WHERE id=3'))
        result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,query=plan.resolved_query,request_plan=plan)
        assert result.source_coverage_complete
        db.exec(text('DELETE FROM studyindexchunk WHERE id=3'))
        # An indexed page with no selected chunk is not magically covered.
        db.exec(text("INSERT INTO studyindexpage(owner_user_id,course_id,material_id,index_version,page_number,extraction_method) VALUES (17,23,1,'v1',3,'EMPTY')"))
        result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,query=plan.resolved_query,request_plan=plan)
        assert not result.source_coverage_complete


def test_ordinary_ocr_answer_uses_published_text_without_originals(db):
    from app.academic_request_understanding import StudyRequest
    from app.academic_semantic_retrieval import retrieve_semantic_context
    from app.study_retrieval_v2 import materialize_visual_sources
    from unittest.mock import Mock
    add(db,1,'hipofiz OCR metni')
    add(db,2,'hipofiz FOREIGN',owner=99)
    add(db,3,'hipofiz STALE',version='v0')
    db.exec(text("INSERT INTO studyindexpage(owner_user_id,course_id,material_id,index_version,page_number,extraction_method,text_content) VALUES (17,23,1,'v1',1,'LOCAL_OCR:test','hipofiz OCR metni')"))
    plan=StudyRequest('Hipofiz anlat','answer','topic',None,None,'',('hipofiz',))
    result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,
        query=plan.resolved_query,request_plan=plan)
    assert [e.chunk_id for e in result.evidence]==[1]
    assert 'hipofiz OCR metni' in '\n'.join(result.note_context)
    assert not result.visual_sources and not result.attachments
    factory=Mock(side_effect=AssertionError('unexpected original-page I/O'))
    materialize_visual_sources(factory,result)
    factory.assert_not_called()


def test_comparison_keeps_rare_subject_in_bounded_pool(db):
    for ident in range(1,41):
        add(db,ident,'hipofiz hipofiz hipofiz')
    add(db,100,'tiroid')
    assert 100 not in {r[0] for r in lookup(db)}  # Reproduces shared-pool loss.
    rows = lookup(db, ('"hipofiz"','"tiroid"'))
    assert len(rows) <= 20
    assert 100 in {r[0] for r in rows}
    assert any('hipofiz' in r[7] for r in rows)


def test_grouped_lookup_preserves_owner_course_version_and_ready_filters(db):
    add(db,1,'hipofiz'); add(db,2,'tiroid')
    add(db,3,'tiroid',owner=99)
    add(db,4,'tiroid',course=99)
    add(db,5,'tiroid',version='stale')
    db.exec(text("INSERT INTO studymaterial VALUES (2,17,'v1','INDEXING',NULL,'pending',23), (3,17,'v1','READY',now(),'deleted',23)"))
    add(db,6,'tiroid',material=2); add(db,7,'tiroid',material=3)
    assert {r[0] for r in lookup(db, ('"hipofiz"','"tiroid"'))} == {1,2}


def test_overlapping_groups_deduplicate_chunks(db):
    add(db,1,'hipofiz tiroid')
    assert [r[0] for r in lookup(db, ('"hipofiz"','"tiroid"'))] == [1]


def test_partial_phrase_recovers_note_without_discarding_strict_preference(db):
    add(db,1,'hipofiz ekstresi')
    add(db,2,'hipofiz etkisi')
    add(db,3,'etkisi farklıdır',owner=99)
    rows = _fts_rows(db, owner_user_id=17, course_id=23,
        lexical_query='"hipofiz" "etkisi"', query_vector=None,
        embedding_provider='', embedding_model='', limit=20,
        lexical_groups=('"hipofiz" "etkisi"',),
        lexical_fallback_groups=('"hipofiz" OR "etkisi"',))
    assert [r[0] for r in rows] == [2,1]


def test_gemini_only_retrieval_keeps_comparison_and_owned_ready_scope(db):
    from app.academic_semantic_retrieval import retrieve_semantic_context
    from app.academic_request_understanding import StudyRequest
    for ident in range(1,41):
        add(db,ident,'hipofiz')
    add(db,100,'tiroid')
    db.exec(text('UPDATE studyindexchunk SET semantic_json=\'{"nodes":["pituitary"]}\' WHERE id<100'))
    db.exec(text('UPDATE studyindexchunk SET semantic_json=\'{"nodes":["thyroid"]}\' WHERE id=100'))
    add(db,200,'Hipotalamo-hipofizer bölgenin devamı')
    add(db,201,'Bu bezin hormon sentezi')
    db.exec(text('UPDATE studyindexchunk SET semantic_json=\'{"nodes":["pituitary"]}\' WHERE id=200'))
    db.exec(text('UPDATE studyindexchunk SET semantic_json=\'{"nodes":["thyroid"]}\' WHERE id=201'))
    add(db,101,'tiroid',owner=99)
    add(db,102,'tiroid',course=99)
    add(db,103,'tiroid',version='stale')
    db.exec(text("INSERT INTO studymaterial VALUES (2,17,'v1','INDEXING',NULL,'pending',23), (3,17,'v1','READY',now(),'deleted',23)"))
    add(db,104,'tiroid',material=2); add(db,105,'tiroid',material=3)
    plan=StudyRequest('Hipofiz ve tiroidi karşılaştır','compare','topic',None,None,'',('hipofiz','tiroid'))
    result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,query=plan.resolved_query,request_plan=plan)
    ids={item.chunk_id for item in result.evidence}
    assert {100,200,201} <= ids and any(i < 100 for i in ids)
    assert not ids & {101,102,103,104,105}
    assert len(ids) <= 16


def test_topic_links_find_distant_page_without_its_query_words(db):
    import json
    from app.academic_semantic_retrieval import retrieve_semantic_context
    from app.academic_request_understanding import StudyRequest
    add(db,1,'ANB açısının ölçümü')
    db.exec(text('UPDATE studyindexchunk SET semantic_json=:tags WHERE id=1'),
            params={'tags':json.dumps({'nodes':['anb']})})
    db.exec(text('''INSERT INTO studyindexchunk
        SELECT n,1,17,23,'v1',NULL,'Bu ölçümün klinik yorumu','',n,
               n,'TEXT',n,'{"nodes":["anb"]}' FROM generate_series(2,1000) AS n'''))
    # Other user/course/generation and distractors never enter linked evidence.
    for ident, kwargs in [(1001,{'owner':99}), (1002,{'course':99}),
                          (1003,{'version':'old'})]:
        add(db,ident,'Bu ölçümün klinik yorumu',**kwargs)
    db.exec(text('UPDATE studyindexchunk SET semantic_json=\'{"nodes":["anb"]}\' WHERE id>=1001'))
    add(db,1004,'Bağlı sorunun yanlış şıkkı')
    db.exec(text('UPDATE studyindexchunk SET semantic_json=\'{"nodes":["anb"]}\', content_kind=\'QUESTION\' WHERE id=1004'))
    plan=StudyRequest('ANB açısını açıkla','explain','topic',None,None,'',('ANB',))
    result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,
        query=plan.resolved_query,request_plan=plan)
    ids={r.chunk_id for r in result.evidence}
    assert {1,501,1000} <= ids
    assert not ids & {1001,1002,1003,1004}
    assert len(ids) <= 16


def test_published_version_change_invalidates_topic_link_cache(db):
    from app.academic_chunk_links import get_course_links
    add(db,1,'eski'); add(db,2,'yeni',version='v2')
    assert set(get_course_links(db,owner_user_id=17,course_id=23).rows) == {1}
    db.exec(text("UPDATE studymaterial SET active_index_version='v2'"))
    assert set(get_course_links(db,owner_user_id=17,course_id=23).rows) == {2}


def test_named_section_hydrates_fifty_short_pages_without_sibling_or_foreign_data(db):
    from app.academic_semantic_retrieval import _linked_candidates
    from app.study_retrieval_v2 import _coverage_evidence_rows
    for ident in range(1, 51):
        add(db, ident, 'Bu başlığa ait kaynak açıklaması')
    db.exec(text("UPDATE studyindexchunk SET section_title='Deri Noktaları > Tek Noktalar'"))
    add(db, 100, 'Çift grubuna ait kaynak açıklaması')
    db.exec(text("UPDATE studyindexchunk SET section_title='Deri Noktaları > Çift Noktalar' WHERE id=100"))
    add(db, 101, 'Başka kullanıcıya ait açıklama', owner=99)
    db.exec(text("UPDATE studyindexchunk SET section_title='Deri Noktaları > Tek Noktalar' WHERE id=101"))
    seed = _coverage_evidence_rows(db, owner_user_id=17, course_id=23, chunk_ids=[1], limit=1)
    rows = _linked_candidates(db, seed, ('deri tek noktalar',), owner_user_id=17, course_id=23, limit=16)
    assert {int(row[0]) for row in rows} == set(range(1, 51))


def test_anb_focus_follows_distant_mentions_without_sna_only_fragments(db):
    import json
    from app.academic_semantic_retrieval import _linked_candidates
    from app.study_retrieval_v2 import _coverage_evidence_rows
    for ident, body, nodes in (
        (1, 'ANB ile SNA karşılaştırması', ['anb', 'sna']),
        (2, 'ANB açısının bağlı açıklaması', ['anb']),
        (3, 'SNA açısının bağımsız açıklaması', ['sna']),
        (4, 'Genel bölümün farklı açıklaması', []),
    ):
        add(db, ident, body)
        db.exec(text('UPDATE studyindexchunk SET section_title=:heading, semantic_json=:meta WHERE id=:id'),
            params={'id': ident, 'heading': 'Sefalometrik Analiz',
                    'meta': json.dumps({'nodes': nodes})})
    seed = _coverage_evidence_rows(db, owner_user_id=17, course_id=23, chunk_ids=[1], limit=1)
    selected = _linked_candidates(db, seed, ('ANB açısı',), owner_user_id=17, course_id=23, limit=16)
    assert {int(row[0]) for row in selected} == {1, 2}


def test_owned_section_recovery_from_real_fragmented_pdf_prefixes(db):
    import json
    from pathlib import Path
    from app.academic_chunk_links import planner_source_outline
    from app.academic_request_understanding import StudyRequest
    from app.academic_semantic_retrieval import retrieve_semantic_context
    fixture=json.loads(Path('evaluation/academic/cephalometric_legacy_prefixes.json').read_text())
    for cid,body in enumerate(fixture['legacy_prefixes'],1):
        add(db,cid,body)
    db.exec(text("UPDATE studyindexchunk SET section_title='Legacy flat point label' WHERE id BETWEEN 3 AND 6"))
    add(db,10,'PRIVATE',owner=99)
    add(db,11,'OLD',version='v0')
    add(db,12,'OTHER COURSE',course=99)
    heading='deri noktaları > tek noktalar'
    assert heading in planner_source_outline(db,owner_user_id=17,course_id=23)['sections']
    plan=StudyRequest('Deri tek noktalarının hepsini anlat','explain','topic',None,None,'',
                      source_sections=(heading,))
    result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,
                                    query=plan.resolved_query,request_plan=plan)
    assert [e.chunk_id for e in result.evidence]==[1,2,3,4,5,6]


def test_mixed_section_and_lexical_search_does_not_treat_filtered_questions_as_missing_source(db):
    from app.academic_request_understanding import StudyRequest
    from app.academic_semantic_retrieval import retrieve_semantic_context
    add(db,1,'Retrognatik yüz tipinde ANB artar; prognatik yüz tipinde ANB azalır.')
    db.exec(text("UPDATE studyindexchunk SET section_title='Yapısal Değerlendirme' WHERE id=1"))
    add(db,2,'ANB başka not açıklaması.')
    add(db,3,'ANB hangi durumda artar? A) Yanlış seçenek B) Başka seçenek')
    db.exec(text("UPDATE studyindexchunk SET content_kind='QUESTION' WHERE id=3"))
    plan=StudyRequest('İki yüz tipini ANB yönünden karşılaştır','compare','topic',None,None,'',
                      ('yapısal değerlendirme','ANB'))
    result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,query=plan.resolved_query,request_plan=plan)
    assert {e.chunk_id for e in result.evidence}=={1,2}
    assert all(e.content_kind!='QUESTION' for e in result.evidence)


def test_whole_source_question_request_includes_beyond_sixteen_with_ownership_fences(db):
    from app.academic_request_understanding import StudyRequest, UnderstandingResult, retrieve_understood_course_context
    for ident in range(1,76):
        add(db,ident,f'{ident}. Kaynaktaki soruyu aynen aktar. A) Birinci seçenek B) İkinci seçenek')
    add(db,76,'foreign question',owner=99)
    add(db,77,'other course question',course=99)
    add(db,78,'old question',version='v0')
    db.exec(text("UPDATE studyindexchunk SET content_kind='QUESTION'"))
    plan=StudyRequest('Mevcut soruların hepsini aynen düzenle, çözme','answer','course',None,None,'',source_kind='questions')
    result=retrieve_understood_course_context(db,owner_user_id=17,course_id=23,
        query=plan.resolved_query,recent_history=[],
        understanding=UnderstandingResult(plan=plan,attempted=True,outcome='interpreted'))
    assert [e.chunk_id for e in result.evidence]==list(range(1,76))
    assert result.study_task['source_kind']=='questions'
    assert len(result.source_batches)>1


def test_candidate_pool_honors_requested_budget_above_twenty(db):
    for ident in range(1,101):
        add(db,ident,'alpha definition')
    selected=_fts_rows(db,owner_user_id=17,course_id=23,lexical_query='"alpha"',
        query_vector=None,embedding_provider='',embedding_model='',limit=96,content_domain='notes')
    assert len(selected)==96
    assert {row[0] for row in selected}==set(range(1,97))


def test_question_noise_cannot_exhaust_the_factual_candidate_budget(db):
    for ident in range(1,101):
        add(db,ident,'alpha quiz question')
    db.exec(text("UPDATE studyindexchunk SET content_kind='QUESTION'"))
    add(db,101,'alpha factual definition')
    add(db,102,'alpha foreign definition',owner=99)
    selected=_fts_rows(db,owner_user_id=17,course_id=23,lexical_query='"alpha"',
        query_vector=None,embedding_provider='',embedding_model='',limit=20,content_domain='notes')
    assert [row[0] for row in selected]==[101]


def test_topic_question_lookup_includes_legacy_text_question_candidates(db):
    from app.academic_request_understanding import StudyRequest
    from app.academic_semantic_retrieval import retrieve_semantic_context
    add(db,1,'1. Alpha hangi durumda uygulanır? A) Bir B) İki')
    add(db,2,'Alpha kaynak açıklaması')
    plan=StudyRequest('Alpha kaynak sorusunu aktar','answer','topic',None,None,'',
                      ('Alpha',),source_kind='questions')
    result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,
        query=plan.resolved_query,request_plan=plan)
    # The hit still selects the source question; its adjoining page is now
    # included so options/continuations are not discarded as lecture TEXT.
    assert [item.chunk_id for item in result.evidence]==[1,2]


def test_small_course_context_answers_without_literal_query_overlap_or_topk_loss(db,monkeypatch):
    from app.academic_request_understanding import StudyRequest, UnderstandingResult, retrieve_understood_course_context
    import app.academic_semantic_retrieval as module
    for ident in range(1,31):
        add(db,ident,f'Source definition {ident}')
    add(db,31,'foreign',owner=99)
    add(db,32,'other course',course=99)
    add(db,33,'old source',version='v0')
    add(db,34,'unresolved question option')
    db.exec(text("UPDATE studyindexchunk SET content_kind='QUESTION' WHERE id=34"))
    monkeypatch.setattr(module,'_fts_rows',lambda *a,**k:pytest.fail('small context should not depend on literal matching'))
    plan=StudyRequest('Bunların mantığını açıkla','explain','topic',None,None,'',('different phrasing',))
    result=retrieve_understood_course_context(db,owner_user_id=17,course_id=23,
        query=plan.resolved_query,recent_history=[],understanding=UnderstandingResult(plan=plan))
    assert [item.chunk_id for item in result.evidence]==list(range(1,31))
    assert result.retrieval_mode=='bounded_note_context'
    assert result.study_task['scope']=='topic'
    assert not result.source_coverage_complete
    assert all('dosya="fixture"' in context for context in result.note_context)


def vector_columns(db):
    db.exec(text('''ALTER TABLE studyindexchunk ADD COLUMN embedding_array double precision[],
        ADD COLUMN embedding_provider text, ADD COLUMN embedding_model text,
        ADD COLUMN embedding_dimensions integer'''))


def test_dense_path_retrieves_a_paraphrase_without_lexical_overlap(db):
    from app.academic_dense_retrieval import QueryEmbedding
    from app.academic_request_understanding import StudyRequest
    from app.academic_semantic_retrieval import retrieve_semantic_context
    vector_columns(db)
    add(db,1,'A meaning-preserving synonymous source description')
    db.exec(text("UPDATE studyindexchunk SET embedding_array=ARRAY[1.0,0.0],embedding_provider='gemini',embedding_model='fixture',embedding_dimensions=2"))
    plan=StudyRequest('Explain alpha','explain','topic',None,None,'',('alpha',))
    result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,query=plan.resolved_query,
        request_plan=plan,query_embedding=QueryEmbedding('gemini','fixture',(1.0,0.0)))
    assert [item.chunk_id for item in result.evidence]==[1]
    assert result.used_semantic_search and result.retrieval_mode=='hybrid_candidates'
    assert result.evidence[0].semantic_rank==1 and result.evidence[0].lexical_rank is None


def test_partial_or_wrong_model_vector_index_is_not_used_for_semantic_answers(db):
    vector_columns(db)
    add(db,1,'synonymous source')
    add(db,2,'another source without vector')
    db.exec(text("UPDATE studyindexchunk SET embedding_array=ARRAY[1.0,0.0],embedding_provider='gemini',embedding_model='fixture',embedding_dimensions=2 WHERE id=1"))
    kwargs=dict(owner_user_id=17,course_id=23,lexical_query='"absent_term"',
                query_vector=[1.0,0.0],embedding_provider='gemini',embedding_model='fixture',limit=16)
    assert _fts_rows(db,**kwargs)==[]
    db.exec(text("UPDATE studyindexchunk SET embedding_array=ARRAY[1.0,0.0],embedding_provider='gemini',embedding_model='different',embedding_dimensions=2 WHERE id=2"))
    assert _fts_rows(db,**kwargs)==[]
    db.exec(text("UPDATE studyindexchunk SET embedding_model='fixture' WHERE id=2"))
    assert {row[0] for row in _fts_rows(db,**kwargs)}=={1,2}


def test_dense_candidates_preserve_owner_course_and_published_version_fences(db):
    vector_columns(db)
    add(db,1,'source')
    add(db,2,'foreign',owner=99)
    add(db,3,'other course',course=99)
    add(db,4,'stale',version='v0')
    db.exec(text("UPDATE studyindexchunk SET embedding_array=ARRAY[1.0,0.0],embedding_provider='gemini',embedding_model='fixture',embedding_dimensions=2"))
    selected=_fts_rows(db,owner_user_id=17,course_id=23,lexical_query='"absent_term"',
        query_vector=[1.0,0.0],embedding_provider='gemini',embedding_model='fixture',limit=96)
    assert [row[0] for row in selected]==[1]


def test_batched_visual_page_read_preserves_owner_version_and_byte_budget(db,monkeypatch):
    from contextlib import contextmanager
    import app.study_retrieval_v2 as retrieval
    db.exec(text("ALTER TABLE studymaterial ADD COLUMN file_path text, ADD COLUMN mime_type text"))
    db.exec(text("ALTER TABLE studyindexpage ADD COLUMN visual_pdf_bytes bytea"))
    db.exec(text("UPDATE studymaterial SET file_path='/synthetic/source.pdf',mime_type='application/pdf'"))
    db.exec(text("INSERT INTO studyindexpage(owner_user_id,course_id,material_id,index_version,page_number,visual_pdf_bytes) SELECT 17,23,1,'v1',p,:data FROM generate_series(1,16) p"),params={'data':b'%PDF-12345'})
    sources=[dict(owner_user_id=17,material_id=1,index_version='v1',reference='ref',page_number=p,
        mime_type='application/pdf',display_name='fixture') for p in range(1,17)]
    @contextmanager
    def factory():yield db
    monkeypatch.setattr(retrieval,'_VISUAL_REQUEST_MAX_BYTES',25)
    with retrieval._PAGE_PDF_CACHE_LOCK:retrieval._PAGE_PDF_CACHE.clear()
    try:
        result=retrieval.RetrievalResult(visual_sources=sources,evidence_sufficient=True,source_coverage_complete=True)
        retrieval.materialize_visual_sources(factory,result)
        assert [item['page_number'] for item in result.attachments]==[1,2]
        assert not result.source_coverage_complete
        for changed in [dict(sources[0],owner_user_id=18),dict(sources[0],index_version='obsolete')]:
            result=retrieval.RetrievalResult(visual_sources=[changed],evidence_sufficient=True)
            retrieval.materialize_visual_sources(factory,result)
            assert not result.attachments
    finally:
        with retrieval._PAGE_PDF_CACHE_LOCK:retrieval._PAGE_PDF_CACHE.clear()
