"""Member-only social extension. Existing consultation routes remain unchanged."""

from __future__ import annotations
import asyncio
import base64
import binascii
import hashlib
import json
import os
import re
import uuid
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Literal
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, ConfigDict, Field as Input
from sqlalchemy import and_, delete, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool
from app import (
    expert_social_safety as safety,
    expert_social_moderation as moderation,
    expert_publications as bibliography,
    object_storage,
)
from app.expert_social_models import (
    SocialPost,
    SocialFollow,
    SocialMedia,
    SocialPreview,
    SocialComment,
    SocialCommentLike,
    SocialLike,
    SocialReport,
    SocialDecision,
    SocialModerationTask,
    SocialModerationEvent,
    Publication,
    OrcidSync,
    DoiMatch,
    now,
)
from app.auth_rate import admit
from app.expert_social_identity import expert_display_name
from app.expert_social_relationships import unblocked_relationship_condition
from app.expert_consultation_requests import consultation_expert_is_verified

HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    "Vary": "Cookie",
}
NETWORK_SLOTS = asyncio.Semaphore(3)
IMAGE_SLOT = threading.BoundedSemaphore(1)
BODY_READ_TIMEOUT = 30


def _encode_moderation_cursor(kind, waiting_since, ident):
    boundary = [kind, waiting_since.isoformat(timespec="microseconds"), ident]
    return "m1_" + base64.urlsafe_b64encode(
        json.dumps(boundary, separators=(",", ":")).encode("ascii")
    ).decode("ascii").rstrip("=")


def _decode_moderation_cursor(value, kind, status):
    """Bounded URL-safe boundary; numeric cursors remain compatible."""
    try:
        if not value or len(value) > 192:
            raise ValueError()
        if re.fullmatch(r"[1-9][0-9]{0,18}", value):
            ident = int(value)
            if ident > 2**63 - 1:
                raise ValueError()
            return ident
        if status != "PENDING" or not re.fullmatch(r"m1_[A-Za-z0-9_-]+", value):
            raise ValueError()
        encoded = value[3:]
        boundary = json.loads(base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True,
        ).decode("ascii"))
        if not isinstance(boundary, list) or len(boundary) != 3:
            raise ValueError()
        scope, timestamp, ident = boundary
        if (scope != kind or not isinstance(timestamp, str) or len(timestamp) != 26
                or type(ident) is not int or not 1 <= ident <= 2**63 - 1):
            raise ValueError()
        waiting_since = datetime.fromisoformat(timestamp)
        if waiting_since.tzinfo is not None or waiting_since.isoformat(timespec="microseconds") != timestamp:
            raise ValueError()
        return waiting_since, ident
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        raise HTTPException(400, "İnceleme sayfasını yeniden açın.") from None


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PostBody(Body):
    text: str = Input(default="", max_length=5000)
    idempotency_key: uuid.UUID
    media_ids: list[int] = Input(default_factory=list, max_length=4)
    link_url: Optional[str] = Input(default=None, max_length=2048)
    preview_id: Optional[int] = None
    cover_media_id: Optional[int] = None


class PostPatch(Body):
    version: int = Input(ge=1)
    text: Optional[str] = Input(default=None, max_length=5000)
    pinned: Optional[bool] = None
    comments_closed: Optional[bool] = None


class CommentBody(Body):
    text: str = Input(min_length=1, max_length=1500)
    parent_id: Optional[int] = None
    idempotency_key: uuid.UUID


class CommentPatch(Body):
    text: str = Input(min_length=1, max_length=1500)
    version: int = Input(ge=1)


class LinkBody(Body):
    url: str = Input(max_length=2048)


class FollowBody(Body):
    followed: bool


class LikeBody(Body):
    liked: bool


class ReportBody(Body):
    target_type: Literal["POST", "COMMENT"]
    target_id: int = Input(ge=1)
    reason: Literal["PRIVACY", "ABUSE", "SPAM", "MISLEADING", "OTHER"]


class ReviewBody(Body):
    status: Literal["PUBLISHED", "REJECTED", "PENDING"]
    version: int = Input(ge=1)
    reason: str = Input(min_length=3, max_length=300)


class PublicationBody(Body):
    version: Optional[int] = Input(default=None, ge=1)
    title: str = Input(min_length=1, max_length=500)
    authors: str = Input(default="", max_length=2000)
    year: Optional[int] = Input(default=None, ge=1000, le=2200)
    journal: str = Input(default="", max_length=300)
    doi: Optional[str] = Input(default=None, max_length=300)
    url: Optional[str] = Input(default=None, max_length=2048)
    description: str = Input(default="", max_length=2000)
    match_id: Optional[int] = None


class OrcidBody(Body):
    orcid: str = Input(max_length=100)


class DoiBody(Body):
    doi: str = Input(max_length=300)


class SocialBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app
        self.active = 0
        self.uploads = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith(
            "/api/expert-social/"
        ):
            return await self.app(scope, receive, send)

        async def private_send(message):
            if message["type"] == "http.response.start":
                names = {k.lower().encode() for k in HEADERS}
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() not in names
                ]
                headers.extend(
                    (k.lower().encode(), v.encode()) for k, v in HEADERS.items()
                )
                message = {**message, "headers": headers}
            await send(message)

        if scope.get("method") in ("GET", "HEAD"):
            return await self.app(scope, receive, private_send)
        is_upload = scope["path"].endswith("/media")
        if self.active >= 8 or (is_upload and self.uploads >= 1):
            return await JSONResponse(
                {"detail": "İşlem yoğunluğu nedeniyle biraz sonra yeniden deneyin."},
                status_code=503,
                headers={**HEADERS, "Retry-After": "3"},
            )(scope, receive, private_send)
        self.active += 1
        if is_upload:
            self.uploads += 1
        try:
            return await self.buffered(scope, receive, private_send, is_upload)
        finally:
            self.active -= 1
            if is_upload:
                self.uploads -= 1

    async def buffered(self, scope, receive, send, is_upload):
        limit = safety.MAX_IMAGE_BYTES + 65536 if is_upload else 65536
        length = dict(scope.get("headers", [])).get(b"content-length", b"")
        if length.isdigit() and int(length) > limit:
            return await JSONResponse(
                {"detail": "İstek boyut sınırını aşıyor."},
                status_code=413,
                headers=HEADERS,
            )(scope, receive, send)
        # Bound allocation by payload bytes, rather than the number of ASGI
        # chunks. Slow/empty chunks must not retain an upload admission forever.
        data = bytearray()
        try:
            async with asyncio.timeout(BODY_READ_TIMEOUT):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(data) + len(chunk) > limit:
                        return await JSONResponse(
                            {"detail": "İstek boyut sınırını aşıyor."},
                            status_code=413,
                            headers=HEADERS,
                        )(scope, receive, send)
                    data.extend(chunk)
                    if not message.get("more_body"):
                        break
        except TimeoutError:
            return await JSONResponse(
                {"detail": "İstek gövdesi zamanında alınamadı. Yeniden deneyin."},
                status_code=408,
                headers=HEADERS,
            )(scope, receive, send)
        payload = bytes(data)
        del data
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": payload, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)


def register(app, main):
    r = APIRouter(prefix="/api/expert-social")

    def actor(request):
        u = main.get_current_user(request)
        if not u or not u.is_active:
            raise HTTPException(401, "Üye girişi gerekiyor.")
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("origin")
            if (
                request.headers.get("X-Dental-Social") != "1"
                or request.headers.get("sec-fetch-site") == "cross-site"
                or (
                    origin
                    and (urlsplit(origin).scheme, urlsplit(origin).netloc)
                    != (request.url.scheme, request.url.netloc)
                )
            ):
                raise HTTPException(403, "İstek doğrulanamadı. Sayfayı yeniden açın.")
        # Resolve MFA authorization before opening a content transaction. Reuse
        # it only within this request, so admin reads also need one connection.
        request.state.social_admin = (
            main._admin_only(request) if u.role == "ADMIN" else None
        )
        return u

    def admin(request):
        actor(request)
        user = request.state.social_admin
        if not user:
            raise HTTPException(403, "Yönetici doğrulaması gerekiyor.")
        return user

    def expert(s, user_id, *, lock=False, write=False):
        stmt = select(main.ExpertProfile).where(main.ExpertProfile.user_id == user_id)
        p = s.exec(stmt.with_for_update() if lock else stmt).first()
        u = s.get(main.User, user_id)
        if (
            not u
            or not u.is_active
            or u.role not in ("DOCTOR", "ADMIN")
            or not p
            or p.application_status != "APPROVED"
            or p.verification_status != "VERIFIED"
            or not p.specialty_verified
            or not p.credential_document_path
            or not p.phone
        ):
            raise HTTPException(
                403 if write else 404, "Aktif ve doğrulanmış uzman profili gerekiyor."
            )
        if write:
            policy = s.exec(
                select(main.ExpertPolicyState).where(
                    main.ExpertPolicyState.expert_user_id == user_id
                )
            ).first()
            if p.availability == "PASSIVE" or (
                policy and main._expert_is_blocked(policy)
            ):
                raise HTTPException(403, "Uzman hesabı şu anda paylaşım yapamıyor.")
        return p

    def throttle(user, action, limit=20, window=60):
        try:
            admit(
                main.engine,
                "social-" + action,
                str(user.id),
                limit=limit,
                window=window,
            )
        except HTTPException as exc:
            if exc.status_code == 429:
                exc.detail = "Çok hızlı işlem yapıyorsunuz. Biraz sonra tekrar deneyin."
            raise

    def load_post(s, ident, user, request, *, lock=False):
        stmt = select(SocialPost).where(SocialPost.id == ident)
        p = s.exec(stmt.with_for_update() if lock else stmt).first()
        if not p or p.status == "DELETED":
            raise HTTPException(404, "Gönderi bulunamadı.")
        is_admin = bool(request.state.social_admin)
        if user.id != p.author_id and not is_admin and main._users_blocked(s,user.id,p.author_id):
            raise HTTPException(404,'Gönderi bulunamadı.')
        if user.id != p.author_id and not is_admin:
            if p.status != "PUBLISHED":
                raise HTTPException(404, "Gönderi bulunamadı.")
            expert(s, p.author_id)
        return p

    def decision(s, kind, row, actor_id=None, reason=None, *, human=False, preserve=False, request=None):
        s.add(
            SocialDecision(
                target_type=kind,
                target_id=row.id,
                actor_id=actor_id,
                status=row.status,
                version=row.version,
                reason=reason or row.reasons_json,
            )
        )
        if request is not None and not preserve:
            from app.expert_social_review_notifications import prepare
            prepare(s, request)
        task = moderation.record(s, kind, row, actor_id, reason, human=human, preserve=preserve)
        if request is not None and not preserve:
            from app.expert_social_review_notifications import record
            record(s, main, request, kind, row, task)

    def review_text(value, link, metadata):
        card = json.loads(metadata) if metadata else {}
        return "\n".join(
            [
                value,
                link or "",
                *(
                    str(card.get(k) or "")
                    for k in ("title", "description", "site_name")
                ),
            ]
        )

    def assert_version(row, v):
        if row.version != v:
            raise HTTPException(
                409, "İçerik değişti. Güncel kaydı açıp yeniden deneyin."
            )

    def previous_post(s, user, body, request_hash):
        previous = s.exec(
            select(SocialPost).where(
                SocialPost.author_id == user.id,
                SocialPost.idempotency_key == str(body.idempotency_key),
            )
        ).first()
        if previous:
            if previous.request_hash != request_hash:
                raise HTTPException(409, "Bu paylaşım isteği farklı içerikle kullanıldı.")
            if previous.status == "DELETED":
                raise HTTPException(409, "Gönderi silinmiş. Yeni bir paylaşım oluşturun.")
        return previous

    def post_rows(s, rows, user, *, admin_view=False):
        if not rows:
            return []
        ids = [p.id for p in rows]
        authors = {p.author_id for p in rows}
        likes = dict(
            s.exec(
                select(SocialLike.post_id, func.count())
                .where(SocialLike.post_id.in_(ids))
                .group_by(SocialLike.post_id)
            ).all()
        )
        comments = dict(
            s.exec(
                select(SocialComment.post_id, func.count())
                .where(
                    SocialComment.post_id.in_(ids), SocialComment.status == "PUBLISHED"
                )
                .group_by(SocialComment.post_id)
            ).all()
        )
        liked = set(
            s.exec(
                select(SocialLike.post_id).where(
                    SocialLike.post_id.in_(ids), SocialLike.user_id == user.id
                )
            ).all()
        )
        media = s.exec(
            select(SocialMedia)
            .where(SocialMedia.post_id.in_(ids))
            .order_by(SocialMedia.position)
        ).all()
        users = {
            u.id: u
            for u in s.exec(select(main.User).where(main.User.id.in_(authors))).all()
        }
        profiles = {
            p.user_id: p
            for p in s.exec(
                select(main.ExpertProfile).where(
                    main.ExpertProfile.user_id.in_(authors)
                )
            ).all()
        }
        lifecycle = moderation.metadata(s, "POST", [
            p for p in rows if p.author_id == user.id or admin_view
        ])
        result = []
        for p in rows:
            u = users[p.author_id]
            profile = profiles.get(p.author_id)
            data = {
                k: getattr(p, k)
                for k in (
                    "id",
                    "author_id",
                    "text",
                    "status",
                    "link_url",
                    "cover_media_id",
                    "pinned",
                    "comments_closed",
                    "version",
                )
            }
            data.update(
                author_name=expert_display_name(profile, u.display_name),
                author_photo=main._profile_photo_url(u),
                created_at=p.created_at.isoformat() + "Z",
                like_count=likes.get(p.id, 0),
                comment_count=comments.get(p.id, 0),
                liked=p.id in liked,
                owned=p.author_id == user.id,
                preview=json.loads(p.preview_json) if p.preview_json else None,
                media=[
                    {"id": m.id, "url": f"/api/expert-social/media/{m.id}"}
                    for m in media
                    if m.post_id == p.id
                ],
            )
            if p.id in lifecycle:
                data["moderation"] = lifecycle[p.id]
            result.append(data)
        return result

    def comment_visibility(user, model=SocialComment, *, admin_view=False):
        conditions = [model.status != "DELETED"]
        if not admin_view:
            conditions.extend((
                or_(model.status == "PUBLISHED", model.author_id == user.id),
                unblocked_relationship_condition(main, user.id, model.author_id),
            ))
        return and_(*conditions)

    def comment_thread_visibility(user, model=SocialComment, *, admin_view=False):
        parent = aliased(SocialComment)
        visible_parent = select(parent.id).where(
            parent.id == model.parent_id,
            parent.post_id == model.post_id,
            parent.parent_id == None,
            comment_visibility(user, parent, admin_view=admin_view),
        ).exists()
        return and_(
            comment_visibility(user, model, admin_view=admin_view),
            or_(model.parent_id == None, visible_parent),
        )

    def comment_rows(s, rows, user, *, admin_view=False):
        if not rows:
            return []
        ids = [c.id for c in rows]
        root_ids = [c.id for c in rows if c.parent_id is None]
        likes = dict(s.exec(
            select(SocialCommentLike.comment_id, func.count())
            .where(SocialCommentLike.comment_id.in_(ids))
            .group_by(SocialCommentLike.comment_id)
        ).all())
        liked = set(s.exec(select(SocialCommentLike.comment_id).where(
            SocialCommentLike.comment_id.in_(ids),
            SocialCommentLike.user_id == user.id,
        )).all())
        reply_counts = dict(s.exec(
            select(SocialComment.parent_id, func.count())
            .where(
                SocialComment.post_id.in_({c.post_id for c in rows if c.parent_id is None}),
                SocialComment.parent_id.in_(root_ids),
                comment_thread_visibility(user, admin_view=admin_view),
            ).group_by(SocialComment.parent_id)
        ).all()) if root_ids else {}
        users = {
            u.id: u
            for u in s.exec(
                select(main.User).where(main.User.id.in_({c.author_id for c in rows}))
            ).all()
        }
        profiles = {p.user_id: p for p in s.exec(select(main.ExpertProfile).where(
            main.ExpertProfile.user_id.in_({c.author_id for c in rows})
        )).all()}
        verified = {ident: consultation_expert_is_verified(member, profiles.get(ident))
                    for ident, member in users.items()}
        lifecycle = moderation.metadata(s, "COMMENT", [
            c for c in rows if c.author_id == user.id or admin_view
        ])
        return [
            {
                **{
                    k: getattr(c, k)
                    for k in (
                        "id",
                        "post_id",
                        "parent_id",
                        "text",
                        "status",
                        "version",
                        "author_id",
                    )
                },
                "author_name": expert_display_name(profiles[c.author_id], users[c.author_id].display_name)
                    if verified[c.author_id] else users[c.author_id].display_name,
                "author_photo": main._profile_photo_url(users[c.author_id]),
                "author_profile_url": f"/expert-support/expert/{c.author_id}" if verified[c.author_id] else None,
                "author_verified": verified[c.author_id],
                "owned": c.author_id == user.id,
                "like_count": likes.get(c.id, 0),
                "liked": c.id in liked,
                "reply_count": reply_counts.get(c.id, 0),
                "created_at": c.created_at.isoformat() + "Z",
                **({"moderation": lifecycle[c.id]} if c.id in lifecycle else {}),
            }
            for c in rows
        ]

    def comment_write_response(s, comment, user, *, admin_view=False):
        data = comment_rows(s, [comment], user, admin_view=admin_view)[0]
        data["comment_count"] = s.exec(
            select(func.count()).select_from(SocialComment).where(
                SocialComment.post_id == comment.post_id,
                SocialComment.status == "PUBLISHED",
            )
        ).one()
        if comment.parent_id is not None:
            data["parent_reply_count"] = s.exec(
                select(func.count()).select_from(SocialComment).where(
                    SocialComment.post_id == comment.post_id,
                    SocialComment.parent_id == comment.parent_id,
                    comment_thread_visibility(user, admin_view=admin_view),
                )
            ).one()
        return data

    def save_image(user, raw):
        if os.getenv("RENDER") and not object_storage.enabled():
            raise HTTPException(503, "Kalıcı görsel deposu şu an kullanılamıyor.")
        try:
            with IMAGE_SLOT:
                clean = safety.clean_image(raw)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        reference = f"uploads/expert-social/{user.id}/{uuid.uuid4().hex}.jpg"
        try:
            object_storage.write_bytes(reference, clean, content_type="image/jpeg")
        except object_storage.ObjectStorageError as exc:
            raise HTTPException(503, "Görsel yüklenemedi. Yeniden deneyin.") from exc
        try:
            with Session(main.engine, expire_on_commit=False) as s:
                expert(s, user.id, write=True)
                m = SocialMedia(owner_id=user.id, reference=reference)
                s.add(m)
                s.commit()
        except Exception:
            # Account revocation/transaction failure can happen during upload.
            # Release the database before remote deletion, and retain a durable
            # retry if storage is temporarily unavailable.
            try:
                object_storage.delete(reference)
            except (OSError, object_storage.ObjectStorageError):
                from app.expert_social_maintenance import enqueue

                with Session(main.engine) as cleanup:
                    enqueue(cleanup, reference)
                    cleanup.commit()
            raise
        return m

    @r.post("/media")
    def upload(request: Request, file: UploadFile = File(...)):
        u = actor(request)
        throttle(u, "upload", 12, 600)
        with Session(main.engine) as s:
            expert(s, u.id, write=True)
        if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise HTTPException(400, "JPEG, PNG veya WebP kullanın.")
        raw = file.file.read(safety.MAX_IMAGE_BYTES + 1)
        m = save_image(u, raw)
        return {"id": m.id, "url": f"/api/expert-social/media/{m.id}"}

    @r.get("/media/{ident}")
    def media(request: Request, ident: int):
        u = actor(request)
        with Session(main.engine) as s:
            m = s.get(SocialMedia, ident)
            if not m:
                raise HTTPException(404, "Görsel bulunamadı.")
            if u.id != m.owner_id:
                is_admin = bool(request.state.social_admin)
                if m.post_id:
                    load_post(s, m.post_id, u, request)
                elif not is_admin:
                    raise HTTPException(404, "Görsel bulunamadı.")
            reference = m.reference
        try:
            with object_storage.object_cache.scope():
                path = object_storage.ensure_local(reference)
                # Keep response independent of a short-lived materialization scope.
                raw = Path(path).read_bytes()
        except (FileNotFoundError, object_storage.ObjectStorageError) as exc:
            raise HTTPException(503, "Görsel şu an yüklenemiyor.") from exc
        from fastapi.responses import Response

        return Response(
            raw,
            media_type="image/jpeg",
            headers={**HEADERS, "Content-Security-Policy": "default-src 'none'"},
        )

    @r.post("/preview")
    async def link_preview(request: Request, body: LinkBody):
        u = await run_in_threadpool(actor, request)
        await run_in_threadpool(throttle, u, "preview", 12, 60)

        def check():
            with Session(main.engine) as s:
                expert(s, u.id, write=True)

        await run_in_threadpool(check)
        try:
            url = safety.safe_url(body.url)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        cover = None
        try:
            async with NETWORK_SLOTS:
                async with asyncio.timeout(12):
                    metadata = await safety.preview(url)
                    image_url = metadata.pop("image_url", None)
                    if image_url:
                        try:
                            raw, _, _ = await safety.fetch_bytes(
                                image_url,
                                limit=safety.MAX_IMAGE_BYTES,
                                accept="image/*",
                            )
                            cover = await run_in_threadpool(save_image, u, raw)
                        except (ValueError, HTTPException, OSError, TimeoutError):
                            pass
        except Exception:
            return JSONResponse(
                {
                    "available": False,
                    "url": url,
                    "domain": urlsplit(url).hostname,
                    "message": "Önizleme alınamadı; bağlantıyı paylaşabilirsiniz.",
                },
                headers=HEADERS,
            )

        def store_preview():
            with Session(main.engine, expire_on_commit=False) as s:
                row = SocialPreview(
                    owner_id=u.id,
                    url=url,
                    metadata_json=json.dumps(metadata, ensure_ascii=False),
                    cover_media_id=cover.id if cover else None,
                )
                s.add(row)
                s.commit()
                return row.id

        ident = await run_in_threadpool(store_preview)
        return JSONResponse(
            {
                "available": True,
                "id": ident,
                **metadata,
                "cover": (
                    {"id": cover.id, "url": f"/api/expert-social/media/{cover.id}"}
                    if cover
                    else None
                ),
            },
            headers=HEADERS,
        )

    @r.post("/posts")
    def create_post(request: Request, body: PostBody):
        u = actor(request)
        request_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
        # A retry keeps its original result, including when the write allowance
        # is exhausted. Release this read before shared rate admission opens its
        # own transaction; never require a second connection while holding locks.
        with Session(main.engine) as s:
            previous = previous_post(s, u, body, request_hash)
            if previous:
                expert(s, u.id, write=True)
                return post_rows(s, [previous], u)[0]
        throttle(u, "post", 10, 600)
        with Session(main.engine, expire_on_commit=False) as s:
            expert(s, u.id, write=True, lock=True)
            previous = previous_post(s, u, body, request_hash)
            if previous:
                return post_rows(s, [previous], u)[0]
            text_value = body.text.strip()
            link = None
            try:
                link = safety.safe_url(body.link_url) if body.link_url else None
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            ids = list(dict.fromkeys(body.media_ids))
            metadata = None
            cover = body.cover_media_id
            if body.preview_id:
                preview = s.get(SocialPreview, body.preview_id)
                if not preview or preview.owner_id != u.id or preview.url != link:
                    raise HTTPException(400, "Bağlantı önizlemesi geçersiz.")
                metadata = preview.metadata_json
                if not cover:
                    cover = preview.cover_media_id
            if cover and cover not in ids:
                ids.append(cover)
            if len(ids) > 4:
                raise HTTPException(400, "En fazla dört görsel ekleyin.")
            media = (
                s.exec(
                    select(SocialMedia).where(SocialMedia.id.in_(ids)).with_for_update()
                ).all()
                if ids
                else []
            )
            if len(media) != len(ids) or any(
                m.owner_id != u.id or m.post_id is not None for m in media
            ):
                raise HTTPException(403, "Görseller bu paylaşım için kullanılamaz.")
            if not text_value and not ids and not link:
                raise HTTPException(400, "Bir metin, görsel veya bağlantı ekleyin.")
            # A repeated payload with a fresh request key is still spam.
            recent = s.exec(
                select(SocialPost).where(
                    SocialPost.author_id == u.id,
                    SocialPost.text == text_value,
                    SocialPost.link_url == link,
                    SocialPost.status != "DELETED",
                    SocialPost.created_at > now() - timedelta(minutes=2),
                )
            ).first()
            if recent:
                raise HTTPException(429, "Bu içeriği kısa süre önce paylaştınız.")
            status, reasons = moderation.evaluate(
                review_text(text_value, link, metadata), has_images=bool(ids)
            )
            p = SocialPost(
                author_id=u.id,
                text=text_value,
                link_url=link,
                preview_json=metadata,
                cover_media_id=cover,
                status=status,
                reasons_json=json.dumps(reasons),
                idempotency_key=str(body.idempotency_key),
                request_hash=request_hash,
            )
            s.add(p)
            try:
                s.flush()
                for m in media:
                    m.post_id = p.id
                    m.position = ids.index(m.id)
                    s.add(m)
                decision(s, "POST", p, request=request)
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                previous = s.exec(
                    select(SocialPost).where(
                        SocialPost.author_id == u.id,
                        SocialPost.idempotency_key == str(body.idempotency_key),
                    )
                ).first()
                if previous and previous.request_hash == request_hash:
                    return post_rows(s, [previous], u)[0]
                raise HTTPException(
                    409, "Paylaşım değişti. Sayfayı yeniden açın."
                ) from exc
            return post_rows(s, [p], u)[0]

    @r.get("/experts/{expert_id}/stats")
    def profile_stats(request: Request, expert_id: int):
        u = actor(request)
        with Session(main.engine) as s:
            expert(s, expert_id)
            if u.id != expert_id and main._users_blocked(s, u.id, expert_id):
                raise HTTPException(404, "Uzman profili bulunamadı.")
            from app.expert_social_relationships import relationship_counts
            relationships=relationship_counts(s,main,expert_id)
            count = lambda model, *conditions: s.exec(
                select(func.count()).select_from(model).where(*conditions)
            ).one()
            return {
                **relationships,
                "posts": count(
                    SocialPost,
                    SocialPost.author_id == expert_id,
                    SocialPost.status == "PUBLISHED",
                ),
                "publications": count(
                    Publication,
                    Publication.expert_id == expert_id,
                    Publication.deleted == False,
                    Publication.status == "PUBLISHED",
                ),
                "following_by_viewer": bool(s.get(SocialFollow, (u.id, expert_id))),
            }

    @r.put("/experts/{expert_id}/follow")
    def follow_expert(request: Request, expert_id: int, body: FollowBody):
        u = actor(request)
        throttle(u, "follow", 30)
        if u.id == expert_id:
            raise HTTPException(400, "Kendi profilinizi takip edemezsiniz.")
        with Session(main.engine) as s:
            expert(s, expert_id, lock=True)
            if body.followed and main._users_blocked(s,u.id,expert_id):
                raise HTTPException(403,'Bu hesapla takip ilişkisi kurulamıyor.')
            row = s.get(SocialFollow, (u.id, expert_id))
            if body.followed and not row:
                s.add(SocialFollow(follower_id=u.id, expert_id=expert_id))
            if not body.followed and row:
                s.delete(row)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
        return {"following_by_viewer": body.followed}

    @r.get("/experts/{expert_id}/posts")
    def feed(
        request: Request,
        expert_id: int,
        before: Optional[int] = Query(default=None, ge=1),
        limit: int = Query(default=15, ge=1, le=30),
    ):
        u = actor(request)
        with Session(main.engine) as s:
            expert(s, expert_id)
            if u.id != expert_id and main._users_blocked(s, u.id, expert_id):
                raise HTTPException(404, "Uzman profili bulunamadı.")
            scope = select(SocialPost).where(
                SocialPost.author_id == expert_id, SocialPost.status != "DELETED"
            )
            if u.id != expert_id:
                scope = scope.where(SocialPost.status == "PUBLISHED")
            pinned = (
                s.exec(scope.where(SocialPost.pinned == True)).first()
                if before is None
                else None
            )
            stmt = scope.where(SocialPost.pinned == False)
            if before:
                stmt = stmt.where(SocialPost.id < before)
            rows = list(
                s.exec(stmt.order_by(SocialPost.id.desc()).limit(limit + 1)).all()
            )
            more = len(rows) > limit
            rows = rows[:limit]
            cursor = rows[-1].id if more else None
            if pinned:
                rows.insert(0, pinned)
            return JSONResponse(
                {"items": post_rows(s, rows, u), "next_cursor": cursor}, headers=HEADERS
            )

    @r.get("/posts/{ident}")
    def get_post(request: Request, ident: int):
        u = actor(request)
        with Session(main.engine) as s:
            return JSONResponse(
                post_rows(s, [load_post(s, ident, u, request)], u)[0], headers=HEADERS
            )

    @r.patch("/posts/{ident}")
    def edit_post(request: Request, ident: int, body: PostPatch):
        u = actor(request)
        throttle(u, "edit")
        with Session(main.engine, expire_on_commit=False) as s:
            expert(s, u.id, lock=True, write=True)
            p = load_post(s, ident, u, request, lock=True)
            if p.author_id != u.id:
                raise HTTPException(403, "Bu gönderiyi düzenleyemezsiniz.")
            assert_version(p, body.version)
            if body.text is not None:
                p.text = body.text.strip()
                images = s.exec(
                    select(SocialMedia.id).where(SocialMedia.post_id == p.id)
                ).first()
                if not p.text and not images and not p.link_url:
                    raise HTTPException(400, "Gönderi boş olamaz.")
                p.status, reasons = moderation.evaluate(
                    review_text(p.text, p.link_url, p.preview_json),
                    has_images=bool(images),
                )
                p.reasons_json = json.dumps(reasons)
            if body.pinned is not None:
                if body.pinned and p.status != "PUBLISHED":
                    raise HTTPException(
                        409, "Yalnızca yayınlanmış gönderi sabitlenebilir."
                    )
                for old in s.exec(
                    select(SocialPost).where(
                        SocialPost.author_id == u.id,
                        SocialPost.pinned == True,
                        SocialPost.id != p.id,
                    )
                ).all():
                    old.pinned = False
                    s.add(old)
                s.flush()
                p.pinned = body.pinned
            if p.status != "PUBLISHED":
                p.pinned = False
            if body.comments_closed is not None:
                p.comments_closed = body.comments_closed
            p.version += 1
            p.updated_at = now()
            s.add(p)
            decision(s, "POST", p, u.id, preserve=body.text is None, request=request)
            s.commit()
            return post_rows(s, [p], u)[0]

    @r.delete("/posts/{ident}")
    def delete_post(request: Request, ident: int):
        u = actor(request)
        with Session(main.engine) as s:
            p = load_post(s, ident, u, request, lock=True)
            if p.author_id != u.id and not request.state.social_admin:
                raise HTTPException(403, "Bu gönderiyi silemezsiniz.")
            p.status = "DELETED"
            p.pinned = False
            p.version += 1
            p.text = ""
            p.preview_json = None
            p.link_url = None
            s.add(p)
            from app.expert_social_maintenance import remove_post_media

            remove_post_media(s, p.id)
            decision(
                s,
                "POST",
                p,
                u.id,
                "DELETED_BY_OWNER" if p.author_id == u.id else "DELETED_BY_ADMIN",
                request=request,
            )
            s.commit()
        return {"ok": True}

    @r.put("/posts/{ident}/like")
    def like(request: Request, ident: int, body: LikeBody):
        u = actor(request)
        throttle(u, "like", 60)
        with Session(main.engine) as s:
            p = load_post(s, ident, u, request, lock=True)
            if p.status != "PUBLISHED":
                raise HTTPException(409, "Gönderi yayınlanmamış.")
            old = s.get(SocialLike, (ident, u.id))
            if body.liked and not old:
                s.add(SocialLike(post_id=ident, user_id=u.id))
            if not body.liked and old:
                s.delete(old)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
            return {
                "liked": body.liked,
                "like_count": s.exec(
                    select(func.count())
                    .select_from(SocialLike)
                    .where(SocialLike.post_id == ident)
                ).one(),
            }

    @r.get("/posts/{ident}/comments")
    def comments(
        request: Request,
        ident: int,
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=50),
        threaded: bool = False,
        parent_id: Optional[int] = Query(default=None, ge=1),
    ):
        u = actor(request)
        with Session(main.engine) as s:
            p = load_post(s, ident, u, request)
            is_admin = bool(request.state.social_admin)
            if parent_id is not None:
                parent = s.exec(select(SocialComment.id).where(
                    SocialComment.id == parent_id,
                    SocialComment.post_id == ident,
                    SocialComment.parent_id == None,
                    comment_visibility(u, admin_view=is_admin),
                )).first()
                if parent is None:
                    raise HTTPException(404, "Ana yorum bulunamadı.")
            stmt = select(SocialComment).where(
                SocialComment.post_id == ident,
                SocialComment.id > after,
                comment_thread_visibility(u, admin_view=is_admin),
            )
            if parent_id is not None:
                stmt = stmt.where(SocialComment.parent_id == parent_id)
            elif threaded:
                stmt = stmt.where(SocialComment.parent_id == None)
            rows = list(s.exec(stmt.order_by(SocialComment.id).limit(limit + 1)).all())
            more = len(rows) > limit
            rows = rows[:limit]
            return JSONResponse(
                {
                    "items": comment_rows(s, rows, u, admin_view=is_admin),
                    "next_cursor": rows[-1].id if more else None,
                    "comment_count": s.exec(select(func.count()).select_from(SocialComment).where(
                        SocialComment.post_id == ident, SocialComment.status == "PUBLISHED"
                    )).one(),
                    **({"reply_count": s.exec(
                        select(func.count()).select_from(SocialComment).where(
                            SocialComment.post_id == ident,
                            SocialComment.parent_id == parent_id,
                            comment_thread_visibility(u, admin_view=is_admin),
                        )
                    ).one()} if parent_id is not None else {}),
                },
                headers=HEADERS,
            )

    @r.post("/posts/{ident}/comments")
    def create_comment(request: Request, ident: int, body: CommentBody):
        u = actor(request)
        value = body.text.strip()
        if not value:
            raise HTTPException(400, "Yorum boş olamaz.")

        def previous_comment(s):
            old = s.exec(
                select(SocialComment).where(
                    SocialComment.author_id == u.id,
                    SocialComment.idempotency_key == str(body.idempotency_key),
                )
            ).first()
            if old and (
                old.post_id != ident
                or old.text != value
                or old.parent_id != body.parent_id
                or old.status == "DELETED"
            ):
                raise HTTPException(409, "Yorum isteği değişmiş.")
            if old and not s.exec(select(SocialComment.id).where(
                SocialComment.id == old.id,
                comment_thread_visibility(u, admin_view=bool(request.state.social_admin)),
            )).first():
                raise HTTPException(404, "Yorum bulunamadı.")
            return old

        with Session(main.engine) as s:
            old = previous_comment(s)
            if old:
                p = load_post(s, ident, u, request)
                if p.status != "PUBLISHED" or p.comments_closed:
                    raise HTTPException(409, "Bu gönderide yorumlar kapalı.")
                return comment_write_response(s, old, u, admin_view=bool(request.state.social_admin))
        throttle(u, "comment", 12)
        with Session(main.engine, expire_on_commit=False) as s:
            p = load_post(s, ident, u, request, lock=True)
            if p.status != "PUBLISHED" or p.comments_closed:
                raise HTTPException(409, "Bu gönderide yorumlar kapalı.")
            old = previous_comment(s)
            if old:
                return comment_write_response(s, old, u, admin_view=bool(request.state.social_admin))
            if body.parent_id:
                parent = s.get(SocialComment, body.parent_id)
                if (
                    not parent
                    or parent.post_id != ident
                    or parent.status != "PUBLISHED"
                    or parent.parent_id
                ):
                    raise HTTPException(
                        400, "Yanıt için yayınlanmış bir ana yorum seçin."
                    )
                if (not request.state.social_admin
                        and main._users_blocked(s, u.id, parent.author_id)):
                    raise HTTPException(404, "Ana yorum bulunamadı.")
            if s.exec(
                select(SocialComment.id).where(
                    SocialComment.author_id == u.id,
                    SocialComment.text == value,
                    SocialComment.created_at > now() - timedelta(minutes=2),
                )
            ).first():
                raise HTTPException(429, "Aynı yorumu kısa süre önce gönderdiniz.")
            status, reasons = moderation.evaluate(value)
            c = SocialComment(
                post_id=ident,
                author_id=u.id,
                parent_id=body.parent_id,
                text=value,
                status=status,
                reasons_json=json.dumps(reasons),
                idempotency_key=str(body.idempotency_key),
            )
            s.add(c)
            try:
                s.flush()
                decision(s, "COMMENT", c, request=request)
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                raise HTTPException(409, "Bu yorum isteği zaten kullanıldı.") from exc
            return comment_write_response(s, c, u, admin_view=bool(request.state.social_admin))

    @r.put("/comments/{ident}/like")
    def like_comment(request: Request, ident: int, body: LikeBody):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        u = actor(request)
        throttle(u, "comment-like", 60)
        with Session(main.engine) as s:
            # Erasure retains the account row. Share-lock it before content
            # locks so erasure removes this reaction or rejects a late writer.
            member_stmt = select(main.User).where(main.User.id == u.id)
            if s.get_bind().dialect.name == "postgresql":
                member_stmt = member_stmt.with_for_update(read=True, key_share=True)
            member = s.exec(member_stmt).first()
            if not member or not member.is_active:
                raise HTTPException(401, "Üye girişi gerekiyor.")
            original = s.get(SocialComment, ident)
            if not original:
                raise HTTPException(404, "Yorum bulunamadı.")
            # Match reply creation/deletion's post-before-comment lock order.
            p = load_post(s, original.post_id, u, request, lock=True)
            comment = s.exec(select(SocialComment).where(
                SocialComment.id == ident,
                comment_thread_visibility(u, admin_view=bool(request.state.social_admin)),
            ).with_for_update().execution_options(populate_existing=True)).first()
            if not comment:
                raise HTTPException(404, "Yorum bulunamadı.")
            if p.status != "PUBLISHED" or comment.status != "PUBLISHED":
                raise HTTPException(409, "Yalnızca yayınlanmış yorumlar beğenilebilir.")
            if body.liked:
                insert = pg_insert if s.get_bind().dialect.name == "postgresql" else sqlite_insert
                s.execute(insert(SocialCommentLike).values(
                    comment_id=ident, user_id=u.id,
                ).on_conflict_do_nothing(index_elements=["comment_id", "user_id"]))
            else:
                s.exec(delete(SocialCommentLike).where(
                    SocialCommentLike.comment_id == ident,
                    SocialCommentLike.user_id == u.id,
                ))
            liked = s.exec(select(SocialCommentLike.comment_id).where(
                SocialCommentLike.comment_id == ident,
                SocialCommentLike.user_id == u.id,
            )).first() is not None
            count = s.exec(select(func.count()).select_from(SocialCommentLike).where(
                SocialCommentLike.comment_id == ident,
            )).one()
            s.commit()
            return {"liked": liked, "like_count": count}

    @r.patch("/comments/{ident}")
    def edit_comment(request: Request, ident: int, body: CommentPatch):
        u = actor(request)
        throttle(u, "comment-edit")
        with Session(main.engine, expire_on_commit=False) as s:
            c = s.exec(
                select(SocialComment).where(SocialComment.id == ident).with_for_update()
            ).first()
            if not c or c.status == "DELETED":
                raise HTTPException(404, "Yorum bulunamadı.")
            if c.author_id != u.id:
                raise HTTPException(403, "Bu yorumu düzenleyemezsiniz.")
            p = load_post(s, c.post_id, u, request)
            if p.comments_closed:
                raise HTTPException(409, "Yorumlar kapalı.")
            assert_version(c, body.version)
            c.text = body.text.strip()
            if not c.text:
                raise HTTPException(400, "Yorum boş olamaz.")
            c.status, reasons = moderation.evaluate(c.text)
            c.reasons_json = json.dumps(reasons)
            c.version += 1
            c.updated_at = now()
            s.add(c)
            decision(s, "COMMENT", c, u.id, request=request)
            s.commit()
            return comment_write_response(s, c, u, admin_view=bool(request.state.social_admin))

    @r.delete("/comments/{ident}")
    def delete_comment(request: Request, ident: int):
        u = actor(request)
        with Session(main.engine) as s:
            c = s.get(SocialComment, ident)
            if not c or c.status == "DELETED":
                raise HTTPException(404, "Yorum bulunamadı.")
            # Serialize parent deletion with comment/reply creation on this post.
            p = load_post(s, c.post_id, u, request, lock=True)
            c = s.exec(select(SocialComment).where(SocialComment.id == ident)
                       .with_for_update().execution_options(populate_existing=True)).first()
            if not c or c.status == "DELETED":
                raise HTTPException(404, "Yorum bulunamadı.")
            if u.id not in (c.author_id, p.author_id) and not request.state.social_admin:
                raise HTTPException(403, "Bu yorumu yönetemezsiniz.")
            affected = s.exec(select(SocialComment.id, SocialComment.version).where(
                SocialComment.post_id == p.id, SocialComment.status != "DELETED",
                or_(SocialComment.id == ident, SocialComment.parent_id == ident),
            )).all()
            s.exec(update(SocialComment).where(
                SocialComment.post_id == p.id, SocialComment.status != "DELETED",
                or_(SocialComment.id == ident, SocialComment.parent_id == ident),
            ).values(status="DELETED", text="", version=SocialComment.version + 1, updated_at=now()))
            decision(s, "COMMENT", c, u.id, "COMMENT_REMOVED", request=request)
            moderation.cancel_tasks(s, kind="COMMENT", versions={
                row_id: version + 1 for row_id, version in affected if row_id != ident
            })
            count = s.exec(select(func.count()).select_from(SocialComment).where(
                SocialComment.post_id == p.id, SocialComment.status == "PUBLISHED"
            )).one()
            s.commit()
        return {"ok": True, "comment_count": count, "removed_count": len(affected)}

    @r.post("/reports")
    def report(request: Request, body: ReportBody):
        u = actor(request)
        throttle(u, "report", 10, 600)
        with Session(main.engine) as s:
            if body.target_type == "POST":
                load_post(s, body.target_id, u, request)
            else:
                c = s.get(SocialComment, body.target_id)
                if not c or c.status != "PUBLISHED":
                    raise HTTPException(404, "Yorum bulunamadı.")
                load_post(s, c.post_id, u, request)
            s.add(SocialReport(reporter_id=u.id, **body.model_dump()))
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
        return {"ok": True}

    def publication_data(s, u, body):
        values = body.model_dump(exclude={"match_id", "version"})
        values["title"] = body.title.strip()
        if not values["title"]:
            raise HTTPException(400, "Makale başlığı girin.")
        try:
            values["doi"] = bibliography.normalize_doi(body.doi or "")
            values["url"] = (
                safety.safe_url(body.url)
                if body.url
                else ("https://doi.org/" + values["doi"] if values["doi"] else None)
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        values["fingerprint"] = bibliography.fingerprint(
            values["title"], body.year, values["doi"]
        )
        values["title_key"] = bibliography.fingerprint(values["title"], body.year, None)
        values["status"], reasons = moderation.evaluate(
            " ".join(str(v or "") for v in values.values())
        )
        values["reasons_json"] = json.dumps(reasons)
        values["source"] = "MANUAL"
        values["source_key"] = None
        values["source_orcid"] = None
        if body.match_id:
            match = s.get(DoiMatch, body.match_id)
            if (
                match
                and match.owner_id == u.id
                and match.created_at > now() - timedelta(days=1)
            ):
                metadata = json.loads(match.metadata_json)
                if all(
                    values.get(k) == metadata.get(k)
                    for k in ("title", "authors", "year", "journal", "doi", "url")
                ):
                    values["source"] = "DOI_MATCH"
        return values

    def publication_row(row, s=None, user=None, *, admin_view=False):
        data = json.loads(row.model_dump_json(
            exclude={"fingerprint", "title_key", "expert_id", "deleted", "reasons_json"}
        ))
        if s is not None and user is not None and (row.expert_id == user.id or admin_view):
            data["moderation"] = moderation.metadata(s, "PUBLICATION", [row])[row.id]
        return data

    @r.get("/experts/{expert_id}/publications")
    def publications(
        request: Request,
        expert_id: int,
        before: Optional[int] = Query(default=None, ge=1),
        limit: int = Query(default=30, ge=1, le=50),
    ):
        u = actor(request)
        with Session(main.engine) as s:
            expert(s, expert_id)
            stmt = select(Publication).where(
                Publication.expert_id == expert_id, Publication.deleted == False
            )
            if u.id != expert_id:
                stmt = stmt.where(Publication.status == "PUBLISHED")
            total = s.exec(select(func.count()).select_from(stmt.subquery())).one()
            if before:
                stmt = stmt.where(Publication.id < before)
            rows = list(
                s.exec(stmt.order_by(Publication.id.desc()).limit(limit + 1)).all()
            )
            more = len(rows) > limit
            rows = rows[:limit]
            sync = s.get(OrcidSync, expert_id) if u.id == expert_id else None
            lifecycle = moderation.metadata(s, "PUBLICATION", rows) if u.id == expert_id else {}
            return JSONResponse(
                {
                    "items": [
                        {**json.loads(
                            p.model_dump_json(
                                exclude={
                                    "fingerprint",
                                    "title_key",
                                    "expert_id",
                                    "deleted",
                                    "reasons_json",
                                }
                            )
                        ), **({"moderation": lifecycle[p.id]} if p.id in lifecycle else {})}
                        for p in rows
                    ],
                    "next_cursor": rows[-1].id if more else None,
                    "sync": json.loads(sync.model_dump_json()) if sync else None,
                    "total": total,
                },
                headers=HEADERS,
            )

    @r.post("/publications")
    def add_publication(request: Request, body: PublicationBody):
        u = actor(request)
        throttle(u, "publication", 30, 600)
        with Session(main.engine, expire_on_commit=False) as s:
            expert(s, u.id, write=True, lock=True)
            row = Publication(expert_id=u.id, **publication_data(s, u, body))
            s.add(row)
            try:
                s.flush()
                decision(s, "PUBLICATION", row, u.id, request=request)
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                raise HTTPException(409, "Bu DOI veya yayın zaten kayıtlı.") from exc
            return publication_row(row, s, u)

    @r.put("/publications/{ident}")
    def edit_publication(request: Request, ident: int, body: PublicationBody):
        u = actor(request)
        throttle(u, "publication-edit")
        with Session(main.engine, expire_on_commit=False) as s:
            expert(s, u.id, lock=True, write=True)
            row = s.exec(
                select(Publication).where(Publication.id == ident).with_for_update()
            ).first()
            if not row or row.deleted:
                raise HTTPException(404, "Yayın bulunamadı.")
            if row.expert_id != u.id:
                raise HTTPException(403, "Bu yayını yönetemezsiniz.")
            if body.version is None:
                raise HTTPException(422, "Yayın sürümü gerekiyor. Güncel kaydı açın.")
            assert_version(row, body.version)
            for k, v in publication_data(s, u, body).items():
                setattr(row, k, v)
            row.updated_at = now()
            row.version += 1
            s.add(row)
            try:
                s.flush()
                decision(s, "PUBLICATION", row, u.id, request=request)
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                raise HTTPException(409, "Bu DOI veya yayın zaten kayıtlı.") from exc
            return publication_row(row, s, u)

    @r.post("/publications/{ident}/share-preview")
    def publication_share_preview(request: Request, ident: int):
        u = actor(request)
        throttle(u, "publication-preview", 20)
        with Session(main.engine, expire_on_commit=False) as s:
            expert(s, u.id, write=True)
            paper = s.get(Publication, ident)
            if not paper or paper.deleted:
                raise HTTPException(404, "Yayın bulunamadı.")
            if paper.expert_id != u.id:
                raise HTTPException(403, "Bu yayın sizin profilinizde değil.")
            url = paper.url or ("https://doi.org/" + paper.doi if paper.doi else None)
            if not url:
                raise HTTPException(400, "Yayına bir kaynak bağlantısı ekleyin.")
            data = {
                "url": url,
                "domain": urlsplit(url).hostname,
                "site_name": paper.journal or "Akademik yayın",
                "title": paper.title,
                "description": " · ".join(
                    str(v) for v in (paper.journal, paper.year) if v
                ),
            }
            preview = SocialPreview(
                owner_id=u.id,
                url=url,
                metadata_json=json.dumps(data, ensure_ascii=False),
            )
            s.add(preview)
            s.commit()
            return {"available": True, "id": preview.id, "cover": None, **data}

    @r.delete("/publications/{ident}")
    def delete_publication(request: Request, ident: int):
        u = actor(request)
        with Session(main.engine) as s:
            row = s.exec(
                select(Publication).where(Publication.id == ident).with_for_update()
            ).first()
            if not row:
                raise HTTPException(404, "Yayın bulunamadı.")
            if row.expert_id != u.id:
                raise HTTPException(403, "Bu yayını yönetemezsiniz.")
            # Hard deletion permits adding the same DOI again. ORCID sync is explicit.
            row.status = "DELETED"
            row.version += 1
            decision(s, "PUBLICATION", row, u.id, "PUBLICATION_REMOVED", request=request)
            s.delete(row)
            s.commit()
        return {"ok": True}

    @r.post("/doi")
    async def lookup_doi(request: Request, body: DoiBody):
        u = await run_in_threadpool(actor, request)
        await run_in_threadpool(throttle, u, "doi", 10, 60)

        def check():
            with Session(main.engine) as s:
                expert(s, u.id, write=True)

        await run_in_threadpool(check)
        try:
            async with NETWORK_SLOTS:
                metadata = await bibliography.crossref(body.doi)
        except Exception as exc:
            raise HTTPException(
                422, "DOI bilgileri alınamadı. Alanları kendiniz doldurabilirsiniz."
            ) from exc

        def store_match():
            with Session(main.engine, expire_on_commit=False) as s:
                row = DoiMatch(owner_id=u.id, metadata_json=json.dumps(metadata))
                s.add(row)
                s.commit()
                return row.id

        ident = await run_in_threadpool(store_match)
        return {"match_id": ident, **metadata}

    @r.post("/orcid/sync")
    async def sync_orcid(request: Request, body: OrcidBody):
        u = await run_in_threadpool(actor, request)
        await run_in_threadpool(throttle, u, "orcid", 3, 600)
        try:
            orcid = bibliography.normalize_orcid(body.orcid)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        def begin():
            with Session(main.engine) as s:
                expert(s, u.id, write=True, lock=True)
                sync = s.get(OrcidSync, u.id)
                if (
                    sync
                    and sync.status == "RUNNING"
                    and sync.last_attempt_at
                    and sync.last_attempt_at > now() - timedelta(minutes=2)
                ):
                    raise HTTPException(409, "ORCID aktarımı sürüyor.")
                if not sync:
                    sync = OrcidSync(expert_id=u.id, orcid=orcid)
                sync.orcid = orcid
                sync.status = "RUNNING"
                sync.last_attempt_at = now()
                sync.error_code = None
                s.add(sync)
                s.commit()

        await run_in_threadpool(begin)
        try:
            async with NETWORK_SLOTS:
                rows = await bibliography.orcid_works(orcid)
                if len(rows) > bibliography.MAX_ORCID_WORKS:
                    raise bibliography.OrcidWorkLimitError()
        except Exception as exc:
            limited = isinstance(exc, bibliography.OrcidWorkLimitError)
            error_code = "ORCID_WORK_LIMIT" if limited else "ORCID_UNAVAILABLE"
            message = (
                str(exc)
                if limited
                else "ORCID yayınları alınamadı. Manuel yayın ekleyebilirsiniz."
            )

            def fail():
                with Session(main.engine) as s:
                    sync = s.get(OrcidSync, u.id)
                    sync.status = "FAILED"
                    sync.error_code = error_code
                    s.add(sync)
                    s.commit()

            await run_in_threadpool(fail)
            return JSONResponse(
                {
                    "ok": False,
                    "error_code": error_code,
                    "message": message,
                },
                status_code=200,
                headers=HEADERS,
            )

        def finish():
            with Session(main.engine) as s:
                profile = expert(s, u.id, lock=True, write=True)
                keys = {
                    bibliography.fingerprint(v["title"], v["year"], v["doi"])
                    for v in rows
                }
                title_keys = {
                    bibliography.fingerprint(v["title"], v["year"], None)
                    for v in rows
                }
                dois = {v["doi"] for v in rows if v["doi"]}
                imported_sources = {v["source_key"] for v in rows}
                existing = s.exec(
                    select(
                        Publication.fingerprint,
                        Publication.doi,
                        Publication.title_key,
                        Publication.source_orcid,
                        Publication.source_key,
                    ).where(
                        Publication.expert_id == u.id,
                        or_(
                            Publication.fingerprint.in_(keys),
                            Publication.title_key.in_(title_keys),
                            Publication.doi.in_(dois),
                            (Publication.source_orcid == orcid)
                            & Publication.source_key.in_(imported_sources),
                        ),
                    )
                ).all()
                fingerprints = {x.fingerprint for x in existing}
                doi_set = {x.doi for x in existing if x.doi}
                titles = {x.title_key for x in existing}
                source_keys = {(x.source_orcid, x.source_key) for x in existing}
                count = 0
                imported = []
                for values in rows:
                    key = bibliography.fingerprint(
                        values["title"], values["year"], values["doi"]
                    )
                    title_key = bibliography.fingerprint(
                        values["title"], values["year"], None
                    )
                    if (
                        key in fingerprints
                        or title_key in titles
                        or (orcid, values["source_key"]) in source_keys
                        or (values["doi"] and values["doi"] in doi_set)
                    ):
                        continue
                    status, reasons = moderation.evaluate(
                        " ".join(str(v or "") for v in values.values())
                    )
                    publication = Publication(
                        expert_id=u.id,
                        source_orcid=orcid,
                        fingerprint=key,
                        title_key=title_key,
                        status=status,
                        reasons_json=json.dumps(reasons),
                        **values,
                    )
                    s.add(publication)
                    imported.append(publication)
                    fingerprints.add(key)
                    titles.add(title_key)
                    source_keys.add((orcid, values["source_key"]))
                    if values["doi"]:
                        doi_set.add(values["doi"])
                    count += 1
                # Obtain generated IDs in one bounded flush, then insert audit
                # rows together. Avoid two round trips for every ORCID work.
                s.flush()
                for publication in imported:
                    decision(s, "PUBLICATION", publication, request=request)
                profile.orcid_url = "https://orcid.org/" + orcid
                s.add(profile)
                sync = s.get(OrcidSync, u.id)
                sync.status = "SUCCEEDED"
                sync.imported_count = count
                sync.last_success_at = now()
                s.add(sync)
                s.commit()
                return {
                    "ok": True,
                    "imported_count": count,
                    "message": f"{count} yeni ORCID kaydı eklendi.",
                }

        return await run_in_threadpool(finish)

    @r.get("/moderation-status/{kind}/{ident}")
    def moderation_status(
        request: Request, kind: Literal["POST", "COMMENT", "PUBLICATION"], ident: int
    ):
        u = actor(request)
        with Session(main.engine) as s:
            row = s.get(moderation.MODELS[kind], ident)
            if (not row or row.status == "DELETED" or getattr(row, "deleted", False)
                    or (moderation.owner_id(kind, row) != u.id and not request.state.social_admin)):
                raise HTTPException(404, "İçerik bulunamadı.")
            return JSONResponse({
                "target_type": kind, "target_id": ident, "status": row.status,
                "version": row.version,
                "moderation": moderation.metadata(s, kind, [row])[row.id],
            }, headers=HEADERS)

    @r.get("/moderation")
    def queue(
        request: Request,
        before: Optional[str] = Query(default=None),
        kind: Literal["POST", "COMMENT", "PUBLICATION"] = "POST",
        status: Literal["PENDING", "PUBLISHED", "REJECTED"] = "PENDING",
    ):
        u = admin(request)
        with Session(main.engine) as s:
            model = (
                SocialPost
                if kind == "POST"
                else (SocialComment if kind == "COMMENT" else Publication)
            )
            # Capture the sort timestamp in the page query. Later reviews or
            # deletions must not move the next page's original boundary.
            waiting = func.coalesce(SocialModerationTask.waiting_since, model.created_at)
            stmt = select(model, waiting).outerjoin(SocialModerationTask,
                (SocialModerationTask.target_type == kind) &
                (SocialModerationTask.target_id == model.id),
            ).where(model.status == status)
            if kind == "PUBLICATION":
                stmt = stmt.where(Publication.deleted == False)
            if before is not None:
                cursor = _decode_moderation_cursor(before, kind, status)
                if status == "PENDING":
                    if isinstance(cursor, int):
                        # Accept a cursor issued by the previous build. All new
                        # pending pages issue a self-contained stable token.
                        cursor = s.exec(select(waiting, model.id).select_from(model)
                            .outerjoin(SocialModerationTask,
                                (SocialModerationTask.target_type == kind) &
                                (SocialModerationTask.target_id == model.id))
                            .where(model.id == cursor)).first()
                        if not cursor:
                            raise HTTPException(400, "İnceleme sayfasını yeniden açın.")
                    stmt = stmt.where(or_(waiting > cursor[0],
                        and_(waiting == cursor[0], model.id > cursor[1])))
                else:
                    stmt = stmt.where(model.id < cursor)
            order = (waiting.asc(), model.id.asc()) if status == "PENDING" else (model.id.desc(),)
            page = list(s.exec(stmt.order_by(*order).limit(31)).all())
            more = len(page) > 30
            page = page[:30]
            rows = [entry[0] for entry in page]
            next_cursor = (_encode_moderation_cursor(kind, page[-1][1], rows[-1].id)
                           if status == "PENDING" else rows[-1].id) if more else None
            data = (
                post_rows(s, rows, u, admin_view=True)
                if kind == "POST"
                else (
                    comment_rows(s, rows, u, admin_view=True)
                    if kind == "COMMENT"
                    else [
                        json.loads(
                            x.model_dump_json(
                                exclude={"fingerprint", "title_key", "reasons_json"}
                            )
                        )
                        for x in rows
                    ]
                )
            )
            for row, item in zip(rows, data):
                item["reasons"] = json.loads(row.reasons_json)
            if kind == "PUBLICATION":
                lifecycle = moderation.metadata(s, kind, rows)
                for row, item in zip(rows, data):
                    item["moderation"] = lifecycle[row.id]
            return JSONResponse(
                {"items": data, "next_cursor": next_cursor,
                 "aging": moderation.aging(s)},
                headers=HEADERS,
            )

    @r.get("/reports")
    def reports(request: Request, before: Optional[int] = Query(default=None, ge=1)):
        admin(request)
        with Session(main.engine) as s:
            stmt = select(SocialReport).where(SocialReport.resolved_at == None)
            if before:
                stmt = stmt.where(SocialReport.id < before)
            rows = list(s.exec(stmt.order_by(SocialReport.id.desc()).limit(31)).all())
            more = len(rows) > 30
            rows = rows[:30]
            return {
                "items": [x.model_dump() for x in rows],
                "next_cursor": rows[-1].id if more else None,
            }

    @r.get("/moderation/{kind}/{ident}")
    def review_detail(
        request: Request, kind: Literal["POST", "COMMENT", "PUBLICATION"], ident: int
    ):
        u = admin(request)
        with Session(main.engine) as s:
            row = s.get(
                (
                    SocialPost
                    if kind == "POST"
                    else (SocialComment if kind == "COMMENT" else Publication)
                ),
                ident,
            )
            if not row or row.status == "DELETED" or getattr(row, "deleted", False):
                raise HTTPException(404, "İçerik bulunamadı.")
            item = (
                post_rows(s, [row], u, admin_view=True)[0]
                if kind == "POST"
                else (
                    comment_rows(s, [row], u, admin_view=True)[0]
                    if kind == "COMMENT"
                    else publication_row(row, s, u, admin_view=True)
                )
            )
            history = s.exec(
                select(SocialDecision)
                .where(
                    SocialDecision.target_type == kind,
                    SocialDecision.target_id == ident,
                )
                .order_by(SocialDecision.id.desc())
                .limit(50)
            ).all()
            operational = s.exec(select(SocialModerationEvent).where(
                SocialModerationEvent.target_type == kind,
                SocialModerationEvent.target_id == ident,
            ).order_by(SocialModerationEvent.id.desc()).limit(50)).all()
            return {"item": item, "history": [h.model_dump() for h in history],
                    "moderation_history": [h.model_dump() for h in operational]}

    @r.post("/moderation/{kind}/{ident}")
    def review(
        request: Request,
        kind: Literal["POST", "COMMENT", "PUBLICATION"],
        ident: int,
        body: ReviewBody,
    ):
        u = admin(request)
        with Session(main.engine, expire_on_commit=False) as s:
            model = (
                SocialPost
                if kind == "POST"
                else (SocialComment if kind == "COMMENT" else Publication)
            )
            row = s.exec(
                select(model).where(model.id == ident).with_for_update()
            ).first()
            if not row or row.status == "DELETED" or getattr(row, "deleted", False):
                raise HTTPException(404, "İçerik bulunamadı.")
            assert_version(row, body.version)
            reason = body.reason.strip()
            if len(reason) < 3:
                raise HTTPException(422, "İnceleme gerekçesini yazın.")
            if body.status == "PUBLISHED":
                expert(
                    s,
                    (
                        row.author_id
                        if kind == "POST"
                        else (
                            s.get(SocialPost, row.post_id).author_id
                            if kind == "COMMENT"
                            else row.expert_id
                        )
                    ),
                    write=True,
                )
                if kind == "COMMENT":
                    commenter = s.get(main.User, row.author_id)
                    if not commenter or not commenter.is_active:
                        raise HTTPException(409, "Yorum yazarı hesabı aktif değil.")
            row.status = body.status
            row.version += 1
            row.updated_at = now()
            if kind == "POST" and body.status != "PUBLISHED":
                row.pinned = False
            s.add(row)
            decision(s, kind, row, u.id, reason, human=True, request=request)
            for report in s.exec(
                select(SocialReport).where(
                    SocialReport.target_type == kind,
                    SocialReport.target_id == ident,
                    SocialReport.resolved_at == None,
                )
            ).all():
                report.resolved_at = now()
                s.add(report)
            if kind == "COMMENT":
                parent = s.get(SocialPost, row.post_id)
                target_url = f"/expert-support/expert/{parent.author_id}?post={parent.id}"
            elif kind == "PUBLICATION":
                target_url = "/expert-support/profile?tab=publications"
            else:
                target_url = f"/expert-support/profile?post={row.id}"
            outcome = "CHANGES_REQUESTED" if body.status == "PENDING" else body.status
            message = {
                "PUBLISHED": "İçeriğiniz yayınlandı. Ayrıntıları görüntüleyebilirsiniz.",
                "REJECTED": "İçeriğiniz yayınlanmadı. İnceleme sonucunu görüntüleyebilirsiniz.",
                "PENDING": "İçeriğiniz için düzenleme istendi. Ayrıntıları görüntüleyebilirsiniz.",
            }[body.status]
            _, notice_event, _ = main._notify_user(
                s, user_id=moderation.owner_id(kind, row), actor_user_id=u.id,
                notice_type="SOCIAL_MODERATION_" + outcome,
                title="İçerik incelemeniz tamamlandı", message=message,
                related_type="social_" + kind.lower(), related_id=row.id,
                dedup_key=f"social-moderation:{kind}:{row.id}:v{row.version}",
                target_url=target_url,
            )
            s.commit()
            response = {"ok": True, "status": row.status, "version": row.version,
                        "moderation": moderation.metadata(s, kind, [row])[row.id]}
        if notice_event:
            try:
                main.on_loop(main._publish_realtime_event, notice_event)
            except Exception:
                # Durable notification/event rows remain available to catch-up.
                main.logger.warning("social.moderation notice_publish_deferred")
        return response

    @app.get(main.ADMIN_CENTER_PATH + "/social")
    def moderation_page(request: Request):
        u = admin(request)
        return main.templates.TemplateResponse(
            request=request,
            name="admin_social.html",
            context={"user": u, "admin_path": main.ADMIN_CENTER_PATH},
        )

    @app.on_event("startup")
    async def start_social_maintenance():
        from app.expert_social_maintenance import embedded

        app.state.social_maintenance = asyncio.create_task(
            embedded(lambda: main.engine)
        )

    @app.on_event("shutdown")
    async def stop_social_maintenance():
        task = getattr(app.state, "social_maintenance", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    from app.expert_social_relationships import register_relationships
    register_relationships(r, main, actor=actor, expert=expert, post_rows=post_rows, headers=HEADERS)
    app.include_router(r)
    from app.expert_social_review_notifications import ReviewNoticeMiddleware
    app.add_middleware(ReviewNoticeMiddleware, main=main)
    app.add_middleware(SocialBodyLimitMiddleware)
