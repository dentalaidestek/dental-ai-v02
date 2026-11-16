import pytest
from sqlmodel import Session, SQLModel, create_engine, select

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main
from app.mobile_api import MobileSupportMutationReceipt


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_mobile_support_requests_are_private_and_idempotent(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "mobile-support.db"), connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr("app.mobile_api.engine", engine)
    now = main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as session:
        users = [
            main.User(username=f"support-{n}", role="DOCTOR", display_name=f"Doctor {n}", email_verified_at=now)
            for n in (1, 2)
        ]
        admin = main.User(username="support-admin-mobile", role="ADMIN", display_name="Admin", email_verified_at=now)
        session.add_all(users + [admin])
        session.commit()
        tokens = ["mobile-support-user-one", "mobile-support-user-two", "mobile-support-admin"]
        for user, token in zip(users + [admin], tokens):
            session.add(main.SessionToken(token_hash=main.hash_session_token(token), user_id=user.id, expires_at=now + main.timedelta(days=1)))
        session.commit()
        first_id, second_id, admin_id = users[0].id, users[1].id, admin.id

    with TestClient(main.app) as client:
        assert client.get("/api/mobile/v1/support/tickets").status_code == 401
        h1 = {"Authorization": "Bearer " + tokens[0]}
        h2 = {"Authorization": "Bearer " + tokens[1]}
        ha = {"Authorization": "Bearer " + tokens[2]}

        created = client.post("/api/mobile/v1/support/tickets", headers=h1, json={
            "subject": "Mobil giriş sorunu", "message": "İlk açıklama", "request_key": "support_create_key_0001"
        })
        assert created.status_code == 200, created.text
        ticket_id = created.json()["ticket_id"]

        replay = client.post("/api/mobile/v1/support/tickets", headers=h1, json={
            "subject": "Mobil giriş sorunu", "message": "İlk açıklama", "request_key": "support_create_key_0001"
        })
        assert replay.status_code == 200
        assert replay.json()["ticket_id"] == ticket_id
        assert replay.json()["replayed"] is True

        collision = client.post("/api/mobile/v1/support/tickets", headers=h1, json={
            "subject": "Farklı içerik", "message": "İlk açıklama", "request_key": "support_create_key_0001"
        })
        assert collision.status_code == 409

        assert client.get(f"/api/mobile/v1/support/tickets/{ticket_id}", headers=h2).status_code == 404
        assert client.post(f"/api/mobile/v1/support/tickets/{ticket_id}/reply", headers=h2, json={
            "message": "Yetkisiz yanıt", "request_key": "support_reply_key_0001"
        }).status_code == 404

        admin_reply = client.post(
            f"{main.ADMIN_CENTER_PATH}/support/{ticket_id}/message",
            data={"message": "Destek ekibi yanıtı"},
            cookies={main.SESSION_COOKIE: tokens[2]},
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert admin_reply.status_code == 200, admin_reply.text

        detail = client.get(f"/api/mobile/v1/support/tickets/{ticket_id}", headers=h1)
        assert detail.status_code == 200
        assert detail.json()["ticket"]["can_reply"] is True

        reply_body = {"message": "Teşekkürler", "request_key": "support_reply_key_0001"}
        replied = client.post(f"/api/mobile/v1/support/tickets/{ticket_id}/reply", headers=h1, json=reply_body)
        assert replied.status_code == 200, replied.text
        duplicate = client.post(f"/api/mobile/v1/support/tickets/{ticket_id}/reply", headers=h1, json=reply_body)
        assert duplicate.status_code == 200
        assert duplicate.json()["message_id"] == replied.json()["message_id"]
        assert duplicate.json()["replayed"] is True

        blocked_turn = client.post(f"/api/mobile/v1/support/tickets/{ticket_id}/reply", headers=h1, json={
            "message": "Aynı turda ikinci mesaj", "request_key": "support_reply_key_0002"
        })
        assert blocked_turn.status_code == 409

        assert client.post(f"/api/mobile/v1/support/tickets/{ticket_id}/read?through_message_id={replied.json()['message_id']}", headers=h1).status_code == 200

    with Session(engine) as session:
        ticket = session.get(main.SupportTicket, ticket_id)
        messages = session.exec(select(main.SupportTicketMessage).where(
            main.SupportTicketMessage.ticket_id == ticket_id
        ).order_by(main.SupportTicketMessage.id)).all()
        receipts = session.exec(select(MobileSupportMutationReceipt).where(
            MobileSupportMutationReceipt.ticket_id == ticket_id
        )).all()
    assert ticket.user_id == first_id
    assert [(m.sender_role, m.message) for m in messages] == [
        ("ADMIN", "Destek ekibi yanıtı"), ("USER", "Teşekkürler")
    ]
    assert len(receipts) == 2
