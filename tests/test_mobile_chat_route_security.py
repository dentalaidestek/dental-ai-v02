"""Route-level regressions for mobile consultation attachment and receipt isolation."""
import io
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import main
from test_mobile_chat_actions import chat, _SESSION_TOKEN


def _png():
    from PIL import Image
    raw = io.BytesIO()
    Image.new("RGB", (12, 10), "white").save(raw, format="PNG")
    return raw.getvalue()


def test_message_receipt_obeys_latest_participant_inbox_state(chat):
    client, engine = chat
    key = "native-inbox-receipt-0001"
    uploaded = client.post(
        "/api/mobile/v1/consultations/1/attachments",
        data={"client_message_id": key},
        files={"file": ("receipt.png", _png(), "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    message_id = uploaded.json()["message"]["id"]

    with Session(engine) as session:
        session.add(main.ConsultationInboxState(case_id=1, user_id=1, deleted_at=None))
        session.add(main.ConsultationInboxState(
            case_id=1,
            user_id=1,
            deleted_at=main._utcnow_naive(),
            recover_until=main._utcnow_naive() + timedelta(days=7),
        ))
        session.commit()

    hidden_receipt = client.get(
        f"/api/mobile/v1/consultations/1/message-receipt?client_message_id={key}"
    )
    assert hidden_receipt.status_code == 404
    assert client.get(
        f"/api/mobile/v1/consultations/1/attachments/{message_id}"
    ).status_code == 404

    with Session(engine) as session:
        session.add(main.ConsultationInboxState(case_id=1, user_id=1, deleted_at=None))
        session.commit()

    restored = client.get(
        f"/api/mobile/v1/consultations/1/message-receipt?client_message_id={key}"
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["message"]["id"] == message_id
    assert restored.headers["cache-control"] == "private, no-store"
    assert "authorization" in restored.headers.get("vary", "").lower()


def test_mobile_attachment_upload_rejects_outsider_and_blocked_participant(chat):
    client, engine = chat
    payload = _png()

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[3]
    outsider = client.post(
        "/api/mobile/v1/consultations/1/attachments",
        data={"client_message_id": "native-outsider-upload-0001"},
        files={"file": ("outsider.png", payload, "image/png")},
    )
    assert outsider.status_code == 404

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[1]
    with Session(engine) as session:
        session.add(main.UserBlock(blocker_user_id=1, blocked_user_id=2))
        session.commit()
    blocked = client.post(
        "/api/mobile/v1/consultations/1/attachments",
        data={"client_message_id": "native-blocked-upload-0001"},
        files={"file": ("blocked.png", payload, "image/png")},
    )
    assert blocked.status_code == 403

    with Session(engine) as session:
        assert session.exec(select(main.ConsultationMessage)).all() == []


def test_attachment_intent_key_is_scoped_to_each_case_participant(chat):
    client, engine = chat
    key = "native-shared-key-per-sender-01"
    payload = _png()
    first = client.post(
        "/api/mobile/v1/consultations/1/attachments",
        data={"client_message_id": key},
        files={"file": ("same.png", payload, "image/png")},
    )
    assert first.status_code == 200, first.text

    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[2]
    second = client.post(
        "/api/mobile/v1/consultations/1/attachments",
        data={"client_message_id": key},
        files={"file": ("same.png", payload, "image/png")},
    )
    assert second.status_code == 200, second.text
    assert second.json()["message"]["id"] != first.json()["message"]["id"]

    with Session(engine) as session:
        rows = session.exec(select(main.ConsultationMessage).where(
            main.ConsultationMessage.case_id == 1
        )).all()
        assert len(rows) == 2


def test_lost_attachment_response_recovers_committed_message_without_duplicate(chat, monkeypatch):
    _, engine = chat
    client = TestClient(main.app, raise_server_exceptions=False)
    client.headers["Authorization"] = "Bearer " + _SESSION_TOKEN[1]
    key = "native-postcommit-recovery-0001"
    payload = _png()

    def fail_after_commit(*_args, **_kwargs):
        raise RuntimeError("synthetic response publication failure")

    monkeypatch.setattr(main, "on_loop", fail_after_commit)
    failed_response = client.post(
        "/api/mobile/v1/consultations/1/attachments",
        data={"client_message_id": key},
        files={"file": ("recovery.png", payload, "image/png")},
    )
    assert failed_response.status_code == 500

    monkeypatch.setattr(main, "on_loop", lambda *_args, **_kwargs: None)
    receipt = client.get(
        f"/api/mobile/v1/consultations/1/message-receipt?client_message_id={key}"
    )
    assert receipt.status_code == 200, receipt.text
    message_id = receipt.json()["message"]["id"]

    retry = client.post(
        "/api/mobile/v1/consultations/1/attachments",
        data={"client_message_id": key},
        files={"file": ("recovery.png", payload, "image/png")},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["replayed"] is True
    assert retry.json()["message"]["id"] == message_id
    with Session(engine) as session:
        rows = session.exec(select(main.ConsultationMessage).where(
            main.ConsultationMessage.case_id == 1,
            main.ConsultationMessage.sender_user_id == 1,
        )).all()
        assert len(rows) == 1
