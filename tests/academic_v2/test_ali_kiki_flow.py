"""Actual source text, hand-authored plans, real PostgreSQL and production gates."""
import json
import os
from pathlib import Path
import pytest
from scripts.evaluate_academic_note_flow import temporary_note_database, evaluate, CASES
from app.academic_request_understanding import StudyRequest
from app.study_retrieval_v2 import retrieve_course_context_v2


@pytest.fixture
def note_db():
    url = os.getenv('ACADEMIC_TEST_DATABASE_URL')
    if not url:
        pytest.skip('requires real PostgreSQL')
    path=Path(__file__).resolve().parents[2]/'evaluation/academic/ali_kiki_text_fixture.json'
    fixture=json.loads(path.read_text())
    rows=[tuple(row) for row in fixture['rows']]
    documents={int(k):v for k,v in fixture['documents'].items()}
    with temporary_note_database(url,rows,documents) as db:
        yield db,rows,documents


def test_real_source_eight_contract_flows(note_db):
    db,rows,documents=note_db
    reports=evaluate(db,rows,documents,CASES,False,False)
    assert all(item['passed'] for item in reports), reports


def test_model_style_phrase_recovers_actual_hipofiz_page(note_db):
    db,_,_=note_db
    plan=StudyRequest('Hipofiz etkisini açıkla','explain','topic',None,None,'',('hipofiz etkisi',))
    out=retrieve_course_context_v2(db,owner_user_id=17,course_id=23,
        query='Hipofiz etkisi ne?',request_plan=plan)
    assert 64 in {item.page_start for item in out.evidence}
    assert out.evidence_sufficient


def test_partial_lexical_hit_cannot_authorize_missing_comparison(note_db):
    db,_,_=note_db
    plan=StudyRequest('Pulpitis ve apikal periodontitis tedavilerini karşılaştır','compare','topic',
        None,None,'',('pulpitis tedavisi','apikal periodontitis tedavisi'))
    out=retrieve_course_context_v2(db,owner_user_id=17,course_id=23,
        query=plan.resolved_query,request_plan=plan)
    assert not out.evidence_sufficient
