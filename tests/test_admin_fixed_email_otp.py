from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")
VERIFY = (ROOT / "app/templates/admin_verify.html").read_text(encoding="utf-8")


def test_fixed_mailbox_and_email_change_blocked():
    assert 'ADMIN_FIXED_EMAIL = "dentalaidestek@gmail.com"' in MAIN
    for name in ("begin_email_change(", "confirm_email_change("):
        block = MAIN.split("def " + name, 1)[1].split("\n\n", 1)[0]
        assert 'user.role == "ADMIN"' in block


def test_admin_login_never_creates_session_before_otp():
    login = MAIN.split("def admin_center_login(", 1)[1].split("@app.get(ADMIN_CENTER_PATH + \"/verify\"", 1)[0]
    assert "send_email_verification_code(ADMIN_FIXED_EMAIL, code)" in login
    assert "create_user_session(" not in login
    assert "secrets.randbelow(1000000)" in login


def test_admin_otp_is_single_use_and_rate_limited():
    block = MAIN.split("def admin_login_verify(", 1)[1].split("def _admin_user_storage_summaries", 1)[0]
    assert "challenge.used_at" in block
    assert "challenge.attempts >= 5" in block
    assert "challenge.expires_at <= now" in block
    assert "secrets.compare_digest" in block
    assert "create_user_session(response, user.id, admin_otp_verified=True)" in block
    assert "for old_session in" in block


def test_admin_template_uses_fixed_code_form():
    assert 'name="code"' in VERIFY
    assert 'autocomplete="one-time-code"' in VERIFY
    assert 'method="post"' in VERIFY


def test_standard_login_and_old_sessions_cannot_bypass_admin_otp():
    normal_login = MAIN.split('def login_user(', 1)[1].split('@app.post("/api/mobile/expert/device/check")', 1)[0]
    assert 'if user.role == "ADMIN":' in normal_login
    assert 'return RedirectResponse(ADMIN_CENTER_PATH' in normal_login
    assert 'elif not s.get(AdminVerifiedSession, token_hash):' in MAIN
    assert 'admin_otp_verified: bool = False' in MAIN


def test_otp_concurrency_and_malformed_attempt_protection():
    verify = MAIN.split('def admin_login_verify(', 1)[1].split('def _admin_user_storage_summaries', 1)[0]
    assert 'with_for_update()' in verify
    assert 'challenge.attempts += 1' in verify
    assert 'not re.fullmatch(r"[0-9]{6}", code.strip()) or' in verify
    assert 'for old_verified in' in verify


def test_code_delivery_throttling_and_fixed_recipient():
    login = MAIN.split('def admin_center_login(', 1)[1].split('@app.get(ADMIN_CENTER_PATH + "/verify"', 1)[0]
    assert 'timedelta(minutes=9)' in login
    assert 'send_email_verification_code(ADMIN_FIXED_EMAIL, code)' in login
    assert 'with_for_update()' in login


def test_existing_admin_email_migrates_only_after_otp():
    verify = MAIN.split('def admin_login_verify(', 1)[1].split('def _admin_user_storage_summaries', 1)[0]
    assert verify.index('secrets.compare_digest') < verify.index('user.email = ADMIN_FIXED_EMAIL')
