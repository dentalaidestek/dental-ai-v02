import json
import pytest
from app import voice_exam_literature as literature
from app import voice_exam_core as core
from app import voice_exam_final as final


@pytest.fixture(autouse=True)
def empty_cache():
    literature._cache.clear()


def test_pubmed_fetches_real_abstract_shape_caches_and_never_sends_patient_text(monkeypatch):
    calls = []
    xml = b'''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>Dental assessment</ArticleTitle><Journal><Title>Dental Journal</Title><JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue></Journal><PublicationTypeList><PublicationType>Systematic Review</PublicationType></PublicationTypeList><Abstract><AbstractText>Clinical examination and radiographic assessment are necessary to evaluate the reported symptoms before planning treatment.</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'''
    def get(utility, params):
        calls.append((utility, params))
        return json.dumps({'esearchresult': {'idlist': ['123']}}).encode() if utility == 'esearch.fcgi' else xml
    monkeypatch.setattr(literature, '_get', get)
    text = 'PRIVATE_NAME PRIVATE_PHONE Soğukta ağrı, film çekelim.'
    refs, missing = literature.retrieve_literature(text)
    assert len(calls) == 3 and not missing
    assert refs[0]['id'] == 'pubmed-123' and refs[0]['excerpts']
    assert 'PRIVATE' not in json.dumps(calls)
    assert literature.retrieve_literature(text)[0] == refs and len(calls) == 3


def test_model_topic_understands_synonyms_but_needs_speech_anchor():
    topic = {'topic': 'endodontic diagnosis', 'quote': 'Gece uyutmuyor.'}
    result = core.normalize({'transcript': 'Gece uyutmuyor.', 'literature_topics': [topic]}, evidence='Gece uyutmuyor.')
    assert result['literature_topics'] == [topic]
    assert not core.normalize({'transcript': 'Gece uyutmuyor.', 'literature_topics': [topic]}, evidence='İyiyim.')['literature_topics']
    with pytest.raises(core.VoiceError):
        core.clinical_context({'literature_topics': [{'topic': 'PRIVATE_NAME', 'quote': 'x'}]})


def test_model_topics_reach_pubmed_without_sending_quote(monkeypatch):
    seen = []
    def get(utility, params):
        seen.append(params)
        return b'{"esearchresult":{"idlist":[]}}'
    monkeypatch.setattr(literature, '_get', get)
    refs, missing = literature.retrieve_literature('Uyutmuyor', topics=[{'topic': 'endodontic diagnosis', 'quote': 'PRIVATE'}])
    assert 'endodontic diagnosis' in seen[0]['term'] and 'PRIVATE' not in json.dumps(seen)
    assert 'pubmed-no-match:endodontic diagnosis' in missing and not refs


def test_failure_and_empty_abstract_are_not_safety_clearance(monkeypatch):
    monkeypatch.setattr(literature, '_get', lambda *args: (_ for _ in ()).throw(TimeoutError()))
    refs, missing = literature.retrieve_literature('ağrı')
    assert not refs and 'pubmed-search-unavailable:endodontic diagnosis' in missing
    assert literature.retrieve_literature('') == ([], [])


def test_final_uses_literature_and_preserves_all_clinical_fields(monkeypatch):
    from test_voice_exam_final import provider, CONTEXT
    ref = {'id': 'pubmed-123', 'institution': 'PubMed', 'title': 'Review', 'url': 'https://pubmed.ncbi.nlm.nih.gov/123/', 'excerpts': ['Assess the cause of dental pain before treatment.']}
    item = {'source_id': ref['id'], 'source_quote': ref['excerpts'][0], 'patient_field': 'chief_complaint', 'patient_quote': 'Soğukta', 'consideration': 'Ağrının nedeni netleştirilmeli.', 'missing_information': 'Ağrı süresi?', 'alternative': ''}
    calls = provider(monkeypatch, {'summary': [{'field': 'medications', 'quote': 'Warfarin', 'text': 'İlaç beyanı'}], 'questions': [], 'contradictions': [], 'clinical_items': [item]})
    monkeypatch.setattr(final, 'retrieve', lambda *args, **kw: {'references': [ref], 'unavailable': [], 'coverage': 'limited', 'notice': 'test'})
    result = final.finalize(CONTEXT, [])
    assert result['clinical_items'] == [item]
    assert {i['field'] for i in result['summary']} == set(CONTEXT['fields'])
    assert len(calls) == 1 and 'pubmed-123' in calls[0]['messages'][0]['content']
