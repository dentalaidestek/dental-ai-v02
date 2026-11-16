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

        closed = client.post(
            f"{main.ADMIN_CENTER_PATH}/support/{ticket_id}",
            data={"status": "CLOSED"},
            cookies={main.SESSION_COOKIE: tokens[2]},
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert closed.status_code == 200
        closed_reply = client.post(f"/api/mobile/v1/support/tickets/{ticket_id}/reply", headers=h1, json={
            "message": "Kapalı talebe yanıt", "request_key": "support_reply_key_0003"
        })
        assert closed_reply.status_code == 409

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



def test_support_receipt_schema_has_serialized_production_upgrade():
    from pathlib import Path
    migration = (Path(__file__).resolve().parents[1] / "app" / "migrate.py").read_text(encoding="utf-8")
    assert "REVISION = 13" in migration
    assert "def _upgrade_support_receipts_schema(main):" in migration
    assert migration.count("MobileSupportMutationReceipt.__table__.create(connection, checkfirst=True)") >= 2
    assert "if _upgrade_support_receipts_schema(main):" in migration


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_mobile_support_case_link_reports_and_ticket_cursor_paging(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "mobile-support-parity.db"), connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr("app.mobile_api.engine", engine)
    now = main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as session:
        owner = main.User(username="support-parity-owner", role="DOCTOR", display_name="Owner", email_verified_at=now)
        other = main.User(username="support-parity-other", role="DOCTOR", display_name="Other", email_verified_at=now)
        session.add_all([owner, other]); session.commit()
        token = "mobile-support-parity-owner"
        other_token = "mobile-support-parity-other"
        session.add_all([
            main.SessionToken(token_hash=main.hash_session_token(token), user_id=owner.id, expires_at=now + main.timedelta(days=1)),
            main.SessionToken(token_hash=main.hash_session_token(other_token), user_id=other.id, expires_at=now + main.timedelta(days=1)),
        ])
        case = main.ConsultationCase(
            requester_user_id=owner.id, expert_user_id=other.id, specialty="Endodonti",
            clinical_summary="Özet", question="Soru", expert_response_deadline=now + main.timedelta(days=1),
        )
        session.add(case); session.flush()
        session.add(main.ConsultationMessage(case_id=case.id, sender_user_id=owner.id, message_type="TEXT", content="Merhaba"))
        report = main.UserReport(reporter_user_id=owner.id, reported_user_id=other.id, case_id=case.id, reason="OTHER", detail="İnceleme")
        session.add(report); session.commit()
        case_id, report_id = case.id, report.id

    with TestClient(main.app) as client:
        headers = {"Authorization": "Bearer " + token}
        options = client.get("/api/mobile/v1/support/conversation-options", headers=headers)
        assert options.status_code == 200
        assert [x["id"] for x in options.json()["items"]] == [case_id]
        reports = client.get("/api/mobile/v1/support/reports", headers=headers)
        assert reports.status_code == 200
        assert [x["id"] for x in reports.json()["items"]] == [report_id]
        report_ticket_id = reports.json()["items"][0]["ticket_id"]
        assert isinstance(report_ticket_id, int)
        report_detail = client.get(f"/api/mobile/v1/support/tickets/{report_ticket_id}", headers=headers)
        assert report_detail.status_code == 200
        assert client.get(f"/api/mobile/v1/support/tickets/{report_ticket_id}", headers={"Authorization": "Bearer " + other_token}).status_code == 404
        created = client.post("/api/mobile/v1/support/tickets", headers=headers, json={
            "subject": "Vaka ile ilgili", "message": "Destek açıklaması",
            "request_key": "support_case_link_key_01", "case_id": case_id,
        })
        assert created.status_code == 200, created.text
        with Session(engine) as session:
            ticket = session.get(main.SupportTicket, created.json()["ticket_id"])
            assert ticket.case_id == case_id
        for n in range(3):
            with Session(engine) as session:
                ticket = main.SupportTicket(user_id=owner.id, subject=f"Eski {n}", message="Mesaj", source_type="SUPPORT")
                session.add(ticket); session.commit()
        first = client.get("/api/mobile/v1/support/tickets?limit=2", headers=headers)
        assert first.status_code == 200
        assert len(first.json()["items"]) == 2
        assert first.json()["has_more"] is True
        second = client.get("/api/mobile/v1/support/tickets?limit=2&before_id=" + str(first.json()["next_before_id"]), headers=headers)
        assert second.status_code == 200
        assert not ({x["id"] for x in first.json()["items"]} & {x["id"] for x in second.json()["items"]})
