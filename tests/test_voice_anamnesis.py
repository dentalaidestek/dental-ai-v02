"""Anamnesis provenance/coverage contracts; no clinical accuracy certification."""
import json
import pytest
from app import voice_exam_core as core, voice_exam_final as final
from test_voice_exam import app_client, payload, Analysis
from test_voice_exam_final import provider
from sqlmodel import Session, select

def test_family_history_and_personal_denial_are_separate_literal_facts():
    text='Hasta: Annem şeker hastası; bende böyle bir tanı yok.'
    facts=[{'field':'family_history','value':'Annenin diyabeti','quote':'Annem şeker hastası','subject':'FAMILY','temporality':'CURRENT'},
           {'field':'medical_history','value':'Diyabet tanısı yok','quote':'bende böyle bir tanı yok','subject':'PATIENT','temporality':'NEGATED'}]
    result=core.normalize({'transcript':text,'clinical_facts':facts},evidence=text)
    assert result['fields']['family_history']['value']=='Güncel: Annem şeker hastası'
    assert result['fields']['medical_history']['value']=='Olumsuz beyan: Diyabet tanısı yok'

def test_relative_disease_cannot_become_personal_medical_history():
    text='Annem şeker hastası.'
    output=core.normalize({'transcript':text,'clinical_facts':[{'field':'medical_history','value':'Diyabet','quote':text,'subject':'FAMILY','temporality':'CURRENT'}]},evidence=text)
    assert 'medical_history' not in output['fields']

def test_conflicting_other_person_anchor_cannot_become_patient_family_history():
    quote='Annem şeker hastası.'
    output=core.normalize({'transcript':'Asistan: '+quote,'clinical_facts':[
        {'field':'family_history','value':quote,'quote':quote,'subject':'FAMILY','temporality':'CURRENT'},
        {'field':'medical_history','value':quote,'quote':quote,'subject':'OTHER','temporality':'CURRENT'}]})
    assert 'family_history' not in output['fields']
    assert output['uncertain']

def test_unattributed_legacy_family_summary_is_not_saved_as_family_fact():
    text='Şeker hastalığı var.'
    output=core.normalize({'transcript':text,'fields':{'family_history':{'value':'Annesinde diyabet','quote':text}}},evidence=text)
    assert 'family_history' not in output['fields']

def test_material_name_or_unknown_selection_stays_literal_and_timed():
    text='Hekim: Fiber post düşünüyoruz. Yapıştırıcının markası henüz belli değil.'
    facts=[{'field':'materials','value':'Uydurulmuş marka X','quote':'Fiber post düşünüyoruz.','subject':'PATIENT','temporality':'PLANNED'},
           {'field':'materials','value':'Rezin siman marka Y','quote':'Yapıştırıcının markası henüz belli değil.','subject':'PATIENT','temporality':'UNKNOWN'}]
    output=core.normalize({'transcript':text,'clinical_facts':facts},evidence=text)
    assert output['fields']['materials']['value']=='Planlanan: Fiber post düşünüyoruz.\nBelirsiz: Yapıştırıcının markası henüz belli değil.'

@pytest.mark.parametrize('subject', ['PATIENT','OTHER','UNKNOWN'])
def test_unproven_family_attribution_is_not_a_family_fact(subject):
    quote='Şeker hastalığı var.'
    output=core.normalize({'transcript':quote,'clinical_facts':[{'field':'family_history','value':'Annesinde şeker','quote':quote,'subject':subject,'temporality':'CURRENT'}]},evidence=quote)
    assert 'family_history' not in output['fields']

def test_explicit_clinician_reply_keeps_speaker_provenance():
    quote='Şu an sökme kararı vermedik.'
    result=core.normalize({'transcript':'Hekim: '+quote,'clinical_facts':[{'field':'clinician_response','value':'Hekim açıklaması','quote':quote,'subject':'PATIENT','temporality':'CURRENT'}]})
    assert result['communication'][0]['category']=='CLINICIAN_RESPONSE'

def test_explicit_patient_reply_is_not_tagged_as_clinician_response():
    text='Hasta: Ağrım yok diye normal yazılmasın.'
    output=core.normalize({'transcript':text,'clinical_facts':[{'field':'clinician_response','value':'Hekim yanıtı','quote':'Ağrım yok diye normal yazılmasın.','subject':'PATIENT','temporality':'CURRENT'}]},evidence=text)
    assert output['communication'][0]['category']=='PATIENT_RESPONSE'

def test_inline_speaker_transition_uses_nearest_explicit_speaker():
    quote='Anladım, önce inceleyeceğiz.'
    result=core.normalize({'transcript':'Hekim: Önce bakalım. Hasta: '+quote,'clinical_facts':[
        {'field':'clinician_response','value':'Yanıt','quote':quote,'temporality':'CURRENT','subject':'PATIENT'}]})
    assert result['communication'][0]['category']=='PATIENT_RESPONSE'

def test_repeated_reply_with_an_unlabelled_occurrence_has_no_verified_speaker():
    quote='Önce inceleyeceğiz.'
    result=core.normalize({'transcript':'Hekim: '+quote+'\n'+quote,'clinical_facts':[
        {'field':'clinician_response','value':'Yanıt','quote':quote,'temporality':'CURRENT','subject':'PATIENT'}]})
    assert result['communication'][0]['category']=='UNATTRIBUTED_RESPONSE'

def test_unanswered_family_question_is_not_a_recorded_family_history():
    quote='Annenizde diyabet var mı?'
    output=core.normalize({'transcript':'Hekim: '+quote,'clinical_facts':[
        {'field':'family_history','value':'Annesinde diyabet','quote':quote,'temporality':'CURRENT','subject':'FAMILY'}]})
    assert 'family_history' not in output['fields']

def test_assistant_own_relative_is_not_patient_family_history():
    quote='Annem şeker hastası.'
    output=core.normalize({'transcript':'Asistan: '+quote,'clinical_facts':[
        {'field':'family_history','value':quote,'quote':quote,'temporality':'CURRENT','subject':'FAMILY'}]})
    assert 'family_history' not in output['fields']

def test_final_receives_literal_plan_and_typed_response_without_new_call(monkeypatch):
    calls=provider(monkeypatch,{'questions':[],'contradictions':[],'clinical_items':[]})
    response='Şu an sökme kararı vermedik. Önce nedeni anlayalım.'
    context={'fields':{'plan':{'value':'Önce inceleme planı','quote':response,'edited':False},
                       'family_history':{'value':'Annem şeker hastası','quote':'Annem şeker hastası','edited':False}}}
    output=final.finalize(context,[{'category':'CLINICIAN_RESPONSE','quote':response,'observation':'Görüşmede verilen yanıt: '+response,'suggestion':''}])
    sent=json.loads(calls[0]['messages'][0]['content'])
    assert sent['clinical_fields']['plan']['evidence_quote']==response
    assert sent['communication_context'][0]['category']=='CLINICIAN_RESPONSE'
    assert sent['communication_context'][0]['quote']==response
    coverage={row['field']:row for row in output['anamnesis_review']}
    assert coverage['family_history']['state']=='recorded'
    assert coverage['medications']['state']=='not_recorded'
    assert len(calls)==1

def test_clinician_edit_does_not_reintroduce_stale_spoken_quote(monkeypatch):
    calls=provider(monkeypatch,{'questions':[],'contradictions':[],'clinical_items':[]})
    context={'fields':{'medications':{'value':'Hekimin düzelttiği ilaç bilgisi',
              'quote':'ESKI_YANLIS_ILAC_BILGISI','edited':True}}}
    final.finalize(context,[])
    sent=json.loads(calls[0]['messages'][0]['content'])
    assert sent['clinical_fields']['medications']=={'value':'Hekimin düzelttiği ilaç bilgisi'}
    assert 'ESKI_YANLIS_ILAC_BILGISI' not in json.dumps(sent)

def test_age_quote_cannot_reintroduce_identity_into_final_review(monkeypatch):
    calls=provider(monkeypatch,{'questions':[],'contradictions':[],'clinical_items':[]})
    final.finalize({'fields':{'age':{'value':'35','quote':'Adım PRIVATE_NAME, 35 yaşındayım.','edited':False}}},[])
    sent=json.loads(calls[0]['messages'][0]['content'])
    assert sent['clinical_fields']['age']=={'value':'35'}
    assert 'PRIVATE_NAME' not in json.dumps(sent)

@pytest.mark.parametrize('edited', ['false',0,None])
def test_edited_flag_requires_an_actual_boolean(edited):
    with pytest.raises(core.VoiceError):
        core.clinical_context({'fields':{'plan':{'value':'Muayene planı','quote':'Önce bakalım.','edited':edited}}})

def test_extractor_gets_history_focus_in_the_existing_call(monkeypatch):
    from app import voice_exam_review_provider
    calls=[]
    def review(prompt,data,schema,**kwargs):
        calls.append(data)
        return {'fields':{},'clinical_facts':[],'literature_topics':[]}
    monkeypatch.setattr(voice_exam_review_provider,'review',review)
    core._understand('Bugün iki ağrı kesici aldım ama düzenli ilacım yok.',{})
    assert {row['field'] for row in calls[0]['anamnesis_scope']} >= {'medications','allergies','family_history','dental_history'}
    assert len(calls)==1

def test_family_and_material_fields_require_approval_and_survive_history(app_client):
    client,engine=app_client
    data=payload(engine,fields={'family_history':'Annesinde diyabet beyanı.', 'materials':'Planlanan: Fiber post düşünüyoruz.'})
    assert client.post('/patients/1/voice-exam/apply',json={**data,'confirmed':False}).status_code==400
    assert client.post('/patients/1/voice-exam/apply',json=data).status_code==200
    with Session(engine) as session:
        notes=session.exec(select(Analysis)).one().clinical_notes
        assert 'Aile sağlık öyküsü: Annesinde diyabet beyanı.' in notes
        assert 'Konuşulan materyaller: Planlanan: Fiber post düşünüyoruz.' in notes
    assert client.get('/patients/1/voice-exam/history').json()['fields']['family_history']['value']=='Annesinde diyabet beyanı.'
