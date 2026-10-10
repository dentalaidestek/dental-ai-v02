import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import main
from app.membership_verification import MembershipVerification, state, validate_document


@pytest.fixture
def setup(monkeypatch, tmp_path):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(main, 'on_loop', lambda *a, **kw: None)
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    def write(path, data, **kw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)
    monkeypatch.setattr(main, 'storage_write_bytes', write)
    monkeypatch.setattr(main, 'storage_ensure_local', lambda path: path)
    monkeypatch.setattr(main, 'storage_delete', lambda path: __import__('pathlib').Path(path).unlink(missing_ok=True))
    with Session(engine, expire_on_commit=False) as s:
        users = [main.User(username=name, display_name=name, role=role) for name, role in [('owner','DOCTOR'),('admin','ADMIN'),('other','DOCTOR')]]
        s.add_all(users); s.commit()
        users = {u.username: u for u in users}
    def current_user(request):
        candidate = users.get(request.headers.get('x-user', 'owner'))
        with Session(engine) as session:
            return session.get(main.User, candidate.id) if candidate else None
    monkeypatch.setattr(main, 'get_current_user', current_user)
    return engine, users, TestClient(main.app), tmp_path


def png():
    buf = io.BytesIO(); Image.new('RGB', (12,12)).save(buf, format='PNG'); return buf.getvalue()


def submit(setup, kind='DIPLOMA'):
    return setup[2].post('/account/verification', data={'document_type':kind, 'consent':'yes'}, files={'document':('belge.png', png(), 'image/png')}, follow_redirects=False)


def row(setup):
    with Session(setup[0]) as s:
        return s.exec(select(MembershipVerification).order_by(MembershipVerification.id.desc())).first()


@pytest.mark.parametrize('kind', ['DIPLOMA','GRADUATION','TDB_CARD','STUDENT'])
def test_upload_private_review_flow(setup, kind):
    engine, users, client, _ = setup
    assert submit(setup,kind).status_code == 303
    verification = row(setup)
    assert verification.status == 'PENDING'
    url = f'/account/verification/{verification.id}/document'
    assert client.get(url, headers={'x-user':'other'}).status_code == 404
    assert client.get(url, headers={'x-user':'missing'}).status_code == 401
    response = client.get(url)
    assert response.content == png()
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert client.get('/admin/member-verifications').status_code == 403
    admin_url = f'/admin/member-verifications/{verification.id}'
    assert client.post(admin_url, data={'decision':'APPROVE','identity_checked':'yes'}).status_code == 403
    assert client.post(admin_url, headers={'x-user':'admin'}, data={'decision':'APPROVE'}).status_code == 400
    assert client.get(url, headers={'x-user':'admin'}).status_code == 200
    assert client.get('/admin/member-verifications', headers={'x-user':'admin'}).status_code == 200
    assert client.post(admin_url, headers={'x-user':'admin'}, data={'decision':'APPROVE','identity_checked':'yes'}, follow_redirects=False).status_code == 303
    assert client.post(admin_url, headers={'x-user':'admin'}, data={'decision':'REJECT','reason':'No'}, follow_redirects=False).status_code == 409
    with Session(engine) as s:
        assert s.get(main.User, users['owner'].id).role == 'DOCTOR'
        assert not s.exec(select(main.ExpertProfile)).all()
        assert s.exec(select(main.AdminAuditLog).where(main.AdminAuditLog.action=='MEMBERSHIP_VERIFIED')).first()
    response = client.get('/account/verification')
    assert ('Öğrenci üyeliğiniz doğrulandı' if kind=='STUDENT' else 'Üyelik belgeniz doğrulandı') in response.text


def test_duplicate_reject_resubmit_and_identity_change(setup):
    engine, users, client, tmp = setup
    assert submit(setup).status_code == 303
    assert submit(setup).status_code == 409
    assert len(list(tmp.rglob('*.png'))) == 1
    url=f'/admin/member-verifications/{row(setup).id}'
    assert client.post(url, headers={'x-user':'admin'}, data={'decision':'REJECT','reason':' '}).status_code==400
    assert client.post(url, headers={'x-user':'admin'}, data={'decision':'REJECT','reason':'Belge okunmuyor'}, follow_redirects=False).status_code==303
    assert 'Belge okunmuyor' in client.get('/account/verification').text
    assert submit(setup).status_code==303
    url=f'/admin/member-verifications/{row(setup).id}'
    with Session(engine) as s:
        owner=s.get(main.User,users['owner'].id); owner.display_name='Changed'; s.add(owner); s.commit()
    assert client.post(url, headers={'x-user':'admin'}, data={'decision':'APPROVE','identity_checked':'yes'}).status_code==409


def test_verified_profile_change_requires_new_verification(setup):
    assert submit(setup).status_code==303
    client=setup[2]
    assert client.post(f'/admin/member-verifications/{row(setup).id}', headers={'x-user':'admin'}, data={'decision':'APPROVE','identity_checked':'yes'}, follow_redirects=False).status_code==303
    with Session(setup[0]) as s:
        owner=s.get(main.User,setup[1]['owner'].id); owner.display_name='New name'; s.add(owner); s.commit()
        assert state(s,owner)['status']=='STALE'
    assert submit(setup).status_code==303


@pytest.mark.parametrize('filename,data', [('x.png',b'bad'),('x.jpg',png()),('x.html',b'<html>'),('x.pdf',b'%PDF-corrupt'),('x.png',b''),('x.png',b'a'*(5*1024*1024+1))])
def test_invalid_documents(filename,data):
    with pytest.raises(ValueError): validate_document(filename,data)


def test_pdf_and_encrypted_pdf():
    writer=PdfWriter(); writer.add_blank_page(width=50,height=50)
    buf=io.BytesIO(); writer.write(buf)
    assert validate_document('x.pdf',buf.getvalue())=='application/pdf'
    writer.encrypt('secret'); buf=io.BytesIO(); writer.write(buf)
    with pytest.raises(ValueError): validate_document('x.pdf',buf.getvalue())


def test_profile_entry_and_steps(setup):
    client=setup[2]
    assert 'Belge Yükle' in client.get('/account').text
    response=client.get('/account/verification')
    assert response.status_code==200
    for text in ['Belge Türü','Yükleme','Gönder','Galeriden Seç','Dosya Seç (PDF)','TDB Kimlik Kartı']:
        assert text in response.text
    response=client.post('/account/verification',data={'document_type':'DIPLOMA'},files={'document':('a.png',png(),'image/png')})
    assert response.status_code==400
    assert row(setup) is None


def test_erasure_removes_document_metadata_and_returns_storage_reference(setup):
    from app.account_erasure import begin_account_erasure
    assert submit(setup).status_code==303
    path=row(setup).document_path
    with Session(setup[0]) as s:
        refs=begin_account_erasure(s,user_id=setup[1]['owner'].id,actor='user'); s.commit()
        assert path in refs
        assert not s.exec(select(MembershipVerification)).all()
