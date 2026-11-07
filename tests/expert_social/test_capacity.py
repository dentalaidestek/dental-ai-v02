"""Opt-in local synthetic scale probe. Never reads production credentials or sends AI requests."""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from statistics import median

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, insert, text
from sqlmodel import Session, create_engine

from app import main
from app.expert_social_api import register
from app.expert_social_models import SocialPost, SocialComment, SocialLike
from app.expert_social_schema import apply
from test_postgres import pg_engine


@pytest.mark.skipif(
    os.getenv("TEST_RUN_CAPACITY") != "1",
    reason="Opt-in isolated synthetic scale probe",
)
def test_sixty_thousand_accounts_and_posts_with_four_connection_pool(
    pg_engine, monkeypatch, tmp_path, request
):
    engine = create_engine(pg_engine.url, pool_size=4, max_overflow=0, pool_timeout=5)
    request.addfinalizer(engine.dispose)
    for model in (
        main.User,
        main.ExpertProfile,
        main.ExpertPolicyState,
        main.SessionToken,
        main.AuthRateBucket,
        main.AdminVerifiedSession,
    ):
        model.__table__.create(engine, checkfirst=True)
    apply(engine)
    monkeypatch.setattr(main, "engine", engine)
    count = 60000
    with engine.begin() as c:
        for offset in range(0, count, 1000):
            c.execute(
                insert(main.User),
                [
                    dict(
                        id=i,
                        username=f"synthetic{i}",
                        display_name="Synthetic member",
                        role="DOCTOR",
                        email_verified_at=main._utcnow_naive(),
                    )
                    for i in range(offset + 1, offset + 1001)
                ],
            )
            c.execute(
                insert(SocialPost),
                [
                    dict(
                        id=i,
                        author_id=1,
                        text="Bilimsel araştırma üzerine paylaşım",
                        status="PUBLISHED",
                        idempotency_key=f"seed{i}",
                        request_hash="synthetic",
                    )
                    for i in range(offset + 1, offset + 1001)
                ],
            )
            c.execute(
                insert(SocialComment),
                [
                    dict(
                        id=i,
                        author_id=i,
                        post_id=i,
                        text="Bilimsel yorum",
                        status="PUBLISHED",
                        idempotency_key=f"comment{i}",
                    )
                    for i in range(offset + 1, offset + 1001)
                ],
            )
            c.execute(
                insert(SocialLike),
                [dict(post_id=i, user_id=i) for i in range(offset + 1, offset + 1001)],
            )
        c.execute(text("ANALYZE"))
    with Session(engine) as s:
        s.add(
            main.ExpertProfile(
                user_id=1,
                specialty="Ortodonti",
                application_status="APPROVED",
                verification_status="VERIFIED",
                specialty_verified=True,
                credential_document_path="synthetic/doc",
                phone="05300000000",
                availability="AVAILABLE",
            )
        )
        s.add(
            main.SessionToken(
                user_id=2,
                token_hash=main.hash_session_token("capacity-token"),
                expires_at=main._utcnow_naive() + timedelta(hours=1),
            )
        )
        s.commit()
    app = FastAPI()
    register(app, main)
    active = 0
    peak = 0
    queries = 0
    lock = threading.Lock()

    def checked_out(*args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(active, peak)

    def checked_in(*args):
        nonlocal active
        with lock:
            active -= 1

    def executed(*args):
        nonlocal queries
        with lock:
            queries += 1

    event.listen(engine, "checkout", checked_out)
    event.listen(engine, "checkin", checked_in)
    event.listen(engine, "before_cursor_execute", executed)

    def fetch(path):
        started = time.perf_counter()
        client = TestClient(app)
        try:
            client.cookies.set(main.SESSION_COOKIE, "capacity-token")
            response = client.get(path)
        finally:
            client.close()
        return (
            response.status_code,
            (time.perf_counter() - started) * 1000,
            response.json(),
        )

    # Query bound must not grow with the stored post count or page offset.
    measurements = []
    for path in (
        "/api/expert-social/experts/1/posts",
        "/api/expert-social/experts/1/posts?before=30000",
    ):
        before = queries
        status, ms, payload = fetch(path)
        assert status == 200 and len(payload["items"]) == 15
        measurements.append(
            dict(path=path, queries=queries - before, latency_ms=round(ms, 2))
        )
    assert max(row["queries"] for row in measurements) <= 15
    assert (
        abs(measurements[0]["queries"] - measurements[1]["queries"]) <= 1
    )  # first page also checks the pin
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(
            pool.map(lambda _: fetch("/api/expert-social/experts/1/posts"), range(100))
        )
    wall = time.perf_counter() - started
    assert all(status == 200 for status, _, _ in results)
    assert peak <= 4 and active == 0
    latency = sorted(ms for _, ms, _ in results)
    report = dict(
        scope="Local FastAPI social router and actual authentication, PostgreSQL; excludes lifespan workers, CDN/network/media/providers and full page middleware",
        synthetic_accounts=count,
        synthetic_posts=count,
        synthetic_comments=count,
        synthetic_likes=count,
        requests=100,
        concurrency=16,
        pool_size=4,
        peak_checked_out=peak,
        errors=0,
        requests_per_second=round(100 / wall, 2),
        p50_ms=round(median(latency), 2),
        p95_ms=round(latency[94], 2),
        query_samples=measurements,
    )
    dest = Path(os.getenv("TEST_ARTIFACT_DIR", str(tmp_path)))
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "capacity-60000.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(json.dumps(report, ensure_ascii=False))
    engine.dispose()
