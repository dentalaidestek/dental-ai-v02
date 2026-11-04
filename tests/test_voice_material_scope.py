"""Material routing contracts, not a clinical accuracy benchmark."""
import json
import pytest
from app import voice_exam_core as core, voice_exam_literature as literature
from app import voice_exam_web_research as web

CASES = [
    ('prosth.zirconia', 'Arkadaki köprüye zirkonyum düşünüyoruz; hasta geceleri dişlerini sıkıyormuş.', 'zirconia'),
    ('prosth.glass_ceramic', 'Ön dişe emax konuşuyoruz, kesince ne kadar yer kalacağını ölçmedik.', 'lithium disilicate'),
    ('prosth.metal_ceramic', 'Metal destekli porselen istiyor ama takınca küpeden kulağı kızarıyormuş.', 'metal ceramic'),
    ('prosth.veneers', 'Ön dişlere ince lamine istiyor; gece sıkıyor, mine ne kadar kalır bilmiyoruz.', 'veneer'),
    ('endo.post_core', 'Kanalı biten dişe fiber post koyalım mı, üstte tutacak diş az kalmış.', 'ferrule'),
    ('endo.irrigation', 'Kanalı hipokloritle yıkayacağız; kökün ucu açık mı filmden bakalım.', 'irrigation'),
    ('endo.obturation', 'Asistan biyoseramik patı hazırlasın, kök ucuna taşmasın diye boyu kontrol edelim.', 'sealer'),
    ('restorative.materials', 'Dolguya kompozit mi cam iyonomer mi, kuru tutabilir miyiz önce bakalım.', 'glass ionomer'),
    ('perio.regeneration', 'Buraya greft ve membran konuşuyoruz, diş etinin durumuna bakalım.', 'membrane'),
    ('implant.components', 'İmplantın üstüne farklı markanın parçasını takabilir miyiz, bağlantıyı bilmiyoruz.', 'compatibility'),
]

@pytest.mark.parametrize('topic,dialogue,term', CASES)
def test_material_and_procedure_reach_public_research_without_patient_text(topic, dialogue, term):
    normalized = core.normalize({'transcript': dialogue, 'literature_topics': [{'topic': topic, 'quote': dialogue}]}, evidence=dialogue)
    assert normalized['literature_topics'] == [{'topic': topic, 'quote': dialogue}], 'Specific material topic must survive closed taxonomy validation'
    data, unverified = web._public_input(normalized['literature_topics'], [])
    assert data['topics'][0]['id'] == topic
    assert term in data['topics'][0]['query'].lower()
    assert dialogue not in json.dumps(data, ensure_ascii=False)
    assert not unverified
    assert literature.selected_topics('', normalized['literature_topics']) == [topic]


def test_material_topic_requires_real_conversation_anchor():
    output = core.normalize({'transcript':'Diş etim kanıyor.', 'literature_topics':[{'topic':'prosth.zirconia','quote':'Zirkonyum köprü yapalım.'}]}, evidence='Diş etim kanıyor.')
    assert output['literature_topics'] == []


def test_material_candidate_keeps_the_relevant_literal_passage_beyond_first_1800_characters():
    from app import voice_exam_materials as materials
    text='General information. ' * 120 + 'Ferrule and remaining tissue must be assessed.'
    rows=materials.source_candidates([{'id':'endo.post_core'}],
        [{'id':'aae','clinical_use':True,'excerpts':[text]}])
    quote=rows[0]['candidates'][0]['source_quote']
    assert 'Ferrule' in quote
    assert quote in text
    assert len(quote)<=1800


def test_unknown_material_cannot_create_an_arbitrary_query():
    data, _ = web._public_input([{'topic':'material.secret_patient_555','query':'PRIVATE','quote':'PRIVATE'}], [])
    assert data['topics'] == []


def test_general_filling_note_does_not_count_as_a_post_appropriateness_check(monkeypatch):
    from app import voice_exam_final as final
    from test_voice_exam_final import provider
    context={'fields':{'plan':{'value':'Fiber post seçeneğini konuşuyoruz.','quote':'Fiber post seçeneğini konuşuyoruz.'}},'literature_topics':[{'topic':'endo.post_core','quote':'Fiber post seçeneğini konuşuyoruz.'}]}
    item={'review_topic':'endo.post_core','source_id':'ada','source_quote':'Composite restorations require isolation.','patient_field':'plan','patient_quote':'Fiber post','consideration':'Post için kompozit kuralını kullan.','missing_information':'','alternative':''}
    calls=provider(monkeypatch,{'questions':[],'contradictions':[],'clinical_items':[item]})
    monkeypatch.setattr(final,'retrieve',lambda *a,**k:{'references':[{'id':'ada','excerpts':['Composite restorations require isolation.'],'clinical_use':True}], 'unavailable':[],'coverage':'limited','notice':'limited'})
    output=final.finalize(context,[])
    assert output['clinical_items']==[]
    assert output['material_review'][0]['status']=='unverified'
    sent=json.loads(calls[0]['messages'][0]['content'])
    assert sent['material_review_targets'][0]['id']=='endo.post_core'


def test_specific_post_passage_can_support_a_control_without_safety_approval(monkeypatch):
    from app import voice_exam_final as final
    from test_voice_exam_final import provider
    context={'fields':{'plan':{'value':'Fiber post konuşuyoruz.','quote':'Fiber post konuşuyoruz.'}},'literature_topics':[{'topic':'endo.post_core','quote':'Fiber post konuşuyoruz.'}]}
    passage='Remaining tooth structure and ferrule affect restorability.'
    item={'review_topic':'endo.post_core','source_id':'aae','source_quote':passage,'patient_field':'plan','patient_quote':'Fiber post','consideration':'Kalan doku değerlendirilmeli.','missing_information':'Doku miktarı bilinmiyor.','alternative':''}
    provider(monkeypatch,{'questions':[],'contradictions':[],'clinical_items':[item]})
    monkeypatch.setattr(final,'retrieve',lambda *a,**k:{'references':[{'id':'aae','excerpts':[passage],'clinical_use':True}], 'unavailable':[],'coverage':'limited','notice':'limited'})
    output=final.finalize(context,[])
    assert len(output['clinical_items'])==1
    assert output['material_review']==[{'topic':'endo.post_core','label':'Post, kor ve kalan diş dokusu','status':'control_point_present','source_ids':['aae']}]


def test_each_material_target_gets_literal_source_candidates_and_gap_diagnostics(monkeypatch):
    from app import voice_exam_final as final
    from test_voice_exam_final import provider
    context={'fields':{'plan':{'value':'Fiber post ve zirkonya konuşuyoruz.','quote':'Fiber post ve zirkonya konuşuyoruz.'}},
             'literature_topics':[{'topic':t,'quote':'Fiber post ve zirkonya konuşuyoruz.'} for t in ('endo.post_core','prosth.zirconia')]}
    calls=provider(monkeypatch,{'questions':[],'contradictions':[],'clinical_items':[]})
    passage='Remaining tooth structure and ferrule affect restorability.'
    monkeypatch.setattr(final,'retrieve',lambda *a,**k:{'references':[
        {'id':'generic','excerpts':['Composite restorations require isolation.'],'clinical_use':True},
        {'id':'background','excerpts':['Zirconia research background.'],'clinical_use':False},
        {'id':'aae','excerpts':[passage],'clinical_use':True}], 'unavailable':[],'coverage':'limited','notice':'limited'})
    output=final.finalize(context,[])
    sent=json.loads(calls[0]['messages'][0]['content'])
    candidates={row['topic']:row['candidates'] for row in sent['material_source_candidates']}
    assert candidates['endo.post_core']==[{'source_id':'aae','source_quote':passage}]
    assert candidates['prosth.zirconia']==[]
    diagnostics={row['topic']:row for row in output['review_status']['material_evidence']}
    assert diagnostics['endo.post_core']['candidate_source_count']==1
    assert diagnostics['endo.post_core']['accepted_control_count']==0
    assert diagnostics['prosth.zirconia']['candidate_source_count']==0
    assert all(row['status']=='unverified' for row in output['material_review'])
    assert len(calls)==1


@pytest.mark.parametrize('quote', ['Postoperative pain requires follow-up.', 'Compost material', 'Composite restorations require isolation.'])
def test_post_relevance_does_not_match_postoperative_or_unrelated_words(quote):
    from app import voice_exam_materials as materials
    assert materials.relevant_passage('endo.post_core',quote) is False


@pytest.mark.parametrize('topic,quote', [
    ('endo.post_core','Post-operative pain requires follow-up.'),
    ('endo.post_core','Post-treatment pain should be monitored.'),
    ('implant.components','The platform provides patient information.'),
    ('implant.components','The connection was closed by the server.'),
])
def test_generic_or_temporal_words_cannot_complete_a_material_check(topic,quote):
    from app import voice_exam_materials as materials
    assert materials.relevant_passage(topic,quote) is False


@pytest.mark.parametrize('suffix',['','?utm_source=test','#materials'])
def test_general_material_table_cannot_warn_about_an_unselected_alloy_in_a_post_case(monkeypatch,suffix):
    from app import voice_exam_final as final
    from test_voice_exam_final import provider
    context={'fields':{'plan':{'value':'Fiber post ve kaplama konuşuyoruz.','quote':'Fiber post ve kaplama konuşuyoruz.'}},'literature_topics':[{'topic':'endo.post_core','quote':'Fiber post ve kaplama konuşuyoruz.'},{'topic':'prosth.fixed','quote':'Fiber post ve kaplama konuşuyoruz.'}]}
    quote='High noble alloys: anterior teeth. Base metal alloys: nickel hypersensitivity.'
    item={'review_topic':'prosth.fixed','source_id':'ada','source_quote':quote,'patient_field':'plan','patient_quote':'kaplama','consideration':'Nikel içeren alaşım seçimini kontrol et.','missing_information':'Metal türü yok.','alternative':''}
    provider(monkeypatch,{'questions':[],'contradictions':[],'clinical_items':[item]})
    monkeypatch.setattr(final,'retrieve',lambda *a,**k:{'references':[{'id':'ada','url':'https://www.ada.org/resources/ada-library/oral-health-topics/materials-for-indirect-restorations'+suffix,'excerpts':[quote],'clinical_use':True}], 'unavailable':[],'coverage':'limited','notice':'limited'})
    output=final.finalize(context,[])
    assert output['clinical_items']==[]
    assert output['material_review'][0]['status']=='unverified'


def test_changed_material_validation_invalidates_prior_source_fingerprint(monkeypatch):
    from app import voice_exam_final as final, voice_exam_materials as materials
    from test_voice_exam_final import provider
    context={'fields':{'plan':{'value':'Fiber post konuşuyoruz.','quote':'Fiber post konuşuyoruz.'}},'literature_topics':[{'topic':'endo.post_core','quote':'Fiber post konuşuyoruz.'}]}
    calls=provider(monkeypatch,{'questions':[],'contradictions':[],'clinical_items':[]})
    monkeypatch.setattr(final,'retrieve',lambda *a,**k:{'references':[{'id':'aae','excerpts':['Ferrule affects restorability.'],'clinical_use':True}], 'unavailable':[],'coverage':'limited','notice':'limited'})
    previous=final.finalize(context,[])
    monkeypatch.setattr(materials,'VALIDATION_VERSION','next-validator')
    result=final.finalize(context,[],previous_source_fingerprint=previous['source_fingerprint'])
    assert not result.get('not_modified')
    assert len(calls)==2
