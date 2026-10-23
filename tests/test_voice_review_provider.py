import json
import sys
from contextlib import nullcontext
from types import ModuleType

import pytest

from app import voice_exam_core as core
from app import voice_exam_review_provider as provider


SCHEMA = {'type': 'OBJECT', 'properties': {'items': {'type': 'ARRAY', 'items': {
    'type': 'OBJECT', 'properties': {'field': {'type': 'STRING', 'enum': ['plan']}},
    'required': ['field']}}}, 'required': ['items']}


def transport(monkeypatch, message):
    import app.http_transport as http
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic-key')
    monkeypatch.setenv('VOICE_EXAM_CLAUDE_MODEL', 'claude-test')
    reservations, calls = [], []
    budget = ModuleType('app.provider_budget')
    def reserve(*args):
        reservations.append(args)
        return nullcontext()
    budget.reservation = reserve
    monkeypatch.setitem(sys.modules, 'app.provider_budget', budget)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return json.dumps(message).encode()
    def request(req, **kwargs):
        calls.append((req, kwargs))
        return Response()
    monkeypatch.setattr(http, 'urlopen', request)
    return calls, reservations


def test_claude_request_uses_single_budgeted_json_call_and_preserves_schema(monkeypatch):
    calls, reservations = transport(monkeypatch, {'stop_reason': 'end_turn',
        'content': [{'type': 'text', 'text': '{"items": []}'}]})
    assert provider.review('System policy', {'clinical_fields': {'plan': {'value': 'Henüz başlanmadı'}}}, SCHEMA) == {'items': []}
    assert len(calls) == 1 and reservations == [('anthropic', 'claude-test')]
    req, options = calls[0]
    payload = json.loads(req.data)
    assert req.full_url == 'https://api.anthropic.com/v1/messages'
    assert options['timeout'] == 90 and payload['stream'] is False
    assert 'generationConfig' not in payload and 'contents' not in payload
    schema = payload['output_config']['format']['schema']
    assert schema['additionalProperties'] is False
    assert schema['properties']['items']['items']['additionalProperties'] is False
    assert schema['properties']['items']['items']['properties']['field']['enum'] == ['plan']
    assert SCHEMA['type'] == 'OBJECT'


@pytest.mark.parametrize('reason', ['max_tokens', 'refusal', 'tool_use', None])
def test_incomplete_response_is_never_a_success_or_retried(monkeypatch, reason):
    calls, _ = transport(monkeypatch, {'stop_reason': reason,
        'content': [{'type': 'text', 'text': '{"items": []}'}]})
    with pytest.raises(ValueError): provider.review('policy', {}, SCHEMA)
    assert len(calls) == 1


def test_missing_key_cannot_silently_fall_back_to_gemini(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setenv('GEMINI_API_KEY', 'present-but-not-used')
    with pytest.raises(core.VoiceError, match='Claude'):
        provider.review('policy', {}, SCHEMA)


def test_extraction_uses_one_forced_data_tool_without_compiled_output_grammar(monkeypatch):
    calls, _ = transport(monkeypatch, {'stop_reason': 'tool_use', 'content': [
        {'type': 'tool_use', 'name': 'clinical_extract', 'input': {'items': []}}]})
    assert provider.review('policy', {}, SCHEMA, extraction=True) == {'items': []}
    payload = json.loads(calls[0][0].data)
    assert payload['tool_choice'] == {'type': 'tool', 'name': 'clinical_extract'}
    assert 'output_config' not in payload and 'strict' not in payload['tools'][0]
    assert len(calls) == 1


@pytest.mark.parametrize('name,reason', [('other_tool', 'tool_use'), ('clinical_extract', 'max_tokens'), ('clinical_extract', 'end_turn')])
def test_extraction_rejects_wrong_tool_or_incomplete_output(monkeypatch, name, reason):
    calls, _ = transport(monkeypatch, {'stop_reason': reason, 'content': [
        {'type': 'tool_use', 'name': name, 'input': {'items': []}}]})
    with pytest.raises(ValueError): provider.review('policy', {}, SCHEMA, extraction=True)
    assert len(calls) == 1
