"""Synthetic saturation checks; no network, providers or clinical accuracy claim."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, OrderedDict
import threading
import time

import pytest


@pytest.fixture(autouse=True)
def isolated_source_state(monkeypatch):
    from app import voice_exam_sources as sources
    from app.voice_source_pool import BoundedPool

    documents = BoundedPool(6, 12, 'test-voice-document')
    groups = BoundedPool(4, 8, 'test-voice-source')
    monkeypatch.setattr(sources, '_cache', OrderedDict())
    monkeypatch.setattr(sources, '_inflight', {})
    monkeypatch.setattr(sources, '_doc_pool', documents)
    monkeypatch.setattr(sources, '_group_pool', groups)
    try:
        yield
    finally:
        # Drain group work before document work, while patches are still active.
        groups.shutdown()
        documents.shutdown()


@pytest.mark.parametrize('concurrency', [1, 5, 20])
def test_simultaneous_reviews_share_bounded_document_work_and_report_capacity(monkeypatch, concurrency):
    from app import voice_exam_sources as sources
    from app import voice_exam_literature, voice_exam_dergipark, voice_exam_drugs
    lock = threading.Lock();active = 0;peak = 0;calls = Counter()
    def fetch(document):
        nonlocal active, peak
        with lock:
            active += 1;peak = max(peak, active);calls[document[0]] += 1
        try:
            time.sleep(.02)
            return {'id': document[0], 'excerpts': ['Public source paragraph. ' * 80]}
        finally:
            with lock: active -= 1
    monkeypatch.setattr(sources, '_fetch', fetch)
    monkeypatch.setattr(voice_exam_literature, 'retrieve_literature', lambda *a, **kw: ([], []))
    monkeypatch.setattr(voice_exam_dergipark, 'retrieve_dergipark', lambda *a, **kw: ([], []))
    monkeypatch.setattr(voice_exam_drugs, 'retrieve_drugs', lambda *a, **kw: [])
    query = 'ilaç statin communication needs ağrı apse çürük gebe tansiyon diyabet profilaksi warfarin bifosfonat'
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda _: sources.retrieve(query), range(concurrency)))
    assert 0 < peak <= 6
    assert calls and max(calls.values()) == 1, 'Overlapping reviews must share one document fetch per ID'
    for result in results:
        assert result['references'] or result['unavailable'], 'Capacity rejection cannot look like completed empty evidence'
        assert sum(len(text) for ref in result['references'] for text in ref['excerpts']) <= 40000
    assert active == 0
