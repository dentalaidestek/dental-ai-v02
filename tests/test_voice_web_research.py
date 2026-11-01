"""Native research uses public inputs and fetched text, never generated evidence."""
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict

import pytest

from app import voice_exam_review_provider as provider
from app import voice_exam_web_research as web
from app.voice_source_pool import BoundedPool

URL = 'https://www.ada.org/resources/research/pain'
TEXT = 'Dental pain management requires clinical assessment.\n\nSource paragraph with literal professional information.'
TOPICS = [{'topic': 'endo.general', 'quote': 'PRIVATE PATIENT ALICE 555', 'query': 'LEAK ME'}]


def fetched(url=URL, text=TEXT, ident='f1', source=None):
    return [
        {'type': 'server_tool_use', 'id': ident, 'name': 'web_fetch', 'input': {'url': url}},
        {'type': 'web_fetch_tool_result', 'tool_use_id': ident, 'content': {
            'type': 'web_fetch_result', 'url': url, 'retrieved_at': '2026-10-27T00:00:00Z',
            'content': {'type': 'document', 'title': 'Dental pain',
                        'source': source or {'type': 'text', 'media_type': 'text/plain', 'data': text}}}}]


def response(content=None, stop='end_turn'):
    return {'content': content or [], 'stop_reason': stop, 'usage': {'input_tokens': 100, 'output_tokens': 40}}


@pytest.mark.parametrize('title,text', [
    ('Checking your browser - reCAPTCHA', 'Checking your browser before accessing pmc.ncbi.nlm.nih.gov ...'),
    ('Just a moment...', 'Enable JavaScript and cookies to continue.'),
    ('Access Denied', 'You do not have permission to access this page.'),
])
def test_access_challenge_is_not_a_fetched_clinical_document(monkeypatch, title, text):
    blocks = fetched(text=text)
    blocks[1]['content']['content']['title'] = title
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(blocks))
    result = web.retrieve_web(TOPICS)
    assert result['references'] == []
    assert 'web-fetch-unavailable:access-blocked' in result['unavailable']


def test_article_mentioning_access_challenges_remains_available(monkeypatch):
    text = 'Clinical dental guideline. A bibliography mentions reCAPTCHA and access denied errors.'
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(fetched(text=text)))
    assert web.retrieve_web(TOPICS)['references'][0]['excerpts'][0] == text


def test_all_access_challenges_block_paid_final_review(monkeypatch):
    from app import voice_exam_final as final, voice_exam_core as core
    monkeypatch.setenv('VOICE_EXAM_SOURCE_MODE', 'claude_web')
    blocks = fetched(text='Checking your browser before accessing pmc.ncbi.nlm.nih.gov ...')
    blocks[1]['content']['content']['title'] = 'Checking your browser - reCAPTCHA'
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(blocks))
    monkeypatch.setattr(final, 'review', lambda *a, **k: pytest.fail('Blocked page must not enable final paid call'))
    with pytest.raises(core.VoiceError, match='Kaynaklara erişilemedi'):
        final.finalize({'fields': {'chief_complaint': {'value': 'Ağrı', 'quote': 'Ağrı'}},
                        'literature_topics': [{'topic': 'endo.general', 'quote': 'Ağrı'}]}, [])


def test_official_start_pages_are_server_owned_not_patient_urls(monkeypatch):
    calls = []
    def research(prompt, data, tools, **kwargs):
        calls.append(data)
        return response(fetched())
    monkeypatch.setattr(provider, 'research_message', research)
    web.retrieve_web([{'topic': 'oral_medicine.cancer', 'quote': 'PRIVATE',
                       'url': 'https://evil.example/PRIVATE'}])
    starts = calls[0]['topics'][0]['professional_start_urls']
    assert starts == ['https://www.ada.org/resources/ada-library/oral-health-topics/cancer-head-and-neck']
    assert 'PRIVATE' not in json.dumps(calls) and 'evil.example' not in json.dumps(calls)


@pytest.mark.parametrize('topic', ['oral_medicine.cancer', 'oral mucosal lesion diagnosis'])
def test_relevant_late_passage_is_not_lost_behind_page_navigation(monkeypatch, topic):
    # Native fetch can return one long text block rather than blank-line paragraphs.
    clinical = 'Persistent oral mucosal lesion or ulcer requires assessment and possible biopsy referral under this guideline.'
    text = ('Navigation home menu about contact ' * 700) + clinical + (' Footer links ' * 700)
    blocks = fetched(text=text)
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(blocks))
    result = web.retrieve_web([{'topic': topic, 'quote': 'PRIVATE PATIENT'}])
    excerpts = result['references'][0]['excerpts']
    assert any(clinical in excerpt for excerpt in excerpts)
    assert all(excerpt in text and len(excerpt) <= 1800 for excerpt in excerpts)


def test_specific_mapped_topic_avoids_unrelated_general_start_pages(monkeypatch):
    calls = []
    def research(prompt, data, tools, **kwargs):
        calls.append(data)
        return response(fetched())
    monkeypatch.setattr(provider, 'research_message', research)
    web.retrieve_web([{'topic': 'oral_medicine.general', 'quote': 'PRIVATE'},
                      {'topic': 'oral_medicine.cancer', 'quote': 'PRIVATE'}])
    rows = {topic['id']: topic for topic in calls[0]['topics']}
    assert rows['oral_medicine.general']['professional_start_urls'] == []
    assert len(rows['oral_medicine.cancer']['professional_start_urls']) == 1


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-no-network-key')
    pool = BoundedPool(2, 4, 'test-web')
    monkeypatch.setattr(web, '_pool', pool)
    monkeypatch.setattr(web, '_cache', OrderedDict())
    monkeypatch.setattr(web, '_inflight', {})
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(fetched()), raising=False)
    yield
    pool.shutdown()


def test_public_payload_and_native_tool_limits(monkeypatch):
    calls = []
    def research(prompt, data, tools, **kwargs):
        calls.append((prompt, data, tools, kwargs))
        return response(fetched())
    monkeypatch.setattr(provider, 'research_message', research)
    result = web.retrieve_web(TOPICS, [{'term': 'amoxicillin', 'quote': 'PRIVATE amoxicillin', 'query': 'LEAK'}])
    assert result['references'][0]['excerpts'][0] in TEXT
    payload = json.dumps(calls)
    assert 'PRIVATE' not in payload and 'LEAK' not in payload and '555' not in payload
    assert calls[0][1]['topics'][0]['id'] == 'endo.general'
    assert calls[0][1]['generic_drug_terms'] == ['amoxicillin']
    search, fetch = calls[0][2]
    assert search['type'] == 'web_search_20250305' and search['max_uses'] == 2
    assert fetch['type'] == 'web_fetch_20250910' and fetch['max_uses'] == 3
    assert fetch['max_content_tokens'] == 8000 and fetch['citations'] == {'enabled': True}
    assert search['allowed_domains'] == fetch['allowed_domains']
    assert calls[0][3]['timeout'] <= 45
    assert result['references'][0]['clinical_use'] is True
    assert result['references'][0]['evidence_level'] == 'professional_information'
    assert result['references'][0]['matched_topics'] == []


def test_empty_unknown_and_invalid_requests_make_no_call(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('No public concepts should cause no provider call')
    monkeypatch.setattr(provider, 'research_message', forbidden)
    for topics, requests in (([], []), ([{'topic': 'arbitrary private query'}], []), ([], [{'term': 'amoxicillin', 'quote': 'not spoken'}])):
        result = web.retrieve_web(topics, requests)
        assert not result['references']
        assert 'web-research-gap:no-public-concepts' in result['unavailable']


def test_generated_prose_and_search_snippets_are_not_evidence(monkeypatch):
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response([
        {'type': 'text', 'text': 'Invented professional evidence', 'citations': [{'url': URL, 'cited_text': 'invented'}]},
        {'type': 'web_search_tool_result', 'tool_use_id': 's', 'content': [{'url': URL, 'title': 'X', 'page_age': 'today', 'encrypted_content': 'opaque'}]}]))
    result = web.retrieve_web(TOPICS)
    assert result['references'] == []
    assert 'web-research-gap:no-fetched-evidence' in result['unavailable']


@pytest.mark.parametrize('url', ['http://www.ada.org/x', 'https://ada.org.evil.test/x', 'https://user@ada.org/x', 'https://ada.org:444/x', 'https://localhost/x', 'https://ada.org/' + 'a'*2048])
def test_unapproved_fetch_urls_rejected(monkeypatch, url):
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(fetched(url)))
    result = web.retrieve_web(TOPICS)
    assert not result['references'] and result['unavailable']


@pytest.mark.parametrize('mutation', ['unbound', 'mismatch', 'pdf', 'nonliteral'])
def test_provenance_and_unsupported_documents(monkeypatch, mutation):
    blocks = fetched()
    if mutation == 'unbound': blocks.pop(0)
    if mutation == 'mismatch': blocks[1]['content']['url'] = 'https://www.aae.org/other'
    if mutation == 'pdf': blocks[1]['content']['content']['source'] = {'type': 'base64', 'media_type': 'application/pdf', 'data': 'aaa'}
    if mutation == 'nonliteral': blocks[1]['content']['content']['source'] = {'type': 'url', 'url': URL}
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(blocks))
    result = web.retrieve_web(TOPICS)
    assert result['references'] == [] and result['unavailable']


def test_journal_is_unassessed_background(monkeypatch):
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(fetched('https://pubmed.ncbi.nlm.nih.gov/123/')))
    ref = web.retrieve_web(TOPICS)['references'][0]
    assert ref['clinical_use'] is False
    assert ref['evidence_level'] == 'unassessed_journal'
    assert 'quality' in ref['limitations'].lower()


def test_pause_preserves_blocks_and_reduces_global_budget(monkeypatch):
    first = [{'type': 'server_tool_use', 'id': 's1', 'name': 'web_search', 'input': {'query': 'endodontic complications'}}, *fetched()]
    snapshots = copy.deepcopy(first)
    calls = []
    def research(prompt, data, tools, **kwargs):
        calls.append((copy.deepcopy(tools), kwargs))
        return response(first, 'pause_turn') if len(calls) == 1 else response(fetched('https://www.aae.org/article', ident='f2'))
    monkeypatch.setattr(provider, 'research_message', research)
    result = web.retrieve_web(TOPICS)
    assert len(calls) == 2 and len(result['references']) == 2
    assert calls[1][0][0]['max_uses'] == 1 and calls[1][0][1]['max_uses'] == 2
    assert calls[1][1]['previous_messages'][-1] == {'role': 'assistant', 'content': snapshots}
    assert first == snapshots
    assert result['usage']['web_search_requests'] == 1
    assert result['usage']['web_fetch_requests'] == 2


def test_pause_never_exceeds_two_calls(monkeypatch):
    calls = []
    def research(*a, **k):
        calls.append(k)
        return response([], 'pause_turn')
    monkeypatch.setattr(provider, 'research_message', research)
    result = web.retrieve_web(TOPICS)
    assert len(calls) == 2
    assert 'unavailable' in ' '.join(result['unavailable'])


def test_http_200_error_block_is_explicit_unavailable(monkeypatch):
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response([
        {'type': 'web_search_tool_result', 'tool_use_id': 's1', 'content': {'type': 'web_search_tool_result_error', 'error_code': 'max_uses_exceeded'}}]))
    assert 'unavailable' in ' '.join(web.retrieve_web(TOPICS)['unavailable'])


def test_cache_copies_and_singleflight(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def research(*a, **k):
        calls.append(1); entered.set()
        assert release.wait(3)
        return response(fetched())
    monkeypatch.setattr(provider, 'research_message', research)
    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(web.retrieve_web, TOPICS)
        assert entered.wait(2)
        b = executor.submit(web.retrieve_web, TOPICS)
        release.set()
        left, right = a.result(), b.result()
    left['references'][0]['excerpts'].clear()
    assert right['references'][0]['excerpts']
    assert web.retrieve_web(TOPICS)['references'][0]['excerpts']
    assert len(calls) == 1


def test_excerpt_and_reference_limits(monkeypatch):
    blocks = []
    text = '\n\n'.join('Literal paragraph ' + str(n) + 'x'*1900 for n in range(30))
    for n in range(9): blocks.extend(fetched(URL + str(n), text=text, ident='f' + str(n)))
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(blocks))
    result = web.retrieve_web(TOPICS)
    assert len(result['references']) <= 6
    excerpts = [e for r in result['references'] for e in r['excerpts']]
    assert sum(map(len, excerpts)) <= 40000
    assert all(len(e) <= 1800 and e in text for e in excerpts)


def test_unconfigured_provider_fails_before_helper(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    def forbidden(*a, **k):
        pytest.fail('Unconfigured research must not call provider helper')
    monkeypatch.setattr(provider, 'research_message', forbidden)
    result = web.retrieve_web(TOPICS)
    assert result['references'] == []
    assert 'unavailable' in ' '.join(result['unavailable'])
    assert result['usage']['http_requests'] == 0


def test_pause_deadline_and_exhausted_tools_stop_continuation(monkeypatch):
    now = [10.0]
    monkeypatch.setattr(web.time, 'monotonic', lambda: now[0])
    calls = []
    def delayed(*a, **k):
        calls.append(k)
        now[0] += 46
        return response(fetched(), 'pause_turn')
    monkeypatch.setattr(provider, 'research_message', delayed)
    result = web.retrieve_web(TOPICS)
    assert len(calls) == 1 and result['unavailable']
    # A caller may time out before the worker publishes its partial result.
    with web._lock:
        pending = list(web._inflight.values())
    for future in pending:
        future.result(timeout=2)
    web._cache.clear()
    calls.clear()
    def exhausted(*a, **k):
        calls.append(k)
        value = response(fetched(), 'pause_turn')
        value['usage']['server_tool_use'] = {'web_search_requests': 2, 'web_fetch_requests': 3}
        return value
    monkeypatch.setattr(provider, 'research_message', exhausted)
    result = web.retrieve_web(TOPICS)
    assert len(calls) == 1 and result['usage']['web_search_requests'] == 2
    assert result['usage']['web_fetch_requests'] == 3


def test_failure_and_partial_cache_expire_earlier_than_success(monkeypatch):
    now, calls = [100.0], []
    monkeypatch.setattr(web.time, 'monotonic', lambda: now[0])
    def research(*a, **k):
        calls.append(1)
        return response()
    monkeypatch.setattr(provider, 'research_message', research)
    web.retrieve_web(TOPICS)
    now[0] += 14
    web.retrieve_web(TOPICS)
    assert len(calls) == 1
    now[0] += 2
    web.retrieve_web(TOPICS)
    assert len(calls) == 2
    web._cache.clear()
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(fetched(), 'max_tokens'))
    web.retrieve_web(TOPICS)
    assert next(iter(web._cache.values()))[0] == now[0] + 60
    web._cache.clear()
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(fetched()))
    web.retrieve_web(TOPICS)
    assert next(iter(web._cache.values()))[0] == now[0] + 3600


def test_only_actual_literal_citations_are_preferred(monkeypatch):
    blocks = fetched()
    blocks.append({'type': 'text', 'text': 'Prose is not evidence', 'citations': [
        {'url': URL, 'cited_text': 'fabricated claim'},
        {'url': URL, 'cited_text': 'literal professional information.'}]})
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(blocks))
    ref = web.retrieve_web(TOPICS)['references'][0]
    assert ref['excerpts'][0] == 'literal professional information.'
    assert 'fabricated claim' not in json.dumps(ref)


def test_public_topic_limit_and_cache_namespace(monkeypatch):
    calls = []
    def research(prompt, data, tools, **kwargs):
        calls.append(data)
        return response(fetched())
    monkeypatch.setattr(provider, 'research_message', research)
    topics = [{'topic': topic, 'quote': 'private'} for topic, _ in web.TOPICS]
    web.retrieve_web(topics)
    assert len(calls[0]['topics']) == 24
    monkeypatch.setenv('VOICE_EXAM_CLAUDE_MODEL', 'claude-another-model')
    web.retrieve_web(topics)
    assert len(calls) == 2
    assert len(web._cache) == 2


def test_capacity_failure_is_explicit(monkeypatch):
    monkeypatch.setattr(web._pool, 'submit', lambda *a: None)
    result = web.retrieve_web(TOPICS)
    assert not result['references']
    assert 'unavailable' in ' '.join(result['unavailable'])


def test_patient_names_never_become_public_generic_terms_and_markers_do_not_pollute_cache(monkeypatch):
    calls = []
    def research(prompt, data, tools, **kwargs):
        calls.append(copy.deepcopy(data))
        return response(fetched())
    monkeypatch.setattr(provider, 'research_message', research)
    mixed = [{'term': 'Cihan Akak', 'quote': 'Cihan Akak'},
             {'term': 'amoxicillin', 'quote': 'amoxicillin'}]
    result = web.retrieve_web(TOPICS, mixed)
    assert calls[0]['generic_drug_terms'] == ['amoxicillin']
    assert 'Cihan' not in json.dumps(calls)
    assert 'unverified-drug-name' in ' '.join(result['unavailable'])
    clean = web.retrieve_web(TOPICS, [mixed[1]])
    assert not clean['unavailable']
    assert len(calls) == 1


def test_malformed_tool_ids_still_consume_native_tool_budget(monkeypatch):
    calls = []
    def research(*a, **k):
        calls.append(1)
        blocks = [{'type': 'server_tool_use', 'name': name, 'input': {}}
                  for name in ['web_search']*2 + ['web_fetch']*3]
        return response(blocks, 'pause_turn')
    monkeypatch.setattr(provider, 'research_message', research)
    result = web.retrieve_web(TOPICS)
    assert len(calls) == 1
    assert result['usage']['web_fetch_requests'] == 3


def test_reported_budget_overrun_is_never_success(monkeypatch):
    value = response(fetched())
    value['usage']['server_tool_use'] = {'web_search_requests': 3, 'web_fetch_requests': 4}
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: value)
    assert 'unavailable' in ' '.join(web.retrieve_web(TOPICS)['unavailable'])


def test_native_character_citations_select_late_literal_document_text(monkeypatch):
    text = '\n\n'.join('Irrelevant introduction ' + str(i) for i in range(9)) + '\n\nRelevant late literal clinical passage.'
    blocks = fetched(text=text)
    blocks.append({'type': 'text', 'text': 'Do not use this prose', 'citations': [
        {'type': 'char_location', 'document_index': 0, 'start_char_index': text.index('Relevant'),
         'end_char_index': len(text), 'cited_text': 'Relevant late literal clinical passage.'}]})
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(blocks))
    ref = web.retrieve_web(TOPICS)['references'][0]
    assert ref['excerpts'][0] == 'Relevant late literal clinical passage.'


def test_document_citation_indices_include_unsupported_documents_and_later_pause_citations(monkeypatch):
    first = fetched('https://www.ada.org/unsupported', source={'type': 'base64', 'media_type': 'application/pdf', 'data': 'opaque'})
    text = '\n\n'.join('Irrelevant introduction ' + str(i) for i in range(9)) + '\n\nCorrect late cited passage.'
    first += fetched(text=text, ident='f2')
    later = [{'type': 'text', 'text': 'Prose', 'citations': [
        {'type': 'char_location', 'document_index': 0, 'cited_text': 'Wrong unverified quote'},
        {'type': 'char_location', 'document_index': 1, 'cited_text': 'Correct late cited passage.'}]}]
    replies = iter([response(first, 'pause_turn'), response(later)])
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: next(replies))
    ref = web.retrieve_web(TOPICS)['references'][0]
    assert ref['excerpts'][0] == 'Correct late cited passage.'


def test_completed_gaps_are_not_transport_failures(monkeypatch):
    from app.voice_exam_sources import retryable_unavailable
    assert not retryable_unavailable(web.retrieve_web([], [])['unavailable'])
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response())
    assert not retryable_unavailable(web.retrieve_web(TOPICS)['unavailable'])


def test_unsupported_pdf_and_unknown_generic_are_permanent_gaps(monkeypatch):
    from app.voice_exam_sources import retryable_unavailable
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: response(fetched(
        source={'type': 'base64', 'media_type': 'application/pdf', 'data': 'aaa'})))
    result = web.retrieve_web(TOPICS, [{'term': 'private unknown', 'quote': 'private unknown'}])
    assert result['references'] == []
    assert not retryable_unavailable(result['unavailable'])


def test_real_provider_failure_is_still_retryable(monkeypatch):
    from app.voice_exam_sources import retryable_unavailable
    def fail(*a, **k):
        raise TimeoutError('synthetic timeout')
    monkeypatch.setattr(provider, 'research_message', fail)
    assert retryable_unavailable(web.retrieve_web(TOPICS)['unavailable'])


@pytest.mark.parametrize('topic', sorted(topic for topic, _ in web.TOPICS))
def test_every_registered_topic_reaches_native_research_without_patient_words(monkeypatch, topic):
    sent = []
    def research(prompt, data, tools, **kwargs):
        sent.append(copy.deepcopy(data))
        return response(fetched())
    monkeypatch.setattr(provider, 'research_message', research)
    private = 'PRIVATE_PATIENT_WORDS_AND_IDENTITY'
    output = web.retrieve_web([{'topic': topic, 'quote': private, 'query': private}])
    assert len(sent) == 1
    assert sent[0]['topics'][0]['id'] == topic
    assert sent[0]['topics'][0]['scope']
    assert private not in json.dumps(sent)
    assert output['references'][0]['excerpts'][0] in TEXT
    # A transport/provenance check never certifies a topic or clinical conclusion.
    assert output['references'][0]['matched_topics'] == []
