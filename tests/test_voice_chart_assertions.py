"""Chart candidate guards test explicit language, not clinical diagnosis."""
import pytest
from app import voice_exam_core as core


def candidate(status, quote):
    return core.normalize({'transcript':quote,'teeth':[{'tooth':'46','status':status,'quote':quote}]})


@pytest.mark.parametrize('status,quote',[
 ('EXTRACTED','46 numaralı dişi yarın çekeceğiz.'),
 ('EXTRACTED','46 numarayı çekelim.'),
 ('EXTRACTED','46 henüz çekilmedi.'),
 ('EXTRACTED','46 çekilmiş olabilir.'),
 ('IMPLANT','46 bölgesine implant yerleştireceğiz.'),
 ('IMPLANT','46 için implant düşünüyoruz.'),
 ('CROWN','46 dişe kaplama yapacağız.'),
 ('FILLING','46 numaraya dolgu yapılacak.'),
 ('ROOT_CANAL','46 kanal tedavisi gerektiriyor.'),
 ('ROOT_CANAL','46 kanal tedavisine başlayacağız.'),
 ('FILLING','46 numarada dolgu yok.'),
 ('CROWN','46 kuronlu değil.'),
 ('IMPLANT','46 implant olabilir mi?'),
 ('FILLING','46 numarada hassasiyet var.'),
])
def test_proposed_uncertain_negated_or_unrelated_status_cannot_become_chart_finding(status,quote):
    output=candidate(status,quote)
    assert output['teeth']==[]
    assert output['uncertain'], 'Withheld candidate must not silently disappear'
    assert output['transcript']==quote


@pytest.mark.parametrize('status,quote',[
 ('EXTRACTED','46 çekilmiş.'),
 ('IMPLANT','46 bölgesinde implant mevcut.'),
 ('CROWN','46 kuronlu.'),
 ('FILLING','46 numarada dolgu var.'),
 ('ROOT_CANAL','46 kanal tedavili.'),
 ('FILLING','46 dolgusu var, yarın çekilecek.'),
])
def test_explicit_existing_finding_remains_a_candidate_for_clinician_approval(status,quote):
    assert candidate(status,quote)['teeth'][0]['status']==status


@pytest.mark.parametrize('status,quote',[
 ('FILLING',"46'da ağrı var, 47'de dolgu var."),
 ('EXTRACTED','46 dolgu var, 47 çekildi.'),
 ('IMPLANT','46 çekilmiş, 47 implant mevcut.'),
 ('IMPLANT','46 kanal tedavili ve 47 implant mevcut.'),
 ('EXTRACTED','46 çekim.'),
])
def test_another_tooth_or_an_ambiguous_procedure_label_is_not_existing_state(status,quote):
    assert candidate(status,quote)['teeth']==[]


@pytest.mark.parametrize('status,quote',[
 ('IMPLANT','46 dolgusu var ve implant yerleştireceğiz.'),
 ('CROWN','46 dolgusu var ve kaplama yapacağız.'),
 ('ROOT_CANAL','46 dolgusu var ve kanal tedavisi planlıyoruz.'),
])
def test_existing_other_procedure_cannot_turn_a_new_plan_into_existing_finding(status,quote):
    assert candidate(status,quote)['teeth']==[]


from test_voice_exam import app_client, payload, ToothStatus, Analysis


def test_planned_procedure_cannot_create_a_chart_record_through_normalized_apply_flow(app_client):
    from sqlmodel import Session, select
    client,engine=app_client
    output=candidate('EXTRACTED','46 numaralı dişi yarın çekeceğiz.')
    result=client.post('/patients/1/voice-exam/apply',json=payload(engine,fields={},teeth=[{'tooth':t['tooth'],'status':t['status'],'note':t['quote']} for t in output['teeth']]))
    assert result.status_code==400
    with Session(engine) as session:
        assert session.exec(select(ToothStatus)).all()==[]
        assert session.exec(select(Analysis)).all()==[]


def test_explicit_candidate_without_physician_confirmation_cannot_write_chart(app_client):
    from sqlmodel import Session, select
    client,engine=app_client
    output=candidate('EXTRACTED','46 çekilmiş.')
    result=client.post('/patients/1/voice-exam/apply',json=payload(engine,confirmed=False,fields={},teeth=[{'tooth':t['tooth'],'status':t['status'],'note':t['quote']} for t in output['teeth']]))
    assert result.status_code==400
    with Session(engine) as session:
        assert session.exec(select(ToothStatus)).all()==[]
        assert session.exec(select(Analysis)).all()==[]


def test_turkish_capital_i_does_not_hide_an_existing_implant():
    assert candidate('IMPLANT','46 İmplant mevcut.')['teeth'][0]['status']=='IMPLANT'


@pytest.mark.parametrize('status,quote',[
 ('CARIES','46 çürük var mı'),
 ('CARIES','46 çürük var mıdır'),
 ('FILLING','46 dolgu var mı'),
 ('FILLING','Kırk altı ağrılı ve kırk yedi dolgulu.'),
 ('IMPLANT','46 bölgesine implant takacağız.'),
 ('CROWN','46 numaraya kaplama yapılmalı.'),
 ('IMPLANT','46 bölgesine implant yapılırsa rahatlar.'),
])
def test_interrogatives_spoken_subjects_and_unlisted_proposals_remain_unconfirmed(status,quote):
    assert candidate(status,quote)['teeth']==[]
