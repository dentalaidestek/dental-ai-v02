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
    assert response.json() == {"ok": True, "status": expected}
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
    assert room_events == [(case_id, {"type": "case_status", "case_id": case_id, "status": expected})]


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
    assert 'id="expertComposeStack"' not in after.text
    assert duplicate.status_code == 409
    with Session(engine) as session:
        reviews = session.exec(select(main.ExpertReview).where(main.ExpertReview.case_id == case_id)).all()
        assert len(reviews) == 1


def test_completed_ui_has_no_finish_action_and_realtime_refresh_is_debounced():
    menu = ROOM.split('<div class="case-room-menu-panel">', 1)[1].split("</div></details>", 1)[0]
    assert 'case.status=="ACTIVE"' in menu
    assert "Danışmayı bitir" in menu and "Danışmanlığı bitir" in menu
    assert 'case.status in ["ACTIVE","EXPERT_COMPLETED"]' not in menu
    assert "Uzman danışmanlığı sonlandırdı" in ROOM
    assert 'evt.event_type==="CASE_STATUS_UPDATED"' in ROOM
    assert "scheduleCaseRoomRefresh(data.status)" in ROOM
    assert "caseRefreshPromise" in ROOM and "caseRefreshTimer" in ROOM
    assert 'e.target.closest?.(".case-state-form,.case-review-form,.case-report-form")' in ROOM
