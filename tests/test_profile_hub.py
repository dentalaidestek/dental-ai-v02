from sqlmodel import Session, select

from app import main
from app.profile_hub import PROFILE_DOCUMENTS
from tests.test_membership_verification import setup, png, submit


def expert(setup, status='APPROVED'):
    with Session(setup[0], expire_on_commit=False) as s:
        owner=s.get(main.User,setup[1]['owner'].id)
        owner.profile_photo_path='photo.jpg';s.add(owner)
        s.add(main.UserAccountMeta(user_id=owner.id,professional_title='Uzman Diş Hekimi'))
        profile=main.ExpertProfile(user_id=owner.id,specialty='Endodonti',phone='05000000000',credential_document_path='credential.pdf',credential_document_name='credential.pdf',application_status=status,verification_status='VERIFIED' if status=='APPROVED' else 'PENDING',specialty_verified=status=='APPROVED',availability='AVAILABLE',consultation_price=200,bio='Keep this biography')
        s.add(profile);s.commit();return profile.id


def test_profile_sections_and_generic_document_entry(setup):
    html=setup[2].get('/account?section=professional').text
    assert 'Mesleki durum ve belgelerim' in html and 'Bilgilerim' in html
    assert 'id="professional-info" open' in html
    assert '/account/documents?purpose=membership' in html
    assert 'Uzman olarak başvur' not in html
    assert submit(setup).headers['location']==PROFILE_DOCUMENTS


def test_verified_expert_is_not_asked_for_generic_membership_document(setup):
    expert(setup)
    html=setup[2].get('/account').text
    assert 'Uzmanlık belgeniz doğrulandı' in html
    assert 'Belge Yükle ve Doğrulan' not in html
    assert '/expert-support/profile' in html
    assert f'/expert-support/expert/{setup[1]["owner"].id}' in html
    html=setup[2].get('/expert-support/profile?edit=1').text
    assert 'id="profileEdit" open' in html
    assert '/account?section=personal#personal-info' in html
    assert 'id="expertPhotoInput"' not in html
    assert 'name="credential_document"' not in html
    assert '/account/documents?purpose=expert' in html
    html=setup[2].get(f'/expert-support/expert/{setup[1]["owner"].id}').text
    assert 'href="/account#expert-info"' in html
    html=setup[2].get(f'/expert-support/expert/{setup[1]["owner"].id}',headers={'x-user':'other'}).text
    assert 'href="/expert-support"' in html


def test_first_expert_application_keeps_required_photo_and_document(setup):
    with Session(setup[0]) as s:
        s.add(main.UserAccountMeta(user_id=setup[1]['owner'].id,professional_title='Uzman Diş Hekimi'));s.commit()
    html=setup[2].get('/expert-support/profile').text
    assert 'id="expertPhotoInput"' in html
    assert 'name="credential_document"' in html
    assert 'Uzmanlık Başvurusunu Gönder' in html


def test_shared_expert_document_upload_preserves_profile_and_requires_new_review(setup):
    profile_id=expert(setup)
    client=setup[2]
    html=client.get('/account/documents?purpose=expert').text
    assert 'action="/account/documents/expert"' in html
    assert 'name="credential_document"' in html
    assert 'data-max-mb="10"' in html
    response=client.post('/account/documents/expert',files={'credential_document':('new.png',png(),'image/png')},follow_redirects=False)
    assert response.status_code==303 and response.headers['location']==PROFILE_DOCUMENTS
    assert client.get('/account/documents?purpose=expert',follow_redirects=False).status_code==303
    assert client.post('/account/documents/expert',files={'credential_document':('again.png',png(),'image/png')}).status_code==409
    with Session(setup[0]) as s:
        profile=s.get(main.ExpertProfile,profile_id)
        assert profile.bio=='Keep this biography'
        assert profile.specialty=='Endodonti' and profile.consultation_price==200
        assert profile.application_status=='SUBMITTED' and profile.verification_status=='PENDING'
        assert not profile.specialty_verified and profile.availability=='PASSIVE'
    assert client.get('/account/documents?purpose=expert',headers={'x-user':'other'}).status_code==403
    assert client.post('/account/documents/expert',headers={'x-user':'other'},files={'credential_document':('new.png',png(),'image/png')}).status_code==403


def test_unvan_document_uses_shared_wizard_and_keeps_current_expert_active(setup):
    profile_id=expert(setup)
    with Session(setup[0]) as s:
        change=main.ExpertTitleChange(user_id=setup[1]['owner'].id,requested_title='Doç. Dr.',previous_title='Uzman Diş Hekimi',status='AWAITING_DOCUMENT')
        s.add(change);s.commit()
    client=setup[2]
    for url in ['/account/documents?purpose=title','/account/professional-title/document']:
        response=client.get(url)
        assert response.status_code==200
        assert 'Unvan Belgesi' in response.text and 'name="credential_document"' in response.text
        assert 'action="/account/professional-title/document"' in response.text
    assert 'Yeni unvan: Doç. Dr.' in client.get('/account?section=professional').text
    response=client.post('/account/professional-title/document',files={'credential_document':('title.png',png(),'image/png')},follow_redirects=False)
    assert response.status_code==303 and response.headers['location']==PROFILE_DOCUMENTS
    with Session(setup[0]) as s:
        profile=s.get(main.ExpertProfile,profile_id)
        assert profile.application_status=='APPROVED' and profile.verification_status=='VERIFIED'
        assert profile.availability=='AVAILABLE'
    response=client.get('/account/documents?purpose=title',follow_redirects=False)
    assert response.status_code==303


def test_shared_document_access_and_invalid_upload(setup):
    client=setup[2]
    assert client.get('/account/documents',headers={'x-user':'missing'},follow_redirects=False).status_code==303
    assert client.get('/account/documents?purpose=bogus').status_code==400
    expert(setup)
    response=client.post('/account/documents/expert',files={'credential_document':('new.png',b'bad','image/png')})
    assert response.status_code==400
    with Session(setup[0]) as s:
        assert s.exec(select(main.ExpertProfile)).one().application_status=='APPROVED'


def test_pending_expert_does_not_receive_a_second_document_prompt(setup):
    expert(setup,status='SUBMITTED')
    html=setup[2].get('/account').text
    assert 'Uzmanlık belgesi inceleniyor' in html
    assert 'Belge Yükle ve Doğrulan' not in html
    assert 'Yeni belge gönder' not in html
