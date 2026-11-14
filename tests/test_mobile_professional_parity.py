from test_mobile_chat_actions import chat
from test_mobile_account_parity import account
from app import main
from sqlmodel import Session, select
from app.membership_verification import MembershipVerification
import io
from PIL import Image


def png():
    raw=io.BytesIO();Image.new('RGB',(12,12),'white').save(raw,format='PNG');return raw.getvalue()


def test_native_title_requires_confirmation_and_keeps_verified_identity(account):
    client,engine,_=account
    with Session(engine) as s:
        s.add(main.UserAccountMeta(user_id=1,professional_title='Doç. Dr.'))
        s.add(main.ExpertProfile(user_id=1,specialty='Endodonti',application_status='APPROVED',verification_status='VERIFIED',specialty_verified=True,credential_document_path='existing.pdf',availability='AVAILABLE'))
        s.commit()
    route='/api/mobile/v1/account/professional-title'
    assert client.post(route,json={'professional_title':'Prof. Dr.','confirm_change':False}).status_code==400
    response=client.post(route,json={'professional_title':'Prof. Dr.','confirm_change':True})
    assert response.status_code==200,response.text
    hub=client.get('/api/mobile/v1/account/professional').json()
    assert hub['current_title']=='Doç. Dr.'
    assert hub['title_change']['requested_title']=='Prof. Dr.' and hub['title_change']['status']=='AWAITING_DOCUMENT'
    assert hub['expert']['availability']=='AVAILABLE'
    assert client.post(route,json={'professional_title':'Öğrenci','confirm_change':True}).status_code==409
    upload=client.post('/api/mobile/v1/account/documents/title',files={'file':('credential.png',png(),'image/png')})
    assert upload.status_code==200,upload.text
    hub=upload.json()['professional'];assert hub['title_change']['status']=='PENDING_REVIEW' and hub['current_title']=='Doç. Dr.'
    assert client.post('/api/mobile/v1/account/documents/title',files={'file':('credential.png',png(),'image/png')}).status_code==409


def test_membership_document_consent_validation_owner_and_no_expert_grant(account,monkeypatch):
    def store(path,raw,**kwargs):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);return str(path)
    monkeypatch.setattr(main,"storage_write_bytes",store)
    client,engine,_=account;route='/api/mobile/v1/account/documents/membership'
    assert client.post(route,data={'document_type':'STUDENT','consent':'no'},files={'file':('proof.png',png(),'image/png')}).status_code==400
    assert client.post(route,data={'document_type':'STUDENT','consent':'yes'},files={'file':('proof.pdf',b'not a PDF','application/pdf')}).status_code==400
    result=client.post(route,data={'document_type':'STUDENT','consent':'yes'},files={'file':('proof.png',png(),'image/png')})
    assert result.status_code==200,result.text
    hub=result.json()['professional'];assert hub['membership']['status']=='PENDING' and hub['expert'] is None
    assert 'document_path' not in str(hub)
    assert client.post(route,data={'document_type':'STUDENT','consent':'yes'},files={'file':('proof.png',png(),'image/png')}).status_code==409
    with Session(engine) as s:assert len(s.exec(select(MembershipVerification)).all())==1
    client.headers['Authorization']='Bearer token2'
    other=client.get('/api/mobile/v1/account/professional').json();assert other['membership']['status']=='NONE' and other['title_change'] is None


def test_expert_profile_creation_preserves_web_rules_and_reverification(account,tmp_path):
    client,engine,_=account
    route='/api/mobile/v1/account/expert-profile'
    values={'specialty':'Endodonti','phone':'05551234567','institution':'Synthetic University','bio':'Synthetic bio','orcid_url':'0000-0002-1825-0097','publications_text':'Synthetic publication','consultation_price':100000}
    assert client.post(route,data=values).status_code==403
    with Session(engine) as s:
        s.add(main.UserAccountMeta(user_id=1,professional_title='Doç. Dr.'));user=s.get(main.User,1);user.profile_photo_path='photo.jpg';s.add(user);s.commit()
    assert client.post(route,data=values).status_code==400
    bad=client.post(route,data=values,files={'file':('bad.pdf',b'not a PDF','application/pdf')});assert bad.status_code==400
    result=client.post(route,data=values,files={'file':('credential.png',png(),'image/png')})
    assert result.status_code==200,result.text
    profile=result.json()['professional']['expert']
    assert profile['application_status']=='SUBMITTED' and profile['availability']=='PASSIVE' and profile['orcid_url']=='https://orcid.org/0000-0002-1825-0097'
    with Session(engine) as s:
        p=s.exec(select(main.ExpertProfile).where(main.ExpertProfile.user_id==1)).one();p.application_status='APPROVED';p.verification_status='VERIFIED';p.specialty_verified=True;p.availability='AVAILABLE';s.add(p);s.commit()
    result=client.post(route,data={**values,'bio':'Updated bio'});assert result.status_code==200,result.text
    assert result.json()['professional']['expert']['availability']=='AVAILABLE'
    result=client.post(route,data={**values,'specialty':'Ortodonti'});assert result.status_code==200,result.text
    assert result.json()['professional']['expert']['verification_status']=='PENDING'
    assert result.json()['professional']['expert']['availability']=='PASSIVE'


def test_unverified_accounts_cannot_set_availability_and_invalid_title_rejected(account):
    client,engine,_=account
    assert client.post('/api/mobile/v1/account/professional-title',json={'professional_title':'ADMIN','confirm_change':True}).status_code==400
    assert client.get('/api/mobile/v1/account/professional').status_code==200
    client.headers.pop('Authorization');assert client.get('/api/mobile/v1/account/professional').status_code==401


def test_native_availability_requires_current_rules_and_preserves_manual_choice(account):
    client,engine,_=account
    with Session(engine) as s:
        s.add(main.UserAccountMeta(user_id=1,professional_title='Doç. Dr.'))
        s.add(main.ExpertProfile(user_id=1,specialty='Endodonti',application_status='APPROVED',verification_status='VERIFIED',specialty_verified=True,credential_document_path='proof.pdf',phone='05551234567',availability='BUSY'))
        s.commit()
    route='/api/mobile/v1/account/expert-availability'
    assert client.post(route,json={'availability':'AVAILABLE'}).status_code==409
    rules=client.get('/api/mobile/v1/account/expert-rules')
    assert rules.status_code==200,rules.text
    data=rules.json();assert '10 dakika' in data['text'] and not data['accepted']
    assert client.post('/api/mobile/v1/account/expert-rules',json={'version':'old','accepted':True}).status_code==409
    assert client.post('/api/mobile/v1/account/expert-rules',json={'version':data['version'],'accepted':False}).status_code==400
    assert client.post('/api/mobile/v1/account/expert-rules',json={'version':data['version'],'accepted':True}).status_code==200
    assert client.post(route,json={'availability':'AVAILABLE'}).status_code==200
    assert client.post(route,json={'availability':'BUSY'}).status_code==200
    with Session(engine) as s:
        p=s.exec(select(main.ExpertProfile).where(main.ExpertProfile.user_id==1)).one();assert p.availability=='BUSY' and not p.capacity_auto_busy
    client.headers['Authorization']='Bearer token2'
    assert client.post(route,json={'availability':'AVAILABLE'}).status_code==404


def test_native_expert_document_reopens_review_and_closes_new_case_intake(account,monkeypatch):
    client,engine,_=account
    def store(path,raw,**kwargs):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);return str(path)
    monkeypatch.setattr(main,'storage_write_bytes',store)
    with Session(engine) as s:
        s.add(main.UserAccountMeta(user_id=1,professional_title='Doç. Dr.'))
        s.add(main.ExpertProfile(user_id=1,specialty='Endodonti',phone='05551234567',application_status='APPROVED',verification_status='VERIFIED',specialty_verified=True,credential_document_path='old.pdf',availability='AVAILABLE'));s.commit()
    route='/api/mobile/v1/account/documents/expert'
    result=client.post(route,files={'file':('updated.png',png(),'image/png')})
    assert result.status_code==200,result.text
    profile=result.json()['professional']['expert']
    assert profile['application_status']=='SUBMITTED' and profile['verification_status']=='PENDING' and not profile['specialty_verified'] and profile['availability']=='PASSIVE'
    assert client.post(route,files={'file':('updated.png',png(),'image/png')}).status_code==409
    client.headers['Authorization']='Bearer token2'
    assert client.post(route,files={'file':('updated.png',png(),'image/png')}).status_code==403
