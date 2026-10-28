import json
import pytest
from app import voice_exam_core as core, voice_exam_literature as literature


def test_every_dental_branch_has_semantic_fallback_and_fixed_query():
    from app.voice_exam_taxonomy import TOPIC_REGISTRY, BRANCH_LABELS
    assert {'prosth', 'ortho', 'pediatric', 'perio', 'surgery', 'oral_medicine',
            'restorative', 'implant', 'endo', 'imaging', 'anesthesia', 'emergencies',
            'special_care', 'prevention', 'orofacial_pain'} <= set(BRANCH_LABELS)
    allowed = core.schema()['properties']['literature_topics']['items']['properties']['topic']['enum']
    for branch in BRANCH_LABELS:
        topic = TOPIC_REGISTRY[branch + '.general']
        assert topic['id'] in allowed
        assert topic['scope'] and topic['label'] and topic['query']
        assert literature.TOPIC_SEARCHES[topic['id']] == topic['query']


def test_new_topic_quotes_are_validated_and_existing_ids_preserved():
    quote = 'Yeni kaplama kapanışta önce değiyor.'
    result = core.normalize({'transcript': quote, 'literature_topics': [{'topic': 'prosth.occlusion', 'quote': quote}]}, evidence=quote)
    assert result['literature_topics'] == [{'topic': 'prosth.occlusion', 'quote': quote}]
    assert core.normalize({'transcript': quote, 'literature_topics': [{'topic': 'prosth.occlusion', 'quote': quote}]}, evidence='Başka metin')['literature_topics'] == []
    for ident in ('endodontic diagnosis', 'endo.root_perforation', 'periodontitis diagnosis treatment'):
        assert ident in dict(literature.TOPICS)


def test_explicit_semantic_topics_override_keyword_guessing():
    # The model understands this is a prosthetic issue despite the word pain.
    assert literature.selected_topics('PRIVATE ağrı diyabet', [{'topic': 'prosth.occlusion', 'quote': 'PRIVATE'}]) == ['prosth.occlusion']
    assert literature.selected_topics('ağrı', []) == []


def test_eight_topics_survive_context_without_silent_six_topic_loss():
    ids = ['prosth.general', 'ortho.general', 'pediatric.general', 'perio.general',
           'surgery.general', 'oral_medicine.general', 'imaging.general', 'anesthesia.general']
    topics = [{'topic': ident, 'quote': 'Konuşulan işlem.'} for ident in ids]
    assert core.clinical_context({'literature_topics': topics})['literature_topics'] == topics
    assert literature.selected_topics('', topics) == ids
    with pytest.raises(core.VoiceError):
        core.clinical_context({'literature_topics': topics * 4})


def test_selected_queries_never_send_patient_words(monkeypatch):
    seen = []
    literature._cache.clear()
    monkeypatch.setattr(literature, '_get', lambda utility, params: seen.append(params) or b'{"esearchresult":{"idlist":[]}}')
    literature.retrieve_literature('PRIVATE_PATIENT', [{'topic': 'prosth.cementation', 'quote': 'PRIVATE_QUOTE'}])
    assert seen and 'cement' in seen[0]['term']
    assert 'PRIVATE' not in json.dumps(seen)


def test_extractor_receives_semantic_scopes_without_an_additional_model_call(monkeypatch):
    from app import voice_exam_review_provider
    calls = []
    def review(prompt, data, schema, **options):
        calls.append((prompt, data, schema, options))
        return {'fields': {}, 'clinical_facts': [], 'literature_topics': []}
    monkeypatch.setattr(voice_exam_review_provider, 'review', review)
    core._understand('Kaplamam kapanışta ilk değiyor.', {})
    assert len(calls) == 1 and calls[0][3]['extraction'] is True
    assert 'prosth.occlusion' in calls[0][0] and 'dikey boyut' in calls[0][0]
    assert '.general' in calls[0][0] and 'Serbest sorgu üretme' in calls[0][0]


def test_topic_coverage_never_uses_an_unrelated_drug_as_prosthetic_evidence():
    from app import voice_exam_sources as sources
    topics = ['prosth.occlusion', 'ortho.retention']
    refs = [{'id': 'drug', 'excerpts': ['Label'], 'clinical_use': True},
            {'id': 'paper', 'excerpts': ['Review'], 'matched_topics': ['ortho.retention'], 'clinical_use': False}]
    coverage = sources.topic_coverage(topics, refs)
    assert coverage[0]['status'] == 'uncovered' and coverage[0]['source_ids'] == []
    assert coverage[1]['status'] == 'background_only'


def test_professional_documents_are_routed_by_semantics_without_keyword_match(monkeypatch):
    from app import voice_exam_sources as sources
    from app import voice_exam_dergipark, voice_exam_drugs
    seen = []
    def fetch_many(documents):
        seen.extend(documents)
        return [{'id': d[0], 'institution': d[1], 'excerpts': ['Public relevant paragraph'], 'clinical_use': True} for d in documents], []
    monkeypatch.setattr(sources, '_fetch_many', fetch_many)
    monkeypatch.setattr(literature, 'retrieve_literature', lambda *a, **k: ([], []))
    monkeypatch.setattr(voice_exam_dergipark, 'retrieve_dergipark', lambda *a, **k: ([], []))
    monkeypatch.setattr(voice_exam_drugs, 'retrieve_drugs', lambda *a, **k: [])
    result = sources.retrieve('Önce değen yeri ayarlayalım; ağrı var.', topics=[{'topic': 'prosth.fixed'}])
    assert 'ada-indirect-materials' in {d[0] for d in seen}
    assert 'ada-pain-guideline' not in {d[0] for d in seen}, 'Keyword fallback must not override validated topic selection'
    assert result['source_coverage'][0]['topic'] == 'prosth.fixed'
    assert result['source_coverage'][0]['status'] == 'related_material'
    assert result['source_coverage'][0]['specific_claim_verified'] is False


def test_final_forwards_topic_gaps_to_model_and_result(monkeypatch):
    from app import voice_exam_final as final
    from test_voice_exam_final import provider, CONTEXT
    calls = provider(monkeypatch, {'questions': [], 'contradictions': [], 'clinical_items': []})
    coverage = [{'topic': 'prosth.fixed', 'status': 'uncovered', 'source_ids': []}]
    monkeypatch.setattr(final, 'retrieve', lambda *a, **k: {'references': [], 'unavailable': [], 'coverage': 'limited', 'notice': 'limited', 'source_coverage': coverage})
    result = final.finalize(CONTEXT, [])
    assert result['source_coverage'] == coverage
    sent = json.loads(calls[0]['messages'][0]['content'])
    assert sent['source_coverage'] == coverage


def test_incremental_extraction_retains_eight_supported_topic_anchors(monkeypatch):
    quote = 'Konuşulan işlem.'
    ids = ['prosth.general', 'ortho.general', 'pediatric.general', 'perio.general',
           'surgery.general', 'oral_medicine.general', 'imaging.general', 'anesthesia.general']
    previous = {'fields': {'chief_complaint': {'value': quote, 'quote': quote}},
                'literature_topics': [{'topic': ident, 'quote': quote} for ident in ids[:-1]]}
    result = core.normalize({'transcript': quote, 'literature_topics': [{'topic': ids[-1], 'quote': quote}]})
    monkeypatch.setattr(core, '_understand', lambda *a: result)
    assert [item['topic'] for item in core.extract(transcript=quote, context=previous)['literature_topics']] == ids


def test_existing_high_risk_documents_have_explicit_semantic_routes():
    from app import voice_exam_sources as sources
    from app.voice_exam_taxonomy import TOPIC_REGISTRY
    for topic, ident in [('special_care.hypertension', 'ada-hypertension'),
                         ('special_care.cardiac', 'ada-prophylaxis'),
                         ('special_care.drug_interactions', 'sps-macrolides-statins')]:
        assert topic in TOPIC_REGISTRY
        assert ident in sources.TOPIC_DOCUMENTS[topic]


def test_explicit_empty_topics_survive_final_and_manual_clinical_callers(monkeypatch):
    from app import voice_exam_final as final, voice_exam_clinical as clinical
    from test_voice_exam_final import provider, CONTEXT
    provider(monkeypatch, {'questions': [], 'contradictions': [], 'clinical_items': []})
    calls = []
    def retrieve(*a, **kw):
        calls.append(kw)
        return {'references': [], 'unavailable': [], 'coverage': 'limited', 'notice': 'limited'}
    monkeypatch.setattr(final, 'retrieve', retrieve)
    monkeypatch.setattr(clinical, 'retrieve', retrieve)
    context = {**CONTEXT, 'literature_topics': []}
    final.finalize(context, [])
    clinical.assess(context)
    assert calls == [{'topics': []}, {'topics': []}]


def test_dergipark_general_anesthesia_does_not_cover_prosthetics_or_periodontics(monkeypatch):
    from app import voice_exam_dergipark as d
    from datetime import datetime, timezone
    monkeypatch.setattr(d, 'JOURNALS', {'selcukdentj': d.JOURNALS['selcukdentj']})
    monkeypatch.setattr(d, '_catalogue', lambda journal: ([{'id':'123', 'title':'General anesthesia in children systematic review', 'text':'General anesthesia in children systematic review'}], False))
    monkeypatch.setattr(d, '_article', lambda *a: {'id':'dergipark-123', 'clinical_use':True, 'excerpts':['Anesthesia information']})
    refs, missing = d.retrieve_dergipark('', [{'topic':'prosth.general'},{'topic':'perio.general'},{'topic':'special_care.general'}])
    assert refs == []
    assert 'dergipark-no-clinical-evidence:prosth.general' in missing


def test_previous_transcript_anchored_topic_does_not_require_field_quote_match(monkeypatch):
    old_quote = 'Önce o kaplamaya temas oluyor.'
    previous = {'fields': {'chief_complaint': {'value':'Kapanış sorunu', 'quote':'Ağzımı rahat kapatamıyorum.'}},
                'literature_topics': [{'topic':'prosth.occlusion', 'quote':old_quote}]}
    result = core.normalize({'transcript':'Diş etim de kanıyor.', 'literature_topics':[{'topic':'perio.general','quote':'Diş etim de kanıyor.'}]})
    monkeypatch.setattr(core, '_understand', lambda *a: result)
    output = core.extract(transcript='Diş etim de kanıyor.', context=previous)
    assert {t['topic'] for t in output['literature_topics']} == {'prosth.occlusion','perio.general'}


def test_explicit_grounded_topic_withdrawal_removes_only_retracted_topic(monkeypatch):
    quote = 'Yüksek kapanış demedim; kaplama yerinde.'
    previous = {'literature_topics':[{'topic':'prosth.occlusion','quote':'Yüksek kapanış.'},
                                    {'topic':'perio.general','quote':'Diş eti kanıyor.'}]}
    result = core.normalize({'transcript':quote, 'removed_literature_topics':[{'topic':'prosth.occlusion','quote':quote}]})
    monkeypatch.setattr(core, '_understand', lambda *a: result)
    output = core.extract(transcript=quote, context=previous)
    assert [t['topic'] for t in output['literature_topics']] == ['perio.general']
