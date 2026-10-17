"""Real source snapshots + SQL retrieval; plans are supplied, not model scores."""
import json
import os
from pathlib import Path
import pytest


# Expected physical pages and exclusions were read from the source snapshot.
CASES = [
    ('Pronasale nedir?',('pronasale',),{2},()),
    ('Sub-nasale tanımını açıkla',('sub-nasale',),{3},()),
    ('Labiale superior ve inferior farkını tabloya koy',('labiale superior','labiale inferior'),{4,5},('molare',)),
    ('Stomion nerede?',('stomion',),{6},()),
    ('Tragion nedir?',('tragion',),{7},()),
    ('Chelion nedir?',('chelion',),{8},()),
    ('Sella nedir?',('sella',),{40},()),
    ('Gonion nasıl bulunur?',('gonion',),{33},()),
    ('Orbitale tanımını yaz',('orbitale',),{34},()),
    ('Porion tanımı',('porion',),{18},()),
    ('Nasion nedir?',('nasion',),{27},()),
    ('Pogonion nedir?',('pogonion',),{30},()),
    ('Deri tek noktalarının tamamını açıkla',('deri tek noktalar',),{2,3,4,5,6},('tragion','chelion')),
    ('Kemik tek noktalarının tamamını açıkla',('kemik tek noktalar',),{9,10,11,12,13,14,15},('zygion','chelion')),
    ('Deri çift noktalarını açıkla',('deri çift noktalar',),{7,8},('pronasale','stomion')),
    ('Frankfurt ve palatal düzlemi karşılaştır',('frankfurt düzlemi','palatal düzlem'),{46,47},()),
    ('Ön ve arka yüz yüksekliğini karşılaştır',('ön yüz yüksekliği','arka yüz yüksekliği'),{58,59},()),
    ('Gonion ile Menton farkını tabloya koy',('gonion','menton'),{32,33},()),
    ('Yalnız 33. sayfadaki tanımı aktar',(),{33},('orbitale',)),
    ('İmplant robotlarının yazılımını açıkla',('implantrobotuyazılımı',),set(),()),
]


def test_twenty_source_matching_cases():
    url=os.getenv('ACADEMIC_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Dedicated PostgreSQL-compatible test database required')
    from scripts.evaluate_academic_note_flow import temporary_note_database
    from app.academic_request_understanding import StudyRequest,UnderstandingResult,retrieve_understood_course_context
    from app.academic_chunk_links import _CACHE
    fixture=json.loads((Path(__file__).resolve().parents[2]/'evaluation/academic/cephalometric_text_fixture.json').read_text())
    rows=[tuple(row) for row in fixture['rows']]
    documents={int(k):v for k,v in fixture['documents'].items()}
    reports=[]
    with temporary_note_database(url,rows,documents) as db:
        _CACHE.clear()
        for index,(question,searches,expected,excluded) in enumerate(CASES,1):
            plan=StudyRequest(question,'compare' if len(searches)>1 else 'answer','topic',None,None,'',searches,
                source_subjects=searches,complete_sections=index in {13,14,15},
                source_pages=(33,) if index==19 else (),output_format='table' if index in {3,18} else 'text')
            result=retrieve_understood_course_context(db,
                understanding=UnderstandingResult(plan=plan,attempted=True,outcome='supplied_plan'),
                owner_user_id=17,course_id=23,query=question,recent_history=[])
            children=result.source_batches or [result]
            pages={e.page_start for child in children for e in child.evidence}
            body='\n'.join(c for child in children for c in child.note_context).casefold()
            missing=expected-pages
            forbidden=[term for term in excluded if term in body]
            assert not missing,(question,'missing pages',missing,sorted(pages))
            assert not forbidden,(question,'excluded subject leaked',forbidden)
            assert not any(child.visual_sources or child.attachments for child in children)
            if not expected:
                assert not result.evidence_sufficient and not pages
            reports.append({'question':question,'expected_pages':sorted(expected),'selected_pages':sorted(pages),
                'excluded_terms':list(excluded),'chunks':len(result.evidence),'original_pages':0,'passed':True})
    if os.getenv('ACADEMIC_MATCHING_REPORT'):
        Path(os.environ['ACADEMIC_MATCHING_REPORT']).write_text(json.dumps({
            'mode':'supplied_plan_real_source_sql','cases':reports,'live_model_calls':0},ensure_ascii=False,indent=2))
