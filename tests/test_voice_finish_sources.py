import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from app import voice_exam_core as core
from app import voice_exam_literature as literature
from app import voice_exam_sources as sources


def test_specific_endodontic_topics_are_closed_and_need_original_evidence():
    quote = 'Eğe kanalda ayrıldı.'
    topic = {'topic': 'endo.instrument_separation', 'quote': quote}
    assert topic['topic'] in core.schema()['properties']['literature_topics']['items']['properties']['topic']['enum']
    result = core.normalize({'transcript': quote, 'literature_topics': [topic]}, evidence=quote)
    assert result['literature_topics'] == [topic]
    assert not core.normalize({'transcript': quote, 'literature_topics': [topic]}, evidence='İyiyim.')['literature_topics']
    with pytest.raises(core.VoiceError):
        core.clinical_context({'literature_topics': [{'topic': 'arbitrary generated search', 'quote': quote}]})


def test_endodontic_topic_maps_to_fixed_scientific_query(monkeypatch):
    seen = []
    literature._cache.clear()
    monkeypatch.setattr(literature, '_get', lambda utility, params: seen.append(params) or b'{"esearchresult":{"idlist":[]}}')
    literature.retrieve_literature('', topics=[{'topic': 'endo.instrument_separation', 'quote': 'PRIVATE_PHRASE'}])
    assert 'instrument separation' in seen[0]['term']
    assert 'PRIVATE' not in json.dumps(seen)


def test_local_index_returns_full_abstract_without_network_and_reports_missing(tmp_path, monkeypatch):
    from app import voice_literature_index as index
    path = tmp_path / 'literature.sqlite'
    monkeypatch.setenv('VOICE_LITERATURE_MODE', 'local')
    monkeypatch.setenv('VOICE_LITERATURE_DB', str(path))
    monkeypatch.setattr(literature, '_get', lambda *a: pytest.fail('Local retrieval must not call PubMed'))
    topics = [{'topic': 'endo.instrument_separation', 'quote': 'Private patient speech'}]
    assert literature.retrieve_literature('PRIVATE', topics)[1] == ['literature-index-unavailable']
    abstract = 'Background. ' * 200 + 'Important results and limitations at the end.'
    ref = {'id': 'pubmed-123', 'title': 'Instrument separation', 'institution': 'PubMed',
           'url': 'https://pubmed.ncbi.nlm.nih.gov/123/', 'excerpts': [abstract],
           'clinical_use': True, 'evidence_level': 'systematic_review', 'publication_year': 2026,
           'matched_topics': ['endo.instrument_separation']}
    index.publish(path, [ref])
    refs, missing = literature.retrieve_literature('PRIVATE', topics)
    assert not missing and refs[0]['excerpts'] == [abstract]
    assert literature.retrieve_literature('', [{'topic': 'fake'}])[1] == ['literature-topic-unsupported']
    index.publish(path, [])
    assert literature.retrieve_literature('', topics)[1] == ['literature:endo.instrument_separation']


def test_source_budget_preserves_short_later_sources_and_cached_objects():
    refs = [{'id': 'large', 'excerpts': ['a' * 30000, 'b' * 15000]}, {'id': 'short', 'excerpts': ['c' * 100]}]
    result = sources._apply_budget(refs)
    assert sum(len(x) for r in result for x in r['excerpts']) <= 40000
    assert any(r['id'] == 'short' for r in result)
    assert refs[0]['excerpts'][1] == 'b' * 15000


def test_document_failures_are_cached_and_shared_inflight(monkeypatch):
    sources._cache.clear()
    started = threading.Event(); release = threading.Event(); calls = []
    def fetch(doc):
        calls.append(doc[0]); started.set(); release.wait(2)
        raise TimeoutError()
    monkeypatch.setattr(sources, '_fetch', fetch)
    monkeypatch.setattr(sources, 'DOCUMENT_TIMEOUT', .04)
    doc = sources.DOCUMENTS[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(sources._fetch_many, [doc]); assert started.wait(1)
        second = pool.submit(sources._fetch_many, [doc])
        assert first.result()[1] == [doc[0]]
        assert second.result()[1] == [doc[0]]
        assert calls == [doc[0]], 'Deadline must not create duplicate outstanding network requests'
        release.set()
    for _ in range(100):
        if not sources._inflight: break
        time.sleep(.002)
    assert sources._fetch_many([doc])[1] == [doc[0]]
    assert calls == [doc[0]], 'Negative cache suppresses repeated failures'


def test_pending_source_work_has_a_hard_admission_limit():
    from app.voice_source_pool import BoundedPool
    gate = threading.Event()
    pool = BoundedPool(1, 2, 'test-source')
    first = pool.submit(lambda: gate.wait(1))
    second = pool.submit(lambda: None)
    assert pool.submit(lambda: None) is None
    assert second.cancel()
    gate.set(); first.result()
    pool.shutdown()


def test_final_prompt_budget_rejects_before_provider_call(monkeypatch):
    from app import voice_exam_final as final
    ref = {'id': 'huge', 'excerpts': ['a' * 81000]}
    monkeypatch.setattr(final, 'retrieve', lambda *a, **k: {'references': [ref], 'unavailable': []})
    monkeypatch.setattr(final, 'review', lambda *a: pytest.fail('Over-budget prompt must not reach provider'))
    with pytest.raises(core.VoiceError, match='uzun'):
        final.finalize({'fields': {'chief_complaint': {'value': 'Ağrı', 'quote': 'Ağrı'}}}, [])


def test_expired_negative_cache_can_recover_before_success_cache_ttl(monkeypatch):
    sources._cache.clear()
    doc = sources.DOCUMENTS[0]
    sources._cache[doc[0]] = (time.monotonic() - 601, None)
    class Response:
        headers = {'Content-Type': 'text/html'}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, *a): return b'<p>Drug interaction guidance: prescribe carefully and check interaction warnings.</p>'
    class Opener:
        def open(self, *a, **k): return Response()
    monkeypatch.setattr(sources.urllib.request, 'build_opener', lambda *a: Opener())
    assert sources._fetch(doc)['excerpts']


def test_local_mode_preserves_closed_keyword_fallback(monkeypatch):
    from app import voice_literature_index as index
    captured = []
    monkeypatch.setenv('VOICE_LITERATURE_MODE', 'local')
    monkeypatch.setattr(index, 'retrieve', lambda topics: captured.extend(topics) or ([], ['test-missing']))
    literature.retrieve_literature('PRIVATE_NAME kanal tedavisi')
    assert {'topic': 'endodontic diagnosis'} in captured
    assert 'PRIVATE_NAME' not in json.dumps(captured)


def test_total_source_outage_does_not_charge_for_final_review(monkeypatch):
    from app import voice_exam_final as final
    monkeypatch.setattr(final, 'retrieve', lambda *a, **k: {'references': [], 'unavailable': ['pubmed-unavailable']})
    monkeypatch.setattr(final, 'review', lambda *a: pytest.fail('Source outage should be retryable before the final model call'))
    with pytest.raises(core.VoiceError, match='Kaynak'):
        final.finalize({'fields': {'chief_complaint': {'value': 'Ağrı', 'quote': 'Ağrı'}}}, [])


def test_retryable_source_status_distinguishes_no_evidence_from_network_failure():
    assert sources.retryable_unavailable(['pubmed-search-unavailable:endodontic diagnosis'])
    assert sources.retryable_unavailable(['group:documents'])
    assert sources.retryable_unavailable(['ada-pain-guideline'])
    assert sources.retryable_unavailable(['drug:warfarin'])
    assert not sources.retryable_unavailable(['pubmed-no-match:endodontic diagnosis', 'source-text-budget'])


def test_unchanged_source_retry_does_not_call_final_model_again(monkeypatch):
    from app import voice_exam_final as final
    from test_voice_exam_final import provider, CONTEXT
    calls = provider(monkeypatch, {'questions': [], 'contradictions': [], 'clinical_items': []})
    evidence = {'references': [{'id': 'test', 'excerpts': ['Public evidence'], 'retrieved_at': 'first'}],
                'unavailable': ['ada-pain-guideline'], 'coverage': 'limited', 'notice': 'Partial'}
    monkeypatch.setattr(final, 'retrieve', lambda *a, **k: evidence)
    first = final.finalize(CONTEXT, [])
    assert first['review_status']['source_retryable']
    evidence['references'][0]['retrieved_at'] = 'later'
    second = final.finalize(CONTEXT, [], previous_source_fingerprint=first['source_fingerprint'])
    assert second['not_modified'] is True
    assert len(calls) == 1, 'Re-reading identical evidence must not incur another final model call'
    changed = {**CONTEXT, 'fields': {**CONTEXT['fields'], 'chief_complaint': {'value': 'Yeni ağrı', 'quote': 'Yeni ağrı'}}}
    assert not final.finalize(changed, [], previous_source_fingerprint=first['source_fingerprint']).get('not_modified')
    assert len(calls) == 2, 'A source fingerprint must not reuse review for changed clinical context'
