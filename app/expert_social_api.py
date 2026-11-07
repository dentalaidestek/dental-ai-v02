"""Member-only social extension. Existing consultation routes remain unchanged."""

from __future__ import annotations
import asyncio
import hashlib
import json
import os
import re
import uuid
import threading
from datetime import timedelta
from pathlib import Path
from typing import Optional, Literal
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, ConfigDict, Field as Input
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool
from app import (
    expert_social_safety as safety,
    expert_publications as bibliography,
    object_storage,
)
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
    now,
)
from app.auth_rate import admit

HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    "Vary": "Cookie",
}
NETWORK_SLOTS = asyncio.Semaphore(3)
IMAGE_SLOT = threading.BoundedSemaphore(1)


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


class LikeBody(Body):
    liked: bool


class ReportBody(Body):
    target_type: Literal["POST", "COMMENT"]
    target_id: int = Input(ge=1)
    reason: Literal["PRIVACY", "ABUSE", "SPAM", "MISLEADING", "OTHER"]


class ReviewBody(Body):
    status: Literal["PUBLISHED", "REJECTED"]
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
        messages = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > limit:
                return await JSONResponse(
                    {"detail": "İstek boyut sınırını aşıyor."},
                    status_code=413,
                    headers=HEADERS,
                )(scope, receive, send)
            messages.append(message)
            if not message.get("more_body"):
                break

        async def replay():
            return messages.pop(0) if messages else await receive()

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
        return u

    def admin(request):
        actor(request)
        user = main._admin_only(request)
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
        is_admin = bool(user.role == "ADMIN" and main._admin_only(request))
        if user.id != p.author_id and not is_admin:
            if p.status != "PUBLISHED":
                raise HTTPException(404, "Gönderi bulunamadı.")
            expert(s, p.author_id)
        return p

    def decision(s, kind, row, actor_id=None, reason=None):
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

    def post_rows(s, rows, user):
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
        result = []
        for p in rows:
            u = users[p.author_id]
            profile = profiles.get(p.author_id)
            title = (
                profile.academic_title
                if profile and profile.academic_title_verified
                else "Uzman Diş Hekimi"
            )
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
                author_name=main._professional_display_name(title, u.display_name),
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
            result.append(data)
        return result

    def comment_rows(s, rows, user):
        if not rows:
            return []
        users = {
            u.id: u
            for u in s.exec(
                select(main.User).where(main.User.id.in_({c.author_id for c in rows}))
            ).all()
        }
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
                "author_name": users[c.author_id].display_name,
                "owned": c.author_id == user.id,
                "created_at": c.created_at.isoformat() + "Z",
            }
            for c in rows
        ]

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
        with Session(main.engine, expire_on_commit=False) as s:
            try:
                expert(s, user.id, write=True)
                m = SocialMedia(owner_id=user.id, reference=reference)
                s.add(m)
                s.commit()
            except Exception:
                # On transaction failures, never retain an untracked object.
                object_storage.delete(reference)
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
                is_admin = bool(u.role == "ADMIN" and main._admin_only(request))
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
        with Session(main.engine, expire_on_commit=False) as s:
            expert(s, u.id, write=True, lock=True)
            previous = s.exec(
                select(SocialPost).where(
                    SocialPost.author_id == u.id,
                    SocialPost.idempotency_key == str(body.idempotency_key),
                )
            ).first()
            if previous:
                if previous.request_hash != request_hash:
                    raise HTTPException(
                        409, "Bu paylaşım isteği farklı içerikle kullanıldı."
                    )
                if previous.status == "DELETED":
                    raise HTTPException(
                        409, "Gönderi silinmiş. Yeni bir paylaşım oluşturun."
                    )
                return post_rows(s, [previous], u)[0]
            throttle(u, "post", 10, 600)
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
            status, reasons = safety.moderate(
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
                decision(s, "POST", p)
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
                p.status, reasons = safety.moderate(
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
            decision(s, "POST", p, u.id)
            s.commit()
            return post_rows(s, [p], u)[0]

    @r.delete("/posts/{ident}")
    def delete_post(request: Request, ident: int):
        u = actor(request)
        with Session(main.engine) as s:
            p = load_post(s, ident, u, request, lock=True)
            if p.author_id != u.id and not main._admin_only(request):
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
    ):
        u = actor(request)
        with Session(main.engine) as s:
            p = load_post(s, ident, u, request)
            stmt = select(SocialComment).where(
                SocialComment.post_id == ident,
                SocialComment.id > after,
                SocialComment.status != "DELETED",
            )
            # Pending comments are visible only to their writer and MFA administrators.
            if not (u.role == "ADMIN" and main._admin_only(request)):
                stmt = stmt.where(
                    or_(
                        SocialComment.status == "PUBLISHED",
                        SocialComment.author_id == u.id,
                    )
                )
            rows = list(s.exec(stmt.order_by(SocialComment.id).limit(limit + 1)).all())
            more = len(rows) > limit
            rows = rows[:limit]
            return JSONResponse(
                {
                    "items": comment_rows(s, rows, u),
                    "next_cursor": rows[-1].id if more else None,
                },
                headers=HEADERS,
            )

    @r.post("/posts/{ident}/comments")
    def create_comment(request: Request, ident: int, body: CommentBody):
        u = actor(request)
        with Session(main.engine, expire_on_commit=False) as s:
            p = load_post(s, ident, u, request, lock=True)
            if p.status != "PUBLISHED" or p.comments_closed:
                raise HTTPException(409, "Bu gönderide yorumlar kapalı.")
            old = s.exec(
                select(SocialComment).where(
                    SocialComment.author_id == u.id,
                    SocialComment.idempotency_key == str(body.idempotency_key),
                )
            ).first()
            value = body.text.strip()
            if not value:
                raise HTTPException(400, "Yorum boş olamaz.")
            if old:
                if (
                    old.post_id != ident
                    or old.text != value
                    or old.parent_id != body.parent_id
                    or old.status == "DELETED"
                ):
                    raise HTTPException(409, "Yorum isteği değişmiş.")
                return comment_rows(s, [old], u)[0]
            throttle(u, "comment", 12)
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
            if s.exec(
                select(SocialComment.id).where(
                    SocialComment.author_id == u.id,
                    SocialComment.text == value,
                    SocialComment.created_at > now() - timedelta(minutes=2),
                )
            ).first():
                raise HTTPException(429, "Aynı yorumu kısa süre önce gönderdiniz.")
            status, reasons = safety.moderate(value)
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
                decision(s, "COMMENT", c)
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                raise HTTPException(409, "Bu yorum isteği zaten kullanıldı.") from exc
            return comment_rows(s, [c], u)[0]

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
            c.status, reasons = safety.moderate(c.text)
            c.reasons_json = json.dumps(reasons)
            c.version += 1
            c.updated_at = now()
            s.add(c)
            decision(s, "COMMENT", c, u.id)
            s.commit()
            return comment_rows(s, [c], u)[0]

    @r.delete("/comments/{ident}")
    def delete_comment(request: Request, ident: int):
        u = actor(request)
        with Session(main.engine) as s:
            c = s.exec(
                select(SocialComment).where(SocialComment.id == ident).with_for_update()
            ).first()
            if not c or c.status == "DELETED":
                raise HTTPException(404, "Yorum bulunamadı.")
            p = load_post(s, c.post_id, u, request)
            if u.id not in (c.author_id, p.author_id) and not main._admin_only(request):
                raise HTTPException(403, "Bu yorumu yönetemezsiniz.")
            c.status = "DELETED"
            c.text = ""
            c.version += 1
            s.add(c)
            decision(s, "COMMENT", c, u.id, "COMMENT_REMOVED")
            s.commit()
        return {"ok": True}

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
        values["status"], reasons = safety.moderate(
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

    def publication_row(row):
        return row.model_dump(
            exclude={"fingerprint", "title_key", "expert_id", "deleted", "reasons_json"}
        )

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
            if before:
                stmt = stmt.where(Publication.id < before)
            rows = list(
                s.exec(stmt.order_by(Publication.id.desc()).limit(limit + 1)).all()
            )
            more = len(rows) > limit
            rows = rows[:limit]
            sync = s.get(OrcidSync, expert_id) if u.id == expert_id else None
            return JSONResponse(
                {
                    "items": [
                        json.loads(
                            p.model_dump_json(
                                exclude={
                                    "fingerprint",
                                    "title_key",
                                    "expert_id",
                                    "deleted",
                                    "reasons_json",
                                }
                            )
                        )
                        for p in rows
                    ],
                    "next_cursor": rows[-1].id if more else None,
                    "sync": json.loads(sync.model_dump_json()) if sync else None,
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
                decision(s, "PUBLICATION", row, u.id)
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                raise HTTPException(409, "Bu DOI veya yayın zaten kayıtlı.") from exc
            return publication_row(row)

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
                decision(s, "PUBLICATION", row, u.id)
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                raise HTTPException(409, "Bu DOI veya yayın zaten kayıtlı.") from exc
            return publication_row(row)

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
            decision(s, "PUBLICATION", row, u.id, "PUBLICATION_REMOVED")
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
        except Exception:

            def fail():
                with Session(main.engine) as s:
                    sync = s.get(OrcidSync, u.id)
                    sync.status = "FAILED"
                    sync.error_code = "ORCID_UNAVAILABLE"
                    s.add(sync)
                    s.commit()

            await run_in_threadpool(fail)
            return JSONResponse(
                {
                    "ok": False,
                    "message": "ORCID yayınları alınamadı. Manuel yayın ekleyebilirsiniz.",
                },
                status_code=200,
                headers=HEADERS,
            )

        def finish():
            with Session(main.engine) as s:
                profile = expert(s, u.id, lock=True, write=True)
                existing = s.exec(
                    select(Publication).where(Publication.expert_id == u.id)
                ).all()
                fingerprints = {x.fingerprint for x in existing}
                doi_set = {x.doi for x in existing if x.doi}
                titles = {x.title_key for x in existing}
                source_keys = {(x.source_orcid, x.source_key) for x in existing}
                count = 0
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
                    status, reasons = safety.moderate(
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
                    s.flush()
                    decision(s, "PUBLICATION", publication)
                    fingerprints.add(key)
                    titles.add(title_key)
                    source_keys.add((orcid, values["source_key"]))
                    if values["doi"]:
                        doi_set.add(values["doi"])
                    count += 1
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

    @r.get("/moderation")
    def queue(
        request: Request,
        before: Optional[int] = Query(default=None, ge=1),
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
            stmt = select(model).where(model.status == status)
            if before:
                stmt = stmt.where(model.id < before)
            rows = list(s.exec(stmt.order_by(model.id.desc()).limit(31)).all())
            more = len(rows) > 30
            rows = rows[:30]
            data = (
                post_rows(s, rows, u)
                if kind == "POST"
                else (
                    comment_rows(s, rows, u)
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
            return JSONResponse(
                {"items": data, "next_cursor": rows[-1].id if more else None},
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
            if not row:
                raise HTTPException(404, "İçerik bulunamadı.")
            item = (
                post_rows(s, [row], u)[0]
                if kind == "POST"
                else (
                    comment_rows(s, [row], u)[0]
                    if kind == "COMMENT"
                    else publication_row(row)
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
            return {"item": item, "history": [h.model_dump() for h in history]}

    @r.post("/moderation/{kind}/{ident}")
    def review(
        request: Request,
        kind: Literal["POST", "COMMENT", "PUBLICATION"],
        ident: int,
        body: ReviewBody,
    ):
        u = admin(request)
        with Session(main.engine) as s:
            model = (
                SocialPost
                if kind == "POST"
                else (SocialComment if kind == "COMMENT" else Publication)
            )
            row = s.exec(
                select(model).where(model.id == ident).with_for_update()
            ).first()
            if not row or row.status == "DELETED":
                raise HTTPException(404, "İçerik bulunamadı.")
            assert_version(row, body.version)
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
            decision(s, kind, row, u.id, body.reason)
            for report in s.exec(
                select(SocialReport).where(
                    SocialReport.target_type == kind,
                    SocialReport.target_id == ident,
                    SocialReport.resolved_at == None,
                )
            ).all():
                report.resolved_at = now()
                s.add(report)
            s.commit()
        return {"ok": True}

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

    app.include_router(r)
    app.add_middleware(SocialBodyLimitMiddleware)
