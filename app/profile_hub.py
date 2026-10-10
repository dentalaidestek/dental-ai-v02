"""Shared profile document UI; each verification retains its own authority."""
import uuid
from pathlib import Path

from fastapi import File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.membership_verification import DOCUMENT_TYPES, validate_document

EXPERT_TITLES = {'Uzman Diş Hekimi', 'Dr. Öğr. Üyesi', 'Doç. Dr.', 'Prof. Dr.'}
PROFILE_DOCUMENTS = '/account?section=professional#professional-info'


def document_page(request, purpose='membership'):
    from app import main as m
    user = m.get_current_user(request)
    if not user:
        return RedirectResponse('/login', status_code=303)
    context = {'purpose': purpose, 'document_types': DOCUMENT_TYPES,
               'document_action': '/account/verification', 'document_field': 'document',
               'max_mb': 5, 'document_heading': 'Üyelik belgenizi doğrulayın',
               'back_url': PROFILE_DOCUMENTS}
    if purpose not in {'membership', 'expert', 'title'}:
        return HTMLResponse('Geçersiz belge işlemi.', status_code=400)
    if purpose != 'membership':
        with Session(m.engine) as s:
            meta = s.exec(select(m.UserAccountMeta).where(m.UserAccountMeta.user_id == user.id)).first()
            if not meta or meta.professional_title not in EXPERT_TITLES:
                return HTMLResponse('Bu belge işlemi için uzmanlık başvurusu uygunluğu gerekiyor.', status_code=403)
            if purpose == 'title':
                pending = s.exec(select(m.ExpertTitleChange).where(
                    m.ExpertTitleChange.user_id == user.id,
                    m.ExpertTitleChange.status.in_(['AWAITING_DOCUMENT','PENDING_REVIEW','REJECTED']),
                ).order_by(m.ExpertTitleChange.created_at.desc()).limit(1)).first()
                if not pending:
                    return RedirectResponse(PROFILE_DOCUMENTS, status_code=303)
                if pending.status == 'PENDING_REVIEW':
                    return RedirectResponse(PROFILE_DOCUMENTS, status_code=303)
                context.update(document_types={'TITLE': ('Unvan Belgesi', pending.requested_title)},
                    document_action='/account/professional-title/document',
                    document_heading=f'{pending.requested_title} unvanını doğrulayın',
                    document_explanation='Yeni unvan onaylanana kadar mevcut doğrulanmış unvanınız ve vaka kabul durumunuz korunur.')
            else:
                profile = s.exec(select(m.ExpertProfile).where(m.ExpertProfile.user_id == user.id)).first()
                if not profile:
                    return RedirectResponse('/expert-support/profile#profileEdit', status_code=303)
                if profile.application_status == 'SUBMITTED':
                    return RedirectResponse(PROFILE_DOCUMENTS, status_code=303)
                context.update(document_types={'EXPERT': ('Uzmanlık Belgesi', 'Unvan ve branşınızı gösteren e-Devlet mesleki belgesi')},
                    document_action='/account/documents/expert', document_heading='Uzmanlık belgenizi gönderin',
                    document_explanation='Yeni belge gönderdiğinizde uzman profiliniz yeniden incelemeye alınır ve inceleme boyunca yeni vaka kabulünüz kapatılır.')
        context.update(document_field='credential_document', max_mb=10)
    return m.templates.TemplateResponse(request=request, name='membership_verification.html', context=context)


def register(app):
    from app import main as m

    @app.get('/account/documents', response_class=HTMLResponse)
    def documents(request: Request, purpose: str = 'membership'):
        return document_page(request, purpose)

    @app.post('/account/documents/expert')
    @m.offload
    def expert_document(request: Request, credential_document: UploadFile = File(...)):
        user = m.get_current_user(request)
        if not user:
            return RedirectResponse('/login', status_code=303)
        filename = (credential_document.filename or '').replace('\\', '/').rsplit('/',1)[-1][:240]
        data = credential_document.file.read(10*1024*1024+1)
        try:
            mime = validate_document(filename, data, max_bytes=10*1024*1024)
        except ValueError as exc:
            return HTMLResponse(str(exc), status_code=400)
        # Check ownership/eligibility before external storage writes.
        with Session(m.engine) as s:
            meta = s.exec(select(m.UserAccountMeta).where(m.UserAccountMeta.user_id == user.id)).first()
            profile = s.exec(select(m.ExpertProfile).where(m.ExpertProfile.user_id == user.id)).first()
            if not meta or meta.professional_title not in EXPERT_TITLES or not profile:
                return HTMLResponse('Uzmanlık başvurusu bulunamadı.', status_code=403)
            if profile.application_status == 'SUBMITTED':
                return HTMLResponse('Belgeniz incelemede. Sonuçlanmadan yeni belge gönderilemez.', status_code=409)
        path = m.UPLOAD_DIR / 'expert_credentials' / f'user_{user.id}' / f'credential_{uuid.uuid4().hex}{Path(filename).suffix.lower()}'
        reference = str(path); committed = False
        try:
            reference = m.storage_write_bytes(path, data, content_type=mime)
            with Session(m.engine, expire_on_commit=False) as s:
                owner_stmt = select(m.User).where(m.User.id == user.id)
                if m.engine.dialect.name == 'postgresql': owner_stmt = owner_stmt.with_for_update()
                owner = s.exec(owner_stmt).first()
                meta = s.exec(select(m.UserAccountMeta).where(m.UserAccountMeta.user_id == user.id)).first()
                stmt = select(m.ExpertProfile).where(m.ExpertProfile.user_id == user.id)
                if m.engine.dialect.name == 'postgresql': stmt = stmt.with_for_update()
                profile = s.exec(stmt).first()
                if not owner or not owner.is_active or not meta or meta.professional_title not in EXPERT_TITLES or not profile:
                    return HTMLResponse('Uzmanlık başvurusu artık belge gönderimine açık değil.', status_code=409)
                if profile.application_status == 'SUBMITTED':
                    return HTMLResponse('Belgeniz incelemede. Sonuçlanmadan yeni belge gönderilemez.', status_code=409)
                profile.credential_document_path = reference
                profile.credential_document_name = filename; profile.credential_document_mime = mime
                profile.application_status = 'SUBMITTED'; profile.verification_status = 'PENDING'
                profile.specialty_verified = False; profile.academic_title_verified = False
                profile.application_reviewed_at = None; profile.verified_at = None
                profile.availability = 'PASSIVE'; profile.capacity_auto_busy = False
                profile.updated_at = m._utcnow_naive(); s.add(profile); s.flush()
                events = m._record_expert_profile_realtime_events(s, profile)
                s.commit(); committed = True
            for event in events: m.on_loop(m._publish_realtime_event, event)
            return RedirectResponse(PROFILE_DOCUMENTS, status_code=303)
        finally:
            if not committed:
                try: m.storage_delete(reference)
                except Exception: m.logger.exception('Expert document cleanup failed')
