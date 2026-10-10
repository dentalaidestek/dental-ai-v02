from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None

from app import main

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(TestClient is None, reason="Starlette TestClient is unavailable")
def test_security_headers_are_present_on_http_responses():
    with TestClient(main.app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(self), microphone=(self), geolocation=(), payment=()"


def test_web_login_rate_limiter_blocks_repeated_failures(monkeypatch):
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, create_engine
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    request = Request({"type": "http", "method": "POST", "path": "/login", "headers": [], "client": ("127.0.0.1", 44321)})
    monkeypatch.setattr(main, "WEB_LOGIN_RATE_MAX_FAILURES", 3)
    for _ in range(3):
        main._check_web_login_rate(request, "doctor@example.test")
    with pytest.raises(HTTPException) as exc:
        main._check_web_login_rate(request, "doctor@example.test")
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"]


def test_session_cookie_is_secure_and_http_only():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    session_block = source.split("def create_user_session", 1)[1].split("def delete_user_session", 1)[0]
    assert "httponly=True" in session_block
    assert "samesite=\"lax\"" in session_block
    assert "secure=True" in session_block
    assert "secure=False" not in session_block


def test_websocket_auth_does_not_accept_tokens_in_query_strings():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert 'query_params.get("access_token")' not in source
    assert "authorization" in source.lower()


def test_native_clinical_media_contract_is_bounded_and_does_not_expose_paths():
    source = (ROOT / "app/mobile_modern_api_v3.py").read_text(encoding="utf-8")
    assert "_copy_validated_image" in source
    assert "shutil.copyfileobj(file.file" not in source
    assert '"path":row.file_path' not in source
    assert 'Cache-Control":"private, no-store' in source
    block = source.split("async def mobile_upload_media", 1)[1].split("@router.get", 1)[0]
    assert 'allowed={".jpg",".jpeg",".png",".webp"}' in block
    assert "if ext not in allowed" in block


def test_native_app_disables_backup_and_cleartext():
    source = (ROOT / "mobile/app.json").read_text(encoding="utf-8")
    assert '"allowBackup": false' in source
    assert '"usesCleartextTraffic": false' in source


def test_protected_clinical_media_is_not_browser_cached():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    start = source.index("def patient_media_file")
    block = source[start:source.index("def delete_patient_media", start)]
    assert 'Cache-Control":"private, no-store' in block


def test_admin_login_uses_same_brute_force_throttle():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split('def admin_center_login', 1)[1].split('def _admin_user_storage_summaries', 1)[0]
    assert "_check_web_login_rate" in block
    assert "_record_web_login_failure" in block
    assert "_clear_web_login_failures" in block


def test_session_cookie_has_explicit_root_path_and_logout_clears_same_path():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    session_block = source.split("def create_user_session", 1)[1].split("def delete_user_session", 1)[0]
    assert 'path="/"' in session_block
    logout_block = source.split('@app.post("/logout")', 1)[1].split('app.mount("/static"', 1)[0]
    assert 'delete_cookie(SESSION_COOKIE, path="/")' in logout_block
    assert 'delete_cookie("dai_push_subscription_id", path="/")' in logout_block


def test_password_change_clears_browser_session_cookie_after_revocation():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split('@app.post("/account/password"', 1)[1].split('def _safe_login_next', 1)[0]
    assert 'response.delete_cookie(SESSION_COOKIE, path="/")' in block


def test_password_change_revokes_existing_sessions():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split('@app.post("/account/password"', 1)[1].split('def _safe_login_next', 1)[0]
    assert "select(SessionToken).where(SessionToken.user_id == user.id)" in block
    assert "s.delete(session_token)" in block


def test_anatomy_direct_service_requires_internal_key_and_bounds_upload():
    source = (ROOT / "vision_service/anatomy3d_direct_app.py").read_text(encoding="utf-8")
    assert "require_anatomy_key" in source
    assert 'Depends(require_anatomy_key)' in source
    assert "MAX_IMAGE_BYTES" in source
    assert "MAX_IMAGE_PIXELS" in source
    assert "probe.verify()" in source


def test_password_reset_link_does_not_trust_request_host_header():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split('@app.post("/forgot-password")', 1)[1].split('@app.get("/reset-password"', 1)[0]
    assert 'request.base_url' not in block
    assert 'os.getenv("PUBLIC_BASE_URL") or "https://dentalai.tr"' in block
    assert 'public_base.username' in block
    assert 'public_base.password' in block


def test_password_reset_requests_are_throttled():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split('@app.post("/forgot-password")', 1)[1].split('@app.get("/reset-password"', 1)[0]
    assert "_check_web_login_rate" in block
    assert "_record_web_login_failure" in block
    assert "password-reset:" in block


def test_native_analysis_assets_are_not_browser_cached():
    source = (ROOT / "app/mobile_analysis_api.py").read_text(encoding="utf-8")
    assert 'Cache-Control": "private, no-store"' in source


def test_clinical_ai_router_redacts_direct_patient_identifiers():
    source = (ROOT / "app/clinical_rag_router.py").read_text(encoding="utf-8")
    assert "_provider_safe_text" in source
    assert "_PROVIDER_EMAIL_RE" in source
    assert "_PROVIDER_PHONE_RE" in source
    assert "_PROVIDER_TC_RE" in source


def test_websocket_endpoints_enforce_browser_origin_policy():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "def _socket_origin_allowed" in source
    sync = source.split('@app.websocket("/ws/sync")', 1)[1].split('@app.websocket("/ws/expert-support/cases/{case_id}")', 1)[0]
    expert = source.split('@app.websocket("/ws/expert-support/cases/{case_id}")', 1)[1].split('@app.post("/expert-support/cases/{case_id}/review")', 1)[0]
    assert "_socket_origin_allowed(websocket)" in sync
    assert "_socket_origin_allowed(websocket)" in expert
    assert "WEB_ALLOWED_ORIGINS" in source


def test_email_verification_is_one_time_and_has_bounded_lifetime():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "class EmailVerificationChallenge" in source
    assert "user_id: int = Field(index=True, unique=True)" in source
    assert "public_token: str = Field(index=True, unique=True)" in source
    assert "email_verified_at" in source
    assert "def _ensure_email_verification_challenge" in source
    assert "def _verify_email_code" in source
    assert "attempts >= 5" in source
    assert "timedelta(minutes=10)" in source
    assert "def resend_email" not in source


def test_web_login_blocks_unverified_users_before_session_creation():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split('@app.post("/login")', 1)[1].split('@app.post("/api/mobile/expert/device/check")', 1)[0]
    assert "if not user.email_verified_at" in block
    assert "_ensure_email_verification_challenge" in block
    assert "create_user_session(response, user.id)" in block


def test_native_login_requires_shared_email_verification():
    source = (ROOT / "app/mobile_api.py").read_text(encoding="utf-8")
    block = source.split("def mobile_login(", 1)[1].split('@router.post("/auth/logout")', 1)[0]
    assert "if not user.email_verified_at" in block
    assert "_ensure_email_verification_challenge" in block
    assert "challenge_token=challenge.public_token" in block


def test_existing_web_and_native_sessions_cannot_bypass_email_verification():
    main_source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    web_block = main_source.split("def get_current_user", 1)[1].split("def create_user_session", 1)[0]
    assert "not user.email_verified_at" in web_block

    mobile_source = (ROOT / "app/mobile_api.py").read_text(encoding="utf-8")
    mobile_block = mobile_source.split("def _mobile_user", 1)[1].split("def _user_payload", 1)[0]
    assert "not user.email_verified_at" in mobile_block


def test_public_vision_health_does_not_fingerprint_models():
    source = (ROOT / "vision_service/app.py").read_text(encoding="utf-8")
    block = source.split('@app.get("/health")', 1)[1].split('@app.get("/viewer")', 1)[0]
    assert '"service": "dental-ai-vision"' in block
    assert "catalog_total" not in block
    assert "implementation_total" not in block


def test_main_app_has_global_request_admission_limits():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "from app.request_limits import RequestLimits" in source
    assert "app.add_middleware(RequestLimits" in source


def test_registration_has_ip_abuse_rate_limit():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split('@app.post("/register")', 1)[1].split('@app.post("/login")', 1)[0]
    assert "_check_registration_rate(request)" in block
    assert "_record_registration_attempt(registration_rate_key)" in block
    assert "REGISTRATION_MAX_ATTEMPTS" in source


def test_email_verification_is_single_use_and_strictly_bounded():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split("def _verify_email_code", 1)[1].split("def send_expert_device_code", 1)[0]
    assert 're.fullmatch(r"\\d{6}", normalized_code)' in block
    assert "challenge.verified_at" in block
    assert "challenge.code_hash = secrets.token_urlsafe(32)" in block
    assert "challenge.attempts >= 5" in block


def test_native_and_web_share_email_verification_state():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    mobile = (ROOT / "app/mobile_api.py").read_text(encoding="utf-8")
    assert "email_verified_at" in main
    assert "/auth/verify-email" in mobile
    assert "EmailVerificationChallenge" in mobile


def test_selected_get_handlers_are_side_effect_free():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    for route in ['@app.get("/messages"', '@app.get("/expert-support/expert/{expert_user_id}"']:
        start = source.index(route)
        end = source.find("\n@app.", start + 10)
        block = source[start:end if end != -1 else len(source)]
        assert "_consultation_event(" not in block
        assert "_expire_pending_expert_requests(" not in block


def test_email_verification_serializes_replay_and_attempt_races():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split("def _verify_email_code", 1)[1].split("def send_expert_device_code", 1)[0]
    assert "select(EmailVerificationChallenge)" in block
    assert "with_for_update()" in block
    assert "locked_challenge.verified_at" in block
    assert "locked_challenge.attempts >= 5" in block
    assert "select(SessionToken).where(SessionToken.user_id == user.id)" in block
    assert "session.delete(stale_session)" in block


def test_admin_login_requires_verified_email_before_session_creation():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split("def admin_center_login(", 1)[1].split("def _admin_user_storage_summaries", 1)[0]
    assert "user.email_verified_at" in block
    assert "create_user_session(response,user.id)" in block


def test_password_reset_expires_browser_session_cookie_after_server_revocation():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split('@app.post("/reset-password")', 1)[1].split('@app.post("/logout")', 1)[0]
    assert "select(SessionToken).where(SessionToken.user_id==user.id)" in "".join(block.split())
    assert "s.delete(session_token)" in block
    assert 'response.delete_cookie(SESSION_COOKIE, path="/")' in block


def test_account_deletion_expires_browser_cookies_with_root_path():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split('@app.post("/account/delete")', 1)[1]
    assert 'response.delete_cookie(SESSION_COOKIE, path="/")' in block


def test_native_media_file_enforces_media_owner_as_well_as_patient_owner():
    source = (ROOT / "app/mobile_api.py").read_text(encoding="utf-8")
    block = source.split('def mobile_patient_media_file', 1)[1].split('def _mobile_access_token', 1)[0]
    assert 'media.patient_id!=patient_id' in block
    assert 'media.owner_user_id!=user.id' in block
    assert 'Cache-Control":"private, no-store' in block

def test_e2ee_message_storage_has_ciphertext_envelopes_without_forcing_plaintext():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    consultation = source.split("class ConsultationMessage", 1)[1].split("class ConsultationEvent", 1)[0]
    support = source.split("class SupportTicketMessage", 1)[1].split("class SupportTicketReadState", 1)[0]
    for block in (consultation, support):
        assert "e2ee_ciphertext" in block
        assert "e2ee_ephemeral_public_key" in block
        assert "e2ee_key_version" in block
    assert "message: Optional[str] = None" in support


def test_e2ee_device_keys_are_client_public_keys_and_migration_is_versioned():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "class E2EEDeviceKey" in source
    assert "public_key: str" in source
    assert "revoked_at" in source
    migration = (ROOT / "app/migrate.py").read_text(encoding="utf-8")
    assert "REVISION = 12" in migration
    assert "e2eedevicekey" in migration
    assert "consultationmessage ADD COLUMN IF NOT EXISTS e2ee_ciphertext" in migration
    assert "supportticketmessage ADD COLUMN IF NOT EXISTS e2ee_ciphertext" in migration


def test_mobile_e2ee_uses_x25519_and_authenticated_xchacha_and_device_only_storage():
    source = (ROOT / "mobile/src/e2ee.ts").read_text(encoding="utf-8")
    assert '@noble/curves/ed25519.js' in source
    assert "x25519.getSharedSecret" in source
    assert '@noble/ciphers/chacha.js' in source
    assert "xchacha20poly1305" in source
    assert "WHEN_UNLOCKED_THIS_DEVICE_ONLY" in source
    assert "Math.random" not in source



def test_e2ee_device_key_lifecycle_has_peer_scope_rotation_and_revocation():
    source = (ROOT / "app/mobile_api.py").read_text(encoding="utf-8")
    assert 'def _e2ee_peer_allowed' in source
    assert '@router.get("/e2ee/users/{user_id}/keys")' in source
    assert '@router.delete("/e2ee/device/{device_id}")' in source
    keys_block = source.split('@router.get("/e2ee/users/{user_id}/keys")', 1)[1].split('@router.get("/e2ee/users/{user_id}/key")', 1)[0]
    assert "revoked_at == None" in keys_block
    assert "ConsultationCase" in source
    revoke_block = source.split('@router.delete("/e2ee/device/{device_id}")', 1)[1].split('@router.post("/auth/login")', 1)[0]
    assert "E2EEDeviceKey.user_id == user.id" in revoke_block
    assert "row.revoked_at = datetime.utcnow()" in revoke_block


def test_mobile_api_exposes_e2ee_device_rotation_contract():
    source = (ROOT / "mobile/src/api.ts").read_text(encoding="utf-8")
    assert "registerE2EEDevice" in source
    assert "getE2EEUserKeys" in source
    assert "revokeE2EEDevice" in source
    assert "/e2ee/users/" in source


def test_e2ee_device_migration_generates_primary_keys():
    source = (ROOT / "app/migrate.py").read_text(encoding="utf-8")
    assert "id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY" in source


def test_private_document_responses_are_not_cacheable():
    MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert 'return FileResponse(path, media_type=mime_type, headers={"Cache-Control": "private, no-store"})' in MAIN
    assert 'content_disposition_type="inline", headers={"Cache-Control": "private, no-store"}' in MAIN
