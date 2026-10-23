"""Selected dental journals via public OAI metadata; bounded, cached discovery.

DergiPark hosting/index membership is not an article-level quality certificate.
Only article-page metadata, not OAI submission dates, supplies publication dates.
"""
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

from app.voice_exam_evidence import quality_metadata
from app.voice_exam_literature import TOPICS, selected_topics

JOURNALS = {
    'selcukdentj': {'title': 'Selcuk Dental Journal', 'issn': '2148-7529',
                   'policy_url': 'https://dergipark.org.tr/en/pub/selcukdentj/indexes'},
    'adoklinikbilimler': {'title': 'ADO Klinik Bilimler Dergisi', 'issn': '1307-3540',
                        'policy_url': 'https://dergipark.org.tr/tr/pub/adoklinikbilimler/indexes'},
}
NS = {'o': 'http://www.openarchives.org/OAI/2.0/', 'dc': 'http://purl.org/dc/elements/1.1/'}
_cache = {}
_lock = threading.Lock()
_capacity = threading.BoundedSemaphore(1)


def _read(url, limit):
    # All callers construct fixed-host URLs from journal allowlists/numeric IDs.
    from app.voice_exam_sources import _NoRedirect
    with urllib.request.build_opener(_NoRedirect()).open(urllib.request.Request(
            url, headers={'User-Agent': 'DentalAI-Literature/1.0'}), timeout=5) as response:
        data = response.read(limit + 1)
    if len(data) > limit: raise ValueError('DergiPark response exceeds limit')
    return data


def _cached(key, fetch):
    with _lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < 86400: return cached[1]
    result = fetch()
    with _lock:
        if len(_cache) >= 128: _cache.pop(next(iter(_cache)))
        _cache[key] = (time.monotonic(), result)
    return result


def _catalogue(journal):
    def fetch():
        since = (datetime.now(timezone.utc) - timedelta(days=120)).date().isoformat()
        params = {'verb': 'ListRecords', 'metadataPrefix': 'oai_dc', 'set': journal,
                  'from': since + 'T00:00:00Z'}
        raw = _read('https://dergipark.org.tr/api/public/oai/?' + urllib.parse.urlencode(params), 1000000)
        if b'<!ENTITY' in raw.upper() or b'<!DOCTYPE' in raw.upper(): raise ValueError('Unexpected XML declaration')
        root = ET.fromstring(raw)
        error = root.find('o:error', NS)
        if error is not None:
            if error.get('code') == 'noRecordsMatch': return [], False
            raise ValueError('OAI error')
        records = []
        for record in root.findall('.//o:record', NS)[:100]:
            header = record.find('o:header', NS)
            if header is None or header.get('status') == 'deleted': continue
            urls = [n.text or '' for n in record.findall('.//dc:identifier', NS)]
            matches = [re.fullmatch(r'https://dergipark\.org\.tr/(?:tr|en)/pub/' + journal + r'/article/(\d{1,12})', url) for url in urls]
            match = next((m for m in matches if m), None)
            if not match: continue
            title = ' '.join(''.join(n.itertext()).strip() for n in record.findall('.//dc:title', NS))
            # Only potential reviews; verify type again on canonical article page.
            if not any(t in title.casefold() for t in ('review', 'derleme', 'meta-analysis', 'meta analiz', 'guideline')): continue
            description = ' '.join(''.join(n.itertext()).strip() for n in record.findall('.//dc:description', NS))
            records.append({'id': match.group(1), 'title': title, 'text': title + ' ' + description})
        return records, bool(root.findtext('.//o:resumptionToken', '', NS).strip())
    return _cached(('catalogue', journal), fetch)


class _Meta(HTMLParser):
    def __init__(self): super().__init__(); self.values = {}
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name'):
            self.values.setdefault(attrs['name'].casefold(), attrs.get('content', ''))


def _article(journal, ident):
    def fetch():
        url = 'https://dergipark.org.tr/en/pub/' + journal + '/article/' + ident
        parser = _Meta(); parser.feed(_read(url, 300000).decode('utf-8', errors='replace'))
        meta = parser.values
        if meta.get('citation_issn') != JOURNALS[journal]['issn']: raise ValueError('Journal mismatch')
        title = meta.get('citation_title', '')
        date = meta.get('citation_publication_date', '')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date): raise ValueError('Publication date missing')
        if date > datetime.now(timezone.utc).date().isoformat(): raise ValueError('Future publication')
        article_type = meta.get('citation_article_type', '')
        if article_type.casefold() not in {'review', 'derleme', 'systematic review', 'meta-analysis'}:
            return None
        quality = quality_metadata(title, [article_type], date[:4])
        abstract = meta.get('citation_abstract', '').strip()
        if quality is None or len(abstract) < 80: return None
        return {'id': 'dergipark-' + ident, 'institution': 'DergiPark · ' + JOURNALS[journal]['title'],
                'title': title[:500], 'url': url, 'excerpts': [abstract[:2400]],
                'retrieved_at': datetime.now(timezone.utc).isoformat(), 'publication_date': date,
                'doi': meta.get('citation_doi', ''), 'evidence_type': 'journal_abstract',
                'journal_policy_url': JOURNALS[journal]['policy_url'], **quality}
    return _cached(('article', journal, ident), fetch)


def retrieve_dergipark(text, topics=None):
    selected = selected_topics(text, topics)
    if not selected: return [], []
    if not _capacity.acquire(blocking=False): return [], ['dergipark-busy']
    try:
        refs = []; missing = []; candidates = []; deadline = time.monotonic() + 12
        topic_terms = {topic: tuple(t for t in re.findall(r'[a-z]+', topic) if t not in
                       {'dental', 'oral', 'diagnosis', 'management', 'treatment', 'care', 'assessment', 'selection', 'medication'}) +
                       next(triggers for name, triggers in TOPICS if name == topic) for topic in selected}
        for journal in JOURNALS:
            if time.monotonic() > deadline:
                missing.append('dergipark-time-budget'); break
            try:
                records, partial = _catalogue(journal)
                if partial: missing.append('dergipark-partial-catalogue:' + journal)
                candidates = []
                for record in records:
                    matched = [topic for topic, terms in topic_terms.items() if any(t in record['text'].casefold() for t in terms)]
                    if matched:
                        score = sum(any(t in record['title'].casefold() for t in topic_terms[topic]) for topic in matched)
                        strong = any(t in record['title'].casefold() for t in ('systematic review', 'sistematik derleme', 'meta-analysis', 'meta analiz', 'guideline'))
                        candidates.append((score + 3 * strong, record, matched))
                # Resolve a candidate before querying another catalogue, so a cold
                # cache cannot consume the entire deadline on discovery alone.
                if candidates and time.monotonic() <= deadline:
                    _, record, matched = max(candidates, key=lambda row: row[0])
                    try:
                        ref = _article(journal, record['id'])
                        if ref: refs.append({**ref, 'matched_topics': matched})
                    except Exception:
                        missing.append('dergipark-article-unavailable:' + record['id'])
                elif candidates:
                    missing.append('dergipark-time-budget')
            except Exception:
                missing.append('dergipark-unavailable:' + journal)
        for topic in selected:
            if not any(topic in r['matched_topics'] and r['clinical_use'] for r in refs):
                missing.append('dergipark-no-clinical-evidence:' + topic)
        return refs, missing
    finally:
        _capacity.release()
