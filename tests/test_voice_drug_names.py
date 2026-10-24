import pytest
from app.voice_drug_names import supported_search_term, is_spelling_candidate
from app import voice_exam_core as core
from app import voice_exam_live_sources as live


@pytest.mark.parametrize('term,quote', [
    ('simvastatin', 'Simvastati kullanıyorum.'),
    ('clarithromycin', 'Klaritromisin düşünüyorum.'),
    ('naproxen', 'Naproksen kullanıyorum.'),
    ('miconazole', 'Mikonazol ağız jeli düşünüyorum.')])
def test_partial_and_turkish_spellings_only_enable_search_hypothesis(term, quote):
    assert supported_search_term(term, quote) and is_spelling_candidate(term, quote)
    out = core.normalize({'transcript': quote, 'source_requests': [{'term': term, 'quote': quote}],
        'clinical_facts': [{'field': 'medications', 'value': term, 'quote': quote, 'temporality': 'CURRENT'}]})
    assert out['fields']['medications']['value'] == 'Güncel: ' + quote
    assert out['source_requests'][0]['term'] == term
    assert core.clinical_context({'source_requests': out['source_requests']})['source_requests']


@pytest.mark.parametrize('term,quote', [
    ('etidronate', 'Haftalık hissedronat kullandım.'),
    ('simvastatin', 'Kolesterol ilacı kullanıyorum.'),
    ('denosumab', 'Prolia yaptırdım.'),
    ('https://evil.example', 'Bir ilaç alıyorum.')])
def test_missing_ambiguous_or_semantic_substitution_cannot_enable_search(term, quote):
    assert not supported_search_term(term, quote)


def test_candidate_label_is_marked_unconfirmed_without_mutating_cached_record(monkeypatch):
    cached = {'id': 'official', 'excerpts': ['Label content']}
    monkeypatch.setattr(live, 'lookup', lambda term: cached)
    refs, missing = live.retrieve_requests([{'term': 'simvastatin', 'quote': 'Simvastati alıyorum.'}])
    assert refs[0]['name_resolution'] == 'unconfirmed_spelling_candidate'
    assert 'name_resolution' not in cached and not missing
    monkeypatch.setattr(live, 'lookup', lambda term: (_ for _ in ()).throw(ValueError()))
    assert live.retrieve_requests([{'term': 'simvastatin', 'quote': 'Simvastati alıyorum.'}]) == ([], ['drug:simvastatin'])
