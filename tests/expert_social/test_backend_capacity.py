"""Local-only regressions for abuse bounds and small shared database pools."""

import asyncio
import io
import tracemalloc
import uuid

import pytest
from PIL import Image
from sqlmodel import Session, create_engine, select

from app import expert_publications, expert_social_api, main, object_storage
from app.expert_social_api import SocialBodyLimitMiddleware
from app.expert_social_models import OrcidSync, Publication, SocialMediaDeletion
from test_api import env, post


@pytest.mark.parametrize("action", ["post", "comment", "admin_read"])
def test_social_write_does_not_need_a_second_pool_connection(env, monkeypatch, action):
    client, engine = env
    if action != "post":
        original = post(client).json()
        client.cookies.set(
            main.SESSION_COOKIE, "t4" if action == "admin_read" else "t2"
        )
    # One connection is enough for a serial request. This also detects a
    # pool-wide stall when every concurrent request has its first connection.
    small_pool = create_engine(
        engine.url,
        connect_args={"check_same_thread": False},
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.05,
    )
    monkeypatch.setattr(main, "engine", small_pool)
    try:
        if action == "post":
            response = post(client)
        elif action == "comment":
            response = client.post(
                f"/api/expert-social/posts/{original['id']}/comments",
                json={"text": "Bilimsel görüş", "idempotency_key": str(uuid.uuid4())},
            )
        else:
            response = client.get(f"/api/expert-social/posts/{original['id']}")
        assert response.status_code == 200, response.text
        assert small_pool.pool.checkedout() == 0
    finally:
        small_pool.dispose()


def test_demoted_expert_cannot_publish_or_remain_in_member_social_views(env):
    client, engine = env
    original = post(client).json()
    paper = client.post(
        "/api/expert-social/publications", json={"title": "Bilimsel kaynak"}
    )
    assert paper.status_code == 200, paper.text
    with Session(engine) as session:
        user = session.get(main.User, 1)
        user.role = "STUDENT"
        session.add(user)
        session.commit()
    assert post(client, text="Yeni kaynak").status_code == 403
    client.cookies.set(main.SESSION_COOKIE, "t2")
    for path in (
        "/experts/1/stats",
        "/experts/1/posts",
        "/experts/1/publications",
        f"/posts/{original['id']}",
    ):
        response = client.get("/api/expert-social" + path)
        assert response.status_code == 404, (path, response.text)


def test_verified_admin_expert_can_still_publish_with_current_mfa(env):
    client, engine = env
    with Session(engine) as session:
        profile = session.exec(
            select(main.ExpertProfile).where(main.ExpertProfile.user_id == 1)
        ).one()
        session.add(
            main.ExpertProfile(
                user_id=4, **profile.model_dump(exclude={"id", "user_id"})
            )
        )
        session.commit()
    client.cookies.set(main.SESSION_COOKIE, "t4")
    response = post(client)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "PUBLISHED"


def test_request_buffer_memory_is_bounded_even_for_empty_chunks():
    async def run():
        count = 20_000

        async def receive():
            nonlocal count
            count -= 1
            return {
                "type": "http.request",
                "body": b"x" if count == 0 else b"",
                "more_body": count > 0,
            }

        async def app(scope, incoming, send):
            body = bytearray()
            while True:
                message = await incoming()
                body.extend(message.get("body", b""))
                if not message.get("more_body"):
                    break
            assert body == b"x"

        async def send(message):
            pass

        middleware = SocialBodyLimitMiddleware(app)
        await middleware(
            {"type": "http", "path": "/api/expert-social/posts", "method": "POST"},
            receive,
            send,
        )
        assert middleware.active == 0

    tracemalloc.start()
    try:
        asyncio.run(run())
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1024 * 1024, f"Tiny request retained {peak} bytes of chunk metadata"


def test_slow_body_times_out_and_releases_the_upload_slot(monkeypatch):
    monkeypatch.setattr(expert_social_api, "BODY_READ_TIMEOUT", 0.01, raising=False)

    async def run():
        response = []
        entered_app = False

        async def receive():
            await asyncio.Event().wait()

        async def app(scope, receive, send):
            nonlocal entered_app
            entered_app = True

        async def send(message):
            response.append(message)

        middleware = SocialBodyLimitMiddleware(app)
        await asyncio.wait_for(
            middleware(
                {"type": "http", "path": "/api/expert-social/media", "method": "POST"},
                receive,
                send,
            ),
            timeout=0.2,
        )
        assert response[0]["status"] == 408
        assert middleware.active == 0 and middleware.uploads == 0
        assert entered_app is False

    asyncio.run(run())


def work(index):
    return {
        "title": f"Bilimsel çalışma {index}",
        "authors": "",
        "year": 2025,
        "journal": "Dergi",
        "doi": f"10.1000/work{index}",
        "url": f"https://doi.org/10.1000/work{index}",
        "source": "ORCID",
        "source_key": str(index),
        "description": "",
    }


def test_oversized_orcid_import_fails_atomically_and_preserves_saved_work(
    env, monkeypatch
):
    client, engine = env
    saved = client.post(
        "/api/expert-social/publications", json={"title": "Kaydedilmiş kaynak"}
    ).json()

    async def oversized(orcid):
        return [work(i) for i in range(501)]

    monkeypatch.setattr(expert_publications, "orcid_works", oversized)
    response = client.post(
        "/api/expert-social/orcid/sync", json={"orcid": "0000-0002-1825-0097"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "ORCID_WORK_LIMIT"
    with Session(engine) as session:
        assert [row.id for row in session.exec(select(Publication)).all()] == [
            saved["id"]
        ]
        assert session.get(OrcidSync, 1).status == "FAILED"


def test_orcid_parser_has_a_record_limit():
    data = {
        "group": [
            {
                "work-summary": [
                    {
                        "visibility": "public",
                        "title": {"title": {"value": f"Study {i}"}},
                    }
                ]
            }
            for i in range(501)
        ]
    }
    with pytest.raises(ValueError, match="500"):
        expert_publications.parse_orcid(data)


@pytest.mark.parametrize("delete_failure", [False, True])
def test_upload_rejection_releases_database_before_storage_cleanup(
    env, monkeypatch, delete_failure
):
    client, engine = env
    deleted = []

    def write(reference, raw, **kwargs):
        assert engine.pool.checkedout() == 0
        with Session(engine) as session:
            profile = session.exec(
                select(main.ExpertProfile).where(main.ExpertProfile.user_id == 1)
            ).one()
            profile.verification_status = "PENDING"
            session.add(profile)
            session.commit()

    def delete(reference):
        assert engine.pool.checkedout() == 0
        deleted.append(reference)
        if delete_failure:
            raise object_storage.ObjectStorageError("offline")

    monkeypatch.setattr(object_storage, "write_bytes", write)
    monkeypatch.setattr(object_storage, "delete", delete)
    raw = io.BytesIO()
    Image.new("RGB", (4, 4)).save(raw, "PNG")
    response = client.post(
        "/api/expert-social/media",
        files={"file": ("cover.png", raw.getvalue(), "image/png")},
    )
    assert response.status_code == 403, response.text
    assert len(deleted) == 1
    with Session(engine) as session:
        queued = session.exec(select(SocialMediaDeletion)).all()
        assert [row.reference for row in queued] == (deleted if delete_failure else [])
