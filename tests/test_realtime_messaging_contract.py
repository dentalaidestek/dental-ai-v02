from pathlib import Path
import json
import pytest

from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
try:
    from fastapi.testclient import TestClient
except RuntimeError:  # Starlette exposes TestClient only when its optional httpx2 extra is installed.
    TestClient = None

from app import main


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
BASE = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
MESSAGES = (ROOT / "app" / "templates" / "messages.html").read_text(encoding="utf-8")
ROOM = (ROOT / "app" / "templates" / "expert_case_room.html").read_text(encoding="utf-8")
ROW = (ROOT / "app" / "templates" / "_message_row.html").read_text(encoding="utf-8")


def _engine():
    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(test_engine)
    return test_engine


def test_message_event_is_durable_for_both_participants():
    helper = MAIN.split("def _record_message_realtime_events", 1)[1].split("@app.get", 1)[0]
    assert "{case.requester_user_id, case.expert_user_id}" in helper
    assert '"MESSAGE_CREATED"' in helper
    assert '"is_outgoing"' in MAIN
    assert 'evt.event_type==="MESSAGE_CREATED"&&!data.is_outgoing' in BASE


def test_http_text_send_broadcasts_room_after_commit():
    endpoint = MAIN.split("def expert_support_message(", 1)[1].split("@app.get", 1)[0]
    assert "s.commit()" in endpoint
    assert "on_loop(consultation_socket_hub.broadcast" in endpoint
    assert endpoint.index("s.commit()") < endpoint.index("on_loop(consultation_socket_hub.broadcast")
    assert "for realtime_event in realtime_events" in endpoint


def test_inbox_updates_existing_card_without_full_page_fetch():
    assert 'querySelector(".message-preview")' in MESSAGES
    assert 'querySelector(".message-side time")' in MESSAGES
    assert "data.is_outgoing" in MESSAGES
    assert "sortMessageRows" in MESSAGES
    assert 'a.dataset.status==="NEW_REQUEST"' in MESSAGES
    assert 'fetch("/messages"' not in MESSAGES
    assert '"/messages/"+encodeURIComponent(caseId)+"/row"' in MESSAGES
    assert 'data-last-message-id=' in ROW
    assert 'data-sort-at=' in ROW


def test_case_room_deduplicates_and_keeps_ajax_submit_after_dom_refresh():
    assert 'document.getElementById("msg-"+m.id)' in ROOM
    assert 'document.addEventListener("submit"' in ROOM
    assert 'e.target.closest?.(".expert-composer")' in ROOM
    assert "sendInFlight" in ROOM
    assert 'currentTextForm=()=>document.querySelector(".expert-composer")' in ROOM
    assert 'fetch("/expert-support/cases/{{ case.id }}/message"' in ROOM
    assert 'if(textForm)textForm.addEventListener("submit"' not in ROOM


def test_empty_conversation_is_removed_when_first_card_arrives():
    assert 'list.querySelector(".messages-empty")?.remove()' in MESSAGES


def test_message_event_payloads_cover_sender_and_recipient():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        sender = main.User(username="sender", role="DOCTOR", display_name="Gönderen")
        recipient = main.User(username="recipient", role="DOCTOR", display_name="Alıcı")
        session.add(sender)
        session.add(recipient)
        session.commit()
        case = main.ConsultationCase(
            requester_user_id=sender.id,
            expert_user_id=recipient.id,
            specialty="Endodonti",
            clinical_summary="Özet",
            question="Soru",
            status="ACTIVE",
            expert_response_deadline=main._utcnow_naive(),
        )
        session.add(case)
        session.commit()
        message = main.ConsultationMessage(case_id=case.id, sender_user_id=sender.id, content="Merhaba")
        session.add(message)
        session.commit()
        events = main._record_message_realtime_events(session, case, message, sender)
        session.commit()

        assert {event.user_id for event in events} == {sender.id, recipient.id}
        payloads = {event.user_id: json.loads(event.payload_json) for event in events}
        assert payloads[sender.id]["is_outgoing"] is True
        assert payloads[recipient.id]["is_outgoing"] is False
        assert all(payload["message_id"] == message.id for payload in payloads.values())


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient optional dependency is unavailable")
def test_http_message_reaches_room_and_both_global_sessions(monkeypatch):
    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(main, "engine", test_engine)
    with Session(test_engine, expire_on_commit=False) as session:
        sender = main.User(username="a", role="DOCTOR", display_name="A")
        recipient = main.User(username="b", role="DOCTOR", display_name="B")
        session.add(sender)
        session.add(recipient)
        session.commit()
        case = main.ConsultationCase(
            requester_user_id=sender.id,
            expert_user_id=recipient.id,
            specialty="Endodonti",
            clinical_summary="Özet",
            question="Soru",
            status="ACTIVE",
            expert_response_deadline=main._utcnow_naive(),
        )
        session.add(case)
        sender_token, recipient_token = "sender-token", "recipient-token"
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(sender_token), user_id=sender.id,
            expires_at=main._utcnow_naive() + main.timedelta(days=1),
        ))
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(recipient_token), user_id=recipient.id,
            expires_at=main._utcnow_naive() + main.timedelta(days=1),
        ))
        session.commit()

    with TestClient(main.app) as client:
        with client.websocket_connect(
            f"/ws/expert-support/cases/{case.id}", cookies={main.SESSION_COOKIE: recipient_token}
        ) as recipient_room, client.websocket_connect(
            "/ws/sync", cookies={main.SESSION_COOKIE: recipient_token}
        ) as recipient_sync, client.websocket_connect(
            "/ws/sync", cookies={main.SESSION_COOKIE: sender_token}
        ) as sender_sync:
            assert recipient_room.receive_json()["type"] == "ready"
            assert recipient_sync.receive_json()["type"] == "ready"
            assert sender_sync.receive_json()["type"] == "ready"
            response = client.post(
                f"/expert-support/cases/{case.id}/message",
                data={"content": "Anlık mesaj"},
                headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
                cookies={main.SESSION_COOKIE: sender_token},
            )
            assert response.status_code == 200
            message_id = response.json()["message"]["id"]
            room_event = recipient_room.receive_json()
            recipient_event = recipient_sync.receive_json()
            sender_event = sender_sync.receive_json()

    assert room_event["type"] == "message"
    assert room_event["message"]["id"] == message_id
    assert recipient_event["event_type"] == "MESSAGE_CREATED"
    assert recipient_event["payload"]["message_id"] == message_id
    assert recipient_event["payload"]["is_outgoing"] is False
    assert sender_event["event_type"] == "MESSAGE_CREATED"
    assert sender_event["payload"]["message_id"] == message_id
    assert sender_event["payload"]["is_outgoing"] is True


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient optional dependency is unavailable")
def test_inbox_server_order_keeps_new_requests_first_then_latest_message(monkeypatch):
    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(main, "engine", test_engine)
    now = main._utcnow_naive()
    with Session(test_engine, expire_on_commit=False) as session:
        viewer = main.User(username="viewer", role="DOCTOR", display_name="Viewer")
        other = main.User(username="other", role="DOCTOR", display_name="Other")
        session.add(viewer)
        session.add(other)
        session.commit()

        def make_case(status, requested_at):
            case = main.ConsultationCase(
                requester_user_id=other.id if status == "REQUESTED" else viewer.id,
                expert_user_id=viewer.id if status == "REQUESTED" else other.id,
                specialty="Endodonti", clinical_summary="Özet", question="Soru",
                status=status, requested_at=requested_at,
                expert_response_deadline=now + main.timedelta(minutes=10),
            )
            session.add(case)
            session.commit()
            return case

        new_request = make_case("REQUESTED", now - main.timedelta(hours=3))
        older = make_case("ACTIVE", now - main.timedelta(hours=2))
        newer = make_case("ACTIVE", now - main.timedelta(hours=1))
        session.add(main.ConsultationMessage(
            case_id=older.id, sender_user_id=other.id, content="Eski", created_at=now - main.timedelta(minutes=20)
        ))
        session.add(main.ConsultationMessage(
            case_id=newer.id, sender_user_id=other.id, content="Yeni", created_at=now - main.timedelta(minutes=2)
        ))
        token = "viewer-token"
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(token), user_id=viewer.id,
            expires_at=now + main.timedelta(days=1),
        ))
        session.commit()

    with TestClient(main.app) as client:
        response = client.get("/messages", cookies={main.SESSION_COOKIE: token})
    assert response.status_code == 200
    html = response.text
    positions = [html.index(f'data-case-id="{case_id}"') for case_id in (new_request.id, newer.id, older.id)]
    assert positions == sorted(positions)


def test_realtime_cursor_tolerates_cross_process_commit_reordering():
    assert "seenEventIds.has(id)" in BASE
    assert "if(id>lastEventId)" in BASE
    assert "id&&id<=lastEventId" not in BASE
    assert "lastEventId-syncOverlap" in BASE


def test_ws_resume_history_is_marked_replay_and_silent_in_client():
    assert 'payload["replay"] = True' in MAIN
    assert 'notify:evt?.replay!==true' in BASE
    assert 'if(notify){bumpMessageBadge();showLiveMessage(data);}' in BASE
    assert 'replayProgramState=evt.replay===true&&["PROGRAM_CREATED","PROGRAM_UPDATED","PROGRAM_COMPLETED","PROGRAM_DELETED"]' in BASE


def test_notification_center_open_marks_active_notices_seen():
    assert '@app.post("/account/notifications/read-all")' in MAIN
    assert MAIN.index('@app.post("/account/notifications/read-all")') < MAIN.index('@app.post("/account/notifications/{notice_id}/read")')
    assert 'if(open)markNotificationsSeen();' in BASE
    assert 'fetch("/account/notifications/read-all",{method:"POST"' in BASE
    assert "seen_before:seenBefore" in BASE
    assert "AdminNotice.created_at <= seen_before" in MAIN
    assert 'sessionStorage.setItem(notificationUnreadKey' in BASE
    assert '"NOTIFICATIONS_READ"' in MAIN
    assert 'evt.event_type==="NOTIFICATIONS_READ"' in BASE
    read_all = MAIN.split("def account_notifications_read_all", 1)[1].split('@app.get("/account/admin-notices")', 1)[0]
    assert "_record_realtime_event" in read_all
    assert "on_loop(_publish_realtime_event, realtime_event)" in read_all



@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_notification_read_all_route_persists_seen_state_and_keeps_notice_active(monkeypatch):
    engine = _engine()
    now = main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as session:
        user = main.User(username="notice-owner", role="DOCTOR", display_name="Notice Owner")
        session.add(user)
        session.commit()
        notice = main.AdminNotice(
            user_id=user.id, title="Hatırlatma", message="Program kaydı",
            notice_type="PROGRAM_REMINDER", status="ACTIVE",
        )
        session.add(notice)
        token = "notice-owner-token"
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(token), user_id=user.id,
            expires_at=now + main.timedelta(days=1),
        ))
        session.commit()
        notice_id = notice.id
        user_id = user.id
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as client:
        response = client.post("/account/notifications/read-all", cookies={main.SESSION_COOKIE: token})
    assert response.status_code == 200
    assert response.json()["read_count"] == 1
    with Session(engine) as session:
        notice = session.get(main.AdminNotice, notice_id)
        assert notice.user_id == user_id
        assert notice.status == "ACTIVE"
        assert notice.is_read is True
        assert notice.read_at is not None
        events = session.exec(select(main.RealtimeEvent).where(
            main.RealtimeEvent.user_id == user_id,
            main.RealtimeEvent.event_type == "NOTIFICATIONS_READ",
        )).all()
        assert len(events) == 1

def test_seen_program_reminders_expire_without_touching_other_notices():
    helper = MAIN.split("def _expire_seen_program_reminders", 1)[1].split('@app.get("/account/notifications")', 1)[0]
    assert 'AdminNotice.notice_type == "PROGRAM_REMINDER"' in helper
    assert "AdminNotice.is_read == True" in helper
    assert "AdminNotice.read_at <= cutoff" in helper
    assert 'notice.status = "RESOLVED"' in helper
    assert "timedelta(hours=24)" in helper
