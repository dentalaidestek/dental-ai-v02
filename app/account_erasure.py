"""Shared account-erasure coordinator.

Immediate phase revokes access and removes/anonymizes account identity. External
objects and Academic V2 derivatives are handed to durable deletion jobs.
Records that may be needed for payment, dispute, security or legal retention are
not blindly deleted here; they keep only the minimum referential anchor.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlmodel import Session, select

from app.study_index_jobs import enqueue_material_deletion, tombstone_material


def utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def begin_account_erasure(
    session: Session,
    *,
    user_id: int,
    actor: str,
    block_registration: bool = False,
    deleted_email_fingerprint: str | None = None,
    admin_user_id: int | None = None,
) -> list[str]:
    """Atomically make an account inaccessible and queue owned academic erasure.

    Returns non-academic storage references (profile/credential) for the caller's
    durable generic-storage cleanup path. Never return identity values.
    """
    # Import here to avoid a module cycle while main.py still owns legacy models.
    from app.main import (
        AdminAuditLog, DeletedAccountEmail, ExpertDeviceChallenge,
        ExpertProfile, ExpertTrustedDevice, PasswordResetToken,
        SessionToken, StudyChatMessage, StudyCourse, StudyMaterial, User,
        WebPushDelivery, WebPushMessageDelivery, WebPushSubscription, RealtimeEvent,
    )

    user = session.get(User, user_id)
    if not user or user.role == "ADMIN":
        raise ValueError("ACCOUNT_NOT_ERASABLE")

    extra_storage: list[str] = []
    if user.profile_photo_path:
        extra_storage.append(user.profile_photo_path)

    profile = session.exec(select(ExpertProfile).where(ExpertProfile.user_id == user_id)).first()
    if profile:
        if profile.credential_document_path:
            extra_storage.append(profile.credential_document_path)
        profile.phone = None
        profile.phone_verified = False
        profile.credential_document_path = None
        profile.credential_document_name = None
        profile.credential_document_mime = None
        profile.availability = "PASSIVE"
        profile.application_status = "REJECTED"
        profile.verification_status = "REJECTED"
        profile.identity_verified = False
        profile.specialty_verified = False
        profile.academic_title_verified = False
        profile.verified_at = None
        profile.updated_at = utcnow_naive()
        session.add(profile)

    for model in (SessionToken, PasswordResetToken, ExpertTrustedDevice, ExpertDeviceChallenge):
        for row in session.exec(select(model).where(model.user_id == user_id)).all():
            session.delete(row)

    # Remove per-user realtime/push traces. Delivery rows reference subscriptions
    # and notices; delete the per-device delivery records before subscriptions.
    sub_ids = [row.id for row in session.exec(
        select(WebPushSubscription).where(WebPushSubscription.user_id == user_id)
    ).all()]
    if sub_ids:
        for model in (WebPushDelivery, WebPushMessageDelivery):
            for row in session.exec(select(model).where(model.subscription_id.in_(sub_ids))).all():
                session.delete(row)
    for sub in session.exec(select(WebPushSubscription).where(WebPushSubscription.user_id == user_id)).all():
        session.delete(sub)
    for event in session.exec(select(RealtimeEvent).where(RealtimeEvent.user_id == user_id)).all():
        session.delete(event)

    materials = session.exec(
        select(StudyMaterial).where(
            StudyMaterial.owner_user_id == user_id,
            StudyMaterial.deleted_at == None,
        )
    ).all()
    for material in materials:
        tombstone_material(session, material_id=material.id, owner_user_id=user_id)
        enqueue_material_deletion(
            session,
            owner_user_id=user_id,
            material_id=material.id,
            storage_reference=material.file_path,
            provider_file_name=material.gemini_file_name,
        )
        # Remove direct provider URI/name from the live material row immediately.
        material.gemini_file_name = None
        material.gemini_file_uri = None
        material.gemini_file_expires_at = None
        session.add(material)

    # Academic chat text is user-authored content and is not needed for retained
    # payment/dispute references. Courses can be removed after material jobs hold
    # the deletion references they need.
    for msg in session.exec(select(StudyChatMessage).where(StudyChatMessage.owner_user_id == user_id)).all():
        session.delete(msg)
    for course in session.exec(select(StudyCourse).where(StudyCourse.owner_user_id == user_id)).all():
        session.delete(course)

    if block_registration:
        if not admin_user_id or not deleted_email_fingerprint:
            raise ValueError("ADMIN_BLOCK_METADATA_REQUIRED")
        existing = session.exec(
            select(DeletedAccountEmail).where(DeletedAccountEmail.deleted_user_id == user_id)
        ).first()
        if not existing:
            session.add(DeletedAccountEmail(
                email_fingerprint=deleted_email_fingerprint,
                deleted_user_id=user_id,
                deleted_by_admin_id=admin_user_id,
            ))

    # Keep only a pseudonymous FK anchor so retained payment/dispute/audit rows
    # do not break. Self-delete does not create a permanent email fingerprint.
    user.username = f"deleted_user_{user.id}_{uuid.uuid4().hex[:10]}"
    user.display_name = "Silinmiş Kullanıcı"
    user.email = None
    user.password_hash = None
    user.profile_photo_path = None
    user.is_active = False
    session.add(user)

    session.add(AdminAuditLog(
        admin_user_id=admin_user_id or user_id,
        action="ACCOUNT_ERASURE_STARTED",
        target_user_id=user_id,
        detail=f"actor={actor}; registration_block={int(block_registration)}",
    ))
    return extra_storage
