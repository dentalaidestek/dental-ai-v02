"""Subject scope is separate from speaker, and literal clinical scope is retained."""
import pytest
from app import voice_exam_core as core

@pytest.mark.parametrize('subject,field,quote,recorded',[
    ('THIS_PATIENT','plan','Önce muayene edelim, sonra karar verelim.',True),
    ('OTHER_PERSON','medical_history','Ben de şeker ilacı kullanıyorum hocam.',False),
    ('UNCLEAR_PERSON','medical_history','Şeker ilacı kullanılıyor.',False),
    ('PATIENT_RELATIVE','family_history','Annem şeker hastası.',True),
])
def test_explicit_person_scope_is_not_the_speaker_role(subject,field,quote,recorded):
    text=('Hekim: ' if field=='plan' else 'Hasta: ')+quote
    output=core.normalize({'transcript':text,'clinical_facts':[{'field':field,'value':quote,'quote':quote,'subject':subject,'temporality':'PLANNED' if field=='plan' else 'CURRENT'}]})
    assert (field in output['fields']) is recorded

@pytest.mark.parametrize('field,quote,invented,temporality',[
    ('medical_history','Bende şeker tanısı yok.','Hiçbir sistemik hastalığı yok.','NEGATED'),
    ('plan','Önce bakalım, gerekirse filmle değerlendirelim.','Film çekildi ve kanal tedavisi yapıldı.','PLANNED'),
])
def test_atomic_medical_history_and_plan_do_not_publish_model_rewritten_meaning(field,quote,invented,temporality):
    output=core.normalize({'transcript':quote,'clinical_facts':[{'field':field,'value':invented,'quote':quote,'subject':'PATIENT','temporality':temporality}]})
    assert quote in output['fields'][field]['value']
    assert invented not in output['fields'][field]['value']

@pytest.mark.parametrize('quote,keep',[
    ('Yeni kaplamam önce değiyor.',False),
    ('Zirkonya üstüne porselen tabakalanacak.',False),
    ('Zirkonya altyapı üzerine veneering porseleni uygulanacak.',False),
    ('Veneered zirconia crown düşünüyoruz.',False),
    ('Ön dişe lamine düşünüyoruz.',True),
    ('İnce yaprak porselen düşünüyoruz.',True),
    ('Porcelain laminate veneers değerlendirilecek.',True),
])
def test_generic_crown_does_not_route_to_specific_veneer_material(quote,keep):
    data={'transcript':quote,'literature_topics':[{'topic':'prosth.veneers','quote':quote}]}
    output=core.normalize(data)
    context=core.clinical_context({'literature_topics':data['literature_topics']})
    assert bool(output['literature_topics']) is keep
    assert bool(context['literature_topics']) is keep


def test_unexpected_model_summary_cannot_override_literal_fact_in_real_extraction_path(monkeypatch):
    from app import voice_exam_review_provider as provider
    quote='Bende şeker tanısı yok.'
    monkeypatch.setattr(provider,'review',lambda *a,**k:{
        'fields':{'medical_history':{'value':'Hiçbir sistemik hastalığı yok.','quote':quote}},
        'clinical_facts':[{'field':'medical_history','value':'Sistemik hastalık yok.','quote':quote,'subject':'THIS_PATIENT','temporality':'NEGATED'}]})
    output=core._understand(quote,core.clinical_context({}))
    assert output['fields']['medical_history']['value']=='Olumsuz beyan: '+quote
