"""Unambiguous attribution/field assignment regressions from live synthetic cases."""
import pytest
from app import voice_exam_core as core


def normalize(field,quote,subject='PATIENT',temporality='NEGATED',speaker='Hasta'):
    return core.normalize({'transcript':speaker+': '+quote,'clinical_facts':[
        {'field':field,'value':'Model özeti','quote':quote,'subject':subject,'temporality':temporality}]})

@pytest.mark.parametrize('field,quote',[
    ('medical_history','Düzenli ilaç yok; bildiğim alerjim de yok.'),
    ('medications','İlaç yok, alerji bildiğim de yok.'),
])
def test_clear_medication_and_allergy_denials_have_their_own_fields(field,quote):
    result=normalize(field,quote)
    assert set(result['fields'])=={'medications','allergies'}
    assert 'ilaç' in result['fields']['medications']['value'].lower().replace('\u0307','')
    assert 'alerji' not in result['fields']['medications']['value'].lower().replace('\u0307','')
    assert 'alerji' in result['fields']['allergies']['value'].lower().replace('\u0307','')

@pytest.mark.parametrize('subject',['OTHER','UNKNOWN'])
def test_other_person_denial_is_not_rerouted_as_patient_information(subject):
    assert normalize('medical_history','Düzenli ilaç yok; bildiğim alerjim de yok.',subject)['fields']=={}


def test_mixed_or_uncertain_clause_is_not_silently_split_or_lost():
    quote='Düzenli ilaç yok; şeker hastalığı olabilir.'
    result=normalize('medical_history',quote,temporality='UNKNOWN')
    assert set(result['fields'])=={'medical_history'}
    assert quote in result['fields']['medical_history']['value']


def test_allergy_paraphrase_cannot_invent_a_named_drug_allergy():
    quote='Bir ilaçtan döküntü olmuştu, adını bilmiyorum.'
    output=core.normalize({'transcript':quote,'clinical_facts':[{'field':'allergies','value':'Penisilin alerjisi','quote':quote,'subject':'PATIENT','temporality':'HISTORICAL'}]})
    assert quote in output['fields']['allergies']['value']
    assert 'Penisilin' not in output['fields']['allergies']['value']

@pytest.mark.parametrize('speaker,field',[('Hasta','chief_complaint'),('Hekim','clinical_findings')])
def test_explicit_patient_report_is_not_an_observed_clinical_finding(speaker,field):
    quote='Ağzımı kapatınca önce o diş değiyor.'
    result=normalize('clinical_findings',quote,temporality='CURRENT',speaker=speaker)
    assert set(result['fields'])=={field}
    assert quote in result['fields'][field]['value']


def test_split_denial_cannot_splice_patient_and_assistant_speech():
    text='Hasta: İlaç yok.\nAsistan: Alerjim yok.'
    output=core.normalize({'transcript':text,'clinical_facts':[{'field':'medical_history','value':'İlaç ve alerji yok','quote':'İlaç yok; Alerjim yok.','subject':'PATIENT','temporality':'NEGATED'}]})
    assert output['fields']=={}
