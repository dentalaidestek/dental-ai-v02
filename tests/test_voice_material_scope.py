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


def test_unknown_material_cannot_create_an_arbitrary_query():
    data, _ = web._public_input([{'topic':'material.secret_patient_555','query':'PRIVATE','quote':'PRIVATE'}], [])
    assert data['topics'] == []
