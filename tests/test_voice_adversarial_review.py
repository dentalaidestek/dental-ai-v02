"""Adversarial provider outputs against real final-review validation, no network.

These tests exercise rejection/retention contracts, not real-model comprehension.
"""
import copy
import pytest
from app import voice_exam_final as final

PATIENT = 'Yeni kaplamam önce değiyor, ağrım yok.'
SOURCE = 'Occlusal contacts require clinical assessment.'


@pytest.fixture
def review_case(monkeypatch):
    reference = {'id': 'public-occlusion', 'url': 'https://www.ada.org/example',
                 'excerpts': [SOURCE], 'clinical_use': True}
    item = {'source_id': reference['id'], 'source_quote': SOURCE,
            'patient_field': 'chief_complaint', 'patient_quote': PATIENT,
            'consideration': 'Kapanış ilişkisini klinik muayene ile değerlendirin.',
            'missing_information': 'Kapanış muayenesi', 'alternative': ''}
    evidence = {'references': [reference], 'unavailable': [], 'coverage': 'limited', 'notice': 'Synthetic'}
    monkeypatch.setattr(final, 'retrieve', lambda *a, **k: evidence)
    context = {'fields': {'chief_complaint': {'value': PATIENT, 'quote': PATIENT}}, 'literature_topics': []}
    def run(mutation=None, eligible=True):
        output = copy.deepcopy(item)
        if mutation: output.update(mutation)
        reference['clinical_use'] = eligible
        monkeypatch.setattr(final, 'review', lambda *a, **k: {'questions': [], 'contradictions': [], 'clinical_items': [output]})
        return final.finalize(context, [])
    return run


@pytest.mark.parametrize('mutation', [
    {'source_id': 'invented-source'},
    {'source_quote': 'Kapanış ilişkisi muayene gerektirir.'},
    {'source_quote': 'A completely different source sentence.'},
    {'patient_quote': 'Kaplaması yüksek ve ağrısı var.'},
    {'patient_field': 'invented-field'},
    {'source_quote': ' '},
    {'source_quote': '\n\t'},
    {'patient_quote': ' '},
    {'consideration': '  \n'},
])
def test_invalid_or_vacuous_model_claim_is_not_shown(review_case, mutation):
    output = review_case(mutation)
    assert output['clinical_items'] == []
    assert output['review_status']['rejected_clinical_items'] == 1
    assert output['summary'][0]['text'] == PATIENT


def test_unassessed_journal_cannot_be_used_for_clinical_claim(review_case):
    assert review_case(eligible=False)['clinical_items'] == []


def test_legitimate_grounded_review_remains_visible_and_negation_is_preserved(review_case):
    output = review_case()
    assert len(output['clinical_items']) == 1
    assert output['clinical_items'][0]['source_quote'] == SOURCE
    assert output['summary'][0]['text'] == PATIENT
