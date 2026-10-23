import json
import sys
from contextlib import nullcontext
from types import ModuleType

import pytest
from sqlmodel import Session

from app import voice_exam_core as core
from app import voice_exam_final as final
from test_voice_exam import app_client, payload


CONTEXT = {'fields': {'chief_complaint': {'value': 'Soğukta ağrı', 'quote': 'Soğuk içemiyorum.'},
                      'medications': {'value': 'Warfarin', 'quote': 'Warfarin kullanıyorum.'}}}


def provider(monkeypatch, result, finish='STOP'):
    import app.http_transport as transport
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-test-secret')
    monkeypatch.setenv('VOICE_EXAM_GEMINI_MODEL', 'gemini-test')
    module = ModuleType('app.provider_budget'); module.reservation = lambda *args: nullcontext()
    monkeypatch.setitem(sys.modules, 'app.provider_budget', module)
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            return json.dumps({'candidates': [{'finishReason': finish, 'content': {
                'parts': [{'text': json.dumps(result)}]}}]}).encode()
    def request(req, **options):
        calls.append(json.loads(req.data)); return Response()
    monkeypatch.setattr(transport, 'urlopen', request)
    monkeypatch.setattr(final, 'retrieve', lambda q: {'references': [], 'unavailable': [], 'coverage': 'limited', 'notice': 'limited'})
    return calls


def test_one_final_call_covers_entire_context_and_excludes_identity_and_coaching(monkeypatch):
    result = {'summary': [{'field': 'chief_complaint', 'quote': 'Soğukta', 'text': 'Soğukta ağrı beyanı'}],
              'questions': [{'field': 'chief_complaint', 'quote': 'Soğukta', 'text': 'Ne zamandır?'}],
              'contradictions': [], 'clinical_items': []}
    calls = provider(monkeypatch, result)
    context = {**CONTEXT, 'fields': {**CONTEXT['fields'], 'first_name': {'value': 'PRIVATE_NAME', 'quote': 'PRIVATE_NAME'}}}
    output = final.finalize(context, [{'quote': 'PRIVATE_QUOTE', 'observation': 'PRIVATE_COACHING'}])
    assert output['summary'][0] == result['summary'][0] and output['questions'] == result['questions']
    assert {item['field'] for item in output['summary']} == set(CONTEXT['fields'])
    assert len(calls) == 1
    submitted = calls[0]['contents'][0]['parts'][0]['text']
    assert 'Warfarin' in submitted and 'chief_complaint' in submitted
    assert 'PRIVATE_' not in submitted and 'transcript' not in json.loads(submitted)


def test_fabricated_final_anchor_is_rejected(monkeypatch):
    calls = provider(monkeypatch, {'summary': [{'field': 'allergies', 'quote': 'penisilin', 'text': 'Uydurma'}],
        'questions': [], 'contradictions': [], 'clinical_items': []})
    summary = final.finalize(CONTEXT, [])['summary']
    assert summary and all(item['text'] != 'Uydurma' for item in summary)
    assert all(item['quote'] in CONTEXT['fields'][item['field']]['value'] for item in summary)
    assert len(calls) == 1


def test_partial_final_response_is_not_success(monkeypatch):
    provider(monkeypatch, {}, finish='MAX_TOKENS')
    with pytest.raises(core.VoiceError, match='tamamlanamadı'):
        final.finalize(CONTEXT, [])


def test_text_quotes_are_anchored_to_original_input_not_model_transcript():
    model = {'transcript': 'Penisilin alerjim var.', 'fields': {
        'allergies': {'value': 'Penisilin alerjisi', 'quote': 'Penisilin alerjim var.'}}}
    assert not core.normalize(model, evidence='Soğuk içemiyorum.')['fields']


def test_in_session_questions_require_original_evidence():
    output = core.normalize({'transcript': 'Şekerim var.', 'follow_up_questions': [
        {'quote': 'Şekerim var.', 'question': 'Güncel ilaçlarınız neler?', 'reason': 'Beyanı netleştir', 'priority': 'CLARIFY_NOW'},
        {'quote': 'Uydurma', 'question': 'Geçersiz', 'reason': '', 'priority': 'CLARIFY_NOW'}]}, evidence='Şekerim var.')
    assert len(output['follow_up_questions']) == 1


def test_longer_but_bounded_clinical_context():
    context = {'fields': {k: {'value': 'a' * 2000, 'quote': 'b' * 100} for k in core.FIELDS}}
    assert len(core.clinical_context(context)['fields']) == 9
    context['teeth'] = [{'tooth': '11', 'status': 'CARIES', 'quote': 'c' * 1500}] * 10
    with pytest.raises(core.VoiceError): core.clinical_context(context)


def test_final_endpoint_access_consent_and_no_record_write(app_client, monkeypatch):
    client, engine = app_client
    monkeypatch.setattr(final, 'finalize', lambda *args: {'summary': [], 'questions': [], 'contradictions': []})
    assert client.post('/patients/2/voice-exam/finalize', json={'context': CONTEXT, 'consent': True}).status_code == 404
    assert client.post('/patients/1/voice-exam/finalize', json={'context': CONTEXT}).status_code == 400
    assert client.post('/patients/1/voice-exam/finalize', json={'context': CONTEXT, 'consent': True}).status_code == 200
    assert client.post('/patients/1/voice-exam/finalize', headers={'x-role': 'PATIENT'}, json={'context': CONTEXT, 'consent': True}).status_code == 401


def test_history_is_owner_scoped_and_only_contains_explicitly_saved_fields(app_client):
    client, engine = app_client
    assert client.get('/patients/2/voice-exam/history').status_code == 404
    assert client.get('/patients/1/voice-exam/history').json()['fields'] == {}
    assert client.post('/patients/1/voice-exam/apply', json=payload(engine, fields={
        'medications': 'Hasta Warfarin kullandığını söylüyor', 'allergies': 'Bilmiyor',
        'clinical_findings': 'Muayene notu; özel kayıt aktarılmamalı'})).status_code == 200
    fields = client.get('/patients/1/voice-exam/history').json()['fields']
    assert set(fields) == {'medications', 'allergies'}
    assert fields['allergies']['value'] == 'Bilmiyor'
    assert 'Muayene notu' not in json.dumps(fields)


def test_spoken_appointment_requires_explicit_time_of_day():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime(2026, 10, 22, 10, 0, tzinfo=ZoneInfo('Europe/Istanbul'))
    assert core.resolve_appointment('Yarın öğleden sonra saat üçte gelin.', 'Tamam.', now) == '2026-10-23T15:00'
    assert core.resolve_appointment('Yarın saat on beşte gelin.', 'Tamam.', now) == '2026-10-23T15:00'
    assert core.resolve_appointment('Yarın saat üçte gelin.', 'Tamam.', now) is None
    assert core.resolve_appointment('Yarın sabah saat sekizde gelin.', 'Belki.', now) is None


def test_omitted_previous_field_is_preserved_but_explicit_retraction_is_respected(monkeypatch):
    import app.http_transport as transport
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-test-secret')
    module = ModuleType('app.provider_budget'); module.reservation = lambda *args: nullcontext()
    monkeypatch.setitem(sys.modules, 'app.provider_budget', module)
    response = {'transcript': 'Yanlış anlaşıldı.', 'fields': {}, 'removed_fields': []}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            return json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(response)}]}}]}).encode()
    monkeypatch.setattr(transport, 'urlopen', lambda *args, **kw: Response())
    context = {'fields': {'allergies': {'value': 'Belirsiz alerji', 'quote': 'Alerjim var.'}}}
    assert 'allergies' in core.extract(transcript='Yanlış anlaşıldı.', context=context)['fields']
    response['removed_fields'] = [{'name': 'allergies', 'quote': 'Yanlış anlaşıldı.'}]
    assert 'allergies' not in core.extract(transcript='Yanlış anlaşıldı.', context=context)['fields']


def test_concurrent_tooth_update_invalidates_save_revision(app_client):
    from test_voice_exam import ToothStatus
    client, engine = app_client
    data = payload(engine)
    with Session(engine) as session:
        session.add(ToothStatus(patient_id=1, tooth_number='44', status='FILLING'))
        session.commit()
    assert client.post('/patients/1/voice-exam/apply', json=data).status_code == 409


def test_rendered_entry_and_finish_controls_are_present():
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from types import SimpleNamespace
    env = Environment(loader=FileSystemLoader('app/templates'), autoescape=select_autoescape())
    user = SimpleNamespace(role='DOCTOR')
    request = SimpleNamespace(url=SimpleNamespace(path='/voice-exams'))
    entry = env.get_template('voice_exam_entry.html').render(user=user, request=request, q='<script>', patients=[])
    assert '&lt;script&gt;' in entry and 'Yeni hasta ile devam et' in entry
    panel = env.get_template('voice_exam_panel.html').render(patient=SimpleNamespace(id=7))
    assert 'data-voice-finalize' in panel and 'data-voice-final-results' in panel
    assert 'data-voice-history-confirm' in panel and 'data-voice-save disabled' in panel


@pytest.mark.parametrize('quote,acceptance,expected', [
    ("Yarın öğleden sonra 3.30'da kontrole gelebilir misiniz?", "Yarın 15.30'da gelirim, tamam hocam.", '2026-10-23T15:30'),
    ("Yarın öğleden sonra 3.30'da gelin. Yarın 15.30'da gelirim.", "Yarın 15.30'da gelirim, tamam hocam.", '2026-10-23T15:30'),
    ('Yarın 15:30 gelin.', 'Tamam hocam, gelirim.', '2026-10-23T15:30'),
    ('Yarın 15:30 gelin.', 'Tamam ama gelemeyebilirim.', None),
    ('Yarın 15:30 gelin.', 'Yarın 16.30 gelirim, tamam hocam.', None),
    ('Yarın 15:30 gelin.', 'Bugün 15.30 gelirim, tamam hocam.', None),
    ('Yarın 15:30 veya 16:00 gelin.', 'Tamam hocam.', None),
])
def test_natural_appointment_acceptance_keeps_time_and_day_agreement(quote, acceptance, expected):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime(2026, 10, 22, 10, 0, tzinfo=ZoneInfo('Europe/Istanbul'))
    assert core.resolve_appointment(quote, acceptance, now) == expected


def test_final_only_submits_current_values_not_distracting_speech_quotes(monkeypatch):
    calls = provider(monkeypatch, {'summary': [], 'questions': [], 'contradictions': [], 'clinical_items': []})
    final.finalize(CONTEXT, [])
    fields = json.loads(calls[0]['contents'][0]['parts'][0]['text'])['clinical_fields']
    assert fields['chief_complaint'] == {'value': 'Soğukta ağrı'}
