"""Transactional moderator inbox; network delivery starts after the HTTP body."""
import asyncio
import logging

from sqlalchemy import event, update
from sqlmodel import select

logger = logging.getLogger(__name__)


def resolve_targets(session, kind, identifiers):
    """Cascades and background checks close stale alerts in their transaction."""
    if not identifiers:
        return
    from app import main
    notices = session.execute(update(main.AdminNotice).where(
        main.AdminNotice.notice_type == "SOCIAL_REVIEW_REQUIRED",
        main.AdminNotice.related_type == "social_review_" + kind.lower(),
        main.AdminNotice.related_id.in_([str(ident) for ident in identifiers]),
        main.AdminNotice.status == "ACTIVE",
    ).values(status="RESOLVED", resolved_at=main._utcnow_naive()).returning(main.AdminNotice)).scalars().all()
    for notice in notices:
        item = main._record_realtime_event(session, notice.user_id, "NOTICE_RESOLVED", "notification", notice.id,
            {"notice_id": notice.id, "notice_type": notice.notice_type})
        if "social_review_events" in session.info:
            session.info["social_review_events"].append(main.RealtimeEvent(**item.model_dump()))


def record(session, main, request, kind, row, task):
    needs_review = task.state in {"WAITING_HUMAN", "FAILED"}
    if not needs_review and row.version == 1:
        return
    admins = session.exec(select(main.User.id).where(
        main.User.role == "ADMIN", main.User.is_active == True,
        main.User.email == main.ADMIN_FIXED_EMAIL,
        main.User.email_verified_at != None,
    )).all()
    if not admins:
        return
    prepare(session, request)
    events = session.info["social_review_events"]
    for admin_id in admins:
        related = "social_review_" + kind.lower()
        resolved = main._resolve_notifications(
            session, user_id=admin_id, notice_type="SOCIAL_REVIEW_REQUIRED",
            related_type=related, related_id=row.id,
        )
        events.extend(main.RealtimeEvent(**item.model_dump()) for item in resolved)
        if needs_review:
            label = {"POST": "gönderi", "COMMENT": "yorum", "PUBLICATION": "akademik yayın"}[kind]
            _, created, _ = main._notify_user(
                session, user_id=admin_id, notice_type="SOCIAL_REVIEW_REQUIRED",
                title="Yeni içerik inceleme bekliyor",
                message=f"Yeni bir {label} yönetici incelemesi bekliyor.",
                related_type=related, related_id=row.id,
                dedup_key=f"social-review:{kind}:{row.id}:v{row.version}",
                target_url=f"{main.ADMIN_CENTER_PATH}/social?kind={kind}&target={row.id}",
            )
            if created:
                events.append(main.RealtimeEvent(**created.model_dump()))


def prepare(session, request):
    if "social_review_events" not in session.info:
        session.info["social_review_events"] = []

        def committed(candidate):
            # _notify_user uses nested savepoints. They are not a commit of
            # the surrounding content write and must not publish its events.
            if not candidate.in_nested_transaction():
                request.scope.setdefault("state", {}).setdefault("social_review_events", []).extend(
                    candidate.info.pop("social_review_events", [])
                )

        def rolled_back(candidate, transaction):
            if transaction.parent is None:
                candidate.info.pop("social_review_events", None)

        event.listen(session, "after_commit", committed)
        event.listen(session, "after_soft_rollback", rolled_back)


class ReviewNoticeMiddleware:
    def __init__(self, app, main):
        self.app, self.main = app, main

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/expert-social/"):
            return await self.app(scope, receive, send)
        status = None

        async def track(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        await self.app(scope, receive, track)
        if status is not None and status < 400:
            for item in scope.get("state", {}).pop("social_review_events", []):
                try:
                    await asyncio.wait_for(self.main._publish_realtime_event(item), timeout=5)
                except Exception:
                    # Durable notices/outbox remain available through catch-up.
                    logger.warning("social.review notification_delivery_deferred")
