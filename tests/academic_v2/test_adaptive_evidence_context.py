from unittest.mock import Mock
import pytest
from app.academic_evidence_context import small_note_context
from app.academic_request_understanding import StudyRequest, UnderstandingResult, retrieve_understood_course_context
from app.study_retrieval_v2 import RetrievalResult, _fts_rows


def test_expanded_candidates_and_source_domain_are_applied_before_ranking():
    session=Mock()
    session.exec.return_value.all.return_value=[]
    for domain,clause in [('notes', "c.content_kind <> 'QUESTION'"),
                          ('questions', "c.content_kind = 'QUESTION'")]:
        _fts_rows(session,owner_user_id=17,course_id=23,lexical_query='"subject"',
                  query_vector=None,embedding_provider='',embedding_model='',limit=96,
                  content_domain=domain)
        query=str(session.exec.call_args.args[0])
        assert clause in query[:query.index('candidates AS')]
        assert 'm.course_id=c.course_id' in query
        assert session.exec.call_args.kwargs['params']['limit']==96
    with pytest.raises(ValueError,match='source content domain'):
        _fts_rows(session,owner_user_id=17,course_id=23,lexical_query='"subject"',
                  query_vector=None,embedding_provider='',embedding_model='',limit=96,
                  content_domain='unsafe')


@pytest.mark.parametrize('totals', [(0,0),(129,2000),(1,48001)])
def test_large_or_empty_courses_do_not_hydrate_whole_text(monkeypatch,totals):
    reader=Mock(side_effect=AssertionError('unbounded hydration'))
    monkeypatch.setattr('app.academic_source_batches.load_owned_source_rows',reader)
    session=Mock();session.exec.return_value.first.return_value=totals
    assert small_note_context(session,owner_user_id=17,course_id=23) is None
    reader.assert_not_called()


def test_small_course_preserves_every_row_and_has_no_provider_call(monkeypatch):
    rows=[(i,1,'note',i,i,'heading','TEXT','definition',None,None,None,None,1,i,'{}') for i in range(1,31)]
    reader=Mock(return_value=iter(rows))
    monkeypatch.setattr('app.academic_source_batches.load_owned_source_rows',reader)
    session=Mock(); session.exec.return_value.first.return_value=(30,6000)
    session.exec.return_value.all.return_value=[]
    assert small_note_context(session,owner_user_id=17,course_id=23)==rows
    reader.assert_called_once_with(session,owner_user_id=17,course_id=23)
    query=str(session.exec.call_args_list[0].args[0])
    assert "m.active_index_version=c.index_version" in query and "m.deleted_at IS NULL" in query
    assert session.exec.call_args_list[0].kwargs['params']=={'owner':17,'course':23}


def test_large_scan_set_stays_on_query_retrieval(monkeypatch):
    reader=Mock(side_effect=AssertionError('visual corpus hydration'))
    monkeypatch.setattr('app.academic_source_batches.load_owned_source_rows',reader)
    session=Mock();session.exec.return_value.first.return_value=(5,1200)
    session.exec.return_value.all.return_value=[(1,i) for i in range(1,6)]
    assert small_note_context(session,owner_user_id=17,course_id=23) is None
    reader.assert_not_called()


def test_small_context_rejects_changed_generation(monkeypatch):
    monkeypatch.setattr('app.academic_source_batches.load_owned_source_rows',Mock(return_value=[]))
    session=Mock(); session.exec.return_value.first.return_value=(1,200)
    session.exec.return_value.all.return_value=[]
    with pytest.raises(ValueError,match='generation changed'):
        small_note_context(session,owner_user_id=17,course_id=23)


def test_enabled_gateway_requests_adaptive_context_without_changing_gemini_task(monkeypatch):
    retrieve=Mock(return_value=RetrievalResult())
    monkeypatch.setattr('app.academic_semantic_retrieval.retrieve_semantic_context',retrieve)
    plan=StudyRequest('İkisini tabloyla karşılaştır','compare','topic',None,None,'',('alpha','beta'))
    retrieve_understood_course_context(Mock(),understanding=UnderstandingResult(plan=plan),
        owner_user_id=17,course_id=23,query='İkisini tabloyla karşılaştır',recent_history=[])
    assert retrieve.call_args.kwargs['prefer_full_context'] is True
    assert retrieve.call_args.kwargs['request_plan'] is plan


def test_named_subsection_boundary_prevents_whole_course_expansion(monkeypatch):
    import app.academic_semantic_retrieval as module
    from app.academic_chunk_links import build_course_links
    rows=[(1,1,'note',1,1,'Alpha > Single','TEXT','One definition',1,.2,None,None,1,1,'{}'),
          (2,1,'note',2,2,'Alpha > Paired','TEXT','Excluded sibling',1,.2,None,None,1,2,'{}')]
    monkeypatch.setattr(module,'get_course_links',lambda *a,**k:build_course_links([rows]))
    monkeypatch.setattr('app.academic_evidence_context.small_note_context',
                        Mock(side_effect=AssertionError('named section broadened')))
    monkeypatch.setattr(module,'_fts_rows',Mock(return_value=[]))
    monkeypatch.setattr(module,'_coverage_evidence_rows',lambda session,**kw:[row for row in rows if row[0] in kw['chunk_ids']])
    session=Mock();session.get_bind.return_value.dialect.name='postgresql'
    session.exec.return_value.all.return_value=[]
    plan=StudyRequest('Explain alpha single','explain','topic',None,None,'',('alpha single',))
    result=module.retrieve_semantic_context(session,owner_user_id=17,course_id=23,
        query=plan.resolved_query,request_plan=plan,prefer_full_context=True)
    assert [item.chunk_id for item in result.evidence]==[1]
