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
    # The real extraction contract always includes these critical structures.
    extract_schema = {'type': 'OBJECT', 'properties': {key: {'type': 'OBJECT'} for key in
        ('clinical_facts', 'fields', 'teeth', 'appointment')},
        'required': ['clinical_facts', 'fields', 'teeth', 'appointment']}
    result = {key: {} for key in extract_schema['required']}
    calls, _ = transport(monkeypatch, {'stop_reason': 'tool_use', 'content': [
        {'type': 'tool_use', 'name': 'clinical_extract', 'input': result}]})
    assert provider.review('policy', {}, extract_schema, extraction=True) == result
    payload = json.loads(calls[0][0].data)
    assert payload['tool_choice'] == {'type': 'tool', 'name': 'clinical_extract'}
    assert 'output_config' not in payload and payload['tools'][0]['strict'] is True
    assert len(calls) == 1


@pytest.mark.parametrize('name,reason', [('other_tool', 'tool_use'), ('clinical_extract', 'max_tokens'), ('clinical_extract', 'end_turn')])
def test_extraction_rejects_wrong_tool_or_incomplete_output(monkeypatch, name, reason):
    calls, _ = transport(monkeypatch, {'stop_reason': reason, 'content': [
        {'type': 'tool_use', 'name': name, 'input': {'items': []}}]})
    with pytest.raises(ValueError): provider.review('policy', {}, SCHEMA, extraction=True)
    assert len(calls) == 1


@pytest.mark.parametrize('encoded', [False, True])
def test_extraction_unpacks_single_known_data_wrapper_without_inventing_fields(monkeypatch, encoded):
    keys = ['clinical_facts', 'fields', 'teeth', 'appointment']
    schema = {'type': 'OBJECT', 'properties': {}, 'required': keys}
    nested = {'clinical_facts': [], 'fields': {}, 'teeth': []}
    wrapped = {'appointment': {}, 'data': json.dumps(nested) if encoded else nested}
    transport(monkeypatch, {'stop_reason': 'tool_use', 'content': [
        {'type': 'tool_use', 'name': 'clinical_extract', 'input': wrapped}]})
    assert provider.review('policy', {}, schema, extraction=True) == {**nested, 'appointment': {}}


def test_wrapper_empty_placeholder_and_rewritten_transcript_do_not_hide_facts(monkeypatch):
    keys = ['clinical_facts', 'fields', 'teeth', 'appointment', 'transcript']
    schema = {'type': 'OBJECT', 'properties': {}, 'required': keys}
    text = 'Bugün saat on yedide gelin.'
    nested = {'clinical_facts': [], 'fields': {}, 'teeth': [], 'transcript': 'Farklı model özeti',
              'appointment': {'quote': text, 'acceptance_quote': ''}}
    wrapped = {'transcript': 'Başka özet', 'appointment': {'quote': '', 'acceptance_quote': ''}, 'data': nested}
    transport(monkeypatch, {'stop_reason': 'tool_use', 'content': [
        {'type': 'tool_use', 'name': 'clinical_extract', 'input': wrapped}]})
    result = provider.review('policy', {'clinical_text': text}, schema, extraction=True)
    assert result['appointment']['quote'] == text and result['transcript'] == text


def test_wrapper_conflicting_nonempty_clinical_fields_are_rejected(monkeypatch):
    keys = ['clinical_facts', 'fields', 'teeth', 'appointment']
    schema = {'type': 'OBJECT', 'properties': {}, 'required': keys}
    wrapped = {'fields': {'medications': 'A'}, 'data': {
        'clinical_facts': [], 'fields': {'medications': 'B'}, 'teeth': [], 'appointment': {}}}
    transport(monkeypatch, {'stop_reason': 'tool_use', 'content': [
        {'type': 'tool_use', 'name': 'clinical_extract', 'input': wrapped}]})
    with pytest.raises(ValueError, match='Conflicting'):
        provider.review('policy', {}, schema, extraction=True)
