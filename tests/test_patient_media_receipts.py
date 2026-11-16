import json
from types import SimpleNamespace

import pytest

from app.patient_media_receipts import (
    KEY_ENV,
    PatientMediaReceiptConflict,
    PatientMediaReceiptCorrupt,
    PatientMediaReceiptKeyUnavailable,
    encryption_key,
    keyed_fingerprint,
    upgrade_legacy_receipt,
)

KEY = bytes.fromhex("11" * 32)
OWNER_ID = 7
PATIENT_ID = 42
BATCH_ID = "clinical-media-batch-0001"


def receipt(source_hash="a" * 64, *, payload=None):
    payload = payload or {
        "patient_id": PATIENT_ID,
        "media_id": 901,
        "batch_id": BATCH_ID,
        "file_bytes": 2048,
    }
    return SimpleNamespace(
        owner_user_id=OWNER_ID,
        resource_id=PATIENT_ID,
        source_hash=source_hash,
        payload_json=json.dumps(payload),
    )


def test_receipt_key_requires_a_dedicated_32_byte_hex_secret(monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    with pytest.raises(PatientMediaReceiptKeyUnavailable):
        encryption_key()
    monkeypatch.setenv(KEY_ENV, "not-a-secret")
    with pytest.raises(PatientMediaReceiptKeyUnavailable):
        encryption_key()
    monkeypatch.setenv(KEY_ENV, "12" * 32)
    assert encryption_key() == bytes.fromhex("12" * 32)


def test_fingerprint_is_keyed_domain_separated_and_owner_patient_scoped():
    legacy = "a" * 64
    first = keyed_fingerprint(legacy, KEY, OWNER_ID, PATIENT_ID)
    assert len(first) == 64
    assert first != legacy
    assert first == keyed_fingerprint(legacy, KEY, OWNER_ID, PATIENT_ID)
    assert first != keyed_fingerprint(legacy, bytes.fromhex("22" * 32), OWNER_ID, PATIENT_ID)
    assert first != keyed_fingerprint(legacy, KEY, OWNER_ID + 1, PATIENT_ID)
    assert first != keyed_fingerprint(legacy, KEY, OWNER_ID, PATIENT_ID + 1)


def test_legacy_receipt_upgrades_once_without_reading_or_rewriting_media():
    legacy = "a" * 64
    row = receipt(legacy)
    expected = keyed_fingerprint(legacy, KEY, OWNER_ID, PATIENT_ID)
    changed = upgrade_legacy_receipt(
        row, digest=expected, legacy_digest=legacy, key=KEY,
        owner_id=OWNER_ID, patient_id=PATIENT_ID,
    )
    assert changed is True
    assert row.source_hash == expected
    assert row.source_hash != legacy
    assert json.loads(row.payload_json)["fingerprint_version"] == 1

    replay_changed = upgrade_legacy_receipt(
        row, digest=expected, legacy_digest=legacy, key=KEY,
        owner_id=OWNER_ID, patient_id=PATIENT_ID,
    )
    assert replay_changed is False
    assert row.source_hash == expected


def test_legacy_receipt_rejects_different_content_without_mutation():
    row = receipt("a" * 64)
    before_payload = row.payload_json
    with pytest.raises(PatientMediaReceiptConflict):
        upgrade_legacy_receipt(
            row, digest="b" * 64, legacy_digest="b" * 64, key=KEY,
            owner_id=OWNER_ID, patient_id=PATIENT_ID,
        )
    assert row.source_hash == "a" * 64
    assert row.payload_json == before_payload


def test_versioned_receipt_rejects_reused_key_with_different_digest():
    expected = keyed_fingerprint("a" * 64, KEY, OWNER_ID, PATIENT_ID)
    row = receipt(expected, payload={
        "patient_id": PATIENT_ID,
        "media_id": 901,
        "batch_id": BATCH_ID,
        "file_bytes": 2048,
        "fingerprint_version": 1,
    })
    with pytest.raises(PatientMediaReceiptConflict):
        upgrade_legacy_receipt(
            row, digest="c" * 64, legacy_digest="c" * 64, key=KEY,
            owner_id=OWNER_ID, patient_id=PATIENT_ID,
        )


def test_status_lookup_can_key_a_legacy_receipt_without_raw_media():
    legacy = "d" * 64
    row = receipt(legacy)
    expected = keyed_fingerprint(legacy, KEY, OWNER_ID, PATIENT_ID)
    assert upgrade_legacy_receipt(
        row, digest=None, legacy_digest=None, key=KEY,
        owner_id=OWNER_ID, patient_id=PATIENT_ID,
    ) is True
    assert row.source_hash == expected
    assert json.loads(row.payload_json)["fingerprint_version"] == 1


def test_corrupt_legacy_receipt_fails_closed():
    row = receipt("not-a-digest", payload={"patient_id": PATIENT_ID, "media_id": 901})
    with pytest.raises(PatientMediaReceiptCorrupt):
        upgrade_legacy_receipt(
            row, digest=None, legacy_digest=None, key=KEY,
            owner_id=OWNER_ID, patient_id=PATIENT_ID,
        )
