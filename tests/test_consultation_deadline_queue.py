from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import main


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")


def _case(session, status="REQUESTED"):
    requester = main.User(username="queue-requester", role="DOCTOR", display_name="Requester")
    expert = main.User(username="queue-expert", role="DOCTOR", display_name="Expert")
    session.add(requester); session.add(expert); session.flush()
    deadline = main._utcnow_naive() + main.timedelta(minutes=10)
    case = main.ConsultationCase(
        requester_user_id=requester.id, expert_user_id=expert.id, specialty="Endodonti",
        clinical_summary="Özet", question="Soru", status=status, expert_response_deadline=deadline,
    )
    session.add(case); session.flush()
    return case


def test_deadline_pair_is_durable_and_deduplicated():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        case = _case(session)
        main._enqueue_deadline_pair(session, case.id, "EXPERT_RESPONSE", case.expert_response_deadline)
        main._enqueue_deadline_pair(session, case.id, "EXPERT_RESPONSE", case.expert_response_deadline)
        session.commit()
        jobs = session.exec(select(main.ConsultationDeadlineJob).where(main.ConsultationDeadlineJob.case_id == case.id)).all()
        assert {job.job_type for job in jobs} == {"EXPERT_RESPONSE_WARNING", "EXPERT_RESPONSE_DUE"}
        assert len(jobs) == 2


def test_stale_deadline_job_becomes_noop():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        case = _case(session)
        main._enqueue_deadline_pair(session, case.id, "EXPERT_RESPONSE", case.expert_response_deadline)
        session.flush()
        job = session.exec(select(main.ConsultationDeadlineJob).where(main.ConsultationDeadlineJob.job_type == "EXPERT_RESPONSE_DUE")).first()
        case.status = "ACTIVE"; session.add(case); session.flush()
        notices, events = main._process_deadline_job(session, job, case.expert_response_deadline + main.timedelta(seconds=1))
        assert notices == []
        assert events == []
        assert case.status == "ACTIVE"


def test_worker_contract_is_bounded_and_multi_worker_safe():
    assert "CONSULTATION_DEADLINE_BATCH_SIZE = 100" in MAIN
    assert ".with_for_update(skip_locked=True)" in MAIN
    assert 'ConsultationDeadlineJob.status == "PENDING"' in MAIN
    assert "while await _process_consultation_deadline_jobs()" in MAIN
    assert "_consultation_deadline_wakeup" in MAIN


def test_render_paths_do_not_mutate_deadline_state():
    room = MAIN.split("async def expert_support_case_room", 1)[1].split("@app.get", 1)[0]
    inbox = MAIN.split("def consultation_messages_inbox", 1)[1].split("@app.get", 1)[0]
    assert 'case.status = "PROPOSAL_EXPIRED"' not in room
    assert '"START_DEADLINE_MISSED"' not in inbox
