"""Conservative source relevance and visible gaps, never material safety rules."""
import re
from app.voice_exam_taxonomy import TOPIC_REGISTRY

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


def relevant_passage(topic, quote):
    normalized = re.sub(r'[-‐‑–—]', ' ', quote.casefold())
    return any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', normalized)
               for term in _TERMS.get(topic, ()))


def review_status(items, selected):
    return [{'topic': row['id'], 'label': row['label'],
             'status': 'control_point_present' if any(item.get('review_topic') == row['id'] for item in items) else 'unverified',
             'source_ids': sorted({item['source_id'] for item in items if item.get('review_topic') == row['id']})}
            for row in selected]
