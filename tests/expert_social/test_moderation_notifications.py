"""Synthetic moderation notices use the existing transactional notification log."""

import json
import uuid

import pytest
from sqlmodel import Session, select

from app import main
from app.expert_social_models import SocialPost
from test_api import env, post


def pending_item(client, kind):
    if kind == "POST":
        response = post(client, text="Hasta adı: CONTENT_SENTINEL")
        owner, target = 1, None
    elif kind == "PUBLICATION":
        response = client.post("/api/expert-social/publications", json={
            "title": "Hasta adı: CONTENT_SENTINEL"})
        owner, target = 1, "/expert-support/profile?tab=publications"
    else:
        parent = post(client).json()
        client.cookies.set(main.SESSION_COOKIE, "t2")
        response = client.post(f"/api/expert-social/posts/{parent['id']}/comments", json={
            "text": "Hasta adı: CONTENT_SENTINEL", "idempotency_key": str(uuid.uuid4())})
        owner = 2
        target = f"/expert-support/expert/1?post={parent['id']}"
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["status"] == "PENDING"
    return item, owner, target or f"/expert-support/profile?post={item['id']}"


@pytest.mark.parametrize("kind", ["POST", "COMMENT", "PUBLICATION"])
@pytest.mark.parametrize("status", ["PUBLISHED", "REJECTED", "PENDING"])
def test_review_notifies_owner_once_with_generic_copy_after_transaction_closes(env, monkeypatch, kind, status):
    client, engine = env
    item, owner, target = pending_item(client, kind)
    published = []

    async def capture(event):
        assert engine.pool.checkedout() == 0
        with Session(engine) as session:
            notice = session.exec(select(main.AdminNotice)).one()
            assert notice.user_id == owner
        published.append(event)

    monkeypatch.setattr(main, "_publish_realtime_event", capture)
    client.cookies.set(main.SESSION_COOKIE, "t4")
    body = {"status": status, "version": item["version"], "reason": "PRIVATE_ADMIN_REASON_SENTINEL"}
    path = f"/api/expert-social/moderation/{kind}/{item['id']}"
    reviewed = client.post(path, json=body)
    assert reviewed.status_code == 200, reviewed.text
    assert client.post(path, json=body).status_code == 409
    assert client.post(path, json={**body, "status": "REJECTED"}).status_code == 409
    with Session(engine) as session:
        notice = session.exec(select(main.AdminNotice)).one()
        event = session.exec(select(main.RealtimeEvent)).one()
        assert notice.user_id == event.user_id == owner
        assert notice.target_url == target
        suffix = "CHANGES_REQUESTED" if status == "PENDING" else status
        assert notice.notice_type == "SOCIAL_MODERATION_" + suffix
        assert notice.dedup_key == f"u{owner}:social-moderation:{kind}:{item['id']}:v2"
        assert notice.related_type == "social_" + kind.lower()
        assert notice.related_id == str(item["id"])
        serialized = json.dumps([notice.model_dump(mode="json"), event.model_dump(mode="json")])
        assert "CONTENT_SENTINEL" not in serialized
        assert "PRIVATE_ADMIN_REASON_SENTINEL" not in serialized
    assert len(published) == 1 and published[0].event_type == "NOTICE_CREATED"


def test_review_rolls_back_notice_and_outbox_when_notification_step_fails(env, monkeypatch):
    client, engine = env
    item, _, _ = pending_item(client, "POST")
    notify = main._notify_user
    published = []

    def fail_after_recording(*args, **kwargs):
        notify(*args, **kwargs)
        raise RuntimeError("synthetic notice failure")

    monkeypatch.setattr(main, "_notify_user", fail_after_recording)
    monkeypatch.setattr(main, "on_loop", lambda *args: published.append(args))
    client.cookies.set(main.SESSION_COOKIE, "t4")
    with pytest.raises(RuntimeError, match="synthetic notice failure"):
        client.post(f"/api/expert-social/moderation/POST/{item['id']}", json={
            "status": "PUBLISHED", "version": 1, "reason": "İncelendi"})
    with Session(engine) as session:
        row = session.get(SocialPost, item["id"])
        assert row.status == "PENDING" and row.version == 1
        assert session.exec(select(main.AdminNotice)).all() == []
        assert session.exec(select(main.RealtimeEvent)).all() == []
    assert published == []


def test_ordinary_member_cannot_moderate_or_create_review_notification(env):
    client, engine = env
    item, _, _ = pending_item(client, "POST")
    response = client.post(f"/api/expert-social/moderation/POST/{item['id']}", json={
        "status": "PUBLISHED", "version": 1, "reason": "İncelendi"})
    assert response.status_code == 403
    with Session(engine) as session:
        assert session.get(SocialPost, item["id"]).status == "PENDING"
        assert session.exec(select(main.AdminNotice)).all() == []
        assert session.exec(select(main.RealtimeEvent)).all() == []


def test_realtime_delivery_failure_keeps_committed_notice_and_review(env, monkeypatch):
    client, engine = env
    item, _, _ = pending_item(client, "POST")

    async def failed_delivery(event):
        raise RuntimeError("synthetic disconnected realtime client")

    monkeypatch.setattr(main, "_publish_realtime_event", failed_delivery)
    client.cookies.set(main.SESSION_COOKIE, "t4")
    response = client.post(f"/api/expert-social/moderation/POST/{item['id']}", json={
        "status": "PUBLISHED", "version": 1, "reason": "İncelendi"})
    assert response.status_code == 200, response.text
    with Session(engine) as session:
        assert session.get(SocialPost, item["id"]).status == "PUBLISHED"
        assert len(session.exec(select(main.AdminNotice)).all()) == 1
        assert len(session.exec(select(main.RealtimeEvent)).all()) == 1
