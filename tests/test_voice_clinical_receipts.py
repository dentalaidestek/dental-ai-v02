from datetime import datetime, timedelta, timezone
import hashlib

import pytest
from sqlalchemy.orm import registry
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Field, Session, create_engine, select

from app.work_jobs import WorkJob as ProductionWorkJob
from app import voice_clinical_receipts as receipts

receipt_registry = registry()


class ReceiptTestModel(SQLModel, registry=receipt_registry):
    pass


class WorkJob:
    pass


receipt_registry.map_imperatively(
    WorkJob, ProductionWorkJob.__table__.to_metadata(ReceiptTestModel.metadata)
)


class User(ReceiptTestModel, table=True):
    id: int | None = Field(default=None, primary_key=True)


class Patient(ReceiptTestModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int


@pytest.fixture
def receipt_db(monkeypatch):
    monkeypatch.setattr(receipts, "WorkJob", WorkJob)
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    ReceiptTestModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            User(id=1), User(id=2),
            Patient(id=10, owner_user_id=1), Patient(id=11, owner_user_id=1),
            Patient(id=12, owner_user_id=2),
        ])
        session.commit()
    yield engine
    engine.dispose()


KEY = bytes.fromhex("11" * 32)
STAMP = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
REQUEST = "session_1234567890_chunk_0"
REVISION = "b" * 64
TRANSCRIPT = "Synthetic clinical transcript must remain encrypted."
REVIEW = {"fields": {"chief_complaint": {"value": "Synthetic pain", "quote": "Synthetic quote"}}, "teeth": []}
RAW_MARKERS = ("Synthetic clinical transcript", "Synthetic pain", "Synthetic quote")


def digest(transcript=TRANSCRIPT, context=None):
    return receipts.clinical_input_digest(transcript, context or {}, KEY)


def reserve(session, *, owner=1, patient=10, request=REQUEST, input_digest=None, now=STAMP):
    return receipts.reserve_receipt(
        session, owner_id=owner, patient_id=patient, request_key=request,
        digest=input_digest or digest(), key=KEY, now=now,
    )


def complete(session, claim, *, owner=1, patient=10, request=REQUEST, input_digest=None, now=STAMP + timedelta(seconds=1)):
    return receipts.complete_receipt(
        session, owner_id=owner, patient_id=patient, request_key=request,
        digest=input_digest or digest(), lease_token=claim["lease_token"],
        key=KEY, review=REVIEW, revision=REVISION, now=now,
    )


def test_completed_review_replays_from_aes_gcm_without_plaintext_storage(receipt_db):
    with Session(receipt_db) as session:
        claim = reserve(session)
        assert claim["state"] == "CLAIMED"
        session.commit()
    with Session(receipt_db) as session:
        assert complete(session, claim)
        session.commit()
    with Session(receipt_db) as session:
        replay = reserve(session, now=STAMP + timedelta(minutes=1))
        assert replay == {
            "state": "REPLAY",
            "dedupe_key": receipts.receipt_dedupe_key(1, 10, REQUEST),
            "review": REVIEW,
            "revision": REVISION,
        }
        row = session.exec(select(WorkJob)).one()
        assert row.status == "DONE"
        assert all(marker not in row.payload_json for marker in RAW_MARKERS)
        assert row.payload_json != "{}"


def test_same_request_key_with_changed_transcript_or_context_is_rejected(receipt_db):
    first_digest = digest()
    with Session(receipt_db) as session:
        claim = reserve(session, input_digest=first_digest)
        session.commit()
    with Session(receipt_db) as session:
        with pytest.raises(receipts.ReceiptConflict):
            reserve(session, input_digest=digest("Changed transcript"))
        row = session.exec(select(WorkJob)).one()
        assert row.lease_token == claim["lease_token"]
        assert row.attempts == 1
    with Session(receipt_db) as session:
        with pytest.raises(receipts.ReceiptConflict):
            reserve(session, input_digest=digest(context={"fields": {"allergies": "changed"}}))


def test_same_request_key_isolated_by_account_and_patient(receipt_db):
    with Session(receipt_db) as session:
        one = reserve(session, owner=1, patient=10)
        two = reserve(session, owner=2, patient=12)
        three = reserve(session, owner=1, patient=11)
        session.commit()
        assert len({one["dedupe_key"], two["dedupe_key"], three["dedupe_key"]}) == 3
        assert len(session.exec(select(WorkJob)).all()) == 3


def test_processing_receipt_is_busy_and_does_not_claim_a_second_provider_call(receipt_db):
    with Session(receipt_db) as session:
        first = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        second = reserve(session, now=STAMP + timedelta(seconds=20))
        session.commit()
        assert second["state"] == "PROCESSING"
        row = session.exec(select(WorkJob)).one()
        assert row.lease_token == first["lease_token"]
        assert row.attempts == 1


def test_expired_provider_lease_is_terminal_unknown_not_reclaimed(receipt_db):
    with Session(receipt_db) as session:
        first = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        unknown = reserve(session, now=STAMP + timedelta(seconds=receipts.LEASE_SECONDS + 1))
        session.commit()
        assert unknown["state"] == "UNKNOWN"
        row = session.exec(select(WorkJob)).one()
        assert row.status == "FAILED"
        assert row.payload_json == receipts.TOMBSTONE
        assert row.lease_token is None
    with Session(receipt_db) as session:
        again = reserve(session, now=STAMP + timedelta(minutes=5))
        assert again["state"] == "UNKNOWN"
        assert session.exec(select(WorkJob)).one().attempts == 1


def test_done_receipt_expires_ciphertext_after_24_hours(receipt_db):
    with Session(receipt_db) as session:
        claim = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        assert complete(session, claim)
        session.commit()
    with Session(receipt_db) as session:
        expired = reserve(session, now=STAMP + timedelta(hours=25))
        session.commit()
        row = session.exec(select(WorkJob)).one()
        assert expired["state"] == "EXPIRED"
        assert row.status == "EXPIRED"
        assert row.payload_json == receipts.TOMBSTONE


def test_only_known_pre_provider_failure_can_retry_same_key(receipt_db):
    with Session(receipt_db) as session:
        claim = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        assert receipts.finish_receipt(
            session, owner_id=1, patient_id=10, request_key=REQUEST,
            digest=digest(), lease_token=claim["lease_token"], retryable=True,
            now=STAMP + timedelta(seconds=1),
        )
        session.commit()
    with Session(receipt_db) as session:
        retry = reserve(session, now=STAMP + timedelta(seconds=2))
        session.commit()
        assert retry["state"] == "CLAIMED"
        assert retry["lease_token"] != claim["lease_token"]
        assert session.exec(select(WorkJob)).one().attempts == 2


def test_unknown_provider_failure_is_not_retryable(receipt_db):
    with Session(receipt_db) as session:
        claim = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        receipts.finish_receipt(
            session, owner_id=1, patient_id=10, request_key=REQUEST,
            digest=digest(), lease_token=claim["lease_token"], retryable=False,
            now=STAMP + timedelta(seconds=1),
        )
        session.commit()
    with Session(receipt_db) as session:
        assert reserve(session, now=STAMP + timedelta(seconds=2))["state"] == "UNKNOWN"
        assert session.exec(select(WorkJob)).one().attempts == 1


def test_tampered_encrypted_review_fails_closed(receipt_db):
    with Session(receipt_db) as session:
        claim = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        assert complete(session, claim)
        session.commit()
    with Session(receipt_db) as session:
        row = session.exec(select(WorkJob)).one()
        row.payload_json = row.payload_json.replace('"ciphertext":"', '"ciphertext":"AA')
        session.add(row)
        session.commit()
    with Session(receipt_db) as session:
        with pytest.raises(receipts.ReceiptCorrupt):
            reserve(session, now=STAMP + timedelta(minutes=1))


def test_lost_or_expired_lease_cannot_complete_receipt(receipt_db):
    with Session(receipt_db) as session:
        claim = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        assert not complete(session, claim, now=STAMP + timedelta(seconds=receipts.LEASE_SECONDS + 1))
        session.rollback()
        assert session.exec(select(WorkJob)).one().status == "PROCESSING"


def test_expiry_worker_erases_old_results_stale_leases_and_deleted_patients(receipt_db):
    with Session(receipt_db) as session:
        session.add_all([
            WorkJob(owner_user_id=1, resource_id=10, resource_type="PATIENT",
                kind=receipts.KIND, source_hash="d" * 64, dedupe_key="1" * 64,
                payload_json="encrypted", status="DONE", created_at=STAMP - timedelta(hours=25),
                updated_at=STAMP - timedelta(hours=25)),
            WorkJob(owner_user_id=1, resource_id=11, resource_type="PATIENT",
                kind=receipts.KIND, source_hash="e" * 64, dedupe_key="2" * 64,
                payload_json="encrypted", status="PROCESSING", lease_token="lease",
                lease_until=STAMP - timedelta(seconds=1), created_at=STAMP - timedelta(hours=1),
                updated_at=STAMP - timedelta(hours=1)),
            WorkJob(owner_user_id=2, resource_id=999, resource_type="PATIENT",
                kind=receipts.KIND, source_hash="f" * 64, dedupe_key="3" * 64,
                payload_json="encrypted", status="DONE", created_at=STAMP,
                updated_at=STAMP),
        ])
        session.commit()
    with Session(receipt_db) as session:
        counts = receipts.expire_voice_clinical_receipts(
            session, patient_model=Patient, now=STAMP, limit=100
        )
        session.commit()
        assert counts == {"deleted": 1, "expired": 1, "stale": 1, "pruned": 0}
        rows = session.exec(select(WorkJob).order_by(WorkJob.dedupe_key)).all()
        assert [(row.dedupe_key, row.status) for row in rows] == [
            ("1" * 64, "EXPIRED"), ("2" * 64, "FAILED")
        ]
        assert all(row.payload_json == receipts.TOMBSTONE for row in rows)


def test_input_digest_is_keyed_and_binds_context():
    one = digest()
    assert one == digest()
    assert one != digest("Changed")
    assert one != receipts.clinical_input_digest(TRANSCRIPT, {"fields": {"allergies": "changed"}}, KEY)
    assert one != receipts.clinical_input_digest(TRANSCRIPT, {}, bytes.fromhex("22" * 32))


def test_receipt_key_is_validated_and_dedicated_encryption_key_is_required(monkeypatch):
    assert receipts.receipt_dedupe_key(1, 10, REQUEST)
    with pytest.raises(ValueError):
        receipts.receipt_dedupe_key(1, 10, "short")
    from app.voice_asr_receipts import encryption_key, ReceiptKeyUnavailable
    assert encryption_key("12" * 32) == bytes.fromhex("12" * 32)
    with pytest.raises(ReceiptKeyUnavailable):
        encryption_key("not-a-secret")


def test_missing_claude_configuration_is_typed_before_provider_invocation(monkeypatch):
    from app import voice_exam_core as core
    from app.voice_exam_review_provider import _configuration

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("VOICE_EXAM_CLAUDE_MODEL", "claude-test")
    with pytest.raises(core.VoiceConfigurationError):
        _configuration()
