"""Read an operator-imported public drug-label corpus; no patient data leaves the app."""
import json
import os
import re
import threading
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

_lock = threading.Lock()
_cached = None
DEFAULT_CORPUS = Path(__file__).parent / 'data' / 'voice_drug_sources.jsonl'


def folded(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold().replace('ı', 'i')) if not unicodedata.combining(c))


def _load():
    global _cached
    path = Path(os.getenv('VOICE_EXAM_DRUG_CORPUS') or DEFAULT_CORPUS)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return []
    # Bounded file and entries; collection is an offline operation, not a request job.
    if stat.st_size > 64 * 1024 * 1024:
        raise ValueError('Drug corpus exceeds configured implementation limit')
    signature = (str(path), stat.st_mtime_ns, stat.st_size)
    with _lock:
        if _cached and _cached[0] == signature:
            return _cached[1]
        records = []
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                if len(line) > 1000000:
                    raise ValueError('Drug record exceeds limit')
                if not line.strip(): continue
                item = json.loads(line)
                url = urlsplit(item['url'])
                if url.scheme != 'https' or url.hostname not in {'dailymed.nlm.nih.gov', 'www.titck.gov.tr', 'titck.gov.tr'}:
                    raise ValueError('Unapproved drug document source')
                if not isinstance(item.get('aliases'), list) or not isinstance(item.get('sections'), list):
                    raise ValueError('Invalid drug document')
                records.append(item)
                if len(records) > 10000:
                    raise ValueError('Drug corpus record limit')
        _cached = (signature, records)
        return records


def retrieve_drugs(query, limit=3):
    text = folded(query)
    references = []
    for item in _load():
        matches = [a for a in item['aliases'] if len(a) >= 3 and re.search(r'(?<!\w)' + re.escape(folded(a)) + r'(?!\w)', text)]
        if not matches: continue
        # Preserve section titles and complete bounded paragraphs, never fabricate
        # a contraindication or conflate an absence of evidence with safety.
        sections = item['sections']
        ordered = sorted(sections, key=lambda section: (section['kind'] not in {'contraindications', 'interactions', 'warnings'}, section['kind']))
        excerpts = []
        for section in ordered:
            for paragraph in section['paragraphs']:
                if len(paragraph) <= 2400 and paragraph.strip():
                    excerpts.append(section['title'] + ': ' + paragraph)
                    break
        references.append({'id': item['id'], 'institution': item['institution'], 'title': item['title'],
            'url': item['url'], 'retrieved_at': item['retrieved_at'], 'effective_date': item.get('effective_date'),
            'version': item.get('version'), 'jurisdiction': item.get('jurisdiction'),
            'matched_aliases': matches, 'excerpts': excerpts[:6],
            'limitations': 'Product-specific foreign label where marked US; verify formulation, indication and Turkish KÜB. Not a complete interaction checker.'})
    return references[:limit]
