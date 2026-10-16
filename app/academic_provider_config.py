"""One explicit provider for every Academic language-model stage."""
import os
import re

from app.study_provider import ProviderTarget, StudyProviderError


def academic_target(stage='generation'):
    if stage not in {'planner', 'generation'}:
        raise ValueError('invalid academic stage')
    provider = os.getenv('STUDY_ACADEMIC_PROVIDER', 'gemini').strip().lower()
    defaults = {'gemini': 'gemini-3.5-flash-lite', 'anthropic': 'claude-haiku-5-5'}
    if provider not in defaults:
        raise StudyProviderError('Akademik AI sağlayıcı ayarı geçersiz.', code=400)
    model = (os.getenv(f'STUDY_ACADEMIC_{stage.upper()}_MODEL') or defaults[provider]).strip()
    prefix = 'claude-' if provider == 'anthropic' else 'gemini-'
    if not re.fullmatch(re.escape(prefix) + r'[A-Za-z0-9._-]{1,100}', model):
        raise StudyProviderError('Akademik AI model ayarı geçersiz.', code=400)
    return ProviderTarget(provider, model)
