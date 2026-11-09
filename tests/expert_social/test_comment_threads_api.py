"""Viewer-scoped comment threads, persisted likes and additive rollout checks."""

import uuid
import time

import pytest
from sqlalchemy import event, inspect, text
from sqlmodel import Session, create_engine, select

from app import main
from app.expert_social_models import SocialComment, SocialPost
from test_api import env, post


PREFIX = "/api/expert-social"


def seed_comment(session, post_id, author_id=3, status="PUBLISHED", parent_id=None):
    row = SocialComment(
        post_id=post_id,
        author_id=author_id,
        status=status,
        parent_id=parent_id,
        text="Bilimsel görüş " + uuid.uuid4().hex,
        idempotency_key=str(uuid.uuid4()),
    )
    session.add(row)
    session.flush()
    return row


def published_comment(env):
    client, engine = env
    post_id = post(client).json()["id"]
    with Session(engine) as session:
        row = seed_comment(session, post_id)
        comment_id = row.id
        session.commit()
    return client, engine, post_id, comment_id


def test_comment_write_responses_return_current_published_counts_on_create_edit_and_replay(env):
    client, _ = env
    post_id = post(client).json()["id"]
    endpoint = f"{PREFIX}/posts/{post_id}/comments"
    root_body = {"text": "Bilimsel kaynak önerisi", "idempotency_key": str(uuid.uuid4())}
    root_response = client.post(endpoint, json=root_body)
    assert root_response.status_code == 200, root_response.text
    root = root_response.json()
    assert root["comment_count"] == 1
    assert "parent_reply_count" not in root
    reply_body = {
        "text": "Kaynak üzerine bilimsel bir yanıt", "parent_id": root["id"],
        "idempotency_key": str(uuid.uuid4()),
    }
    reply = client.post(endpoint, json=reply_body).json()
    assert reply["comment_count"] == 2
    assert reply["parent_reply_count"] == 1 and reply["reply_count"] == 0
    replayed_root = client.post(endpoint, json=root_body).json()
    assert replayed_root["id"] == root["id"]
    assert replayed_root["comment_count"] == 2
    assert "parent_reply_count" not in replayed_root
    # Reopening has already counted the committed reply before its lost POST
    # response is retried. The retry must return the current total, not a delta.
    reopened = client.get(endpoint, params={"threaded": True}).json()["items"][0]
    assert reopened["reply_count"] == 1
    replayed_reply = client.post(endpoint, json=reply_body).json()
    assert replayed_reply["id"] == reply["id"]
    assert replayed_reply["comment_count"] == 2
    assert replayed_reply["parent_reply_count"] == reopened["reply_count"]
    assert replayed_reply["reply_count"] == 0
    pending = client.post(endpoint, json={
        "text": "Hasta adı: PRIVATE_COUNT_SENTINEL", "idempotency_key": str(uuid.uuid4()),
    }).json()
    assert pending["status"] == "PENDING" and pending["comment_count"] == 2
    pending_reply_body = {
        "text": "Hasta adı: PRIVATE_PENDING_REPLY_SENTINEL", "parent_id": root["id"],
        "idempotency_key": str(uuid.uuid4()),
    }
    pending_reply = client.post(endpoint, json=pending_reply_body).json()
    assert pending_reply["status"] == "PENDING" and pending_reply["comment_count"] == 2
    assert pending_reply["parent_reply_count"] == 2 and pending_reply["reply_count"] == 0
    replayed_pending_reply = client.post(endpoint, json=pending_reply_body).json()
    assert replayed_pending_reply["id"] == pending_reply["id"]
    assert replayed_pending_reply["parent_reply_count"] == 2
    assert client.post(endpoint, json=reply_body).json()["parent_reply_count"] == 2
    assert client.get(endpoint, params={"parent_id": root["id"]}).json()["reply_count"] == 2
    edited_reply = client.patch(f"{PREFIX}/comments/{reply['id']}", json={
        "text": "Hasta adı: PRIVATE_REPLY_SENTINEL", "version": reply["version"],
    }).json()
    assert edited_reply["status"] == "PENDING" and edited_reply["comment_count"] == 1
    assert edited_reply["parent_reply_count"] == 2 and edited_reply["reply_count"] == 0
    assert client.post(endpoint, json=root_body).json()["comment_count"] == 1
    edited_root = client.patch(f"{PREFIX}/comments/{root['id']}", json={
        "text": "Hasta adı: PRIVATE_ROOT_SENTINEL", "version": root["version"],
    }).json()
    assert edited_root["status"] == "PENDING" and edited_root["comment_count"] == 0
    restored = client.patch(f"{PREFIX}/comments/{root['id']}", json={
        "text": "Düzeltilmiş bilimsel kaynak önerisi", "version": edited_root["version"],
    }).json()
    assert restored["status"] == "PUBLISHED" and restored["comment_count"] == 1
    assert client.get(endpoint).json()["comment_count"] == restored["comment_count"]


def test_comment_likes_are_idempotent_persisted_and_available_when_comments_close(env):
    client, engine, post_id, comment_id = published_comment(env)
    endpoint = f"{PREFIX}/comments/{comment_id}/like"
    client.cookies.set(main.SESSION_COOKIE, "t2")
    for _ in range(2):
        response = client.put(endpoint, json={"liked": True})
        assert response.status_code == 200, response.text
        assert response.json() == {"liked": True, "like_count": 1}
    row = client.get(f"{PREFIX}/posts/{post_id}/comments", params={"threaded": True}).json()["items"][0]
    assert row["liked"] is True and row["like_count"] == 1 and row["reply_count"] == 0
    client.cookies.set(main.SESSION_COOKIE, "t3")
    assert client.put(endpoint, json={"liked": True}).json() == {"liked": True, "like_count": 2}
    client.cookies.set(main.SESSION_COOKIE, "t2")
    for _ in range(2):
        assert client.put(endpoint, json={"liked": False}).json() == {"liked": False, "like_count": 1}
    row = client.get(f"{PREFIX}/posts/{post_id}/comments").json()["items"][0]
    assert row["liked"] is False and row["like_count"] == 1
    with Session(engine) as session:
        parent = session.get(SocialPost, post_id)
        parent.comments_closed = True
        session.add(parent)
        session.commit()
    assert client.put(endpoint, json={"liked": True}).json() == {"liked": True, "like_count": 2}
    assert response.headers["cache-control"] == "private, no-store"


def test_comment_like_auth_csrf_and_input_validation(env):
    client, engine, _, comment_id = published_comment(env)
    endpoint = f"{PREFIX}/comments/{comment_id}/like"
    client.cookies.clear()
    assert client.put(endpoint, json={"liked": True}).status_code == 401
    client.cookies.set(main.SESSION_COOKIE, "t2")
    client.headers["Origin"] = "https://different.example"
    assert client.put(endpoint, json={"liked": True}).status_code == 403
    client.headers["Origin"] = "http://testserver"
    del client.headers["X-Dental-Social"]
    assert client.put(endpoint, json={"liked": True}).status_code == 403
    client.headers["X-Dental-Social"] = "1"
    client.headers["Sec-Fetch-Site"] = "cross-site"
    assert client.put(endpoint, json={"liked": True}).status_code == 403
    del client.headers["Sec-Fetch-Site"]
    assert client.put(endpoint, json={"liked": True, "extra": 1}).status_code == 422
    assert client.put(endpoint, json={}).status_code == 422
    with Session(engine) as session:
        member = session.get(main.User, 2)
        member.is_active = False
        session.add(member)
        session.commit()
    assert client.put(endpoint, json={"liked": True}).status_code == 401


def test_comment_likes_use_shared_rate_limits_without_holding_a_second_connection(env, monkeypatch):
    from app.auth_rate import AuthRateBucket, bucket_key
    from app.expert_social_models import SocialCommentLike

    client, engine, _, comment_id = published_comment(env)
    client.cookies.set(main.SESSION_COOKIE, "t2")
    endpoint = f"{PREFIX}/comments/{comment_id}/like"
    with Session(engine) as session:
        session.add(AuthRateBucket(
            bucket_key=bucket_key("social-comment-like", "2"),
            attempts=60,
            reset_at=int(time.time()) + 120,
        ))
        session.commit()
    blocked = client.put(endpoint, json={"liked": True})
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    with Session(engine) as session:
        assert session.exec(select(SocialCommentLike)).all() == []
        bucket = session.get(AuthRateBucket, bucket_key("social-comment-like", "2"))
        session.delete(bucket)
        session.commit()
    small_pool = create_engine(
        engine.url, connect_args={"check_same_thread": False},
        pool_size=1, max_overflow=0, pool_timeout=0.05,
    )
    monkeypatch.setattr(main, "engine", small_pool)
    try:
        response = client.put(endpoint, json={"liked": True})
        assert response.status_code == 200, response.text
        assert response.json() == {"liked": True, "like_count": 1}
        assert small_pool.pool.checkedout() == 0
    finally:
        small_pool.dispose()


@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "DELETED"])
def test_comment_likes_do_not_expose_unpublished_comments(env, status):
    client, engine, _, comment_id = published_comment(env)
    with Session(engine) as session:
        row = session.get(SocialComment, comment_id)
        row.status = status
        session.add(row)
        session.commit()
    endpoint = f"{PREFIX}/comments/{comment_id}/like"
    client.cookies.set(main.SESSION_COOKIE, "t2")
    assert client.put(endpoint, json={"liked": True}).status_code == 404
    client.cookies.set(main.SESSION_COOKIE, "t3")
    expected = 404 if status == "DELETED" else 409
    assert client.put(endpoint, json={"liked": True}).status_code == expected


@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "DELETED"])
def test_comment_like_requires_a_published_visible_post(env, status):
    client, engine, post_id, comment_id = published_comment(env)
    with Session(engine) as session:
        row = session.get(SocialPost, post_id)
        row.status = status
        session.add(row)
        session.commit()
    endpoint = f"{PREFIX}/comments/{comment_id}/like"
    client.cookies.set(main.SESSION_COOKIE, "t2")
    assert client.put(endpoint, json={"liked": True}).status_code == 404
    client.cookies.set(main.SESSION_COOKIE, "t1")
    assert client.put(endpoint, json={"liked": True}).status_code == (404 if status == "DELETED" else 409)


@pytest.mark.parametrize("blocker,blocked", [(2, 3), (3, 2)])
def test_blocked_comment_threads_cannot_be_read_replied_to_or_liked(env, blocker, blocked):
    client, engine, post_id, comment_id = published_comment(env)
    with Session(engine) as session:
        reply = seed_comment(session, post_id, author_id=1, parent_id=comment_id)
        reply_id = reply.id
        session.add(main.UserBlock(blocker_user_id=blocker, blocked_user_id=blocked))
        session.commit()
    client.cookies.set(main.SESSION_COOKIE, "t2")
    endpoint = f"{PREFIX}/posts/{post_id}/comments"
    for params in ({}, {"threaded": True}):
        assert client.get(endpoint, params=params).json()["items"] == []
    assert client.get(endpoint, params={"parent_id": comment_id}).status_code == 404
    for ident in (comment_id, reply_id):
        assert client.put(f"{PREFIX}/comments/{ident}/like", json={"liked": True}).status_code == 404
    assert client.post(endpoint, json={"text": "Yeni bilimsel yanıt", "parent_id": comment_id, "idempotency_key": str(uuid.uuid4())}).status_code == 404


def test_thread_pages_and_reply_counts_follow_the_viewers_visible_scope(env):
    client, engine = env
    post_id = post(client).json()["id"]
    other_post_id = post(client, text="Diğer bilimsel paylaşım").json()["id"]
    with Session(engine) as session:
        root = seed_comment(session, post_id)
        second = seed_comment(session, post_id, author_id=2)
        hidden = seed_comment(session, post_id, status="PENDING")
        own_pending = seed_comment(session, post_id, author_id=2, status="PENDING")
        rejected = seed_comment(session, post_id, status="REJECTED")
        own_rejected = seed_comment(session, post_id, author_id=2, status="REJECTED")
        deleted = seed_comment(session, post_id, author_id=2, status="DELETED")
        replies = [seed_comment(session, post_id, author_id=author, status=status, parent_id=root.id)
                   for author, status in [(3,"PUBLISHED"),(3,"PENDING"),(2,"PENDING"),(3,"REJECTED"),(2,"REJECTED"),(2,"DELETED"),(1,"PUBLISHED")]]
        own_child = seed_comment(session, post_id, parent_id=own_pending.id)
        seed_comment(session, post_id, parent_id=hidden.id)
        seed_comment(session, post_id, parent_id=deleted.id)
        seed_comment(session, other_post_id, parent_id=root.id)
        deep = seed_comment(session, post_id, parent_id=replies[0].id)
        root_ids = [row.id for row in (root, second, own_pending, own_rejected)]
        reply_ids = [replies[index].id for index in (0, 2, 4, 6)]
        flat_ids = sorted(root_ids + reply_ids + [own_child.id])
        hidden_ids = [hidden.id, rejected.id, deleted.id, deep.id]
        session.commit()
    client.cookies.set(main.SESSION_COOKIE, "t2")
    endpoint = f"{PREFIX}/posts/{post_id}/comments"
    first = client.get(endpoint, params={"threaded": True, "limit": 2}).json()
    assert [row["id"] for row in first["items"]] == root_ids[:2]
    assert first["next_cursor"] == root_ids[1]
    assert [row["reply_count"] for row in first["items"]] == [4, 0]
    second_page = client.get(endpoint, params={"threaded": True, "limit": 2, "after": first["next_cursor"]}).json()
    assert [row["id"] for row in second_page["items"]] == root_ids[2:]
    assert [row["reply_count"] for row in second_page["items"]] == [1, 0]
    assert second_page["next_cursor"] is None
    first_replies = client.get(endpoint, params={"parent_id": root_ids[0], "limit": 2}).json()
    assert [row["id"] for row in first_replies["items"]] == reply_ids[:2]
    assert first_replies["reply_count"] == 4
    later_replies = client.get(endpoint, params={"parent_id": root_ids[0], "limit": 2, "after": first_replies["next_cursor"]}).json()
    assert [row["id"] for row in later_replies["items"]] == reply_ids[2:]
    assert later_replies["next_cursor"] is None
    flat = client.get(endpoint).json()
    assert [row["id"] for row in flat["items"]] == flat_ids
    assert all(row["reply_count"] == 0 for row in flat["items"] if row["parent_id"] is not None)
    assert client.get(f"{PREFIX}/posts/{other_post_id}/comments", params={"parent_id": root_ids[0]}).status_code == 404
    for ident in hidden_ids:
        assert client.get(endpoint, params={"parent_id": ident}).status_code == 404
    client.cookies.set(main.SESSION_COOKIE, "t4")
    admin_roots = client.get(endpoint, params={"threaded": True}).json()["items"]
    assert next(row for row in admin_roots if row["id"] == root_ids[0])["reply_count"] == 6
    with Session(engine) as session:
        published_count = len(session.exec(select(SocialComment).where(SocialComment.post_id == post_id, SocialComment.status == "PUBLISHED")).all())
    assert flat["comment_count"] == published_count


@pytest.mark.parametrize("blocker,blocked", [(2, 3), (3, 2)])
def test_reply_counts_exclude_blocked_reply_authors_under_a_visible_root(env, blocker, blocked):
    client, engine = env
    post_id = post(client).json()["id"]
    with Session(engine) as session:
        root = seed_comment(session, post_id, author_id=1)
        root_id = root.id
        seed_comment(session, post_id, author_id=3, parent_id=root_id)
        own = seed_comment(session, post_id, author_id=2, parent_id=root_id)
        own_id = own.id
        session.add(main.UserBlock(blocker_user_id=blocker, blocked_user_id=blocked))
        session.commit()
    client.cookies.set(main.SESSION_COOKIE, "t2")
    endpoint = f"{PREFIX}/posts/{post_id}/comments"
    roots = client.get(endpoint, params={"threaded": True}).json()["items"]
    assert len(roots) == 1 and roots[0]["reply_count"] == 1
    replies = client.get(endpoint, params={"parent_id": root_id}).json()
    assert [row["id"] for row in replies["items"]] == [own_id]
    assert replies["reply_count"] == 1


@pytest.mark.parametrize("parent_status", ["PENDING", "REJECTED", "DELETED"])
def test_orphaned_published_replies_are_hidden_from_other_viewers(env, parent_status):
    client, engine, post_id, comment_id = published_comment(env)
    with Session(engine) as session:
        root = session.get(SocialComment, comment_id)
        root.status = parent_status
        session.add(root)
        reply = seed_comment(session, post_id, author_id=2, parent_id=comment_id)
        reply_id = reply.id
        session.commit()
    client.cookies.set(main.SESSION_COOKIE, "t2")
    endpoint = f"{PREFIX}/posts/{post_id}/comments"
    assert client.get(endpoint).json()["items"] == []
    assert client.get(endpoint, params={"parent_id": comment_id}).status_code == 404
    assert client.put(f"{PREFIX}/comments/{reply_id}/like", json={"liked": True}).status_code == 404


def test_comment_thread_serialization_batches_all_metadata(env):
    client, engine = env
    post_id = post(client).json()["id"]
    with Session(engine) as session:
        for _ in range(30):
            root = seed_comment(session, post_id)
            seed_comment(session, post_id, author_id=2, parent_id=root.id)
        session.commit()
    client.cookies.set(main.SESSION_COOKIE, "t2")
    statements = []

    def observe(_connection, _cursor, statement, *_arguments):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        one = client.get(f"{PREFIX}/posts/{post_id}/comments", params={"threaded": True, "limit": 1})
        one_count = len(statements)
        statements.clear()
        many = client.get(f"{PREFIX}/posts/{post_id}/comments", params={"threaded": True, "limit": 30})
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert one.status_code == many.status_code == 200
    assert len(many.json()["items"]) == 30
    assert all(row["reply_count"] == 1 for row in many.json()["items"])
    assert len(statements) <= one_count + 1
    assert len(statements) <= 15


def test_additive_comment_like_schema_preserves_revision_and_checks_both_indexes(tmp_path):
    from app.expert_social_schema import apply, require_schema
    from app.expert_social_models import SocialCommentLike

    engine = create_engine("sqlite:///" + str(tmp_path / "comment-schema.db"))
    main.User.__table__.create(engine)
    apply(engine)
    apply(engine)
    require_schema(engine)
    assert inspect(engine).get_pk_constraint("socialcommentlike")["constrained_columns"] == ["comment_id", "user_id"]
    foreign_keys = inspect(engine).get_foreign_keys("socialcommentlike")
    assert {row["referred_table"] for row in foreign_keys} == {"socialcomment", "user"}
    assert all(row["options"]["ondelete"] == "CASCADE" for row in foreign_keys)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version FROM dental_social_revision WHERE id=1")).scalar_one() == 2
    with engine.begin() as connection:
        SocialCommentLike.__table__.drop(connection)
    with pytest.raises(RuntimeError):
        require_schema(engine)
    apply(engine)
    require_schema(engine)
    for name in ("ix_socialcomment_replies", "ix_socialcommentlike_user_id"):
        with engine.begin() as connection:
            connection.execute(text(f"DROP INDEX {name}"))
        with pytest.raises(RuntimeError):
            require_schema(engine)
        apply(engine)
        require_schema(engine)


def test_account_erasure_removes_comment_likes_from_retained_user_anchor(env):
    from app.account_erasure import begin_account_erasure
    from app.expert_social_models import SocialCommentLike

    client, engine, post_id, comment_id = published_comment(env)
    with Session(engine) as session:
        own = seed_comment(session, post_id, author_id=2)
        session.add(SocialCommentLike(comment_id=comment_id, user_id=2))
        session.add(SocialCommentLike(comment_id=comment_id, user_id=3))
        session.add(SocialCommentLike(comment_id=own.id, user_id=2))
        session.commit()
        begin_account_erasure(session, user_id=2, actor="user")
        session.commit()
        assert session.get(main.User, 2).is_active is False
        assert session.exec(select(SocialCommentLike).where(SocialCommentLike.user_id == 2)).all() == []
        assert session.get(SocialCommentLike, (comment_id, 3)) is not None
