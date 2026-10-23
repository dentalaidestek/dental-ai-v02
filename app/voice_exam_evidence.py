"""Evidence metadata is a selection aid, never a scientific truth guarantee."""
import re
from datetime import datetime, timezone


def quality_metadata(title, publication_types=(), year=None):
    kinds = ' '.join(publication_types).casefold()
    name = title.casefold()
    if any(term in kinds + ' ' + name for term in ('retracted publication', 'retraction of publication', 'withdrawn', 'geri çekil')):
        return None
    if 'meta-analysis' in kinds or 'meta-analysis' in name or 'meta analiz' in name:
        level = 'meta_analysis'
    elif 'systematic review' in kinds or 'systematic review' in name or 'sistematik derleme' in name:
        level = 'systematic_review'
    elif 'guideline' in kinds or 'practice guideline' in name or 'clinical practice guideline' in name:
        level = 'guideline'
    else:
        level = 'background_review'
    if any(term in kinds + ' ' + name for term in ('case report', 'olgu sunumu', 'editorial', 'editöre mektup')):
        level = 'background_review'
    preclinical = any(term in name for term in ('in vitro', 'in-vitro', 'ex vivo', 'ex-vivo', 'animal', 'rat model', 'laboratuvar'))
    year = int(year) if year and re.fullmatch(r'\d{4}', str(year)) else None
    current_year = datetime.now(timezone.utc).year
    # Old/undated reports remain discoverable but cannot ground clinical suggestions.
    dated = year is not None and current_year - 10 <= year <= current_year
    return {'evidence_level': level, 'publication_year': year,
            'publication_types': list(publication_types), 'preclinical': preclinical,
            'clinical_use': dated and not preclinical and level != 'background_review',
            'quality_notice': 'Yayın türü ve tarih ön elemesidir; yanlılık ve hastaya uygulanabilirlik ayrıca değerlendirilmelidir.'}
