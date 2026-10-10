"""Bounded note-flow evaluation: explicit replay or real Gemini + PostgreSQL.

Replay uses hand-authored contracts and a token matcher, NOT model accuracy or
PostgreSQL recall. Live mode uses temporary tables on a dedicated test database;
it never enables the planner in production or writes published note data.
"""
import argparse
from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import sys
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pypdf import PdfReader
from app.academic_request_understanding import StudyRequest, understand_study_request
from app.study_chunking import chunk_dental_page
from app.dental_semantics import analyze_dental_text, retrieval_enrichment_text
from app.study_retrieval_v2 import retrieve_course_context_v2
from app.study_ai_v2 import _prompt, ask_rag_v2


# Topics and page ranges were checked in the actual Ali Kiki PDF bytes. Page
# ranges are physical PDF pages, not slide numbers or extracted Library pages.
CASES = [
    ('Hipofiz etkisini açıkla', ('hipofiz',), (64,), 'explain', None),
    ('Tiroid etkisini açıkla', ('tiroid',), (66,), 'explain', None),
    ('Hipofiz ile tiroid etkisini karşılaştır', ('hipofiz','tiroid'), (64,66), 'compare', None),
    ('Prenatal hayatın safhalarını özetle', ('prenatal',), (101,), 'summarize', None),
    ('Organogenez safhasını anlat', ('organogenez',), (105,107), 'explain', None),
    ('Hipofiz etkisinden 5 zor soru hazırla', ('hipofiz',), (64,), 'generate_questions', 5),
    ('Bunu daha basit açıkla', ('tiroid',), (66,), 'explain', None),
    ('İkincisini açıkla', (), (), 'clarify', None),
]


def note_rows(source):
    rows, documents = [], {}
    title = None
    reader = PdfReader(source)
    empty_pages = []
    for page, item in enumerate(reader.pages, 1):
        text = item.extract_text() or ''
        if not text.strip():
            empty_pages.append(page)
        chunks = chunk_dental_page(text, inherited_section_title=title)
        for local, chunk in enumerate(chunks):
            if chunk.section_title:
                title = chunk.section_title
            source_text = f'{chunk.section_title or ""}\n{chunk.text}'
            features = analyze_dental_text(source_text)
            metadata = json.dumps(dict(nodes=features.node_ids, specialties=features.specialties,
                kinds=features.kinds, measurements=features.measurements, teeth=features.tooth_numbers,
                imaging=features.imaging_types, negated_nodes=features.negated_node_ids))
            ident = len(rows) + 1
            rows.append((ident,1,Path(source).name,page,page,chunk.section_title,chunk.content_kind,
                         chunk.text,ident,0.2,None,None,1/(60+ident),(page-1)*1000+local,metadata))
            documents[ident] = source_text + ' ' + retrieval_enrichment_text(source_text, features=features)
    return rows, documents, len(reader.pages), empty_pages


@contextmanager
def temporary_note_database(url, rows, documents):
    from sqlalchemy import text
    from sqlmodel import Session, create_engine
    engine = create_engine(url)
    if engine.dialect.name != 'postgresql':
        raise ValueError('a dedicated PostgreSQL test database is required')
    with Session(engine) as db:
        db.exec(text('''CREATE TEMP TABLE studymaterial (id bigint, owner_user_id bigint,
            active_index_version text,index_status text,deleted_at timestamp,display_name text)'''))
        db.exec(text('''CREATE TEMP TABLE studyindexchunk (id bigint, material_id bigint,
            owner_user_id bigint,course_id bigint,index_version text,section_title text,
            text_content text,retrieval_terms text,page_start int,page_end int,
            content_kind text,chunk_index int,semantic_json text)'''))
        db.exec(text("INSERT INTO studymaterial VALUES (1,17,'fixture','READY',NULL,:name)"),
                params={'name':rows[0][2] if rows else 'empty'})
        for row in rows:
            db.exec(text('''INSERT INTO studyindexchunk VALUES
                (:id,1,17,23,'fixture',:title,:body,:terms,:page,:page,:kind,:idx,:metadata)'''),
                params=dict(id=row[0],title=row[5],body=row[7],terms=documents[row[0]],
                            page=row[3],kind=row[6],idx=row[13],metadata=row[14]))
        try:
            yield db
        finally:
            db.rollback()
    engine.dispose()


def replay_lookup(rows, documents, **kwargs):
    # A simple-token approximation cannot reproduce PostgreSQL phrase parsing
    # or ts_rank. Keep that limitation visible in every resulting report.
    groups = kwargs.get('lexical_groups') or tuple(kwargs['lexical_query'].split(' OR '))
    picked = {}
    for group in groups:
        tokens = set(re.findall(r'[^\W_]+', group.lower()))
        matches = [r for r in rows if tokens <= set(re.findall(r'[^\W_]+', documents[r[0]].lower()))]
        for rank, row in enumerate(matches[:120//max(1,len(groups))],1):
            candidate = (*row[:8],rank,0.2,*row[10:12],1/(60+rank),*row[13:])
            if row[0] not in picked or picked[row[0]][8] > rank:
                picked[row[0]] = candidate
    return sorted(picked.values(),key=lambda r:(r[8],r[3],r[0]))[:min(kwargs['limit'],20)]


def evaluate(db, rows, documents, cases, live, answers):
    reports = []
    for index,(question, searches, expected, operation, count) in enumerate(cases,1):
        history = [{'role':'user','content':'Tiroid etkisini anlat'}] if index == 7 else []
        if live:
            with patch.dict(os.environ, {'STUDY_ACADEMIC_SEMANTIC_PLANNER':'1'}):
                understanding = understand_study_request(question, history)
            plan = understanding.plan
        else:
            understanding = None
            plan = StudyRequest('Tiroid etkisini basit açıkla' if index == 7 else question,
                operation,'topic',count,'zor' if count else None,
                'Hangi ikinci konuyu kastediyorsun?' if operation == 'clarify' else '',searches)
        if plan is None:
            reports.append(dict(case=index,passed=False,outcome=understanding.outcome))
            continue
        retrieval = retrieve_course_context_v2(db,owner_user_id=17,course_id=23,
            query=question,recent_history=history,request_plan=plan)
        pages = sorted({e.page_start for e in retrieval.evidence})
        recall = all(p in pages for p in expected)
        contract = plan.operation == operation and plan.count == count
        sufficient = bool(retrieval.clarification) if operation == 'clarify' else retrieval.evidence_sufficient
        answer = ask_rag_v2('Ali Kiki Ortodonti',question,history,retrieval) if answers else None
        reports.append(dict(case=index,passed=bool(recall and contract and sufficient),
            planner_origin='real_gemini' if live else 'hand_authored_replay',
            plan=asdict(plan),expected_pages=expected,selected_pages=pages,
            evidence_sufficient=retrieval.evidence_sufficient,missing_facets=retrieval.missing_facets,
            answer=answer,answer_prompt_built=bool(_prompt('Ali Kiki Ortodonti',question,retrieval,history)),
            answer_requires_semantic_review=bool(answer)))
    return reports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-pdf',required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--run',action='store_true')
    mode.add_argument('--replay',action='store_true')
    parser.add_argument('--answers',action='store_true',help='Spend the final answer call too; requires --run')
    parser.add_argument('--limit',type=int,default=8)
    args = parser.parse_args()
    if args.answers and not args.run:
        parser.error('--answers requires --run')
    if args.run and (not os.getenv('GEMINI_API_KEY') or not os.getenv('ACADEMIC_TEST_DATABASE_URL')):
        parser.exit(2,'GEMINI_API_KEY and a dedicated ACADEMIC_TEST_DATABASE_URL are required; no calls made.\n')
    rows, documents, pages, empty = note_rows(args.source_pdf)
    output = dict(source_name=Path(args.source_pdf).name,physical_pdf_pages=pages,
        chunks=len(rows),pages_without_extracted_text=empty,
        production_ocr_or_margin_cleanup_reproduced=False,
        backend='postgresql' if args.run else 'token_replay_not_postgresql',
        real_gemini=args.run,final_answer_calls_enabled=args.answers)
    cases = CASES[:max(1,min(8,args.limit))]
    if args.run:
        with temporary_note_database(os.environ['ACADEMIC_TEST_DATABASE_URL'],rows,documents) as db:
            output['cases'] = evaluate(db,rows,documents,cases,True,args.answers)
    elif args.replay:
        db = Mock(); db.get_bind.return_value.dialect.name = 'postgresql'
        with patch('app.study_retrieval_v2._fts_rows',side_effect=lambda session,**kw:replay_lookup(rows,documents,**kw)), \
             patch('app.study_retrieval_v2._neighbor_rows',return_value=[]):
            output['cases'] = evaluate(db,rows,documents,cases,False,False)
    print(json.dumps(output,ensure_ascii=False,indent=2))
    # Replay never grants production enablement. Live recall/schema success also
    # does not automatically approve factual correctness of generated answers.
    return 1 if any(not c['passed'] for c in output.get('cases',[])) else 0


if __name__ == '__main__':
    raise SystemExit(main())
