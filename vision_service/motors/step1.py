"""Step 1 candidate adapter. No runtime/clinical approval or weight availability claim.

Source: https://universe.roboflow.com/prime-snf1v/step-1-o18pv
Project labels are not proof that every label is supported by model version 6.
Only named predictions may be adapted; numeric class IDs are never guessed.
"""
import math
from vision_service.motors.catalog import FINDING_CATALOG

MODEL_ID = 'step-1-o18pv/6'
RAW_TO_CANONICAL = {
    'Supernumerary tooth': 'SUPERNUMERARY_TOOTH',
    'External resorption': 'EXTERNAL_ROOT_RESORPTION',
    'Internal resorption': 'INTERNAL_ROOT_RESORPTION',
    'Root fracture': 'ROOT_FRACTURE',
    'Horizontal bone loss': 'HORIZONTAL_BONE_LOSS',
    'Vertical bone loss': 'VERTICAL_BONE_LOSS',
    'Calculus': 'CALCULUS',
    'Pontic': 'PONTIC',
    'Post': 'ENDO_POST',
    'Post-Core Restorasyon': 'ENDO_POST',
    'Signs of secondary caries': 'RECURRENT_CARIES',
    'Yetersiz canal filling': 'UNDERFILLED_ROOT_CANAL',
    'Dilaserasgon': 'ROOT_DILACERATION',
    'Fractured crown': 'TOOTH_FRACTURE',
    'Signs of caries': 'CARIES',
    'Artifical crown': 'CROWN',
    'Implant': 'IMPLANT',
    'Filling': 'FILLING',
    'Endodontically treated teeth': 'ROOT_CANAL_TREATED',
    'Impacted tooth': 'IMPACTED_TOOTH',
    'Braces': 'ORTHODONTIC_APPLIANCE',
    'Retainer': 'ORTHODONTIC_APPLIANCE',
}
RAW_TO_HELPER = {
    'Periodontal bone loss': 'BONE_LOSS_GENERIC',
    'Decidious teeth': 'PRIMARY_TOOTH_HELPER',
    'Germ': 'TOOTH_GERM_HELPER',
    'Lesion': 'UNSPECIFIED_LESION_HELPER',
    'Furcation lesion': 'FURCATION_LESION_CANDIDATE',
    'Cystic lesion': 'CYSTIC_LESION_CANDIDATE',
    'Apical lesion': 'APICAL_LESION_CANDIDATE',
    'Apical Lesion': 'APICAL_LESION_CANDIDATE',
}

def normalize_class(raw_class, **_):
    raw = str(raw_class or '').strip()
    if raw in RAW_TO_CANONICAL:
        return {'type': 'finding', 'finding_code': RAW_TO_CANONICAL[raw]}
    if raw in RAW_TO_HELPER:
        return {'type': 'helper', 'signal': RAW_TO_HELPER[raw]}
    return {'type': 'unknown', 'raw_class': raw}

def adapt_predictions(payload, *, threshold):
    """Convert documented Roboflow xywh response into internal candidate records.

    The caller must explicitly supply a calibrated threshold. Unknown labels
    are returned separately for backend audit, never shown as clinical findings.
    This function does not download a model or send images anywhere.
    """
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('invalid threshold')
    findings, helpers, rejected = [], [], []
    for pred in payload.get('predictions', []):
        raw = pred.get('class')
        mapped = normalize_class(raw)
        if mapped['type'] == 'unknown':
            rejected.append({'raw_class': raw, 'reason': 'unmapped_label'})
            continue
        try:
            x, y, w, h, confidence = (float(pred[k]) for k in ('x','y','width','height','confidence'))
            if not all(math.isfinite(v) for v in (x,y,w,h,confidence)) or w <= 0 or h <= 0 or not 0 <= confidence <= 1:
                raise ValueError('invalid geometry or score')
        except (KeyError, TypeError, ValueError):
            rejected.append({'raw_class': raw, 'reason': 'invalid_prediction'})
            continue
        if confidence < threshold:
            continue
        base = {'raw_class': raw, 'motor': 'step1', 'model_id': MODEL_ID,
                'confidence': confidence, 'bbox': [x-w/2,y-h/2,x+w/2,y+h/2],
                'validation_status': 'CANDIDATE_NOT_VALIDATED'}
        if mapped['type'] == 'finding':
            code = mapped['finding_code']
            label, category = FINDING_CATALOG[code]
            findings.append({**base, 'finding_code': code, 'label': label, 'category': category})
        else:
            helpers.append({**base, 'signal': mapped['signal']})
    return findings, helpers, rejected
