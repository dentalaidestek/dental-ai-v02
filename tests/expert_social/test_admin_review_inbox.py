"""Review alerts are durable, content-free, targeted and sent after commit."""
import json
import uuid

import pytest
from sqlmodel import Session, select

from app import main
from app.expert_social_models import SocialPost
from test_api import env, post


@pytest.mark.parametrize("kind", ["POST", "COMMENT", "PUBLICATION"])
def test_pending_content_notifies_verified_admin_once_after_commit(env, monkeypatch, kind):
    client, engine = env
    delivered = []

    async def capture(event):
        assert engine.pool.checkedout() == 0
        with Session(engine) as session:
            assert session.get(main.RealtimeEvent, event.id) is not None
        delivered.append(event)

    monkeypatch.setattr(main, "_publish_realtime_event", capture)
    if kind == "POST":
        key = str(uuid.uuid4())
        create = lambda: post(client, text="Hasta adı: SECRET_CONTENT", idempotency_key=key)
    elif kind == "COMMENT":
        parent = post(client).json()
        key = str(uuid.uuid4())
        create = lambda: client.post(f"/api/expert-social/posts/{parent['id']}/comments", json={
            "text": "Hasta adı: SECRET_CONTENT", "idempotency_key": key})
    else:
        create = lambda: client.post("/api/expert-social/publications", json={"title": "Hasta adı: SECRET_CONTENT"})
    response = create()
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["status"] == "PENDING"
    if kind != "PUBLICATION":
        assert create().status_code == 200
    with Session(engine) as session:
        notices = session.exec(select(main.AdminNotice).where(main.AdminNotice.user_id == 4)).all()
        assert len(notices) == 1
        notice = notices[0]
        assert notice.notice_type == "SOCIAL_REVIEW_REQUIRED"
        assert notice.status == "ACTIVE"
        assert notice.target_url == f"{main.ADMIN_CENTER_PATH}/social?kind={kind}&target={item['id']}"
        assert "SECRET_CONTENT" not in json.dumps(notice.model_dump(mode="json"))
        assert session.exec(select(main.AdminNotice).where(main.AdminNotice.user_id != 4)).all() == []
    assert len(delivered) == 1
    client.cookies.set(main.SESSION_COOKIE, "t4")
    detail = client.get(f"/api/expert-social/moderation/{kind}/{item['id']}")
    assert detail.status_code == 200
    reviewed = client.post(f"/api/expert-social/moderation/{kind}/{item['id']}", json={
        "status": "PUBLISHED", "version": 1, "reason": "Sentetik test içeriği"})
    assert reviewed.status_code == 200, reviewed.text
    assert any(event.user_id == 4 and event.event_type == 'NOTICE_RESOLVED' for event in delivered)
    with Session(engine) as session:
        assert session.exec(select(main.AdminNotice).where(main.AdminNotice.user_id == 4)).one().status == "RESOLVED"


def test_public_content_and_inactive_or_unverified_admins_receive_no_alert(env):
    client, engine = env
    assert post(client).status_code == 200
    with Session(engine) as session:
        admin = session.get(main.User, 4)
        admin.is_active = False
        session.add(admin)
        session.add(main.User(id=5, username="fake-admin", display_name="Sentetik yönetici", role="ADMIN", email="other@example.test", email_verified_at=main._utcnow_naive()))
        session.commit()
    assert post(client, text="Hasta adı: SECRET_CONTENT").status_code == 200
    with Session(engine) as session:
        assert session.exec(select(main.AdminNotice)).all() == []


def test_failed_notification_rolls_back_content_and_event(env, monkeypatch):
    client, engine = env
    original = main._notify_user

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic notification failure")

    monkeypatch.setattr(main, "_notify_user", fail)
    with pytest.raises(RuntimeError, match="synthetic notification failure"):
        post(client, text="Hasta adı: SECRET_CONTENT")
    with Session(engine) as session:
        assert session.exec(select(SocialPost)).all() == []
        assert session.exec(select(main.AdminNotice)).all() == []
        assert session.exec(select(main.RealtimeEvent)).all() == []


def test_realtime_failure_does_not_lose_pending_submission(env, monkeypatch):
    client, engine = env

    async def fail(event):
        raise RuntimeError("synthetic disconnected admin")

    monkeypatch.setattr(main, "_publish_realtime_event", fail)
    response = post(client, text="Hasta adı: SECRET_CONTENT")
    assert response.status_code == 200
    with Session(engine) as session:
        assert session.exec(select(main.AdminNotice)).one().status == "ACTIVE"
        assert session.exec(select(main.RealtimeEvent)).one().event_type == "NOTICE_CREATED"


@pytest.mark.parametrize("removal", ["root", "post", "account"])
def test_cascade_removal_resolves_pending_reply_alert(env, removal):
    client, engine = env
    parent_post = post(client).json()
    endpoint = f"/api/expert-social/posts/{parent_post['id']}/comments"
    root = client.post(endpoint, json={"text": "Bilimsel ana yorum.", "idempotency_key": str(uuid.uuid4())}).json()
    reply = client.post(endpoint, json={"text": "Hasta adı: SYNTHETIC", "parent_id": root["id"], "idempotency_key": str(uuid.uuid4())}).json()
    assert reply["status"] == "PENDING"
    if removal == "root":
        assert client.delete(f"/api/expert-social/comments/{root['id']}").status_code == 200
    elif removal == "post":
        assert client.delete(f"/api/expert-social/posts/{parent_post['id']}").status_code == 200
    else:
        from app.expert_social_maintenance import erase_user_content
        with Session(engine) as session:
            erase_user_content(session, 1)
            session.commit()
    with Session(engine) as session:
        notices = session.exec(select(main.AdminNotice).where(main.AdminNotice.notice_type == "SOCIAL_REVIEW_REQUIRED")).all()
        assert [(n.related_id, n.status) for n in notices] == [(str(reply["id"]), "RESOLVED")]


def test_successful_background_retry_resolves_admin_alert(env, monkeypatch):
    from app import expert_social_safety, expert_social_moderation
    client, engine = env
    original = expert_social_safety.moderate
    def fail(*args, **kwargs):
        raise ValueError('synthetic triage failure')
    monkeypatch.setattr(expert_social_safety, 'moderate', fail)
    item = post(client).json()
    assert item['status'] == 'PENDING'
    monkeypatch.setattr(expert_social_safety, 'moderate', original)
    assert expert_social_moderation.retry_failed(engine) == 1
    with Session(engine) as session:
        assert session.get(SocialPost, item['id']).status == 'PUBLISHED'
        assert session.exec(select(main.AdminNotice)).one().status == 'RESOLVED'
