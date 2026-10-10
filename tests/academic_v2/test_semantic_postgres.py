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
            index_status text, deleted_at timestamp, display_name text)'''))
        session.exec(text('''CREATE TEMP TABLE studyindexchunk (
            id bigint, material_id bigint, owner_user_id bigint, course_id bigint,
            index_version text, section_title text, text_content text, retrieval_terms text,
            page_start int, page_end int, content_kind text, chunk_index int, semantic_json text)'''))
        session.exec(text("INSERT INTO studymaterial VALUES (1,17,'v1','READY',NULL,'fixture')"))
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
    db.exec(text("INSERT INTO studymaterial VALUES (2,17,'v1','INDEXING',NULL,'pending'), (3,17,'v1','READY',now(),'deleted')"))
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
