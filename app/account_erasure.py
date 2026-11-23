"""Shared account-erasure coordinator.

Immediate phase revokes access and removes/anonymizes account identity. External
objects and Academic V2 derivatives are handed to durable deletion jobs.
Records that may be needed for payment, dispute, security or legal retention are
not blindly deleted here; they keep only the minimum referential anchor.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, text
from sqlmodel import Session, select

from app.study_index_jobs import enqueue_material_deletion, tombstone_material


def utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def erase_account_ai_data(session: Session, user_id: int) -> tuple[int, list[str]]:
    """Erase guest analyses and scrub all queued AI payloads for this account.

    Patient-linked Analysis/ImageAsset/PatientMedia and treatment/tooth records
    are intentionally retained: they can contain third-party clinical records
    subject to separate patient-care and legal-retention duties. Patient AI jobs
    are cancelled and their transient payloads are cleared; published result
    objects are preserved by the WorkGarbage reference check when still linked.
    """
    from app.main import GuestAnalysis, GuestImageAsset
    from app.work_jobs import (
        WorkJob,
        enqueue_ai_result_cleanup,
        enqueue_guest_analysis_cleanup,
    )

    dialect = session.get_bind().dialect.name
    guests_query = select(GuestAnalysis).where(
        GuestAnalysis.owner_user_id == user_id
    ).order_by(GuestAnalysis.id)
    if dialect == "postgresql":
        guests_query = guests_query.with_for_update()
    guests = session.exec(
        guests_query.execution_options(populate_existing=True)
    ).all()
    guest_ids = [row.id for row in guests if row.id is not None]

    assets = []
    if guest_ids:
        assets_query = select(GuestImageAsset).where(
            GuestImageAsset.guest_analysis_id.in_(guest_ids)
        ).order_by(GuestImageAsset.id)
        if dialect == "postgresql":
            assets_query = assets_query.with_for_update()
        assets = session.exec(
            assets_query.execution_options(populate_existing=True)
        ).all()

    jobs_query = select(WorkJob).where(
        WorkJob.owner_user_id == user_id,
    ).order_by(WorkJob.id)
    if dialect == "postgresql":
        jobs_query = jobs_query.with_for_update()
    jobs = session.exec(
        jobs_query.execution_options(populate_existing=True)
    ).all()

    guest_references = {
        str(reference)
        for reference in (
            [row.file_path for row in assets]
            + [row.result_path for row in guests]
        )
        if reference
    }
    queued_references: set[str] = set()
    unqueued_references: list[str] = []
    for reference in sorted(guest_references):
        if enqueue_guest_analysis_cleanup(session, reference):
            queued_references.add(reference)
        elif enqueue_ai_result_cleanup(session, reference):
            queued_references.add(reference)
        else:
            # Keep the existing caller fallback for legacy guest references;
            # never broaden the worker's accepted object-key patterns.
            unqueued_references.append(reference)

    # Remove guest jobs entirely and scrub transient payloads from all other
    # jobs. Re-arm result cleanup only for the private AI-result namespace;
    # the collector preserves any result still referenced by a patient record.
    for job in jobs:
        reference = str(job.result_ref) if job.result_ref else None
        if reference and reference not in queued_references:
            if enqueue_ai_result_cleanup(session, reference):
                queued_references.add(reference)

        if job.resource_type == "GUEST":
            if reference and reference not in queued_references:
                unqueued_references.append(reference)
            session.delete(job)
            continue

        if job.status in {"QUEUED", "RUNNING"}:
            job.status = "CANCELLED"
            job.error_code = "ACCOUNT_ERASED"
            job.lease_token = None
            job.lease_until = None
        job.payload_json = "{}"
        if reference and reference in queued_references:
            job.result_ref = None
        job.updated_at = utcnow_naive()
        session.add(job)

    for asset in assets:
        session.delete(asset)
    for guest in guests:
        session.delete(guest)

    return len(guests), sorted(set(unqueued_references))


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
        ExpertProfile, ExpertTitleChange, ExpertTrustedDevice, PasswordResetToken,
        SessionToken, StudyChatMessage, StudyCourse, StudyMaterial, User, EmailVerificationChallenge, EmailChangeChallenge,
        WebPushDelivery, WebPushMessageDelivery, WebPushSubscription, RealtimeEvent, E2EEDeviceKey,
    )

    user_stmt = select(User).where(User.id == user_id)
    if session.get_bind().dialect.name == 'postgresql':
        user_stmt = user_stmt.with_for_update()
    # Serialize erasure with private membership submissions/reviews.
    user = session.exec(user_stmt.execution_options(populate_existing=True)).first()
    if not user or user.role == "ADMIN":
        raise ValueError("ACCOUNT_NOT_ERASABLE")

    from app.membership_verification import MembershipVerification
    extra_storage: list[str] = []
    _, guest_storage_fallback = erase_account_ai_data(session, user_id)
    extra_storage.extend(guest_storage_fallback)
    from app.expert_social_maintenance import erase_user_content
    erase_user_content(session, user_id)
    # Account erasure retains a pseudonymous User row, so its FK cascade does
    # not run. Remove the member's comment reactions in the same transaction.
    from app.expert_social_models import SocialCommentLike
    session.exec(delete(SocialCommentLike).where(SocialCommentLike.user_id == user_id))
    for verification in session.exec(select(MembershipVerification).where(MembershipVerification.user_id == user_id)).all():
        extra_storage.append(verification.document_path)
        session.delete(verification)
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

    # Keep title-change audit rows, but remove their private source documents too.
    title_changes = session.exec(
        select(ExpertTitleChange).where(ExpertTitleChange.user_id == user_id)
    ).all()
    for change in title_changes:
        if change.credential_document_path:
            extra_storage.append(change.credential_document_path)
        change.credential_document_path = None
        change.credential_document_name = None
        change.credential_document_mime = None
        session.add(change)

    for model in (SessionToken, PasswordResetToken, ExpertTrustedDevice, ExpertDeviceChallenge, EmailVerificationChallenge, EmailChangeChallenge):
        for row in session.exec(select(model).where(model.user_id == user_id)).all():
            session.delete(row)

    # Retain the public-key history needed to identify old envelopes, but never
    # advertise an erased account as an active message recipient.
    for device in session.exec(select(E2EEDeviceKey).where(E2EEDeviceKey.user_id == user_id)).all():
        if device.revoked_at is None:
            device.revoked_at = utcnow_naive()
            session.add(device)

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
    from app.academic_learning import erase as erase_learning
    from app.academic_study_runs import erase as erase_runs
    erase_learning(session,user_id);erase_runs(session,user_id,purge=True)
    for msg in session.exec(select(StudyChatMessage).where(StudyChatMessage.owner_user_id == user_id)).all():
        from app.academic_remote_pdf import queue_erasure
        queue_erasure(session,msg)
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
    # Queue only known server-generated profile/identity assets in the same
    # transaction that clears their metadata. Keep unknown legacy references on
    # the existing caller fallback; never broaden the worker's accepted paths.
    from app.work_jobs import enqueue_account_asset_cleanup
    fallback_storage = []
    for reference in sorted({str(item) for item in extra_storage if item}):
        if not enqueue_account_asset_cleanup(session, reference):
            fallback_storage.append(reference)
    return fallback_storage


