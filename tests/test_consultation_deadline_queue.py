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
    room = MAIN.split("def expert_support_case_room", 1)[1].split("@app.get", 1)[0]
    inbox = MAIN.split("def consultation_messages_inbox", 1)[1].split("@app.get", 1)[0]
    assert 'case.status = "PROPOSAL_EXPIRED"' not in room
    assert '"START_DEADLINE_MISSED"' not in inbox


def test_failed_job_processing_isolated_by_savepoint():
    processor = MAIN.split("def _process_consultation_deadline_jobs", 1)[1].split("def _consultation_deadline_worker", 1)[0]
    assert "with s.begin_nested():" in processor
    assert "rolled back every partial domain/notice/event" in processor


def test_waiting_start_message_paths_resolve_warning_and_publish_status():
    http = MAIN.split("def expert_support_message(", 1)[1].split("@app.get", 1)[0]
    ws = MAIN.split("def _socket_message_sync", 1)[1].split("@app.websocket", 1)[0]
    media = MAIN.split("def expert_support_media_message", 1)[1].split("@app.get", 1)[0]
    for path in (http, ws, media):
        assert "CONSULTATION_DEADLINE_WARNING" in path
        assert "_record_case_status_realtime_events" in path
    assert "notification_events: list[RealtimeEvent] = []" in http
    assert "status_events: list[RealtimeEvent] = []" in http


def test_postgres_cross_process_wakeup_contract():
    assert 'PG_DEADLINE_CHANNEL = "dentalai_deadline_jobs"' in MAIN
    assert 'PG_REALTIME_CHANNEL = "dentalai_realtime_events"' in MAIN
    assert "pg_notify(:channel, :payload)" in MAIN
    assert "def _postgres_event_listener" in MAIN
    assert 'DEADLINE_EXECUTION_MODE = os.getenv("DENTALAI_DEADLINE_EXECUTION", "embedded")' in MAIN


def test_deadline_enqueue_duplicate_isolated_from_domain_transaction():
    enqueue = MAIN.split("def _enqueue_deadline_job", 1)[1].split("def _enqueue_deadline_pair", 1)[0]
    assert "with session.begin_nested():" in enqueue
    assert "except IntegrityError:" in enqueue


def test_capacity_slot_allocation_is_serialized_on_postgres():
    endpoint = MAIN.split("def expert_support_request_create", 1)[1].split("@app.", 1)[0]
    assert "profile_stmt.with_for_update()" in endpoint
    assert "_expert_open_case_count(s, expert_user_id)" in endpoint


def test_startup_reconciles_missing_jobs_even_when_queue_already_has_rows():
    bridge = MAIN.split("def _backfill_legacy_deadline_jobs_if_needed", 1)[1].split("def _cleanup_consultation_deadline_jobs", 1)[0]
    assert "ConsultationDeadlineJob.id).limit(1)" not in bridge
    assert '("REQUESTED", "EXPERT_RESPONSE"' in bridge
    assert "_enqueue_deadline_pair" in bridge


def test_deadline_and_user_state_transitions_lock_case_row_on_postgres():
    processor = MAIN.split("def _process_deadline_job", 1)[1].split("def _process_consultation_deadline_jobs", 1)[0]
    assert "case_stmt.with_for_update()" in processor
    for endpoint_name in (
        "def expert_support_expert_response",
        "def expert_support_proposal_decision",
        "def expert_support_complete",
    ):
        endpoint = MAIN.split(endpoint_name, 1)[1].split("@app.", 1)[0]
        assert "case_stmt.with_for_update()" in endpoint


def test_completion_due_auto_completes_after_24h_and_keeps_actor_distinction():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    original_engine = main.engine
    main.engine = engine
    try:
        with Session(engine, expire_on_commit=False) as session:
            case = _case(session, status="EXPERT_COMPLETED")
            deadline = main._utcnow_naive() - main.timedelta(seconds=1)
            case.expert_completed_at = deadline - main.timedelta(hours=24)
            case.completion_confirmation_deadline = deadline
            session.add(case)
            main._enqueue_deadline_pair(session, case.id, "COMPLETION", deadline)
            session.commit()
            job = session.exec(select(main.ConsultationDeadlineJob).where(
                main.ConsultationDeadlineJob.case_id == case.id,
                main.ConsultationDeadlineJob.job_type == "COMPLETION_DUE",
            )).first()
            notices, events = main._process_deadline_job(session, job, deadline + main.timedelta(seconds=1))
            session.commit()
            session.refresh(case)
            assert case.status == "COMPLETED"
            assert case.completed_at is not None
            assert case.requester_completed_at is None
            audit = session.exec(select(main.ConsultationEvent).where(
                main.ConsultationEvent.case_id == case.id,
                main.ConsultationEvent.event_type == "COMPLETION_AUTO_CONFIRMED",
            )).first()
            assert audit is not None
            assert {event.user_id for event in events} == {case.requester_user_id, case.expert_user_id}
            assert notices
    finally:
        main.engine = original_engine


def test_completion_deadline_is_stale_after_requester_decision():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    original_engine = main.engine
    main.engine = engine
    try:
        with Session(engine, expire_on_commit=False) as session:
            case = _case(session, status="EXPERT_COMPLETED")
            deadline = main._utcnow_naive() - main.timedelta(seconds=1)
            case.completion_confirmation_deadline = deadline
            session.add(case)
            main._enqueue_deadline_pair(session, case.id, "COMPLETION", deadline)
            session.flush()
            job = session.exec(select(main.ConsultationDeadlineJob).where(
                main.ConsultationDeadlineJob.case_id == case.id,
                main.ConsultationDeadlineJob.job_type == "COMPLETION_DUE",
            )).first()
            case.status = "ACTIVE"
            session.add(case)
            session.flush()
            notices, events = main._process_deadline_job(session, job, deadline + main.timedelta(seconds=1))
            assert notices == []
            assert events == []
            assert case.status == "ACTIVE"
    finally:
        main.engine = original_engine
