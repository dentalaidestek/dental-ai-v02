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
