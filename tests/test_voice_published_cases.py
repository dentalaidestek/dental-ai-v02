"""Published-case-inspired dialogues remain provisional, not clinical gold labels."""
import json
from pathlib import Path

import pytest

from scripts.evaluate_voice_spoken import dialogue_text, evaluate_repeated, load_cases, main, score_case, validate_cases

FIXTURE = Path(__file__).parent / 'fixtures' / 'voice_published_case_dialogues.json'


def test_assistant_and_longer_conversation_are_supported():
    case = {'id': 'three-speakers', 'dialogue': [
        {'speaker': speaker, 'text': 'Kontrol edelim.'}
        for speaker in ['Hasta', 'Hekim', 'Asistan', 'Hasta', 'Hekim', 'Asistan', 'Hasta', 'Hekim']],
        'required_any': [['prosth.removable']], 'forbidden': []}
    assert validate_cases([case])['cases'] == 1
    assert 'Asistan: Kontrol edelim.' in dialogue_text(case)


def test_custom_fixture_is_selected_without_provider_calls(tmp_path, capsys):
    path = tmp_path / 'cases.json'
    path.write_text(json.dumps({'synthetic': True, 'cases': [
        {'id': 'chosen', 'dialogue': [
            {'speaker': 'Hasta', 'text': 'Takma dişim oynuyor.'},
            {'speaker': 'Asistan', 'text': 'Doktorumuz bakacak.'}],
         'required_any': [['prosth.removable']], 'forbidden': []}]}))
    assert main(['--fixture', str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output['selected_cases'] == 1 and output['model_calls'] == 0


def test_unknown_speaker_and_unbounded_dialogue_are_rejected():
    case = {'id': 'bad', 'dialogue': [{'speaker': 'Unknown', 'text': 'x'}] * 8,
            'required_any': [], 'forbidden': []}
    with pytest.raises(ValueError, match='invalid_dialogue_turn'):
        validate_cases([case])
    case['dialogue'] = [{'speaker': 'Hasta', 'text': 'x'}] * 13
    with pytest.raises(ValueError, match='invalid_dialogue_length'):
        validate_cases([case])


def test_supported_legacy_topics_do_not_become_unknown_branches():
    case = {'id': 'legacy', 'dialogue': [
        {'speaker': 'Hasta', 'text': 'Dişim düştü.'},
        {'speaker': 'Hekim', 'text': 'Travmayı değerlendirelim.'}],
        'required_any': [['dental trauma management']], 'forbidden': []}
    inventory = validate_cases([case])
    assert inventory['expected_topics'] == 1
    assert inventory['branches'] == 0  # Only registered dot-prefixed branches counted.
    assert inventory['legacy_expected_topics'] == 1


def test_published_cases_have_traceable_sources_and_provisional_checklists():
    fixture = json.loads(FIXTURE.read_text())
    assert fixture['synthetic'] is True
    assert fixture['approval_status'] == 'draft'
    assert fixture['clinical_gold_standard'] is False
    cases = fixture['cases']
    assert validate_cases(cases)['cases'] == 24
    sources = {source['id']: source for source in fixture['sources']}
    assert len(sources) >= 12
    for source in sources.values():
        assert source['url'].startswith('https://')
        assert source['title'] and source['accessed_on'] == '2026-10-31'
        assert source['evidence_scope']
    ids = {case['id'] for case in cases}
    for case in cases:
        assert {'Hasta', 'Hekim', 'Asistan'} <= {t['speaker'] for t in case['dialogue']}
        assert set(case['source_ids']) <= sources.keys() and case['source_ids']
        pair = next(c for c in cases if c['id'] == case['contrast_case_id'])
        assert pair['contrast_case_id'] == case['id'] and pair['dialogue'] != case['dialogue']
        assert case['contrast_case_id'] in ids
        assert case['adaptation_notes'] and case['must_preserve']
        assert case['must_not_infer'] and case['review_checklist']
        assert not set(case.get('required_clinician_quotes', [])) & set(case.get('forbidden_clinician_quotes', []))


@pytest.mark.parametrize('case', load_cases(FIXTURE), ids=lambda case: case['id'])
def test_empty_extraction_never_counts_as_success_for_a_published_case(case):
    report = evaluate_repeated([case], lambda text, context: {}, repeat=1)
    assert not report['all_cases_passed']
    assert 'missing_required_group' in report['results'][0]['runs'][0]['failure_categories']


@pytest.mark.parametrize('case', [c for c in load_cases(FIXTURE) if c.get('forbidden_clinician_quotes')],
                         ids=lambda case: case['id'])
def test_assistant_personal_statement_misattribution_is_detected(case):
    quote = case['forbidden_clinician_quotes'][0]
    result = {'communication': [{'category': 'CLINICAL_STATEMENT', 'quote': quote}]}
    assert 'forbidden_clinician_statement' in score_case(case, result)['failure_categories']


def test_case_metadata_and_expected_answers_are_not_sent_to_extractor(monkeypatch, capsys):
    from app import voice_exam_core as core
    case = load_cases(FIXTURE)[0]
    calls = []
    def extract(text, context):
        assert context == {}
        calls.append(text)
        return {}
    monkeypatch.setattr(core, '_understand', extract)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-not-a-real-key')
    monkeypatch.setenv('VOICE_EXAM_CLAUDE_MODEL', 'claude-test-model')
    assert main(['--fixture', str(FIXTURE), '--live', '--case', case['id'], '--repeat', '2']) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['model_calls'] == 2
    assert calls == [dialogue_text(case)] * 2
    assert case['review_checklist'][0] not in calls[0]
    assert case['source_ids'][0] not in calls[0]
    assert case['required_any'][0][0] not in calls[0]
