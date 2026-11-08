from datetime import timedelta
from pathlib import Path
from sqlmodel import Session, select
from test_api import env, post
from app.expert_social_models import SocialMedia, SocialPost, SocialPreview, DoiMatch
from app.expert_social_maintenance import cleanup_slice, erase_user_content
from app.expert_social_models import now


def test_deleted_post_media_is_durably_removed(env, tmp_path):
    c, e = env
    image = tmp_path / "private.jpg"
    image.write_bytes(b"test")
    with Session(e) as s:
        m = SocialMedia(owner_id=1, reference=str(image))
        s.add(m)
        s.commit()
        mid = m.id
    p = post(c, media_ids=[mid]).json()
    assert c.delete("/api/expert-social/posts/" + str(p["id"])).status_code == 200
    cleanup_slice(e)
    assert not image.exists()


def test_expired_draft_cleanup_does_not_delete_live_post_media(env, tmp_path):
    c, e = env
    live = tmp_path / "live.jpg"
    live.write_bytes(b"live")
    orphan = tmp_path / "orphan.jpg"
    orphan.write_bytes(b"old")
    with Session(e) as s:
        attached = SocialMedia(
            owner_id=1, reference=str(live), created_at=now() - timedelta(days=2)
        )
        s.add(attached)
        s.commit()
        ident = attached.id
        s.add(
            SocialMedia(
                owner_id=1, reference=str(orphan), created_at=now() - timedelta(days=2)
            )
        )
        s.commit()
    assert post(c, media_ids=[ident]).status_code == 200
    cleanup_slice(e)
    assert live.exists() and not orphan.exists()


def test_account_erasure_clears_social_content_and_queues_media(env, tmp_path):
    c, e = env
    p = post(c).json()
    with Session(e) as s:
        erase_user_content(s, 1)
        s.commit()
        row = s.get(SocialPost, p["id"])
        assert row.status == "DELETED" and row.text == ""
    c.cookies.set(
        __import__("app.main", fromlist=["SESSION_COOKIE"]).SESSION_COOKIE, "t2"
    )
    assert c.get("/api/expert-social/posts/" + str(p["id"])).status_code == 404


def test_expired_suggestions_are_removed_in_bounded_slices(env):
    _, engine = env
    cutoff = now() - timedelta(days=3)
    with Session(engine) as session:
        session.add_all(
            SocialPreview(owner_id=1, url="https://example.org/", metadata_json="{}", created_at=cutoff)
            for _ in range(700)
        )
        session.add_all(DoiMatch(owner_id=1, metadata_json="{}", created_at=cutoff) for _ in range(700))
        session.commit()
    cleanup_slice(engine)
    with Session(engine) as session:
        assert len(session.exec(select(SocialPreview)).all()) == 200
        assert len(session.exec(select(DoiMatch)).all()) == 200
    cleanup_slice(engine)
    with Session(engine) as session:
        assert session.exec(select(SocialPreview)).all() == []
        assert session.exec(select(DoiMatch)).all() == []
