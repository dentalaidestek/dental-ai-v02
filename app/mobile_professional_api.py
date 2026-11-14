"""Native profile/document adapters. Web handlers own review and permission rules."""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool
from app.mobile_api import _mobile_access_token, _mobile_request
from app.mobile_account_api import _account_user, _invoke
from app.membership_verification import DOCUMENT_TYPES, state, validate_document
from app.profile_hub import EXPERT_TITLES

router=APIRouter(tags=['mobile-professional'])


def _web_handler(path):
    from app import main as web
    return next(route.endpoint for route in web.app.routes if getattr(route,'path',None)==path and 'POST' in getattr(route,'methods',set()))


@router.get('/account/professional')
def professional(token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    with Session(web.engine,expire_on_commit=False) as s:
        live=s.get(web.User,user.id)
        meta=s.exec(select(web.UserAccountMeta).where(web.UserAccountMeta.user_id==user.id)).first()
        title=meta.professional_title if meta else ''
        profile=s.exec(select(web.ExpertProfile).where(web.ExpertProfile.user_id==user.id)).first()
        pending=s.exec(select(web.ExpertTitleChange).where(web.ExpertTitleChange.user_id==user.id,web.ExpertTitleChange.status.in_(['AWAITING_DOCUMENT','PENDING_REVIEW','REJECTED'])).order_by(web.ExpertTitleChange.created_at.desc()).limit(1)).first()
        expert=None if not profile else {key:getattr(profile,key) for key in ('specialty','phone','phone_verified','institution','bio','orcid_url','publications_text','consultation_price','availability','application_status','verification_status','specialty_verified','academic_title_verified','credential_document_name')}
        return {'current_title':title or '', 'titles':sorted(web.PROFESSIONAL_TITLES), 'eligible':title in EXPERT_TITLES,
                'membership':state(s,live),'document_types':[{'key':key,'label':value[0],'description':value[1]} for key,value in DOCUMENT_TYPES.items()],
                'title_change':None if not pending else {'requested_title':pending.requested_title,'status':pending.status,'reason':pending.rejection_reason,'document_name':pending.credential_document_name},
                'expert':expert,'specialties':list(web.EXPERT_SPECIALTIES),'minimum_price':web._expert_minimum_price(title),
                'has_photo':bool(live.profile_photo_path),'sms_enabled':web._sms_provider_enabled()}


class TitleChange(BaseModel):
    professional_title:str=Field(max_length=80)
    confirm_change:bool=False


@router.post('/account/professional-title')
async def title_change(payload:TitleChange,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    await _invoke(web.change_professional_title,_mobile_request(token),payload.professional_title,'yes' if payload.confirm_change else '')
    return {'ok':True,'professional':await run_in_threadpool(professional,token,user)}


async def _check_file(file:UploadFile,max_bytes:int):
    raw=await file.read(max_bytes+1)
    try:await run_in_threadpool(validate_document,file.filename or '',raw,max_bytes=max_bytes)
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc))
    await file.seek(0)


@router.post('/account/documents/{purpose}')
async def document_upload(purpose:Literal['membership','title','expert'],file:UploadFile=File(...),document_type:str=Form(''),consent:str=Form(''),token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    await _check_file(file,(5 if purpose=='membership' else 10)*1024*1024)
    if purpose=='membership':
        await _invoke(_web_handler('/account/verification'),_mobile_request(token),document_type,consent,file)
    elif purpose=='title':
        await _invoke(web.professional_title_document_upload,_mobile_request(token),file)
    else:
        await _invoke(_web_handler('/account/documents/expert'),_mobile_request(token),file)
    return {'ok':True,'professional':await run_in_threadpool(professional,token,user)}


@router.post('/account/expert-profile')
async def expert_save(specialty:str=Form(...),phone:str=Form(...),consultation_price:int=Form(...),institution:str=Form(''),bio:str=Form(''),orcid_url:str=Form(''),publications_text:str=Form(''),file:Optional[UploadFile]=File(None),token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    # Reject eligibility before processing a potentially large credential.
    current=await run_in_threadpool(professional,token,user)
    if not current['eligible']:raise HTTPException(status_code=403,detail='Bu mesleki unvan uzman danışman başvurusu yapamaz.')
    if file:await _check_file(file,10*1024*1024)
    await _invoke(web.expert_support_profile_save,_mobile_request(token),specialty,phone,institution,bio,orcid_url,publications_text,consultation_price,'PASSIVE','',file)
    return {'ok':True,'professional':await run_in_threadpool(professional,token,user)}


@router.get('/account/expert-rules')
def expert_rules(token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    import re
    from app import main as web
    from app.mobile_account_api import PlainLegal
    source=web.templates.env.loader.get_source(web.templates.env,'expert_rules.html')[0]
    parts=re.findall(r'<section class="expert-rule-card">(.*?)</section>',source,re.S)
    if not parts:raise HTTPException(status_code=503,detail='Güncel vaka kuralları alınamadı.')
    plain=PlainLegal();plain.feed('\n'.join(parts))
    with Session(web.engine) as s:
        policy=s.exec(select(web.ExpertPolicyState).where(web.ExpertPolicyState.expert_user_id==user.id)).first()
        return {'version':web.EXPERT_RULES_VERSION,'text':plain.text(),'accepted':bool(policy and policy.rules_version==web.EXPERT_RULES_VERSION and policy.rules_accepted_at),'blocked_until':policy.new_case_blocked_until if policy else None}


class RulesAcceptance(BaseModel):
    version:str=Field(max_length=80)
    accepted:bool=False


@router.post('/account/expert-rules')
async def accept_rules(payload:RulesAcceptance,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    if not payload.accepted:raise HTTPException(status_code=400,detail='Güncel kuralları okuyup onaylayın.')
    await _invoke(web.expert_support_rules_accept,_mobile_request(token),payload.version,'/expert-support/profile')
    return {'ok':True}


class Availability(BaseModel):
    availability:Literal['AVAILABLE','BUSY']


@router.post('/account/expert-availability')
async def availability(payload:Availability,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    import json
    from app import main as web
    from starlette.concurrency import run_in_threadpool
    # Canonical handler reads JSON on the event loop inside its offloaded worker.
    request=_mobile_request(token);request._json={'availability':payload.availability}
    handler=web.expert_support_availability_update
    import inspect
    response=await handler(request) if inspect.iscoroutinefunction(handler) else await run_in_threadpool(handler,request)
    result=json.loads(response.body)
    if response.status_code>=400 or result.get('ok') is not True:raise HTTPException(status_code=response.status_code if response.status_code>=400 else 502,detail=result.get('detail','Müsaitlik güncellenemedi.'))
    return {'ok':True,'professional':await run_in_threadpool(professional,token,user)}
