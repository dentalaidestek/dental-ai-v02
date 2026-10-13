"""Separate provider waits from local capacity/cleanup without logging content."""
import json
import logging
from contextlib import contextmanager, nullcontext
from unittest.mock import Mock

import pytest
import app.study_provider as providers


def setup_provider(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(providers.time, 'perf_counter', lambda: now[0])
    monkeypatch.setattr(providers, 'router_target_available', lambda *args: True)
    monkeypatch.setattr(providers, 'record_api_result', lambda **kwargs: None)
    provider = providers.GeminiStudyProvider()
    provider.api_key, provider.max_attempts = 'PRIVATE-KEY', 1
    return provider, now


def test_json_timing_separates_capacity_headers_body_and_cleanup(monkeypatch, caplog):
    provider, now = setup_provider(monkeypatch)
    @contextmanager
    def reservation(*args):
        now[0] += 30
        try:
            yield
        finally:
            now[0] += .3
    monkeypatch.setattr(providers, 'provider_reservation', reservation)
    response = Mock(status=200, headers={})
    def read():
        now[0] += .1
        return json.dumps({'candidates':[{'content':{'parts':[{'text':'PRIVATE-ANSWER'}]}}],
            'usageMetadata':{'promptTokenCount':42,'thoughtsTokenCount':7,
                             'candidatesTokenCount':'PRIVATE-TEXT'}}).encode()
    response.read.side_effect = read
    def open_request(*args, **kwargs):
        now[0] += 1
        return nullcontext(response)
    http = Mock(side_effect=open_request)
    monkeypatch.setattr(providers, 'urlopen', http)
    def ledger(**kwargs):
        now[0] += .2
    monkeypatch.setattr(providers, 'record_api_result', ledger)
    with caplog.at_level(logging.INFO):
        assert provider.generate(model='test-model', system_prompt='PRIVATE-SYSTEM',
            history=[], prompt='PRIVATE-QUESTION') == 'PRIVATE-ANSWER'
    http.assert_called_once()
    log = next(record.message for record in caplog.records if 'Gemini timing' in record.message)
    assert "'reservation': 30000" in log and "'headers': 1000" in log
    assert "'body': 100" in log and "'ledger': 200" in log and "'release': 300" in log
    assert 'total_ms=31600' in log and "'thoughtsTokenCount': 7" in log
    assert not any(private in log for private in ['PRIVATE-KEY','PRIVATE-SYSTEM',
        'PRIVATE-QUESTION','PRIVATE-ANSWER','PRIVATE-TEXT'])


def test_stream_timing_distinguishes_first_text_finish_event_and_delayed_eof(monkeypatch, caplog):
    provider, now = setup_provider(monkeypatch)
    monkeypatch.setattr(providers, 'provider_reservation', lambda *args: nullcontext())
    response = Mock(status=200, headers={})
    def events():
        now[0] += 2
        yield b'data: {"candidates":[{"content":{"parts":[{"text":"PRIVATE-ANSWER"}]}}]}\n'
        now[0] += .01
        yield b'data: {"candidates":[{"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":12}}\n'
        now[0] += 30
    response.__iter__ = Mock(side_effect=events)
    def open_request(*args, **kwargs):
        now[0] += 1
        return nullcontext(response)
    http = Mock(side_effect=open_request)
    monkeypatch.setattr(providers, 'urlopen', http)
    with caplog.at_level(logging.INFO):
        assert ''.join(provider.generate_stream(model='test-model',system_prompt='PRIVATE-SYSTEM',
            history=[],prompt='PRIVATE-QUESTION')) == 'PRIVATE-ANSWER'
    http.assert_called_once()
    log = next(record.message for record in caplog.records if 'Gemini timing' in record.message)
    assert 'first_text_ms=3000' in log and 'finish_event_ms=3010' in log
    assert "'stream': 32010" in log and 'total_ms=33010' in log
    assert 'PRIVATE-' not in log and provider.last_finish_reason == 'STOP'


def test_timeout_timing_retains_failed_phase_and_single_attempt(monkeypatch, caplog):
    import urllib.error
    provider, now = setup_provider(monkeypatch)
    monkeypatch.setattr(providers, 'provider_reservation', lambda *args: nullcontext())
    def open_request(*args, **kwargs):
        now[0] += 45
        raise urllib.error.URLError('ReadTimeoutError')
    http = Mock(side_effect=open_request)
    monkeypatch.setattr(providers, 'urlopen', http)
    with caplog.at_level(logging.INFO), pytest.raises(providers.StudyProviderError) as error:
        provider.generate(model='test-model',system_prompt='PRIVATE-SYSTEM',history=[],prompt='PRIVATE-QUESTION')
    http.assert_called_once()
    assert error.value.__cause__.reason == 'ReadTimeoutError'
    log = next(record.message for record in caplog.records if 'Gemini timing' in record.message)
    assert "'headers': 45000" in log and 'PRIVATE-' not in log


def test_phase_timings_follow_uvicorn_level_when_root_filters_info(caplog):
    with caplog.at_level(logging.WARNING), caplog.at_level(logging.INFO, logger='uvicorn.error'):
        timing = providers._GeminiTiming(model='test-model', operation='generation',
            mode='json', input_bytes=1, structured=True)
        timing.finish()
    assert any(record.name == 'uvicorn.error.gemini_timing'
        and 'Gemini timing' in record.message for record in caplog.records)
