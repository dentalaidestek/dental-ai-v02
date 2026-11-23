"""Web analysis upload failure recovery must match the native durable cleanup contract."""
import io
import pytest
from datetime import timedelta
from pathlib import Path

from PIL import Image
from sqlmodel import Session, select

from test_mobile_chat_actions import chat, _SESSION_TOKEN
from app import main, object_storage, work_jobs


def _png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _patient(engine):
    with Session(engine) as session:
        session.add(main.Patient(
            id=8,
            anonymous_id="SYNTHETIC-WEB-UPLOAD-8",
            owner_user_id=1,
        ))
        session.commit()


def test_web_partial_r2_failure_queues_every_asset_and_removes_stuck_analysis(
    chat, monkeypatch, tmp_path
):
    client, engine = chat
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "UPLOAD_DIR", Path("uploads"))
    main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    client.cookies.set(main.SESSION_COOKIE, _SESSION_TOKEN[1])
    _patient(engine)

    persisted = []

    def fail_second_storage_write(path):
        persisted.append(str(path))
        if len(persisted) == 2:
            raise RuntimeError("synthetic R2 write failure")

    monkeypatch.setattr(main, "storage_persist_file", fail_second_storage_write)
    monkeypatch.setattr(main, "classify_dental_image", lambda _path: "PERIAPICAL")

    response = client.post(
        "/analysis/new/8",
        data={
            "tooth_number": "36",
            "clinical_notes": "Synthetic web upload recovery",
        },
        files=[
            ("images", ("first.png", _png_bytes(), "image/png")),
            ("images", ("second.png", _png_bytes(), "image/png")),
        ],
    )

    assert response.status_code == 503, response.text
    assert len(persisted) == 2
    assert all(work_jobs.is_analysis_asset_reference(path) for path in persisted)
    assert all(Path(path).is_file() for path in persisted)

    with Session(engine) as session:
        assert session.exec(select(main.Analysis)).all() == []
        assert session.exec(select(main.ImageAsset)).all() == []
        assert session.exec(select(work_jobs.WorkJob)).all() == []
        receipts = session.exec(select(work_jobs.WorkGarbage)).all()
        assert {row.reference for row in receipts} == set(persisted)
        assert all(row.available_at > work_jobs.now() for row in receipts)

    # Once the in-flight storage-write grace period expires, the existing
    # durable collector must delete both orphan objects and consume both rows.
    deleted = []

    def delete_orphan(reference):
        deleted.append(reference)
        Path(reference).unlink(missing_ok=True)

    monkeypatch.setattr(object_storage, "delete", delete_orphan)
    with Session(engine) as session:
        for receipt in session.exec(select(work_jobs.WorkGarbage)).all():
            receipt.available_at = work_jobs.now() - timedelta(seconds=1)
            session.add(receipt)
        session.commit()

    for _ in persisted:
        work_jobs.collect_garbage(engine)

    assert set(deleted) == set(persisted)
    assert all(not Path(path).exists() for path in persisted)
    with Session(engine) as session:
        assert session.exec(select(work_jobs.WorkGarbage)).all() == []


def test_web_recovery_preserves_assets_when_final_commit_may_have_succeeded(
    chat, monkeypatch, tmp_path
):
    _client, engine = chat
    monkeypatch.chdir(tmp_path)
    _patient(engine)

    with Session(engine) as session:
        analysis = main.Analysis(
            patient_id=8,
            tooth_number="36",
            clinical_notes="Synthetic committed upload",
            status="ANALYZING",
        )
        session.add(analysis)
        session.flush()
        analysis_id = analysis.id
        reference = f"uploads/analysis_{analysis_id}_" + ("c" * 32) + ".png"
        session.add(main.ImageAsset(
            analysis_id=analysis_id,
            original_filename="synthetic.png",
            stored_filename=reference.rsplit("/", 1)[-1],
            file_path=reference,
            image_type="PERIAPICAL",
        ))
        main._enqueue_work(session, "VISION", "ANALYSIS", analysis_id)
        session.commit()

    # Simulate a client/driver reporting a failure after the DB commit became
    # durable. Recovery must not delete a file still referenced by committed rows.
    main._recover_failed_web_analysis_upload(analysis_id, [reference])

    with Session(engine) as session:
        assert session.get(main.Analysis, analysis_id) is not None
        assert session.exec(
            select(main.ImageAsset).where(main.ImageAsset.file_path == reference)
        ).first() is not None
        assert session.exec(
            select(work_jobs.WorkJob).where(
                work_jobs.WorkJob.resource_type == "ANALYSIS",
                work_jobs.WorkJob.resource_id == analysis_id,
            )
        ).first() is not None
        receipt = session.exec(
            select(work_jobs.WorkGarbage).where(work_jobs.WorkGarbage.reference == reference)
        ).one()
        receipt.available_at = work_jobs.now() - timedelta(seconds=1)
        session.add(receipt)
        session.commit()

    deleted = []
    monkeypatch.setattr(object_storage, "delete", lambda value: deleted.append(value))
    work_jobs.collect_garbage(engine)

    assert deleted == []
    with Session(engine) as session:
        assert session.get(main.Analysis, analysis_id) is not None
        assert session.exec(
            select(main.ImageAsset).where(main.ImageAsset.file_path == reference)
        ).first() is not None
        assert session.exec(
            select(work_jobs.WorkGarbage).where(work_jobs.WorkGarbage.reference == reference)
        ).first() is None



def test_web_unsupported_image_extension_is_rejected_before_analysis_allocation(
    chat, monkeypatch, tmp_path
):
    client, engine = chat
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "UPLOAD_DIR", Path("uploads"))
    main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    client.cookies.set(main.SESSION_COOKIE, _SESSION_TOKEN[1])
    _patient(engine)

    persisted = []
    monkeypatch.setattr(main, "storage_persist_file", lambda path: persisted.append(str(path)))

    response = client.post(
        "/analysis/new/8",
        data={"tooth_number": "36", "clinical_notes": "Synthetic invalid format"},
        files=[("images", ("payload.exe", b"not a clinical image", "application/octet-stream"))],
    )

    assert response.status_code == 422
    assert "JPEG, PNG veya WebP" in response.text
    assert persisted == []
    with Session(engine) as session:
        assert session.exec(select(main.Analysis)).all() == []
        assert session.exec(select(main.ImageAsset)).all() == []
        assert session.exec(select(work_jobs.WorkJob)).all() == []
        assert session.exec(select(work_jobs.WorkGarbage)).all() == []



def test_web_recovery_rejects_cleanup_key_from_another_analysis(chat):
    _client, engine = chat
    foreign_reference = "uploads/analysis_43_" + ("d" * 32) + ".png"

    with pytest.raises(RuntimeError, match="cleanup key was rejected"):
        main._recover_failed_web_analysis_upload(42, [foreign_reference])

    with Session(engine) as session:
        assert session.exec(select(work_jobs.WorkGarbage)).all() == []
