"""Owner-scoped follow lists and a bounded feed of followed experts.

Registration reuses the social API's request authorization and batched post
serializer. No relationship graph or response is retained between requests.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import and_, func, or_
from sqlmodel import Session, select

from app.expert_social_identity import expert_display_name
from app.expert_social_models import SocialFollow, SocialPost


def _verified_expert_conditions(main):
    """The read eligibility used by expert_social_api.expert, expressed in SQL."""
    user, profile = main.User, main.ExpertProfile
    return (
        user.is_active == True,
        user.role.in_(("DOCTOR", "ADMIN")),
        profile.application_status == "APPROVED",
        profile.verification_status == "VERIFIED",
        profile.specialty_verified == True,
        profile.credential_document_path != None,
        profile.credential_document_path != "",
        profile.phone != None,
        profile.phone != "",
    )


def unblocked_relationship_condition(main, viewer_id, counterpart_column):
    """Exclude either direction of the application's existing user block."""
    block = main.UserBlock
    return ~select(block.id).where(
        or_(
            and_(
                block.blocker_user_id == viewer_id,
                block.blocked_user_id == counterpart_column,
            ),
            and_(
                block.blocked_user_id == viewer_id,
                block.blocker_user_id == counterpart_column,
            ),
        )
    ).exists()


def _relationship_query(main, owner_id, kind, columns):
    """Keep the public totals and owner-only pages on the same visible scope."""
    user, profile = main.User, main.ExpertProfile
    if kind == "followers":
        counterpart = SocialFollow.follower_id
        owner_condition = SocialFollow.expert_id == owner_id
    else:
        counterpart = SocialFollow.expert_id
        owner_condition = SocialFollow.follower_id == owner_id
    statement = (
        select(*columns)
        .select_from(user)
        .join(SocialFollow, counterpart == user.id)
        .outerjoin(profile, profile.user_id == user.id)
        .where(
            owner_condition,
            user.is_active == True,
            unblocked_relationship_condition(main, owner_id, user.id),
        )
    )
    if kind == "following":
        statement = statement.where(*_verified_expert_conditions(main))
    return statement


def relationship_counts(session, main, owner_id):
    """Count exactly the members visible in the subject owner's two lists.

    Callers authorize access to the profile before requesting its public totals.
    The subject's blocks determine these totals, regardless of who views them.
    """
    return {
        kind: int(
            session.exec(
                _relationship_query(main, owner_id, kind, (func.count(),))
            ).one()
            or 0
        )
        for kind in ("followers", "following")
    }


def register_relationships(
    router: APIRouter, main, *, actor, expert, post_rows, headers
):
    """Attach routes before the existing social router is included in the app.

    ``actor(request)``, ``expert(session, id)`` and
    ``post_rows(session, posts, viewer)`` are the existing request-local helpers.
    The router must already carry the ``/api/expert-social`` prefix.
    """
    user_model, profile_model = main.User, main.ExpertProfile

    # The API can be registered on isolated apps in tests. The member page
    # belongs to the main application and is mounted once on that application.
    if not any(
        getattr(route, "path", None) == "/expert-support/following"
        for route in main.app.routes
    ):

        @main.app.get("/expert-support/following", response_class=HTMLResponse)
        def expert_social_following_page(request: Request):
            viewer = actor(request)
            return main.templates.TemplateResponse(
                request=request,
                name="expert_following.html",
                context={"user": viewer, "title": "Takip ettiklerim"},
                headers=headers,
            )

    def relationship_list(request, owner_id, kind, before, limit):
        viewer = actor(request)
        if viewer.id != owner_id:
            raise HTTPException(403, "Takip listesini yalnızca hesap sahibi görebilir.")
        with Session(main.engine) as session:
            if kind == "followers":
                expert(session, owner_id)
            # Every active member can follow experts, including members
            # who do not have an expert profile of their own.
            eligibility = and_(*_verified_expert_conditions(main))
            statement = _relationship_query(
                main,
                owner_id,
                kind,
                (
                    user_model,
                    profile_model,
                    SocialFollow.created_at,
                    eligibility.label("is_expert"),
                ),
            )
            if before is not None:
                statement = statement.where(user_model.id < before)
            rows = list(
                session.exec(
                    statement.order_by(user_model.id.desc()).limit(limit + 1)
                ).all()
            )
            has_more = len(rows) > limit
            rows = rows[:limit]
            ids = [member.id for member, *_ in rows]
            # The reverse edge is needed for follow controls on the owner's
            # follower list. Load it once for the entire bounded page.
            followed_ids = (
                set(
                    session.exec(
                        select(SocialFollow.expert_id).where(
                            SocialFollow.follower_id == viewer.id,
                            SocialFollow.expert_id.in_(ids),
                        )
                    ).all()
                )
                if ids
                else set()
            )
            items = []
            for member, profile, followed_at, is_expert in rows:
                is_expert = bool(is_expert)
                name = member.display_name
                if is_expert:
                    name = expert_display_name(profile, name)
                items.append(
                    {
                        "user_id": member.id,
                        "name": name,
                        "photo": main._profile_photo_url(member),
                        "is_expert": is_expert,
                        "specialty": profile.specialty if is_expert else None,
                        "profile_url": (
                            f"/expert-support/expert/{member.id}"
                            if is_expert
                            else None
                        ),
                        "following_by_viewer": member.id in followed_ids,
                        "followed_at": followed_at.isoformat() + "Z",
                    }
                )
            return JSONResponse(
                {
                    "items": items,
                    "next_cursor": rows[-1][0].id if has_more else None,
                },
                headers=headers,
            )

    @router.get("/experts/{expert_id}/followers")
    def followers(
        request: Request,
        expert_id: int,
        before: Optional[int] = Query(default=None, ge=1),
        limit: int = Query(default=15, ge=1, le=30),
    ):
        return relationship_list(request, expert_id, "followers", before, limit)

    @router.get("/experts/{expert_id}/following")
    def following(
        request: Request,
        expert_id: int,
        before: Optional[int] = Query(default=None, ge=1),
        limit: int = Query(default=15, ge=1, le=30),
    ):
        return relationship_list(request, expert_id, "following", before, limit)

    @router.get("/feed/following")
    def followed_experts_feed(
        request: Request,
        before: Optional[int] = Query(default=None, ge=1),
        limit: int = Query(default=15, ge=1, le=30),
    ):
        viewer = actor(request)
        with Session(main.engine) as session:
            statement = (
                select(SocialPost)
                .join(SocialFollow, SocialFollow.expert_id == SocialPost.author_id)
                .join(user_model, user_model.id == SocialPost.author_id)
                .join(profile_model, profile_model.user_id == SocialPost.author_id)
                .where(
                    SocialFollow.follower_id == viewer.id,
                    SocialPost.status == "PUBLISHED",
                    *_verified_expert_conditions(main),
                    unblocked_relationship_condition(
                        main, viewer.id, SocialPost.author_id
                    ),
                )
            )
            if before is not None:
                statement = statement.where(SocialPost.id < before)
            rows = list(
                session.exec(
                    statement.order_by(SocialPost.id.desc()).limit(limit + 1)
                ).all()
            )
            has_more = len(rows) > limit
            rows = rows[:limit]
            return JSONResponse(
                {
                    "items": post_rows(session, rows, viewer),
                    "next_cursor": rows[-1].id if has_more else None,
                },
                headers=headers,
            )
