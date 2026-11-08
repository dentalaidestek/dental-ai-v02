"""Local synthetic moderation lifecycle; no patient data or provider calls."""

import json
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest

from sqlalchemy import text
from sqlmodel import Session, select

from app import expert_social_safety, main
from app.expert_social_models import SocialDecision, SocialMedia, SocialPost, now
from test_api import env, post
from test_postgres import pg_engine


def image_post(client, engine, caption="Klinikteyiz"):
    with Session(engine) as session:
        media = SocialMedia(owner_id=1, reference="private/synthetic-clinic.jpg")
        session.add(media)
        session.commit()
        ident = media.id
    response = post(client, text=caption, media_ids=[ident])
    assert response.status_code == 200, response.text
    return response.json()


def test_clinic_image_policy_is_human_review_with_observable_owner_status(env):
    client, engine = env
    # This is the actual preexisting policy, not an imaginary queue failure.
    assert expert_social_safety.moderate("Klinikteyiz", has_images=True) == (
        "PENDING", ["IMAGE_REVIEW"]
    )
    item = image_post(client, engine)
    assert item["status"] == "PENDING"
    task = item["moderation"]
    assert task["state"] == "WAITING_HUMAN"
    assert task["wait_type"] == "HUMAN_REVIEW"
    assert task["reasons"] == ["IMAGE_REVIEW"]
    assert task["job_id"] and task["content_version"] == item["version"]
    assert task["age_seconds"] >= 0 and task["last_decision"]["source"] == "AUTOMATIC"
    path = f"/api/expert-social/moderation-status/POST/{item['id']}"
    assert client.get(path).json()["moderation"]["job_id"] == task["job_id"]
    client.cookies.set(main.SESSION_COOKIE, "t2")
    assert client.get(path).status_code == 404
    assert client.get(f"/api/expert-social/posts/{item['id']}").status_code == 404


def test_approval_is_atomic_audited_and_metadata_is_owner_or_admin_only(env):
    client, engine = env
    item = image_post(client, engine)
    client.cookies.set(main.SESSION_COOKIE, "t4")
    url = f"/api/expert-social/moderation/POST/{item['id']}"
    response = client.post(url, json={"status": "PUBLISHED", "version": 1,
                                      "reason": "Hasta verisi içermeyen klinik görseli."})
    assert response.status_code == 200, response.text
    detail = client.get(url).json()
    assert detail["item"]["moderation"]["state"] == "HUMAN_DONE"
    assert detail["item"]["moderation"]["job_id"] == item["moderation"]["job_id"]
    assert detail["item"]["moderation"]["content_version"] == 2
    assert len(detail["moderation_history"]) == 2
    assert detail["moderation_history"][0]["source"] == "HUMAN"
    assert client.post(url, json={"status": "REJECTED", "version": 1,
                                  "reason": "Eski sürüm"}).status_code == 409
    client.cookies.set(main.SESSION_COOKIE, "t2")
    public = client.get(f"/api/expert-social/posts/{item['id']}").json()
    assert public["status"] == "PUBLISHED" and "moderation" not in public
    client.cookies.set(main.SESSION_COOKIE, "t1")
    owned = client.get(f"/api/expert-social/posts/{item['id']}").json()
    assert owned["moderation"]["last_decision"]["status"] == "PUBLISHED"
    pinned = client.patch(f"/api/expert-social/posts/{item['id']}",
                          json={"pinned": True, "version": 2})
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["moderation"]["state"] == "HUMAN_DONE"
    assert pinned.json()["moderation"]["last_decision"] == owned["moderation"]["last_decision"]


def test_oldest_first_queue_counts_and_version_checked_request_changes(env):
    client, engine = env
    old = post(client, text="Hasta adı: Örnek Bir").json()
    recent = post(client, text="Hasta adı: Örnek İki").json()
    from app.expert_social_models import SocialModerationTask
    with Session(engine) as session:
        task = session.exec(select(SocialModerationTask).where(
            SocialModerationTask.target_type == "POST",
            SocialModerationTask.target_id == old["id"])).one()
        task.waiting_since = now() - timedelta(hours=3)
        task.created_at = task.waiting_since
        session.add(task)
        session.commit()
    client.cookies.set(main.SESSION_COOKIE, "t4")
    queue = client.get("/api/expert-social/moderation").json()
    assert [row["id"] for row in queue["items"]] == [old["id"], recent["id"]]
    assert queue["aging"]["waiting_human"] == 2
    assert queue["aging"]["over_1h"] == 1
    assert queue["aging"]["oldest_wait_seconds"] >= 10800
    url = f"/api/expert-social/moderation/POST/{old['id']}"
    response = client.post(url, json={"status": "PENDING", "version": 1,
                                      "reason": "Hasta bilgisini çıkarıp yeniden gönderin."})
    assert response.status_code == 200, response.text
    assert client.get(url).json()["item"]["moderation"]["state"] == "WAITING_OWNER"
    client.cookies.set(main.SESSION_COOKIE, "t1")
    settings = client.patch(f"/api/expert-social/posts/{old['id']}",
                            json={"comments_closed": True, "version": 2})
    assert settings.status_code == 200, settings.text
    assert settings.json()["moderation"]["state"] == "WAITING_OWNER"
    updated = client.patch(f"/api/expert-social/posts/{old['id']}",
                           json={"text": "Bilimsel kaynak notu", "version": 3})
    assert updated.status_code == 200, updated.text
    assert updated.json()["moderation"]["state"] == "AUTO_DONE"


def test_bounded_legacy_backfill_preserves_wait_age_and_never_approves_images(env):
    from app import expert_social_moderation as moderation
    from app.expert_social_models import SocialModerationTask
    _, engine = env
    start = now() - timedelta(hours=5)
    with Session(engine) as session:
        for index in range(5):
            session.add(SocialPost(author_id=1, text="Klinikteyiz", status="PENDING",
                                   reasons_json='["IMAGE_REVIEW"]',
                                   idempotency_key=f"legacy-{index}", request_hash="legacy",
                                   created_at=start + timedelta(seconds=index)))
        session.commit()
    assert moderation.backfill_pending(engine, limit=2) == 2
    assert moderation.backfill_pending(engine, limit=2) == 2
    assert moderation.backfill_pending(engine, limit=2) == 1
    assert moderation.backfill_pending(engine, limit=2) == 0
    assert moderation.retry_failed(engine) == 0
    with Session(engine) as session:
        tasks = session.exec(select(SocialModerationTask)).all()
        assert len(tasks) == 5
        assert all(task.state == "WAITING_HUMAN" and task.waiting_since < start + timedelta(seconds=5)
                   for task in tasks)
        assert all(row.status == "PENDING" for row in session.exec(select(SocialPost)).all())


def test_real_triage_error_is_durable_and_local_retry_recovers_idempotently(env, monkeypatch):
    from app import expert_social_moderation as moderation
    from app.expert_social_models import SocialModerationEvent, SocialModerationTask
    client, engine = env
    original = expert_social_safety.moderate
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic failure; must not become stored error text")
    monkeypatch.setattr(expert_social_safety, "moderate", fail)
    response = post(client, text="Bilimsel seminer notu")
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["status"] == "PENDING" and item["moderation"]["state"] == "FAILED"
    monkeypatch.setattr(expert_social_safety, "moderate", original)
    assert moderation.retry_failed(engine) == 1
    assert moderation.retry_failed(engine) == 0
    with Session(engine) as session:
        task = session.exec(select(SocialModerationTask)).one()
        assert task.job_id == item["moderation"]["job_id"] and task.state == "AUTO_DONE"
        assert task.attempts == 1 and task.lease_token is None
        assert session.get(SocialPost, item["id"]).status == "PUBLISHED"
        assert len(session.exec(select(SocialDecision)).all()) == 2
        events = session.exec(select(SocialModerationEvent)).all()
        assert len(events) == 3 and len({event.revision for event in events}) == 3
        assert "synthetic failure" not in json.dumps([event.model_dump(mode="json") for event in events])


def test_retry_budget_and_lease_expiry_are_bounded_and_image_recovery_waits_human(env, monkeypatch):
    from app import expert_social_moderation as moderation
    from app.expert_social_models import SocialModerationTask
    client, engine = env
    original = expert_social_safety.moderate
    monkeypatch.setattr(expert_social_safety, "moderate", lambda *a, **k: (_ for _ in ()).throw(ValueError("synthetic")))
    item = image_post(client, engine)
    assert item["moderation"]["state"] == "FAILED"
    with Session(engine) as session:
        task = session.exec(select(SocialModerationTask)).one()
        task.state = "RUNNING"
        task.lease_token = "crashed-lease"
        task.lease_until = now() - timedelta(seconds=1)
        session.add(task)
        session.commit()
    monkeypatch.setattr(expert_social_safety, "moderate", original)
    assert moderation.retry_failed(engine) == 1
    with Session(engine) as session:
        task = session.exec(select(SocialModerationTask)).one()
        assert task.state == "WAITING_HUMAN"
        assert task.reasons_json == '["IMAGE_REVIEW"]'
        assert session.get(SocialPost, item["id"]).status == "PENDING"
    assert moderation.retry_failed(engine) == 0


def test_failed_checks_exhaust_the_retry_budget_without_publishing(env, monkeypatch):
    from app import expert_social_moderation as moderation
    from app.expert_social_models import SocialModerationTask
    client, engine = env
    monkeypatch.setattr(expert_social_safety, "moderate", lambda *a, **k: (_ for _ in ()).throw(ValueError("synthetic")))
    item = post(client, text="Yerel kontrol hata denemesi").json()
    for attempt in range(moderation.MAX_ATTEMPTS):
        with Session(engine) as session:
            task = session.exec(select(SocialModerationTask)).one()
            task.next_attempt_at = now() - timedelta(seconds=1)
            session.add(task)
            session.commit()
        assert moderation.retry_failed(engine) == 1
    assert moderation.retry_failed(engine) == 0
    with Session(engine) as session:
        task = session.exec(select(SocialModerationTask)).one()
        assert task.state == "FAILED" and task.wait_type == "RETRY_EXHAUSTED"
        assert task.attempts == moderation.MAX_ATTEMPTS and task.next_attempt_at is None
        assert session.get(SocialPost, item["id"]).status == "PENDING"


def test_retry_reconciles_content_changed_by_older_build_without_using_stale_check(env, monkeypatch):
    from app import expert_social_moderation as moderation
    from app.expert_social_models import SocialModerationTask
    client, engine = env
    original = expert_social_safety.moderate
    monkeypatch.setattr(expert_social_safety, "moderate", lambda *a, **k: (_ for _ in ()).throw(ValueError("synthetic")))
    item = post(client, text="Eski bilimsel not").json()
    with Session(engine) as session:
        row = session.get(SocialPost, item["id"])
        row.text, row.status, row.reasons_json, row.version = "Hasta adı: Örnek", "PENDING", '["PRIVACY"]', 2
        session.add(row)
        session.commit()
    monkeypatch.setattr(expert_social_safety, "moderate", original)
    assert moderation.retry_failed(engine) == 1
    with Session(engine) as session:
        row = session.get(SocialPost, item["id"])
        task = session.exec(select(SocialModerationTask)).one()
        assert row.status == "PENDING" and row.version == 2
        assert task.state == "WAITING_HUMAN" and task.content_version == 2
        assert task.last_decision_source == "RECONCILED"


def test_human_approval_rolls_back_if_durable_audit_fails(env, monkeypatch):
    from app import expert_social_moderation as moderation
    from app.expert_social_models import SocialModerationEvent, SocialModerationTask
    client, engine = env
    item = image_post(client, engine)
    original = moderation.record
    def broken(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic audit write failure")
    monkeypatch.setattr(moderation, "record", broken)
    client.cookies.set(main.SESSION_COOKIE, "t4")
    with pytest.raises(RuntimeError, match="synthetic audit"):
        client.post(f"/api/expert-social/moderation/POST/{item['id']}",
                    json={"status": "PUBLISHED", "version": 1, "reason": "İncelendi"})
    with Session(engine) as session:
        row = session.get(SocialPost, item["id"])
        assert row.status == "PENDING" and row.version == 1
        assert session.exec(select(SocialModerationTask)).one().state == "WAITING_HUMAN"
        assert len(session.exec(select(SocialModerationEvent)).all()) == 1
        assert len(session.exec(select(SocialDecision)).all()) == 1


def test_failed_retry_respects_current_expert_eligibility(env, monkeypatch):
    from app import expert_social_moderation as moderation
    from app.expert_social_models import SocialModerationTask
    client, engine = env
    original = expert_social_safety.moderate
    monkeypatch.setattr(expert_social_safety, "moderate", lambda *a, **k: (_ for _ in ()).throw(ValueError("synthetic")))
    item = post(client, text="Bilimsel etkinlik notu").json()
    with Session(engine) as session:
        user = session.get(main.User, 1)
        user.is_active = False
        session.add(user)
        session.commit()
    monkeypatch.setattr(expert_social_safety, "moderate", original)
    assert moderation.retry_failed(engine) == 1
    with Session(engine) as session:
        assert session.get(SocialPost, item["id"]).status == "PENDING"
        task = session.exec(select(SocialModerationTask)).one()
        assert task.state == "WAITING_HUMAN" and task.reasons_json == '["ACCOUNT_REVIEW"]'


@pytest.mark.parametrize("kind", ["COMMENT", "PUBLICATION"])
def test_comment_and_publication_owner_receive_the_same_status_contract(env, kind):
    import uuid
    client, _ = env
    if kind == "COMMENT":
        parent = post(client).json()
        response = client.post(f"/api/expert-social/posts/{parent['id']}/comments",
            json={"text": "Hasta adı: Örnek", "idempotency_key": str(uuid.uuid4())})
    else:
        response = client.post("/api/expert-social/publications", json={"title": "Hasta adı: Örnek"})
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["moderation"]["state"] == "WAITING_HUMAN"
    path = f"/api/expert-social/moderation-status/{kind}/{item['id']}"
    assert client.get(path).json()["moderation"]["job_id"] == item["moderation"]["job_id"]
    client.cookies.set(main.SESSION_COOKIE, "t2")
    assert client.get(path).status_code == 404


def test_pending_queue_cursor_pages_oldest_first_without_gaps(env):
    from app import expert_social_moderation as moderation
    client, engine = env
    with Session(engine) as session:
        for index in range(35):
            session.add(SocialPost(author_id=1, text="Klinikteyiz", status="PENDING",
                                   reasons_json='["IMAGE_REVIEW"]',
                                   idempotency_key=f"page-{index}", request_hash="legacy"))
        session.commit()
    moderation.backfill_pending(engine, limit=60)
    client.cookies.set(main.SESSION_COOKIE, "t4")
    first = client.get("/api/expert-social/moderation").json()
    assert len(first["items"]) == 30 and first["next_cursor"]
    second = client.get(f"/api/expert-social/moderation?before={first['next_cursor']}").json()
    assert len(second["items"]) == 5 and second["next_cursor"] is None
    combined = [row["id"] for row in first["items"] + second["items"]]
    assert combined == sorted(set(combined))


def seed_edited_pending(engine, kind, count=35):
    from app import expert_social_moderation as moderation
    from app.expert_social_models import Publication
    past = now() - timedelta(days=2)
    with Session(engine) as session:
        rows = []
        for index in range(count):
            common = {"status": "PENDING", "version": 2,
                      "reasons_json": '["PRIVACY"]', "created_at": past,
                      "updated_at": past + timedelta(hours=1)}
            if kind == "POST":
                row = SocialPost(author_id=1, text=f"Hasta adı: Örnek {index}",
                    idempotency_key=f"edited-{index}", request_hash="synthetic", **common)
            else:
                row = Publication(expert_id=1, title=f"Kaynak {index}",
                    fingerprint=f"edited-{index}", title_key=f"edited-{index}", **common)
            rows.append(row)
            session.add(row)
        session.flush()
        for row in rows:
            moderation.record(session, kind, row)
        session.commit()


def test_pending_cursor_keeps_original_boundary_after_last_item_review(env):
    client, engine = env
    seed_edited_pending(engine, "POST")
    client.cookies.set(main.SESSION_COOKIE, "t4")
    first = client.get("/api/expert-social/moderation").json()
    assert [row["id"] for row in first["items"]] == list(range(1, 31))
    last = first["items"][-1]
    reviewed = client.post(f"/api/expert-social/moderation/POST/{last['id']}",
        json={"status": "PUBLISHED", "version": last["version"], "reason": "İncelendi"})
    assert reviewed.status_code == 200, reviewed.text
    second = client.get("/api/expert-social/moderation", params={"before": first["next_cursor"]})
    assert second.status_code == 200, second.text
    assert [row["id"] for row in second.json()["items"]] == list(range(31, 36))
    assert second.json()["next_cursor"] is None


def test_pending_publication_cursor_survives_boundary_hard_deletion(env):
    client, engine = env
    seed_edited_pending(engine, "PUBLICATION")
    client.cookies.set(main.SESSION_COOKIE, "t4")
    first = client.get("/api/expert-social/moderation?kind=PUBLICATION").json()
    assert [row["id"] for row in first["items"]] == list(range(1, 31))
    client.cookies.set(main.SESSION_COOKIE, "t1")
    assert client.delete(f"/api/expert-social/publications/{first['items'][-1]['id']}").status_code == 200
    client.cookies.set(main.SESSION_COOKIE, "t4")
    second = client.get("/api/expert-social/moderation", params={
        "kind": "PUBLICATION", "before": first["next_cursor"]})
    assert second.status_code == 200, second.text
    assert [row["id"] for row in second.json()["items"]] == list(range(31, 36))
    assert second.json()["next_cursor"] is None


def test_pending_queue_rejects_malformed_and_out_of_scope_cursors(env):
    import base64
    client, engine = env
    seed_edited_pending(engine, "POST")
    client.cookies.set(main.SESSION_COOKIE, "t4")
    def encoded(payload):
        return "m1_" + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    malformed = ["bad", "m1_???", "m1_", "-1", "0", "9" * 200, "m1_" + "a" * 256,
                 encoded(["POST", "2026-11-07T00:00:00.000000", 0]),
                 encoded(["PUBLICATION", "2026-11-07T00:00:00.000000", 30]),
                 encoded(["POST", "2026-11-07T00:00:00+00:00", 30])]
    for cursor in malformed:
        response = client.get("/api/expert-social/moderation", params={"before": cursor})
        assert response.status_code == 400, (cursor, response.status_code, response.text)


@pytest.mark.parametrize("status", ["PUBLISHED", "REJECTED"])
def test_resolved_moderation_queue_keeps_numeric_descending_cursor(env, status):
    from app import expert_social_moderation as moderation
    client, engine = env
    seed_edited_pending(engine, "POST")
    with Session(engine) as session:
        for row in session.exec(select(SocialPost)).all():
            row.status, row.version = status, row.version + 1
            session.add(row)
            moderation.record(session, "POST", row, actor_id=4, reason="İncelendi", human=True)
        session.commit()
    client.cookies.set(main.SESSION_COOKIE, "t4")
    first = client.get("/api/expert-social/moderation", params={"status": status}).json()
    assert [row["id"] for row in first["items"]] == list(range(35, 5, -1))
    assert first["next_cursor"] == 6
    second = client.get("/api/expert-social/moderation", params={
        "status": status, "before": first["next_cursor"]}).json()
    assert [row["id"] for row in second["items"]] == [5, 4, 3, 2, 1]
    assert second["next_cursor"] is None


def test_pending_queue_accepts_legacy_numeric_cursor(env):
    client, engine = env
    seed_edited_pending(engine, "POST")
    client.cookies.set(main.SESSION_COOKIE, "t4")
    page = client.get("/api/expert-social/moderation?before=30")
    assert page.status_code == 200, page.text
    assert [row["id"] for row in page.json()["items"]] == [31, 32, 33, 34, 35]


def test_publication_can_be_readded_after_hard_deletion_with_retained_task_history(env):
    client, _ = env
    original = client.post("/api/expert-social/publications", json={"title": "Tekrar eklenen kaynak"}).json()
    assert client.delete(f"/api/expert-social/publications/{original['id']}").status_code == 200
    response = client.post("/api/expert-social/publications", json={"title": "Tekrar eklenen kaynak"})
    assert response.status_code == 200, response.text
    assert response.json()["moderation"]["state"] == "AUTO_DONE"


def test_postgres_concurrent_failed_retry_claims_have_one_completion(pg_engine, monkeypatch):
    from app import expert_social_moderation as moderation
    from app.expert_social_models import SocialModerationEvent, SocialModerationTask
    from test_orcid_postgres import setup_social, client
    app = setup_social(pg_engine, monkeypatch)
    original = expert_social_safety.moderate
    monkeypatch.setattr(expert_social_safety, "moderate", lambda *a, **k: (_ for _ in ()).throw(ValueError("synthetic")))
    item = post(client(app), text="Eşzamanlı yerel kontrol").json()
    monkeypatch.setattr(expert_social_safety, "moderate", original)
    with ThreadPoolExecutor(max_workers=4) as workers:
        claims = list(workers.map(lambda _: moderation.retry_failed(pg_engine), range(4)))
    assert sum(claims) == 1
    with Session(pg_engine) as session:
        task = session.exec(select(SocialModerationTask)).one()
        assert task.job_id == item["moderation"]["job_id"]
        assert task.state == "AUTO_DONE" and task.attempts == 1
        assert len(session.exec(select(SocialModerationEvent)).all()) == 3
        assert len(session.exec(select(SocialDecision)).all()) == 2


def test_postgres_pending_cursor_keeps_reviewed_or_deleted_page_boundary(pg_engine, monkeypatch):
    from test_orcid_postgres import setup_social, client
    app = setup_social(pg_engine, monkeypatch)
    with Session(pg_engine) as session:
        session.add(main.User(id=4, username="local-admin", role="ADMIN", display_name="Admin",
            email=main.ADMIN_FIXED_EMAIL, email_verified_at=now()))
        session.flush()
        for ident in (1, 4):
            session.add(main.SessionToken(token_hash=main.hash_session_token(f"t{ident}"),
                user_id=ident, expires_at=now() + timedelta(days=1)))
        session.add(main.AdminVerifiedSession(token_hash=main.hash_session_token("t4"), user_id=4))
        session.commit()
    browser = client(app)
    for kind in ("POST", "PUBLICATION"):
        seed_edited_pending(pg_engine, kind)
        browser.cookies.set(main.SESSION_COOKIE, "t4")
        first = browser.get("/api/expert-social/moderation", params={"kind": kind}).json()
        last = first["items"][-1]
        if kind == "POST":
            response = browser.post(f"/api/expert-social/moderation/{kind}/{last['id']}",
                json={"status": "PUBLISHED", "version": last["version"], "reason": "İncelendi"})
        else:
            browser.cookies.set(main.SESSION_COOKIE, "t1")
            response = browser.delete(f"/api/expert-social/publications/{last['id']}")
        assert response.status_code == 200, response.text
        browser.cookies.set(main.SESSION_COOKIE, "t4")
        second = browser.get("/api/expert-social/moderation", params={
            "kind": kind, "before": first["next_cursor"]})
        assert second.status_code == 200, second.text
        assert [row["id"] for row in second.json()["items"]] == [31, 32, 33, 34, 35]


def test_additive_task_migration_preserves_baseline_and_social_revisions(env):
    from app.expert_social_schema import apply, require_schema
    from app.expert_social_models import SocialModerationTask
    _, engine = env
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE dental_schema_revision(id INTEGER PRIMARY KEY, version INTEGER NOT NULL)"))
        connection.execute(text("INSERT INTO dental_schema_revision VALUES (1,12)"))
        SocialModerationTask.__table__.drop(connection)
    apply(engine)
    apply(engine)
    require_schema(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version FROM dental_schema_revision")).scalar_one() == 12
        assert connection.execute(text("SELECT version FROM dental_social_revision")).scalar_one() == 2


def test_human_decision_creates_one_private_generic_notification(env):
    client,engine=env
    item=post(client).json()
    client.cookies.set(main.SESSION_COOKIE,'t4')
    endpoint=f"/api/expert-social/moderation/POST/{item['id']}"
    body={'status':'PENDING','version':item['version'],'reason':'Kaynak bilgisini tamamlayın.'}
    response=client.post(endpoint,json=body)
    assert response.status_code==200,response.text
    assert client.post(endpoint,json=body).status_code==409
    with Session(engine) as session:
        notices=session.exec(select(main.AdminNotice)).all()
        assert len(notices)==1
        notice=notices[0]
        assert notice.user_id==1
        assert notice.target_url==f"/expert-support/profile?post={item['id']}"
        assert 'Kaynak bilgisini' not in notice.model_dump_json()
    client.cookies.set(main.SESSION_COOKIE,'t2')
    assert client.post(endpoint,json={**body,'version':response.json()['version']}).status_code==403
    with Session(engine) as session:
        assert len(session.exec(select(main.AdminNotice)).all())==1


def test_failed_notice_insert_rolls_back_moderator_decision(env,monkeypatch):
    client,engine=env
    item=post(client).json()
    client.cookies.set(main.SESSION_COOKIE,'t4')
    def unavailable(*args,**kwargs):
        raise RuntimeError('Synthetic outbox failure')
    monkeypatch.setattr(main,'_notify_user',unavailable)
    with pytest.raises(RuntimeError):
        client.post(f"/api/expert-social/moderation/POST/{item['id']}",json={
            'status':'REJECTED','version':item['version'],'reason':'Yeniden düzenleme gerekiyor.'})
    with Session(engine) as session:
        row=session.get(SocialPost,item['id'])
        assert row.status=='PUBLISHED' and row.version==item['version']
        assert len(session.exec(select(SocialDecision)).all())==1
        assert not session.exec(select(main.AdminNotice)).all()
