"""Messages API framing, request isolation, stage routing, and failure integrity."""
from contextlib import nullcontext
from copy import deepcopy
import io
import json
import logging
import urllib.error
from unittest.mock import Mock

import pytest
import app.study_anthropic as transport
from app.study_anthropic import AnthropicStudyProvider
from app.study_provider import StudyProviderError


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(transport, 'target_available', lambda *a: True)
    monkeypatch.setattr(transport, 'provider_reservation', lambda *a: nullcontext())
    monkeypatch.setattr(transport, 'record_api_result', Mock())
    value = AnthropicStudyProvider()
    value.api_key = 'PRIVATE-KEY'
    return value


def kwargs(**extra):
    return dict(model='claude-haiku-5-5', system_prompt='PRIVATE-SYSTEM', history=[],
                prompt='PRIVATE-QUESTION', **extra)


def response(monkeypatch, *, result=None, events=None):
    value = Mock(status=200, headers={})
    value.read.return_value = json.dumps(result or {}).encode()
    value.__iter__ = Mock(return_value=iter(events or []))
    call = Mock(return_value=nullcontext(value))
    monkeypatch.setattr(transport, 'urlopen', call)
    return call


def frames(*events):
    return [line for event in events for line in
            [b'event: ' + event['type'].encode() + b'\r\n',
             b'data: ' + json.dumps(event).encode() + b'\r\n', b'\r\n']]


def ending(reason='end_turn'):
    return [{'type': 'message_delta', 'delta': {'stop_reason': reason},
             'usage': {'output_tokens': 7}}, {'type': 'message_stop'}]


def text(value):
    return {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': value}}


def test_json_request_uses_claude_schema_and_preserves_history_sources(provider, monkeypatch):
    from app.academic_request_understanding import SCHEMA
    schema = deepcopy(SCHEMA)
    provider.response_schema = schema
    call = response(monkeypatch, result={'content': [{'type': 'text', 'text': '{"ok":true}'}],
                                         'stop_reason': 'end_turn', 'usage': {'input_tokens': 13}})
    assert provider.generate(**{**kwargs(), 'history': [{'role': 'ASSISTANT', 'content': 'prior'}]},
        attachments=[{'mime_type': 'image/png', 'data': b'page', 'label': 'source page 4'}]) == '{"ok":true}'
    request = call.call_args.args[0]
    payload = json.loads(request.data)
    assert request.full_url == 'https://api.anthropic.com/v1/messages'
    assert request.get_header('X-api-key') == 'PRIVATE-KEY'
    assert request.get_header('Anthropic-version') == '2023-06-01'
    assert payload['system'] == 'PRIVATE-SYSTEM' and payload['messages'][0]['role'] == 'assistant'
    content = payload['messages'][-1]['content']
    assert content[0]['text'] == 'source page 4' and content[1]['type'] == 'image'
    assert content[-1]['text'] == 'PRIVATE-QUESTION'
    assert payload['output_config']['effort'] == 'medium'
    assert 'maxItems' not in payload['output_config']['format']['schema']['properties']['source_pages']
    assert schema == SCHEMA and 'temperature' not in payload and 'generationConfig' not in payload
    assert payload['max_tokens'] == 7000 and payload['stream'] is False


def test_stream_only_emits_answer_text_and_accounts_usage(provider, monkeypatch, caplog):
    call = response(monkeypatch, events=frames(
        {'type': 'message_start', 'message': {'usage': {'input_tokens': 11}}},
        {'type': 'content_block_delta', 'delta': {'type': 'thinking_delta', 'thinking': 'PRIVATE-THINKING'}},
        text('Birinci '), {'type': 'ping'}, text('yanıt'), *ending()))
    with caplog.at_level(logging.INFO):
        assert list(provider.generate_stream(**kwargs())) == ['Birinci ', 'yanıt']
    assert provider.last_finish_reason == 'STOP' and call.call_count == 1
    ledger = transport.record_api_result.call_args.kwargs
    assert ledger['success'] and ledger['response_json']['usage'] == {'input_tokens': 11, 'output_tokens': 7}
    assert not any(value in caplog.text for value in ['PRIVATE-KEY', 'PRIVATE-THINKING', 'PRIVATE-QUESTION', 'PRIVATE-SYSTEM'])


@pytest.mark.parametrize('events', [frames(text('partial')), frames(text('partial'), {'type':'message_stop'}),
    frames(text('partial'), {'type':'error','error':{'type':'overloaded_error','message':'PRIVATE'}})])
def test_incomplete_stream_is_never_successfully_completed_or_replayed(provider, monkeypatch, events):
    call = response(monkeypatch, events=events)
    provider.capacity_retry = True
    retry = Mock(return_value=True)
    monkeypatch.setattr(provider, '_recover_capacity', retry)
    stream = provider.generate_stream(**kwargs())
    assert next(stream) == 'partial'
    with pytest.raises(StudyProviderError):
        list(stream)
    retry.assert_not_called()
    assert not transport.record_api_result.call_args.kwargs['success'] and call.call_count == 1


def test_max_tokens_is_reported_to_generation_and_rejected_by_planner(provider, monkeypatch):
    response(monkeypatch, events=frames(text('incomplete'), *ending('max_tokens')))
    assert ''.join(provider.generate_stream(**kwargs())) == 'incomplete'
    assert provider.last_finish_reason == 'MAX_TOKENS'
    response(monkeypatch, result={'content': [{'type': 'text', 'text': '{}'}], 'stop_reason': 'max_tokens'})
    with pytest.raises(StudyProviderError, match='uzunluk'):
        provider.generate(**kwargs())


@pytest.mark.parametrize('code', [400, 401, 402, 403, 404, 429, 500, 503, 529])
def test_http_failure_is_tracked_once_without_exposing_body(provider, monkeypatch, code, caplog):
    call = Mock(side_effect=urllib.error.HTTPError('https://api.anthropic.com/v1/messages', code,
        'PRIVATE', {}, io.BytesIO(b'PRIVATE-SOURCE')))
    monkeypatch.setattr(transport, 'urlopen', call)
    with pytest.raises(StudyProviderError) as failure:
        provider.generate(**kwargs())
    assert failure.value.code == code and failure.value.tracked and call.call_count == 1
    assert transport.record_api_result.call_count == 1
    assert transport.record_api_result.call_args.kwargs['status_code'] == code
    assert 'PRIVATE' not in str(failure.value) and 'PRIVATE' not in caplog.text


def test_preoutput_overload_retries_same_payload_at_most_once(provider, monkeypatch):
    calls = []
    def run(payload):
        calls.append(payload)
        if len(calls) == 1:
            raise StudyProviderError('busy', code=529, retryable=True)
        yield 'answer'
    monkeypatch.setattr(provider, '_run_once', run)
    provider.capacity_retry = True
    assert list(provider.generate_stream(**kwargs())) == ['answer']
    assert calls[0] == calls[1] and provider._capacity_recovery_used
    assert not provider._recover_capacity(StudyProviderError('busy', code=529, retryable=True), 'test')


def test_missing_key_unsupported_attachment_and_invalid_effort_fail_before_transport(provider, monkeypatch):
    http = Mock()
    monkeypatch.setattr(transport, 'urlopen', http)
    provider.api_key = ''
    with pytest.raises(StudyProviderError) as error:
        provider.generate(**kwargs())
    assert error.value.code == 401
    with pytest.raises(StudyProviderError):
        provider.generate(**kwargs(attachments=[{'mime_type': 'application/zip', 'data': b'bad'}]))
    monkeypatch.setenv('STUDY_ANTHROPIC_EFFORT', 'unbounded')
    with pytest.raises(StudyProviderError):
        provider.generate(**kwargs())
    http.assert_not_called()


def test_selected_provider_routes_planner_and_final_without_gemini(monkeypatch, provider):
    import app.study_provider as providers
    import app.study_ai_v2 as generation
    import app.academic_request_understanding as planner
    from app.academic_provider_config import academic_target
    from app.study_retrieval_v2 import RetrievalResult
    monkeypatch.setenv('STUDY_ACADEMIC_PROVIDER', 'anthropic')
    monkeypatch.delenv('STUDY_ACADEMIC_PLANNER_MODEL', raising=False)
    monkeypatch.delenv('STUDY_ACADEMIC_GENERATION_MODEL', raising=False)
    class ForbiddenGemini(providers.GeminiStudyProvider):
        def __init__(self):
            raise AssertionError('Gemini constructed')
    monkeypatch.setattr(providers, 'GeminiStudyProvider', ForbiddenGemini)
    monkeypatch.setattr(providers, 'target_available', lambda *a: True)
    monkeypatch.setattr(providers, 'get_provider', lambda name: provider if name == 'anthropic' else None)
    monkeypatch.setattr(provider, 'generate', Mock(return_value=json.dumps(dict(
        resolved_query='Sella nedir?', retrieval_queries=['Sella'], operation='answer', scope='topic',
        count=None, difficulty=None, clarification='', source_kind='notes', depth='standard',
        needs_visual=False, continue_source=False))))
    result = planner.understand_study_request('Sella nedir?', [])
    assert result.plan and provider.generate.call_args.kwargs['model'] == 'claude-haiku-5-5'
    assert provider.response_schema is None  # Planner modified only its copied adapter.
    assert academic_target('planner') == academic_target('generation')
    assert generation._generation_targets() == [academic_target()]
    # Final generation accepts real Claude transport, selected source images and source text.
    monkeypatch.setattr(generation, 'get_provider', lambda name: provider if name == 'anthropic' else None)
    monkeypatch.setattr(generation, 'target_available', lambda *a: True)
    monkeypatch.setattr(generation, 'report_target_success', lambda *a: None)
    monkeypatch.setattr(provider, 'generate_stream', Mock(return_value=iter(['source answer'])))
    retrieval = RetrievalResult(note_context=['owned source'], evidence_sufficient=True)
    assert 'source answer' in ''.join(generation.stream_rag_v2('Orto', 'Sella?', [], retrieval))


def test_bad_provider_model_pair_and_cached_usage(monkeypatch):
    from app.academic_provider_config import academic_target
    from app.study_router_state import _usage_from_json, _backoff_seconds
    monkeypatch.setenv('STUDY_ACADEMIC_PROVIDER', 'anthropic')
    monkeypatch.setenv('STUDY_ACADEMIC_PLANNER_MODEL', 'gemini-3.5-flash-lite')
    with pytest.raises(StudyProviderError, match='model ayarı'):
        academic_target('planner')
    assert _usage_from_json({'usage': {'input_tokens': 10, 'cache_read_input_tokens': 100,
        'cache_creation_input_tokens': 20, 'output_tokens': 7}}) == (130, 7, 137)
    assert _backoff_seconds(529, 1, None) == 2
    assert _backoff_seconds(529, 1, 180) == 180
