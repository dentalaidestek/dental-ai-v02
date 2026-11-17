import pytest
from sqlmodel import Session, SQLModel, create_engine

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_mobile_consultation_live_messages_are_incremental_and_case_scoped(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "consultation-live.db"),
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr("app.mobile_api.engine", engine)
    now = main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as session:
        requester = main.User(
            username="live-requester", role="DOCTOR",
            display_name="Requester", email_verified_at=now,
        )
        expert = main.User(
            username="live-expert", role="DOCTOR",
            display_name="Expert", email_verified_at=now,
        )
        outsider = main.User(
            username="live-outsider", role="DOCTOR",
            display_name="Outsider", email_verified_at=now,
        )
        session.add_all([requester, expert, outsider])
        session.commit()
        tokens = {
            requester.id: "mobile-live-requester-token",
            expert.id: "mobile-live-expert-token",
            outsider.id: "mobile-live-outsider-token",
        }
        for user in (requester, expert, outsider):
            session.add(main.SessionToken(
                token_hash=main.hash_session_token(tokens[user.id]),
                user_id=user.id,
                expires_at=now + main.timedelta(days=1),
            ))
        case = main.ConsultationCase(
            requester_user_id=requester.id,
            expert_user_id=expert.id,
            specialty="Endodonti",
            clinical_summary="Synthetic clinical summary",
            question="Synthetic question",
            status="ACTIVE",
            expert_response_deadline=now + main.timedelta(days=1),
        )
        session.add(case)
        session.flush()
        messages = [
            main.ConsultationMessage(
                case_id=case.id, sender_user_id=sender,
                message_type="TEXT", content=body,
            )
            for sender, body in (
                (requester.id, "İlk mesaj"),
                (expert.id, "İkinci mesaj"),
                (expert.id, "Üçüncü mesaj"),
                (requester.id, "Dördüncü mesaj"),
            )
        ]
        session.add_all(messages)
        session.commit()
        case_id = case.id
        message_ids = [message.id for message in messages]
        requester_token = tokens[requester.id]
        outsider_token = tokens[outsider.id]

    with TestClient(main.app) as client:
        headers = {"Authorization": "Bearer " + requester_token}
        outsider_headers = {"Authorization": "Bearer " + outsider_token}

        assert client.get(
            f"/api/mobile/v1/consultations/{case_id}/messages-live"
        ).status_code == 401

        inbox = client.get("/api/mobile/v1/consultations", headers=headers)
        assert inbox.status_code == 200, inbox.text
        row = next(item for item in inbox.json()["items"] if item["id"] == case_id)
        assert row["last_message_id"] == message_ids[-1]
        assert row["last_message"] == "Dördüncü mesaj"

        first = client.get(
            f"/api/mobile/v1/consultations/{case_id}/messages-live?after_id={message_ids[0]}&limit=2",
            headers=headers,
        )
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert [item["id"] for item in first_body["messages"]] == message_ids[1:3]
        assert first_body["has_more"] is True
        assert first_body["next_after"] == message_ids[2]
        assert "patient_id" not in first_body["case"]
        assert "clinical_summary" not in first_body["case"]

        second = client.get(
            f"/api/mobile/v1/consultations/{case_id}/messages-live?after_id={first_body['next_after']}&limit=2",
            headers=headers,
        )
        assert second.status_code == 200, second.text
        assert [item["id"] for item in second.json()["messages"]] == [message_ids[3]]
        assert second.json()["has_more"] is False
        assert second.json()["next_after"] is None

        empty = client.get(
            f"/api/mobile/v1/consultations/{case_id}/messages-live?after_id={message_ids[-1]}",
            headers=headers,
        )
        assert empty.status_code == 200
        assert empty.json()["messages"] == []
        assert empty.json()["has_more"] is False

        assert client.get(
            f"/api/mobile/v1/consultations/{case_id}/messages-live",
            headers=outsider_headers,
        ).status_code == 404
