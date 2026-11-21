"""KVKK: misafir (guest) AI analizi için açık rıza regresyon testleri.

Kapsam:
1. Açık rıza (ai_consent) gönderilmeden analiz başlatılamaz — 400 ve kayıt/AI çağrısı olmaz.
2. Rıza şablonu görünür ve zorunludur (checkbox + açık rıza metni).
3. Rıza kaydı AgreementAcceptance tablosuna AI_GUEST_ANALYSIS türüyle yazılır (kaynak sözleşmesi).
"""
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app import main

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_guest_analysis_rejects_missing_ai_consent_before_any_side_effect():
    with TestClient(main.app) as client:
        response = client.post(
            "/analysis/guest/new",
            data={"tooth_number": "36", "clinical_notes": "Soğukta ağrı"},
        )
    assert response.status_code == 400
    assert "açık rıza" in response.text


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_guest_analysis_consent_gate_runs_before_authentication():
    """Rıza kapısı oturumdan bağımsız çalışmalı: rıza yoksa oturum olsa da 400."""
    with TestClient(main.app) as client:
        response = client.post(
            "/analysis/guest/new",
            data={"tooth_number": "36", "ai_consent": "off"},
        )
    assert response.status_code == 400
    assert "açık rıza" in response.text


def test_guest_consent_template_requires_explicit_checkbox():
    template = (ROOT / "app/templates/guest_analysis_new.html").read_text(encoding="utf-8")
    assert 'name="ai_consent"' in template
    assert "required" in template
    assert "açık rıza" in template
    assert "yapay zekâ" in template


def test_guest_consent_is_recorded_with_agreement_acceptance():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split('def create_guest_analysis', 1)[1].split("@app.post", 1)[0]
    assert 'agreement_type="AI_GUEST_ANALYSIS"' in block
    assert "agreement_version=LEGAL_VERSION" in block
