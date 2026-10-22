"""On-demand official label lookup. Only bounded generic ingredient terms leave the app."""
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from collections import OrderedDict

from app.voice_exam_sources import _NoRedirect

_cache = OrderedDict()
_lock = threading.Lock()
_capacity = threading.BoundedSemaphore(2)
BASE = 'https://dailymed.nlm.nih.gov/dailymed/'


def _read(path, limit):
    # All paths are constructed here from validated terms/UUIDs; never model URLs.
    request = urllib.request.Request(BASE + path, headers={'User-Agent': 'DentalAI-SourceLookup/1.0'})
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=8) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit: raise ValueError('Official source exceeds limit')
    return raw


def lookup(term):
    if not isinstance(term, str) or not re.fullmatch(r'[A-Za-z][A-Za-z -]{2,79}', term):
        raise ValueError('Invalid generic ingredient')
    term = term.lower().strip()
    with _lock:
        cached = _cache.get(term)
        if cached and time.monotonic() - cached[0] < 3600:
            _cache.move_to_end(term); return cached[1]
    if not _capacity.acquire(blocking=False): raise ValueError('Source lookup busy')
    try:
        listing = json.loads(_read('services/v2/spls.json?' + urllib.parse.urlencode({
            'drug_name': term, 'name_type': 'generic', 'pagesize': 10}), 128000))
        candidates = listing.get('data', [])
        selected = None
        # Avoid silently replacing a single ingredient with a combination product.
        for item in candidates[:10]:
            title = item.get('title', '').lower()
            if term in title and ' and ' not in title.split('[')[0]:
                selected = item; break
        if not selected: raise ValueError('No unambiguous official label')
        setid = selected.get('setid', '')
        if not re.fullmatch(r'[0-9a-fA-F-]{36}', setid): raise ValueError('Invalid official label identity')
        from scripts.import_voice_drug_labels import parse_spl
        record = parse_spl(_read('services/v2/spls/' + setid + '.xml', 4000000))
        if record['id'] != 'dailymed-' + setid:
            raise ValueError('Official label identity mismatch')
        # Do not cache or transmit patient statements, model clinical context or quotes.
        excerpts = []
        for kind in ('contraindications', 'interactions', 'warnings', 'indications', 'pregnancy', 'lactation', 'specific_populations'):
            for section in record['sections']:
                if section['kind'] != kind: continue
                paragraphs = [p for p in section['paragraphs'] if len(p) <= 2400]
                for paragraph in paragraphs[:2]:
                    excerpts.append(section['title'] + ': ' + paragraph)
        if not excerpts: raise ValueError('No extractable official clinical content')
        result = {key: record[key] for key in ('id', 'institution', 'title', 'url', 'retrieved_at', 'version', 'effective_date', 'jurisdiction')}
        result['excerpts'] = excerpts[:10]
        result['matched_aliases'] = [term]
        result['limitations'] = 'Selected US product/formulation label; not a Turkish approval or comprehensive interaction check.'
        with _lock:
            _cache[term] = (time.monotonic(), result)
            while len(_cache) > 128: _cache.popitem(last=False)
        return result
    finally:
        _capacity.release()


def retrieve_requests(requests):
    references, unavailable = [], []
    # More terms remain explicitly uncovered instead of silently being cleared.
    terms = list(dict.fromkeys(item['term'] for item in requests))
    for term in terms[:3]:
        try: references.append(lookup(term))
        except Exception: unavailable.append('drug:' + term)
    unavailable.extend('drug:' + term for term in terms[3:])
    return references, unavailable
