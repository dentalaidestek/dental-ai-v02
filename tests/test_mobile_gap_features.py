"""Mobil parite boşluk özelliklerinin regresyon testleri.

Kapsam: uzman müsaitlik aboneliği (web /expert-support/availability-watch birebir mantık),
profesyonel belge görüntüleme (web profile_document_page kaynak alanları) ve
danışmanlık görüntü anotasyonu (web expert_support_annotate_message delege).
"""
import base64

import pytest
from sqlmodel import Session, SQLModel, create_engine

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main

BASE = "/api/mobile/v1"


def _build(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "gap-features.db"),
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr("app.mobile_api.engine", engine)
    return TestClient(main.app), engine


def _user_and_token(session, username):
    user = main.User(
        username=username, role="DOCTOR", display_name=username,
        email_verified_at=main._utcnow_naive(),
    )
    session.add(user)
    session.commit()
    token = "gap-" + username + "-" + "t" * 24
    session.add(main.SessionToken(
        token_hash=main.hash_session_token(token),
        user_id=user.id,
        expires_at=main._utcnow_naive() + main.timedelta(days=1),
    ))
    session.commit()
    # Session açıkken kimliği yakala; kapalı session üzerinde detached erişim yok.
    return int(user.id), token


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_availability_watch_is_idempotent_and_validates_specialty(monkeypatch, tmp_path):
    client, engine = _build(monkeypatch, tmp_path)
    with Session(engine) as session:
        _, token = _user_and_token(session, "watch-owner")
    headers = {"Authorization": "Bearer " + token}

    response = client.post(
        BASE + "/expert-support/availability-watch",
        json={"specialty": "Endodonti"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["specialty"] == "Endodonti"
    assert [w["specialty"] for w in body["watches"]] == ["Endodonti"]

    # Web mantığıyla aynı idempotent davranış: aktif kayıt varsa yenisi eklenmez.
    second = client.post(
        BASE + "/expert-support/availability-watch",
        json={"specialty": "Endodonti"}, headers=headers,
    )
    assert second.status_code == 200
    assert len(second.json()["watches"]) == 1

    listed = client.get(BASE + "/expert-support/availability-watch", headers=headers)
    assert listed.status_code == 200
    assert [w["specialty"] for w in listed.json()["watches"]] == ["Endodonti"]

    invalid = client.post(
        BASE + "/expert-support/availability-watch",
        json={"specialty": "Bilinmeyen Branş"}, headers=headers,
    )
    assert invalid.status_code == 400
    assert "Geçersiz branş" in invalid.json()["detail"]

    unauthenticated = client.post(
        BASE + "/expert-support/availability-watch",
        json={"specialty": "Endodonti"},
    )
    assert unauthenticated.status_code == 401


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_professional_document_content_is_owner_scoped_and_encoded(monkeypatch, tmp_path):
    client, engine = _build(monkeypatch, tmp_path)
    with Session(engine) as session:
        owner_id, owner_token = _user_and_token(session, "doc-owner")
        _other_id, other_token = _user_and_token(session, "doc-other")
    owner_headers = {"Authorization": "Bearer " + owner_token}

    missing = client.get(
        BASE + "/account/documents/title/content", headers=owner_headers,
    )
    assert missing.status_code == 404

    document = tmp_path / "title-credential.jpg"
    document.write_bytes(b"fake-jpeg-bytes")
    with Session(engine, expire_on_commit=False) as session:
        session.add(main.ExpertTitleChange(
            user_id=owner_id,
            requested_title="Doç. Dr.",
            previous_title="Dr. Öğr. Üyesi",
            status="PENDING_REVIEW",
            credential_document_name="diploma.jpg",
            credential_document_path=str(document),
        ))
        session.commit()

    response = client.get(
        BASE + "/account/documents/title/content", headers=owner_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["media_type"] == "image/jpeg"
    assert body["filename"].endswith("title-credential.jpg")
    assert base64.b64decode(body["data_base64"]) == b"fake-jpeg-bytes"

    unsupported = client.get(
        BASE + "/account/documents/expert/content", headers=owner_headers,
    )
    assert unsupported.status_code == 404


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_chat_annotate_action_reuses_the_web_annotation_message(monkeypatch, tmp_path):
    client, engine = _build(monkeypatch, tmp_path)
    with Session(engine) as session:
        requester_id, requester_token = _user_and_token(session, "annotate-requester")
        expert_id, expert_token = _user_and_token(session, "annotate-expert")
        now = main._utcnow_naive()
        case = main.ConsultationCase(
            requester_user_id=requester_id,
            expert_user_id=expert_id,
            specialty="Endodonti",
            clinical_summary="Synthetic clinical summary",
            question="Synthetic question",
            status="ACTIVE",
            expert_response_deadline=now + main.timedelta(days=1),
        )
        session.add(case)
        session.flush()
        image_message = main.ConsultationMessage(
            case_id=case.id,
            sender_user_id=requester_id,
            message_type="IMAGE",
            content="Görüntü",
            media_path="/uploads/synthetic/radyografi.jpg",
        )
        text_message = main.ConsultationMessage(
            case_id=case.id,
            sender_user_id=expert_id,
            message_type="TEXT",
            content="Bulguları paylaşın.",
        )
        session.add_all([image_message, text_message])
        session.commit()
        case_id = case.id
        image_id = image_message.id
        text_id = text_message.id
    headers = {"Authorization": "Bearer " + requester_token}

    payload = {"v": 1, "kind": "note", "text": "Sağ alt bölgede lezyon"}
    response = client.post(
        BASE + f"/consultations/{case_id}/actions",
        json={
            "action": "annotate",
            "message_id": image_id,
            "annotation_json": __import__("json").dumps(payload, ensure_ascii=False),
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True

    with Session(engine) as session:
        annotations = session.exec(
            main.select(main.ConsultationMessage).where(
                main.ConsultationMessage.case_id == case_id,
                main.ConsultationMessage.message_type == "ANNOTATION",
            )
        ).all()
        assert len(annotations) == 1
        annotation = annotations[0]
        assert annotation.reply_to_message_id == image_id
        assert annotation.original_media_path == "/uploads/synthetic/radyografi.jpg"
        assert "Sağ alt bölgede lezyon" in annotation.annotation_json

    rejected = client.post(
        BASE + f"/consultations/{case_id}/actions",
        json={
            "action": "annotate",
            "message_id": text_id,
            "annotation_json": "{\"v\":1}",
        },
        headers=headers,
    )
    assert rejected.status_code == 403

    outsider_ok = client.post(
        BASE + f"/consultations/{case_id}/actions",
        json={
            "action": "annotate",
            "message_id": image_id,
            "annotation_json": "{}",
        },
        headers={"Authorization": "Bearer " + expert_token},
    )
    assert outsider_ok.status_code == 200
