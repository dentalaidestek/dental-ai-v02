"""Shared build identity for web readiness and durable source indexing."""
import hashlib
import json
import os
from app.study_local_ocr import LOCAL_OCR_ENGINE_VERSION


def _bounded_env(name, default, low, high):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(value, high))


def index_fingerprint():
    payload = {
        'schema': 'academic-v2-dental-semantics-10',
        'retrieval_profile': 'fts-local-v1',
        'chunk_profile': 'dental-page-v3-layout-heading-paths',
        'embedding_provider': None, 'embedding_model': None, 'embedding_dimensions': None,
        'ocr_provider': (os.getenv('STUDY_V2_OCR_PROVIDER') or 'local').strip().lower(),
        'ocr_engine': LOCAL_OCR_ENGINE_VERSION,
        'ocr_dpi': _bounded_env('STUDY_V2_LOCAL_OCR_DPI', 150, 120, 200),
        'ocr_retry_dpi': _bounded_env('STUDY_V2_LOCAL_OCR_RETRY_DPI', 210, 160, 240),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
