from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from fastapi.testclient import TestClient

from app import main


def _verified_profile(user_id: int) -> main.ExpertProfile:
    return main.ExpertProfile(
        user_id=user_id,
        specialty="Endodonti",
        application_status="APPROVED",
        verification_status="VERIFIED",
        specialty_verified=True,
        credential_document_path=f"expert/{user_id}/credential.pdf",
        phone="05000000000",
        availability="AVAILABLE",
        consultation_price=200,
    )


def test_distinct_expert_is_routed_by_profile_user_id_and_self_stays_blocked(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    now = main._utcnow_naive()

    with Session(engine, expire_on_commit=False) as session:
        requester = main.User(username="requester", role="DOCTOR", display_name="A")
        expert = main.User(username="expert", role="DOCTOR", display_name="B")
        session.add(requester)
        session.add(expert)
        session.commit()
        session.add(_verified_profile(requester.id))
        session.add(_verified_profile(expert.id))
        token = "identity-routing-token"
        session.add(main.SessionToken(
            token_hash=main.hash_session_token(token),
            user_id=requester.id,
            expires_at=now + main.timedelta(days=1),
        ))
        session.commit()

    cookies = {main.SESSION_COOKIE: token}
    with TestClient(main.app) as client:
        directory = client.get("/expert-support", cookies=cookies)
        own_page = client.get(f"/expert-support/request/{requester.id}", cookies=cookies)
        other_page = client.get(f"/expert-support/request/{expert.id}", cookies=cookies)
        own_post = client.post(
            f"/expert-support/request/{requester.id}",
            data={"clinical_summary": "Özet", "question": "Soru"},
            cookies=cookies,
        )
        other_post = client.post(
            f"/expert-support/request/{expert.id}",
            data={"clinical_summary": "Özet", "question": "Soru"},
            cookies=cookies,
            follow_redirects=False,
        )

    assert directory.status_code == 200
    assert f'/expert-support/request/{expert.id}' in directory.text
    assert f'/expert-support/request/{requester.id}' not in directory.text
    assert own_page.status_code == 400
    assert own_post.status_code == 400
    assert other_page.status_code == 200
    assert other_post.status_code == 303

    with Session(engine) as session:
        cases = session.exec(select(main.ConsultationCase)).all()
        assert len(cases) == 1
        assert cases[0].requester_user_id == requester.id
        assert cases[0].expert_user_id == expert.id

