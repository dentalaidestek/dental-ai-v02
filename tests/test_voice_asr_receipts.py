from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import registry
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Field, Session, create_engine, select

from app.work_jobs import WorkJob as ProductionWorkJob
from app import voice_asr_receipts as receipts


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
        session.add_all([User(id=1), User(id=2)])
        session.commit()
    yield engine
    engine.dispose()


KEY = bytes.fromhex("11" * 32)
STAMP = datetime(2026, 11, 16, 12, 0, 0)
REQUEST = "9d1b45a0-3d25-4d2e-aaf2-74f19c81d89e"
DIGEST = "a" * 64
REVISION = "b" * 64
TRANSCRIPT = "Hasta soğukta kısa süreli ağrı tarif ediyor."
RAW_AUDIO_MARKER = "raw-audio-must-never-be-stored"


def reserve(session, *, owner=1, patient=10, request=REQUEST, digest=DIGEST, now=STAMP):
    return receipts.reserve_receipt(
        session,
        owner_id=owner,
        patient_id=patient,
        request_key=request,
        digest=digest,
        key=KEY,
        now=now,
    )


def test_completed_receipt_replays_encrypted_transcript_without_provider_call(receipt_db):
    with Session(receipt_db) as session:
        first = reserve(session)
        assert first["state"] == "CLAIMED"
        session.commit()

    with Session(receipt_db) as session:
        assert receipts.complete_receipt(
            session,
            owner_id=1,
            patient_id=10,
            request_key=REQUEST,
            digest=DIGEST,
            lease_token=first["lease_token"],
            key=KEY,
            transcript=TRANSCRIPT,
            revision=REVISION,
            now=STAMP + timedelta(seconds=2),
        )
        session.commit()

    with Session(receipt_db) as session:
        replay = reserve(session, now=STAMP + timedelta(minutes=1))
        session.commit()
        assert replay == {
            "state": "REPLAY",
            "dedupe_key": receipts.receipt_dedupe_key(1, 10, REQUEST),
            "transcript": TRANSCRIPT,
            "revision": REVISION,
        }
        row = session.exec(select(WorkJob)).one()
        assert TRANSCRIPT not in row.payload_json
        assert RAW_AUDIO_MARKER not in row.payload_json
        assert row.status == "DONE"


def test_same_key_with_different_audio_is_rejected_before_second_claim(receipt_db):
    with Session(receipt_db) as session:
        first = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        with pytest.raises(receipts.ReceiptConflict):
            reserve(session, digest="c" * 64, now=STAMP + timedelta(seconds=1))
        row = session.exec(select(WorkJob)).one()
        assert row.lease_token == first["lease_token"]
        assert row.attempts == 1


def test_same_segment_key_isolated_by_account_and_patient(receipt_db):
    with Session(receipt_db) as session:
        one = reserve(session, owner=1, patient=10)
        two = reserve(session, owner=2, patient=10)
        three = reserve(session, owner=1, patient=11)
        session.commit()
        assert {one["dedupe_key"], two["dedupe_key"], three["dedupe_key"]}.__len__() == 3
        assert len(session.exec(select(WorkJob)).all()) == 3


def test_live_processing_receipt_is_busy_not_reprocessed(receipt_db):
    with Session(receipt_db) as session:
        first = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        second = reserve(session, now=STAMP + timedelta(seconds=30))
        session.commit()
        assert second["state"] == "PROCESSING"
        row = session.exec(select(WorkJob)).one()
        assert row.lease_token == first["lease_token"]
        assert row.attempts == 1


def test_expired_processing_receipt_becomes_terminal_unknown_not_reclaimed(receipt_db):
    with Session(receipt_db) as session:
        first = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        unknown = reserve(session, now=STAMP + timedelta(seconds=receipts.LEASE_SECONDS + 1))
        session.commit()
        assert unknown["state"] == "UNKNOWN"
        row = session.exec(select(WorkJob)).one()
        assert row.status == "FAILED"
        assert row.lease_token is None
        assert row.payload_json == receipts.TOMBSTONE
    with Session(receipt_db) as session:
        again = reserve(session, now=STAMP + timedelta(minutes=5))
        session.commit()
        assert again["state"] == "UNKNOWN"
        assert session.exec(select(WorkJob)).one().attempts == 1


def test_done_receipt_expires_and_ciphertext_is_cleared_after_24_hours(receipt_db):
    with Session(receipt_db) as session:
        first = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        receipts.complete_receipt(
            session, owner_id=1, patient_id=10, request_key=REQUEST,
            digest=DIGEST, lease_token=first["lease_token"], key=KEY,
            transcript=TRANSCRIPT, revision=REVISION, now=STAMP + timedelta(seconds=1),
        )
        session.commit()
    with Session(receipt_db) as session:
        expired = reserve(session, now=STAMP + timedelta(hours=25))
        session.commit()
        assert expired["state"] == "EXPIRED"
        row = session.exec(select(WorkJob)).one()
        assert row.status == "EXPIRED"
        assert row.payload_json == receipts.TOMBSTONE
        assert TRANSCRIPT not in row.payload_json


def test_known_pre_provider_failure_can_retry_same_key(receipt_db):
    with Session(receipt_db) as session:
        first = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        assert receipts.finish_receipt(
            session, owner_id=1, patient_id=10, request_key=REQUEST,
            digest=DIGEST, lease_token=first["lease_token"], retryable=True,
            now=STAMP + timedelta(seconds=1),
        )
        session.commit()
    with Session(receipt_db) as session:
        retry = reserve(session, now=STAMP + timedelta(seconds=2))
        session.commit()
        assert retry["state"] == "CLAIMED"
        assert retry["lease_token"] != first["lease_token"]
        assert session.exec(select(WorkJob)).one().attempts == 2


def test_tampered_encrypted_receipt_fails_closed(receipt_db):
    with Session(receipt_db) as session:
        first = reserve(session)
        session.commit()
    with Session(receipt_db) as session:
        receipts.complete_receipt(
            session, owner_id=1, patient_id=10, request_key=REQUEST,
            digest=DIGEST, lease_token=first["lease_token"], key=KEY,
            transcript=TRANSCRIPT, revision=REVISION, now=STAMP + timedelta(seconds=1),
        )
        session.commit()
    with Session(receipt_db) as session:
        row = session.exec(select(WorkJob)).one()
        row.payload_json = row.payload_json.replace('"ciphertext":"', '"ciphertext":"AA')
        session.add(row)
        session.commit()
    with Session(receipt_db) as session:
        with pytest.raises(receipts.ReceiptCorrupt):
            reserve(session, now=STAMP + timedelta(minutes=1))


def test_expiry_worker_clears_old_ciphertext_stale_leases_and_prunes_tombstones(receipt_db):
    old = STAMP - timedelta(days=8)
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
            WorkJob(owner_user_id=2, resource_id=12, resource_type="PATIENT",
                kind=receipts.KIND, source_hash="f" * 64, dedupe_key="3" * 64,
                payload_json=receipts.TOMBSTONE, status="EXPIRED",
                created_at=old, updated_at=old),
        ])
        session.commit()
    with Session(receipt_db) as session:
        counts = receipts.expire_voice_asr_receipts(session, now=STAMP, limit=100)
        session.commit()
        assert counts == {"expired": 1, "stale": 1, "pruned": 1}
        rows = session.exec(select(WorkJob).order_by(WorkJob.dedupe_key)).all()
        assert [(row.dedupe_key, row.status) for row in rows] == [
            ("1" * 64, "EXPIRED"), ("2" * 64, "FAILED")
        ]
        assert all(row.payload_json == receipts.TOMBSTONE for row in rows)


def test_receipt_key_is_dedicated_strict_32_byte_hex_secret():
    assert receipts.encryption_key("12" * 32) == bytes.fromhex("12" * 32)
    with pytest.raises(receipts.ReceiptKeyUnavailable):
        receipts.encryption_key("not-a-secret")


def test_voice_capacity_failure_is_typed_as_safe_pre_provider_retry(monkeypatch):
    from app import voice_exam_core as core

    monkeypatch.setenv("GEMINI_API_KEY", "configured")
    monkeypatch.setenv("VOICE_EXAM_GEMINI_MODEL", "gemini-test")
    class BusyCapacity:
        def acquire(self, blocking=False):
            assert blocking is False
            return False
    monkeypatch.setattr(core, "_capacity", BusyCapacity())
    with pytest.raises(core.VoiceBusy):
        core.extract(data=b"bounded-audio", mime="audio/webm", transcription_only=True)


def test_missing_gemini_configuration_is_typed_before_provider_call(monkeypatch):
    from app import voice_exam_core as core

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("VOICE_EXAM_GEMINI_MODEL", "gemini-test")
    with pytest.raises(core.VoiceConfigurationError):
        core.extract(data=b"bounded-audio", mime="audio/webm", transcription_only=True)
