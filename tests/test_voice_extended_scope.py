"""Scope/record contracts. These tests do not establish clinical accuracy."""
import json
import pytest
from app import voice_exam_core as core, voice_exam_web_research as web
from test_voice_exam import app_client, payload, Analysis
from sqlmodel import Session, select

CASES = [
 ('endo.vital_pulp','Çürüğü temizlerken sinire yaklaşabiliriz; canlı kısmı koruma seçeneğini konuşalım.'),
 ('endo.retreatment','Önceden kanal olan diş yine sızlıyor; eski dolguyu söküp yeniden bakmak gerekebilir.'),
 ('implant.planning','Kemik ölçüsünü ve yanındaki siniri görmeden vidayı nereye koyacağımıza karar vermeyelim.'),
 ('implant.maintenance','Vidalı dişler yapıldıktan sonra kontrolleri ve altını nasıl temizleyeceğimizi konuşalım.'),
 ('prosth.digital_workflow','Ağızdan taradığımız ölçüde kenar görünmemiş, laboratuvara göndermeden tekrar bakalım.'),
 ('prosth.overdenture','Alt damak oynuyor; iki implanttan destek alan çıkarılabilir protez seçeneğini konuşuyoruz.'),
 ('restorative.deep_caries','Çürük çok derin, hepsini bir anda alırsak ne olur; film ve canlılık testini görelim.'),
 ('restorative.repair','Dolgunun kenarından küçük bir parça kopmuş; tümünü mü yenileyeceğiz, tamir olur mu?'),
 ('ortho.periodontal','Diş etlerim kanarken tellere başlayabilir miyim; önce diş etine bakalım.'),
 ('surgery.bone_augmentation','Vida için kemik eklemeyi konuşuyoruz; nereden alacağız, ne kadar var henüz ölçülmedi.'),
 ('surgery.alveolitis','Çekimden üç gün sonra ağrı arttı, kötü tat var; iltihap mı oldu diye korktum.'),
 ('orofacial_pain.neuropathic','Dişime dokunmadan elektrik çarpar gibi yüzüm sızlıyor; sırf ağrı var diye dişi çekmeyelim.'),
]

@pytest.mark.parametrize('topic,dialogue', CASES)
def test_extended_topics_are_closed_and_public_research_gets_no_dialogue(topic,dialogue):
    result=core.normalize({'transcript':dialogue,'literature_topics':[{'topic':topic,'quote':dialogue}]},evidence=dialogue)
    assert result['literature_topics']==[{'topic':topic,'quote':dialogue}]
    data,_=web._public_input(result['literature_topics'],[])
    assert data['topics'][0]['id']==topic
    assert data['topics'][0]['scope']
    assert dialogue not in json.dumps(data,ensure_ascii=False)


def test_dental_history_and_habits_stay_distinct_from_systemic_history():
    quotes={'dental_history':'İki yıl önce sol öndeki dişe kanal yapılmıştı.',
            'oral_habits':'Sigara günde beş tane, araları pek temizlemiyorum.'}
    text=' '.join(quotes.values())
    facts=[{'field':field,'quote':quote,'value':'Yanlış özet',
            'temporality':'HISTORICAL' if field=='dental_history' else 'CURRENT','subject':'PATIENT'}
           for field,quote in quotes.items()]
    result=core.normalize({'transcript':text,'clinical_facts':facts},evidence=text)
    assert 'medical_history' not in result['fields']
    for field,quote in quotes.items():
        assert quote in result['fields'][field]['value']
        assert core.clinical_context({'fields':result['fields']})['fields'][field]['quote']==quote


@pytest.mark.parametrize('field,quote', [('dental_history','Daha önce kanal yapıldı mı?'),('oral_habits','Sigara içiyor musunuz?')])
def test_unanswered_history_or_habit_question_is_not_a_patient_fact(field,quote):
    assert field not in core.normalize({'transcript':quote,'fields':{field:{'value':'Var','quote':quote}}},evidence=quote)['fields']


@pytest.mark.parametrize('field,quote', [('dental_history','Eski dolgum çıktı.'),('oral_habits','Günde beş sigara içiyorum.')])
def test_legacy_history_or_habit_summary_cannot_replace_its_literal_statement(field,quote):
    output=core.normalize({'transcript':quote,'fields':{field:{'value':'Uydurulmuş ayrıntı','quote':quote}}},evidence=quote)
    assert output['fields'][field]['value']==quote


def test_new_clinical_fields_require_confirmation_and_save_as_distinct_notes(app_client):
    client,engine=app_client
    fields={'dental_history':'Önceden sol ön dişte kanal yapılmış.', 'oral_habits':'Günde beş sigara beyanı.'}
    data=payload(engine,fields=fields)
    rejected=client.post('/patients/1/voice-exam/apply',json={**data,'confirmed':False})
    assert rejected.status_code==400
    with Session(engine) as session:
        assert not session.exec(select(Analysis)).all()
    response=client.post('/patients/1/voice-exam/apply',json=data)
    assert response.status_code==200,response.text
    with Session(engine) as session:
        notes=session.exec(select(Analysis)).one().clinical_notes
        assert 'Önceki diş tedavileri: '+fields['dental_history'] in notes
        assert 'Ağız bakımı ve alışkanlıklar: '+fields['oral_habits'] in notes
        assert 'Sistemik hastalık' not in notes
    history=client.get('/patients/1/voice-exam/history').json()['fields']
    assert history['dental_history']['value']==fields['dental_history']


def test_all_eleven_reviewed_fields_can_be_saved_together(app_client):
    client,engine=app_client
    fields={'first_name':'Sentetik','last_name':'Test','age':'40',
            'chief_complaint':'Soğukta sızı beyanı.', 'medical_history':'Hastalık öyküsü yok beyanı.',
            'medications':'Düzenli ilaç yok beyanı.', 'allergies':'Bilinen alerji yok beyanı.',
            'clinical_findings':'Muayene bulguları konuşuldu.', 'plan':'Muayene sonrası değerlendirme planı.',
            'dental_history':'Eski kanal tedavisi beyanı.', 'oral_habits':'Günde beş sigara beyanı.'}
    response=client.post('/patients/1/voice-exam/apply',json=payload(engine,fields=fields))
    assert response.status_code==200,response.text
    with Session(engine) as session:
        notes=session.exec(select(Analysis)).one().clinical_notes
        assert fields['dental_history'] in notes and fields['oral_habits'] in notes
