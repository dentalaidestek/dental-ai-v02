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
TOPIC_LABELS = dict(zip((topic for topic, _ in TOPICS), (
    'Endodontik değerlendirme', 'Çürük ve restoratif tedavi', 'Diyabet ve diş tedavisi',
    'İlaç alerjisi', 'Dental kaygı', 'Periodontal değerlendirme', 'İmplant değerlendirmesi',
    'Diş çekimi', 'Dental travma', 'Ağız mukozası lezyonları', 'Gebelikte diş tedavisi',
    'Antikoagülanlar', 'Çene osteonekrozu', 'Odontojenik enfeksiyon', 'Radyografik değerlendirme',
    'Çene eklemi bozuklukları')))
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


def selected_topics(text, topics=None):
    allowed = {query for query, _ in TOPICS}
    return list(dict.fromkeys([item['topic'] for item in (topics or []) if item.get('topic') in allowed] +
        [query for query, triggers in TOPICS if any(t in text.casefold() for t in triggers)]))[:6]


def retrieve_literature(text, topics=None):
    selected = selected_topics(text, topics)
    if not selected:
        return [], []
    key = tuple(selected)
    with _lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < 86400:
            return cached[1], cached[2]
    if not _capacity.acquire(blocking=False):
        return [], ['pubmed-busy']
    try:
        refs = []; missing = []; ids_by_topic = {}; deadline = time.monotonic() + 15
        # Separate searches keep one common topic from consuming every result slot.
        for topic in selected:
            if time.monotonic() > deadline:
                missing.append('pubmed-search-time-budget'); break
            query = '(' + topic + ') AND (dentistry OR dental OR oral) AND (guideline[pt] OR systematic review[pt] OR meta-analysis[pt]) NOT (retracted publication[pt] OR retraction of publication[pt])'
            try:
                ids = json.loads(_get('esearch.fcgi', {'term': query, 'retmode': 'json', 'retmax': 2, 'sort': 'relevance', 'datetype': 'pdat', 'mindate': str(datetime.now(timezone.utc).year - 10)}))['esearchresult']['idlist']
                if not isinstance(ids, list) or len(ids) > 2 or any(not isinstance(i, str) or not re.fullmatch(r'\d{1,12}', i) for i in ids):
                    raise ValueError('Invalid PubMed identifiers')
                for pmid in ids:
                    ids_by_topic.setdefault(pmid, []).append(topic)
                if not ids: missing.append('pubmed-no-match:' + topic)
            except Exception:
                missing.append('pubmed-search-unavailable:' + topic)
        if ids_by_topic:
            raw = _get('efetch.fcgi', {'id': ','.join(ids_by_topic), 'retmode': 'xml', 'rettype': 'abstract'})
            if b'<!ENTITY' in raw.upper():
                raise ValueError('Unexpected XML entity')
            from app.voice_exam_evidence import quality_metadata
            for article in ET.fromstring(raw).findall('.//PubmedArticle'):
                pmid = article.findtext('.//MedlineCitation/PMID', '')
                if pmid not in ids_by_topic:
                    continue
                if any(n.get('RefType') in {'RetractionIn', 'ExpressionOfConcernIn'} for n in article.findall('.//CommentsCorrections')):
                    continue
                title_node = article.find('.//ArticleTitle')
                if title_node is None: continue
                title = ''.join(title_node.itertext())
                types = [n.text or '' for n in article.findall('.//PublicationType')]
                date = article.findtext('.//JournalIssue/PubDate/Year') or article.findtext('.//ArticleDate/Year')
                if not date:
                    match = re.search(r'\b(19|20)\d{2}\b', article.findtext('.//PubDate/MedlineDate', ''))
                    date = match.group() if match else None
                quality = quality_metadata(title, types, date)
                if quality is None: continue
                mesh = {n.text for n in article.findall('.//MeshHeading/DescriptorName')}
                corrections = {n.get('RefType') for n in article.findall('.//CommentsCorrections')}
                if ('Animals' in mesh and 'Humans' not in mesh) or corrections & {'ErratumIn', 'CorrectedandRepublishedIn'}:
                    quality['clinical_use'] = False
                    quality['quality_notice'] = 'Hayvan çalışması veya düzeltme bildirimi var; klinik öneriye dayanak yapılmadı.'
                excerpts = [''.join(node.itertext()).strip()[:1600] for node in article.findall('.//Abstract/AbstractText')]
                excerpts = [s for s in excerpts if len(s) >= 80][:2]
                if not excerpts: continue
                doi = next((n.text for n in article.findall('.//ArticleId') if n.get('IdType') == 'doi'), '')
                refs.append({'id': 'pubmed-' + pmid, 'institution': 'PubMed · ' + article.findtext('.//Journal/Title', ''),
                             'title': title[:500], 'url': 'https://pubmed.ncbi.nlm.nih.gov/' + pmid + '/',
                             'retrieved_at': datetime.now(timezone.utc).isoformat(), 'excerpts': excerpts,
                             'evidence_type': 'indexed_abstract', 'doi': doi, 'matched_topics': ids_by_topic[pmid], **quality})
        for topic in selected:
            if not any(topic in ref['matched_topics'] and ref['clinical_use'] for ref in refs):
                missing.append('pubmed-no-clinical-evidence:' + topic)
        # Preserve partial/error status when cached; do not cache transport failures.
        if not any('unavailable' in item or 'time-budget' in item for item in missing):
            with _lock:
                if len(_cache) >= 128: _cache.pop(next(iter(_cache)))
                _cache[key] = (time.monotonic(), refs, missing)
        return refs, list(dict.fromkeys(missing))
    except Exception:
        return [], ['pubmed-unavailable']
    finally:
        _capacity.release()
