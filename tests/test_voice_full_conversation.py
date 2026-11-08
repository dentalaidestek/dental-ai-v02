"""Full final-review context stays bounded, transient and outside public research."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlmodel import Session, select

from app import voice_exam_core as core, voice_exam_final as final
from test_voice_exam import app_client, Analysis, WorkJob, Patient
from test_voice_exam_final import provider, CONTEXT


def test_final_can_ground_an_extraction_omission_to_transient_conversation(monkeypatch):
    quote = "Hasta: Dün ateşim vardı, bugün yutarken zorlanıyorum."
    source = "Swallowing difficulty requires clinical assessment."
    calls = provider(
        monkeypatch,
        {
            "questions": [],
            "contradictions": [],
            "clinical_items": [
                {
                    "review_topic": "other",
                    "source_id": "synthetic",
                    "source_quote": source,
                    "patient_field": "conversation",
                    "patient_quote": "bugün yutarken zorlanıyorum",
                    "consideration": "Yutma yakınmasını klinik değerlendirme ile netleştirin.",
                    "missing_information": "",
                    "alternative": "",
                }
            ],
        },
    )
    searches = []
    monkeypatch.setattr(
        final,
        "retrieve",
        lambda query, **kwargs: searches.append((query, kwargs))
        or {
            "references": [
                {"id": "synthetic", "excerpts": [source], "clinical_use": True}
            ],
            "unavailable": [],
            "coverage": "limited",
            "notice": "Synthetic",
        },
    )

    output = final.finalize(CONTEXT, [], conversation_text=quote)

    assert output["clinical_items"][0]["patient_field"] == "conversation"
    assert not any(item["field"] == "conversation" for item in output["summary"])
    submitted = json.loads(calls[0]["messages"][0]["content"])
    assert submitted["conversation_text"] == quote
    assert (
        "conversation" not in submitted["clinical_fields"]
    ), "Do not duplicate the full text in the paid input"
    assert (
        "conversation"
        in calls[0]["output_config"]["format"]["schema"]["properties"][
            "clinical_items"
        ]["items"]["properties"]["patient_field"]["enum"]
    )
    assert quote not in json.dumps(searches, ensure_ascii=False)
    assert "conversation_text" not in output
    assert output["review_status"]["conversation_included"] is True
    assert len(calls) == 1


def test_final_conversation_minimizes_identity_without_erasing_clinical_cost_or_fear(
    monkeypatch,
):
    calls = provider(
        monkeypatch, {"questions": [], "contradictions": [], "clinical_items": []}
    )
    context = {
        "fields": {
            **CONTEXT["fields"],
            "first_name": {"value": "Zeynep", "quote": "Zeynep"},
            "last_name": {"value": "Deniz", "quote": "Deniz"},
        }
    }
    text = (
        "Hasta: Adım Zeynep Deniz. E-posta zeynep@example.org; telefon 0555 111 22 33; "
        "TC kimlik 12345678901. Adresim Gizli Mahallesi 17. Maaşım 85000 TL. "
        "Dişim çok ağrıyor. İğneden korkuyorum, kaplama ücretini taksitle ödeyebilir miyim?"
    )
    output = final.finalize(context, [], conversation_text=text)
    submitted = calls[0]["messages"][0]["content"]
    for private in (
        "Zeynep",
        "Deniz",
        "zeynep@example.org",
        "0555 111 22 33",
        "12345678901",
        "Gizli Mahallesi",
        "85000",
    ):
        assert private not in submitted
    conversation = json.loads(submitted)["conversation_text"]
    assert "Dişim çok ağrıyor." in conversation
    assert (
        "İğneden korkuyorum, kaplama ücretini taksitle ödeyebilir miyim?"
        in conversation
    )
    assert text not in json.dumps(output, ensure_ascii=False)


def test_income_redaction_preserves_a_cost_barrier_in_the_same_sentence(monkeypatch):
    calls = provider(
        monkeypatch, {"questions": [], "contradictions": [], "clinical_items": []}
    )
    text = "Maaşım 85000 TL, bu yüzden kaplama ücretini ödeyemiyorum ve iğneden korkuyorum."
    final.finalize(CONTEXT, [], conversation_text=text)
    submitted = json.loads(calls[0]["messages"][0]["content"])["conversation_text"]
    assert "85000" not in submitted
    assert "kaplama ücretini ödeyemiyorum ve iğneden korkuyorum" in submitted


def test_address_redaction_keeps_the_following_clinical_clause(monkeypatch):
    calls = provider(
        monkeypatch, {"questions": [], "contradictions": [], "clinical_items": []}
    )
    text = "Adresim Gizli Mahallesi 17, dişim ağrıyor, yaklaşık üç gündür."
    final.finalize(CONTEXT, [], conversation_text=text)
    submitted = json.loads(calls[0]["messages"][0]["content"])["conversation_text"]
    assert "Gizli Mahallesi" not in submitted
    assert "dişim ağrıyor, yaklaşık üç gündür" in submitted


def test_known_identity_in_a_clinical_evidence_quote_does_not_leak_in_final_transport(
    monkeypatch,
):
    calls = provider(
        monkeypatch, {"questions": [], "contradictions": [], "clinical_items": []}
    )
    context = {
        "fields": {
            "first_name": {"value": "Zeynep", "quote": "Zeynep"},
            "chief_complaint": {
                "value": "Dişim ağrıyor.",
                "quote": "Adım Zeynep. Dişim ağrıyor.",
                "edited": False,
            },
        }
    }
    final.finalize(context, [], conversation_text="Adım Zeynep. Dişim ağrıyor.")
    assert "Zeynep" not in calls[0]["messages"][0]["content"]


def test_conversation_changes_invalidate_reused_review(monkeypatch):
    calls = provider(
        monkeypatch, {"questions": [], "contradictions": [], "clinical_items": []}
    )
    first = final.finalize(CONTEXT, [], conversation_text="Hasta: Ateşim yok.")
    unchanged = final.finalize(
        CONTEXT,
        [],
        conversation_text="Hasta: Ateşim yok.",
        previous_source_fingerprint=first["source_fingerprint"],
    )
    assert unchanged["not_modified"] is True and len(calls) == 1
    changed = final.finalize(
        CONTEXT,
        [],
        conversation_text="Hasta: Ateşim var.",
        previous_source_fingerprint=first["source_fingerprint"],
    )
    assert not changed.get("not_modified") and len(calls) == 2


def test_final_accepts_supported_long_conversation_without_silent_truncation(
    monkeypatch,
):
    calls = provider(
        monkeypatch, {"questions": [], "contradictions": [], "clinical_items": []}
    )
    text = (
        "Hasta: Dişim ağrıyor.\n" * 3200
    ) + "Hekim: En son belirtiyi de inceleyelim."
    assert 18000 < len(text) <= 72000
    final.finalize(CONTEXT, [], conversation_text=text)
    assert json.loads(calls[0]["messages"][0]["content"])["conversation_text"] == text


@pytest.mark.parametrize("conversation", ["a" * 72001, None, 42, []])
def test_invalid_full_conversation_fails_before_public_or_private_paid_call(
    monkeypatch, conversation
):
    monkeypatch.setattr(
        final,
        "retrieve",
        lambda *a, **k: pytest.fail("Invalid conversation must fail before research"),
    )
    monkeypatch.setattr(
        final,
        "review",
        lambda *a, **k: pytest.fail("Invalid conversation must fail before provider"),
    )
    with pytest.raises(core.VoiceError):
        final.finalize(CONTEXT, [], conversation_text=conversation)


def test_final_endpoint_keeps_full_conversation_out_of_patient_and_job_records(
    app_client, monkeypatch
):
    client, engine = app_client
    calls = provider(
        monkeypatch, {"questions": [], "contradictions": [], "clinical_items": []}
    )
    text = "Hasta: Dişim ağrıyor. Hekim: Önce değerlendirelim."
    response = client.post(
        "/patients/1/voice-exam/finalize",
        json={"consent": True, "context": CONTEXT, "conversation_text": text},
    )
    assert response.status_code == 200
    assert json.loads(calls[0]["messages"][0]["content"])["conversation_text"] == text
    with Session(engine) as session:
        assert session.exec(select(Analysis)).all() == []
        assert session.exec(select(WorkJob)).all() == []
        patient = session.get(Patient, 1)
        assert (
            patient.first_name == "Mevcut" and patient.chief_complaint == "Eski şikâyet"
        )
    assert "no-store" in response.headers["cache-control"]


def test_identical_inflight_review_cannot_start_a_second_paid_final_call(monkeypatch):
    provider(monkeypatch, {"questions": [], "contradictions": [], "clinical_items": []})
    entered, release = threading.Event(), threading.Event()
    calls = []

    def held_review(*args):
        calls.append(1)
        entered.set()
        assert release.wait(3)
        return {"questions": [], "contradictions": [], "clinical_items": []}

    monkeypatch.setattr(final, "review", held_review)
    monkeypatch.setattr(core, "_capacity", threading.BoundedSemaphore(2))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(final.finalize, CONTEXT, [], request_scope=(1, 1))
        assert entered.wait(1)
        second = pool.submit(final.finalize, CONTEXT, [], request_scope=(1, 1))
        try:
            with pytest.raises(core.VoiceError):
                second.result(timeout=1)
        finally:
            release.set()
        assert first.result(timeout=1)["summary"]
    assert calls == [1]


def test_identical_clinical_context_for_distinct_owned_patients_can_run_in_parallel(
    app_client, monkeypatch
):
    client, engine = app_client
    provider(monkeypatch, {"questions": [], "contradictions": [], "clinical_items": []})
    with Session(engine) as session:
        session.add(Patient(id=3, owner_user_id=1, first_name="Berrin"))
        session.commit()
    entered, both_entered, release = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def held_review(*args):
        calls.append(1)
        entered.set()
        if len(calls) == 2:
            both_entered.set()
        assert release.wait(3)
        return {"questions": [], "contradictions": [], "clinical_items": []}

    monkeypatch.setattr(final, "review", held_review)
    monkeypatch.setattr(core, "_capacity", threading.BoundedSemaphore(2))
    assert client.post(
        "/patients/1/voice-exam/finalize",
        json={"consent": True, "context": CONTEXT, "request_scope": [1, 3]},
    ).status_code == 422
    first_context = {"fields": {**CONTEXT["fields"], "first_name": {"value": "Zeynep", "quote": "Zeynep"}}}
    other_context = {"fields": {**CONTEXT["fields"], "first_name": {"value": "Berrin", "quote": "Berrin"}}}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, "/patients/1/voice-exam/finalize",
                            json={"consent": True, "context": first_context})
        assert entered.wait(1)
        other = pool.submit(client.post, "/patients/3/voice-exam/finalize",
                            json={"consent": True, "context": other_context})
        try:
            assert both_entered.wait(1), "Separate patients must not share the pending-review key"
        finally:
            release.set()
        assert first.result(timeout=1).status_code == 200
        assert other.result(timeout=1).status_code == 200
    assert calls == [1, 1]
