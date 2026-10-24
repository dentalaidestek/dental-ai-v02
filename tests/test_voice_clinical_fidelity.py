from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app import voice_exam_core as core


def test_atomic_facts_survive_invalid_combined_summary_and_daily_denial():
    text = 'Her gün aldığım bir şey yok. Eskiden risedronat kullandım. Prolia iğnesi yapıldı. Altı ayda bir. Mikonazol ağız jeli düşünüyorum. Henüz başlamadım. INR ikiyle üç arasında.'
    facts = [
        ('medications', 'Her gün ilaç almıyor', 'Her gün aldığım bir şey yok.', 'NEGATED'),
        ('medications', 'Risedronat kullanmış', 'Eskiden risedronat kullandım.', 'HISTORICAL'),
        ('medications', 'Prolia enjeksiyonu', 'Prolia iğnesi yapıldı.', 'CURRENT'),
        ('medications', 'Altı ayda bir uygulanıyor', 'Altı ayda bir.', 'CURRENT'),
        ('plan', 'Mikonazol ağız jeli düşünülüyor; henüz başlanmadı', 'Mikonazol ağız jeli düşünüyorum. Henüz başlamadım.', 'PLANNED'),
        ('medical_history', 'INR 2–3 beyanı', 'INR ikiyle üç arasında.', 'CURRENT')]
    data = {'transcript': text, 'fields': {'medications': {'value': 'Eksik özet', 'quote': 'risedronat ve Prolia'}},
        'clinical_facts': [dict(zip(('field', 'value', 'quote', 'temporality'), fact)) for fact in facts]}
    fields = core.normalize(data, evidence=text)['fields']
    assert 'Geçmiş: Eskiden risedronat' in fields['medications']['value']
    assert 'Güncel: Prolia' in fields['medications']['value']
    assert 'Altı ayda bir' in fields['medications']['value']
    assert 'Planlanan:' in fields['plan']['value'] and 'henüz başlanmadı' in fields['plan']['value']
    assert 'INR 2–3' in fields['medical_history']['value']


def test_fabricated_fact_and_private_categories_are_not_accepted():
    facts = [{'field': field, 'value': 'Uydurma', 'quote': quote, 'temporality': 'CURRENT'}
             for field, quote in [('medications', 'Varfarin kullanıyorum.'), ('private_life', 'İyiyim.')]]
    assert not core.normalize({'transcript': 'İyiyim.', 'clinical_facts': facts})['fields']


def test_doctor_response_and_patient_teachback_are_grounded_transient_context():
    text = 'Elinizi kaldırırsanız duralım. Bugün temizleyeceksiniz, yeni ilaca başlamıyorum.'
    facts = [{'field': 'clinician_response', 'value': 'Durma işareti açıklandı.',
              'quote': 'Elinizi kaldırırsanız duralım.', 'temporality': 'CURRENT'},
             {'field': 'clinician_response', 'value': 'Hasta planı geri anlattı.',
              'quote': 'Bugün temizleyeceksiniz, yeni ilaca başlamıyorum.', 'temporality': 'CURRENT'},
             {'field': 'clinician_response', 'value': 'Uydurma yanıt',
              'quote': 'Her şeyi anladım.', 'temporality': 'CURRENT'}]
    result = core.normalize({'transcript': text, 'clinical_facts': facts})
    assert not result['fields']
    assert len(result['communication']) == 2
    assert all(item['quote'] in text for item in result['communication'])
    assert all('Görüşmede verilen yanıt' in item['observation'] for item in result['communication'])


def test_private_coaching_survives_formatting_only_quote_changes():
    text = 'Biraz da çekimden korkuyorum. Bugün bitsin istiyorum.'
    quote = 'Biraz da çekimden korkuyorum, bugün bitsin istiyorum.'
    result = core.normalize({'transcript': text,
        'communication': [{'quote': quote, 'observation': 'Korku belirtildi', 'suggestion': 'Endişesini sorun'}],
        'decision_barriers': [{'quote': quote, 'category': 'FEAR', 'observation': 'Korku belirtildi',
            'question': 'Neden endişeleniyorsunuz?', 'explanation': 'Adımları anlatın'}],
        'follow_up_questions': [{'quote': quote, 'priority': 'CLARIFY_NOW',
            'question': 'Neden endişeleniyorsunuz?', 'reason': 'Kaygıyı anlamak'}]})
    for key in ('communication', 'decision_barriers', 'follow_up_questions'):
        assert result[key][0]['quote'] == text.rstrip('.')
    fabricated = core.normalize({'transcript': text, 'communication': [
        {'quote': 'Parayı ödeyemiyorum.', 'observation': 'Maddi sorun', 'suggestion': 'Sorun'}]})
    assert not fabricated['communication']


def test_uncertain_spoken_drug_cannot_be_replaced_or_searched_as_another_ingredient():
    quote = 'Haftalık hissedronat hapı kullandım.'
    output = core.normalize({'transcript': quote, 'clinical_facts': [{
        'field': 'medications', 'value': 'Etidronat kullanmış', 'quote': quote, 'temporality': 'HISTORICAL'}],
        'source_requests': [{'term': 'etidronate', 'quote': quote}]})
    assert output['fields']['medications']['value'] == 'Geçmiş: ' + quote
    assert not output['source_requests']
    context = core.clinical_context({'source_requests': [{'term': 'etidronate', 'quote': quote}]})
    assert not context['source_requests']


@pytest.mark.parametrize('quote', ['46 dolguya uygun değil.', '46 çürük yok.', '46 çürük olabilir.', '46 çürük var mı?'])
def test_unspoken_or_uncertain_caries_is_not_a_chart_candidate(quote):
    assert not core.normalize({'transcript': quote, 'teeth': [{'tooth': '46', 'status': 'CARIES', 'quote': quote}]})['teeth']


def test_explicit_caries_is_preserved():
    quote = '46 numarada çürük var.'
    assert core.normalize({'transcript': quote, 'teeth': [{'tooth': '46', 'status': 'CARIES', 'quote': quote}]})['teeth'][0]['status'] == 'CARIES'


def test_appointment_acceptance_with_work_leave_tail_and_bare_hour():
    now = datetime(2026, 10, 24, 10, tzinfo=ZoneInfo('Europe/Istanbul'))
    for proposal in ('Yarın saat on dörtte kontrol için gelebilir misiniz?', 'Yarın saat 14 kontrol için gelebilir misiniz?'):
        assert core.resolve_appointment(proposal, 'Yarın ikide gelebilirim, işten izin ayarlarım.', now) == '2026-10-25T14:00'
        assert core.resolve_appointment(proposal, 'Yarın ikide gelebilirim, ama üçte olmaz.', now) is None
        assert core.resolve_appointment(proposal, 'Yarın ikili gelebilirim.', now) is None


@pytest.mark.parametrize('quote,expected', [
    ('Sağ alt arka dişim kırıldı hocam.', False),
    ('Numara dişin kalan kısmı dolguya uygun değil.', False),
    ('46 numaralı diş kırık.', True),
    ('Kırk altı numaralı diş kırık.', True),
    ('146 numarası.', False)])
def test_specific_tooth_requires_an_explicit_fdi_number_in_its_quotation(quote, expected):
    result = core.normalize({'transcript': quote, 'teeth': [{'tooth': '46', 'status': 'OTHER', 'quote': quote}]})
    assert bool(result['teeth']) is expected


@pytest.mark.parametrize('query,topics', [
    ('', [{'topic': 'antiresorptive medication osteonecrosis jaw'}]),
    ('Kemik erimesi için tedavi alıyorum.', []),
    ('Geçmişte risedronat kullandım.', [])])
def test_relevant_osteoporosis_source_is_selected_without_requiring_a_risk_diagnosis(monkeypatch, query, topics):
    from app import voice_exam_sources as sources
    from app import voice_exam_literature, voice_exam_dergipark, voice_exam_drugs
    fetched = []
    def fetch(doc):
        fetched.append(doc[0])
        return {'id': doc[0]}
    monkeypatch.setattr(sources, '_fetch', fetch)
    monkeypatch.setattr(voice_exam_literature, 'retrieve_literature', lambda *a, **k: ([], []))
    monkeypatch.setattr(voice_exam_dergipark, 'retrieve_dergipark', lambda *a, **k: ([], []))
    monkeypatch.setattr(voice_exam_drugs, 'retrieve_drugs', lambda *a, **k: [])
    result = sources.retrieve(query, topics=topics)
    assert 'ada-mronj' in fetched
    assert result['coverage'] == 'limited'


@pytest.mark.parametrize('acceptance,expected', [
    ('Tamam hocam, bugün beşte gelirim.', '2026-10-23T17:00'),
    ('Tamam hocam, bugün beşte gelirim. Kartı da getiririm.', '2026-10-23T17:00'),
    ('Tamam hocam, bugün beşte gelirim. Ama gelemeyebilirim.', None),
    ('Tamam hocam, bugün beşte gelirim. Yarın demek istedim.', None),
    ('Tamam hocam, bugün altıda gelirim.', None),
    ('Tamam hocam, bugün sabah beşte gelirim.', None),
    ('Bugün beşte gelemem.', None),
    ('Tamam ama bugün beşte gelirim diyemem.', None),
    ('Tamam hocam, yarın beşte gelirim.', None)])
def test_colloquial_hour_acceptance_requires_same_day_and_same_proposal(acceptance, expected):
    now = datetime(2026, 10, 23, 13, 0, tzinfo=ZoneInfo('Europe/Istanbul'))
    assert core.resolve_appointment('Bugün saat on yedide tekrar gelir misiniz?', acceptance, now) == expected


@pytest.mark.parametrize('acceptance,expected', [
    ("Tamam hocam, bugün 5'te gelirim. Kartı da getiririm.", '2026-10-23T17:00'),
    ('Tamam bugün 17’de gelirim.', '2026-10-23T17:00'),
    ("Bugün 6'da gelirim.", None),
    ("Bugün sabah 5'te gelirim.", None)])
def test_stt_numeric_suffixed_hours(acceptance, expected):
    now = datetime(2026, 10, 23, 13, tzinfo=ZoneInfo('Europe/Istanbul'))
    assert core.resolve_appointment("Bugün saat 17'de tekrar gelir misiniz?", acceptance, now) == expected


def test_text_understanding_uses_claude_once_and_keeps_original_text(monkeypatch):
    from app import voice_exam_review_provider as provider
    calls = []
    def review(prompt, data, schema, **options):
        calls.append(data)
        assert options == {'extraction': True}
        assert schema['properties']['fields']['required'] == list(core.FIELDS[:3])
        assert 'transcript' not in schema['properties']
        assert schema['properties']['clinical_facts']['items']['properties']['field']['enum'] == [*core.FIELDS[3:], 'patient_concern', 'clinician_response']
        return {'transcript': 'Modelin eksik yeniden yazımı', 'fields': {}, 'clinical_facts': []}
    monkeypatch.setattr(provider, 'review', review)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    original = 'Kartımda Prolia yazıyor. Her gün ilaç almıyorum.'
    output = core.extract(transcript=original)
    assert output['transcript'] == original
    assert len(calls) == 1 and calls[0]['clinical_text'] == original
    assert 'sources' not in calls[0]  # Extraction is not a second literature review.


def test_full_claude_transport_to_normalized_fields(monkeypatch):
    from test_voice_review_provider import transport
    text = 'Prolia iğnesi yapıldı. Altı ayda bir.'
    result = {key: [] for key in core.schema()['required']}
    result.update(transcript=text, uncertain='', fields={}, appointment={'quote': '', 'acceptance_quote': ''},
        clinical_facts=[{'field': 'medications', 'value': 'Prolia enjeksiyonu, altı ayda bir',
                         'quote': text, 'temporality': 'CURRENT'}])
    calls, _ = transport(monkeypatch, {'stop_reason': 'tool_use', 'content': [
        {'type': 'tool_use', 'name': 'clinical_extract', 'input': result}]})
    output = core.extract(transcript=text)
    assert 'Prolia' in output['fields']['medications']['value']
    assert len(calls) == 1


def test_long_input_without_grounded_clinical_fields_is_explicitly_incomplete(monkeypatch, caplog):
    from app import voice_exam_review_provider as provider
    text = 'Hasta: Çiğnerken ağrıyor. Hekim: Film çekelim. ' * 4
    monkeypatch.setattr(provider, 'review', lambda *a, **k: {
        'fields': {}, 'clinical_facts': [], 'uncertain': ''})
    output = core._understand(text, {})
    assert 'klinik alan çıkarılmadı' in output['uncertain']
    assert 'candidates=0 grounded_fields=0' in caplog.text
    assert 'Çiğnerken' not in caplog.text


def test_atomic_private_concern_is_shown_only_as_private_coaching():
    text = 'Biraz da çekimden korkuyorum.'
    value = 'Endişenizi en çok hangi aşama artırıyor diye sorun; adımları sakin anlatın.'
    output = core.normalize({'transcript': text, 'clinical_facts': [
        {'field': 'patient_concern', 'value': value, 'quote': text, 'temporality': 'CURRENT'}]})
    assert not output['fields']
    assert output['communication'] == [{'quote': text, 'observation': text, 'suggestion': value}]
    assert text not in str(core.clinical_context({'fields': output['fields']}))
