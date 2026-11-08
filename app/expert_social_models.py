"""Independent additive social tables; identifiers always refer to existing accounts."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint, CheckConstraint, Index, text
from app.expert_consultation_requests import ConsultationRequestReceipt


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SocialPost(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("author_id", "idempotency_key"),
        CheckConstraint("status IN ('PUBLISHED','PENDING','REJECTED','DELETED')"),
        Index("ix_socialpost_feed", "author_id", "status", "id"),
        Index("ix_socialpost_moderation", "status", "id"),
        Index("ix_socialpost_waiting", "status", "created_at", "id"),
        Index(
            "uq_socialpost_pin",
            "author_id",
            unique=True,
            postgresql_where=text("pinned = true AND status != 'DELETED'"),
            sqlite_where=text("pinned = 1 AND status != 'DELETED'"),
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    author_id: int = Field(foreign_key="user.id", ondelete="CASCADE")
    text: str
    status: str = "PENDING"
    reasons_json: str = "[]"
    link_url: Optional[str] = None
    preview_json: Optional[str] = None
    cover_media_id: Optional[int] = None
    pinned: bool = False
    comments_closed: bool = False
    idempotency_key: str
    request_hash: str
    version: int = 1
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class SocialMedia(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    post_id: Optional[int] = Field(
        default=None, foreign_key="socialpost.id", ondelete="CASCADE", index=True
    )
    reference: str
    position: int = 0
    created_at: datetime = Field(default_factory=now, index=True)


class SocialPreview(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    url: str
    metadata_json: str
    cover_media_id: Optional[int] = Field(
        default=None, foreign_key="socialmedia.id", ondelete="SET NULL"
    )
    created_at: datetime = Field(default_factory=now, index=True)


class SocialComment(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("author_id", "idempotency_key"),
        CheckConstraint("status IN ('PUBLISHED','PENDING','REJECTED','DELETED')"),
        Index("ix_socialcomment_thread", "post_id", "id"),
        Index("ix_socialcomment_moderation", "status", "id"),
        Index("ix_socialcomment_waiting", "status", "created_at", "id"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="socialpost.id", ondelete="CASCADE")
    author_id: int = Field(foreign_key="user.id", ondelete="CASCADE")
    parent_id: Optional[int] = Field(
        default=None, foreign_key="socialcomment.id", ondelete="CASCADE"
    )
    text: str
    status: str = "PENDING"
    reasons_json: str = "[]"
    idempotency_key: str
    version: int = 1
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class SocialLike(SQLModel, table=True):
    post_id: int = Field(
        primary_key=True, foreign_key="socialpost.id", ondelete="CASCADE"
    )
    user_id: int = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")


class SocialReport(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("reporter_id", "target_type", "target_id"),
        CheckConstraint("target_type IN ('POST','COMMENT')"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    reporter_id: int = Field(foreign_key="user.id", ondelete="CASCADE")
    target_type: str = Field(index=True)
    target_id: int = Field(index=True)
    reason: str
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now)


class SocialDecision(SQLModel, table=True):
    """Append-only through the API. No raw text, media, or health data in audit."""

    id: Optional[int] = Field(default=None, primary_key=True)
    target_type: str = Field(index=True)
    target_id: int = Field(index=True)
    actor_id: Optional[int] = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )
    status: str
    version: int
    reason: str
    created_at: datetime = Field(default_factory=now)


class Publication(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("expert_id", "fingerprint"),
        UniqueConstraint("expert_id", "doi"),
        UniqueConstraint("expert_id", "title_key"),
        UniqueConstraint("expert_id", "source_orcid", "source_key"),
        Index("ix_publication_profile", "expert_id", "deleted", "year", "id"),
        Index("ix_publication_moderation", "status", "id"),
        Index("ix_publication_waiting", "status", "created_at", "id"),
        CheckConstraint("source IN ('MANUAL','ORCID','DOI_MATCH')"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    expert_id: int = Field(foreign_key="user.id", ondelete="CASCADE")
    title: str
    authors: str = ""
    year: Optional[int] = None
    journal: str = ""
    doi: Optional[str] = None
    url: Optional[str] = None
    description: str = ""
    source: str = "MANUAL"
    source_key: Optional[str] = None
    source_orcid: Optional[str] = None
    fingerprint: str
    title_key: str
    status: str = "PENDING"
    reasons_json: str = "[]"
    version: int = 1
    deleted: bool = False
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class OrcidSync(SQLModel, table=True):
    expert_id: int = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    orcid: str
    status: str = "IDLE"
    imported_count: int = 0
    last_attempt_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    error_code: Optional[str] = None


class DoiMatch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    metadata_json: str
    created_at: datetime = Field(default_factory=now, index=True)


SOCIAL_MODELS = (
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
)


class SocialMediaDeletion(SQLModel, table=True):
    reference: str = Field(primary_key=True)
    attempts: int = 0
    next_attempt_at: datetime = Field(default_factory=now, index=True)
    created_at: datetime = Field(default_factory=now)


SOCIAL_MODELS = (*SOCIAL_MODELS, SocialMediaDeletion)


class SocialFollow(SQLModel, table=True):
    follower_id: int = Field(
        primary_key=True, foreign_key="user.id", ondelete="CASCADE"
    )
    expert_id: int = Field(
        primary_key=True, foreign_key="user.id", ondelete="CASCADE", index=True
    )
    created_at: datetime = Field(default_factory=now)


SOCIAL_MODELS = (*SOCIAL_MODELS, SocialFollow)


class SocialModerationTask(SQLModel, table=True):
    """One durable lifecycle per target; no text, image, or provider payloads."""

    __table_args__ = (
        UniqueConstraint("target_type", "target_id"),
        UniqueConstraint("job_id"),
        CheckConstraint("target_type IN ('POST','COMMENT','PUBLICATION')"),
        CheckConstraint("state IN ('AUTO_DONE','HUMAN_DONE','WAITING_HUMAN','WAITING_OWNER','FAILED','RUNNING')"),
        CheckConstraint("attempts >= 0 AND revision >= 1 AND content_version >= 1"),
        Index("ix_socialmoderationtask_waiting", "state", "waiting_since", "id"),
        Index("ix_socialmoderationtask_retry", "state", "next_attempt_at", "id"),
        Index("ix_socialmoderationtask_lease", "state", "lease_until", "id"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    target_type: str
    target_id: int
    owner_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    content_version: int
    revision: int = 1
    state: str
    wait_type: str = "NONE"
    reasons_json: str = "[]"
    last_decision_status: str
    last_decision_reason: str = ""
    last_decision_source: str = "AUTOMATIC"
    last_decision_at: datetime = Field(default_factory=now)
    attempts: int = 0
    next_attempt_at: Optional[datetime] = None
    lease_token: Optional[str] = None
    lease_until: Optional[datetime] = None
    last_error_code: Optional[str] = None
    waiting_since: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class SocialModerationEvent(SQLModel, table=True):
    """Append-only operational history, including recoverable local failures."""

    __table_args__ = (
        UniqueConstraint("job_id", "revision"),
        Index("ix_socialmoderationevent_target", "target_type", "target_id", "id"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str
    target_type: str
    target_id: int
    revision: int
    content_version: int
    state: str
    status: str
    source: str
    reason: str
    actor_id: Optional[int] = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    created_at: datetime = Field(default_factory=now)


SOCIAL_MODELS = (
    *SOCIAL_MODELS, SocialModerationTask, SocialModerationEvent,
    ConsultationRequestReceipt,
)
