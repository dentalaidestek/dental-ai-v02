"""Native clinical review reuses the web result, source identity and durable queue."""
import inspect
import json
import re
from fastapi import APIRouter,BackgroundTasks,Depends,HTTPException,Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field,field_validator
from sqlmodel import Session,select
from starlette.concurrency import run_in_threadpool
from app.mobile_account_api import _account_user
from app.mobile_api import _mobile_access_token,_mobile_request
from app.work_jobs import WorkJob

HEADERS={'Cache-Control':'private, no-store','Vary':'Authorization'}
def _private(response:Response):response.headers.update(HEADERS)
router=APIRouter(tags=['mobile-clinical'],dependencies=[Depends(_private)])
FDI=r'(?:[1-4][1-8]|[5-8][1-5])'

def _owned(s,user,ident):
    from app import main as web
    a=s.get(web.Analysis,ident);p=s.get(web.Patient,a.patient_id) if a else None
    if not a or not p or user.role!='ADMIN' and p.owner_user_id!=user.id:raise HTTPException(404,'Analiz bulunamadı.')
    return a,p

def _result(a):
    from app import main as web
    try:
        path=web.storage_ensure_local(web._result_reference(a))
        result=json.loads(path.read_text(encoding='utf8')).get('ai_result')
    except FileNotFoundError:return None
    except (OSError,ValueError,TypeError,AttributeError):raise HTTPException(502,'Kaydedilmiş analiz sonucu okunamadı.')
    if result is not None and not isinstance(result,dict):raise HTTPException(502,'Kaydedilmiş klinik sonuç geçersiz.')
    return result

def _job(j):
    return {'id':j.id,'kind':j.kind,'status':j.status,'retryable':j.status=='FAILED' or j.status=='CANCELLED' and j.error_code=='USER_CANCELLED'} if j else None

def _latest(s,ident):return s.exec(select(WorkJob).where(WorkJob.resource_type=='ANALYSIS',WorkJob.resource_id==ident,WorkJob.kind.in_(['VISION','PRELIMINARY','FINAL'])).order_by(WorkJob.id.desc()).limit(1)).first()

@router.get('/analyses/{analysis_id}/clinical')
def clinical(analysis_id:int,user=Depends(_account_user)):
    from app import main as web
    from app.work_jobs import source_identity
    with Session(web.engine) as s:
        a,p=_owned(s,user,analysis_id);_,_,revision=source_identity(s,'FINAL','ANALYSIS',analysis_id)
        return {'analysis_id':a.id,'patient_id':p.id,'status':a.status,'clinical_notes':a.clinical_notes,'tooth_number':a.tooth_number,'revision':revision,'result':_result(a),'job':_job(_latest(s,a.id)),'assets':[{'id':x.id,'name':x.original_filename,'image_type':x.image_type,'has_vision':bool(x.vision_snapshot_json),'url':f'/api/mobile/v1/analyses/{a.id}/assets/{x.id}'} for x in s.exec(select(web.ImageAsset).where(web.ImageAsset.analysis_id==a.id).order_by(web.ImageAsset.id)).all()]}

class FinalInput(BaseModel):
    revision:str=Field(pattern=r'^[0-9a-f]{64}$')
    answers:dict[str,str]
    @field_validator('answers')
    @classmethod
    def valid_answers(cls,values):
        if len(values)>3 or any(not re.fullmatch(r'answer_[0-2]',key) or not value.strip() or len(value)>2000 for key,value in values.items()):raise ValueError('Bütün klinik sorulara geçerli cevap verin.')
        return {key:value.strip() for key,value in values.items()}

@router.post('/analyses/{analysis_id}/final-review')
def final_review(analysis_id:int,payload:FinalInput,user=Depends(_account_user)):
    from app import main as web
    from app.work_jobs import source_identity
    with Session(web.engine,expire_on_commit=False) as s:
        a,_=_owned(s,user,analysis_id)
        # A receipt is recognized even after FINAL replaces the preliminary result.
        serialized=json.dumps(payload.answers,sort_keys=True,ensure_ascii=False)
        previous=s.exec(select(WorkJob).where(WorkJob.resource_type=='ANALYSIS',WorkJob.resource_id==a.id,WorkJob.kind=='FINAL',WorkJob.source_hash==payload.revision,WorkJob.payload_json==serialized).order_by(WorkJob.id.desc()).limit(1)).first()
        if previous:return JSONResponse({'ok':True,'job':_job(previous)},status_code=202,headers=HEADERS)
        _,_,revision=source_identity(s,'FINAL','ANALYSIS',a.id,lock=True)
        if revision!=payload.revision:raise HTTPException(409,'Hasta veya analiz bilgileri değişti. Sonucu yenileyip klinik cevapları kontrol edin.')
        result=_result(a) or {};questions=result.get('questions')
        if a.status!='AI_ANALYZED' or result.get('status') not in {'INITIAL','ANALYSIS_COMPLETE'} or not isinstance(questions,list) or not questions:raise HTTPException(409,'Hekim değerlendirmesine hazır ön sonuç bulunmuyor.')
        if set(payload.answers)!={f'answer_{i}' for i in range(len(questions))}:raise HTTPException(422,'Bütün klinik soruları cevaplayın.')
        j=web._enqueue_work(s,'FINAL','ANALYSIS',a.id,payload=payload.answers);s.commit()
        return JSONResponse({'ok':True,'job':_job(j)},status_code=202,headers=HEADERS)

async def _web(handler,token,*args,body=None):
    req=_mobile_request(token)
    if body is not None:req._body=json.dumps(body).encode()
    response=await handler(req,*args) if inspect.iscoroutinefunction(handler) else await run_in_threadpool(handler,req,*args)
    if response.status_code>=400:
        raise HTTPException(response.status_code,'Klinik işlem tamamlanamadı. Analiz erişimini ve işlem durumunu kontrol edin.')
    return response

class NoteInput(BaseModel):
    tooth:str=Field(default='',max_length=2)
    note:str=Field(default='',max_length=2000)
    finding:str=Field(default='',max_length=500)
    @field_validator('tooth')
    @classmethod
    def valid_tooth(cls,v):
        if v and not re.fullmatch(FDI,v):raise ValueError('Geçersiz FDI diş numarası.')
        return v

@router.post('/analyses/{analysis_id}/clinical-note')
async def note(analysis_id:int,payload:NoteInput,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    if not payload.note.strip() and not payload.finding.strip():raise HTTPException(422,'Not veya bulgu yazın.')
    await _web(web.save_viewer_finding if payload.finding.strip() else web.save_analysis_viewer_note,token,analysis_id,body=payload.model_dump());return {'ok':True}

class TeethInput(BaseModel):
    teeth:list[str]=Field(min_length=1,max_length=32)
    @field_validator('teeth')
    @classmethod
    def valid_teeth(cls,v):
        if len(set(v))!=len(v) or any(not re.fullmatch(FDI,tooth) for tooth in v):raise ValueError('Geçersiz veya yinelenen FDI diş numarası.')
        return v

@router.post('/analyses/{analysis_id}/selected-teeth')
async def selected_teeth(analysis_id:int,payload:TeethInput,background_tasks:BackgroundTasks,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    await _web(web.viewer_analyze,token,analysis_id,background_tasks,body=payload.model_dump())
    with Session(web.engine) as s:
        _owned(s,user,analysis_id);return JSONResponse({'ok':True,'job':_job(_latest(s,analysis_id))},status_code=202,headers=HEADERS)

@router.post('/analyses/{analysis_id}/jobs/{job_id}/{action}')
async def job_action(analysis_id:int,job_id:int,action:str,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    if action not in {'retry','cancel'}:raise HTTPException(404,'İşlem bulunamadı.')
    def owned():
        with Session(web.engine) as s:
            _owned(s,user,analysis_id);j=s.get(WorkJob,job_id)
            if not j or j.resource_type!='ANALYSIS' or j.resource_id!=analysis_id or j.kind not in {'VISION','PRELIMINARY','FINAL'}:raise HTTPException(404,'Analiz işi bulunamadı.')
    await run_in_threadpool(owned)
    await _web(web.retry_work if action=='retry' else web.cancel_work,token,job_id);return {'ok':True}

@router.get('/analyses/{analysis_id}/assets/{asset_id}/vision')
async def asset_vision(analysis_id:int,asset_id:int,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    response=await run_in_threadpool(web.analysis_asset_vision,_mobile_request(token,'GET'),analysis_id,asset_id)
    response.headers.update(HEADERS)
    return response
