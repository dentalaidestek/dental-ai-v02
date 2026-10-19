from app.study_anthropic import AnthropicStudyProvider
from app.study_router_state import _usage_from_json


def test_cache_boundary_excludes_changing_sources_and_history():
    provider = AnthropicStudyProvider()
    provider.cache_static_system = True
    def payload(question):
        return provider._payload(model='claude-haiku-5-5', system_prompt='Fixed instructions',
            history=[{'role': 'USER', 'content': 'Private conversation'}], prompt=question,
            attachments=[{'mime_type': 'application/pdf', 'data': b'%PDF-private'}])
    first, second = payload('Source A'), payload('Source B')
    assert first['system'] == second['system'] == [
        {'type': 'text', 'text': 'Fixed instructions', 'cache_control': {'type': 'ephemeral'}}]
    assert first['messages'] != second['messages']
    assert 'cache_control' not in repr(first['messages'])
    assert 'cache_control' not in first


def test_other_callers_do_not_implicitly_enable_cache():
    payload = AnthropicStudyProvider()._payload(model='claude-haiku-5-5',
        system_prompt='Caller supplied context', history=[], prompt='Question')
    assert payload['system'] == 'Caller supplied context'


def test_cached_input_still_counts_toward_total_usage():
    assert _usage_from_json({'usage': {'input_tokens': 100, 'cache_read_input_tokens': 2000,
        'cache_creation_input_tokens': 300, 'output_tokens': 20}}) == (2400, 20, 2420)
