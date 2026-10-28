import pytest
from app import voice_exam_core as core


def test_default_research_is_claude_web_and_patient_text_never_reaches_adapter(monkeypatch):
    from app import voice_exam_research as routing, voice_exam_web_research as web
    monkeypatch.delenv('VOICE_EXAM_SOURCE_MODE',raising=False)
    calls=[]
    def retrieve(topics,requests=None):
        calls.append((topics,requests))
        return {'references':[{'id':'native','url':'https://www.ada.org/a','excerpts':['Public text'],'clinical_use':True}],
                'unavailable':[],'coverage':'limited','notice':'native','usage':{'http_requests':1}}
    monkeypatch.setattr(web,'retrieve_web',retrieve)
    result=routing.retrieve('PRIVATE_FULL_CONVERSATION',[{'term':'warfarin','quote':'Warfarin kullanıyorum.'}],
                            [{'topic':'prosth.occlusion','quote':'PRIVATE_QUOTE'}])
    assert calls[0][0]==[{'topic':'prosth.occlusion'}]
    assert 'PRIVATE' not in str(calls)
    assert result['source_coverage'][0]['status']=='research_material_unverified'
    assert result['source_coverage'][0]['source_ids']==[]
    assert result['research_usage']=={'http_requests':1}


def test_explicit_legacy_mode_keeps_existing_retrieval(monkeypatch):
    from app import voice_exam_research as routing, voice_exam_sources as sources
    monkeypatch.setenv('VOICE_EXAM_SOURCE_MODE','legacy')
    calls=[]
    monkeypatch.setattr(sources,'retrieve',lambda *a,**kw:calls.append((a,kw)) or {'legacy':True})
    assert routing.retrieve('Existing query',topics=[])=={'legacy':True}
    assert calls[0][1]['topics']==[]


def test_invalid_source_mode_never_silently_falls_back(monkeypatch):
    from app import voice_exam_research as routing
    monkeypatch.setenv('VOICE_EXAM_SOURCE_MODE','typo')
    with pytest.raises(core.VoiceError):routing.retrieve('Anything',topics=[])


def test_web_failure_remains_failure_without_unrequested_legacy_fallback(monkeypatch):
    from app import voice_exam_research as routing, voice_exam_web_research as web,voice_exam_sources as sources
    monkeypatch.delenv('VOICE_EXAM_SOURCE_MODE',raising=False)
    monkeypatch.setattr(web,'retrieve_web',lambda *a,**k:{'references':[],'unavailable':['web-research-unavailable:test'],'coverage':'limited','notice':'failure'})
    monkeypatch.setattr(sources,'retrieve',lambda *a,**k:pytest.fail('No silent fallback'))
    result=routing.retrieve('PRIVATE',topics=[{'topic':'prosth.fixed'}])
    assert not result['references']
    assert result['source_coverage'][0]['status']=='uncovered'
