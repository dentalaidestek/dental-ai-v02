from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from scripts.enrich_academic_vectors import enrich


def setup(monkeypatch,*,changed=False):
    import scripts.enrich_academic_vectors as module
    monkeypatch.setattr(module,'get_embedding_target',lambda:SimpleNamespace(provider='gemini',model='fixture'))
    monkeypatch.setattr(module,'get_embedding_dimensions',lambda:128)
    session=Mock();session.get_bind.return_value.dialect.name='postgresql'
    values=[(1,'v1','source-sha','literal source','parent > heading','file.pdf')]
    session.exec.side_effect=[Mock(first=Mock(return_value=(1,))),Mock(all=Mock(return_value=values)),
                              Mock(rowcount=0 if changed else 1)]
    state={'open':False}
    @contextmanager
    def factory():
        state['open']=True
        try:yield session
        finally:state['open']=False
    def embed(**kwargs):
        assert not state['open']
        assert 'file.pdf' in kwargs['text'] and 'parent > heading' in kwargs['text'] and 'literal source' in kwargs['text']
        return [1.0]+[0.0]*127
    provider=SimpleNamespace(embed_text=Mock(side_effect=embed))
    monkeypatch.setattr(module,'GeminiStudyProvider',lambda:provider)
    return session,factory,provider


def test_default_dry_run_has_zero_vendor_calls_and_no_writes(monkeypatch):
    session,factory,provider=setup(monkeypatch)
    result=enrich(factory,owner_user_id=17,course_id=23)
    assert result['pending']==1 and result['external_calls']==0 and not result['run']
    provider.embed_text.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize('changed',[False,True])
def test_enrichment_is_source_scoped_resume_safe_and_never_republishes(monkeypatch,changed):
    session,factory,provider=setup(monkeypatch,changed=changed)
    result=enrich(factory,owner_user_id=17,course_id=23,max_chunks=1,run=True)
    assert result['external_calls']==1 and result['updated']==int(not changed)
    assert result['skipped_changed']==int(changed)
    provider.embed_text.assert_called_once()
    assert provider.max_attempts==1
    query=str(session.exec.call_args_list[-1].args[0])
    assert 'c.text_sha256=:sha' in query and 'm.active_index_version=c.index_version' in query
    assert 'active_index_version=' not in query.split('FROM studymaterial')[0]
    assert 'index_status=' not in query.split('FROM studymaterial')[0]
    if changed:session.rollback.assert_called_once();session.commit.assert_not_called()
    else:session.commit.assert_called_once()


def test_invalid_chunk_budget_never_accesses_database():
    with pytest.raises(ValueError,match='bounded source selection'):
        enrich(Mock(side_effect=AssertionError('database access')),owner_user_id=17,course_id=23,max_chunks=257)
