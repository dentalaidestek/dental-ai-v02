"""Private, manually reviewed membership documents; no expert-role grants."""
import io
import uuid
import warnings
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from PIL import Image
from pypdf import PdfReader
from sqlmodel import Field, SQLModel, Session, select

DOCUMENT_TYPES = {
    'DIPLOMA': ('Diploma', 'Diş hekimliği fakültesi diploması'),
    'GRADUATION': ('Mezuniyet Belgesi', 'Üniversiteden alınan resmi mezuniyet belgesi'),
    'TDB_CARD': ('TDB Kimlik Kartı', 'Türk Diş Hekimleri Birliği üye kartı'),
    'STUDENT': ('Öğrenci Belgesi', 'Güncel öğrenci durum belgesi'),
}
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024


class MembershipVerification(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    document_type: str
    document_path: str
    document_name: str
    document_mime: str
    name_snapshot: str
    title_snapshot: str = ''
    status: str = Field(default='PENDING', index=True)
    submitted_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by_user_id: Optional[int] = None
    rejection_reason: Optional[str] = None


def latest(session, user_id):
    return session.exec(select(MembershipVerification).where(MembershipVerification.user_id == user_id).order_by(MembershipVerification.id.desc()).limit(1)).first()


def title_for(session, user_id):
    from app import main
    meta = session.exec(select(main.UserAccountMeta).where(main.UserAccountMeta.user_id == user_id)).first()
    return (meta.professional_title if meta else '') or ''


def state(session, user):
    row = latest(session, user.id)
    if not row:
        return {'status': 'NONE'}
    status = row.status
    if status == 'VERIFIED' and (row.name_snapshot != user.display_name or row.title_snapshot != title_for(session, user.id)):
        status = 'STALE'
    return {'status': status, 'id': row.id, 'document_type': row.document_type,
            'label': DOCUMENT_TYPES.get(row.document_type, ('Belge',))[0],
            'reason': row.rejection_reason, 'student': row.document_type == 'STUDENT'}


def validate_document(filename, data, *, max_bytes=MAX_DOCUMENT_BYTES):
    if not data or len(data) > max_bytes:
        raise ValueError(f'Belge boş olamaz ve {max_bytes // (1024*1024)} MB sınırını aşamaz.')
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == '.pdf':
            if not data.lstrip().startswith(b'%PDF-'):
                raise ValueError()
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
                raise ValueError()
            return 'application/pdf'
        expected = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG'}.get(suffix)
        if not expected:
            raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != expected:
                    raise ValueError()
                image.verify()
        return 'image/png' if expected == 'PNG' else 'image/jpeg'
    except Exception as exc:
        raise ValueError('Okunabilir JPG, PNG veya şifresiz PDF yükleyin (PDF en fazla 100 sayfa).') from exc


def register(app):
    from app import main as m

    def render(request, error=None, status_code=200):
        return m.templates.TemplateResponse(request=request, name='membership_verification.html', context={'document_types': DOCUMENT_TYPES, 'error': error}, status_code=status_code)

    @app.get('/account/verification', response_class=HTMLResponse)
    def verification_page(request: Request):
        if not m.get_current_user(request):
            return RedirectResponse('/login', status_code=303)
        return render(request)

    @app.post('/account/verification')
    @m.offload
    def submit(request: Request, document_type: str = Form(...), consent: str = Form(''), document: UploadFile = File(...)):
        user = m.get_current_user(request)
        if not user:
            return RedirectResponse('/login', status_code=303)
        if document_type not in DOCUMENT_TYPES or consent != 'yes':
            return render(request, 'Belge türünü seçin ve belgenin size ait olduğunu onaylayın.', 400)
        data = document.file.read(MAX_DOCUMENT_BYTES + 1)
        filename = (document.filename or '').replace('\\', '/').rsplit('/', 1)[-1][:240]
        try:
            mime = validate_document(filename, data)
        except ValueError as exc:
            return render(request, str(exc), 400)
        with Session(m.engine) as session:
            if state(session, user)['status'] in {'PENDING', 'VERIFIED'}:
                return render(request, 'Mevcut başvurunuz incelemede veya üyeliğiniz zaten doğrulanmış.', 409)
        destination = m.UPLOAD_DIR / 'membership_documents' / f'user_{user.id}' / f'{uuid.uuid4().hex}{Path(filename).suffix.lower()}'
        reference = str(destination)
        committed = False
        try:
            # Object-storage I/O never holds a database connection.
            reference = m.storage_write_bytes(destination, data, content_type=mime)
            events = []
            with Session(m.engine, expire_on_commit=False) as session:
                stmt = select(m.User).where(m.User.id == user.id)
                if m.engine.dialect.name == 'postgresql': stmt = stmt.with_for_update()
                owner = session.exec(stmt).first()
                if not owner or not owner.is_active:
                    return HTMLResponse('Hesap aktif değil.', status_code=403)
                if state(session, owner)['status'] in {'PENDING', 'VERIFIED'}:
                    return render(request, 'Mevcut başvurunuz incelemede veya üyeliğiniz zaten doğrulanmış.', 409)
                if len((owner.display_name or '').strip()) < 2:
                    return render(request, 'Önce Profilim bölümünden ad soyadınızı girin.', 400)
                row = MembershipVerification(user_id=owner.id, document_type=document_type, document_path=reference, document_name=filename, document_mime=mime, name_snapshot=owner.display_name, title_snapshot=title_for(session, owner.id), submitted_at=m._utcnow_naive())
                session.add(row); session.flush()
                _, event, _ = m._notify_user(session, user_id=owner.id, actor_user_id=owner.id, notice_type='MEMBERSHIP_SUBMITTED', title='Üyelik belgeniz incelemede', message='Belgeniz yönetici incelemesine gönderildi.', related_type='membership_verification', related_id=row.id, dedup_key=f'membership-submitted:{row.id}', target_url='/account/verification')
                if event: events.append(event)
                for admin in session.exec(select(m.User).where(m.User.role == 'ADMIN', m.User.is_active == True)).all():
                    events.append(m._record_realtime_event(session, admin.id, 'MEMBERSHIP_SUBMITTED', 'membership_verification', row.id, {'verification_id': row.id, 'target_url': '/admin/member-verifications'}))
                session.commit(); committed = True
            for event in events: m.on_loop(m._publish_realtime_event, event)
            return RedirectResponse('/account/documents?purpose=membership&submitted=1', status_code=303)
        finally:
            if not committed:
                try: m.storage_delete(reference)
                except Exception: m.logger.exception('Membership upload cleanup failed')

    @app.get('/account/verification/{verification_id}/document')
    @m.offload
    def document_view(request: Request, verification_id: int):
        user = m.get_current_user(request)
        if not user: return HTMLResponse('Oturum gerekli.', status_code=401)
        with Session(m.engine, expire_on_commit=False) as session:
            row = session.get(MembershipVerification, verification_id)
            if not row or (row.user_id != user.id and user.role != 'ADMIN'):
                return HTMLResponse('Belge bulunamadı.', status_code=404)
            if user.role == 'ADMIN':
                session.add(m.AdminAuditLog(admin_user_id=user.id, action='MEMBERSHIP_DOCUMENT_VIEWED', target_user_id=row.user_id, detail=f'#{row.id}'))
                session.commit()
        try: path = m.storage_ensure_local(row.document_path)
        except FileNotFoundError: return HTMLResponse('Belge bulunamadı.', status_code=404)
        return FileResponse(path, media_type=row.document_mime, filename=row.document_name, content_disposition_type='attachment', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; sandbox"})

    @app.get('/admin/member-verifications', response_class=HTMLResponse)
    def admin_page(request: Request, status: str = 'PENDING', cursor: Optional[int] = None):
        admin = m.get_current_user(request)
        if not admin or admin.role != 'ADMIN': return HTMLResponse('Yetkisiz işlem.', status_code=403)
        status = status if status in {'PENDING','VERIFIED','REJECTED','ALL'} else 'PENDING'
        with Session(m.engine, expire_on_commit=False) as session:
            stmt = select(MembershipVerification)
            if status != 'ALL': stmt = stmt.where(MembershipVerification.status == status)
            if cursor is not None: stmt = stmt.where(MembershipVerification.id < cursor)
            rows = session.exec(stmt.order_by(MembershipVerification.id.desc()).limit(26)).all()
            more = len(rows) > 25; rows = rows[:25]
            ids = {row.user_id for row in rows}
            users = {user.id: user for user in session.exec(select(m.User).where(m.User.id.in_(ids))).all()} if ids else {}
        return m.templates.TemplateResponse(request=request, name='admin_membership_verifications.html', context={'rows': rows, 'users': users, 'status': status, 'more': more, 'document_types': DOCUMENT_TYPES, 'admin_path': m.ADMIN_CENTER_PATH})

    @app.post('/admin/member-verifications/{verification_id}')
    @m.offload
    def review(request: Request, verification_id: int, decision: str = Form(...), reason: str = Form(''), identity_checked: str = Form('')):
        admin = m.get_current_user(request)
        if not admin or admin.role != 'ADMIN': return HTMLResponse('Yetkisiz işlem.', status_code=403)
        if decision not in {'APPROVE', 'REJECT'} or (decision == 'REJECT' and not reason.strip()) or (decision == 'APPROVE' and identity_checked != 'yes'):
            return HTMLResponse('Onay için belge kontrolünü işaretleyin; ret için açıklama girin.', status_code=400)
        with Session(m.engine, expire_on_commit=False) as session:
            initial = session.get(MembershipVerification, verification_id)
            if not initial: return HTMLResponse('Başvuru bulunamadı.', status_code=404)
            owner_id = initial.user_id
            owner_stmt = select(m.User).where(m.User.id == owner_id)
            if m.engine.dialect.name == 'postgresql': owner_stmt = owner_stmt.with_for_update()
            owner = session.exec(owner_stmt).first()
            stmt = select(MembershipVerification).where(MembershipVerification.id == verification_id)
            if m.engine.dialect.name == 'postgresql': stmt = stmt.with_for_update()
            row = session.exec(stmt.execution_options(populate_existing=True)).first()
            if not owner or not owner.is_active or not row or row.status != 'PENDING':
                return HTMLResponse('Başvuru artık incelemeye açık değil.', status_code=409)
            if decision == 'APPROVE' and (owner.display_name != row.name_snapshot or title_for(session, owner.id) != row.title_snapshot):
                return HTMLResponse('Profil bilgileri değişti. Başvuruyu reddedip yeni belge isteyin.', status_code=409)
            row.status = 'VERIFIED' if decision == 'APPROVE' else 'REJECTED'
            row.rejection_reason = reason.strip()[:1000] if decision == 'REJECT' else None
            row.reviewed_at = m._utcnow_naive(); row.reviewed_by_user_id = admin.id; session.add(row)
            session.add(m.AdminAuditLog(admin_user_id=admin.id, action='MEMBERSHIP_'+row.status, target_user_id=owner.id, detail=f'#{row.id} · {row.document_type}'))
            message = 'Öğrenci üyeliğiniz doğrulandı.' if row.document_type == 'STUDENT' else 'Üyelik belgeniz doğrulandı.'
            if decision == 'REJECT': message = 'Belgeniz onaylanmadı: ' + row.rejection_reason
            _, event, _ = m._notify_user(session, user_id=owner.id, actor_user_id=admin.id, notice_type='MEMBERSHIP_REVIEWED', title='Üyelik doğrulama sonucu', message=message, related_type='membership_verification', related_id=row.id, dedup_key=f'membership-reviewed:{row.id}', target_url='/account/verification')
            profile_event = m._record_realtime_event(session, owner.id, 'MEMBERSHIP_UPDATED', 'membership_verification', row.id, {'status': row.status})
            session.commit()
        for notice in (event, profile_event):
            if notice: m.on_loop(m._publish_realtime_event, notice)
        return RedirectResponse('/admin/member-verifications', status_code=303)
