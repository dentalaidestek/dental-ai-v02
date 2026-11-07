"""Actual PostgreSQL round trips and pool contention; all data is synthetic."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, create_engine

from app import expert_publications, main
from app.expert_social_api import register
from app.expert_social_schema import apply
from test_backend_capacity import work
from test_postgres import pg_engine


def setup_social(engine, monkeypatch):
    for model in (
        main.User,
        main.ExpertProfile,
        main.ExpertPolicyState,
        main.SessionToken,
        main.AdminVerifiedSession,
        main.AuthRateBucket,
    ):
        model.__table__.create(engine, checkfirst=True)
    apply(engine)
    monkeypatch.setattr(main, "engine", engine)
    with Session(engine) as session:
        session.add(
            main.User(
                id=1,
                username="local-expert",
                role="DOCTOR",
                display_name="Local Expert",
                email_verified_at=main._utcnow_naive(),
            )
        )
        session.add(
            main.ExpertProfile(
                user_id=1,
                specialty="Ortodonti",
                application_status="APPROVED",
                verification_status="VERIFIED",
                specialty_verified=True,
                credential_document_path="private/local-test.pdf",
                phone="05300000000",
                availability="AVAILABLE",
            )
        )
        session.add(
            main.SessionToken(
                token_hash=main.hash_session_token("local-pg-token"),
                user_id=1,
                expires_at=main._utcnow_naive() + timedelta(days=1),
            )
        )
        session.commit()
    app = FastAPI()
    register(app, main)
    return app


def client(app):
    result = TestClient(app)
    result.cookies.set(main.SESSION_COOKIE, "local-pg-token")
    result.headers.update({"Origin": "http://testserver", "X-Dental-Social": "1"})
    return result


def test_full_orcid_import_batches_publications_and_audit_in_postgres(
    pg_engine, monkeypatch
):
    app = setup_social(pg_engine, monkeypatch)
    inserts = []

    async def sample(orcid):
        assert pg_engine.pool.checkedout() == 0
        return [work(i) for i in range(expert_publications.MAX_ORCID_WORKS)]

    def record(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith(
            ("INSERT INTO publication ", "INSERT INTO socialdecision ")
        ):
            inserts.append(statement.split()[2])

    monkeypatch.setattr(expert_publications, "orcid_works", sample)
    event.listen(pg_engine, "before_cursor_execute", record)
    try:
        result = client(app).post(
            "/api/expert-social/orcid/sync", json={"orcid": "0000-0002-1825-0097"}
        )
        assert result.status_code == 200, result.text
        assert result.json()["imported_count"] == 500
        assert inserts.count("publication") == 1, inserts
        assert inserts.count("socialdecision") == 1, inserts
        assert pg_engine.pool.checkedout() == 0
    finally:
        event.remove(pg_engine, "before_cursor_execute", record)


def test_four_writers_can_fill_a_four_connection_pool_without_nested_admission(
    pg_engine, monkeypatch
):
    small = create_engine(pg_engine.url, pool_size=4, max_overflow=0, pool_timeout=0.5)
    try:
        app = setup_social(small, monkeypatch)
        ready = threading.Barrier(4)

        def synchronize(
            connection, cursor, statement, parameters, context, executemany
        ):
            # All four writers hold a connection when their profile lock starts.
            # Three wait on the same row. The winner must not need a fifth
            # connection to reserve a shared rate allowance.
            if "FROM expertprofile" in statement and "FOR UPDATE" in statement:
                ready.wait(timeout=3)

        event.listen(small, "before_cursor_execute", synchronize)

        def submit(index):
            return client(app).post(
                "/api/expert-social/posts",
                json={
                    "text": f"Scientific discussion {index}",
                    "idempotency_key": str(uuid.uuid4()),
                },
            )

        with ThreadPoolExecutor(max_workers=4) as workers:
            responses = list(workers.map(submit, range(4)))
        assert [response.status_code for response in responses] == [200] * 4, [
            response.text for response in responses
        ]
        assert small.pool.checkedout() == 0
        assert small.pool.size() == 4 and small.pool.overflow() == 0
    finally:
        small.dispose()
