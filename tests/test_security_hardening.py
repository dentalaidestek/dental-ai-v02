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
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/login",
        "headers": [],
        "client": ("127.0.0.1", 44321),
    })
    monkeypatch.setattr(main, "WEB_LOGIN_RATE_MAX_FAILURES", 3)
    monkeypatch.setattr(main, "_WEB_LOGIN_FAILURES", {})
    key = main._web_login_key(request, "doctor@example.test")
    for _ in range(3):
        main._record_web_login_failure(key)
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
    assert ".heic" not in source


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


def test_password_reset_requests_are_throttled():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    block = source.split('@app.post("/forgot-password")', 1)[1].split('@app.get("/reset-password"', 1)[0]
    assert "_check_web_login_rate" in block
    assert "_record_web_login_failure" in block
    assert "password-reset:" in block


def test_native_analysis_assets_are_not_browser_cached():
    source = (ROOT / "app/mobile_analysis_api.py").read_text(encoding="utf-8")
    assert 'Cache-Control": "private, no-store"' in source
