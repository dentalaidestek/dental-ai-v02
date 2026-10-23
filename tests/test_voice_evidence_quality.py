import json
from datetime import datetime, timezone

import pytest

from app import voice_exam_dergipark as dergipark
from app import voice_exam_literature as pubmed
from app.voice_exam_clinical import grounded_items
from app.voice_exam_evidence import quality_metadata

YEAR = datetime.now(timezone.utc).year


@pytest.fixture(autouse=True)
def clear_caches():
    dergipark._cache.clear(); pubmed._cache.clear()


def test_metadata_does_not_promote_index_membership_case_reports_or_laboratory_reviews():
    assert quality_metadata('Retracted publication', ['Systematic Review'], YEAR) is None
    assert quality_metadata('Systematic review of in vitro models', ['Review'], YEAR)['clinical_use'] is False
    assert quality_metadata('A clinical review', ['Review'], YEAR)['clinical_use'] is False
    assert quality_metadata('A clinical review', ['Systematic Review'], YEAR)['clinical_use'] is True
    assert quality_metadata('Clinical practice guideline', ['Guideline'], YEAR - 20)['clinical_use'] is False
    assert quality_metadata('Clinical practice guideline', ['Guideline'])['clinical_use'] is False


def test_background_source_cannot_ground_a_clinical_suggestion_even_with_exact_quotes():
    ref = {'id': 'background', 'excerpts': ['Exact source quote'], 'clinical_use': False}
    fields = {'plan': {'value': 'Film çekelim'}}
    item = {'source_id': ref['id'], 'source_quote': ref['excerpts'][0], 'patient_field': 'plan',
            'patient_quote': 'Film', 'consideration': 'Test', 'missing_information': '', 'alternative': ''}
    assert grounded_items({'items': [item]}, fields, [ref]) == []


def test_separate_pubmed_queries_preserve_coverage_and_reject_retraction(monkeypatch):
    calls = []
    def get(utility, params):
        calls.append(params)
        if utility == 'esearch.fcgi':
            ident = '1' if 'endodontic' in params['term'] else '2'
            return json.dumps({'esearchresult': {'idlist': [ident]}}).encode()
        return (f'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><ArticleTitle>Endodontic review</ArticleTitle><Journal><JournalIssue><PubDate><Year>{YEAR}</Year></PubDate></JournalIssue></Journal><PublicationTypeList><PublicationType>Systematic Review</PublicationType></PublicationTypeList><Abstract><AbstractText>' + 'Pain assessment evidence. ' * 8 + '</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle><PubmedArticle><MedlineCitation><PMID>2</PMID><CommentsCorrectionsList><CommentsCorrections RefType="RetractionIn"/></CommentsCorrectionsList><Article><ArticleTitle>Retracted diabetes review</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>').encode()
    monkeypatch.setattr(pubmed, '_get', get)
    refs, missing = pubmed.retrieve_literature('ağrı diyabet')
    assert len(calls) == 3
    assert [r['id'] for r in refs] == ['pubmed-1']
    assert refs[0]['matched_topics'] == ['endodontic diagnosis']
    assert 'pubmed-no-clinical-evidence:diabetes dental treatment' in missing
    assert ' OR ' not in calls[0]['term'].split(') AND')[0]


def catalogue():
    return b'''<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"><ListRecords><record><header><identifier>oai:dergipark.org.tr:article/123</identifier></header><metadata><dc:title>Endodontic diagnosis: systematic review</dc:title><dc:description>Pain diagnosis.</dc:description><dc:date>2000-01-01</dc:date><dc:identifier>https://dergipark.org.tr/en/pub/selcukdentj/article/123</dc:identifier></metadata></record><record><header/><metadata><dc:title>Endodontic review</dc:title><dc:identifier>https://evil.example/pub/selcukdentj/article/999</dc:identifier></metadata></record><resumptionToken>unfinished-page</resumptionToken></ListRecords></OAI-PMH>'''


def article(issn='2148-7529', title='Endodontic diagnosis: systematic review'):
    return (f'<meta name="citation_issn" content="{issn}"><meta name="citation_title" content="{title}"><meta name="citation_article_type" content="Review"><meta name="citation_publication_date" content="{YEAR}-01-01"><meta name="citation_abstract" content="' + 'Clinical pain assessment before treatment. ' * 8 + '">').encode()


def test_dergipark_uses_public_oai_no_patient_query_validates_journal_and_real_publication_date(monkeypatch):
    calls = []
    def read(url, limit):
        calls.append(url)
        return catalogue() if 'oai/' in url else article()
    monkeypatch.setattr(dergipark, '_read', read)
    monkeypatch.setattr(dergipark, 'JOURNALS', {'selcukdentj': dergipark.JOURNALS['selcukdentj']})
    refs, missing = dergipark.retrieve_dergipark('PRIVATE_NAME soğukta ağrı PRIVATE_PHONE')
    assert len(refs) == 1 and refs[0]['clinical_use']
    assert refs[0]['publication_year'] == YEAR  # Not the OAI submission date 2000.
    assert len(calls) == 2 and 'PRIVATE' not in json.dumps(calls)
    assert not any('evil.example' in url for url in calls)
    assert missing == ['dergipark-partial-catalogue:selcukdentj']
    dergipark.retrieve_dergipark('soğukta ağrı')
    assert len(calls) == 2


def test_dergipark_rejects_wrong_journal_and_does_not_hide_transport_failure(monkeypatch):
    monkeypatch.setattr(dergipark, '_read', lambda *args: article(issn='0000-0000'))
    with pytest.raises(ValueError, match='Journal mismatch'):
        dergipark._article('selcukdentj', '123')
    monkeypatch.setattr(dergipark, '_read', lambda *args: (_ for _ in ()).throw(TimeoutError()))
    refs, missing = dergipark.retrieve_dergipark('ağrı')
    assert not refs and 'dergipark-unavailable:selcukdentj' in missing


def test_empty_pubmed_status_is_preserved_on_cache_hit(monkeypatch):
    calls = []
    monkeypatch.setattr(pubmed, '_get', lambda *args: (calls.append(args) or b'{"esearchresult":{"idlist":[]}}'))
    first = pubmed.retrieve_literature('ağrı')
    assert first == pubmed.retrieve_literature('ağrı') and first[1] and len(calls) == 1


def test_rejection_diagnostics_contain_only_reason_counts():
    fields = {'allergies': {'value': 'Antibiyotik döküntüsü', 'quote': 'Bir antibiyotik döküntü yapmıştı.'}}
    refs = [{'id': 's', 'excerpts': ['Original English source excerpt.']}]
    item = {'source_id': 's', 'source_quote': refs[0]['excerpts'][0], 'patient_field': 'allergies',
            'patient_quote': fields['allergies']['quote'], 'consideration': 'Test', 'missing_information': '', 'alternative': ''}
    diagnostics = {}
    assert grounded_items({'items': [item]}, fields, refs, diagnostics) == []
    assert diagnostics == {'patient_quote_mismatch': 1}
    assert fields['allergies']['quote'] not in json.dumps(diagnostics)
    item.update(patient_quote='Antibiyotik', source_quote='Translated source excerpt')
    diagnostics = {}
    assert grounded_items({'items': [item]}, fields, refs, diagnostics) == []
    assert diagnostics == {'source_quote_mismatch': 1}
