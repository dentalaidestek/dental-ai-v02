from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.academic_dense_retrieval import QueryEmbedding, prepare_query_embedding, hybrid_candidates
from app.academic_request_understanding import StudyRequest, UnderstandingResult


def understanding(scope='topic',operation='explain'):
    return UnderstandingResult(plan=StudyRequest('Explain alpha and beta',operation,scope,None,None,'',
        ('alpha','beta') if scope=='topic' else ()))


def dependencies(monkeypatch, totals, *, scans=0):
    import app.study_provider as module
    monkeypatch.setattr(module,'get_embedding_target',lambda:SimpleNamespace(provider='gemini',model='fixture-model'))
    monkeypatch.setattr(module,'get_embedding_dimensions',lambda:128)
    monkeypatch.setattr(module,'target_available',lambda target:True)
    state={'closed':False}
    session=Mock()
    session.exec.side_effect=[Mock(first=Mock(return_value=totals)),Mock(first=Mock(return_value=(scans,)))]
    @contextmanager
    def factory():
        try:yield session
        finally:state['closed']=True
    return session,factory,state


@pytest.mark.parametrize('plan',[UnderstandingResult(),understanding('course'),understanding(operation='clarify')])
def test_irrelevant_plans_never_open_database_or_call_embedding(plan):
    factory=Mock(side_effect=AssertionError('unnecessary preflight'))
    assert prepare_query_embedding(plan,session_factory=factory,owner_user_id=17,course_id=23) is None
    factory.assert_not_called()


@pytest.mark.parametrize('totals', [(129,60000,0),(1,500,1)])
def test_no_ready_vectors_or_small_context_makes_no_paid_call(monkeypatch,totals):
    session,factory,state=dependencies(monkeypatch,totals)
    constructor=Mock(side_effect=AssertionError('unnecessary embedding call'))
    monkeypatch.setattr('app.study_provider.GeminiStudyProvider',constructor)
    assert prepare_query_embedding(understanding(),session_factory=factory,owner_user_id=17,course_id=23) is None
    assert state['closed']
    constructor.assert_not_called()


def test_one_embedding_request_runs_after_preflight_transaction_closes(monkeypatch):
    session,factory,state=dependencies(monkeypatch,(129,60000,129))
    def embed(**kwargs):
        assert state['closed']
        assert kwargs=={'model':'fixture-model','text':'alpha\nbeta','dimensions':128}
        return [1.0]+[0.0]*127
    provider=SimpleNamespace(api_key='test-only',embed_text=Mock(side_effect=embed))
    monkeypatch.setattr('app.study_provider.GeminiStudyProvider',lambda:provider)
    result=prepare_query_embedding(understanding(),session_factory=factory,owner_user_id=17,course_id=23)
    assert result.provider=='gemini' and result.model=='fixture-model' and len(result.vector)==128
    assert provider.max_attempts==1
    provider.embed_text.assert_called_once()
    sql=str(session.exec.call_args_list[0].args[0])
    assert 'pending.index_version=c.index_version' in sql and 'm.active_index_version=c.index_version' in sql
    assert session.exec.call_args_list[0].kwargs['params']['owner']==17


def test_embedding_failure_preserves_lexical_search_without_retry(monkeypatch):
    session,factory,state=dependencies(monkeypatch,(129,60000,129))
    provider=SimpleNamespace(api_key='test-only',embed_text=Mock(side_effect=TimeoutError()))
    monkeypatch.setattr('app.study_provider.GeminiStudyProvider',lambda:provider)
    assert prepare_query_embedding(understanding(),session_factory=factory,owner_user_id=17,course_id=23) is None
    provider.embed_text.assert_called_once()
    assert state['closed']


@pytest.mark.parametrize('values',[(),(float('nan'),),(float('inf'),),(0.0,0.0)])
def test_invalid_query_vectors_are_rejected(values):
    with pytest.raises(ValueError,match='query embedding'):
        QueryEmbedding('gemini','fixture',values)


def row(ident,body,semantic_rank=None):
    return (ident,1,'note',ident,ident,None,'TEXT',body,1,.1,semantic_rank,.8,.3,ident,'{}')


def test_dense_paraphrase_survives_even_when_lexical_candidates_fill_budget():
    linked=[row(i,'alpha literal topic') for i in range(1,30)]
    dense=row(100,'a synonymous description with no literal overlap',1)
    selected=hybrid_candidates(linked,[dense,*linked],('alpha',),16)
    assert 100 in {value[0] for value in selected}
    assert any(value[7]=='alpha literal topic' for value in selected)
    assert len(selected)==16


def test_named_source_section_is_not_truncated_by_hybrid_ranking():
    from app.academic_semantic_retrieval import SectionEvidenceRows
    linked=SectionEvidenceRows([row(i,'alpha definition') for i in range(1,41)])
    result=hybrid_candidates(linked,[row(100,'synonymous description',1)],('alpha',),16)
    assert isinstance(result,SectionEvidenceRows)
    assert {value[0] for value in result}==set(range(1,41))|{100}
