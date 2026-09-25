from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main


ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
ROOM = (ROOT / "app" / "templates" / "expert_case_room.html").read_text(encoding="utf-8")
MESSAGES = (ROOT / "app" / "templates" / "messages.html").read_text(encoding="utf-8")
ROW = (ROOT / "app" / "templates" / "_message_row.html").read_text(encoding="utf-8")


def test_messages_to_case_uses_scoped_partial_navigation():
    assert 'event.target.closest?.(".messages-list .message-row-main")' in BASE
    assert 'headers:{"X-Requested-With":"partial-navigation"}' in BASE
    assert 'incomingMain?.querySelector(".expert-room")' in BASE
    assert "history.pushState({daiPartialCase:true}" in BASE
    assert "location.assign(url)" in BASE
    assert 'class="message-row-main"' in ROW


def test_back_restores_live_list_dom_and_scroll_without_fetch():
    assert 'host.id="daiMessagesSnapshotHost"' in BASE
    assert "while(main.firstChild) host.appendChild(main.firstChild)" in BASE
    assert "replaceChildren(...snapshot.host.childNodes)" in BASE
    assert "scrollTo(snapshot.scrollX,snapshot.scrollY)" in BASE
    assert 'if(back&&messagesSnapshot){event.preventDefault();history.back();return;}' in BASE
    restore = BASE.split("function restoreMessagesView()", 1)[1].split("document.addEventListener", 1)[0]
    assert "fetch(" not in restore


def test_case_room_socket_and_global_listeners_have_cleanup_lifecycle():
    assert "window.__daiCaseRoomCleanup?.()" in ROOM
    assert "const roomAbort=new AbortController()" in ROOM
    assert "signal:roomSignal" in ROOM
    assert "clearInterval(countdownTimer)" in ROOM
    assert "clearTimeout(reconnectTimer)" in ROOM
    assert "active.onclose=null" in ROOM
    assert "if(destroyed||socket!==connection)return" in ROOM
    assert "window.__daiCaseRoomCleanup?.();" in BASE


def test_existing_realtime_send_and_dedup_are_preserved():
    assert 'document.getElementById("msg-"+m.id)' in ROOM
    assert 'document.addEventListener("submit"' in ROOM
    assert 'e.target.closest?.(".expert-composer")' in ROOM
    assert "sendInFlight" in ROOM
    assert 'headers:{"Accept":"application/json","X-Requested-With":"XMLHttpRequest"}' in ROOM
    assert 'window.addEventListener("dai:sync-event"' in ROOM


def test_global_sync_socket_is_singleton_and_stale_safe():
    assert "!window.__daiSyncConnectionStarted" in BASE
    assert "window.__daiSyncConnectionStarted = true" in BASE
    assert "syncSocket.readyState===WebSocket.CONNECTING" in BASE
    assert "syncSocket.readyState===WebSocket.OPEN" in BASE
    assert "if(syncSocket!==connection)return" in BASE
    assert "syncSocket=null" in BASE


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient optional dependency is unavailable")
def test_messages_and_direct_case_url_keep_server_rendered_fallback(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    now = main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as session:
        viewer = main.User(username="viewer", role="DOCTOR", display_name="Viewer")
        expert = main.User(username="expert", role="DOCTOR", display_name="Expert")
        session.add(viewer)
        session.add(expert)
        session.commit()
        case = main.ConsultationCase(
            requester_user_id=viewer.id,
            expert_user_id=expert.id,
            specialty="Endodonti",
            clinical_summary="Özet",
            question="Soru",
            status="ACTIVE",
            expert_response_deadline=now + main.timedelta(minutes=10),
        )
        session.add(case)
        token = "partial-navigation-token"
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(token), user_id=viewer.id,
            expires_at=now + main.timedelta(days=1),
        ))
        session.commit()

    with TestClient(main.app) as client:
        messages = client.get("/messages", cookies={main.SESSION_COOKIE: token})
        direct = client.get(
            f"/expert-support/cases/{case.id}", cookies={main.SESSION_COOKIE: token}
        )
        partial = client.get(
            f"/expert-support/cases/{case.id}",
            headers={"X-Requested-With": "partial-navigation"},
            cookies={main.SESSION_COOKIE: token},
        )

    assert messages.status_code == 200
    assert f'href="/expert-support/cases/{case.id}"' in messages.text
    assert direct.status_code == 200
    assert partial.status_code == 200
    assert 'class="expert-shell expert-room"' in direct.text
    assert 'class="expert-shell expert-room"' in partial.text
