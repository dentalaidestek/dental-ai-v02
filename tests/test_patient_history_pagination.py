from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlmodel import Session

from app import main
from app.patient_history_pagination import (
    HISTORY_PAGE_SIZE,
    decode_history_cursor,
    encode_history_cursor,
    history_page_slice,
)
from app.work_jobs import WorkJob
from test_mobile_chat_actions import chat, _SESSION_TOKEN


def test_patient_history_cursor_round_trips_and_rejects_malformed_values():
    stamp = datetime(2026, 11, 20, 8, 30, 12, 345678)
    cursor = encode_history_cursor(stamp, 1234)
    assert decode_history_cursor(cursor) == (stamp, 1234)
    aware = datetime(2026, 11, 20, 11, 30, tzinfo=timezone(timedelta(hours=3)))
    aware_cursor = encode_history_cursor(aware, 1235)
    assert decode_history_cursor(aware_cursor) == (
        datetime(2026, 11, 20, 8, 30), 1235
    )
    assert decode_history_cursor(None) is None
    for invalid in ("!", "a" * 193, "////", "", 123):
        with pytest.raises(ValueError):
            decode_history_cursor(invalid)


def test_history_page_slice_uses_created_at_and_id_boundary():
    stamp = datetime(2026, 11, 20, 8, 0)
    rows = [
        SimpleNamespace(id=100 - index, created_at=stamp + timedelta(minutes=20 - index))
        for index in range(HISTORY_PAGE_SIZE + 1)
    ]
    page, cursor = history_page_slice(rows)
    assert len(page) == HISTORY_PAGE_SIZE
    assert decode_history_cursor(cursor) == (page[-1].created_at, page[-1].id)
    complete, no_cursor = history_page_slice(rows[:HISTORY_PAGE_SIZE])
    assert len(complete) == HISTORY_PAGE_SIZE
    assert no_cursor is None
    with pytest.raises(ValueError):
        history_page_slice(rows, True)


def test_web_patient_analysis_and_treatment_history_are_bounded_and_owner_scoped(chat):
    client, engine = chat
    client.cookies.set(main.SESSION_COOKIE, _SESSION_TOKEN[1])
    base = datetime(2026, 11, 1, 9, 0)
    with Session(engine) as session:
        session.add(main.Patient(
            id=8801, anonymous_id="SYNTHETIC-HISTORY-8801", owner_user_id=1
        ))
        session.add(main.Patient(
            id=8802, anonymous_id="SYNTHETIC-HISTORY-8802", owner_user_id=2
        ))
        session.add_all([
            main.Analysis(
                id=1000 + index, patient_id=8801, tooth_number="36",
                status="DRAFT", created_at=base,
            )
            for index in range(25)
        ])
        session.add_all([
            main.Treatment(
                id=2000 + index, patient_id=8801, tooth_number="36",
                treatment_name=f"Synthetic treatment {index}",
                treatment_date="20.11.2026",
                created_at=base,
            )
            for index in range(25)
        ])
        session.add(main.ImageAsset(
            id=3001, analysis_id=1024, original_filename="synthetic.png",
            stored_filename="synthetic.png", file_path="uploads/synthetic.png",
            image_type="PHOTO",
        ))
        session.add_all([
            WorkJob(
                owner_user_id=1, resource_id=1024, resource_type="ANALYSIS",
                kind="VOICE_REVIEW", status="DONE", source_hash="history-done",
                dedupe_key="history-done-8801", payload_json="{}",
            ),
            WorkJob(
                owner_user_id=1, resource_id=1023, resource_type="ANALYSIS",
                kind="VOICE_REVIEW", status="RUNNING", source_hash="history-running",
                dedupe_key="history-running-8801", payload_json="{}",
            ),
        ])
        session.commit()

    profile = client.get("/patients/8801")
    assert profile.status_code == 200, profile.text
    assert profile.text.count('class="analysis-history-item"') == HISTORY_PAGE_SIZE
    assert profile.text.count('class="treatment-item"') == HISTORY_PAGE_SIZE
    assert 'id="loadMoreAnalyses"' in profile.text
    assert 'id="loadMoreTreatments"' in profile.text

    first_analysis = client.get("/patients/8801/history/analyses/page")
    assert first_analysis.status_code == 200, first_analysis.text
    assert first_analysis.headers["cache-control"] == "private, no-store"
    assert "cookie" in first_analysis.headers.get("vary", "").lower()
    assert "Sesli muayene #1024" in first_analysis.json()["html"]
    assert "Analiz #1023" in first_analysis.json()["html"]
    assert "synthetic.png" in first_analysis.json()["html"]
    analysis_cursor = first_analysis.json()["next_cursor"]
    assert analysis_cursor

    first_treatment = client.get("/patients/8801/history/treatments/page")
    assert first_treatment.status_code == 200, first_treatment.text
    treatment_cursor = first_treatment.json()["next_cursor"]
    assert treatment_cursor

    # Newer inserts must not shift the remainder of an already-open cursor walk.
    with Session(engine) as session:
        session.add(main.Analysis(
            id=1099, patient_id=8801, tooth_number="11",
            created_at=base + timedelta(days=2),
        ))
        session.add(main.Treatment(
            id=2099, patient_id=8801, tooth_number="11",
            treatment_name="Concurrent new treatment",
            created_at=base + timedelta(days=2),
        ))
        session.commit()

    second_analysis = client.get(
        "/patients/8801/history/analyses/page", params={"before": analysis_cursor}
    )
    assert second_analysis.status_code == 200, second_analysis.text
    assert "Analiz #1004" in second_analysis.json()["html"]
    assert "Analiz #1099" not in second_analysis.json()["html"]
    assert second_analysis.json()["next_cursor"] is None

    collapsed_treatments = client.get(
        "/patients/8801/history/treatments/page",
        params={"before": treatment_cursor, "expanded": "false"},
    )
    expanded_treatments = client.get(
        "/patients/8801/history/treatments/page",
        params={"before": treatment_cursor, "expanded": "true"},
    )
    assert collapsed_treatments.status_code == expanded_treatments.status_code == 200
    assert 'style="display:none;"' in collapsed_treatments.json()["html"]
    assert 'style=""' in expanded_treatments.json()["html"]
    assert "Concurrent new treatment" not in expanded_treatments.json()["html"]
    assert expanded_treatments.json()["next_cursor"] is None

    assert client.get(
        "/patients/8801/history/analyses/page", params={"before": "!"}
    ).status_code == 400
    assert client.get("/patients/8801/history/analyses/page").status_code == 200

    client.cookies.set(main.SESSION_COOKIE, "token2")
    assert client.get("/patients/8801/history/analyses/page").status_code == 403
    assert client.get("/patients/8801/history/treatments/page").status_code == 403
