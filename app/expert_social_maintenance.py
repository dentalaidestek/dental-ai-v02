"""Durable media erasure and bounded housekeeping, isolated from consultations."""

import asyncio
import logging
from datetime import timedelta
from sqlalchemy import update, delete, or_
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool
from app import object_storage
from app.expert_social_models import (
    SocialPost,
    SocialMedia,
    SocialPreview,
    SocialComment,
    SocialLike,
    SocialReport,
    SocialDecision,
    Publication,
    OrcidSync,
    DoiMatch,
    SocialMediaDeletion,
    now,
)

logger = logging.getLogger(__name__)


def enqueue(session, reference):
    # An idempotent outbox insert also handles simultaneous user/admin erasure.
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    insert = (
        pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    )
    session.execute(
        insert(SocialMediaDeletion)
        .values(
            reference=reference, attempts=0, next_attempt_at=now(), created_at=now()
        )
        .on_conflict_do_nothing(index_elements=["reference"])
    )


def remove_media(session, rows):
    for media in rows:
        enqueue(session, media.reference)
        session.exec(
            update(SocialPreview)
            .where(SocialPreview.cover_media_id == media.id)
            .values(cover_media_id=None)
        )
        session.delete(media)


def remove_post_media(session, post_id):
    remove_media(
        session,
        session.exec(
            select(SocialMedia).where(SocialMedia.post_id == post_id).with_for_update()
        ).all(),
    )
    # Deleted threads are no longer eligible for publication or admin approval.
    session.exec(
        update(SocialComment)
        .where(SocialComment.post_id == post_id, SocialComment.status != "DELETED")
        .values(
            text="",
            status="DELETED",
            version=SocialComment.version + 1,
            updated_at=now(),
        )
    )


def erase_user_content(session, user_id):
    for post in session.exec(
        select(SocialPost).where(SocialPost.author_id == user_id).with_for_update()
    ).all():
        post.status = "DELETED"
        post.text = ""
        post.link_url = None
        post.preview_json = None
        post.pinned = False
        post.version += 1
        session.add(post)
        remove_post_media(session, post.id)
    remove_media(
        session,
        session.exec(select(SocialMedia).where(SocialMedia.owner_id == user_id)).all(),
    )
    session.exec(
        update(SocialComment)
        .where(SocialComment.author_id == user_id)
        .values(
            text="",
            status="DELETED",
            version=SocialComment.version + 1,
            updated_at=now(),
        )
    )
    session.exec(
        update(SocialDecision)
        .where(SocialDecision.actor_id == user_id)
        .values(actor_id=None)
    )
    for model, column in (
        (SocialLike, SocialLike.user_id),
        (SocialReport, SocialReport.reporter_id),
        (SocialPreview, SocialPreview.owner_id),
        (DoiMatch, DoiMatch.owner_id),
        (Publication, Publication.expert_id),
        (OrcidSync, OrcidSync.expert_id),
    ):
        session.exec(delete(model).where(column == user_id))


def cleanup_slice(engine):
    """Lease one deletion at a time; external I/O never holds a DB transaction."""
    with Session(engine) as s:
        cutoff = now() - timedelta(days=1)
        rows = s.exec(
            select(SocialMedia)
            .where(SocialMedia.post_id == None, SocialMedia.created_at < cutoff)
            .order_by(SocialMedia.id)
            .limit(10)
            .with_for_update(skip_locked=True)
        ).all()
        remove_media(s, rows)
        # Temporary bibliographic suggestions carry no long-term user value.
        s.exec(
            delete(SocialPreview).where(
                SocialPreview.created_at < now() - timedelta(days=2)
            )
        )
        s.exec(delete(DoiMatch).where(DoiMatch.created_at < now() - timedelta(days=2)))
        s.commit()
    for _ in range(2):
        with Session(engine, expire_on_commit=False) as s:
            row = s.exec(
                select(SocialMediaDeletion)
                .where(SocialMediaDeletion.next_attempt_at <= now())
                .order_by(SocialMediaDeletion.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if not row:
                break
            row.attempts += 1
            row.next_attempt_at = now() + timedelta(minutes=5)
            s.add(row)
            s.commit()
            reference = row.reference
        try:
            object_storage.delete(reference)
        except Exception:
            # Keep the outbox entry for restart/network recovery. Do not log
            # the object reference, clinical contents, or the exception payload.
            logger.warning("social.media_delete deferred")
            continue
        with Session(engine) as s:
            current = s.get(SocialMediaDeletion, reference)
            if current and current.attempts == row.attempts:
                s.delete(current)
                s.commit()


async def embedded(engine_provider):
    while True:
        try:
            await run_in_threadpool(cleanup_slice, engine_provider())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("social.maintenance deferred")
        await asyncio.sleep(60)
