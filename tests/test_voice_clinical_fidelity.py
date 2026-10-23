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
    assert 'Geçmiş: Risedronat' in fields['medications']['value']
    assert 'Güncel: Prolia' in fields['medications']['value']
    assert 'Altı ayda bir' in fields['medications']['value']
    assert 'Planlanan:' in fields['plan']['value'] and 'henüz başlanmadı' in fields['plan']['value']
    assert 'INR 2–3' in fields['medical_history']['value']


def test_fabricated_fact_and_private_categories_are_not_accepted():
    facts = [{'field': field, 'value': 'Uydurma', 'quote': quote, 'temporality': 'CURRENT'}
             for field, quote in [('medications', 'Varfarin kullanıyorum.'), ('private_life', 'İyiyim.')]]
    assert not core.normalize({'transcript': 'İyiyim.', 'clinical_facts': facts})['fields']


@pytest.mark.parametrize('quote', ['46 dolguya uygun değil.', '46 çürük yok.', '46 çürük olabilir.', '46 çürük var mı?'])
def test_unspoken_or_uncertain_caries_is_not_a_chart_candidate(quote):
    assert not core.normalize({'transcript': quote, 'teeth': [{'tooth': '46', 'status': 'CARIES', 'quote': quote}]})['teeth']


def test_explicit_caries_is_preserved():
    quote = '46 numarada çürük var.'
    assert core.normalize({'transcript': quote, 'teeth': [{'tooth': '46', 'status': 'CARIES', 'quote': quote}]})['teeth'][0]['status'] == 'CARIES'


@pytest.mark.parametrize('acceptance,expected', [
    ('Tamam hocam, bugün beşte gelirim.', '2026-10-23T17:00'),
    ('Tamam hocam, bugün altıda gelirim.', None),
    ('Tamam hocam, bugün sabah beşte gelirim.', None),
    ('Bugün beşte gelemem.', None),
    ('Tamam ama bugün beşte gelirim diyemem.', None),
    ('Tamam hocam, yarın beşte gelirim.', None)])
def test_colloquial_hour_acceptance_requires_same_day_and_same_proposal(acceptance, expected):
    now = datetime(2026, 10, 23, 13, 0, tzinfo=ZoneInfo('Europe/Istanbul'))
    assert core.resolve_appointment('Bugün saat on yedide tekrar gelir misiniz?', acceptance, now) == expected


def test_text_understanding_uses_claude_once_and_keeps_original_text(monkeypatch):
    from app import voice_exam_review_provider as provider
    calls = []
    def review(prompt, data, schema, **options):
        calls.append(data)
        assert options == {'extraction': True}
        assert schema['properties']['fields']['required'] == list(core.FIELDS)
        return {'transcript': 'Modelin eksik yeniden yazımı', 'fields': {}, 'clinical_facts': []}
    monkeypatch.setattr(provider, 'review', review)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    original = 'Kartımda Prolia yazıyor. Her gün ilaç almıyorum.'
    output = core.extract(transcript=original)
    assert output['transcript'] == original
    assert len(calls) == 1 and calls[0]['clinical_text'] == original
    assert 'sources' not in calls[0]  # Extraction is not a second literature review.
