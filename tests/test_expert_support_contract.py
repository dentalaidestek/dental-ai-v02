from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
PROFILE = (ROOT / "app" / "templates" / "expert_profile_edit.html").read_text(encoding="utf-8")
CASE_ROOM = (ROOT / "app" / "templates" / "expert_case_room.html").read_text(encoding="utf-8")


def test_application_approval_does_not_auto_verify_identity_or_specialty():
    endpoint = MAIN.split("def admin_center_verify", 1)[1].split("@app.get", 1)[0]
    approve_branch = endpoint.split('if decision=="APPROVE":', 1)[1].split('elif decision=="REJECT":', 1)[0]
    assert 'application_status="APPROVED"' in approve_branch
    assert 'verification_status="PENDING"' in approve_branch
    assert 'identity_verified=False' in approve_branch
    assert 'specialty_verified=False' in approve_branch
    assert 'verification_status="VERIFIED"' not in approve_branch


def test_public_expert_queries_require_all_trust_gates():
    directory = MAIN.split("def expert_support_directory", 1)[1].split("@app.post", 1)[0]
    assert 'ExpertProfile.application_status == "APPROVED"' in directory
    assert 'ExpertProfile.verification_status == "VERIFIED"' in directory
    assert "ExpertProfile.identity_verified == True" in directory
    assert "ExpertProfile.specialty_verified == True" in directory


def test_profile_copy_keeps_approval_and_verification_separate():
    assert "Başvurunuz onaylandı" in PROFILE
    assert "Bu onay kimlik veya uzmanlık doğrulaması değildir" in PROFILE
    assert "Kimlik doğrulaması bekliyor" in PROFILE


def test_chat_has_read_receipt_and_inline_upload_error_contract():
    assert "✓✓ Okundu" in CASE_ROOM
    assert "composerInlineError" in CASE_ROOM
    assert "upload_max_mb" in CASE_ROOM
    assert "iyzico entegrasyonu henüz aktif değil" in CASE_ROOM

