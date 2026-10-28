import hashlib
import json
import sys
from collections import OrderedDict
from contextlib import nullcontext
from types import ModuleType
from app import voice_exam_final as final, voice_exam_web_research as web
from app.voice_source_pool import BoundedPool


def test_finish_researches_public_concepts_then_grounds_private_review_and_reuses_research(monkeypatch):
    import app.http_transport as transport
    monkeypatch.delenv('VOICE_EXAM_SOURCE_MODE',raising=False)
    monkeypatch.setenv('ANTHROPIC_API_KEY','synthetic-secret')
    monkeypatch.setenv('VOICE_EXAM_CLAUDE_MODEL','claude-web-integration')
    pool=BoundedPool(2,4,'integration-web')
    monkeypatch.setattr(web,'_pool',pool)
    monkeypatch.setattr(web,'_cache',OrderedDict())
    monkeypatch.setattr(web,'_inflight',{})
    budget=ModuleType('app.provider_budget');budget.reservation=lambda *a:nullcontext()
    monkeypatch.setitem(sys.modules,'app.provider_budget',budget)
    url='https://www.ada.org/resources/public-restoration'
    source='Synthetic public source: Occlusal contacts require clinical assessment.'
    source_id='native-web-'+hashlib.sha256(url.encode()).hexdigest()[:20]
    private='Yeni yapılan kaplamam önce değiyor; PRIVATE_DETAIL.'
    calls=[]
    class Response:
        def __init__(self,body):self.body=body
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,*a):return json.dumps(self.body).encode()
    def request(req,**kw):
        payload=json.loads(req.data);calls.append(payload)
        if 'tools' in payload:
            assert 'PRIVATE' not in json.dumps(payload)
            assert {t['name'] for t in payload['tools']}=={'web_search','web_fetch'}
            return Response({'stop_reason':'end_turn','content':[
                {'type':'server_tool_use','id':'fetch1','name':'web_fetch','input':{'url':url}},
                {'type':'web_fetch_tool_result','tool_use_id':'fetch1','content':{'type':'web_fetch_result','url':url,
                    'content':{'type':'document','title':'Restoration information','source':{'type':'text','media_type':'text/plain','data':source}}}}]})
        assert 'PRIVATE_DETAIL' in payload['messages'][0]['content']
        assert 'tools' not in payload and 'output_config' in payload
        return Response({'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps({
            'questions':[],'contradictions':[],'clinical_items':[{'source_id':source_id,'source_quote':source,
                'patient_field':'chief_complaint','patient_quote':private,'consideration':'Kapanış hekimce değerlendirilebilir.',
                'missing_information':'Klinik muayene','alternative':''}]})}]})
    monkeypatch.setattr(transport,'urlopen',request)
    context={'fields':{'chief_complaint':{'value':private,'quote':private}},
             'literature_topics':[{'topic':'prosth.occlusion','quote':private}]}
    try:
        output=final.finalize(context,[])
        assert len(calls)==2 and len(output['clinical_items'])==1
        assert output['references'][0]['url']==url and output['research_mode']=='claude_web'
        assert output['source_coverage'][0]['status']=='research_material_unverified'
        retry=final.finalize(context,[],previous_source_fingerprint=output['source_fingerprint'])
        assert retry['not_modified'] and len(calls)==2
    finally:
        pool.shutdown()


def test_finish_without_public_topic_still_reviews_but_cannot_invent_clinical_evidence(monkeypatch):
    from app import voice_exam_review_provider as provider
    monkeypatch.delenv('VOICE_EXAM_SOURCE_MODE', raising=False)
    monkeypatch.setattr(provider, 'research_message', lambda *a, **k: (_ for _ in ()).throw(AssertionError('No research needed')))
    monkeypatch.setattr(final, 'review', lambda *a, **k: {'questions': [], 'contradictions': [],
        'clinical_items': [{'source_id': 'invented', 'source_quote': 'invented', 'patient_field': 'chief_complaint',
            'patient_quote': 'Kontrole geldim.', 'consideration': 'All safe', 'missing_information': '', 'alternative': ''}]})
    result = final.finalize({'fields': {'chief_complaint': {'value': 'Kontrole geldim.', 'quote': 'Kontrole geldim.'}},
                             'literature_topics': []}, [])
    assert result['clinical_items'] == []
    assert not result['review_status']['source_retryable']


def test_all_source_transport_failure_blocks_final_paid_review(monkeypatch):
    import pytest
    from app import voice_exam_review_provider as provider, voice_exam_core as core
    monkeypatch.setattr(final, 'retrieve', lambda *a, **k: {'references': [], 'unavailable': ['web-research-unavailable:provider-error']})
    monkeypatch.setattr(final, 'review', lambda *a, **k: pytest.fail('Final call must not run'))
    with pytest.raises(core.VoiceError, match='Kaynaklara erişilemedi'):
        final.finalize({'fields': {'chief_complaint': {'value': 'Ağrıyor.', 'quote': 'Ağrıyor.'}}, 'literature_topics': []}, [])
