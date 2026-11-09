"""Durable local triage and human review; images never leave this service.

Triage is synchronous and conservative. A human-review result is a completed
automatic check, not a broken worker. Only actual failed local checks are retried.
"""

import json
import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import case, func, or_
from sqlmodel import Session, select

from app import expert_social_safety as safety
from app.expert_social_models import (
    Publication, SocialComment, SocialDecision, SocialMedia, SocialModerationEvent,
    SocialModerationTask, SocialPost, now,
)

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
LEASE_SECONDS = 60
MODELS = {"POST": SocialPost, "COMMENT": SocialComment, "PUBLICATION": Publication}
REASON_TEXT = {
    "IMAGE_REVIEW": "Görsel, hasta mahremiyeti açısından yönetici incelemesi bekliyor.",
    "PRIVACY": "Olası kişisel veya hasta bilgisi için yönetici incelemesi gerekiyor.",
    "CONTENT_REVIEW": "İçerik için yönetici incelemesi gerekiyor.",
    "SPAM": "Tekrarlanan veya yoğun bağlantılı içerik inceleniyor.",
    "ABUSE": "Uygunsuz dil nedeniyle yayınlanmadı.",
    "MODERATION_UNAVAILABLE": "Otomatik kontrol tamamlanamadı; yeniden denenecek.",
    "ACCOUNT_REVIEW": "Hesap veya paylaşım durumu nedeniyle yönetici incelemesi gerekiyor.",
}


def evaluate(content, *, has_images=False):
    """Persist a recoverable failure without storing exception/provider payloads."""
    try:
        return safety.moderate(content, has_images=has_images)
    except Exception:
        logger.warning("social.moderation local_check_failed")
        return "PENDING", ["MODERATION_UNAVAILABLE"]


def reasons(row):
    try:
        value = json.loads(row.reasons_json)
        return value if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


def owner_id(kind, row):
    return row.expert_id if kind == "PUBLICATION" else row.author_id


def _event(session, task, *, source=None, reason=None, actor_id=None):
    session.add(SocialModerationEvent(
        job_id=task.job_id, target_type=task.target_type, target_id=task.target_id,
        revision=task.revision, content_version=task.content_version, state=task.state,
        status=task.last_decision_status, source=source or task.last_decision_source,
        reason=reason if reason is not None else task.last_decision_reason,
        actor_id=actor_id,
    ))


def record(session, kind, row, actor_id=None, reason=None, *, human=False,
           source=None, current=None, legacy=False, retry=False, preserve=False):
    """Update the lifecycle and its event in the caller's content transaction.

    Version-one records are new API writes (or explicitly selected legacy rows).
    Avoiding a lookup for each new row preserves bulk ORCID/audit insertion.
    Existing targets are locked after the caller locks their content row.
    """
    # PostgreSQL sequences never reuse a deleted publication ID. SQLite may,
    # so reconcile its retained target task before inserting a new lifecycle.
    reused_publication_id = kind == "PUBLICATION" and session.get_bind().dialect.name == "sqlite"
    if current is None and (row.version > 1 or reused_publication_id):
        with session.no_autoflush:
            current = session.exec(select(SocialModerationTask).where(
                SocialModerationTask.target_type == kind,
                SocialModerationTask.target_id == row.id,
            ).with_for_update()).first()
    stamp = now()
    if current is not None and preserve:
        # Pin/comment settings do not rerun triage or replace a human decision.
        current.content_version = row.version
        current.revision += 1
        current.updated_at = stamp
        if current.state == "RUNNING":
            current.state, current.wait_type = "FAILED", "RETRY"
            current.lease_token = current.lease_until = None
            current.next_attempt_at = stamp if current.attempts < MAX_ATTEMPTS else None
            if current.attempts >= MAX_ATTEMPTS:
                current.wait_type = "RETRY_EXHAUSTED"
        session.add(current)
        _event(session, current, source="SETTINGS", reason="POST_SETTINGS_UPDATED", actor_id=actor_id)
        return current
    codes = reasons(row)
    removed = row.status == "DELETED" or getattr(row, "deleted", False)
    if removed:
        state, wait_type = "AUTO_DONE", "NONE"
    elif human:
        state, wait_type = (("WAITING_OWNER", "OWNER_CHANGES") if row.status == "PENDING"
                            else ("HUMAN_DONE", "NONE"))
    elif row.status == "PENDING" and "MODERATION_UNAVAILABLE" in codes:
        state, wait_type = "FAILED", "RETRY"
    elif row.status == "PENDING":
        state, wait_type = "WAITING_HUMAN", "HUMAN_REVIEW"
    else:
        state, wait_type = "AUTO_DONE", "NONE"
    explanation = reason if reason is not None else " ".join(
        REASON_TEXT.get(code, "İçerik yönetici incelemesi bekliyor.") for code in codes
    )
    if not explanation:
        explanation = ("İçerik kaldırıldı." if removed else
                       "İçerik yönetici incelemesi bekliyor." if state == "WAITING_HUMAN" else
                       "Otomatik kontrol tamamlandı.")
    if current is None:
        current = SocialModerationTask(
            target_type=kind, target_id=row.id, owner_id=owner_id(kind, row),
            content_version=row.version, state=state, last_decision_status=row.status,
            created_at=row.created_at if legacy else stamp,
        )
    else:
        current.revision += 1
        if not retry:
            current.attempts = 0
    prior_wait = current.waiting_since
    current.owner_id = owner_id(kind, row)
    current.content_version = row.version
    current.state = state
    current.wait_type = wait_type
    current.reasons_json = json.dumps(codes)
    current.last_decision_status = row.status
    current.last_decision_reason = explanation
    current.last_decision_source = source or ("HUMAN" if human else "AUTOMATIC")
    current.last_decision_at = row.updated_at if legacy else stamp
    current.updated_at = stamp
    current.waiting_since = ((prior_wait if retry and prior_wait else
                              row.created_at if legacy else stamp)
                             if state in ("WAITING_HUMAN", "WAITING_OWNER", "FAILED") else None)
    current.last_error_code = "LOCAL_TRIAGE_FAILED" if state == "FAILED" else None
    current.next_attempt_at = (stamp + timedelta(minutes=2 ** current.attempts)
                               if retry and current.attempts < MAX_ATTEMPTS else
                               stamp if not retry else None) if state == "FAILED" else None
    if state == "FAILED" and current.attempts >= MAX_ATTEMPTS:
        current.wait_type = "RETRY_EXHAUSTED"
        current.last_decision_reason = "Otomatik kontrol tamamlanamadı; yönetici müdahalesi gerekiyor."
    current.lease_token = None
    current.lease_until = None
    session.add(current)
    _event(session, current, actor_id=actor_id)
    if state not in {"WAITING_HUMAN", "FAILED"} and row.version > 1:
        from app.expert_social_review_notifications import resolve_targets
        resolve_targets(session, kind, [row.id])
    return current


def _iso(value):
    return value.isoformat() + "Z" if value else None


def describe(task, row):
    if not task or task.content_version != row.version:
        # Read paths never create jobs or scan the backlog. Legacy pending rows
        # are registered by bounded migration/maintenance slices.
        codes = reasons(row)
        return {
            "job_id": task.job_id if task else None, "registered": False,
            "content_version": row.version, "revision": task.revision if task else 0,
            "state": "FAILED" if "MODERATION_UNAVAILABLE" in codes else
                     "WAITING_HUMAN" if row.status == "PENDING" else "AUTO_DONE",
            "wait_type": "RETRY" if "MODERATION_UNAVAILABLE" in codes else
                         "HUMAN_REVIEW" if row.status == "PENDING" else "NONE",
            "reasons": codes,
            "reason": " ".join(REASON_TEXT.get(code, "Yönetici incelemesi gerekiyor.") for code in codes)
                      or ("İçerik yönetici incelemesi bekliyor." if row.status == "PENDING" else "Otomatik kontrol tamamlandı."),
            "age_seconds": max(0, int((now() - row.created_at).total_seconds())),
            "waiting_since": _iso(row.created_at) if row.status == "PENDING" else None,
            "last_decision": {"status": row.status, "source": "LEGACY",
                              "reason": "", "at": _iso(row.updated_at)},
            "retryable": False,
        }
    return {
        "job_id": task.job_id, "registered": True,
        "content_version": task.content_version, "revision": task.revision,
        "state": task.state, "wait_type": task.wait_type,
        "reasons": json.loads(task.reasons_json), "reason": task.last_decision_reason,
        "created_at": _iso(task.created_at), "updated_at": _iso(task.updated_at),
        "waiting_since": _iso(task.waiting_since),
        "age_seconds": max(0, int((now() - (task.waiting_since or task.created_at)).total_seconds())),
        "last_decision": {"status": task.last_decision_status,
                          "source": task.last_decision_source,
                          "reason": task.last_decision_reason, "at": _iso(task.last_decision_at)},
        "attempts": task.attempts,
        "retryable": task.state == "FAILED" and task.attempts < MAX_ATTEMPTS,
        "next_attempt_at": _iso(task.next_attempt_at), "error_code": task.last_error_code,
    }


def metadata(session, kind, rows):
    if not rows:
        return {}
    tasks = {task.target_id: task for task in session.exec(select(SocialModerationTask).where(
        SocialModerationTask.target_type == kind,
        SocialModerationTask.target_id.in_([row.id for row in rows]),
    )).all()}
    return {row.id: describe(tasks.get(row.id), row) for row in rows}


def aging(session):
    """Aggregate the indexed queue, including pending rows predating task rollout."""
    result = {"waiting_human": 0, "waiting_owner": 0, "failed": 0, "running": 0,
              "over_1h": 0, "over_24h": 0, "oldest_wait_seconds": 0}
    stamp = now()
    for kind, model in MODELS.items():
        waiting = func.coalesce(SocialModerationTask.waiting_since, model.created_at)
        state = case((SocialModerationTask.content_version == model.version,
                      SocialModerationTask.state), else_="WAITING_HUMAN")
        statement = select(state, func.count(), func.min(waiting),
            func.sum(case((waiting < stamp - timedelta(hours=1), 1), else_=0)),
            func.sum(case((waiting < stamp - timedelta(hours=24), 1), else_=0)),
        ).select_from(model).outerjoin(SocialModerationTask,
            (SocialModerationTask.target_type == kind) &
            (SocialModerationTask.target_id == model.id),
        ).where(model.status == "PENDING")
        if kind == "PUBLICATION":
            statement = statement.where(Publication.deleted == False)
        for current, count, oldest, hour, day in session.exec(statement.group_by(state)).all():
            key = current.lower()
            if key in result:
                result[key] += count
            if current in ("WAITING_HUMAN", "FAILED", "RUNNING"):
                result["over_1h"] += int(hour or 0)
                result["over_24h"] += int(day or 0)
                if oldest:
                    result["oldest_wait_seconds"] = max(result["oldest_wait_seconds"],
                        max(0, int((stamp - oldest).total_seconds())))
    return result


def cancel_tasks(session, *, kind=None, versions=None, owner=None):
    """Close removed targets and append the cancellation in the erasure transaction."""
    statement = select(SocialModerationTask)
    if kind is not None:
        if not versions:
            return
        statement = statement.where(SocialModerationTask.target_type == kind,
                                    SocialModerationTask.target_id.in_(versions))
    if owner is not None:
        statement = statement.where(SocialModerationTask.owner_id == owner)
    removed = {}
    for task in session.exec(statement.with_for_update()).all():
        removed.setdefault(task.target_type, []).append(task.target_id)
        if task.last_decision_status == "DELETED":
            continue
        task.content_version = versions[task.target_id] if versions else task.content_version + 1
        task.revision += 1
        task.state, task.wait_type = "AUTO_DONE", "NONE"
        task.last_decision_status, task.last_decision_reason = "DELETED", "İçerik kaldırıldı."
        task.last_decision_source, task.last_decision_at = "DELETION", now()
        task.reasons_json = "[]"
        task.waiting_since = task.lease_token = task.lease_until = None
        task.next_attempt_at = task.last_error_code = None
        task.updated_at = now()
        session.add(task)
        _event(session, task)
    from app.expert_social_review_notifications import resolve_targets
    for target_kind, identifiers in removed.items():
        resolve_targets(session, target_kind, identifiers)


def backfill_pending(engine, *, limit=60):
    """Register at most `limit` legacy pending rows, oldest first, off read paths."""
    remaining = max(0, min(limit, 200))
    count = 0
    for kind, model in MODELS.items():
        if not remaining:
            break
        with Session(engine) as session:
            statement = select(model, SocialModerationTask).outerjoin(
                SocialModerationTask,
                (SocialModerationTask.target_type == kind) &
                (SocialModerationTask.target_id == model.id),
            ).where(model.status == "PENDING", or_(
                SocialModerationTask.id == None,
                SocialModerationTask.content_version < model.version,
            ))
            if kind == "PUBLICATION":
                statement = statement.where(Publication.deleted == False)
            rows = session.exec(statement.order_by(model.created_at, model.id)
                .limit(remaining).with_for_update(of=model, skip_locked=True)).all()
            for row, task in rows:
                if task is not None:
                    task = session.exec(select(SocialModerationTask).where(
                        SocialModerationTask.id == task.id).with_for_update()).one()
                record(session, kind, row, current=task, legacy=True, source="LEGACY_BACKFILL")
            session.commit()
            count += len(rows)
            remaining -= len(rows)
    return count


def _retry_content(session, kind, row):
    if kind == "POST":
        card = json.loads(row.preview_json) if row.preview_json else {}
        content = "\n".join([row.text, row.link_url or "", *(
            str(card.get(key) or "") for key in ("title", "description", "site_name")
        )])
        images = session.exec(select(SocialMedia.id).where(SocialMedia.post_id == row.id)).first()
        return content, images is not None
    if kind == "COMMENT":
        return row.text, False
    return " ".join(str(getattr(row, key) or "") for key in (
        "title", "authors", "year", "journal", "doi", "url", "description"
    )), False


def _can_publish(session, kind, row):
    # A retry must obey the same current account/profile constraints as a new
    # write or human approval. This import is late to avoid application cycles.
    from app import main

    author = session.get(main.User, owner_id(kind, row))
    if not author or not author.is_active:
        return False
    expert_id = owner_id(kind, row)
    if kind == "COMMENT":
        parent = session.get(SocialPost, row.post_id)
        if not parent or parent.status != "PUBLISHED":
            return False
        expert_id = parent.author_id
    expert = session.get(main.User, expert_id)
    profile = session.exec(select(main.ExpertProfile).where(main.ExpertProfile.user_id == expert_id)).first()
    policy = session.exec(select(main.ExpertPolicyState).where(
        main.ExpertPolicyState.expert_user_id == expert_id)).first()
    return bool(expert and expert.is_active and expert.role in ("DOCTOR", "ADMIN")
        and profile and profile.application_status == "APPROVED"
        and profile.verification_status == "VERIFIED" and profile.specialty_verified
        and profile.credential_document_path and profile.phone
        and profile.availability != "PASSIVE" and not (policy and main._expert_is_blocked(policy)))


def retry_failed(engine, *, limit=2):
    """Lease failed local checks; never retry/autoapprove a human-review wait."""
    limit = max(0, min(limit, 10))
    if not limit:
        return 0
    stamp = now()
    claims = []
    with Session(engine) as session:
        expired = session.exec(select(SocialModerationTask).where(
            SocialModerationTask.state == "RUNNING", SocialModerationTask.lease_until <= stamp,
        ).order_by(SocialModerationTask.lease_until, SocialModerationTask.id).limit(limit)
         .with_for_update(skip_locked=True)).all()
        for task in expired:
            task.state = "FAILED"
            task.wait_type = "RETRY" if task.attempts < MAX_ATTEMPTS else "RETRY_EXHAUSTED"
            task.lease_token = task.lease_until = None
            task.last_error_code = "LEASE_EXPIRED"
            task.next_attempt_at = stamp if task.attempts < MAX_ATTEMPTS else None
            task.updated_at = stamp
            task.revision += 1
            session.add(task)
            _event(session, task, source="RECOVERY", reason="WORKER_LEASE_EXPIRED")
        session.flush()
        rows = session.exec(select(SocialModerationTask).where(
            SocialModerationTask.state == "FAILED", SocialModerationTask.attempts < MAX_ATTEMPTS,
            SocialModerationTask.next_attempt_at <= stamp,
        ).order_by(SocialModerationTask.next_attempt_at, SocialModerationTask.id).limit(limit)
         .with_for_update(skip_locked=True)).all()
        for task in rows:
            task.state = "RUNNING"
            task.lease_token = str(uuid4())
            task.lease_until = stamp + timedelta(seconds=LEASE_SECONDS)
            task.attempts += 1
            task.revision += 1
            task.updated_at = stamp
            session.add(task)
            _event(session, task, source="RETRY", reason="LOCAL_RETRY_STARTED")
            claims.append((task.target_type, task.target_id, task.lease_token, task.content_version))
        session.commit()
    for kind, ident, token, version in claims:
        try:
            with Session(engine) as session:
                model = MODELS[kind]
                # Match API lock order: content, then task. The persisted lease
                # prevents multiple processes from completing the same attempt.
                row = session.exec(select(model).where(model.id == ident).with_for_update()).first()
                task = session.exec(select(SocialModerationTask).where(
                    SocialModerationTask.target_type == kind, SocialModerationTask.target_id == ident,
                ).with_for_update()).first()
                if not task or task.state != "RUNNING" or task.lease_token != token:
                    continue
                if not row or row.status == "DELETED" or getattr(row, "deleted", False):
                    task.state, task.wait_type = "AUTO_DONE", "NONE"
                    task.lease_token = task.lease_until = task.next_attempt_at = None
                    task.last_decision_status, task.last_decision_reason = "DELETED", "İçerik kaldırıldı."
                    task.last_decision_source, task.last_decision_at = "RECOVERY", now()
                    task.waiting_since, task.last_error_code = None, None
                    task.revision += 1
                    session.add(task)
                    _event(session, task)
                    from app.expert_social_review_notifications import resolve_targets
                    resolve_targets(session, kind, [ident])
                elif row.version != version or task.content_version != version:
                    record(session, kind, row, current=task, source="RECONCILED")
                else:
                    content, has_images = _retry_content(session, kind, row)
                    status, codes = evaluate(content, has_images=has_images)
                    if status == "PUBLISHED" and not _can_publish(session, kind, row):
                        status, codes = "PENDING", ["ACCOUNT_REVIEW"]
                    encoded = json.dumps(codes)
                    if row.status != status or row.reasons_json != encoded:
                        row.status, row.reasons_json = status, encoded
                        row.version += 1
                        row.updated_at = now()
                    session.add(row)
                    record(session, kind, row, current=task, source="AUTOMATIC_RETRY", retry=True)
                    session.add(SocialDecision(target_type=kind, target_id=ident,
                        status=row.status, version=row.version, reason=encoded))
                session.commit()
        except Exception:
            # A crashed transaction leaves its lease for bounded recovery. Never
            # log raw content, storage references, or exception messages.
            logger.warning("social.moderation retry_deferred")
    return len(claims)
