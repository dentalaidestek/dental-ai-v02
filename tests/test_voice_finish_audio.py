import json
from contextlib import nullcontext
from types import ModuleType
import sys

from test_voice_exam import app_client
from app import voice_exam_core as core


def test_transcription_only_audio_never_calls_clinical_model(monkeypatch):
    import app.http_transport as transport
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-test-key')
    monkeypatch.setenv('VOICE_EXAM_GEMINI_MODEL', 'gemini-test')
    module = ModuleType('app.provider_budget');module.reservation = lambda *a: nullcontext()
    monkeypatch.setitem(sys.modules, 'app.provider_budget', module)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, *a):
            return json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
                {'text': json.dumps({'transcript': 'Hekim: Perforasyon şüphesi var.'})}]}}]}).encode()
    monkeypatch.setattr(transport, 'urlopen', lambda *a, **k: Response())
    monkeypatch.setattr(core, '_understand', lambda *a: (_ for _ in ()).throw(AssertionError('Clinical model must wait for Finish')))
    result = core.extract(data=b'\x1aE\xdf\xa3' + b'x' * 100, mime='audio/webm', transcription_only=True)
    assert result == {'transcript': 'Hekim: Perforasyon şüphesi var.'}


def test_audio_endpoint_explicit_transcription_mode_and_consent(app_client, monkeypatch):
    client, _ = app_client
    seen = []
    monkeypatch.setattr(core, 'extract', lambda **kw: seen.append(kw) or {'transcript': 'Görüşme.'})
    data = b'\x1aE\xdf\xa3' + b'x' * 100
    headers = {'content-type': 'audio/webm', 'x-voice-transcription-only': 'yes'}
    assert client.post('/patients/1/voice-exam/audio', content=data, headers=headers).status_code == 400
    headers['x-voice-consent'] = 'yes'
    result = client.post('/patients/1/voice-exam/audio', content=data, headers=headers)
    assert result.status_code == 200
    assert result.json()['transcript'] == 'Görüşme.'
    assert seen[0]['transcription_only'] is True
    assert 'review' not in result.json()


def test_source_retry_fingerprint_is_validated_and_forwarded_after_access(app_client, monkeypatch):
    from app import voice_exam_final as final
    client, _ = app_client
    calls = []
    monkeypatch.setattr(final, 'finalize', lambda *a, **kw: calls.append(kw) or {'not_modified': True})
    body = {'context': {}, 'consent': True, 'source_fingerprint': 'invalid'}
    assert client.post('/patients/1/voice-exam/finalize', json=body).status_code == 422
    body['source_fingerprint'] = 'f' * 64
    assert client.post('/patients/2/voice-exam/finalize', json=body).status_code == 404
    assert not calls
    assert client.post('/patients/1/voice-exam/finalize', json=body).status_code == 200
    assert calls == [{'request_scope': (1, 1), 'previous_source_fingerprint': 'f' * 64}]
