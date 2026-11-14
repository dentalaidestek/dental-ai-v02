"""Native account UI adapters; canonical web handlers retain their security rules."""
import inspect
import re
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from typing import Optional

from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field
from sqlmodel import Session,select
from starlette.concurrency import run_in_threadpool
from app.mobile_api import _mobile_user,_mobile_access_token,_mobile_request,_user_payload,MobileToken

router=APIRouter(tags=['mobile-account'])

class PlainLegal(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'h1','h2','h3','p','li','br'}:self.parts.append('\n\n' if tag!='li' else '\n• ')
    def handle_data(self,data):self.parts.append(data)
    def text(self):return re.sub(r'[ \t]+',' ',''.join(self.parts)).strip()

@router.get('/auth/options')
def mobile_auth_options():
    from app import main as web
    agreements=[]
    for key in ('terms','kvkk','clinical'):
        legal=web.LEGAL_TEXTS[key];plain=PlainLegal();plain.feed(legal['content'])
        agreements.append({'key':key,'title':legal['title'],'text':plain.text()})
    return {'professional_titles':sorted(web.PROFESSIONAL_TITLES),'legal_version':web.LEGAL_VERSION,'agreements':agreements}

def _response(response):
    context=getattr(response,'context',{})
    location=response.headers.get('location','')
    if location.startswith('/login') and 'reset=success' not in location and 'email_changed=1' not in location:
        raise HTTPException(status_code=401,detail='Oturum geçersiz veya süresi dolmuş.')
    if response.status_code>=400 or context.get('error'):
        message=context.get('error')
        if not isinstance(message,str):
            raw=getattr(response,'body',b'').decode('utf-8',errors='replace')
            message=raw[:300] if raw and '<' not in raw else 'İşlem tamamlanamadı.'
        raise HTTPException(status_code=response.status_code if response.status_code>=400 else 400,detail=message)
    return context

async def _invoke(handler,request,*args):
    response=await handler(request,*args) if inspect.iscoroutinefunction(handler) else await run_in_threadpool(handler,request,*args)
    _response(response)
    return response

class Registration(BaseModel):
    display_name:str=Field(max_length=120)
    email:str=Field(max_length=254)
    username:str=Field(max_length=80)
    password:str=Field(max_length=1024)
    university:str=Field(max_length=250)
    professional_title:str=Field(max_length=80)
    specialty:str=Field(default='',max_length=250)
    legal_version:str=Field(default='',max_length=80)
    accept_terms:bool=False
    kvkk_informed:bool=False
    accept_clinical:bool=False

@router.post('/auth/register',response_model=MobileToken)
def mobile_register(payload:Registration,request:Request):
    from app import main as web
    if payload.legal_version!=web.LEGAL_VERSION:raise HTTPException(status_code=409,detail='Hukuki metinler güncellendi. Kayıt ekranını yeniden açıp güncel metinleri okuyun.')
    response=web.register_user(request,payload.display_name,payload.email,payload.username,payload.password,payload.university,payload.professional_title,payload.specialty,'1' if payload.accept_terms else None,'1' if payload.kvkk_informed else None,'1' if payload.accept_clinical else None)
    _response(response)
    if response.status_code!=303:raise HTTPException(status_code=502,detail='Kayıt doğrulanamadı. Giriş ekranından hesabınızı kontrol edin.')
    # Registration creates a browser session in the canonical handler. Never
    # expose or leave that unverified session behind in the native flow.
    cookies=SimpleCookie()
    for header in response.headers.getlist('set-cookie'):cookies.load(header)
    browser_token=cookies.get(web.SESSION_COOKIE)
    with Session(web.engine,expire_on_commit=False) as session:
        if browser_token:
            row=session.exec(select(web.SessionToken).where(web.SessionToken.token_hash==web.hash_session_token(browser_token.value))).first()
            if row:session.delete(row);session.commit()
        user=session.exec(select(web.User).where(web.User.username==payload.username.strip().lower())).first()
        if not user or user.email_verified_at:raise HTTPException(status_code=409,detail='Kayıt durumunu giriş ekranından kontrol edin.')
        try:challenge=web._ensure_email_verification_challenge(session,user)
        except Exception:raise HTTPException(status_code=503,detail='Hesap oluşturuldu; doğrulama kodu gönderilemedi. Giriş ekranından kodu yeniden isteyin.')
        return MobileToken(expires_at=challenge.expires_at,challenge_token=challenge.public_token)

class RecoveryEmail(BaseModel):email:str=Field(max_length=254)
class RecoveryPassword(BaseModel):
    token:str=Field(min_length=1,max_length=512)
    password:str=Field(max_length=1024)
    password_confirm:str=Field(max_length=1024)

@router.post('/auth/forgot-password')
def mobile_forgot(payload:RecoveryEmail,request:Request):
    from app import main as web
    response=web.forgot_password_request(request,payload.email);_response(response)
    return {'ok':True,'message':'Eğer bu e-posta adresi kayıtlıysa, şifre sıfırlama bağlantısı gönderilecektir.'}

@router.post('/auth/reset-password')
def mobile_reset(payload:RecoveryPassword,request:Request):
    from app import main as web
    response=web.reset_password(request,payload.token,payload.password,payload.password_confirm);_response(response)
    if response.status_code!=303:raise HTTPException(status_code=502,detail='Şifre değişikliği doğrulanamadı. Giriş ekranından kontrol edin.')
    return {'ok':True,'requires_login':True}

def _account_user(token:str=Depends(_mobile_access_token),user=Depends(_mobile_user)):
    from app import main as web
    if user.role=='ADMIN' and web.get_current_user(_mobile_request(token,'GET')) is None:
        raise HTTPException(status_code=403,detail='Yönetici oturumu için güvenlik doğrulaması gerekiyor.')
    return user

@router.get('/account')
def mobile_account(token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    with Session(web.engine,expire_on_commit=False) as session:
        live=session.get(web.User,user.id)
        meta=session.exec(select(web.UserAccountMeta).where(web.UserAccountMeta.user_id==user.id)).first()
        next_change=meta.username_changed_at+web.timedelta(days=15) if meta and meta.username_changed_at else None
        return {'user':_user_payload(session,live),'next_username_change_at':next_change,'email_change_allowed':live.role!='ADMIN','photo_url':f'/api/mobile/v1/account/photo/{live.id}?v={web._profile_photo_version(live.profile_photo_path)}' if live.profile_photo_path else None}


@router.get('/account/photo/{user_id}')
def mobile_account_photo(user_id:int,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    if user_id!=user.id:raise HTTPException(status_code=404,detail='Profil fotoğrafı bulunamadı.')
    response=web.profile_photo(_mobile_request(token,'GET'),user_id)
    _response(response)
    response.headers['Cache-Control']='private, no-store'
    return response

class Name(BaseModel):display_name:str=Field(max_length=120)
class Username(BaseModel):username:str=Field(max_length=80)
class PasswordChange(BaseModel):
    current_password:str=Field(max_length=1024)
    new_password:str=Field(max_length=1024)
    new_password_confirm:str=Field(max_length=1024)
class EmailChange(BaseModel):
    new_email:str=Field(max_length=254)
    password:str=Field(max_length=1024)
    renew:bool=False
class EmailCode(BaseModel):code:str=Field(max_length=6)
class Photo(BaseModel):profile_photo_data:str=Field(max_length=15000000)

@router.post('/account/display-name')
async def mobile_name(payload:Name,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    await _invoke(web.change_display_name,_mobile_request(token),payload.display_name)
    return {'ok':True}

@router.post('/account/username')
async def mobile_username(payload:Username,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    await _invoke(web.change_username,_mobile_request(token),payload.username)
    return {'ok':True}

@router.post('/account/password')
async def mobile_password(payload:PasswordChange,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    response=await _invoke(web.change_password,_mobile_request(token),payload.current_password,payload.new_password,payload.new_password_confirm)
    if not getattr(response,'context',{}).get('success'):raise HTTPException(status_code=502,detail='Şifre değişikliği doğrulanamadı.')
    return {'ok':True,'requires_login':True}

@router.post('/account/email')
async def mobile_begin_email(payload:EmailChange,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    response=await _invoke(web.begin_email_change,_mobile_request(token),payload.new_email,payload.password,'1' if payload.renew else '')
    pending=getattr(response,'context',{}).get('email_change_pending')
    if not pending:raise HTTPException(status_code=502,detail='E-posta doğrulama isteği doğrulanamadı.')
    return {'ok':True,'pending_email':pending}

@router.post('/account/email/confirm')
async def mobile_confirm_email(payload:EmailCode,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    response=await _invoke(web.confirm_email_change,_mobile_request(token),payload.code)
    if response.headers.get('location')!='/login?email_changed=1':raise HTTPException(status_code=502,detail='E-posta değişikliği doğrulanamadı.')
    return {'ok':True,'requires_login':True}

@router.post('/account/profile-photo')
async def mobile_photo(payload:Photo,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    await _invoke(web.account_profile_photo,_mobile_request(token),payload.profile_photo_data)
    return {'ok':True}
