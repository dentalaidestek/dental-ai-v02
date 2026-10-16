from unittest.mock import Mock
import pytest
import app.study_provider as providers
from app.study_provider import GeminiStudyProvider, StudyProviderError
from app.study_router_state import _backoff_seconds


def ready_provider(monkeypatch, *, available_at=2):
    clock=[0.0]
    class Pause:
        def wait(self,seconds):
            clock[0]+=seconds
    monkeypatch.setattr(providers.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(providers.threading,'Event',Pause)
    monkeypatch.setattr(providers.random,'uniform',lambda *args:.2)
    gate=Mock(side_effect=lambda *args:clock[0]>=available_at)
    monkeypatch.setattr(providers,'router_target_available',gate)
    provider=GeminiStudyProvider();provider.capacity_retry=True
    return provider,clock,gate


def failure(code=503):
    return StudyProviderError('temporary',code=code,retryable=True,tracked=True)


def test_planner_capacity_recovery_reuses_identical_request_once(monkeypatch):
    provider,clock,gate=ready_provider(monkeypatch)
    call=Mock(side_effect=[failure(),{'ok':True},failure()])
    monkeypatch.setattr(provider,'_request_json_once',call)
    kwargs=dict(model='fixture',operation='generation')
    assert provider._request_json('url',{'original':'payload'},**kwargs)=={'ok':True}
    assert call.call_args_list[0]==call.call_args_list[1]
    assert 2<=clock[0]<=6 and gate.call_count>1
    with pytest.raises(StudyProviderError):
        provider._request_json('url',{},**kwargs)
    assert call.call_count==3  # One recovery budget, not one per subsequent call.


@pytest.mark.parametrize('code',[400,401,402,403,404,429,500,504])
def test_other_errors_do_not_wait_or_retry(monkeypatch,code):
    provider,clock,gate=ready_provider(monkeypatch)
    call=Mock(side_effect=failure(code));monkeypatch.setattr(provider,'_request_json_once',call)
    with pytest.raises(StudyProviderError):
        provider._request_json('url',{},model='fixture',operation='generation')
    assert call.call_count==1 and clock[0]==0 and not gate.called


def test_long_router_block_is_not_bypassed(monkeypatch):
    provider,clock,gate=ready_provider(monkeypatch,available_at=300)
    call=Mock(side_effect=failure());monkeypatch.setattr(provider,'_request_json_once',call)
    with pytest.raises(StudyProviderError):
        provider._request_json('url',{},model='fixture',operation='generation')
    assert call.call_count==1 and clock[0]==6


@pytest.mark.parametrize('partial',[False,True])
def test_stream_retries_only_before_first_output(monkeypatch,partial):
    provider,clock,gate=ready_provider(monkeypatch)
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs)
        if len(calls)==1:
            if partial: yield 'already shown'
            raise failure()
        yield 'complete'
    monkeypatch.setattr(provider,'_generate_stream_once',stream)
    output=provider.generate_stream(model='fixture',prompt='same evidence')
    if partial:
        assert next(output)=='already shown'
        with pytest.raises(StudyProviderError): next(output)
        assert len(calls)==1 and not gate.called
    else:
        assert list(output)==['complete'] and len(calls)==2
        assert calls[0]==calls[1]


def test_extraction_and_embedding_do_not_gain_nested_retries(monkeypatch):
    provider,clock,gate=ready_provider(monkeypatch)
    provider.capacity_retry=False
    assert not provider._recover_capacity(failure(),'fixture')
    provider.capacity_retry=True
    call=Mock(side_effect=failure());monkeypatch.setattr(provider,'_request_json_once',call)
    with pytest.raises(StudyProviderError):
        provider._request_json('url',{},model='fixture',operation='embedding')
    assert call.call_count==1 and not gate.called


def test_capacity_backoff_is_short_bounded_and_respects_retry_after():
    assert [_backoff_seconds(503,n,None) for n in range(1,7)]==[2,5,15,60,120,120]
    assert _backoff_seconds(503,1,180)==180
    assert _backoff_seconds(429,1,None)==600
    assert _backoff_seconds(403,1,None)==21600


@pytest.mark.parametrize('gap,expected',[(10,5),(301,1)])
def test_old_capacity_failure_streak_decays_after_idle(monkeypatch,gap,expected):
    import app.study_router_state as router
    state=router._TargetMemory(provider='gemini',model='fixture',
        consecutive_failures=4,last_failure_at_epoch=1000-gap)
    shared=router._ProviderMemory(provider='gemini')
    monkeypatch.setattr(router,'ensure_started',lambda:None)
    monkeypatch.setattr(router,'_get_target',lambda *args:state)
    monkeypatch.setattr(router,'_get_provider_state',lambda *args:shared)
    monkeypatch.setattr(router.time,'time',lambda:1000)
    monkeypatch.setattr(router,'_QUEUE',Mock())
    router.record_api_result(provider='gemini',model='fixture',operation='generation',
        success=False,status_code=503,latency_ms=1)
    assert state.consecutive_failures==expected
    assert state.circuit_open_until_epoch==1000+_backoff_seconds(503,expected,None)
