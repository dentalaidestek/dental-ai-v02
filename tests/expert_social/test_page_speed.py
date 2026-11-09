"""Ready deployments avoid release DDL; directory reads use fixed-size queries."""
import pytest
from sqlalchemy import event
from starlette.requests import Request
from sqlmodel import Session
from app import main, migrate, expert_social_schema
from test_api import env


@pytest.mark.parametrize("ready", [True, False])
def test_ready_startup_skips_migration_but_missing_schema_is_upgraded(monkeypatch, ready):
    monkeypatch.setenv("RENDER", "1")
    monkeypatch.setenv("DENTAL_MIGRATE_ON_STARTUP", "1")
    monkeypatch.setattr(main, "validate_configuration", lambda: None)
    monkeypatch.setattr(main, "storage_check_connection", lambda: None)
    calls = []
    checks = []

    def require(candidate, **kwargs):
        checks.append(kwargs)
        if not ready and len(checks) == 1:
            raise RuntimeError("migration required")

    monkeypatch.setattr(migrate, "require_schema", require)
    monkeypatch.setattr(expert_social_schema, "require_schema", lambda candidate: None)
    monkeypatch.setattr(migrate, "apply", lambda: calls.append("migrate"))
    main._startup_database()
    assert calls == ([] if ready else ["migrate"])
    assert checks and all(c == {"require_study": True} for c in checks)
    if not ready:
        assert len(checks) == 2


def test_directory_query_count_does_not_grow_per_expert(env, monkeypatch, record_property):
    _, engine = env
    with Session(engine) as session:
        for ident in range(10, 40):
            session.add(main.User(id=ident, username=f"directory{ident}", role="DOCTOR", display_name=f"Uzman {ident}", email_verified_at=main._utcnow_naive()))
            session.add(main.ExpertProfile(user_id=ident, specialty="Ortodonti", application_status="APPROVED", verification_status="VERIFIED", specialty_verified=True, credential_document_path="synthetic.pdf", phone="05000000000", availability="AVAILABLE"))
        session.commit()
    statements = []
    def count(*args):
        statements.append(args[2])
    monkeypatch.setattr(main.templates, "TemplateResponse", lambda **kwargs: kwargs["context"])
    request = Request({"type": "http", "method": "GET", "path": "/expert-support", "headers": [(b"cookie", f"{main.SESSION_COOKIE}=t2".encode())]})
    event.listen(engine, "before_cursor_execute", count)
    try:
        context = main.expert_support_directory(request)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(context["experts"]) == 32
    record_property("directory_sql_statements", len(statements))
    assert len(statements) <= 18, f"Directory executed {len(statements)} SQL statements"


def test_startup_does_not_accept_schema_still_missing_after_migration(monkeypatch):
    monkeypatch.setenv("RENDER", "1")
    monkeypatch.setenv("DENTAL_MIGRATE_ON_STARTUP", "1")
    monkeypatch.setattr(main, "validate_configuration", lambda: None)
    monkeypatch.setattr(main, "storage_check_connection", lambda: None)
    monkeypatch.setattr(migrate, "require_schema", lambda *args, **kwargs: None)
    monkeypatch.setattr(migrate, "apply", lambda: None)

    def missing(candidate):
        raise RuntimeError("social schema still missing")

    monkeypatch.setattr(expert_social_schema, "require_schema", missing)
    with pytest.raises(RuntimeError, match="social schema still missing"):
        main._startup_database()


def test_versioned_public_css_is_compressed_and_cached_without_caching_html(env):
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    response = client.get('/static/expert-social.css?v=20261109-1', headers={'Accept-Encoding': 'gzip'})
    assert response.status_code == 200
    assert response.headers.get('content-encoding') == 'gzip'
    assert response.headers.get('cache-control') == 'public, max-age=86400'
    assert '.ds-comment-send' in response.text
