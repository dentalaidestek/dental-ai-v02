from datetime import datetime, timezone
import json
import pytest


def test_build_failure_keeps_previous_snapshot_and_rebuild_removes_old_records(tmp_path):
    from scripts.build_voice_literature import build
    from app.voice_literature_index import retrieve
    path = tmp_path / 'index.sqlite'
    topic = 'endo.instrument_separation'
    def response(utility, params):
        assert 'PRIVATE' not in json.dumps(params)
        if utility == 'esearch.fcgi':
            return b'{"esearchresult":{"idlist":["123"]}}'
        return (f'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>Instrument separation review</ArticleTitle><Journal><JournalIssue><PubDate><Year>{datetime.now(timezone.utc).year}</Year></PubDate></JournalIssue></Journal><PublicationTypeList><PublicationType>Systematic Review</PublicationType></PublicationTypeList><Abstract><AbstractText>' + 'Evidence sentence. '*20 + '</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>').encode()
    report = build(path, topic_ids=[topic], get=response)
    assert report['stored'] == 1
    before = path.read_bytes()
    with pytest.raises(TimeoutError):
        build(path, topic_ids=[topic], get=lambda *a: (_ for _ in ()).throw(TimeoutError()))
    assert path.read_bytes() == before
    report = build(path, topic_ids=[topic], get=lambda *a: b'{"esearchresult":{"idlist":[]}}')
    assert report['stored'] == 0
    assert path.read_bytes() != before


def test_retraction_notice_removes_article_even_without_retracted_publication_tag():
    from scripts.build_voice_literature import parse_records
    xml = b'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><CommentsCorrectionsList><CommentsCorrections RefType="RetractionIn"/></CommentsCorrectionsList><Article><ArticleTitle>Review</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    assert parse_records(xml, {'123'}, 'endodontic diagnosis') == []


def test_normal_pubmed_public_doctype_is_accepted_without_external_entity_expansion():
    from scripts.build_voice_literature import parse_records
    xml = b'<?xml version="1.0"?><!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2025//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_250101.dtd"><PubmedArticleSet/>'
    assert parse_records(xml, set(), 'endodontic diagnosis') == []
    with pytest.raises(ValueError):
        parse_records(b'<!DOCTYPE x [<!ENTITY injected SYSTEM "file:///etc/passwd">]><PubmedArticleSet/>', set(), 'endodontic diagnosis')


@pytest.mark.parametrize('raw', [
    b'<eFetchResult><ERROR>Unable to obtain query</ERROR></eFetchResult>',
    b'<PubmedArticleSet/>',
])
def test_error_or_incomplete_efetch_does_not_replace_existing_catalogue(tmp_path, raw):
    from scripts.build_voice_literature import build
    path = tmp_path / 'literature.sqlite'
    path.write_bytes(b'existing-catalogue')
    def get(utility, params):
        return b'{"esearchresult":{"idlist":["123"]}}' if utility == 'esearch.fcgi' else raw
    with pytest.raises(ValueError):
        build(path, topic_ids=['endodontic diagnosis'], get=get)
    assert path.read_bytes() == b'existing-catalogue'
