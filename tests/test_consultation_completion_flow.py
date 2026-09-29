from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main


ROOM = (Path(__file__).resolve().parents[1] / "app" / "templates" / "expert_case_room.html").read_text(encoding="utf-8")


@pytest.fixture()
def consultation_app(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    now = main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as session:
        requester = main.User(username="requester", role="DOCTOR", display_name="Gönderen Hekim")
        expert = main.User(username="expert", role="DOCTOR", display_name="Uzman Hekim")
        session.add(requester)
        session.add(expert)
        session.commit()
        tokens = {requester.id: "requester-token", expert.id: "expert-token"}
        for user_id, token in tokens.items():
            session.add(main.SessionToken(
                token_hash=main.hash_session_token(token), user_id=user_id,
                expires_at=now + main.timedelta(days=1),
            ))
        session.commit()
        ids = {"requester": requester.id, "expert": expert.id}
    return engine, ids, tokens


def create_case(engine, ids, status):
    with Session(engine, expire_on_commit=False) as session:
        case = main.ConsultationCase(
            requester_user_id=ids["requester"], expert_user_id=ids["expert"],
            specialty="Endodonti", clinical_summary="Özet", question="Soru",
            status=status, expert_response_deadline=main._utcnow_naive() + main.timedelta(minutes=10),
        )
        session.add(case)
        session.commit()
        return case.id


def post_action(client, case_id, token, action):
    return client.post(
        f"/expert-support/cases/{case_id}/complete",
        data={"action": action}, cookies={main.SESSION_COOKIE: token},
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
@pytest.mark.parametrize(
    "initial,actor,action,expected",
    [
        ("ACTIVE", "expert", "COMPLETE", "EXPERT_COMPLETED"),
        ("ACTIVE", "requester", "COMPLETE", "COMPLETED"),
        ("EXPERT_COMPLETED", "requester", "COMPLETE", "COMPLETED"),
        ("EXPERT_COMPLETED", "requester", "CONTINUE", "ACTIVE"),
        ("EXPERT_COMPLETED", "requester", "DISPUTE", "DISPUTE"),
    ],
)
def test_completion_transitions_and_realtime_events(consultation_app, monkeypatch, initial, actor, action, expected):
    engine, ids, tokens = consultation_app
    case_id = create_case(engine, ids, initial)
    published = []
    room_events = []

    async def capture_publish(event):
        published.append(event.user_id)

    async def capture_room(case_number, payload):
        room_events.append((case_number, payload))

    monkeypatch.setattr(main, "_publish_realtime_event", capture_publish)
    monkeypatch.setattr(main.consultation_socket_hub, "broadcast", capture_room)
    with TestClient(main.app) as client:
        response = post_action(client, case_id, tokens[ids[actor]], action)
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == expected
    assert payload["case_id"] == case_id
    assert payload["viewer_role"] == ("REQUESTER" if actor == "requester" else "EXPERT")
    with Session(engine) as session:
        case = session.get(main.ConsultationCase, case_id)
        events = session.exec(select(main.RealtimeEvent).where(
            main.RealtimeEvent.entity_type == "consultation_case",
            main.RealtimeEvent.entity_id == str(case_id),
            main.RealtimeEvent.event_type == "CASE_STATUS_UPDATED",
        )).all()
        assert case.status == expected
        assert {event.user_id for event in events} == {ids["requester"], ids["expert"]}
        if initial == "ACTIVE" and actor == "expert":
            assert case.expert_completed_at is not None
            assert case.completion_confirmation_deadline is not None
        if initial == "ACTIVE" and actor == "requester":
            assert case.requester_completed_at is not None
            assert case.completed_at is not None
    assert set(published) == {ids["requester"], ids["expert"]}
    assert len(room_events) == 1
    assert room_events[0][0] == case_id
    assert room_events[0][1]["type"] == "case_status"
    assert room_events[0][1]["case_id"] == case_id
    assert room_events[0][1]["status"] == expected


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_review_form_is_replaced_by_persisted_success_state(consultation_app):
    engine, ids, tokens = consultation_app
    case_id = create_case(engine, ids, "COMPLETED")
    cookie = {main.SESSION_COOKIE: tokens[ids["requester"]]}
    with TestClient(main.app) as client:
        before = client.get(f"/expert-support/cases/{case_id}", cookies=cookie)
        saved = client.post(
            f"/expert-support/cases/{case_id}/review",
            data={"rating": "4", "comment": "Faydalı görüşme"}, cookies=cookie,
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        after = client.get(f"/expert-support/cases/{case_id}", cookies=cookie)
        duplicate = client.post(
            f"/expert-support/cases/{case_id}/review",
            data={"rating": "5", "comment": "İkinci"}, cookies=cookie,
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
    assert before.status_code == 200
    assert "Değerlendirmeyi Kaydet" in before.text
    assert saved.status_code == 200 and saved.json() == {"ok": True}
    assert "Değerlendirmeyi Kaydet" not in after.text
    assert "Değerlendirmeniz için teşekkürler" in after.text
    assert "4/5" in after.text and "Faydalı görüşme" in after.text
    assert "Danışmanlığı bitir" not in after.text
    assert 'id="expertComposeStack"' in after.text
    assert 'id="expertComposeStack" data-case-dynamic="post" hidden' in after.text
    assert duplicate.status_code == 409
    with Session(engine) as session:
        reviews = session.exec(select(main.ExpertReview).where(main.ExpertReview.case_id == case_id)).all()
        assert len(reviews) == 1



@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_expert_today_proposal_uses_ajax_state_and_realtime_for_both_participants(consultation_app, monkeypatch):
    engine, ids, tokens = consultation_app
    case_id = create_case(engine, ids, "REQUESTED")
    published = []
    room_events = []

    async def capture_publish(event):
        published.append(event.user_id)

    async def capture_room(case_number, payload):
        room_events.append((case_number, payload))

    monkeypatch.setattr(main, "_publish_realtime_event", capture_publish)
    monkeypatch.setattr(main.consultation_socket_hub, "broadcast", capture_room)
    with TestClient(main.app) as client:
        response = client.post(
            f"/expert-support/cases/{case_id}/expert-response",
            data={"decision": "ACCEPT", "start_option": "TODAY", "proposal_note": "Bugün değerlendireceğim"},
            cookies={main.SESSION_COOKIE: tokens[ids["expert"]]},
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "PROPOSED"
    assert payload["viewer_role"] == "EXPERT"
    assert payload["proposed_start_label"] == "Bugün içinde"
    assert payload["requester_decision_deadline"]
    with Session(engine) as session:
        case = session.get(main.ConsultationCase, case_id)
        assert case.status == "PROPOSED"
        assert case.proposed_start_minutes >= 1
        events = session.exec(select(main.RealtimeEvent).where(
            main.RealtimeEvent.entity_type == "consultation_case",
            main.RealtimeEvent.entity_id == str(case_id),
            main.RealtimeEvent.event_type == "CASE_STATUS_UPDATED",
        )).all()
        assert {event.user_id for event in events} == {ids["requester"], ids["expert"]}
    assert set(published) == {ids["requester"], ids["expert"]}
    assert room_events[0][1]["status"] == "PROPOSED"
    assert room_events[0][1]["proposed_start_label"] == "Bugün içinde"

def test_completed_ui_has_no_finish_action_and_realtime_refresh_is_debounced():
    menu = ROOM.split('<div class="case-room-menu-panel">', 1)[1].split("</div></details>", 1)[0]
    assert 'case.status=="ACTIVE"' in menu
    assert "Danışmayı bitir" in menu and "Danışmanlığı bitir" in menu
    assert 'case.status in ["ACTIVE","EXPERT_COMPLETED"]' not in menu
    assert "Uzman danışmanlığı sonlandırdı" in ROOM
    assert 'evt.event_type==="CASE_STATUS_UPDATED"' in ROOM
    assert "applyCaseState(data)" in ROOM
    assert "if(!applyCaseState(data))await refreshCaseRoom" in ROOM
    assert "caseRefreshPromise" in ROOM and "caseRefreshTimer" in ROOM
    assert 'e.target.closest?.(".case-state-form,.case-review-form,.case-report-form")' in ROOM


def test_dispute_chat_stays_open_but_completed_chat_is_closed_on_every_write_path():
    main_source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert 'case.status not in {"ACTIVE", "WAITING_START", "EXPERT_COMPLETED", "DISPUTE"}' in main_source
    assert 'case.status not in {"ACTIVE","WAITING_START","EXPERT_COMPLETED","DISPUTE"}' in main_source
    assert 'case.status not in ["ACTIVE","WAITING_START","EXPERT_COMPLETED","DISPUTE"]' in ROOM
    assert '["ACTIVE","EXPERT_COMPLETED","DISPUTE"].includes(data.status)' in ROOM
    annotation = main_source.split("def expert_support_annotate_message", 1)[1].split("PROFANITY_PATTERNS", 1)[0]
    assert 'case.status not in {"ACTIVE", "WAITING_START", "EXPERT_COMPLETED", "DISPUTE"}' in annotation
    assert '"COMPLETED"' not in annotation


def test_dispute_is_open_for_capacity_and_inbox_not_history():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    messages_template = (Path(__file__).resolve().parents[1] / "app" / "templates" / "messages.html").read_text(encoding="utf-8")
    assert 'CONSULTATION_CAPACITY_STATUSES = ("ACTIVE", "WAITING_START", "EXPERT_COMPLETED", "DISPUTE")' in source
    assert 'ConsultationCase.status.in_(["ACTIVE", "WAITING_START", "EXPERT_COMPLETED"])' not in source
    assert 'if case.status == "DISPUTE":\n        return "ACTIVE", "Sorun Bildirildi"' in source
    assert '["HISTORY","CLOSED","DISPUTE"]' not in messages_template


def test_requester_decisions_consume_completion_deadline():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    complete = source.split('def expert_support_complete', 1)[1].split('@app.get("/patients/new"', 1)[0]
    assert 'case.requester_completed_at = now; case.completed_at = now; case.completion_confirmation_deadline = None; case.status = "COMPLETED"' in complete
    assert 'case.status = "ACTIVE"; case.completion_confirmation_deadline = None;' in complete
    assert 'case.status = "DISPUTE"\n            case.completion_confirmation_deadline = None' in complete


def test_consultation_reference_state_cards_are_scoped_and_complete():
    root = Path(__file__).resolve().parents[1]
    template = (root / "app" / "templates" / "expert_case_room.html").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "style.css").read_text(encoding="utf-8")
    for state in ("REQUESTED", "PROPOSED", "WAITING_START", "ACTIVE", "EXPERT_COMPLETED", "DISPUTE", "COMPLETED", "REJECTED", "PROPOSAL_REJECTED", "EXPERT_TIMEOUT", "PROPOSAL_EXPIRED"):
        assert state in template
    for tone in ("state-wait", "state-proposed", "state-start", "state-active", "state-expert-completed", "state-dispute", "state-completed", "state-rejected", "state-timeout"):
        assert f".expert-room .consult-state-card.{tone}" in css
    assert 'class="case-live-status"' not in template
    assert 'class="expert-actionbox case-state-form"' not in template
    assert '>Başka Uzman Seç</button>' not in template
    assert '>× Reddet</button>' in template
    assert 'consult-review-toggle' in template
    assert 'form.classList.contains("case-state-form"))stateMenu.open=false' in template


def test_consultation_room_avoids_idle_recovery_and_countdown_work():
    root = Path(__file__).resolve().parents[1]
    room = (root / "app" / "templates" / "expert_case_room.html").read_text(encoding="utf-8")
    messages = (root / "app" / "templates" / "messages.html").read_text(encoding="utf-8")
    source = (root / "app" / "main.py").read_text(encoding="utf-8")
    assert "let catchUpPromise=null" in room
    assert 'if(!socket||socket.readyState!==WebSocket.OPEN)catchUp();' in room
    assert 'if(!nodes.length){if(countdownTimer){clearInterval(countdownTimer);countdownTimer=null}return}' in room
    assert 'if(!hasCountdown){if(messageCountdownTimer!==null){clearInterval(messageCountdownTimer);messageCountdownTimer=null}return}' in messages
    row_endpoint = source.split('def consultation_message_row', 1)[1].split('@app.get("/messages/deleted"', 1)[0]
    assert '.limit(1)).first()' in row_endpoint
    assert 'select(func.count(ConsultationMessage.id))' in row_endpoint
    assert 'order_by(ConsultationMessage.created_at.desc())).all()' not in row_endpoint


def test_unread_count_uses_lightweight_aggregate_path():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    helper = source[source.index("def _consultation_unread_total"):source.index('@app.get("/messages/unread-count")')]
    endpoint = source[source.index('@app.get("/messages/unread-count")'):source.index('@app.get("/expert-support/cases"', source.index('@app.get("/messages/unread-count")'))]
    assert "ConsultationMessage.case_id" in helper
    assert "func.count(ConsultationMessage.id)" in helper
    assert "fresh_request_ids" in helper
    assert "newest.deleted_at" in helper
    assert "_consultation_inbox_rows" not in endpoint
    assert "_consultation_unread_total" in endpoint


def test_global_realtime_catchup_requests_are_coalesced():
    base = (Path(__file__).resolve().parents[1] / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert "catchUpEventsPromise" in base
    assert "unreadCountPromise" in base
    assert "if(catchUpEventsPromise)return catchUpEventsPromise" in base
    assert "if(unreadCountPromise)return unreadCountPromise" in base
