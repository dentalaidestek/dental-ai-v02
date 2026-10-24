import json
from types import SimpleNamespace

import pytest

from app import voice_exam_core as core
from app import voice_exam_live_sources as live
from test_voice_drug_sources import XML
from test_voice_exam import app_client


def test_lookup_fetches_official_document_and_caches_only_drug_data(monkeypatch):
    live._cache.clear(); calls = []
    def read(path, limit):
        calls.append(path)
        if path.startswith('services/v2/spls.json?'):
            return json.dumps({'data': [{'setid': '11111111-1111-1111-1111-111111111111', 'title': 'TESTDRUG TABLET'}]}).encode()
        return XML
    monkeypatch.setattr(live, '_read', read)
    result = live.lookup('testdrug')
    assert result['version'] == '2' and result['excerpts']
    assert live.lookup('testdrug') == result and len(calls) == 2
    assert 'drug_name=testdrug' in calls[0]
    assert 'transcript' not in json.dumps(live._cache) and 'patient' not in json.dumps(live._cache)


@pytest.mark.parametrize('term', ['https://evil.example', 'test@patient.com', '12345678901', 'x' * 81])
def test_source_lookup_rejects_urls_identifiers_and_unbounded_terms(term):
    with pytest.raises(ValueError): live.lookup(term)


def test_lookup_refuses_combination_substitution_and_wrong_document_identity(monkeypatch):
    live._cache.clear()
    monkeypatch.setattr(live, '_read', lambda *a: json.dumps({'data': [{'title': 'TESTDRUG AND OTHERDRUG'}]}).encode())
    with pytest.raises(ValueError, match='unambiguous'): live.lookup('testdrug')
    def wrong(path, limit):
        return (json.dumps({'data': [{'setid': '22222222-2222-2222-2222-222222222222', 'title': 'TESTDRUG'}]}).encode()
                if path.startswith('services/v2/spls.json?') else XML)
    monkeypatch.setattr(live, '_read', wrong)
    with pytest.raises(ValueError, match='identity'): live.lookup('testdrug')


def test_excess_or_failed_lookups_are_reported_as_uncovered(monkeypatch):
    monkeypatch.setattr(live, 'lookup', lambda term: {'id': term})
    found, missing = live.retrieve_requests([{'term': t} for t in ('one', 'two', 'three', 'four')])
    assert len(found) == 3 and missing == ['drug:four']


def test_source_requests_require_actual_quote_and_spoken_drug_term():
    data = core.normalize({'transcript': 'Naproksen kullanıyorum.', 'source_requests': [
        {'term': 'naproksen', 'quote': 'Naproksen kullanıyorum.'},
        {'term': 'naproxen', 'quote': 'Naproksen kullanıyorum.'},
        {'term': 'naproxen', 'quote': 'Uydurma'}, {'term': 'https://evil.example', 'quote': 'Naproksen kullanıyorum.'}]})
    assert data['source_requests'] == [{'term': 'naproksen', 'quote': 'Naproksen kullanıyorum.'}]


def test_device_check_requires_clinician_and_never_calls_provider(app_client, monkeypatch):
    from app import main
    from fastapi.responses import JSONResponse
    client, _ = app_client
    monkeypatch.setattr(main, 'templates', SimpleNamespace(TemplateResponse=lambda **kw: JSONResponse({'page': kw['name']})), raising=False)
    assert client.get('/voice-exams/device-check').json()['page'] == 'voice_exam_device_check.html'
    assert client.get('/voice-exams/device-check', headers={'x-role': 'PATIENT'}, follow_redirects=False).status_code == 303


def test_audio_packet_preserves_long_context_without_headers_or_disk(app_client, monkeypatch):
    client, _ = app_client
    captured = {}
    def extract(**kw):
        captured.update(kw)
        return {'transcript': 'Sentetik', 'fields': {}, 'teeth': [], 'uncertain': ''}
    monkeypatch.setattr(core, 'extract', extract)
    context = {'fields': {'medical_history': {'value': 'x' * 2900, 'quote': 'a'},
                          'medications': {'value': 'y' * 2900, 'quote': 'b'},
                          'allergies': {'value': 'z' * 2900, 'quote': 'c'}}}
    metadata = json.dumps(context).encode()
    audio = b'\x1aE\xdf\xa3' + b'x' * 100
    packet = len(metadata).to_bytes(4, 'big') + metadata + audio
    result = client.post('/patients/1/voice-exam/audio', content=packet, headers={
        'Content-Type': 'application/vnd.dentalai.voice-packet', 'X-Voice-Mime': 'audio/webm', 'X-Voice-Consent': 'yes'})
    assert result.status_code == 200 and captured['data'] == audio
    assert len(captured['context']['fields']) == 3


@pytest.mark.parametrize('packet', [b'', b'\x00\x00\xff\xff{}audio', b'\x00\x00\x00\x05{}'])
def test_malformed_audio_packet_does_not_call_provider(app_client, monkeypatch, packet):
    client, _ = app_client
    monkeypatch.setattr(core, 'extract', lambda **kw: pytest.fail('Malformed input reached provider'))
    assert client.post('/patients/1/voice-exam/audio', content=packet, headers={
        'Content-Type': 'application/vnd.dentalai.voice-packet', 'X-Voice-Mime': 'audio/webm', 'X-Voice-Consent': 'yes'}).status_code == 422
