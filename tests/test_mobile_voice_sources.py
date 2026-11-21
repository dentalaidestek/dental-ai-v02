"""Mobil sesli muayene kaynak akışlarının regresyon testleri.

Kapsam: resmî kaynak dizini araması (web voice_exam.source_references birebir)
ve kaynaklı klinik kontrol noktaları (web voice_exam.clinical_review delege).
"""
import pytest
from sqlmodel import Session, SQLModel, create_engine

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main

BASE = "/api/mobile/v1"


def _build(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "voice-sources.db"),
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr("app.mobile_api.engine", engine)
    return TestClient(main.app), engine


def _user_and_patient(session, username, role="DOCTOR"):
    user = main.User(
        username=username, role=role, display_name=username,
        email_verified_at=main._utcnow_naive(),
    )
    session.add(user)
    session.commit()
    token = "vsrc-" + username + "-" + "t" * 22
    session.add(main.SessionToken(
        token_hash=main.hash_session_token(token),
        user_id=user.id,
        expires_at=main._utcnow_naive() + main.timedelta(days=1),
    ))
    patient = main.Patient(owner_user_id=user.id, anonymous_id="PAT-" + username.replace("-", "").upper()[:14])
    session.add(patient)
    session.commit()
    return token, int(patient.id)


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_voice_sources_enforces_access_and_validation(monkeypatch, tmp_path):
    client, engine = _build(monkeypatch, tmp_path)
    monkeypatch.setattr("app.voice_exam.core.enabled", lambda: True)
    with Session(engine) as session:
        doctor_token, doctor_patient_id = _user_and_patient(session, "vsrc-doctor")
        _, other_patient_id = _user_and_patient(session, "vsrc-other")
        patient_token, _ = _user_and_patient(session, "vsrc-patient", role="PATIENT")
    doctor = {"Authorization": "Bearer " + doctor_token}

    unauthenticated = client.post(
        BASE + f"/patients/{doctor_patient_id}/voice-exam/sources",
        json={"query": "kanama"}, headers={"Authorization": "Bearer x" * 0},
    )
    assert unauthenticated.status_code in (401, 403)

    foreign = client.post(
        BASE + f"/patients/{other_patient_id}/voice-exam/sources",
        json={"query": "kanama"}, headers=doctor,
    )
    assert foreign.status_code == 404

    forbidden = client.post(
        BASE + "/patients/1/voice-exam/sources",
        json={"query": "kanama"}, headers={"Authorization": "Bearer " + patient_token},
    )
    assert forbidden.status_code == 403

    invalid = client.post(
        BASE + f"/patients/{doctor_patient_id}/voice-exam/sources",
        json={"query": "ab"}, headers=doctor,
    )
    assert invalid.status_code == 422

    monkeypatch.setattr("app.voice_exam.core.enabled", lambda: False)
    disabled = client.post(
        BASE + f"/patients/{doctor_patient_id}/voice-exam/sources",
        json={"query": "kanama"}, headers=doctor,
    )
    assert disabled.status_code == 503


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_voice_sources_returns_official_directory(monkeypatch, tmp_path):
    client, engine = _build(monkeypatch, tmp_path)
    monkeypatch.setattr("app.voice_exam.core.enabled", lambda: True)
    with Session(engine) as session:
        token, patient_id = _user_and_patient(session, "vsrc-list")
    headers = {"Authorization": "Bearer " + token}

    captured = {}

    def fake_retrieve(query):
        captured["query"] = query
        return {"notice": "dizin kontrol edildi", "references": [
            {"institution": "ADA", "title": "Antibiyotik profilaksi", "url": "https://ada.org/x"},
        ]}

    monkeypatch.setattr("app.voice_exam_sources.retrieve", fake_retrieve)
    response = client.post(
        BASE + f"/patients/{patient_id}/voice-exam/sources",
        json={"query": "profilaksi"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["notice"] == "dizin kontrol edildi"
    assert body["references"][0]["institution"] == "ADA"
    assert captured["query"] == "profilaksi"


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient unavailable")
def test_voice_clinical_requires_consent_and_delegates(monkeypatch, tmp_path):
    client, engine = _build(monkeypatch, tmp_path)
    monkeypatch.setattr("app.voice_exam.core.enabled", lambda: True)
    with Session(engine) as session:
        token, patient_id = _user_and_patient(session, "vsrc-clinical")
    headers = {"Authorization": "Bearer " + token}
    payload = {"context": {"fields": {"chief_complaint": {"value": "ağrı"}}}}

    no_consent = client.post(
        BASE + f"/patients/{patient_id}/voice-exam/clinical",
        json=payload, headers=headers,
    )
    assert no_consent.status_code == 400
    assert no_consent.json()["code"] == "VOICE_CLINICAL_CONSENT_REQUIRED"

    def fake_assess(context):
        return {"notice": "kontrol tamam", "items": [{"consideration": "c"}], "unavailable": []}

    monkeypatch.setattr("app.voice_exam_clinical.assess", fake_assess)
    response = client.post(
        BASE + f"/patients/{patient_id}/voice-exam/clinical",
        json={**payload, "consent": True}, headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["items"][0]["consideration"] == "c"

    from app.voice_exam import core

    def busy_assess(context):
        raise core.VoiceError("Klinik değerlendirme meşgul; mevcut özet korunuyor.")

    monkeypatch.setattr("app.voice_exam_clinical.assess", busy_assess)
    busy = client.post(
        BASE + f"/patients/{patient_id}/voice-exam/clinical",
        json={**payload, "consent": True}, headers=headers,
    )
    assert busy.status_code == 422
    assert busy.json()["code"] == "VOICE_CLINICAL_UNAVAILABLE"
