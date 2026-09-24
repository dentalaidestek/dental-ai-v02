from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
PROFILE = (ROOT / "app" / "templates" / "expert_profile_edit.html").read_text(encoding="utf-8")
CASE_ROOM = (ROOT / "app" / "templates" / "expert_case_room.html").read_text(encoding="utf-8")


def test_admin_approval_is_single_professional_document_decision():
    endpoint = MAIN.split("def admin_center_verify", 1)[1].split("@app.get", 1)[0]
    approve_branch = endpoint.split('if decision=="APPROVE":', 1)[1].split('elif decision=="REJECT":', 1)[0]
    assert 'application_status="APPROVED"' in approve_branch
    assert 'verification_status="VERIFIED"' in approve_branch
    assert 'identity_verified=False' in approve_branch
    assert 'specialty_verified=True' in approve_branch
    assert "credential_document_path" in approve_branch
    assert "profile_photo_path" in approve_branch
    assert "profile.phone" in approve_branch


def test_public_expert_queries_require_professional_document_gate_only():
    directory = MAIN.split("def expert_support_directory", 1)[1].split("@app.post", 1)[0]
    assert 'ExpertProfile.application_status == "APPROVED"' in directory
    assert 'ExpertProfile.verification_status == "VERIFIED"' in directory
    assert "ExpertProfile.specialty_verified == True" in directory
    assert "ExpertProfile.identity_verified == True" not in directory


def test_profile_requires_phone_photo_and_e_government_document():
    assert 'name="phone"' in PROFILE
    assert 'name="profile_photo_data"' in PROFILE
    assert 'name="credential_document"' in PROFILE
    assert "Kimlik doğrulaması bekliyor" not in PROFILE
    assert "e-Devlet mesleki belge" in PROFILE


def test_chat_has_read_receipt_and_inline_upload_error_contract():
    assert "✓✓ Okundu" in CASE_ROOM
    assert "composerInlineError" in CASE_ROOM
    assert "upload_max_mb" in CASE_ROOM
    assert "iyzico entegrasyonu henüz aktif değil" in CASE_ROOM
