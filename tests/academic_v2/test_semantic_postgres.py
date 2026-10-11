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
            page_number int,extraction_method text)'''))
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


def lookup(db, groups=()):
    return _fts_rows(db, owner_user_id=17, course_id=23,
        lexical_query='"hipofiz" OR "tiroid"', query_vector=None,
        embedding_provider='', embedding_model='', limit=20, lexical_groups=groups)


@pytest.mark.parametrize('scope',['topic','course'])
def test_selected_scanned_pages_are_owned_active_and_require_original_visuals(db,monkeypatch,scope):
    from app.academic_request_understanding import StudyRequest
    from app.academic_semantic_retrieval import retrieve_semantic_context
    add(db,1,'hipofiz'); add(db,2,'hipofiz')
    db.exec(text("ALTER TABLE studymaterial ADD COLUMN file_path text DEFAULT 'private/source.pdf', ADD COLUMN mime_type text DEFAULT 'application/pdf'"))
    db.exec(text("INSERT INTO studyindexpage VALUES (17,23,1,'v1',1,'LOCAL_OCR:test'), (17,23,1,'v1',2,'PDF_TEXT'), (17,23,1,'v0',2,'LOCAL_OCR:old'), (99,23,1,'v1',2,'LOCAL_OCR:foreign'), (17,99,1,'v1',2,'LOCAL_OCR:other-course')"))
    if scope=='course':
        import app.academic_semantic_retrieval as current
        monkeypatch.setattr(current,'get_or_build_coverage_plan',lambda *a,**k:None)
        monkeypatch.setattr(current,'_coverage_hydration_ids',lambda *a,**k:[1,2])
    plan=StudyRequest('Hipofiz anlat','answer',scope,None,None,'',('hipofiz',) if scope=='topic' else ())
    result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,query=plan.resolved_query,request_plan=plan)
    assert {(v['material_id'],v['page_number']) for v in result.visual_sources} == {(1,1)}
    assert result.visual_sources[0]['index_version']=='v1'
    assert 'OCR KAYNAK UYARISI' in result.note_context[0]
    assert '\n'.join(result.note_context).count('hipofiz') == 1  # Digital page survives; OCR does not compete.
    assert len(result.evidence) == 2
    assert result.source_coverage_complete == (scope=='course')
    if scope=='course':
        # The original scan covers other chunks on that page, but a partial
        # digital transcription does not cover omitted digital-page chunks.
        add(db,3,'hidden OCR chunk')
        db.exec(text('UPDATE studyindexchunk SET page_start=1,page_end=1 WHERE id=3'))
        result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,query=plan.resolved_query,request_plan=plan)
        assert result.source_coverage_complete
        db.exec(text('UPDATE studyindexchunk SET page_start=2,page_end=2 WHERE id=3'))
        result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,query=plan.resolved_query,request_plan=plan)
        assert not result.source_coverage_complete
        db.exec(text('DELETE FROM studyindexchunk WHERE id=3'))
        # An indexed page with no selected chunk is not magically covered.
        db.exec(text("INSERT INTO studyindexpage VALUES (17,23,1,'v1',3,'EMPTY')"))
        result=retrieve_semantic_context(db,owner_user_id=17,course_id=23,query=plan.resolved_query,request_plan=plan)
        assert not result.source_coverage_complete


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
