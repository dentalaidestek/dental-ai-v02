"""Regressions from the ten live study-flow checks; no provider calls."""
import json
from types import SimpleNamespace
from app.academic_request_understanding import StudyRequest,interpret_request


def test_normalized_planner_queries_survive_subject_candidate_selection(monkeypatch):
    from app import academic_semantic_retrieval as retrieval
    from app import academic_native_evidence as native
    from app.academic_chunk_links import CourseLinks
    def row(ident,page,text):
        return (ident,37,'Notes.pdf',page,page,None,'TEXT',text,ident,None,None,None,1.0,ident)
    rows=[row(1,2,'Genetik testlerin sınırlarını konuşacağız.'),
          row(2,14,'Genetik testler rutin klinik kullanım için yeterli mi? İstatistiksel ilişki klinik yarar değildir.')]
    captured=[]
    def candidates(session,**kwargs):
        assert kwargs['owner_user_id']==1 and kwargs['course_id']==6
        return rows
    def native_matches(session,**kwargs):
        captured.append(tuple(kwargs['searches']))
        return [],False
    monkeypatch.setattr(retrieval,'_fts_rows',candidates)
    monkeypatch.setattr(retrieval,'get_course_links',lambda *a,**k:CourseLinks(rows={},by_node={},by_section={}))
    monkeypatch.setattr(native,'matching_native_pages',native_matches)
    monkeypatch.setattr(native,'selected_native_pages',lambda *a,**k:{})
    session=SimpleNamespace(get_bind=lambda:SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))
    plan=StudyRequest(resolved_query='Genetik testleri öğret',operation='teach',scope='topic',count=None,
        difficulty=None,clarification='',complete_sections=False,
        source_subjects=('genetik testlerin kullanımı',),
        retrieval_queries=('genetik testler rutin klinik kullanım','istatistiksel ilişki klinik yarar'))
    result=retrieval.retrieve_semantic_context(session,owner_user_id=1,course_id=6,
        query='Bana öğret',request_plan=plan)
    assert (37,14) in {(e.material_id,e.page_start) for e in result.evidence}
    assert captured==[plan.source_subjects+plan.retrieval_queries]


def test_internal_markers_are_not_paid_planner_context_but_source_state_survives():
    from app.academic_direct_request import source_marker
    marker=source_marker({'operation':'answer','scope':'topic','resolved_query':'Genetik testler hakkında','retrieval_queries':['genetik testler'],
        'source_sections':[],'source_files':[],'source_pages':[]})
    history=[{'role':'ASSISTANT','content':'Görünen açıklama.\n'+marker+'\n<!--ACADEMIC_Q_CURSOR:37:14-->'}]
    captured=[]
    def call(prompt):captured.append(json.loads(prompt));return '{}'
    interpret_request('Bunu tablo yap',history,call=call)
    payload=captured[0]
    assert payload['recent_dialogue'][0]['content']=='Görünen açıklama.'
    assert payload['recent_source_request']['retrieval_queries']==['genetik testler']
    assert '<!--ACADEMIC_' in history[0]['content']
    assert 'ACADEMIC_SOURCE_REQUEST' not in json.dumps(payload)


def selected_plan(**changes):
    from dataclasses import replace
    plan=StudyRequest(resolved_query='Genetik testler',operation='answer',scope='topic',
        count=None,difficulty=None,clarification='',complete_sections=False,
        source_files=('Selected.pdf',),source_subjects=('genetik testler',),
        retrieval_queries=('istatistiksel ilişki klinik yarar',))
    return replace(plan,**changes)


def selected_rows():
    def row(ident,page,text):
        return (ident,37,'Selected.pdf',page,page,None,'TEXT',text,ident,None,None,None,1.0,ident)
    return [row(1,2,'Genetik testler hakkında giriş.'),
            row(2,14,'Genetik testler: istatistiksel ilişki klinik yarar değildir.'),
            row(3,20,'Gelir eğitim ve sosyal koşullar.'),
            row(4,21,'Yaş ve biyolojik cinsiyet değiştirilemez.')]


def test_explicit_file_topic_keeps_normalized_answer_page_without_unrelated_pages():
    from app.academic_source_batches import focused_selected_rows
    rows=selected_rows()
    assert [r[3] for r in focused_selected_rows(rows,selected_plan())]==[2,14]
    assert len(rows)==4


def test_compared_subjects_each_keep_their_own_evidence_inside_selected_file():
    from app.academic_source_batches import focused_selected_rows
    plan=selected_plan(source_subjects=('sosyal koşullar','biyolojik cinsiyet'),
                       retrieval_queries=('gelir eğitim','yaş değiştirilemez'))
    assert [r[3] for r in focused_selected_rows(selected_rows(),plan)]==[20,21]


def test_full_coverage_and_explicit_page_requests_are_not_topic_truncated():
    from app.academic_source_batches import focused_selected_rows
    rows=selected_rows()
    for changes in ({'complete_sections':True},{'scope':'course'},
                    {'source_pages':(14,20)}, {'needs_visual':True},
                    {'source_sections':('Genetik',)}, {'source_kind':'questions'}):
        assert focused_selected_rows(rows,selected_plan(**changes)) is rows


def test_unmatched_search_keeps_owned_file_instead_of_claiming_no_evidence():
    from app.academic_source_batches import focused_selected_rows
    rows=selected_rows()
    assert focused_selected_rows(rows,selected_plan(retrieval_queries=('bilinmeyen terim',))) == rows


def test_equally_relevant_pages_are_retained_without_arbitrary_top_k():
    from app.academic_source_batches import focused_selected_rows
    rows=selected_rows()
    rows.append((5,37,'Selected.pdf',15,15,None,'TEXT',rows[1][7],5,None,None,None,1.0,5))
    assert [r[3] for r in focused_selected_rows(rows,selected_plan())]==[2,14,15]


def test_multiple_selected_files_keep_independent_evidence_and_fallbacks():
    from app.academic_source_batches import focused_selected_rows
    rows=selected_rows()
    # A second file's shorter match must not be crowded out by the first file.
    rows.extend([(5,38,'Other.pdf',1,1,None,'TEXT','Genetik testler klinik yarar.',5,None,None,None,1.0,5),
                 (6,38,'Other.pdf',2,2,None,'TEXT','İlişkinin araştırıldığı farklı örneklem.',6,None,None,None,1.0,6)])
    result=focused_selected_rows(rows,selected_plan(source_files=('Selected.pdf','Other.pdf'),retrieval_queries=('istatistiksel',)))
    assert {r[1] for r in result}=={37,38}
    assert {r[0] for r in result}=={1,2,5,6}


def test_course_explanations_retrieve_all_notes_instead_of_sampled_coverage(monkeypatch):
    from app import academic_source_batches as batches
    from app import academic_semantic_retrieval as semantic
    from app.academic_request_understanding import UnderstandingResult,retrieve_understood_course_context
    from app.study_retrieval_v2 import RetrievalResult
    calls=[]
    def retrieve(session,**kwargs):
        calls.append(kwargs['request_plan'].operation)
        return RetrievalResult(evidence_sufficient=True,retrieval_mode='source_batches')
    monkeypatch.setattr(batches,'retrieve_source_batches',retrieve)
    monkeypatch.setattr(semantic,'retrieve_semantic_context',lambda *a,**k: (_ for _ in ()).throw(AssertionError('sampled course coverage')))
    for operation in ('answer','explain','compare','teach','summarize','generate_questions'):
        plan=selected_plan(scope='course',operation=operation,source_files=(),source_subjects=(),retrieval_queries=())
        result=retrieve_understood_course_context(None,understanding=UnderstandingResult(plan=plan,outcome='ok'),
            owner_user_id=1,course_id=6,query='Hepsini detaylandır',recent_history=[])
        assert result.retrieval_mode=='source_batches'
    assert calls==['answer','explain','compare','teach','summarize','generate_questions']


def test_new_quiz_preserves_supporting_pages_beyond_single_best_lexical_hit():
    from app.academic_source_batches import focused_selected_rows
    rows=selected_rows()
    rows.append((5,37,'Selected.pdf',15,15,None,'TEXT','Klinik yarar testin yönetimi iyileştirmesidir.',5,None,None,None,1.0,5))
    plan=selected_plan(operation='generate_questions')
    assert {r[3] for r in focused_selected_rows(rows,plan)}=={2,14,15}
