"""Real comment-reaction contention and cascades in an isolated PostgreSQL cluster."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from sqlalchemy import delete, event
from sqlmodel import Session, select

from app import main
from app.expert_social_models import SocialComment, SocialCommentLike, SocialPost
from app.expert_social_schema import apply, require_schema
from test_comment_threads_api import seed_comment
from test_orcid_postgres import client, setup_social
from test_postgres import pg_engine


def seed_thread(engine, *, reply=False):
    with Session(engine) as session:
        post = SocialPost(
            author_id=1,
            text="Bilimsel tartışma",
            status="PUBLISHED",
            idempotency_key="thread-post",
            request_hash="synthetic",
        )
        session.add(post)
        session.flush()
        root = seed_comment(session, post.id, author_id=1)
        child = seed_comment(session, post.id, author_id=1, parent_id=root.id) if reply else None
        ids = post.id, root.id, child.id if child else None
        session.commit()
        return ids


def test_postgres_concurrent_comment_like_and_unlike_are_idempotent(pg_engine, monkeypatch):
    app = setup_social(pg_engine, monkeypatch)
    post_id, comment_id, _ = seed_thread(pg_engine)
    ready = Barrier(4)

    def synchronize(_connection, _cursor, statement, *_arguments):
        if "FROM socialpost" in statement and "FOR UPDATE" in statement:
            ready.wait(timeout=5)

    def submit(liked):
        requester = client(app)
        try:
            return requester.put(f"/api/expert-social/comments/{comment_id}/like", json={"liked": liked})
        finally:
            requester.close()

    event.listen(pg_engine, "before_cursor_execute", synchronize)
    try:
        for liked, count in ((True, 1), (False, 0)):
            with ThreadPoolExecutor(max_workers=4) as workers:
                responses = list(workers.map(submit, [liked] * 4))
            assert [response.status_code for response in responses] == [200] * 4, [response.text for response in responses]
            assert all(response.json() == {"liked": liked, "like_count": count} for response in responses)
    finally:
        event.remove(pg_engine, "before_cursor_execute", synchronize)
    with Session(pg_engine) as session:
        assert session.exec(select(SocialCommentLike)).all() == []
    response = client(app).get(f"/api/expert-social/posts/{post_id}/comments", params={"threaded": True})
    assert response.json()["items"][0]["liked"] is False
    assert response.json()["items"][0]["like_count"] == 0
    assert pg_engine.pool.checkedout() == 0


def test_postgres_reply_like_waits_for_root_deletion_and_rechecks_visibility(pg_engine, monkeypatch):
    app = setup_social(pg_engine, monkeypatch)
    post_id, root_id, reply_id = seed_thread(pg_engine, reply=True)
    attempting_post_lock = Event()

    def observe(_connection, _cursor, statement, *_arguments):
        if "FROM socialpost" in statement and "FOR UPDATE" in statement:
            attempting_post_lock.set()

    with Session(pg_engine) as deleting:
        deleting.exec(select(SocialPost).where(SocialPost.id == post_id).with_for_update()).one()
        root = deleting.get(SocialComment, root_id)
        root.status = "DELETED"
        root.text = ""
        deleting.add(root)
        deleting.flush()
        event.listen(pg_engine, "before_cursor_execute", observe)
        try:
            with ThreadPoolExecutor(max_workers=1) as workers:
                future = workers.submit(lambda: client(app).put(
                    f"/api/expert-social/comments/{reply_id}/like", json={"liked": True},
                ))
                assert attempting_post_lock.wait(5)
                deleting.commit()
                response = future.result(timeout=5)
            assert response.status_code == 404, response.text
        finally:
            event.remove(pg_engine, "before_cursor_execute", observe)
    with Session(pg_engine) as session:
        assert session.exec(select(SocialCommentLike)).all() == []


def test_postgres_comment_likes_cascade_on_comment_and_account_deletion(pg_engine, monkeypatch):
    setup_social(pg_engine, monkeypatch)
    apply(pg_engine)
    require_schema(pg_engine)
    post_id, comment_id, _ = seed_thread(pg_engine)
    with Session(pg_engine) as session:
        session.add(main.User(id=2, username="local-liker", role="DOCTOR", display_name="Local Liker"))
        session.commit()
        session.add(SocialCommentLike(comment_id=comment_id, user_id=1))
        session.add(SocialCommentLike(comment_id=comment_id, user_id=2))
        session.commit()
        session.exec(delete(main.User).where(main.User.id == 2))
        session.commit()
        likes = session.exec(select(SocialCommentLike)).all()
        assert [(row.comment_id, row.user_id) for row in likes] == [(comment_id, 1)]
        session.exec(delete(SocialComment).where(SocialComment.id == comment_id))
        session.commit()
        assert session.exec(select(SocialCommentLike)).all() == []
        assert session.get(SocialPost, post_id) is not None
