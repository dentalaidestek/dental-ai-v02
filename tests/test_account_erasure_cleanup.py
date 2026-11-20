"""Account-erasure scope and durable guest-object cleanup regressions."""
import base64
import io
from datetime import timedelta
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import account_erasure, main, object_storage, work_jobs
from app.membership_verification import MembershipVerification


@pytest.fixture
def erasure_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_account_erasure_removes_only_guest_ai_data_and_queues_objects(
    erasure_engine,
):
    guest_reference = "uploads/guest_analysis_1_" + ("a" * 32) + ".jpg"
    result_reference = "uploads/ai_results/guest/1/" + ("b" * 32) + ".json"

    with Session(erasure_engine, expire_on_commit=False) as session:
        owner = main.User(
            username="erase-guest-owner",
            email="erase-guest-owner@example.test",
            role="DOCTOR",
            display_name="Erase Guest Owner",
            is_active=True,
        )
        other = main.User(
            username="keep-guest-owner",
            email="keep-guest-owner@example.test",
            role="DOCTOR",
            display_name="Keep Guest Owner",
            is_active=True,
        )
        session.add_all([owner, other])
        session.flush()

        patient = main.Patient(
            anonymous_id="retained-patient-1",
            owner_user_id=owner.id,
            first_name="Retained",
            last_name="Patient",
        )
        session.add(patient)
        session.flush()
        clinical_analysis = main.Analysis(
            patient_id=patient.id,
            status="AI_FINAL",
            result_path="uploads/ai_results/patient/1/" + ("c" * 32) + ".json",
        )
        session.add(clinical_analysis)
        session.flush()
        clinical_asset = main.ImageAsset(
            analysis_id=clinical_analysis.id,
            original_filename="clinical.jpg",
            stored_filename="clinical-retained.jpg",
            file_path="uploads/analysis_retained.jpg",
        )
        clinical_media = main.PatientMedia(
            patient_id=patient.id,
            owner_user_id=owner.id,
            original_filename="archive.jpg",
            stored_filename="archive-retained.jpg",
            file_path="uploads/patient-media/patient_1_" + ("d" * 32) + ".jpg",
        )

        guest = main.GuestAnalysis(
            owner_user_id=owner.id,
            clinical_notes="ephemeral guest notes",
            result_path=result_reference,
        )
        other_guest = main.GuestAnalysis(
            owner_user_id=other.id,
            clinical_notes="other account guest notes",
        )
        session.add_all([clinical_asset, clinical_media, guest, other_guest])
        session.flush()
        session.add(main.GuestImageAsset(
            guest_analysis_id=guest.id,
            original_filename="guest.jpg",
            stored_filename=guest_reference.rsplit("/", 1)[-1],
            file_path=guest_reference,
        ))
        session.add(main.GuestImageAsset(
            guest_analysis_id=other_guest.id,
            original_filename="other.jpg",
            stored_filename="other-guest.jpg",
            file_path="uploads/guest_analysis_2_" + ("e" * 32) + ".jpg",
        ))
        session.add_all([
            work_jobs.WorkJob(
                owner_user_id=owner.id,
                resource_id=guest.id,
                resource_type="GUEST",
                kind="PRELIMINARY",
                source_hash="f" * 64,
                dedupe_key="erase-guest-job",
                payload_json='{"clinical_notes":"ephemeral guest notes"}',
                result_ref=result_reference,
                status="RUNNING",
                lease_token="running-guest-lease",
            ),
            work_jobs.WorkJob(
                owner_user_id=owner.id,
                resource_id=clinical_analysis.id,
                resource_type="ANALYSIS",
                kind="FINAL",
                source_hash="d" * 64,
                dedupe_key="cancel-clinical-job",
                payload_json='{"clinical_notes":"transient queued payload"}',
                result_ref=clinical_analysis.result_path,
                status="QUEUED",
            ),
            work_jobs.WorkJob(
                owner_user_id=other.id,
                resource_id=other_guest.id,
                resource_type="GUEST",
                kind="PRELIMINARY",
                source_hash="e" * 64,
                dedupe_key="keep-guest-job",
                payload_json="{}",
            ),
        ])
        session.commit()
        owner_id = owner.id
        other_guest_id = other_guest.id
        guest_id = guest.id
        patient_id = patient.id
        analysis_id = clinical_analysis.id
        media_id = clinical_media.id
        image_id = clinical_asset.id

        erased_count, fallback = account_erasure.erase_account_ai_data(
            session, owner_id
        )
        session.commit()

    assert erased_count == 1
    assert fallback == []
    with Session(erasure_engine) as session:
        assert session.get(main.GuestAnalysis, guest_id) is None
        assert session.exec(
            select(main.GuestImageAsset).where(
                main.GuestImageAsset.guest_analysis_id == guest_id
            )
        ).all() == []
        assert session.exec(
            select(work_jobs.WorkJob).where(
                work_jobs.WorkJob.owner_user_id == owner_id,
                work_jobs.WorkJob.resource_type == "GUEST",
            )
        ).all() == []
        assert session.get(main.GuestAnalysis, other_guest_id) is not None
        assert session.exec(
            select(work_jobs.WorkJob).where(
                work_jobs.WorkJob.dedupe_key == "keep-guest-job"
            )
        ).one()
        cancelled_clinical_job = session.exec(
            select(work_jobs.WorkJob).where(
                work_jobs.WorkJob.dedupe_key == "cancel-clinical-job"
            )
        ).one()
        assert cancelled_clinical_job.status == "CANCELLED"
        assert cancelled_clinical_job.error_code == "ACCOUNT_ERASED"
        assert cancelled_clinical_job.payload_json == "{}"
        assert cancelled_clinical_job.result_ref is None

        # Patient-linked clinical records are intentionally not erased with a
        # clinician account: they belong to patients and may have retention duties.
        assert session.get(main.Patient, patient_id) is not None
        assert session.get(main.Analysis, analysis_id) is not None
        assert session.get(main.ImageAsset, image_id) is not None
        assert session.get(main.PatientMedia, media_id) is not None

        queued = {
            row.reference
            for row in session.exec(select(work_jobs.WorkGarbage)).all()
        }
        assert queued == {guest_reference, result_reference, clinical_analysis.result_path}


def test_guest_cleanup_worker_deletes_only_after_guest_metadata_is_gone(
    erasure_engine, monkeypatch
):
    guest_reference = "uploads/guest_analysis_3_" + ("a" * 32) + ".webp"
    result_reference = "uploads/ai_results/guest/3/" + ("b" * 32) + ".json"
    with Session(erasure_engine) as session:
        session.add_all([
            work_jobs.WorkGarbage(
                reference=guest_reference,
                available_at=work_jobs.now() - timedelta(seconds=1),
            ),
            work_jobs.WorkGarbage(
                reference=result_reference,
                available_at=work_jobs.now() - timedelta(seconds=1),
            ),
        ])
        session.commit()

    deleted = []
    monkeypatch.setattr(object_storage, "delete", lambda reference: deleted.append(reference))
    work_jobs.collect_garbage(erasure_engine)
    work_jobs.collect_garbage(erasure_engine)

    assert set(deleted) == {guest_reference, result_reference}
    with Session(erasure_engine) as session:
        assert session.exec(select(work_jobs.WorkGarbage)).all() == []


def test_account_erasure_cleanup_allowlists_reject_untrusted_paths():
    valid_guest = "uploads/guest_analysis_8_" + ("a" * 32) + ".png"
    valid_result = "uploads/ai_results/guest/8/" + ("b" * 32) + ".json"
    assert work_jobs.is_guest_analysis_reference(valid_guest)
    assert work_jobs.is_ai_result_reference(valid_result)

    for invalid in (
        "../uploads/guest_analysis_8_" + ("a" * 32) + ".png",
        "uploads/guest_analysis_0_" + ("a" * 32) + ".png",
        "uploads/guest_analysis_8_" + ("A" * 32) + ".png",
        "uploads/guest_analysis_8_" + ("a" * 32) + ".exe",
        "uploads/ai_results/../private.json",
        "uploads\\ai_results\\private.json",
        "/uploads/ai_results/private.json",
    ):
        assert not work_jobs.is_guest_analysis_reference(invalid)
        assert not work_jobs.is_ai_result_reference(invalid)


def test_guest_upload_finalization_serializes_with_account_erasure():
    source = Path(main.__file__).read_text(encoding="utf-8")
    block = source.split("def create_guest_analysis", 1)[1].split(
        '@app.post("/analysis/new/{patient_id}")', 1
    )[0]
    assert "with_for_update()" in block
    assert "enqueue_guest_analysis_cleanup" in block
    assert "s.rollback()" in block

    erasure_source = Path(account_erasure.__file__).read_text(encoding="utf-8")
    begin = erasure_source.split("def begin_account_erasure", 1)[1]
    assert "erase_account_ai_data(session, user_id)" in begin


def test_account_erasure_queues_profile_and_all_identity_documents(erasure_engine):
    with Session(erasure_engine, expire_on_commit=False) as session:
        owner = main.User(
            username="erase-account-assets",
            email="erase-account-assets@example.test",
            role="DOCTOR",
            display_name="Erase Account Assets",
            is_active=True,
        )
        session.add(owner)
        session.flush()
        profile_photo = f"uploads/profile_photos/user_{owner.id}_{'a' * 16}.jpg"
        credential = f"uploads/expert_credentials/user_{owner.id}/credential_{'b' * 32}.pdf"
        title_change_document = f"uploads/expert_title_changes/user_{owner.id}/title_{'c' * 32}.pdf"
        membership_document = f"uploads/membership_documents/user_{owner.id}/{'d' * 32}.pdf"
        owner.profile_photo_path = profile_photo
        profile = main.ExpertProfile(
            user_id=owner.id,
            specialty="Endodonti",
            credential_document_path=credential,
            credential_document_name="credential.pdf",
            credential_document_mime="application/pdf",
        )
        title_change = main.ExpertTitleChange(
            user_id=owner.id,
            requested_title="Doç. Dr.",
            status="PENDING_REVIEW",
            credential_document_path=title_change_document,
            credential_document_name="title-change.pdf",
            credential_document_mime="application/pdf",
        )
        membership = MembershipVerification(
            user_id=owner.id,
            document_type="DIPLOMA",
            document_path=membership_document,
            document_name="diploma.pdf",
            document_mime="application/pdf",
            name_snapshot="Erase Account Assets",
            title_snapshot="Diş Hekimi",
            submitted_at=main._utcnow_naive(),
        )
        session.add_all([owner, profile, title_change, membership])
        session.commit()
        owner_id = owner.id
        profile_id = profile.id
        title_change_id = title_change.id
        membership_id = membership.id

        fallback = account_erasure.begin_account_erasure(
            session, user_id=owner_id, actor="SELF"
        )
        session.commit()

    assert fallback == []
    with Session(erasure_engine) as session:
        erased = session.get(main.User, owner_id)
        assert erased is not None and erased.is_active is False
        assert erased.profile_photo_path is None
        retained_profile = session.get(main.ExpertProfile, profile_id)
        assert retained_profile.credential_document_path is None
        retained_title_change = session.get(main.ExpertTitleChange, title_change_id)
        assert retained_title_change.credential_document_path is None
        assert retained_title_change.credential_document_name is None
        assert session.get(MembershipVerification, membership_id) is None
        queued = {
            row.reference
            for row in session.exec(select(work_jobs.WorkGarbage)).all()
        }
        assert queued == {
            profile_photo,
            credential,
            title_change_document,
            membership_document,
        }


def test_account_asset_cleanup_allowlist_is_strict():
    valid = (
        "uploads/profile_photos/user_7_" + "a" * 16 + ".jpg",
        "uploads/expert_credentials/user_7/credential_" + "b" * 32 + ".pdf",
        "uploads/expert_title_changes/user_7/title_" + "c" * 32 + ".png",
        "uploads/membership_documents/user_7/" + "d" * 32 + ".jpeg",
    )
    assert all(work_jobs.is_account_asset_reference(reference) for reference in valid)

    invalid = (
        "../uploads/profile_photos/user_7_" + "a" * 16 + ".jpg",
        "uploads/profile_photos/user_0_" + "a" * 16 + ".jpg",
        "uploads/profile_photos/user_7_" + "a" * 32 + ".jpg",
        "uploads/expert_credentials/user_7/credential_" + "b" * 32 + ".exe",
        "uploads/expert_title_changes/user_7/../title_" + "c" * 32 + ".pdf",
        "uploads/membership_documents/user_7/" + "D" * 32 + ".pdf",
        "uploads/patient-media/patient_7_" + "e" * 32 + ".jpg",
        "r2://bucket/uploads/profile_photos/user_7_" + "a" * 16 + ".jpg",
    )
    assert all(not work_jobs.is_account_asset_reference(reference) for reference in invalid)


def test_account_asset_cleanup_retries_r2_failure_with_backoff_across_collector_invocations(
    erasure_engine, monkeypatch
):
    reference = "uploads/profile_photos/user_8_" + "f" * 16 + ".jpg"
    with Session(erasure_engine) as session:
        assert work_jobs.enqueue_account_asset_cleanup(session, reference)
        session.commit()

    calls = []
    def delete_twice_fails(path):
        calls.append(path)
        if len(calls) <= 2:
            raise object_storage.ObjectStorageError("synthetic R2 timeout")

    monkeypatch.setattr(object_storage, "delete", delete_twice_fails)
    work_jobs.collect_garbage(erasure_engine)
    with Session(erasure_engine) as session:
        receipt = session.exec(
            select(work_jobs.WorkGarbage).where(work_jobs.WorkGarbage.reference == reference)
        ).one()
        assert receipt.attempts == 1
        first_retry_at = receipt.available_at
        assert first_retry_at > work_jobs.now()
        receipt.available_at = work_jobs.now() - timedelta(seconds=1)
        session.add(receipt)
        session.commit()

    # A second worker invocation still uses only the durable receipt.
    work_jobs.collect_garbage(erasure_engine)
    with Session(erasure_engine) as session:
        receipt = session.exec(
            select(work_jobs.WorkGarbage).where(work_jobs.WorkGarbage.reference == reference)
        ).one()
        assert receipt.attempts == 2
        assert receipt.available_at > first_retry_at
        receipt.available_at = work_jobs.now() - timedelta(seconds=1)
        session.add(receipt)
        session.commit()

    monkeypatch.setattr(object_storage, "delete", lambda path: calls.append(path))
    work_jobs.collect_garbage(erasure_engine)
    assert calls == [reference, reference, reference]
    with Session(erasure_engine) as session:
        assert session.exec(
            select(work_jobs.WorkGarbage).where(work_jobs.WorkGarbage.reference == reference)
        ).all() == []


def test_account_asset_cleanup_preserves_any_still_referenced_identity_object(
    erasure_engine, monkeypatch
):
    references = {
        "profile": "uploads/profile_photos/user_9_" + "a" * 16 + ".jpg",
        "credential": "uploads/expert_credentials/user_9/credential_" + "b" * 32 + ".pdf",
        "title": "uploads/expert_title_changes/user_9/title_" + "c" * 32 + ".pdf",
        "membership": "uploads/membership_documents/user_9/" + "d" * 32 + ".pdf",
    }
    with Session(erasure_engine) as session:
        owner = main.User(
            username="retained-asset-owner",
            email="retained-asset-owner@example.test",
            role="DOCTOR",
            display_name="Retained Asset Owner",
            profile_photo_path=references["profile"],
        )
        session.add(owner)
        session.flush()
        session.add_all([
            main.ExpertProfile(
                user_id=owner.id,
                specialty="Endodonti",
                credential_document_path=references["credential"],
            ),
            main.ExpertTitleChange(
                user_id=owner.id,
                requested_title="Doç. Dr.",
                credential_document_path=references["title"],
            ),
            MembershipVerification(
                user_id=owner.id,
                document_type="DIPLOMA",
                document_path=references["membership"],
                document_name="diploma.pdf",
                document_mime="application/pdf",
                name_snapshot="Retained Asset Owner",
                submitted_at=main._utcnow_naive(),
            ),
        ])
        for reference in references.values():
            assert work_jobs.enqueue_account_asset_cleanup(session, reference)
        session.commit()

    deleted = []
    monkeypatch.setattr(object_storage, "delete", lambda path: deleted.append(path))
    for _ in references:
        work_jobs.collect_garbage(erasure_engine)

    assert deleted == []
    with Session(erasure_engine) as session:
        assert session.exec(select(work_jobs.WorkGarbage)).all() == []


def test_replaced_account_asset_cleanup_queues_only_a_different_allowlisted_key(erasure_engine):
    previous = "uploads/profile_photos/user_17_" + "a" * 16 + ".jpg"
    current = "uploads/profile_photos/user_17_" + "b" * 16 + ".jpg"
    legacy = "../uploads/profile_photos/user_17_" + "c" * 16 + ".jpg"

    with Session(erasure_engine) as session:
        assert work_jobs.enqueue_replaced_account_asset_cleanup(session, previous, current)
        assert not work_jobs.enqueue_replaced_account_asset_cleanup(session, current, current)
        assert not work_jobs.enqueue_replaced_account_asset_cleanup(session, legacy, current)
        session.commit()

    with Session(erasure_engine) as session:
        queued = session.exec(select(work_jobs.WorkGarbage)).all()
        assert [row.reference for row in queued] == [previous]


def test_replaced_profile_and_credential_objects_are_collected_after_metadata_switch(
    erasure_engine, monkeypatch
):
    references = {
        "old_photo": "uploads/profile_photos/user_18_" + "a" * 16 + ".jpg",
        "new_photo": "uploads/profile_photos/user_18_" + "b" * 16 + ".jpg",
        "old_credential": "uploads/expert_credentials/user_18/credential_" + "c" * 32 + ".pdf",
        "new_credential": "uploads/expert_credentials/user_18/credential_" + "d" * 32 + ".pdf",
        "old_title": "uploads/expert_title_changes/user_18/title_" + "e" * 32 + ".pdf",
        "new_title": "uploads/expert_title_changes/user_18/title_" + "f" * 32 + ".pdf",
    }
    with Session(erasure_engine, expire_on_commit=False) as session:
        owner = main.User(
            username="replace-account-assets",
            email="replace-account-assets@example.test",
            role="DOCTOR",
            display_name="Replace Account Assets",
            profile_photo_path=references["old_photo"],
        )
        session.add(owner)
        session.flush()
        profile = main.ExpertProfile(
            user_id=owner.id,
            specialty="Endodonti",
            credential_document_path=references["old_credential"],
        )
        title_change = main.ExpertTitleChange(
            user_id=owner.id,
            requested_title="Doç. Dr.",
            status="PENDING_REVIEW",
            credential_document_path=references["old_title"],
        )
        session.add_all([profile, title_change])
        session.flush()
        owner.profile_photo_path = references["new_photo"]
        profile.credential_document_path = references["new_credential"]
        title_change.credential_document_path = references["new_title"]
        assert work_jobs.enqueue_replaced_account_asset_cleanup(
            session, references["old_photo"], references["new_photo"]
        )
        assert work_jobs.enqueue_replaced_account_asset_cleanup(
            session, references["old_credential"], references["new_credential"]
        )
        assert work_jobs.enqueue_replaced_account_asset_cleanup(
            session, references["old_title"], references["new_title"]
        )
        session.add_all([owner, profile, title_change])
        session.commit()
        owner_id, profile_id, title_id = owner.id, profile.id, title_change.id

    deleted = []
    monkeypatch.setattr(object_storage, "delete", lambda reference: deleted.append(reference))
    for _ in range(3):
        work_jobs.collect_garbage(erasure_engine)

    assert set(deleted) == {
        references["old_photo"],
        references["old_credential"],
        references["old_title"],
    }
    with Session(erasure_engine) as session:
        assert session.get(main.User, owner_id).profile_photo_path == references["new_photo"]
        assert session.get(main.ExpertProfile, profile_id).credential_document_path == references["new_credential"]
        assert session.get(main.ExpertTitleChange, title_id).credential_document_path == references["new_title"]
        assert session.exec(select(work_jobs.WorkGarbage)).all() == []


def test_web_account_asset_replacements_use_transactional_cleanup_and_validate_before_write():
    source = Path(main.__file__).read_text(encoding="utf-8")

    photo = source.split("def account_profile_photo", 1)[1].split(
        '@app.post("/account/professional-title")', 1
    )[0]
    assert "enqueue_replaced_account_asset_cleanup(s, previous_path, path)" in photo
    assert "_queue_uncommitted_account_asset_cleanup(path)" in photo

    title = source.split("def professional_title_document_upload", 1)[1].split(
        '@app.post("/account/username"', 1
    )[0]
    assert "enqueue_replaced_account_asset_cleanup(s, previous_document_path, str(destination))" in title
    assert "_queue_uncommitted_account_asset_cleanup(str(destination))" in title

    expert = source.split("def expert_support_profile_save", 1)[1].split(
        '@app.get("/expert-support/request/', 1
    )[0]
    assert "enqueue_replaced_account_asset_cleanup(s, previous_photo_path, new_photo_path)" in expert
    assert "enqueue_replaced_account_asset_cleanup(s, previous_credential_path, new_credential_path)" in expert
    assert expert.index("if compact_orcid[-1].upper()") < expert.index(
        "storage_write_bytes(destination, document_bytes, content_type=document_mime)"
    )
    assert "_queue_uncommitted_account_asset_cleanup(new_credential_path)" in expert

def test_profile_photo_keys_are_unique_for_identical_uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(main, "storage_persist_file", lambda *args, **kwargs: None)
    image_bytes = io.BytesIO()
    Image.new("RGB", (16, 16), (30, 60, 90)).save(image_bytes, format="JPEG")
    encoded = "data:image/jpeg;base64," + base64.b64encode(image_bytes.getvalue()).decode("ascii")

    first = main._save_profile_photo(23, encoded)
    second = main._save_profile_photo(23, encoded)

    assert first != second
    assert work_jobs.is_account_asset_reference(first)
    assert work_jobs.is_account_asset_reference(second)
