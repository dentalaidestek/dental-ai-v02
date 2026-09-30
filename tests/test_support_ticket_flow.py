import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_support_ticket_full_user_admin_turn_lifecycle(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    now = main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username="support-user", role="DOCTOR", display_name="Kullanıcı")
        admin = main.User(username="support-admin", role="ADMIN", display_name="Yönetici")
        session.add(user)
        session.add(admin)
        session.commit()
        user_token, admin_token = "support-user-token", "support-admin-token"
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(user_token), user_id=user.id,
            expires_at=now + main.timedelta(days=1),
        ))
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(admin_token), user_id=admin.id,
            expires_at=now + main.timedelta(days=1),
        ))
        session.commit()
        user_id, admin_id = user.id, admin.id

    published = []

    async def capture_publish(event):
        published.append((event.user_id, event.event_type))

    monkeypatch.setattr(main, "_publish_realtime_event", capture_publish)
    ajax = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
    user_cookie = {main.SESSION_COOKIE: user_token}
    admin_cookie = {main.SESSION_COOKIE: admin_token}

    with TestClient(main.app) as client:
        created = client.post(
            "/support-request",
            data={"subject": "Bildirim sorunu", "message": "İlk talep metni"},
            cookies=user_cookie,
            headers=ajax,
        )
        assert created.status_code == 200
        ticket_id = created.json()["ticket_id"]

        admin_view = client.get(
            f"{main.ADMIN_CENTER_PATH}/support/{ticket_id}/conversation",
            cookies=admin_cookie,
        )
        assert admin_view.status_code == 200
        assert admin_view.json()["ticket"]["initial_message"] == "İlk talep metni"
        assert admin_view.json()["unread_count"] == 1

        admin_read = client.post(
            f"{main.ADMIN_CENTER_PATH}/support/{ticket_id}/read",
            data={"through_message_id": "0"}, cookies=admin_cookie, headers=ajax,
        )
        assert admin_read.status_code == 200
        assert admin_read.json()["unread_count"] == 0

        answered = client.post(
            f"{main.ADMIN_CENTER_PATH}/support/{ticket_id}/message",
            data={"message": "Destek yanıtı"}, cookies=admin_cookie, headers=ajax,
        )
        assert answered.status_code == 200
        assert answered.json()["status"] == "ANSWERED"

        user_view = client.get(
            f"/support-request/{ticket_id}/conversation", cookies=user_cookie
        )
        assert user_view.status_code == 200
        assert [row["message"] for row in user_view.json()["messages"]] == ["Destek yanıtı"]
        assert user_view.json()["can_reply"] is True
        assert user_view.json()["unread_count"] == 1

        replied = client.post(
            f"/support-request/{ticket_id}/reply",
            data={"message": "Kullanıcı yanıtı"}, cookies=user_cookie, headers=ajax,
        )
        assert replied.status_code == 200
        assert replied.json()["status"] == "USER_REPLIED"

        duplicate = client.post(
            f"/support-request/{ticket_id}/reply",
            data={"message": "İkinci yanıt olmamalı"}, cookies=user_cookie, headers=ajax,
        )
        assert duplicate.status_code == 409

        closed = client.post(
            f"{main.ADMIN_CENTER_PATH}/support/{ticket_id}",
            data={"status": "CLOSED"}, cookies=admin_cookie, headers=ajax,
        )
        assert closed.status_code == 200
        assert closed.json()["status"] == "CLOSED"

    with Session(engine) as session:
        ticket = session.get(main.SupportTicket, ticket_id)
        messages = session.exec(select(main.SupportTicketMessage).where(
            main.SupportTicketMessage.ticket_id == ticket_id
        ).order_by(main.SupportTicketMessage.id)).all()
        events = session.exec(select(main.RealtimeEvent).where(
            main.RealtimeEvent.entity_type.in_({"support_ticket", "support_ticket_message"})
        )).all()
        notices = session.exec(select(main.AdminNotice).where(
            main.AdminNotice.user_id == user_id,
            main.AdminNotice.related_type == "support_ticket",
        )).all()

    assert ticket.status == "CLOSED"
    assert [(row.sender_role, row.message) for row in messages] == [
        ("ADMIN", "Destek yanıtı"), ("USER", "Kullanıcı yanıtı")
    ]
    assert {(event.user_id, event.event_type) for event in events} >= {
        (admin_id, "SUPPORT_TICKET_CREATED"),
        (user_id, "SUPPORT_MESSAGE_CREATED"),
        (admin_id, "SUPPORT_MESSAGE_CREATED"),
        (user_id, "SUPPORT_TICKET_UPDATED"),
    }
    assert {notice.notice_type for notice in notices} >= {
        "SUPPORT_MESSAGE", "SUPPORT_TICKET_UPDATE"
    }
    assert (admin_id, "SUPPORT_TICKET_CREATED") in published
    assert (user_id, "SUPPORT_MESSAGE_CREATED") in published
