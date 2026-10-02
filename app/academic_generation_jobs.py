"""Durable jobs for broad Academic AI generation."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets
from sqlalchemy import text
from sqlmodel import Field, Session, SQLModel

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class AcademicGenerationJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True)
    course_id: int = Field(index=True)
    request_key: str = Field(index=True)
    request_json: str
    status: str = Field(default="QUEUED", index=True)
    generated_count: int = 0
    target_count: int = 0
    lease_token: Optional[str] = Field(default=None, index=True)
    lease_until: Optional[datetime] = Field(default=None, index=True)
    worker_id: Optional[str] = Field(default=None, index=True)
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=_now, index=True)
    updated_at: datetime = Field(default_factory=_now, index=True)
    completed_at: Optional[datetime] = None

def claim_generation_job(session: Session, worker_id: str, lease_seconds: int = 90):
    """Claim one job with SKIP LOCKED; web requests never execute broad generation."""
    if session.get_bind().dialect.name != "postgresql":
        return None
    now = _now()
    row = session.exec(text("""
        SELECT id FROM academicgenerationjob
        WHERE status='QUEUED' OR (
          status='RUNNING' AND lease_until IS NOT NULL AND lease_until < :now
        )
        ORDER BY created_at, id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    """), params={"now": now}).first()
    if not row:
        return None
    token = secrets.token_urlsafe(24)
    until = now + timedelta(seconds=max(30, min(int(lease_seconds), 300)))
    session.exec(text("""
        UPDATE academicgenerationjob
        SET status='RUNNING', lease_token=:token, lease_until=:until,
            worker_id=:worker, updated_at=:now
        WHERE id=:id
    """), params={"token": token, "until": until, "worker": worker_id, "now": now, "id": int(row[0])})
    session.commit()
    return session.get(AcademicGenerationJob, int(row[0]))


def enqueue_generation_job(
    session: Session, *, owner_user_id: int, course_id: int,
    request_key: str, request_json: str, target_count: int,
) -> AcademicGenerationJob:
    # Serialize enqueue for one user/course so double taps cannot create a
    # provider-call burst. PostgreSQL advisory lock is transaction scoped.
    if session.get_bind().dialect.name == "postgresql":
        session.exec(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), params={
            "k1": int(owner_user_id) & 2147483647,
            "k2": int(course_id) & 2147483647,
        })
    existing = session.exec(text("""
        SELECT id FROM academicgenerationjob
        WHERE owner_user_id=:owner AND course_id=:course
          AND status IN ('QUEUED','RUNNING')
        ORDER BY id DESC LIMIT 1
    """), params={"owner": owner_user_id, "course": course_id}).first()
    if existing:
        return session.get(AcademicGenerationJob, int(existing[0]))
    job = AcademicGenerationJob(
        owner_user_id=owner_user_id, course_id=course_id,
        request_key=request_key, request_json=request_json,
        target_count=max(1, min(int(target_count), 200)),
    )
    session.add(job)
    session.flush()
    return job

def checkpoint_generation_job(
    session: Session, *, job_id: int, lease_token: str,
    generated_count: int, done: bool = False,
) -> bool:
    now = _now()
    result = session.exec(text("""
        UPDATE academicgenerationjob
        SET generated_count=GREATEST(generated_count, :count),
            status=CASE WHEN :done THEN 'DONE' ELSE 'QUEUED' END,
            lease_token=NULL, lease_until=NULL, worker_id=NULL,
            completed_at=CASE WHEN :done THEN :now ELSE completed_at END,
            updated_at=:now
        WHERE id=:id AND status='RUNNING' AND lease_token=:token
        RETURNING id
    """), params={
        "count": max(0, int(generated_count)), "done": bool(done),
        "now": now, "id": job_id, "token": lease_token,
    }).first()
    session.commit()
    return bool(result)
