"""Fetch bounded clinical excerpts from fixed professional sources. No patient query leaves the app."""
import re
import logging
from collections import OrderedDict
from concurrent.futures import wait
from app.voice_source_pool import BoundedPool
import threading
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

# Fixed document URLs only: user/model text cannot become a URL or redirect target.
DOCUMENTS = (
    ('sdcep-drug-interactions', 'SDCEP', 'Drug interactions in dental prescribing',
     'https://sdcepdentalprescribing.nhs.scot/guidance/supporting-tools/drug-interactions/',
     ('ilaç', 'antibiyotik', 'drug'), ('macrolide', 'statin', 'interaction', 'prescribe')),
    ('sps-macrolides-statins', 'NHS SPS', 'Managing interactions between macrolides and statins',
     'https://sps.nhs.uk/articles/managing-interactions-between-macrolides-and-statins/',
     ('statin', 'klaritromisin', 'clarithromycin', 'eritromisin', 'erythromycin'),
     ('clarithromycin', 'simvastatin', 'rosuvastatin', 'contraindicated')),
    ('gdc-communication', 'General Dental Council', 'Communicate effectively with patients',
     'https://standards.gdc-uk.org/pages/principle2/principle2',
     ('communication needs',), ('understand', 'listen', 'cost', 'information')),
    ('ada-pain-guideline', 'ADA', 'Acute Dental Pain Management Guideline',
     'https://www.ada.org/resources/research/science/evidence-based-dental-research/pain-management-guideline',
     ('ağrı', 'sızl', 'soğuk', 'endodontic diagnosis'), ('toothache', 'recommend', 'treatment', 'adolescent')),
    ('ada-antibiotics-guideline', 'ADA', 'Antibiotics for Dental Pain and Swelling Guideline (2019)',
     'https://www.ada.org/resources/research/science/evidence-based-dental-research/antibiotics-for-dental-pain-and-swelling',
     ('apse', 'şişlik', 'enfeksiyon', 'odontogenic infection management'), ('pulpal', 'systemic', 'antibiotic', 'treatment')),
    ('ada-caries-guideline', 'ADA', 'Restorative Treatments for Caries Lesions Guideline (2023)',
     'https://www.ada.org/resources/research/science/evidence-based-dental-research/caries-management-clinical-practice-guidelines/evidence-based-clinical-practice-guideline-on-restorative-treatments-for-caries-lesions',
     ('çürük', 'dolgu', 'dental caries diagnosis management'), ('caries', 'permanent', 'primary', 'restorative')),
    ('ada-pregnancy', 'ADA', 'Pregnancy', 'https://www.ada.org/resources/ada-library/oral-health-topics/pregnancy',
     ('gebelik', 'gebe', 'hamile', 'emzir'), ('pregnan', 'dental', 'consultation', 'medication')),
    ('ada-hypertension', 'ADA', 'Hypertension', 'https://www.ada.org/resources/ada-library/oral-health-topics/hypertension',
     ('hipertansiyon', 'tansiyon', 'kan basın'), ('dental', 'blood pressure', 'vasoconstrictor', 'cardiovascular')),
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
     ('bifosfonat', 'bisfosfonat', 'denosumab', 'alendronat', 'zoledron', 'osteoporoz', 'osteonekroz',
      'kemik erimesi', 'risedronat', 'ibandronat', 'antiresorptive medication osteonecrosis jaw'),
     ('dental', 'risk', 'extraction', 'antiresorptive')),
)
_lock = threading.RLock()
_cache = OrderedDict()
_inflight = {}
_doc_pool = BoundedPool(6, 12, 'voice-document')
_group_pool = BoundedPool(4, 8, 'voice-source')
DOCUMENT_TIMEOUT = 12
GROUP_TIMEOUT = 16
EXCERPT_BUDGET = 40000
log = logging.getLogger(__name__)


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
        if cached and time.monotonic() - cached[0] < (3600 if cached[1] is not None else 600):
            if cached[1] is None:
                raise ValueError('Source failure cached')
            return dict(cached[1])
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
    paragraphs = [p for p in paragraphs if len(p) >= 25]
    ranked = sorted(enumerate(paragraphs), key=lambda pair: (-sum(t in pair[1].casefold() for t in terms), pair[0]))
    excerpts = [text[:1800] for _, text in ranked[:5] if any(t in text.casefold() for t in terms)]
    if not excerpts:
        raise ValueError('No clinical excerpt')
    result = dict(id=ident, institution=institution, title=title, url=url,
                  retrieved_at=datetime.now(timezone.utc).isoformat(), excerpts=excerpts,
                  evidence_level='guideline' if ident.endswith('-guideline') else 'professional_information',
                  evidence_type='professional_document', clinical_use=True)
    with _lock:
        _cache[ident] = (time.monotonic(), result)
    return result


def _fetch_many(documents):
    futures = {}; found = {}; missing = []
    def completed(ident, future):
        with _lock:
            try:
                value = future.result()
            except Exception:
                value = None
            _cache[ident] = (time.monotonic(), value)
            _cache.move_to_end(ident)
            while len(_cache) > 64:
                _cache.popitem(last=False)
            _inflight.pop(ident, None)
    for doc in documents:
        ident = doc[0]
        with _lock:
            cached = _cache.get(ident)
            if cached and time.monotonic() - cached[0] < (3600 if cached[1] is not None else 600):
                if cached[1] is None: missing.append(ident)
                else: found[ident] = dict(cached[1])
                continue
            future = _inflight.get(ident)
            if future is None:
                future = _doc_pool.submit(_fetch, doc)
                if future is not None:
                    _inflight[ident] = future
                    future.add_done_callback(lambda f, ident=ident: completed(ident, f))
            if future is None:
                missing.append(ident)
            else:
                futures[future] = ident
    done, _ = wait(futures, timeout=DOCUMENT_TIMEOUT) if futures else (set(), set())
    for future, ident in futures.items():
        if future in done and not future.cancelled() and future.exception() is None:
            found[ident] = future.result()
        else:
            missing.append(ident)
    # Timed-out shared requests keep their slots until actual completion. Admission
    # is bounded and later reviews share the same future, never an unbounded queue.
    return [found[doc[0]] for doc in documents if doc[0] in found], missing


def _run_groups(groups):
    def run(name, fn):
        started = time.monotonic()
        try: return fn()
        finally: log.info('voice_sources group=%s seconds=%.2f', name, time.monotonic() - started)
    futures = {name: _group_pool.submit(run, name, fn) for name, fn in groups.items()}
    admitted = [f for f in futures.values() if f is not None]
    done, _ = wait(admitted, timeout=GROUP_TIMEOUT) if admitted else (set(), set())
    results = {}
    for name, future in futures.items():
        if future is not None and future in done and not future.cancelled() and future.exception() is None:
            results[name] = future.result()
        else:
            if future is not None: future.cancel()  # queued work only; running work keeps its slot
            results[name] = ([], ['group:' + name])
    return results


def _apply_budget(references):
    used = 0; result = []
    for ref in references:
        kept = []
        for excerpt in ref.get('excerpts', []):
            if used + len(excerpt) <= EXCERPT_BUDGET:
                kept.append(excerpt); used += len(excerpt)
        if kept: result.append(dict(ref, excerpts=kept))
    return result


def retrieve(query, requests=None, topics=None):
    """Topic selection is limited and must never be represented as comprehensive clearance."""
    text = (query + ' ' + ' '.join(item.get('topic', '') for item in (topics or []))).casefold()
    selected = [doc for doc in DOCUMENTS if any(term in text for term in doc[4])]
    started = time.monotonic()
    from app.voice_exam_literature import retrieve_literature
    from app.voice_exam_dergipark import retrieve_dergipark
    groups = {
        'documents': lambda: _fetch_many(selected),
        'literature': lambda: retrieve_literature(query, topics=topics),
        'dergipark': lambda: retrieve_dergipark(query, topics=topics),
    }
    if requests:
        from app.voice_exam_live_sources import retrieve_requests
        groups['requests'] = lambda: retrieve_requests(requests)
    references = []; unavailable = []
    for found, missing in _run_groups(groups).values():
        references.extend(found); unavailable.extend(missing)
    try:
        from app.voice_exam_drugs import retrieve_drugs
        # Existing small corpus is only a fallback; no bulk loading is required.
        existing = {item['id'] for item in references}
        references.extend(item for item in retrieve_drugs(query) if item['id'] not in existing)
    except Exception:
        unavailable.append('local-drug-corpus')
    # A paper indexed in two services must not inflate the evidence count.
    unique = []; seen = set()
    for ref in references:
        doi = ref.get('doi', '').casefold().strip().removeprefix('https://doi.org/')
        key = 'doi:' + doi if doi else ref['id']
        if key not in seen:
            unique.append(ref); seen.add(key)
    references = _apply_budget(unique)
    if sum(len(x) for r in references for x in r['excerpts']) < sum(len(x) for r in unique for x in r['excerpts']):
        unavailable.append('source-text-budget')
    log.info('voice_sources total_seconds=%.2f refs=%d unavailable=%d', time.monotonic() - started, len(references), len(unavailable))
    from app.voice_exam_literature import TOPIC_LABELS
    for ref in references:
        ref['topic_labels'] = [TOPIC_LABELS.get(topic, topic) for topic in ref.get('matched_topics', [])]
    return {'references': references, 'unavailable': unavailable,
            'coverage': 'limited',
            'notice': 'Konuya göre seçilmiş meslek kuruluşu belgeleri, PubMed ve seçilmiş DergiPark diş hekimliği dergilerinin yayın özetleri değerlendirilir; kapsamlı sistematik tarama değildir. DergiPark keşfi sınırlı bir güncellenmiş kayıt penceresidir; tüm arşivi kapsamaz. Dizin/barındırma bilgisi tek başına bilimsel doğruluk onayı değildir. Yayının PubMed’de indekslenmesi tek başına öneriyi doğrulamaz; tam metin ve hastaya uygunluk hekim tarafından kontrol edilmelidir. DailyMed kayıtları ABD ürün belgeleridir; Türkiye’deki ürünün etken maddesi, formu ve güncel KÜB’ü ayrıca doğrulanmalıdır. Kaynak bulunmaması klinik güvenlik onayı değildir. Bu sistem tüm ilaç etkileşimlerini kapsamaz. Belge alıntısını ve hastaya uygunluğunu hekim doğrulamalıdır.'}


