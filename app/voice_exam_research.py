"""Source boundary: Claude manages public web research by default.

The legacy fixed-source engine is an explicit operator choice, never a silent
fallback after unsupported tools, capacity errors or failed native research.
"""
import os


def retrieve(query, requests=None, topics=None):
    from app import voice_exam_core as core
    from app import voice_exam_sources as legacy
    mode = os.getenv('VOICE_EXAM_SOURCE_MODE', 'claude_web').strip().lower()
    if mode == 'legacy':
        return legacy.retrieve(query, requests=requests, topics=topics)
    if mode != 'claude_web':
        raise core.VoiceError('Kaynak araştırması yapılandırması doğrulanamadı; taslak korunuyor.')
    from app.voice_exam_literature import selected_topics
    from app.voice_exam_web_research import retrieve_web
    selected = selected_topics(query, topics)
    # Only IDs reach the native adapter. Quotes/private clinical fields stay here.
    result = retrieve_web([{'topic': ident} for ident in selected], requests=requests)
    coverage = legacy.topic_coverage(selected, result['references'])
    for item in coverage:
        if item['status'] == 'uncovered' and result['references']:
            item['status'] = ('research_material_unverified' if any(
                ref.get('clinical_use') is not False for ref in result['references'])
                else 'research_background_unverified')
            # Discovery produced material, not a validated topic-to-claim binding.
            item['source_ids'] = []
    return {**result, 'source_coverage': coverage, 'research_mode': mode,
            'research_usage': result.get('usage', {})}
