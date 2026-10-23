"""Bounded PubMed abstracts selected by clinical concepts, never patient text."""
import json
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# Queries contain only these public clinical concepts, not names or verbatim speech.
TOPICS = (
    ('endodontic diagnosis', ('ağrı', 'sızl', 'soğuk', 'sıcak', 'pulp', 'kanal')),
    ('dental caries diagnosis management', ('çürük', 'dolgu', 'restorasyon')),
    ('diabetes dental treatment', ('şeker', 'diyabet', 'metformin', 'insülin')),
    ('drug allergy dental treatment', ('alerji', 'döküntü', 'anafilaksi')),
    ('dental anxiety management', ('kork', 'kaygı', 'anksiyete')),
    ('periodontitis diagnosis treatment', ('periodont', 'diş eti', 'dişeti', 'mobilite')),
    ('dental implant assessment', ('implant',)),
    ('tooth extraction complications', ('çekim', 'çekil')),
    ('dental trauma management', ('travma', 'kırık', 'avülsiyon')),
    ('oral mucosal lesion diagnosis', ('lezyon', 'ülser', 'yara', 'beyaz plak')),
    ('pregnancy dental care', ('gebe', 'hamile', 'emzir')),
    ('anticoagulants dental procedures', ('kan sulandır', 'warfarin', 'antikoag', 'apiksaban')),
    ('antiresorptive medication osteonecrosis jaw', ('bifosfonat', 'denosumab', 'osteonekroz')),
    ('odontogenic infection management', ('şişlik', 'apse', 'enfeksiyon', 'ateş')),
    ('dental radiography selection', ('röntgen', 'film', 'radyograf')),
    ('temporomandibular disorders diagnosis', ('çene eklem', 'bruksizm', 'diş sık')),
)
_lock = threading.Lock()
_request_lock = threading.Lock()
_capacity = threading.BoundedSemaphore(1)
_cache = {}
_last_request = 0.0


def _get(utility, params):
    global _last_request
    url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/' + utility + '?' + urllib.parse.urlencode(
        {'db': 'pubmed', 'tool': 'DentalAI', **params})
    # Serialize calls process-wide to respect NCBI's public 3 requests/sec limit.
    with _request_lock:
        time.sleep(max(0, .35 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
        from app.voice_exam_sources import _NoRedirect
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(urllib.request.Request(url, headers={'User-Agent': 'DentalAI-Literature/1.0'}), timeout=5) as response:
            raw = response.read(256001)
    if len(raw) > 256000:
        raise ValueError('Literature response exceeds limit')
    return raw


def retrieve_literature(text, topics=None):
    allowed = {query for query, _ in TOPICS}
    selected = list(dict.fromkeys([item['topic'] for item in (topics or []) if item.get('topic') in allowed] +
        [query for query, triggers in TOPICS if any(t in text.casefold() for t in triggers)]))[:6]
    if not selected:
        return [], []
    # One combined search and one abstract fetch, regardless of selected topic count.
    query = '(' + ' OR '.join('(' + q + ')' for q in selected) + ') AND (dentistry OR dental OR oral) AND (guideline[pt] OR systematic review[pt] OR meta-analysis[pt]) NOT (retracted publication[pt])'
    with _lock:
        cached = _cache.get(query)
        if cached and time.monotonic() - cached[0] < 86400:
            return cached[1], []
    if not _capacity.acquire(blocking=False):
        return [], ['pubmed-busy']
    try:
        ids = json.loads(_get('esearch.fcgi', {'term': query, 'retmode': 'json', 'retmax': 6, 'sort': 'relevance'}))['esearchresult']['idlist']
        if not isinstance(ids, list) or len(ids) > 6 or any(not re.fullmatch(r'\d{1,12}', str(i)) for i in ids):
            raise ValueError('Invalid PubMed identifiers')
        refs = []
        if ids:
            raw = _get('efetch.fcgi', {'id': ','.join(ids), 'retmode': 'xml', 'rettype': 'abstract'})
            if b'<!ENTITY' in raw.upper():
                raise ValueError('Unexpected XML entity')
            for article in ET.fromstring(raw).findall('.//PubmedArticle'):
                pmid = article.findtext('.//MedlineCitation/PMID', '')
                if pmid not in ids:
                    continue
                title = ''.join(article.find('.//ArticleTitle').itertext())
                excerpts = [''.join(node.itertext()).strip()[:1800] for node in article.findall('.//Abstract/AbstractText')]
                excerpts = [s for s in excerpts if len(s) >= 80][:3]
                if not excerpts:
                    continue
                refs.append({'id': 'pubmed-' + pmid, 'institution': 'PubMed · ' + article.findtext('.//Journal/Title', ''),
                             'title': title[:500], 'url': 'https://pubmed.ncbi.nlm.nih.gov/' + pmid + '/',
                             'retrieved_at': datetime.now(timezone.utc).isoformat(), 'excerpts': excerpts,
                             'evidence_type': 'indexed_abstract'})
        with _lock:
            if len(_cache) >= 128:
                _cache.pop(next(iter(_cache)))
            _cache[query] = (time.monotonic(), refs)
        return refs, ([] if refs else ['pubmed-no-matching-abstract'])
    except Exception:
        return [], ['pubmed-unavailable']
    finally:
        _capacity.release()
