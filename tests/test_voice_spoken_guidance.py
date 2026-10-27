import json
from app import voice_exam_core as core, voice_exam_literature as literature


def test_same_extraction_call_receives_contextual_everyday_speech_guidance(monkeypatch):
    from app import voice_exam_review_provider as provider
    calls=[]
    def review(prompt, data, schema, **options):
        calls.append((prompt,data,options))
        return {'fields':{},'clinical_facts':[],'literature_topics':[]}
    monkeypatch.setattr(provider,'review',review)
    core._understand('Hasta: Ağzımı kapatınca önce o değiyor. Hekim: Yeni yapılanı mı diyorsunuz?',{})
    assert len(calls)==1
    assert 'GÜNDELİK KONUŞMAYI YORUMLAMA' in calls[0][0]
    from app.voice_exam_speech import interpretation_guide
    guide=interpretation_guide()
    assert {r['branch'] for r in guide['examples']} == set(__import__('app.voice_exam_taxonomy',fromlist=['BRANCH_LABELS']).BRANCH_LABELS)
    assert all(rule in calls[0][0] for rule in guide['rules'])


def test_new_common_concerns_have_fixed_queries_and_professional_sources():
    from app.voice_exam_sources import DOCUMENTS,TOPIC_DOCUMENTS
    from app.voice_exam_taxonomy import TOPIC_REGISTRY
    expected={'endo.cracked_tooth':'aae-cracked-teeth','restorative.esthetics':'ada-whitening',
              'orofacial_pain.sleep':'ada-sleep-apnea','pediatric.development':'aapd-occlusion',
              'prevention.diet':'ada-nutrition'}
    docs={d[0] for d in DOCUMENTS}
    for topic,doc in expected.items():
        assert topic in TOPIC_REGISTRY
        assert literature.TOPIC_SEARCHES[topic]
        assert doc in TOPIC_DOCUMENTS[topic] and doc in docs


def test_patient_language_examples_never_become_external_search_terms(monkeypatch):
    from app.voice_exam_speech import interpretation_guide
    sent=[]
    monkeypatch.setattr(literature,'_get',lambda utility,params:sent.append(params) or b'{"esearchresult":{"idlist":[]}}')
    literature._cache.clear()
    quote='Basarken değil lokmayı bırakınca elektrik gibi oluyor.'
    literature.retrieve_literature(quote,[{'topic':'endo.cracked_tooth','quote':quote}])
    assert sent and 'cracked tooth' in sent[0]['term']
    assert quote not in json.dumps(sent,ensure_ascii=False)
    assert interpretation_guide()['ambiguous_mentions']
