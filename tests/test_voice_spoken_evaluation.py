"""Offline checks of synthetic routing evaluation, never a clinical benchmark."""
import copy
import json
import os
import subprocess
import sys

import pytest

from scripts.evaluate_voice_spoken import load_cases, score_case, validate_cases
from app.voice_exam_taxonomy import BRANCH_LABELS


def sample_case():
    return {'id': 'paraphrase', 'dialogue': [
        {'speaker': 'Hasta', 'text': 'Yeni dişim ağzımı kapatınca öbürlerinden önce buluşuyor.'},
        {'speaker': 'Hekim', 'text': 'Kapanışını kontrol edelim.'}],
        'required_any': [['prosth.occlusion'], ['restorative.general', 'prosth.fixed']],
        'forbidden': ['endo.instrument_separation']}


def result_for(case):
    return {'literature_topics': [
        {'topic': 'prosth.occlusion', 'quote': case['dialogue'][0]['text']},
        {'topic': 'prosth.fixed', 'quote': case['dialogue'][0]['text']}], 'uncertain': ''}


def test_grounded_paraphrase_route_is_accepted():
    case = sample_case()
    score = score_case(case, result_for(case))
    assert score['passed'] and score['topic_group_recall'] == 1
    assert score['valid_quote_anchors'] == 2


def test_missing_required_group_is_rejected():
    case = sample_case()
    result = result_for(case)
    result['literature_topics'].pop()
    score = score_case(case, result)
    assert not score['passed'] and score['topic_group_recall'] == .5
    assert 'missing_required_group' in score['failure_categories']


def test_forbidden_route_is_rejected_even_with_grounded_quote():
    case = sample_case()
    result = result_for(case)
    result['literature_topics'].append({'topic': 'endo.instrument_separation', 'quote': case['dialogue'][1]['text']})
    score = score_case(case, result)
    assert not score['passed'] and score['forbidden_hits'] == 1


def test_ungrounded_route_cannot_satisfy_required_group():
    case = sample_case()
    result = result_for(case)
    result['literature_topics'][0]['quote'] = 'Hastanın yeni kaplaması yüksek.'
    score = score_case(case, result)
    assert not score['passed'] and score['topic_group_recall'] == .5
    assert 'invalid_quote_anchor' in score['failure_categories']


def test_unknown_ids_and_missing_uncertainty_are_rejected():
    case = sample_case()
    case['requires_uncertainty'] = True
    result = result_for(case)
    result['literature_topics'].append({'topic': 'invented.topic', 'quote': case['dialogue'][0]['text']})
    score = score_case(case, result)
    assert score['unknown_ids'] == 1 and not score['passed']
    assert 'missing_uncertainty' in score['failure_categories']
    result['literature_topics'].pop()
    result['follow_up_questions'] = [{'quote': case['dialogue'][0]['text'], 'question': 'Hangi dişiniz?', 'priority': 'CLARIFY_NOW'}]
    assert score_case(case, result)['passed']


def test_fixture_has_all_fifteen_branches_and_short_synthetic_dialogues():
    cases = load_cases()
    inventory = validate_cases(cases)
    assert 30 <= len(cases) <= 45
    assert inventory['branches'] == 15 == len(BRANCH_LABELS)
    assert all(2 <= len(case['dialogue']) <= 6 for case in cases)
    assert any(case.get('requires_uncertainty') for case in cases)
    assert len({case['id'] for case in cases}) == len(cases)


def test_validation_rejects_unknown_topic_and_empty_group():
    case = sample_case()
    bad = copy.deepcopy(case)
    bad['required_any'] = [['invented.topic']]
    with pytest.raises(ValueError):
        validate_cases([bad])
    bad['required_any'] = [[]]
    with pytest.raises(ValueError):
        validate_cases([bad])


def test_default_cli_is_offline_and_does_not_print_dialogues():
    env = dict(os.environ, ANTHROPIC_API_KEY='', VOICE_EXAM_CLAUDE_MODEL='')
    completed = subprocess.run([sys.executable, 'scripts/evaluate_voice_spoken.py'], env=env, capture_output=True, text=True)
    assert completed.returncode == 0
    output = json.loads(completed.stdout)
    assert output['mode'] == 'offline_inventory'
    assert output['cases'] >= 30
    assert 'Hasta' not in completed.stdout and 'literature_topics' not in completed.stdout


def test_live_cli_fails_closed_without_key_before_calling_provider():
    env = dict(os.environ, ANTHROPIC_API_KEY='', VOICE_EXAM_CLAUDE_MODEL='claude-haiku-5-5')
    completed = subprocess.run([sys.executable, 'scripts/evaluate_voice_spoken.py', '--live'], env=env, capture_output=True, text=True)
    assert completed.returncode != 0
    assert 'missing_provider_configuration' in completed.stdout
    assert not completed.stderr


def test_generic_extraction_warning_cannot_satisfy_ambiguity_clarification():
    case = sample_case()
    case['requires_uncertainty'] = True
    result = result_for(case)
    result['uncertain'] = 'Bu bölümden klinik alan çıkarılmadı. Konuşma metnini kontrol edin.'
    assert not score_case(case, result)['passed']
