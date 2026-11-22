"""Five-route web-parity regression matrix (PR #257).

Routes: POST/GET consultations attachments, messages/unread-count,
notifications/unread-count, experts/performance-info. Each route is locked to
the canonical web handler semantics found in app/main.py: case/patient
ownership, authorization, sender-scoped idempotency receipts, same-key crash
recovery and wrong-account denial.
"""
import io
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import SQLModel, Session, create_engine, select
from app import main, mobile_api, mobile_modern_api_v3

_SESSION_TOKEN={1:"parity1-"+"A"*28,2:"parity2-"+"A"*28,3:"parity3-"+"A"*28,4:"parity4-"+"A"*28}


@pytest.fixture
def parity(monkeypatch,tmp_path):
    engine=create_engine("sqlite:///"+str(tmp_path/"parity.db"),connect_args={"check_same_thread":False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,"engine",engine)
    monkeypatch.setattr(mobile_api,"engine",engine)
    monkeypatch.setattr(mobile_modern_api_v3,"engine",engine)
    monkeypatch.setattr(main,"UPLOAD_DIR",tmp_path/"uploads")
    monkeypatch.setattr(main,"storage_write_bytes",lambda path,raw,**kwargs:path.write_bytes(raw))
    monkeypatch.setattr(main,"storage_ensure_local",lambda path:__import__("pathlib").Path(path))
    monkeypatch.setattr(mobile_api,"storage_ensure_local",lambda path:__import__("pathlib").Path(path))
    monkeypatch.setattr(main,"storage_delete",lambda *args:None)
    with Session(engine) as s:
        for i in (1,2,3,4):
            # user4 keeps the plain "USER" role: the web performance-info page
            # only requires a signed-in account, never an expert profile.
            s.add(main.User(id=i,username="parity-user-"+str(i),display_name="Parity "+str(i),
                role="USER" if i==4 else "DOCTOR",is_active=True,email_verified_at=main._utcnow_naive()))
            s.add(main.SessionToken(token_hash=main.hash_session_token(_SESSION_TOKEN[i]),user_id=i,
                expires_at=main._utcnow_naive()+timedelta(days=1)))
        s.add(main.ConsultationCase(id=1,requester_user_id=1,expert_user_id=2,specialty="Endodonti",
            clinical_summary="Synthetic",question="Synthetic",status="ACTIVE",
            expert_response_deadline=main._utcnow_naive()+timedelta(hours=1)))
        s.add(main.ConsultationCase(id=2,requester_user_id=2,expert_user_id=3,specialty="Ortodonti",
            clinical_summary="Synthetic",question="Synthetic",status="ACTIVE",
            expert_response_deadline=main._utcnow_naive()+timedelta(hours=1)))
        s.commit()
    c=TestClient(main.app);c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[1]
    return c,engine


def _png(color="white",size=(8,8)):
    raw=io.BytesIO();Image.new("RGB",size,color).save(raw,format="PNG");return raw.getvalue()


# ---------------------------------------------------------------------------
# Route 1: POST /api/mobile/v1/consultations/{case_id}/attachments
# ---------------------------------------------------------------------------

def test_attachment_upload_requires_session_and_participant_ownership(parity):
    c,engine=parity
    png=_png()
    # (b) yetki: the web handler answers anonymous browsers with /login; the
    # native contract is 401 so revalidateSession can run. Detail is the
    # shared mobile unauthorized copy.
    saved=c.headers.pop("Authorization")
    denied=c.post("/api/mobile/v1/consultations/1/attachments",files={"file":("photo.png",png,"image/png")})
    assert denied.status_code==401,denied.text
    assert denied.json()["detail"]=="Oturum geçersiz veya süresi dolmuş."
    c.headers["Authorization"]=saved
    # (a) vaka sahipliği: an outsider's upload is indistinguishable from a
    # missing case, exactly like the web "Bu vakaya dosya gönderilemez." gate.
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[4]
    outsider=c.post("/api/mobile/v1/consultations/1/attachments",files={"file":("photo.png",png,"image/png")})
    assert outsider.status_code==404
    assert outsider.json()["detail"]=="Görüşme bulunamadı."
    assert c.post("/api/mobile/v1/consultations/999/attachments",files={"file":("photo.png",png,"image/png")}).status_code==404
    # (e) yanlış hesap: no message row was created by any denied attempt.
    with Session(engine) as session:
        assert session.exec(select(main.ConsultationMessage)).all()==[]


def test_attachment_idempotency_key_replays_same_image_without_second_row(parity):
    c,engine=parity
    key="parity-media-key-000001"
    first=c.post("/api/mobile/v1/consultations/1/attachments",
        files={"file":("photo.png",_png(),"image/png")},data={"client_message_id":key})
    assert first.status_code==200,first.text
    body=first.json()
    assert body["ok"] is True and body["message"]["has_media"] is True
    assert "replayed" not in body or body["replayed"] is not True
    # Same key and bytes, different display name: the receipt binds the media
    # digest, not the filename, so the retry must replay the original message.
    second=c.post("/api/mobile/v1/consultations/1/attachments",
        files={"file":("photo-renamed.png",_png(),"image/png")},data={"client_message_id":key})
    assert second.status_code==200,second.text
    assert second.json()["replayed"] is True
    assert second.json()["message"]["id"]==body["message"]["id"]
    assert second.json()["message"]["client_message_id"]==key
    # Changed bytes under the same key stay a hard 409 (web payload-hash rule).
    conflict=c.post("/api/mobile/v1/consultations/1/attachments",
        files={"file":("photo.png",_png("black"),"image/png")},data={"client_message_id":key})
    assert conflict.status_code==409
    with Session(engine) as session:
        rows=session.exec(select(main.ConsultationMessage).where(
            main.ConsultationMessage.case_id==1)).all()
        assert len(rows)==1
        receipts=session.exec(select(main.ConsultationMessageReceipt)).all()
        assert len(receipts)==1 and receipts[0].sender_user_id==1


def test_attachment_same_key_recovering_after_lost_response(parity):
    """Crash recovery: receipt exists, client response was lost before render."""
    c,engine=parity
    key="parity-crash-recover-0001"
    png=_png()
    first=c.post("/api/mobile/v1/consultations/1/attachments",
        files={"file":("photo.png",png,"image/png")},data={"client_message_id":key})
    assert first.status_code==200,first.text
    original=first.json()["message"]
    # The response never reached the client: the native composer first asks the
    # receipt endpoint whether the upload committed (mobile_api message-receipt).
    probe=c.get(f"/api/mobile/v1/consultations/1/message-receipt?client_message_id={key}")
    assert probe.status_code==200,probe.text
    assert probe.json()["deleted"] is False
    recovered=probe.json()["message"]
    assert recovered["id"]==original["id"] and recovered["has_media"] is True
    # A full retry with the same key must replay, never duplicate the media.
    retry=c.post("/api/mobile/v1/consultations/1/attachments",
        files={"file":("photo.png",png,"image/png")},data={"client_message_id":key})
    assert retry.status_code==200,retry.text
    assert retry.json()["replayed"] is True and retry.json()["message"]["id"]==original["id"]
    with Session(engine) as session:
        media_rows=[row for row in session.exec(select(main.ConsultationMessage).where(
            main.ConsultationMessage.case_id==1)).all() if row.media_path]
        assert len(media_rows)==1


def test_attachment_key_is_sender_scoped_against_wrong_account(parity):
    c,engine=parity
    key="parity-wrong-owner-0001"
    png=_png()
    first=c.post("/api/mobile/v1/consultations/1/attachments",
        files={"file":("photo.png",png,"image/png")},data={"client_message_id":key})
    assert first.status_code==200,first.text
    owner_message_id=first.json()["message"]["id"]
    # (e) yanlış hesap: the peer participant reusing user1's key must never
    # receive user1's receipt; the web receipt lookup is (case, sender, key).
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[2]
    peer_lookup=c.get(f"/api/mobile/v1/consultations/1/message-receipt?client_message_id={key}")
    assert peer_lookup.status_code==200
    assert peer_lookup.json()=={"message":None,"deleted":False}
    peer_retry=c.post("/api/mobile/v1/consultations/1/attachments",
        files={"file":("photo.png",png,"image/png")},data={"client_message_id":key})
    assert peer_retry.status_code==200,peer_retry.text
    assert peer_retry.json().get("replayed") is not True
    assert peer_retry.json()["message"]["id"]!=owner_message_id
    assert peer_retry.json()["message"]["sender_user_id"]==2
    with Session(engine) as session:
        rows=session.exec(select(main.ConsultationMessage).where(
            main.ConsultationMessage.case_id==1)).all()
        assert {row.sender_user_id for row in rows}=={1,2}


# ---------------------------------------------------------------------------
# Route 2: GET /api/mobile/v1/consultations/{case_id}/attachments/{message_id}
# ---------------------------------------------------------------------------

def test_attachment_download_is_case_and_message_bound(parity):
    from pypdf import PdfWriter
    c,engine=parity
    pdf=io.BytesIO();writer=PdfWriter()
    writer.add_blank_page(width=72,height=72);writer.write(pdf);pdf_bytes=pdf.getvalue()
    sent=c.post("/api/mobile/v1/consultations/1/attachments",files={"file":("case.pdf",pdf_bytes,"application/pdf")})
    assert sent.status_code==200,sent.text
    message_id=sent.json()["message"]["id"]
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[2]
    other=c.post("/api/mobile/v1/consultations/2/attachments",files={"file":("case2.png",_png(),"image/png")})
    assert other.status_code==200,other.text
    other_message_id=other.json()["message"]["id"]
    # (a) ownership: a real message id from another case is not servable under
    # this case path; the web handler binds msg.case_id == case.id.
    assert c.get(f"/api/mobile/v1/consultations/1/attachments/{other_message_id}").status_code==404
    assert c.get("/api/mobile/v1/consultations/1/attachments/999999").status_code==404
    # (e) wrong pairing: user2 owns case2 but has no case1 access, and an
    # uninvolved account never learns the attachment exists.
    assert c.get(f"/api/mobile/v1/consultations/2/attachments/{other_message_id}").status_code==200
    assert c.get(f"/api/mobile/v1/consultations/2/attachments/{message_id}").status_code==404
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[4]
    assert c.get(f"/api/mobile/v1/consultations/2/attachments/{other_message_id}").status_code==404
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[1]
    # (d) reads are side-effect free: repeated GETs replay the exact bytes and
    # never create receipt or message rows.
    for _ in range(2):
        again=c.get(f"/api/mobile/v1/consultations/1/attachments/{message_id}")
        assert again.status_code==200 and again.content==pdf_bytes
        assert again.headers["cache-control"]=="private, no-store"
    with Session(engine) as session:
        assert len(session.exec(select(main.ConsultationMessage)).all())==2
        assert session.exec(select(main.ConsultationMessageReceipt)).all()==[]


def test_attachment_download_requires_session(parity):
    c,engine=parity
    sent=c.post("/api/mobile/v1/consultations/1/attachments",files={"file":("photo.png",_png(),"image/png")})
    assert sent.status_code==200,sent.text
    message_id=sent.json()["message"]["id"]
    saved=c.headers.pop("Authorization")
    assert c.get(f"/api/mobile/v1/consultations/1/attachments/{message_id}").status_code==401
    c.headers["Authorization"]=saved


# ---------------------------------------------------------------------------
# Route 3: GET /api/mobile/v1/messages/unread-count
# ---------------------------------------------------------------------------

def test_messages_unread_count_is_self_scoped_with_web_count_semantics(parity):
    c,engine=parity
    # (b) yetki: the web badge answers anonymous browsers with {"count": 0};
    # native must instead force revalidateSession, so the mobile contract is 401.
    saved=c.headers.pop("Authorization")
    assert c.get("/api/mobile/v1/messages/unread-count").status_code==401
    c.headers["Authorization"]=saved
    sent_ids=[]
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[2]
    for index in range(3):
        sent=c.post("/api/mobile/v1/consultations/1/messages",
            json={"content":"Synthetic "+str(index),"client_message_id":"parity-unread-"+str(index).zfill(4)})
        assert sent.status_code==200,sent.text
        sent_ids.append(sent.json()["message"]["id"])
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[1]
    # (a) kendi sayacı: only the listening side counts incoming messages; the
    # expert never counts their own outgoing traffic.
    assert c.get("/api/mobile/v1/messages/unread-count").json()=={"count":3}
    assert c.get("/api/mobile/v1/messages/unread-count").json()=={"count":3}
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[2]
    assert c.get("/api/mobile/v1/messages/unread-count").json()=={"count":0}
    # (e) yanlış hesap: an account without cases never borrows another user's
    # badge, and repeated reads stay stable without writing rows.
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[4]
    assert c.get("/api/mobile/v1/messages/unread-count").json()=={"count":0}
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[1]
    # count semantics: a fresh REQUESTED case counts at least one for the
    # assigned expert before any message exists (web _consultation_unread_total).
    with Session(engine) as session:
        session.add(main.ConsultationCase(id=3,requester_user_id=1,expert_user_id=3,specialty="Endodonti",
            clinical_summary="Synthetic",question="Synthetic",status="REQUESTED",
            expert_response_deadline=main._utcnow_naive()+timedelta(hours=1)))
        session.commit()
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[3]
    fresh=c.get("/api/mobile/v1/messages/unread-count").json()
    assert fresh=={"count":1}
    # The shared web read cursor clears the badge (mobile /consultations/{id}/read).
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[1]
    read=c.post("/api/mobile/v1/consultations/1/read",json={"through_id":sent_ids[-1]})
    assert read.status_code==200,read.text
    assert c.get("/api/mobile/v1/messages/unread-count").json()=={"count":0}
    # A conversation the user hid themselves stops counting until restored.
    assert c.post("/api/mobile/v1/consultations/1/actions",json={"action":"delete"}).status_code==200
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[2]
    reply=c.post("/api/mobile/v1/consultations/1/messages",
        json={"content":"Cevap silindi sonra","client_message_id":"parity-unread-after-delete1"})
    assert reply.status_code==200,reply.text
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[1]
    assert c.get("/api/mobile/v1/messages/unread-count").json()=={"count":0}
    assert c.post("/api/mobile/v1/consultations/1/actions",json={"action":"restore"}).status_code==200
    assert c.get("/api/mobile/v1/messages/unread-count").json()=={"count":1}


# ---------------------------------------------------------------------------
# Route 4: GET /api/mobile/v1/notifications/unread-count
# ---------------------------------------------------------------------------

def test_notification_unread_count_is_self_scoped_active_only(parity):
    c,engine=parity
    saved=c.headers.pop("Authorization")
    assert c.get("/api/mobile/v1/notifications/unread-count").status_code==401
    c.headers["Authorization"]=saved
    with Session(engine) as session:
        session.add_all([
            main.AdminNotice(user_id=1,title="Aktif",message="Synthetic",notice_type="TEST",status="ACTIVE",is_read=False),
            main.AdminNotice(user_id=1,title="Okundu",message="Synthetic",notice_type="TEST",status="ACTIVE",is_read=True),
            main.AdminNotice(user_id=1,title="Arşiv",message="Synthetic",notice_type="TEST",status="RESOLVED",is_read=False),
            main.AdminNotice(user_id=2,title="Diğer hesap",message="Synthetic",notice_type="TEST",status="ACTIVE",is_read=False),
        ])
        session.commit()
        other_notice_id=session.exec(select(main.AdminNotice).where(
            main.AdminNotice.user_id==2)).one().id
    badge=c.get("/api/mobile/v1/notifications/unread-count")
    assert badge.status_code==200
    # only the signed-in user's ACTIVE unread notices are counted; the endpoint
    # must not leak notice bodies.
    assert set(badge.json())=={"unread_count"} and badge.json()["unread_count"]==1
    listing=c.get("/api/mobile/v1/notifications").json()
    own_id=next(item["id"] for item in listing["items"] if item["title"]=="Aktif")
    assert c.post(f"/api/mobile/v1/notifications/{own_id}/read").json()["ok"] is True
    assert c.get("/api/mobile/v1/notifications/unread-count").json()=={"unread_count":0}
    # (e) yanlış hesap: user2's badge is untouched and user1 cannot mark or even
    # resolve user2's notice (mobile_notification_read ownership rule).
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[2]
    assert c.get("/api/mobile/v1/notifications/unread-count").json()=={"unread_count":1}
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[1]
    wrong=c.post(f"/api/mobile/v1/notifications/{other_notice_id}/read")
    assert wrong.status_code==404 and wrong.json()["detail"]=="Bildirim bulunamadı."
    assert c.get("/api/mobile/v1/notifications/unread-count").json()=={"unread_count":0}


# ---------------------------------------------------------------------------
# Route 5: GET /api/mobile/v1/experts/performance-info
# ---------------------------------------------------------------------------

_SECTION_HEADINGS=("Kullanıcıların gördüğü bilgiler","Kaydedilen performans olayları",
    "Neler performansınızı düşürmez?","10 dakikalık talep kuralı")


def test_performance_info_requires_session_but_mirrors_web_login_only_role(parity):
    c,engine=parity
    # (b) yetki: web redirects anonymous visitors to /login; the native contract
    # is 401 for revalidateSession.
    saved=c.headers.pop("Authorization")
    assert c.get("/api/mobile/v1/experts/performance-info").status_code==401
    c.headers["Authorization"]=saved
    # Role parity: the web page has no expert gate — any signed-in account may
    # read it, so a plain USER account without an ExpertProfile also gets 200.
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[4]
    response=c.get("/api/mobile/v1/experts/performance-info")
    assert response.status_code==200,response.text


def test_performance_info_returns_the_canonical_web_copy_without_user_data(parity):
    c,engine=parity
    # (a) kendi sayacı / (e) yanlış hesap: the payload is the shared web text,
    # never any account-specific field (no ids, no owner scoping to leak).
    first=c.get("/api/mobile/v1/experts/performance-info").json()
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[4]
    second=c.get("/api/mobile/v1/experts/performance-info").json()
    c.headers["Authorization"]="Bearer "+_SESSION_TOKEN[1]
    assert first==second
    assert first["ok"] is True
    for key in ("title","body","content"):
        assert isinstance(first[key],str) and first[key]
    assert first["title"]=="Performansınız nasıl değerlendirilir?"
    # The sections are the same expert-rule cards the web template renders.
    sections=first["sections"]
    assert [section["title"] for section in sections]==list(_SECTION_HEADINGS)
    assert all(section["body"] for section in sections)
    for sentence in ("Mesaj sayısı veya mesaj uzunluğu kalite ölçütü değildir.",
                     "yeni vaka kabulünüz 24 saat durdurulur"):
        assert sentence in first["body"]
    assert "user_id" not in first and "owner_id" not in first
    for section in sections:
        assert set(section)=={"title","body"}
