"""Native consultation adapters must preserve participant and web lifecycle rules."""
import io
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import SQLModel, Session, create_engine
from app import main, mobile_api

@pytest.fixture
def chat(monkeypatch,tmp_path):
    engine=create_engine("sqlite:///"+str(tmp_path/"chat.db"),connect_args={"check_same_thread":False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,"engine",engine)
    monkeypatch.setattr(mobile_api,"engine",engine)
    monkeypatch.setattr(main,"UPLOAD_DIR",tmp_path/"uploads")
    monkeypatch.setattr(main,"storage_write_bytes",lambda path,raw,**kwargs:path.write_bytes(raw))
    monkeypatch.setattr(main,"storage_ensure_local",lambda path:__import__("pathlib").Path(path))
    monkeypatch.setattr(mobile_api,"storage_ensure_local",lambda path:__import__("pathlib").Path(path))
    monkeypatch.setattr(main,"storage_delete",lambda *args:None)
    with Session(engine) as s:
        for i in (1,2,3):
            s.add(main.User(id=i,username="chat-user-"+str(i),display_name="Synthetic "+str(i),role="DOCTOR",
                is_active=True,email_verified_at=main._utcnow_naive()))
            s.add(main.SessionToken(token_hash=main.hash_session_token("token"+str(i)),user_id=i,
                expires_at=main._utcnow_naive()+timedelta(days=1)))
        s.add(main.ConsultationCase(id=1,requester_user_id=1,expert_user_id=2,specialty="Endodonti",
            clinical_summary="Synthetic",question="Synthetic",status="ACTIVE",
            expert_response_deadline=main._utcnow_naive()+timedelta(hours=1)))
        s.commit()
    c=TestClient(main.app);c.headers["Authorization"]="Bearer token1"
    return c,engine

def test_two_participants_share_persisted_text_and_outsider_is_rejected(chat):
    c,engine=chat
    r=c.post("/api/mobile/v1/consultations/1/messages",json={"content":"Synthetic first","client_message_id":"first"})
    assert r.status_code==200,r.text
    ident=r.json()["message"]["id"]
    c.headers["Authorization"]="Bearer token2"
    r=c.post("/api/mobile/v1/consultations/1/messages",json={"content":"Synthetic reply","reply_to_message_id":ident,"client_message_id":"reply"})
    assert r.status_code==200,r.text
    messages=c.get("/api/mobile/v1/consultations/1").json()["messages"]
    assert [m["sender_user_id"] for m in messages]==[1,2]
    assert messages[1]["reply_to_message_id"]==ident
    c.headers["Authorization"]="Bearer token3"
    assert c.get("/api/mobile/v1/consultations/1").status_code==404
    assert c.post("/api/mobile/v1/consultations/1/actions",json={"action":"complete"}).status_code==403

def test_photo_upload_is_sanitized_and_attachment_authorized(chat):
    c,engine=chat
    raw=io.BytesIO();Image.new("RGB",(12,12),"white").save(raw,format="PNG")
    r=c.post("/api/mobile/v1/consultations/1/attachments",files={"file":("image.png",raw.getvalue(),"image/png")})
    assert r.status_code==200,r.text
    ident=r.json()["message"]["id"]
    assert c.get("/api/mobile/v1/consultations/1").json()["messages"][-1]["has_media"] is True
    r=c.get(f"/api/mobile/v1/consultations/1/attachments/{ident}")
    assert r.status_code==200
    assert r.headers["cache-control"]=="private, no-store"
    c.headers["Authorization"]="Bearer token2"
    assert c.get(f"/api/mobile/v1/consultations/1/attachments/{ident}").status_code==200
    c.headers["Authorization"]="Bearer token3"
    assert c.get(f"/api/mobile/v1/consultations/1/attachments/{ident}").status_code==404

def test_malformed_or_unsupported_upload_does_not_create_message(chat):
    c,engine=chat
    assert c.post("/api/mobile/v1/consultations/1/attachments",files={"file":("bad.jpg",b"not an image","image/jpeg")}).status_code==422
    assert c.post("/api/mobile/v1/consultations/1/attachments",files={"file":("script.exe",b"bad","application/octet-stream")}).status_code==415
    assert c.get("/api/mobile/v1/consultations/1").json()["messages"]==[]

def test_completion_reuses_web_roles_and_transitions(chat):
    c,engine=chat
    c.headers["Authorization"]="Bearer token2"
    r=c.post("/api/mobile/v1/consultations/1/actions",json={"action":"complete"})
    assert r.status_code==200,r.text
    assert c.get("/api/mobile/v1/consultations/1").json()["case"]["status"]=="EXPERT_COMPLETED"
    c.headers["Authorization"]="Bearer token1"
    r=c.post("/api/mobile/v1/consultations/1/actions",json={"action":"complete","completion_action":"CONTINUE"})
    assert r.status_code==200,r.text
    assert c.get("/api/mobile/v1/consultations/1").json()["case"]["status"]=="ACTIVE"

def test_delete_is_local_and_restore_preserves_messages(chat):
    c,engine=chat
    r=c.post("/api/mobile/v1/consultations/1/actions",json={"action":"delete"})
    assert r.status_code==200,r.text
    assert c.get("/api/mobile/v1/consultations").json()["items"]==[]
    assert c.get("/api/mobile/v1/messages/deleted").json()["items"][0]["id"]==1
    c.headers["Authorization"]="Bearer token2"
    assert c.get("/api/mobile/v1/consultations").json()["items"][0]["id"]==1
    c.headers["Authorization"]="Bearer token1"
    assert c.post("/api/mobile/v1/consultations/1/actions",json={"action":"restore"}).status_code==200
    assert c.get("/api/mobile/v1/consultations").json()["items"][0]["id"]==1

def test_action_validation_rejects_unknown_lifecycle_operation(chat):
    c,engine=chat
    assert c.post("/api/mobile/v1/consultations/1/actions",json={"action":"grant-admin"}).status_code==422
    assert c.post("/api/mobile/v1/consultations/1/actions",json={"action":"review","rating":8}).status_code==422

def test_pdf_and_audio_share_the_existing_web_attachment_workflow(chat):
    from pypdf import PdfWriter
    import wave
    c,engine=chat
    pdf=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=72,height=72);writer.write(pdf)
    audio=io.BytesIO()
    with wave.open(audio,"wb") as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(8000);output.writeframes(b"\x00\x00"*80)
    for name,raw,mime,kind in [("case.pdf",pdf.getvalue(),"application/pdf","FILE"),("voice.wav",audio.getvalue(),"audio/wav","VOICE")]:
        r=c.post("/api/mobile/v1/consultations/1/attachments",files={"file":(name,raw,mime)})
        assert r.status_code==200,r.text
        assert r.json()["message"]["message_type"]==kind
        ident=r.json()["message"]["id"]
        media=c.get(f"/api/mobile/v1/consultations/1/attachments/{ident}")
        assert media.status_code==200
        assert media.content==raw

def test_spoofed_document_and_audio_content_never_reach_web_storage(chat):
    c,engine=chat
    for name,mime in [("case.pdf","application/pdf"),("voice.mp3","audio/mpeg"),("voice.m4a","audio/mp4"),("voice.wav","audio/wav"),("voice.ogg","audio/ogg")]:
        assert c.post("/api/mobile/v1/consultations/1/attachments",files={"file":(name,b"not a supported document",mime)}).status_code==422
    assert c.get("/api/mobile/v1/consultations/1").json()["messages"]==[]

def test_case_shared_media_is_selected_link_scoped_and_private(chat, tmp_path):
    c,engine=chat
    path=tmp_path/'shared.png';Image.new('RGB',(4,4),'white').save(path)
    with Session(engine) as s:
        p=main.Patient(anonymous_id='SYNTHETIC',owner_user_id=1);s.add(p);s.flush()
        media=main.PatientMedia(patient_id=p.id,owner_user_id=1,file_path=str(path),original_filename='synthetic.png',stored_filename='shared.png',media_type='PHOTO');s.add(media);s.flush()
        s.add(main.ConsultationCaseMedia(id=5,case_id=1,patient_media_id=media.id,added_by_user_id=1));s.commit()
    for token in ('token1','token2'):
        c.headers['Authorization']='Bearer '+token
        shared=c.get('/api/mobile/v1/consultations/1').json()['case']['shared_media']
        assert shared==[{'id':5,'media_type':'PHOTO'}]
        response=c.get('/api/mobile/v1/consultations/1/shared-media/5')
        assert response.status_code==200
        assert response.headers['cache-control']=='private, no-store'
        assert c.get('/api/mobile/v1/consultations/1/shared-media/6').status_code==404
    c.headers['Authorization']='Bearer token3'
    assert c.get('/api/mobile/v1/consultations/1/shared-media/5').status_code==404
