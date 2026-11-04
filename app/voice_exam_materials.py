"""Conservative source relevance and visible gaps, never material safety rules."""
import re
from urllib.parse import unquote, urlsplit
from app.voice_exam_taxonomy import TOPIC_REGISTRY

VALIDATION_VERSION = 'material-scope-v2'

# Retrieval/relevance vocabulary only. A word match is NOT clinical applicability.
_TERMS = {
    'prosth.zirconia': ('zirconia', 'zirconium', 'zirkonya', 'zirkonyum'),
    'prosth.glass_ceramic': ('lithium disilicate', 'glass ceramic', 'lityum disilikat', 'cam seramik'),
    'prosth.metal_ceramic': ('metal ceramic', 'porcelain fused to metal', 'pfm', 'nickel', 'alloy', 'alaşım'),
    'prosth.veneers': ('veneer', 'veneers', 'laminate', 'lamine'),
    'endo.post_core': ('ferrule', 'post core', 'post and core', 'fiber post', 'fibre post', 'cast post', 'post space', 'post placement', 'post retention', 'intraradicular', 'kalan diş dokusu'),
    'endo.irrigation': ('irrigation', 'irrigant', 'hypochlorite', 'edta', 'chlorhexidine', 'irrigasyon'),
    'endo.obturation': ('sealer', 'sealers', 'obturation', 'gutta percha', 'bioceramic', 'kanal patı'),
    'restorative.materials': ('composite', 'glass ionomer', 'restorative material', 'kompozit', 'cam iyonomer'),
    'perio.regeneration': ('regeneration', 'graft', 'membrane', 'greft', 'membran'),
    'implant.components': ('abutment', 'implant connection', 'implant component', 'implant components', 'platform switching', 'prosthetic connection', 'implant parçası'),
}


def targets(topics):
    ids = {row.get('topic') for row in topics if isinstance(row, dict)}
    return [{'id': ident, 'label': TOPIC_REGISTRY[ident]['label'],
             'scope': TOPIC_REGISTRY[ident]['scope']}
            for ident in _TERMS if ident in ids]


def _relevant_match(topic, quote):
    normalized = re.sub(r'[-‐‑–—]', ' ', quote)
    return next((match for term in _TERMS.get(topic, ())
                 if (match := re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', normalized, re.IGNORECASE))), None)


def relevant_passage(topic, quote):
    return _relevant_match(topic, quote) is not None


def general_material_document(reference):
    # A broad comparison table cannot establish an unmentioned material choice.
    try:
        url = urlsplit(reference.get('url', ''))
        return url.hostname in {'ada.org', 'www.ada.org'} and unquote(url.path).rstrip('/') in {
            '/resources/ada-library/oral-health-topics/materials-for-indirect-restorations',
            '/resources/ada-library/oral-health-topics/materials-for-direct-restorations'}
    except (ValueError, TypeError):
        return False


def review_status(items, selected):
    return [{'topic': row['id'], 'label': row['label'],
             'status': 'control_point_present' if any(item.get('review_topic') == row['id'] for item in items) else 'unverified',
             'source_ids': sorted({item['source_id'] for item in items if item.get('review_topic') == row['id']})}
            for row in selected]


def source_candidates(selected, references):
    """A bounded literal passage per target; relevance is not clinical approval."""
    rows = []
    for target in selected:
        candidates = []
        for reference in references:
            if reference.get('clinical_use') is not True:
                continue
            for passage in reference.get('excerpts', []):
                if isinstance(passage, str) and relevant_passage(target['id'], passage):
                    start = max(0, _relevant_match(target['id'], passage).start() - 500)
                    candidates.append({'source_id': reference['id'], 'source_quote': passage[start:start + 1800]})
                    break
        rows.append({'topic': target['id'], 'candidate_source_count': len(candidates),
                     'candidates': candidates[:1]})
    return rows
