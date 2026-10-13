import pytest
from app.academic_source_batches import partition_source_rows, load_owned_source_rows


def row(cid, page, heading='Deri noktalar > Tek noktalar', material=1, text='definition'):
    return (cid,material,'note',page,page,heading,'TEXT',text,None,None,None,None,1,cid,'{}')


def test_long_section_keeps_every_middle_and_end_page_in_source_order():
    rows = [row(i,i) for i in range(1,1001)]
    batches = partition_source_rows(reversed(rows), max_pages=16)
    assert [cid for batch in batches for cid in batch.chunk_ids] == list(range(1,1001))
    assert len(batches) == 63
    assert all(len(batch.chunk_ids) <= 16 for batch in batches)


def test_small_documents_share_budget_with_heading_identity_and_deduplication():
    rows = [row(1,1),row(1,1),row(2,2,'Deri noktalar > Çift noktalar'),
            row(3,1,material=2)]
    batches = partition_source_rows(rows)
    assert [batch.chunk_ids for batch in batches] == [(1,2,3)]
    assert 'Tek' in batches[0].title and 'Çift' in batches[0].title


def test_visual_page_budget_counts_same_page_number_in_different_documents():
    rows = [row(1,1,material=1), row(2,1,material=2), row(3,1,material=3)]
    batches = partition_source_rows(rows, max_pages=2,
                                    visual_pages={(1,1),(2,1),(3,1)})
    assert [batch.chunk_ids for batch in batches] == [(1,2),(3,)]


def test_cross_document_character_budget_still_splits_without_losing_sources():
    rows = [row(i,1,material=i,text='x'*300) for i in range(1,5)]
    batches = partition_source_rows(rows, max_chars=1200, visual_pages=set())
    assert [batch.chunk_ids for batch in batches] == [(1,2),(3,4)]


def test_cross_document_comparison_reaches_one_generation_with_both_sources(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    import app.academic_semantic_retrieval as semantic
    import app.study_ai_v2 as generation
    from app.academic_source_batches import retrieve_row_batches
    from app.study_retrieval_v2 import RetrievalResult

    rows = [row(1,90,material=1,text='Retrognatik: ANB artar.'),
            row(2,6,material=2,text='Prognatik: ANB azalır.')]
    session = Mock()
    session.exec.return_value.all.return_value = []
    plan = SimpleNamespace(needs_visual=False, scope='topic')
    def retrieve(session, **kwargs):
        selected = kwargs['_source_rows']
        return RetrievalResult(note_context=[r[7] for r in selected],
            evidence_sufficient=True, study_task={'operation':'compare','scope':'topic'})
    monkeypatch.setattr(semantic, 'retrieve_semantic_context', retrieve)
    result = retrieve_row_batches(session, rows=rows, owner_user_id=17,
        course_id=23, query='İki yüz tipini karşılaştır', request_plan=plan)
    model = Mock()
    model.generate_stream.return_value = iter(['Retrognatik: artar. Prognatik: azalır.'])
    monkeypatch.setattr(generation, 'target_available', lambda target: True)
    monkeypatch.setattr(generation, 'get_provider', lambda name: model)
    monkeypatch.setattr(generation, 'report_target_success', lambda target: None)
    assert generation.ask_rag_v2('Course','İki yüz tipini karşılaştır',[],result)
    assert model.generate_stream.call_count == 1
    prompt = model.generate_stream.call_args.kwargs['prompt']
    assert rows[0][7] in prompt and rows[1][7] in prompt


def test_character_budget_splits_without_discarding_remainder():
    batches = partition_source_rows([row(i,i,text='a'*300) for i in range(1,9)],max_chars=1200)
    assert [cid for batch in batches for cid in batch.chunk_ids] == list(range(1,9))
    assert len(batches) > 1
    with pytest.raises(ValueError, match='exceeds'):
        partition_source_rows([row(1,1,text='a'*2000)],max_chars=1200)


def test_many_short_digital_pages_share_one_request_but_visual_pages_split():
    rows=[row(i,i) for i in range(1,51)]
    assert len(partition_source_rows(rows,visual_pages=set()))==1
    assert len(partition_source_rows(rows,visual_pages={(1,i) for i in range(1,51)}))==4


def test_reader_paginates_beyond_old_limit_with_owner_course_fences(monkeypatch):
    import app.study_retrieval_v2 as module
    rows = [row(i,i) for i in range(1,301)]
    calls=[]
    def metadata(session, **kw):
        calls.append(kw)
        return [r for r in rows if r[0]>kw['after_id']][:kw['limit']]
    def hydrate(session, **kw):
        assert kw['owner_user_id']==17 and kw['course_id']==23
        return [r for r in rows if r[0] in kw['chunk_ids']]
    monkeypatch.setattr(module,'_coverage_metadata_page',metadata)
    monkeypatch.setattr(module,'_coverage_evidence_rows',hydrate)
    assert len(list(load_owned_source_rows(None,owner_user_id=17,course_id=23)))==300
    assert [kw['after_id'] for kw in calls]==[0,128,256,300]
    assert all(kw['owner_user_id']==17 and kw['course_id']==23 for kw in calls)


def test_question_reader_visits_beyond_first_sixteen_without_fact_filter(monkeypatch):
    from app.academic_source_batches import load_owned_question_rows
    import app.study_retrieval_v2 as module
    rows=[tuple(list(row(i,i))[:6]+['QUESTION']+list(row(i,i))[7:]) for i in range(1,71)]
    calls=[]
    def questions(session, **kw):
        calls.append(kw)
        after=kw['after_cursor'] or (0,0)
        return [r for r in rows if (r[1],r[13])>after][:33]
    monkeypatch.setattr(module,'_question_rows',questions)
    selected=list(load_owned_question_rows(None,owner_user_id=17,course_id=23))
    assert selected==rows
    batches=partition_source_rows(selected,include_questions=True,visual_pages=set())
    assert [cid for batch in batches for cid in batch.chunk_ids]==list(range(1,71))
    assert all(c['owner_user_id']==17 and c['course_id']==23 for c in calls)
    assert list(partition_source_rows(selected,visual_pages=set()))==[]


def test_question_reader_rejects_nonadvancing_cursor(monkeypatch):
    from app.academic_source_batches import load_owned_question_rows
    monkeypatch.setattr('app.study_retrieval_v2._question_rows',lambda *a,**k:[row(1,1)])
    with pytest.raises(ValueError,match='did not advance'):
        list(load_owned_question_rows(None,owner_user_id=17,course_id=23))
