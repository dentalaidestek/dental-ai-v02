"""Consultation entry must use current eligibility and create once on retries."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event, get_ident
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select

from app import main
from app.expert_consultation_requests import ConsultationRequestReceipt
from test_postgres import pg_engine


@pytest.fixture
def entry_env(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "entry.db"),
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setenv("IYZICO_PAYMENTS_ENABLED", "0")
    seed_entry(engine)
    client = entry_client()
    yield client, engine
    client.close()
    engine.dispose()


def seed_entry(engine):
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for user_id in (1, 2, 3):
            session.add(main.User(
                id=user_id, username=f"entry-{user_id}", role="DOCTOR",
                display_name=f"Hekim {user_id}", email_verified_at=main._utcnow_naive(),
            ))
            session.add(main.SessionToken(
                token_hash=main.hash_session_token(f"entry-token-{user_id}"), user_id=user_id,
                expires_at=main._utcnow_naive() + timedelta(days=1),
            ))
        session.add(main.ExpertProfile(
            user_id=2, specialty="Endodonti", application_status="APPROVED",
            verification_status="VERIFIED", specialty_verified=True,
            credential_document_path="private/credential.pdf", phone="05300000000",
            availability="AVAILABLE", consultation_price=400, max_active_cases=2,
        ))
        session.add(main.ExpertPolicyState(
            expert_user_id=2, rules_version=main.EXPERT_RULES_VERSION,
            rules_accepted_at=main._utcnow_naive(),
        ))
        session.add(main.Patient(
            id=10, owner_user_id=1, anonymous_id="requester-patient", first_name="A", last_name="B",
        ))
        session.add(main.Patient(
            id=11, owner_user_id=3, anonymous_id="other-patient", first_name="C", last_name="D",
        ))
        session.commit()


def entry_client(*, include_social=False):
    api = FastAPI()
    api.get("/expert-support/expert/{expert_user_id}")(main.expert_support_public_profile)
    api.get("/expert-support/request/{expert_user_id}")(main.expert_support_request_page)
    api.post("/expert-support/request/{expert_user_id}")(main.expert_support_request_create)
    if include_social:
        from app.expert_social_api import register
        register(api, main)
    client = TestClient(api, follow_redirects=False)
    client.cookies.set(main.SESSION_COOKIE, "entry-token-1")
    return client


def form(**overrides):
    return {
        "clinical_summary": "Kısa klinik bilgi", "question": "Tedavi seçeneği nedir?",
        "requester_opinion": "Ön değerlendirme", "tooth_region": "46",
        "patient_id": "10", "urgency": "NORMAL", **overrides,
    }


def counts(engine):
    with Session(engine) as session:
        return tuple(len(session.exec(select(model)).all()) for model in (
            main.ConsultationCase, main.ConsultationPayment, main.AdminNotice,
        ))


@pytest.mark.parametrize("keyed", [True, False])
def test_repeated_request_creates_one_case_payment_and_notice(entry_env, keyed):
    client, engine = entry_env
    body = form(**({"request_key": str(uuid4())} if keyed else {}))
    first = client.post("/expert-support/request/2", data=body)
    second = client.post("/expert-support/request/2", data=body)
    assert first.status_code == second.status_code == 303
    assert second.headers["location"] == first.headers["location"]
    assert counts(engine) == (1, 1, 1)
    with Session(engine) as session:
        case = session.exec(select(main.ConsultationCase)).one()
        payment = session.exec(select(main.ConsultationPayment)).one()
        deadlines = session.exec(select(main.ConsultationDeadlineJob)).all()
        requested = session.exec(select(main.ConsultationEvent).where(
            main.ConsultationEvent.event_type == "REQUESTED",
        )).all()
        assert case.status == "REQUESTED" and case.price_amount == 400
        assert case.expert_response_deadline > case.requested_at
        assert payment.case_id == case.id and payment.status == "INTEGRATION_PENDING"
        assert len(deadlines) == 2 and len(requested) == 1


def test_request_key_cannot_be_reused_for_a_different_payload(entry_env):
    client, engine = entry_env
    key = str(uuid4())
    assert client.post("/expert-support/request/2", data=form(request_key=key)).status_code == 303
    changed = client.post("/expert-support/request/2", data=form(request_key=key, question="Farklı soru"))
    assert changed.status_code == 409
    assert counts(engine) == (1, 1, 1)


def test_retry_redirects_to_its_case_after_expert_becomes_busy(entry_env):
    client, engine = entry_env
    body = form(request_key=str(uuid4()))
    first = client.post("/expert-support/request/2", data=body)
    with Session(engine) as session:
        profile = session.exec(select(main.ExpertProfile)).one()
        profile.availability = "BUSY"
        session.add(profile)
        session.commit()
    repeated = client.post("/expert-support/request/2", data=body)
    assert repeated.status_code == 303
    assert repeated.headers["location"] == first.headers["location"]
    assert counts(engine) == (1, 1, 1)


@pytest.mark.parametrize("change", [
    {"is_active": False}, {"role": "STUDENT"},
])
def test_ineligible_target_is_not_public_or_requestable(entry_env, change):
    client, engine = entry_env
    with Session(engine) as session:
        expert = session.get(main.User, 2)
        for key, value in change.items():
            setattr(expert, key, value)
        session.add(expert)
        session.commit()
    assert client.get("/expert-support/expert/2").status_code == 404
    assert client.get("/expert-support/request/2").status_code == 409
    assert client.post("/expert-support/request/2", data=form()).status_code == 409
    assert counts(engine) == (0, 0, 0)


def test_approved_active_admin_expert_remains_requestable(entry_env):
    client, engine = entry_env
    with Session(engine) as session:
        expert = session.get(main.User, 2)
        expert.role = "ADMIN"
        session.add(expert)
        session.commit()
    profile = client.get("/expert-support/expert/2")
    assert profile.status_code == 200 and profile.context.get("support_available") is True
    assert client.get("/expert-support/request/2").status_code == 200
    assert client.post("/expert-support/request/2", data=form(request_key=str(uuid4()))).status_code == 303
    assert counts(engine) == (1, 1, 1)


@pytest.mark.parametrize("change", [
    {"application_status": "SUBMITTED"}, {"verification_status": "PENDING"},
    {"specialty_verified": False}, {"credential_document_path": ""}, {"phone": ""},
])
def test_unverified_target_is_not_public_or_requestable(entry_env, change):
    client, engine = entry_env
    with Session(engine) as session:
        profile = session.exec(select(main.ExpertProfile)).one()
        for key, value in change.items():
            setattr(profile, key, value)
        session.add(profile)
        session.commit()
    assert client.get("/expert-support/expert/2").status_code == 404
    assert client.get("/expert-support/request/2").status_code == 409
    assert client.post("/expert-support/request/2", data=form()).status_code == 409
    assert counts(engine) == (0, 0, 0)


@pytest.mark.parametrize("blocker,blocked", [(1, 2), (2, 1)])
def test_blocks_apply_in_both_directions_to_profile_and_request(entry_env, blocker, blocked):
    client, engine = entry_env
    with Session(engine) as session:
        session.add(main.UserBlock(blocker_user_id=blocker, blocked_user_id=blocked))
        session.commit()
    assert client.get("/expert-support/expert/2").status_code == 404
    assert client.get("/expert-support/request/2").status_code == 409
    assert client.post("/expert-support/request/2", data=form()).status_code == 409
    assert counts(engine) == (0, 0, 0)


@pytest.mark.parametrize("reason", ["BUSY", "POLICY", "CAPACITY"])
def test_support_cta_and_request_entry_share_availability_gate(entry_env, reason):
    client, engine = entry_env
    with Session(engine) as session:
        if reason == "BUSY":
            profile = session.exec(select(main.ExpertProfile)).one()
            profile.availability = "BUSY"
            session.add(profile)
        elif reason == "POLICY":
            policy = session.exec(select(main.ExpertPolicyState)).one()
            policy.new_case_blocked_until = main._utcnow_naive() + timedelta(hours=1)
            session.add(policy)
        else:
            for status in ("ACTIVE", "WAITING_START"):
                session.add(main.ConsultationCase(
                    requester_user_id=1, expert_user_id=2, specialty="Endodonti",
                    clinical_summary="Mevcut", question="Soru", status=status,
                    expert_response_deadline=main._utcnow_naive() + timedelta(minutes=10),
                ))
        session.commit()
    profile_response = client.get("/expert-support/expert/2")
    assert profile_response.status_code == 200
    assert profile_response.context.get("support_available") is False
    assert client.get("/expert-support/request/2").status_code == 409
    assert client.post("/expert-support/request/2", data=form()).status_code == 409


def test_available_request_page_supplies_a_new_uuid_per_render(entry_env):
    client, _ = entry_env
    profile = client.get("/expert-support/expert/2")
    first = client.get("/expert-support/request/2?patient_id=10")
    second = client.get("/expert-support/request/2")
    assert profile.context.get("support_available") is True
    key = first.context.get("request_key")
    assert isinstance(key, str) and str(UUID(key)) == key
    assert second.context.get("request_key") != key
    assert first.context["patient"].id == 10


def test_self_request_stays_400_and_own_profile_has_no_support_cta(entry_env):
    client, engine = entry_env
    client.cookies.set(main.SESSION_COOKIE, "entry-token-2")
    profile = client.get("/expert-support/expert/2")
    assert profile.status_code == 200 and profile.context.get("support_available") is False
    assert client.get("/expert-support/request/2").status_code == 400
    assert client.post("/expert-support/request/2", data=form()).status_code == 400
    assert counts(engine) == (0, 0, 0)


def test_patient_idor_is_rejected_before_case_or_receipt_creation(entry_env):
    client, engine = entry_env
    response = client.post("/expert-support/request/2", data=form(patient_id="11", request_key=str(uuid4())))
    assert response.status_code == 403
    assert counts(engine) == (0, 0, 0)


@pytest.mark.parametrize("key", ["broken", "x" * 1000])
def test_malformed_request_key_is_rejected_without_side_effects(entry_env, key):
    client, engine = entry_env
    assert client.post("/expert-support/request/2", data=form(request_key=key)).status_code == 400
    assert counts(engine) == (0, 0, 0)


@pytest.mark.parametrize("change", [
    {"patient_id": ""}, {"urgency": "ASAP"}, {"media_ids": "123"},
])
def test_request_key_hash_covers_patient_urgency_and_media(entry_env, change):
    client, engine = entry_env
    key = str(uuid4())
    assert client.post("/expert-support/request/2", data=form(request_key=key)).status_code == 303
    assert client.post("/expert-support/request/2", data=form(request_key=key, **change)).status_code == 409
    assert counts(engine) == (1, 1, 1)


def test_receipts_are_scoped_to_both_participants_and_do_not_copy_clinical_text(entry_env):
    client, engine = entry_env
    key = str(uuid4())
    first = client.post("/expert-support/request/2", data=form(request_key=key))
    client.cookies.set(main.SESSION_COOKIE, "entry-token-3")
    second = client.post("/expert-support/request/2", data=form(request_key=key, patient_id=""))
    assert first.status_code == second.status_code == 303
    assert first.headers["location"] != second.headers["location"]
    with Session(engine) as session:
        session.add(main.ExpertProfile(
            user_id=3, specialty="Endodonti", application_status="APPROVED",
            verification_status="VERIFIED", specialty_verified=True,
            credential_document_path="private/other.pdf", phone="05300000000",
            availability="AVAILABLE",
        ))
        session.commit()
    client.cookies.set(main.SESSION_COOKIE, "entry-token-1")
    third = client.post("/expert-support/request/3", data=form(request_key=key))
    assert third.status_code == 303
    assert third.headers["location"] not in {first.headers["location"], second.headers["location"]}
    assert counts(engine) == (3, 3, 3)
    with Session(engine) as session:
        receipts = session.exec(select(ConsultationRequestReceipt)).all()
        assert len(receipts) == 3
        assert {(r.requester_user_id, r.expert_user_id) for r in receipts} == {(1, 2), (3, 2), (1, 3)}
        assert all(len(r.payload_hash) == 64 and r.request_key == key for r in receipts)
        assert all("Kısa klinik bilgi" not in str(r.model_dump()) for r in receipts)
        session.add(ConsultationRequestReceipt(
            requester_user_id=1, expert_user_id=2, request_key=key,
            payload_hash="a" * 64, case_id=999,
        ))
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("changed", ["OLD", "NO_LONGER_PENDING"])
def test_legacy_dedup_does_not_suppress_a_new_intent_after_its_short_window(entry_env, changed):
    client, engine = entry_env
    first = client.post("/expert-support/request/2", data=form())
    with Session(engine) as session:
        if changed == "OLD":
            receipt = session.exec(select(ConsultationRequestReceipt)).one()
            receipt.created_at -= timedelta(minutes=3)
            session.add(receipt)
        else:
            case = session.exec(select(main.ConsultationCase)).one()
            case.status = "PROPOSED"
            session.add(case)
        session.commit()
    second = client.post("/expert-support/request/2", data=form())
    assert first.status_code == second.status_code == 303
    assert first.headers["location"] != second.headers["location"]
    assert counts(engine) == (2, 2, 2)


def test_request_and_receipt_roll_back_together_if_notification_write_fails(entry_env, monkeypatch):
    client, engine = entry_env
    notify = main._notify_user

    def fail_after_notice(*args, **kwargs):
        notify(*args, **kwargs)
        raise RuntimeError("transaction interrupted")

    monkeypatch.setattr(main, "_notify_user", fail_after_notice)
    with pytest.raises(RuntimeError, match="transaction interrupted"):
        client.post("/expert-support/request/2", data=form(request_key=str(uuid4())))
    assert counts(engine) == (0, 0, 0)
    with Session(engine) as session:
        assert session.exec(select(ConsultationRequestReceipt)).all() == []
        assert session.exec(select(main.ConsultationDeadlineJob)).all() == []
        assert session.exec(select(main.ConsultationEvent)).all() == []


@pytest.mark.parametrize("keyed", [True, False])
def test_postgres_concurrent_request_retries_create_once(pg_engine, monkeypatch, keyed):
    seed_entry(pg_engine)
    monkeypatch.setattr(main, "engine", pg_engine)
    monkeypatch.setenv("IYZICO_PAYMENTS_ENABLED", "0")
    body = form(**({"request_key": str(uuid4())} if keyed else {}))

    def submit(_):
        with entry_client() as client:
            return client.post("/expert-support/request/2", data=body)

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(submit, range(4)))
    assert [response.status_code for response in responses] == [303] * 4
    assert len({response.headers["location"] for response in responses}) == 1
    assert counts(pg_engine) == (1, 1, 1)
    with Session(pg_engine) as session:
        assert len(session.exec(select(ConsultationRequestReceipt)).all()) == 1
        assert len(session.exec(select(main.ConsultationDeadlineJob)).all()) == 2


def seed_performance_history(engine, now):
    requested = now - timedelta(days=1)
    rows = [
        {"status": "COMPLETED", "proposed_at": requested + timedelta(seconds=60),
         "requester_accepted_at": requested + timedelta(seconds=1), "expert_started_at": requested + timedelta(seconds=2)},
        {"status": "COMPLETED", "requester_accepted_at": requested + timedelta(seconds=120),
         "expert_started_at": requested + timedelta(seconds=1)},
        {"status": "ACTIVE", "expert_started_at": requested + timedelta(seconds=300)},
        {"status": "WAITING_START"},
        {"status": "EXPERT_TIMEOUT", "requested_at": now - timedelta(days=30)},
        {"status": "EXPERT_TIMEOUT", "requested_at": now - timedelta(days=29),
         "proposed_at": now - timedelta(days=29, seconds=1),
         "requester_accepted_at": now - timedelta(days=29) + timedelta(seconds=600)},
        {"status": "EXPERT_TIMEOUT", "requested_at": now - timedelta(days=31)},
        {"status": "REJECTED", "proposed_at": requested},
        {"status": "COMPLETED"},
    ]
    with Session(engine) as session:
        cases = []
        for row in rows:
            case = main.ConsultationCase(
                requester_user_id=1, expert_user_id=2, specialty="Endodonti",
                clinical_summary="Kısa bilgi", question="Soru",
                expert_response_deadline=now + timedelta(minutes=10),
                **{"requested_at": requested, **row},
            )
            session.add(case)
            cases.append(case)
        unrelated = main.ConsultationCase(
            requester_user_id=1, expert_user_id=3, specialty="Endodonti",
            clinical_summary="Diğer uzman", question="Soru", status="COMPLETED",
            requested_at=requested, proposed_at=requested + timedelta(hours=9),
            expert_response_deadline=now + timedelta(minutes=10),
        )
        session.add(unrelated)
        session.flush()
        for case, rating in zip(cases, (4, 5, 1)):
            session.add(main.ExpertReview(case_id=case.id, reviewer_user_id=1, expert_user_id=2, rating=rating))
        session.add(main.ExpertReview(case_id=unrelated.id, reviewer_user_id=1, expert_user_id=3, rating=5))
        session.commit()


EXPECTED_PERFORMANCE = {
    "rating_avg": 3.3, "review_count": 3, "completed_count": 3,
    "avg_response_minutes": 2.0, "missed_30": 2,
}


def assert_aggregated_performance(engine, monkeypatch):
    now = datetime(2026, 11, 7, 12, 0, 0)
    monkeypatch.setattr(main, "_utcnow_naive", lambda: now)
    seed_performance_history(engine, now)
    loaded = []
    with Session(engine) as session:
        event.listen(session, "loaded_as_persistent", lambda _, obj: loaded.append(type(obj).__name__))
        assert main._expert_performance(session, 2) == EXPECTED_PERFORMANCE
        assert main._expert_performance(session, 999) == {
            "rating_avg": None, "review_count": 0, "completed_count": 0,
            "avg_response_minutes": None, "missed_30": 0,
        }
    assert loaded == [], "Aggregate statistics must not hydrate case/review histories"


def test_performance_aggregates_mixed_history_without_loading_entities(entry_env, monkeypatch):
    _, engine = entry_env
    assert_aggregated_performance(engine, monkeypatch)


def test_postgres_performance_aggregates_mixed_history_without_loading_entities(pg_engine, monkeypatch):
    seed_entry(pg_engine)
    assert_aggregated_performance(pg_engine, monkeypatch)


def test_public_profile_uses_aggregate_counts_and_still_renders(entry_env, monkeypatch):
    client, engine = entry_env
    now = datetime(2026, 11, 7, 12, 0, 0)
    monkeypatch.setattr(main, "_utcnow_naive", lambda: now)
    seed_performance_history(engine, now)
    loaded = []

    def capture_history(_, obj):
        if isinstance(obj, (main.ConsultationCase, main.ExpertReview)):
            loaded.append(type(obj).__name__)

    event.listen(Session, "loaded_as_persistent", capture_history)
    try:
        response = client.get("/expert-support/expert/2")
    finally:
        event.remove(Session, "loaded_as_persistent", capture_history)
    assert response.status_code == 200
    assert response.context["performance"] == EXPECTED_PERFORMANCE
    assert response.context["completed_count"] == 3
    assert response.context["review_count"] == 3 and response.context["rating_avg"] == 3.3
    assert "3.3/5" in response.text
    assert loaded == [], "Rendering statistics must not load case/review histories"


@pytest.mark.parametrize("elapsed,expected", [(timedelta(seconds=3), 0.1), (timedelta(microseconds=2999999), 0.0)])
def test_response_duration_rounding_preserves_fractional_seconds(entry_env, elapsed, expected):
    _, engine = entry_env
    requested = datetime(2026, 11, 6, 12, 0, 0, 123456)
    with Session(engine) as session:
        session.add(main.ConsultationCase(
            requester_user_id=1, expert_user_id=2, specialty="Endodonti",
            clinical_summary="Kısa bilgi", question="Soru", requested_at=requested,
            proposed_at=requested + elapsed, expert_response_deadline=requested + timedelta(minutes=10),
        ))
        session.commit()
    with Session(engine) as session:
        assert main._expert_performance(session, 2)["avg_response_minutes"] == expected


@pytest.mark.parametrize("erased_user_id,expected_status", [(1, 303), (2, 409)])
def test_postgres_request_waits_for_account_erasure_before_profile_allocation(
    pg_engine, monkeypatch, erased_user_id, expected_status,
):
    from app.account_erasure import begin_account_erasure

    seed_entry(pg_engine)
    monkeypatch.setattr(main, "engine", pg_engine)
    monkeypatch.setenv("IYZICO_PAYMENTS_ENABLED", "0")
    account_locked, first_request_lock = Event(), Event()
    profile_locked, allow_request, allow_erasure = Event(), Event(), Event()
    erasure_thread, request_locks = [], []

    def before_query(_, __, statement, ___, ____, _____):
        if erasure_thread and get_ident() == erasure_thread[0]:
            return
        if "FOR UPDATE" in statement or "FOR KEY SHARE" in statement:
            request_locks.append(statement)
            first_request_lock.set()

    def after_query(_, __, statement, ___, ____, _____):
        if erasure_thread and get_ident() == erasure_thread[0]:
            return
        if "expertprofile" in statement and "FOR UPDATE" in statement:
            profile_locked.set()
            assert allow_request.wait(5)

    def erase():
        erasure_thread.append(get_ident())
        try:
            with Session(pg_engine) as session:
                session.exec(text("SET LOCAL lock_timeout = '4s'"))
                session.exec(select(main.User).where(main.User.id == erased_user_id).with_for_update()).one()
                account_locked.set()
                assert allow_erasure.wait(5)
                begin_account_erasure(session, user_id=erased_user_id, actor="user")
                session.commit()
            return "erased"
        except Exception as error:
            return error

    def submit():
        try:
            with entry_client() as client:
                return client.post("/expert-support/request/2", data=form(request_key=str(uuid4())))
        except Exception as error:
            return error

    event.listen(pg_engine, "before_cursor_execute", before_query)
    event.listen(pg_engine, "after_cursor_execute", after_query)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            erasing = pool.submit(erase)
            assert account_locked.wait(5)
            requesting = pool.submit(submit)
            assert first_request_lock.wait(5)
            if "expertprofile" in request_locks[0]:
                assert profile_locked.wait(5)
            allow_request.set()
            allow_erasure.set()
            request_result = requesting.result(timeout=10)
            erasure_result = erasing.result(timeout=10)
    finally:
        allow_request.set()
        allow_erasure.set()
        event.remove(pg_engine, "before_cursor_execute", before_query)
        event.remove(pg_engine, "after_cursor_execute", after_query)
    assert erasure_result == "erased", repr(erasure_result)
    assert not isinstance(request_result, Exception), repr(request_result)
    assert request_result.status_code == expected_status
    if erased_user_id == 1:
        assert request_result.headers["location"] == "/login"
    assert 'FROM "user"' in request_locks[0] and "FOR KEY SHARE" in request_locks[0]
    assert "ORDER BY" in request_locks[0]
    assert counts(pg_engine) == (0, 0, 0)
    with Session(pg_engine) as session:
        assert session.get(main.User, erased_user_id).is_active is False
        assert session.exec(select(ConsultationRequestReceipt)).all() == []


def test_postgres_participant_key_locks_allow_concurrent_expert_social_post(pg_engine, monkeypatch):
    from app.expert_social_models import SocialPost

    seed_entry(pg_engine)
    monkeypatch.setattr(main, "engine", pg_engine)
    monkeypatch.setenv("IYZICO_PAYMENTS_ENABLED", "0")
    social_profile_locked, request_waiting_for_profile, allow_social = Event(), Event(), Event()
    social_connection = []

    def after_query(connection, _, statement, __, ___, ____):
        if "expertprofile" in statement and "FOR UPDATE" in statement and not social_connection:
            social_connection.append(id(connection))
            social_profile_locked.set()
            assert allow_social.wait(5)

    def before_query(connection, _, statement, __, ___, ____):
        if (social_connection and id(connection) != social_connection[0]
                and "expertprofile" in statement and "FOR UPDATE" in statement):
            request_waiting_for_profile.set()

    def publish():
        client = entry_client(include_social=True)
        client.cookies.set(main.SESSION_COOKIE, "entry-token-2")
        client.headers.update({"Origin": "http://testserver", "X-Dental-Social": "1"})
        try:
            return client.post("/api/expert-social/posts", json={
                "text": "Bilimsel bir paylaşım", "idempotency_key": str(uuid4()),
            })
        except Exception as error:
            return error
        finally:
            client.close()

    def submit():
        with entry_client() as client:
            try:
                return client.post("/expert-support/request/2", data=form(request_key=str(uuid4())))
            except Exception as error:
                return error

    event.listen(pg_engine, "before_cursor_execute", before_query)
    event.listen(pg_engine, "after_cursor_execute", after_query)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            publishing = pool.submit(publish)
            assert social_profile_locked.wait(5)
            requesting = pool.submit(submit)
            assert request_waiting_for_profile.wait(5)
            allow_social.set()
            post_result = publishing.result(timeout=10)
            request_result = requesting.result(timeout=10)
    finally:
        allow_social.set()
        event.remove(pg_engine, "before_cursor_execute", before_query)
        event.remove(pg_engine, "after_cursor_execute", after_query)
    assert not isinstance(post_result, Exception), repr(post_result)
    assert not isinstance(request_result, Exception), repr(request_result)
    assert post_result.status_code == 200, post_result.text
    assert request_result.status_code == 303, request_result.text
    assert counts(pg_engine) == (1, 1, 1)
    with Session(pg_engine) as session:
        assert len(session.exec(select(SocialPost)).all()) == 1
        assert len(session.exec(select(ConsultationRequestReceipt)).all()) == 1
