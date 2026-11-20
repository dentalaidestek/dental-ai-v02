"""Native consultation adapters must preserve participant and web lifecycle rules."""
import io
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import SQLModel, Session, create_engine, select
from app import main, mobile_api

_SESSION_TOKEN={1:"token1-"+"A"*28,2:"token2-"+"A"*28,3:"token3-"+"A"*28}

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
            s.add(main.SessionToken(token_hash=main.hash_session_token(_SESSION_TOKEN[i]),user_id=i,
                expires_at=main._utcnow_naive()+timedelta(days=1)))
        s.add(main.ConsultationCase(id=1,requester_user_id=1,expert_user_id=2,specialty="Endodonti",
            clinical_summary="Synthetic",question="Synthetic",status="ACTIVE",
            expert_response_deadline=main._utcnow_naive()+timedelta(hours=1)))
        s.commit()
    c=TestClient(main.app);c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[1]
    return c,engine

def test_two_participants_share_persisted_text_and_outsider_is_rejected(chat):
    c,engine=chat
    r=c.post("/api/mobile/v1/consultations/1/messages",json={"content":"Synthetic first","client_message_id":"native-first-00000001"})
    assert r.status_code==200,r.text
    ident=r.json()["message"]["id"]
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[2]
    r=c.post("/api/mobile/v1/consultations/1/messages",json={"content":"Synthetic reply","reply_to_message_id":ident,"client_message_id":"native-reply-00000001"})
    assert r.status_code==200,r.text
    messages=c.get("/api/mobile/v1/consultations/1").json()["messages"]
    assert [m["sender_user_id"] for m in messages]==[1,2]
    assert messages[1]["reply_to_message_id"]==ident
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[3]
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
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[2]
    assert c.get(f"/api/mobile/v1/consultations/1/attachments/{ident}").status_code==200
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[3]
    assert c.get(f"/api/mobile/v1/consultations/1/attachments/{ident}").status_code==404

def test_malformed_or_unsupported_upload_does_not_create_message(chat):
    c,engine=chat
    assert c.post("/api/mobile/v1/consultations/1/attachments",files={"file":("bad.jpg",b"not an image","image/jpeg")}).status_code==422
    assert c.post("/api/mobile/v1/consultations/1/attachments",files={"file":("script.exe",b"bad","application/octet-stream")}).status_code==415
    assert c.get("/api/mobile/v1/consultations/1").json()["messages"]==[]

def test_completion_reuses_web_roles_and_transitions(chat):
    c,engine=chat
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[2]
    r=c.post("/api/mobile/v1/consultations/1/actions",json={"action":"complete"})
    assert r.status_code==200,r.text
    assert c.get("/api/mobile/v1/consultations/1").json()["case"]["status"]=="EXPERT_COMPLETED"
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[1]
    r=c.post("/api/mobile/v1/consultations/1/actions",json={"action":"complete","completion_action":"CONTINUE"})
    assert r.status_code==200,r.text
    assert c.get("/api/mobile/v1/consultations/1").json()["case"]["status"]=="ACTIVE"

def test_delete_is_local_and_restore_preserves_messages(chat):
    c,engine=chat
    r=c.post("/api/mobile/v1/consultations/1/actions",json={"action":"delete"})
    assert r.status_code==200,r.text
    assert c.get("/api/mobile/v1/consultations").json()["items"]==[]
    assert c.get("/api/mobile/v1/messages/deleted").json()["items"][0]["id"]==1
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[2]
    assert c.get("/api/mobile/v1/consultations").json()["items"][0]["id"]==1
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[1]
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
    for token in (_SESSION_TOKEN[1], _SESSION_TOKEN[2]):
        c.headers['Authorization']='Bearer '+token
        shared=c.get('/api/mobile/v1/consultations/1').json()['case']['shared_media']
        assert shared==[{'id':5,'media_type':'PHOTO'}]
        response=c.get('/api/mobile/v1/consultations/1/shared-media/5')
        assert response.status_code==200
        assert response.headers['cache-control']=='private, no-store'
        assert c.get('/api/mobile/v1/consultations/1/shared-media/6').status_code==404
    c.headers['Authorization']='Bearer ' + _SESSION_TOKEN[3]
    assert c.get('/api/mobile/v1/consultations/1/shared-media/5').status_code==404


def test_text_message_receipt_replays_once_and_rejects_payload_reuse(chat):
    c, engine = chat
    key = "native-text-receipt-000001"
    first = c.post("/api/mobile/v1/consultations/1/messages",
                   json={"content": "Aynı klinik mesaj", "client_message_id": key})
    assert first.status_code == 200, first.text
    second = c.post("/api/mobile/v1/consultations/1/messages",
                    json={"content": "Aynı klinik mesaj", "client_message_id": key})
    assert second.status_code == 200, second.text
    assert second.json()["replayed"] is True
    assert second.json()["message"]["id"] == first.json()["message"]["id"]
    conflict = c.post("/api/mobile/v1/consultations/1/messages",
                      json={"content": "Farklı içerik", "client_message_id": key})
    assert conflict.status_code == 409
    with Session(engine) as session:
        rows = session.exec(select(main.ConsultationMessage).where(
            main.ConsultationMessage.case_id == 1,
            main.ConsultationMessage.sender_user_id == 1,
        )).all()
        assert len(rows) == 1


def test_message_receipt_is_private_and_sender_scoped(chat):
    c, engine = chat
    key = "native-scope-receipt-0001"
    first = c.post("/api/mobile/v1/consultations/1/messages",
                   json={"content": "Gönderen hesabın mesajı", "client_message_id": key})
    assert first.status_code == 200, first.text
    own = c.get(f"/api/mobile/v1/consultations/1/message-receipt?client_message_id={key}")
    assert own.status_code == 200
    assert own.headers["cache-control"] == "private, no-store"
    assert own.json()["message"]["id"] == first.json()["message"]["id"]
    c.headers["Authorization"] = "Bearer "+_SESSION_TOKEN[2]
    peer = c.get(f"/api/mobile/v1/consultations/1/message-receipt?client_message_id={key}")
    assert peer.status_code == 200
    assert peer.json()["message"] is None
    c.headers["Authorization"] = "Bearer "+_SESSION_TOKEN[3]
    assert c.get(f"/api/mobile/v1/consultations/1/message-receipt?client_message_id={key}").status_code == 404


def test_same_client_key_is_isolated_between_consultation_participants(chat):
    c, engine = chat
    key = "native-two-senders-0001"
    first = c.post("/api/mobile/v1/consultations/1/messages",
                   json={"content": "İlk hekim", "client_message_id": key})
    assert first.status_code == 200, first.text
    c.headers["Authorization"] = "Bearer "+_SESSION_TOKEN[2]
    second = c.post("/api/mobile/v1/consultations/1/messages",
                    json={"content": "Uzman yanıtı", "client_message_id": key})
    assert second.status_code == 200, second.text
    assert second.json()["message"]["id"] != first.json()["message"]["id"]
    with Session(engine) as session:
        rows = session.exec(select(main.ConsultationMessage).where(
            main.ConsultationMessage.case_id == 1,
        )).all()
        assert len(rows) == 2


def test_media_message_receipt_replays_same_bytes_and_rejects_changed_bytes(chat):
    import wave
    c, engine = chat
    def wav(sample):
        raw = io.BytesIO()
        with wave.open(raw, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(sample * 80)
        return raw.getvalue()
    key = "native-media-receipt-0001"
    payload = wav(b"\x00\x00")
    first = c.post("/api/mobile/v1/consultations/1/attachments",
                   files={"file": ("voice.wav", payload, "audio/wav")},
                   data={"client_message_id": key})
    assert first.status_code == 200, first.text
    second = c.post("/api/mobile/v1/consultations/1/attachments",
                    files={"file": ("voice-copy.wav", payload, "audio/wav")},
                    data={"client_message_id": key})
    assert second.status_code == 200, second.text
    assert second.json()["message"]["id"] == first.json()["message"]["id"]
    conflict = c.post("/api/mobile/v1/consultations/1/attachments",
                      files={"file": ("voice.wav", wav(b"\x01\x00"), "audio/wav")},
                      data={"client_message_id": key})
    assert conflict.status_code == 409
    with Session(engine) as session:
        rows = session.exec(select(main.ConsultationMessage).where(
            main.ConsultationMessage.case_id == 1,
            main.ConsultationMessage.sender_user_id == 1,
        )).all()
        assert len(rows) == 1

def test_chat_retention_removes_message_receipts(chat):
    c, engine = chat
    key = "native-retention-receipt-0001"
    sent = c.post("/api/mobile/v1/consultations/1/messages",
                  json={"content": "Retained only until policy expiry", "client_message_id": key})
    assert sent.status_code == 200, sent.text
    with Session(engine) as session:
        case = session.get(main.ConsultationCase, 1)
        main._purge_consultation_messages(session, case, main._utcnow_naive(), actor_id=1)
        session.commit()
        assert session.exec(select(main.ConsultationMessageReceipt).where(
            main.ConsultationMessageReceipt.case_id == 1,
        )).all() == []
    receipt = c.get(f"/api/mobile/v1/consultations/1/message-receipt?client_message_id={key}")
    assert receipt.status_code == 200
    assert receipt.headers["cache-control"] == "private, no-store"
    assert receipt.json() == {"message": None, "deleted": True}

def test_consultation_receipt_schema_is_compact_and_sender_scoped():
    columns = [column.name for column in main.ConsultationMessageReceipt.__table__.primary_key.columns]
    assert columns == ["case_id", "sender_user_id", "client_message_id"]
    assert "content" not in main.ConsultationMessageReceipt.__table__.columns


def test_attachment_receipt_hash_binds_bytes_and_reply_but_not_filename():
    same_a = main._consultation_message_payload_hash(1, 7, "VOICE", "patient-a.wav", 12, b"audio-bytes")
    same_b = main._consultation_message_payload_hash(1, 7, "VOICE", "renamed.wav", 12, b"audio-bytes")
    changed_bytes = main._consultation_message_payload_hash(1, 7, "VOICE", "patient-a.wav", 12, b"changed-audio")
    changed_reply = main._consultation_message_payload_hash(1, 7, "VOICE", "patient-a.wav", 13, b"audio-bytes")
    assert same_a == same_b
    assert same_a != changed_bytes
    assert same_a != changed_reply


def test_consultation_client_intent_key_has_bounded_format():
    assert main._normalize_consultation_client_message_id("native-key-000000000001") == "native-key-000000000001"
    with pytest.raises(main.HTTPException) as error:
        main._normalize_consultation_client_message_id("short")
    assert error.value.status_code == 422

