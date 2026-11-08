"""Optional real PostgreSQL migration and concurrent request tests.

TEST_POSTGRES_BIN points to an installed PostgreSQL bin directory. No production
connection is read; this test creates an isolated cluster and TCP-only listener.
"""

import os
import socket
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import text, inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import main
from app.expert_social_api import register
from app.expert_social_models import SocialPost
from app.expert_social_schema import apply, require_schema
from datetime import timedelta
import uuid


@pytest.fixture
def pg_engine(tmp_path):
    binary = os.getenv("TEST_POSTGRES_BIN")
    if not binary:
        pytest.skip("Set TEST_POSTGRES_BIN for the isolated PostgreSQL test")
    binary = Path(binary)
    data = tmp_path / "pgdata"
    subprocess.run(
        [
            str(binary / "initdb"),
            "-D",
            str(data),
            "-A",
            "trust",
            "--no-locale",
            "--encoding=UTF8",
        ],
        check=True,
        capture_output=True,
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    log = (tmp_path / "pg.log").open("w")
    process = subprocess.Popen(
        [
            str(binary / "postgres"),
            "-D",
            str(data),
            "-k",
            "",
            "-h",
            "127.0.0.1",
            "-p",
            str(port),
        ],
        stdout=log,
        stderr=log,
    )
    engine = create_engine(
        f'postgresql+psycopg2://{os.getenv("USER","agent")}@127.0.0.1:{port}/postgres',
        pool_size=10,
    )
    for _ in range(100):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except Exception:
            time.sleep(0.05)
    else:
        raise AssertionError("Test PostgreSQL did not start")
    yield engine
    engine.dispose()
    process.terminate()
    process.wait(timeout=5)
    log.close()


def test_postgres_migration_idempotency_and_single_pin(pg_engine, monkeypatch):
    # Real baseline compatibility: only the existing account/profile tables are
    # prerequisites, not a replay of unrelated clinical migrations.
    for model in (
        main.User,
        main.ExpertProfile,
        main.ExpertPolicyState,
        main.SessionToken,
        main.AdminVerifiedSession,
        main.AdminNotice,
        main.RealtimeEvent,
        main.UserBlock,
        main.AuthRateBucket,
    ):
        model.__table__.create(pg_engine, checkfirst=True)
    with pytest.raises(RuntimeError):
        require_schema(pg_engine)
    apply(pg_engine)
    apply(pg_engine)
    require_schema(pg_engine)
    monkeypatch.setattr(main, "engine", pg_engine)
    with Session(pg_engine) as s:
        s.add(
            main.User(
                id=1,
                username="pgexpert",
                role="DOCTOR",
                display_name="PG Expert",
                email_verified_at=main._utcnow_naive(),
            )
        )
        s.add(
            main.ExpertProfile(
                user_id=1,
                specialty="Ortodonti",
                application_status="APPROVED",
                verification_status="VERIFIED",
                specialty_verified=True,
                credential_document_path="private/doc",
                phone="05300000000",
                availability="AVAILABLE",
            )
        )
        s.add(
            main.SessionToken(
                token_hash=main.hash_session_token("pg-token"),
                user_id=1,
                expires_at=main._utcnow_naive() + timedelta(days=1),
            )
        )
        s.commit()
    app = FastAPI()
    register(app, main)
    key = str(uuid.uuid4())

    def submit():
        client = TestClient(app)
        client.cookies.set(main.SESSION_COOKIE, "pg-token")
        client.headers.update({"X-Dental-Social": "1", "Origin": "http://testserver"})
        return client.post(
            "/api/expert-social/posts",
            json={"text": "Concurrent scientific post", "idempotency_key": key},
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: submit(), range(4)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert len({r.json()["id"] for r in responses}) == 1
    with Session(pg_engine) as s:
        assert len(s.exec(select(SocialPost)).all()) == 1
    # Enforce the single-pin invariant at database level too.
    with Session(pg_engine) as s:
        first = s.exec(select(SocialPost)).one()
        first.pinned = True
        s.add(first)
        s.commit()
        s.add(
            SocialPost(
                author_id=1,
                text="Other",
                status="PUBLISHED",
                pinned=True,
                idempotency_key=str(uuid.uuid4()),
                request_hash="test",
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_publication_owner_edit_and_admin_review_serialize(pg_engine, monkeypatch):
    for model in (
        main.User,
        main.ExpertProfile,
        main.ExpertPolicyState,
        main.SessionToken,
        main.AdminVerifiedSession,
        main.AdminNotice,
        main.RealtimeEvent,
        main.UserBlock,
        main.AuthRateBucket,
    ):
        model.__table__.create(pg_engine, checkfirst=True)
    apply(pg_engine)
    monkeypatch.setattr(main, "engine", pg_engine)
    with Session(pg_engine) as s:
        s.add(
            main.User(
                id=1,
                username="pgexpert",
                role="DOCTOR",
                display_name="PG Expert",
                email_verified_at=main._utcnow_naive(),
            )
        )
        s.add(
            main.User(
                id=4,
                username="pgadmin",
                role="ADMIN",
                display_name="PG Admin",
                email=main.ADMIN_FIXED_EMAIL,
                email_verified_at=main._utcnow_naive(),
            )
        )
        s.add(
            main.ExpertProfile(
                user_id=1,
                specialty="Ortodonti",
                application_status="APPROVED",
                verification_status="VERIFIED",
                specialty_verified=True,
                credential_document_path="private/doc",
                phone="05300000000",
                availability="AVAILABLE",
            )
        )
        for ident, token in ((1, "pg-owner"), (4, "pg-admin")):
            s.add(
                main.SessionToken(
                    token_hash=main.hash_session_token(token),
                    user_id=ident,
                    expires_at=main._utcnow_naive() + timedelta(days=1),
                )
            )
        s.add(
            main.AdminVerifiedSession(
                token_hash=main.hash_session_token("pg-admin"), user_id=4
            )
        )
        s.commit()
    app = FastAPI()
    register(app, main)

    def client(token):
        c = TestClient(app)
        c.cookies.set(main.SESSION_COOKIE, token)
        c.headers.update({"X-Dental-Social": "1", "Origin": "http://testserver"})
        return c

    original = (
        client("pg-owner")
        .post("/api/expert-social/publications", json={"title": "Bilimsel makale"})
        .json()
    )

    def edit():
        return client("pg-owner").put(
            "/api/expert-social/publications/" + str(original["id"]),
            json={"title": "Hasta adı: Ayşe Yılmaz", "version": original["version"]},
        )

    def review():
        return client("pg-admin").post(
            "/api/expert-social/moderation/PUBLICATION/" + str(original["id"]),
            json={
                "status": "PUBLISHED",
                "version": original["version"],
                "reason": "Kaynak bilgisi incelendi",
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(edit)
        b = pool.submit(review)
        responses = [a.result(), b.result()]
    assert sorted(r.status_code for r in responses) == [200, 409], [
        r.text for r in responses
    ]
    from app.expert_social_models import Publication

    with Session(pg_engine) as s:
        result = s.get(Publication, original["id"])
        assert result.version == 2
        assert result.status != "PUBLISHED" or result.title == "Bilimsel makale"


def test_release_migration_upgrades_existing_revision_12_before_web_start(
    pg_engine, monkeypatch
):
    from sqlmodel import SQLModel
    from app.expert_social_models import SOCIAL_MODELS
    from app import migrate

    SQLModel.metadata.create_all(pg_engine)
    with pg_engine.begin() as connection:
        for model in reversed(SOCIAL_MODELS):
            model.__table__.drop(connection)
        connection.execute(
            text(
                "CREATE TABLE dental_schema_revision(id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO dental_schema_revision(id,version) VALUES(1,12)")
        )
    monkeypatch.setattr(main, "engine", pg_engine)
    with pytest.raises(RuntimeError):
        require_schema(pg_engine)
    migrate.apply()
    migrate.apply()
    require_schema(pg_engine)
    with pg_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version FROM dental_schema_revision WHERE id=1")
            ).scalar_one()
            == 12
        )
