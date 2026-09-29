"""Durable, bounded application work. PostgreSQL is the production queue.

Payloads contain identifiers and object references, not images or prompts.
Result publication is fenced by a lease and the current source fingerprint.
"""
from __future__ import annotations
import hashlib
import json
import os
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from sqlalchemy import Index, text, func, update, or_, and_
from sqlalchemy.orm import aliased
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, select


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WorkJob(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int = Field(index=True, foreign_key="user.id", ondelete="CASCADE")
    resource_id: int = Field(index=True)
    resource_type: str = Field(index=True)
    kind: str = Field(index=True)
    source_hash: str
    dedupe_key: str = Field(unique=True)
    payload_json: str = "{}"
    result_ref: str | None = None
    status: str = Field(default="QUEUED", index=True)
    attempts: int = 0
    available_at: datetime = Field(default_factory=now, index=True)
    lease_token: str | None = None
    lease_until: datetime | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    error_code: str | None = None
    __table_args__ = (
        Index("ix_workjob_claim", "status", "available_at", "created_at", "id"),
        Index("ix_workjob_resource_history", "resource_type", "resource_id", "id"),
        Index("ix_workjob_owner_pending", "owner_user_id", "status"),
        Index("uq_workjob_running_resource", "resource_type", "resource_id", unique=True,
              postgresql_where=text("status='RUNNING'"), sqlite_where=text("status='RUNNING'")),
    )


class WorkCancelled(RuntimeError):
    pass


class WorkCapacity(RuntimeError):
    pass


current_job: ContextVar[WorkJob | None] = ContextVar("dental_work_job", default=None)


@lru_cache(maxsize=1)
def _code_version():
    base = Path(__file__).parent
    paths = [base / name for name in ("ai_engine.py", "main.py", "vision_llm_context.py", "study_rag.py", "clinical_rag_router.py")]
    paths.extend(sorted((base.parent / "dental_rag").rglob("*.txt")))
    paths.extend(sorted((base.parent / "dental_rag").rglob("*.py")))
    return hashlib.sha256(b"".join(path.read_bytes() for path in paths)).hexdigest()


def source_identity(session: Session, kind: str, resource_type: str, resource_id: int, *, lock=False):
    # Lazy import avoids registering a second application/model graph in workers.
    from app import main as m
    def one(model, ident):
        stmt = select(model).where(model.id == ident)
        if lock:
            stmt = stmt.with_for_update()
        return session.exec(stmt.execution_options(populate_existing=True)).first()
    def dump(row, exclude=()):
        return row.model_dump(mode="json", exclude=set(exclude)) if row else None
    if resource_type == "COURSE":
        resource = one(m.StudyCourse, resource_id)
        if resource is None:
            raise WorkCancelled("RESOURCE_DELETED")
        owner = resource.owner_user_id
        materials = session.exec(select(m.StudyMaterial).where(
            m.StudyMaterial.course_id == resource_id, m.StudyMaterial.owner_user_id == owner,
            m.StudyMaterial.deleted_at == None).order_by(m.StudyMaterial.id)).all()
        content = [(x.id, x.file_path, x.size_bytes, x.mime_type) for x in materials]
    else:
        guest = resource_type == "GUEST"
        resource = one(m.GuestAnalysis if guest else m.Analysis, resource_id)
        if resource is None:
            raise WorkCancelled("RESOURCE_DELETED")
        patient = None if guest else one(m.Patient, resource.patient_id)
        if not guest and patient is None:
            raise WorkCancelled("PATIENT_DELETED")
        owner = resource.owner_user_id if guest else patient.owner_user_id
        model = m.GuestImageAsset if guest else m.ImageAsset
        condition = model.guest_analysis_id == resource_id if guest else model.analysis_id == resource_id
        assets_stmt = select(model).where(condition).order_by(model.id)
        if lock:
            assets_stmt = assets_stmt.with_for_update()
        assets = session.exec(assets_stmt.execution_options(populate_existing=True)).all()
        content = {"assets": [dump(x, {"vision_snapshot_json"}) for x in assets]}
        if kind != "VISION":
            content["analysis"] = dump(resource, {"status", "result_path"})
            content["patient"] = dump(patient)
            if patient:
                for table in (m.ToothStatus, m.ToothSurfaceStatus, m.Treatment):
                    stmt = select(table).where(table.patient_id == patient.id).order_by(table.id)
                    if lock:
                        stmt = stmt.with_for_update()
                    content[table.__name__] = [dump(x) for x in session.exec(stmt).all()]
    user = one(m.User, owner)
    if user is None or not user.is_active:
        raise WorkCancelled("OWNER_UNAVAILABLE")
    profile = {key: value for key, value in os.environ.items() if key in {
        "DENTAL_INFERENCE_REVISION", "GEMINI_MODEL", "DENTAL_CLINICAL_AI_MODEL", "STUDY_EMBEDDING_PROVIDER",
        "STUDY_EMBEDDING_MODEL", "STUDY_EMBEDDING_DIMENSIONS", "DENTAL_VISION_MODAL_URL",
        "BITEWING_ENSEMBLE_URL", "PERIAPICAL_INFERENCE_URL", "INTRAORAL_ENSEMBLE_URL"}}
    digest = hashlib.sha256(json.dumps([content, profile, _code_version()], sort_keys=True,
                                       ensure_ascii=False, default=str).encode()).hexdigest()
    return resource, owner, digest


def enqueue(session, *, kind, resource_type, resource_id, payload=None):
    if kind not in {"VISION", "PRELIMINARY", "FINAL", "LEGACY_INDEX"}:
        raise ValueError("Unsupported job kind")
    payload_json = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False)
    if len(payload_json.encode()) > 16384:
        raise WorkCapacity("Job input exceeds 16 KiB")
    input_digest = hashlib.sha256(payload_json.encode()).hexdigest()
    # One short admission lock makes the global backlog bound exact on PG.
    if session.get_bind().dialect.name == "postgresql":
        session.exec(text("SELECT pg_advisory_xact_lock(71048231)"))
    resource, owner, digest = source_identity(session, kind, resource_type, resource_id, lock=True)
    key = hashlib.sha256(f"{owner}:{resource_type}:{resource_id}:{kind}:{digest}:{input_digest}".encode()).hexdigest()
    existing = session.exec(select(WorkJob).where(WorkJob.dedupe_key == key)).first()
    if existing:
        return existing
    # Lock the owner row so simultaneous submissions cannot bypass its quota.
    from app.main import User
    session.exec(select(User).where(User.id == owner).with_for_update()).first()
    count = session.exec(select(WorkJob.id).where(
        WorkJob.owner_user_id == owner, WorkJob.status.in_(["QUEUED", "RUNNING"])).limit(33)).all()
    if len(count) >= 32:
        raise WorkCapacity("Too many pending jobs; retry when current work completes")
    total = session.exec(select(func.count()).select_from(WorkJob).where(WorkJob.status.in_(["QUEUED", "RUNNING"]))).one()
    if total >= int(os.getenv("DENTAL_MAX_PENDING_JOBS", "1000")):
        raise WorkCapacity("The processing queue is full; retry later")
    job = WorkJob(owner_user_id=owner, resource_id=resource_id, resource_type=resource_type,
                  kind=kind, source_hash=digest, dedupe_key=key, payload_json=payload_json)
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError:
        job = session.exec(select(WorkJob).where(WorkJob.dedupe_key == key)).one()
    return job


def claim(engine, *, lease_seconds=180):
    stamp = now()
    try:
        with Session(engine, expire_on_commit=False) as s:
            # Recovery never leaves a dead consumer's RUNNING resource pinned.
            s.exec(text("""UPDATE workjob SET status=CASE WHEN attempts>=3 THEN 'FAILED' ELSE 'QUEUED' END,
                lease_token=NULL, lease_until=NULL, error_code='LEASE_EXPIRED'
                WHERE status='RUNNING' AND lease_until <= :stamp"""), params={"stamp": stamp})
            running = aliased(WorkJob)
            occupied = select(running.id).where(running.status == "RUNNING",
                running.resource_type == WorkJob.resource_type,
                running.resource_id == WorkJob.resource_id).exists()
            stmt = select(WorkJob).where(WorkJob.status == "QUEUED", WorkJob.available_at <= stamp,
                                         ~occupied).order_by(WorkJob.created_at, WorkJob.id).limit(1)
            if engine.dialect.name == "postgresql":
                stmt = stmt.with_for_update(skip_locked=True)
            job = s.exec(stmt).first()
            if job is None:
                s.commit()
                return None
            token = secrets.token_hex(24)
            changed = s.exec(update(WorkJob).where(WorkJob.id == job.id,
                WorkJob.status == "QUEUED", WorkJob.attempts == job.attempts).values(
                status="RUNNING", attempts=WorkJob.attempts + 1, lease_token=token,
                lease_until=stamp + timedelta(seconds=lease_seconds), updated_at=stamp))
            if changed.rowcount != 1:
                s.rollback()
                return None
            s.commit()
            s.refresh(job)
            return job
    except IntegrityError:
        # Another job for this resource is already executing.
        return None


def heartbeat(engine, job, *, lease_seconds=180):
    stamp = now()
    with engine.begin() as conn:
        result = conn.execute(text("""UPDATE workjob SET lease_until=:until, updated_at=:stamp
            WHERE id=:id AND status='RUNNING' AND lease_token=:token AND lease_until>:stamp"""),
            {"id": job.id, "token": job.lease_token, "stamp": stamp,
             "until": stamp + timedelta(seconds=lease_seconds)})
        return result.rowcount == 1


def guard_publication(session):
    job = current_job.get()
    if job is None:
        return
    _, owner, digest = source_identity(session, job.kind, job.resource_type, job.resource_id, lock=True)
    fresh = session.exec(select(WorkJob).where(WorkJob.id == job.id).with_for_update()
                         .execution_options(populate_existing=True)).first()
    if not fresh or fresh.status != "RUNNING" or fresh.lease_token != job.lease_token or fresh.lease_until <= now():
        raise WorkCancelled("LEASE_LOST")
    if owner != job.owner_user_id or digest != job.source_hash:
        raise WorkCancelled("SOURCE_CHANGED")


def finish(engine, job, *, status, error_code=None):
    with engine.begin() as conn:
        conn.execute(text("""UPDATE workjob SET status=:status, error_code=:error,
            updated_at=:stamp, available_at=:available, lease_until=NULL, lease_token=NULL
            WHERE id=:id AND status='RUNNING' AND lease_token=:token AND lease_until>:stamp"""),
            {"id": job.id, "token": job.lease_token, "status": status, "error": error_code,
             "stamp": now(), "available": now() + timedelta(seconds=min(120, 10 * 2 ** job.attempts))})


def retry(session, job):
    if job.status not in {"FAILED", "CANCELLED"}:
        return job
    if session.get_bind().dialect.name == "postgresql":
        session.exec(text("SELECT pg_advisory_xact_lock(71048231)"))
    _, owner, digest = source_identity(session, job.kind, job.resource_type, job.resource_id, lock=True)
    if owner != job.owner_user_id or digest != job.source_hash:
        raise WorkCancelled("SOURCE_CHANGED")
    # Explicit retries are bounded by the same pending-owner admission limit.
    pending = session.exec(select(func.count()).select_from(WorkJob).where(
        WorkJob.owner_user_id == owner, WorkJob.status.in_(["QUEUED", "RUNNING"]))).one()
    total = session.exec(select(func.count()).select_from(WorkJob).where(WorkJob.status.in_(["QUEUED", "RUNNING"]))).one()
    if pending >= 32 or total >= int(os.getenv("DENTAL_MAX_PENDING_JOBS", "1000")):
        raise WorkCapacity("Too many pending jobs")
    session.exec(update(WorkJob).where(WorkJob.id == job.id, WorkJob.status.in_(["FAILED", "CANCELLED"])).values(
        status="QUEUED", attempts=0, available_at=now(), error_code=None, updated_at=now()))
    session.flush()
    session.refresh(job)
    return job


class WorkGarbage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reference: str = Field(unique=True)
    available_at: datetime = Field(default_factory=lambda: now() + timedelta(days=1), index=True)
    attempts: int = 0


def collect_garbage(engine):
    from app.object_storage import delete
    with Session(engine, expire_on_commit=False) as session:
        query = select(WorkGarbage).where(WorkGarbage.available_at <= now()).order_by(WorkGarbage.id).limit(1)
        if engine.dialect.name == 'postgresql':
            query = query.with_for_update(skip_locked=True)
        garbage = session.exec(query).first()
        if garbage is None:
            return
        garbage.available_at = now() + timedelta(minutes=5)
        garbage.attempts += 1
        session.add(garbage)
        session.commit()
        session.close()
        # Only immutable generated results belong in this queue.
        if not str(garbage.reference).startswith('uploads/ai_results/'):
            return
        # Never erase a successfully published result after an ambiguous commit.
        in_use = session.exec(text("SELECT 1 FROM analysis WHERE result_path=:ref UNION ALL SELECT 1 FROM guestanalysis WHERE result_path=:ref LIMIT 1"), params={"ref": garbage.reference}).first()
        session.close()
        if in_use:
            session.exec(__import__('sqlalchemy').delete(WorkGarbage).where(WorkGarbage.id == garbage.id))
            session.commit()
            return
        try:
            delete(garbage.reference)
        except Exception:
            return
        session.exec(__import__('sqlalchemy').delete(WorkGarbage).where(WorkGarbage.id == garbage.id))
        session.commit()


def prune_history(engine):
    from sqlalchemy import delete
    with Session(engine) as session:
        ids = session.exec(select(WorkJob.id).where(
            WorkJob.status.in_(["DONE", "CANCELLED", "FAILED"]),
            WorkJob.updated_at < now() - timedelta(days=30)).order_by(WorkJob.id).limit(100)).all()
        if ids:
            session.exec(delete(WorkJob).where(WorkJob.id.in_(ids)))
        session.commit()
