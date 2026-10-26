"""Build a bounded, complete replacement snapshot outside the examination path.

Run: python -m scripts.build_voice_literature --db /persistent/literature.sqlite
No patient input, no credentials in output, no automatic production scheduling.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import re
import xml.etree.ElementTree as ET

from app.voice_exam_evidence import quality_metadata
from app.voice_exam_literature import TOPICS, TOPIC_SEARCHES, _get
from app.voice_literature_index import publish


def parse_records(raw, requested, topic):
    # EFetch normally declares an external public DTD. ElementTree does not
    # retrieve that DTD. Reject internal subsets/entities, not the normal header.
    if b'<!ENTITY' in raw.upper() or re.search(br'<!DOCTYPE[^>]*\[', raw, re.I):
        raise ValueError('Unsafe literature XML')
    root = ET.fromstring(raw)
    articles = root.findall('PubmedArticle')
    received = {article.findtext('MedlineCitation/PMID', '') for article in articles}
    if root.tag != 'PubmedArticleSet' or root.find('.//ERROR') is not None or not requested <= received:
        raise ValueError('Incomplete or invalid PubMed batch; previous catalogue retained')
    refs = []
    for article in articles:
        ident = article.findtext('.//MedlineCitation/PMID', '')
        if ident not in requested:
            continue
        corrections = {node.get('RefType') for node in article.findall('.//CommentsCorrections')}
        if corrections & {'RetractionIn', 'ExpressionOfConcernIn', 'RetractedandRepublishedIn'}:
            continue
        title_node = article.find('.//ArticleTitle')
        if title_node is None:
            continue
        title = ''.join(title_node.itertext()).strip()
        types = [node.text or '' for node in article.findall('.//PublicationType')]
        date = article.findtext('.//JournalIssue/PubDate/Year') or article.findtext('.//ArticleDate/Year')
        quality = quality_metadata(title, types, date)
        if quality is None:
            continue
        mesh = {node.text for node in article.findall('.//MeshHeading/DescriptorName')}
        if ('Animals' in mesh and 'Humans' not in mesh) or corrections & {'ErratumIn', 'CorrectedandRepublishedIn'}:
            quality['clinical_use'] = False
        excerpts = [''.join(node.itertext()).strip() for node in article.findall('.//Abstract/AbstractText')]
        excerpts = [text for text in excerpts if text]
        if not excerpts:
            continue
        refs.append({'id': 'pubmed-' + ident, 'institution': 'PubMed', 'title': title,
            'url': 'https://pubmed.ncbi.nlm.nih.gov/' + ident + '/', 'excerpts': excerpts,
            'doi': next((node.text for node in article.findall('.//ArticleId') if node.get('IdType') == 'doi'), '') or '',
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'matched_topics': [topic],
            'evidence_type': 'indexed_abstract', **quality})
    return refs


def build(path, *, topic_ids=None, get=None, per_topic=200):
    get = get or _get
    allowed = {topic for topic, _ in TOPICS}
    selected = list(dict.fromkeys(topic_ids if topic_ids is not None else [t for t, _ in TOPICS]))
    if not selected or any(topic not in allowed for topic in selected) or not 1 <= per_topic <= 200:
        raise ValueError('Invalid closed taxonomy selection or build size')
    refs = {}; counts = {}
    # Build entirely before publishing. A failed topic never overwrites the last
    # usable snapshot. Rebuilds revalidate records and drop all stale memberships.
    for topic in selected:
        query = '(' + TOPIC_SEARCHES.get(topic, topic) + ') AND (dentistry OR dental OR oral) AND (guideline[pt] OR systematic review[pt] OR meta-analysis[pt]) AND hasabstract NOT (retracted publication[pt] OR retraction of publication[pt])'
        listing = json.loads(get('esearch.fcgi', {'term': query, 'retmode': 'json', 'retmax': per_topic, 'sort': 'relevance'}))
        ids = listing['esearchresult']['idlist']
        if not isinstance(ids, list) or len(ids) > per_topic or any(not isinstance(i, str) or not re.fullmatch(r'\d{1,12}', i) for i in ids):
            raise ValueError('Invalid PubMed search result')
        count = 0
        for offset in range(0, len(ids), 10):
            batch = ids[offset:offset+10]
            raw = get('efetch.fcgi', {'id': ','.join(batch), 'retmode': 'xml', 'rettype': 'abstract'})
            for ref in parse_records(raw, set(batch), topic):
                previous = refs.get(ref['id'])
                if previous:
                    previous['matched_topics'] = list(dict.fromkeys(previous['matched_topics'] + [topic]))
                else:
                    refs[ref['id']] = ref
                count += 1
        counts[topic] = {'found': len(ids), 'stored': count}
    publish(path, list(refs.values()))
    return {'stored': len(refs), 'topics': counts, 'coverage': 'bounded_snapshot',
            'notice': 'Fixed topic queries; at most 200 results per topic. Not comprehensive evidence coverage.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.db), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
