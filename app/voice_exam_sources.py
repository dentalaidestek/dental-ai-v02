"""Fetch bounded clinical excerpts from fixed professional sources. No patient query leaves the app."""
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

# Fixed document URLs only: user/model text cannot become a URL or redirect target.
DOCUMENTS = (
    ('ada-diabetes', 'ADA', 'Diabetes', 'https://www.ada.org/resources/ada-library/oral-health-topics/diabetes',
     ('diyabet', 'diabet', 'şeker', 'metformin', 'insülin'), ('dental', 'treatment', 'glycemic', 'hypoglycemia')),
    ('ada-prophylaxis', 'ADA', 'Antibiotic Prophylaxis Prior to Dental Procedures',
     'https://www.ada.org/resources/ada-library/oral-health-topics/antibiotic-prophylaxis',
     ('profilaksi', 'endokardit', 'kalp kapa', 'protez kapak', 'eklem protez'), ('patient', 'cardiac', 'prophylaxis', 'consultation')),
    ('ada-anticoagulants', 'ADA', 'Oral Anticoagulant and Antiplatelet Medications and Dental Procedures',
     'https://www.ada.org/resources/ada-library/oral-health-topics/oral-anticoagulant-and-antiplatelet-medications-and-dental-procedures',
     ('antikoag', 'kan sulandır', 'warfarin', 'apiksaban', 'rivaroksaban', 'dabigatran', 'klopidogrel', 'aspirin'),
     ('dental', 'bleeding', 'physician', 'risk')),
    ('ada-mronj', 'ADA', 'Osteoporosis Medications and Medication-Related Osteonecrosis of the Jaw',
     'https://www.ada.org/resources/ada-library/oral-health-topics/osteoporosis-medications',
     ('bifosfonat', 'bisfosfonat', 'denosumab', 'alendronat', 'zoledron', 'osteoporoz', 'osteonekroz'),
     ('dental', 'risk', 'extraction', 'antiresorptive')),
)
_lock = threading.Lock()
_cache = {}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip = 0; self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'nav', 'footer', 'header'}:
            self.skip += 1
        if tag in {'p', 'li', 'h1', 'h2', 'h3', 'br'} and not self.skip:
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'nav', 'footer', 'header'} and self.skip:
            self.skip -= 1
        if tag in {'p', 'li', 'h1', 'h2', 'h3'} and not self.skip:
            self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(document):
    ident, institution, title, url, triggers, terms = document
    with _lock:
        cached = _cache.get(ident)
        if cached and time.monotonic() - cached[0] < 3600:
            return cached[1]
    # Dedicated opener: redirects refused, bounded input, no PHI in URL/headers.
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers={'User-Agent': 'DentalAI-ClinicalSource/1.0', 'Accept': 'text/html'})
    with opener.open(request, timeout=8) as response:
        if 'text/html' not in response.headers.get('Content-Type', ''):
            raise ValueError('Unsupported source format')
        raw = response.read(512001)
    if len(raw) > 512000:
        raise ValueError('Source exceeds limit')
    parser = _Text(); parser.feed(raw.decode('utf-8', errors='replace'))
    paragraphs = [' '.join(p.split()) for p in ''.join(parser.parts).split('\n')]
    paragraphs = [p for p in paragraphs if len(p) >= 80]
    ranked = sorted(enumerate(paragraphs), key=lambda pair: (-sum(t in pair[1].casefold() for t in terms), pair[0]))
    excerpts = [text[:1800] for _, text in ranked[:5] if any(t in text.casefold() for t in terms)]
    if not excerpts:
        raise ValueError('No clinical excerpt')
    result = dict(id=ident, institution=institution, title=title, url=url,
                  retrieved_at=datetime.now(timezone.utc).isoformat(), excerpts=excerpts)
    with _lock:
        _cache[ident] = (time.monotonic(), result)
    return result


def retrieve(query):
    """Topic selection is limited and must never be represented as comprehensive clearance."""
    text = query.casefold()
    selected = [doc for doc in DOCUMENTS if any(term in text for term in doc[4])][:3]
    references = []; unavailable = []
    for doc in selected:
        try:
            references.append(_fetch(doc))
        except Exception:
            unavailable.append(doc[0])
    return {'references': references, 'unavailable': unavailable,
            'coverage': 'limited',
            'notice': 'Sınırlı resmî belge kapsamı. Kaynak bulunmaması klinik güvenlik onayı değildir. Belge alıntısını ve hastaya uygunluğunu hekim doğrulamalıdır.'}
