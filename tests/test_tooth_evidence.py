from vision_service.tooth_evidence import build_tooth_evidence_package


def test_multimodal_same_finding_fuses_without_score_math():
    results = [
        {"ok": True, "modality": "PANORAMIC", "findings": [{"finding_code": "CARIES", "label": "Çürük", "tooth_fdi": 46, "confidence": .71}]},
        {"ok": True, "modality": "INTRAORAL_PHOTO", "findings": [{"finding_code": "CARIES", "label": "Çürük", "tooth_fdi": 46, "confidence": .84}]},
    ]
    p = build_tooth_evidence_package(tooth_fdi=46, modality_results=results)
    assert len(p["fused_findings"]) == 1
    f = p["fused_findings"][0]
    assert f["evidence_count"] == 2
    assert f["supported_by"] == ["INTRAORAL_PHOTO", "PANORAMIC"]
    assert "confidence" not in f


def test_wrong_tooth_and_rejected_are_excluded():
    results = [{"ok": True, "modality": "PANORAMIC", "findings": [
        {"finding_code": "CARIES", "tooth_fdi": 45, "confidence": .9},
        {"finding_code": "CROWN", "tooth_fdi": 46, "confidence": .9, "review_state": "rejected"},
    ]}]
    p = build_tooth_evidence_package(tooth_fdi=46, modality_results=results)
    assert p["fused_findings"] == []


def test_unassigned_pai_is_not_guessed_onto_selected_tooth():
    results = [{"ok": True, "modality": "PERIAPICAL", "findings": [
        {"finding_code": "APICAL_PERIODONTITIS_PAI", "pai_score": 4, "confidence": .8, "image_level": True}
    ]}]
    p = build_tooth_evidence_package(tooth_fdi=46, modality_results=results)
    assert p["fused_findings"] == []
    assert len(p["unassigned_image_evidence"]) == 1


def test_tooth_record_and_manual_context_are_preserved():
    p = build_tooth_evidence_package(
        tooth_fdi=46,
        modality_results=[],
        tooth_record={"status": "crown", "history": ["RCT"]},
        manual_findings=["gece ağrısı", {"text": "perküsyon pozitif"}],
        clinical_context={"note": "hekim girişi"},
    )
    assert p["tooth_record"]["status"] == "crown"
    assert len(p["manual_findings"]) == 2
    assert p["clinical_context"]["note"] == "hekim girişi"
