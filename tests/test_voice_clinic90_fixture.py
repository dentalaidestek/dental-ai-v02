"""Acceptance checks for varied clinic-noise cases; no clinical accuracy claim."""
from scripts.evaluate_voice_spoken import load_cases, validate_cases


def test_clinic_cases_cover_distinct_specialties_and_daily_three_speaker_speech():
    cases = load_cases('tests/fixtures/voice_clinic90_dialogues.json')
    inventory = validate_cases(cases)
    assert len(cases) == 8 and inventory['branches'] >= 8
    assert {case['branch'] for case in cases} >= {'perio','surgery','implant','prosth','endo','pediatric','ortho','oral_medicine'}
    for case in cases:
        assert len(case['dialogue']) >= 10
        assert {'Hekim','Hasta','Asistan'} <= {turn['speaker'] for turn in case['dialogue']}
        assert 160 <= sum(len(turn['text'].split()) for turn in case['dialogue']) <= 220
        assert case['required_patient_fields'] == ['chief_complaint','plan']
        assert case['must_preserve'] and case['must_not_infer']


def test_cases_include_negation_correction_other_person_and_unperformed_plans():
    cases = {case['id']:case for case in load_cases('tests/fixtures/voice_clinic90_dialogues.json')}
    assert any('üç gün önce kes' in t['text'] for t in cases['surgery-warfarin-90']['dialogue'])
    assert any('daha kesmedim' in t['text'] for t in cases['surgery-warfarin-90']['dialogue'])
    assert any('diş numarası yazmayın' in t['text'] for t in cases['crown-high-bite-90']['dialogue'])
    assert any('annem' in t['text'].casefold() and 'bende tanı yok' in t['text'] for t in cases['implant-mobility-90']['dialogue'])
