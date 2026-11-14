"""Native academic adapters retain existing course/index/run/quiz authority."""
import inspect,json,re
from fastapi import APIRouter,BackgroundTasks,Depends,File,Form,HTTPException,Query,Response,UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field
from sqlmodel import Session,select
from starlette.concurrency import run_in_threadpool
from app.mobile_api import _mobile_access_token,_mobile_request
from app.mobile_account_api import _account_user,PlainLegal

HEADERS={'Cache-Control':'private, no-store','Vary':'Authorization'}
def _private(response:Response):response.headers.update(HEADERS)
router=APIRouter(tags=['mobile-academic'],dependencies=[Depends(_private)])

async def _call(handler,token,*args,method='POST',query=''):
    request=_mobile_request(token,method)
    request.scope['query_string']=query.encode()
    response=await handler(request,*args) if inspect.iscoroutinefunction(handler) else await run_in_threadpool(handler,request,*args)
    try:data=json.loads(response.body)
    except (AttributeError,ValueError,TypeError):data={}
    if response.headers.get('location','').startswith('/login'):raise HTTPException(401,'Oturumunuz sona ermiş.')
    if response.status_code>=400 or isinstance(data,dict) and data.get('ok') is False:
        message=data.get('error') or data.get('detail') if isinstance(data,dict) else None
        if not isinstance(message,str):
            plain=PlainLegal();plain.feed(getattr(response,'body',b'').decode('utf8',errors='replace'));message=plain.text()[:300] or 'Akademik işlem tamamlanamadı.'
        raise HTTPException(response.status_code if response.status_code>=400 else 400,message)
    return response,data

def _owned(session,user,course_id):
    from app import main as web
    result=web._owned_study_course(session,user,course_id)
    if not result:raise HTTPException(404,'Ders bulunamadı.')
    return result

def _course(c):return {'id':c.id,'title':c.title,'description':c.description,'created_at':c.created_at,'updated_at':c.updated_at}

def _workspace(user,course_id,before=None):
    from app import main as web
    with Session(web.engine) as s:
        c=_owned(s,user,course_id)
        query=select(web.StudyMaterial).where(web.StudyMaterial.course_id==course_id,web.StudyMaterial.owner_user_id==user.id)
        if before:query=query.where(web.StudyMaterial.id<before)
        rows=s.exec(query.order_by(web.StudyMaterial.id.desc()).limit(51)).all();more=len(rows)>50;rows=rows[:50]
        return {'course':_course(c),'max_file_bytes':web.STUDY_MAX_FILE_BYTES,'max_upload_count':web.STUDY_MAX_UPLOAD_COUNT,'materials':[{'id':m.id,'name':m.display_name or m.original_filename,'mime':m.mime_type,'size':m.size_bytes,'index_status':m.index_status,'created_at':m.created_at,'url':f'/api/mobile/v1/academic/courses/{course_id}/materials/{m.id}/file'} for m in rows],'next_before':rows[-1].id if more else None}

@router.get('/academic/library')
def library(q:str=Query('',max_length=120),before:int|None=Query(None,ge=1),user=Depends(_account_user)):
    from app import main as web
    from sqlalchemy import func
    with Session(web.engine) as s:
        query=select(web.StudyCourse).where(web.StudyCourse.owner_user_id==user.id)
        if q.strip():query=query.where(web.StudyCourse.title.ilike('%'+q.strip()+'%'))
        if before:query=query.where(web.StudyCourse.id<before)
        rows=s.exec(query.order_by(web.StudyCourse.id.desc()).limit(51)).all();more=len(rows)>50;rows=rows[:50];ids=[r.id for r in rows]
        counts=dict(s.exec(select(web.StudyMaterial.course_id,func.count(web.StudyMaterial.id)).where(web.StudyMaterial.owner_user_id==user.id,web.StudyMaterial.course_id.in_(ids)).group_by(web.StudyMaterial.course_id)).all()) if ids else {}
        return {'items':[{**_course(c),'material_count':counts.get(c.id,0)} for c in rows],'next_before':rows[-1].id if more else None}

class CourseInput(BaseModel):
    title:str=Field(max_length=120)
    description:str=Field(default='',max_length=500)

@router.post('/academic/library')
async def create_course(payload:CourseInput,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    response,_=await _call(web.create_study_course,token,payload.title,payload.description)
    match=re.fullmatch(r'/notes/courses/([1-9][0-9]*)',response.headers.get('location',''))
    if not match:raise HTTPException(502,'Ders oluşturma sonucu doğrulanamadı. Kütüphaneyi kontrol edin.')
    return await run_in_threadpool(_workspace,user,int(match[1]))

@router.get('/academic/courses/{course_id}/workspace')
def workspace(course_id:int,before:int|None=Query(None,ge=1),user=Depends(_account_user)):return _workspace(user,course_id,before)

@router.put('/academic/courses/{course_id}')
async def rename_course(course_id:int,payload:CourseInput,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    await _call(web.rename_study_course,token,course_id,payload.title)
    return await run_in_threadpool(_workspace,user,course_id)

@router.delete('/academic/courses/{course_id}')
async def delete_course(course_id:int,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    await _call(web.delete_study_course,token,course_id);return {'ok':True}

@router.post('/academic/courses/{course_id}/materials')
async def upload_materials(course_id:int,background_tasks:BackgroundTasks,files:list[UploadFile]=File(...),original_filename:str=Form('',max_length=240),token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    if original_filename:
        from pathlib import Path
        if len(files)!=1 or Path(original_filename).name!=original_filename or '\\' in original_filename:
            raise HTTPException(400,'Geçersiz dosya adı.')
        files[0].filename=original_filename
    await _call(web.upload_study_materials,token,course_id,background_tasks,files,False);return {'ok':True}

@router.delete('/academic/courses/{course_id}/materials/{material_id}')
async def delete_material(course_id:int,material_id:int,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    await _call(web.delete_study_material,token,course_id,material_id);return {'ok':True}

@router.get('/academic/courses/{course_id}/materials/{material_id}/file')
async def material_file(course_id:int,material_id:int,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    response,_=await _call(web.study_material_file,token,course_id,material_id,method='GET');response.headers.update(HEADERS);return response

@router.get('/academic/courses/{course_id}/index-status')
async def index_status(course_id:int,background_tasks:BackgroundTasks,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    _,data=await _call(web.study_ai_index_status,token,course_id,background_tasks,method='GET');return data

class RunInput(BaseModel):
    message:str=Field(min_length=1,max_length=8000)
    request_key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,80}$')

@router.post('/academic/courses/{course_id}/runs')
async def create_run(course_id:int,payload:RunInput,background_tasks:BackgroundTasks,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    _,data=await _call(web.study_run_create,token,course_id,background_tasks,payload.message,payload.request_key);return JSONResponse(data,status_code=202,headers=HEADERS)

@router.get('/academic/courses/{course_id}/runs/active')
async def active_run(course_id:int,background_tasks:BackgroundTasks,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    _,data=await _call(web.study_run_active,token,course_id,background_tasks,method='GET');return data

@router.get('/academic/courses/{course_id}/runs/receipt')
def run_receipt(course_id:int,request_key:str=Query(...,min_length=16,max_length=80),user=Depends(_account_user)):
    from app import main as web
    from app.academic_study_runs import StudyRun,payload
    with Session(web.engine) as s:
        _owned(s,user,course_id)
        row=s.exec(select(StudyRun).where(StudyRun.owner_user_id==user.id,StudyRun.course_id==course_id,StudyRun.request_key==request_key)).first()
        return {'ok':True,'run':payload(s,row) if row else None}

@router.get('/academic/courses/{course_id}/runs/{run_id}')
async def run_status(course_id:int,run_id:int,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    _,data=await _call(web.study_run_status,token,course_id,run_id,method='GET');return data


def _quizzes(user,course_id,message_id=None):
    from app import main as web
    from app.academic_quiz_interactions import _loaded,_public,_choice_snapshot
    with Session(web.engine) as s:
        _owned(s,user,course_id);versions=web._study_source_versions(s,user.id,course_id)
        query=select(web.StudyChatMessage).where(web.StudyChatMessage.owner_user_id==user.id,web.StudyChatMessage.course_id==course_id)
        if message_id:query=query.where(web.StudyChatMessage.id==message_id)
        rows=list(reversed(s.exec(query.order_by(web.StudyChatMessage.id.desc()).limit(40)).all()))
        history=_loaded(rows,versions);selected=_choice_snapshot(s,user.id,course_id,history);quizzes=[]
        for item in history:
            if not item.get('quiz') or str(item['mode']).endswith('_PDF'):continue
            if message_id:
                from app.academic_quiz_interactions import _saved_choices
                selected[item['id']]=_saved_choices(s,user.id,course_id,item['id'],item['quiz'],versions)
            result=_public(item['id'],item['quiz'],selected.get(item['id'],{}))
            for public,original in zip(result['questions'],item['quiz']['questions']):
                if public['result'] is not None:public.update(rationale=original['rationale'],source=original['source'],material_id=original['material_id'],page=original['page'])
            quizzes.append(result)
        return {'ok':True,'quizzes':quizzes}

@router.get('/academic/courses/{course_id}/quizzes')
def quizzes(course_id:int,user=Depends(_account_user)):return _quizzes(user,course_id)

class ChoiceInput(BaseModel):
    number:int=Field(ge=1)
    choice:str=Field(pattern=r'^[A-E]$')

@router.post('/academic/courses/{course_id}/quizzes/{message_id}/answers')
async def answer(course_id:int,message_id:int,payload:ChoiceInput,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app.academic_quiz_interactions import select_answer
    _,data=await _call(select_answer,token,course_id,message_id,payload.number,payload.choice)
    restored=await run_in_threadpool(_quizzes,user,course_id,message_id)
    return {**data,'quiz':restored['quizzes'][0] if restored['quizzes'] else None}

class VoteInput(BaseModel):vote:str=Field(pattern=r'^(like|dislike|none)$')
@router.post('/academic/courses/{course_id}/messages/{message_id}/feedback')
async def feedback(course_id:int,message_id:int,payload:VoteInput,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app.academic_quiz_interactions import save_feedback
    _,data=await _call(save_feedback,token,course_id,message_id,payload.vote);return data

@router.get('/academic/courses/{course_id}/timeline')
def timeline(course_id:int,before:int|None=Query(None,ge=1),user=Depends(_account_user)):
    from app import main as web
    from app.academic_quiz_interactions import _loaded,_public,_choice_snapshot
    from app.academic_pdf import pdf_artifact
    with Session(web.engine) as s:
        c=_owned(s,user,course_id);query=select(web.StudyChatMessage).where(web.StudyChatMessage.owner_user_id==user.id,web.StudyChatMessage.course_id==course_id)
        if before:query=query.where(web.StudyChatMessage.id<before)
        rows=s.exec(query.order_by(web.StudyChatMessage.id.desc()).limit(51)).all();more=len(rows)>50;rows=list(reversed(rows[:50]));versions=web._study_source_versions(s,user.id,course_id)
        loaded=_loaded(rows,versions);choices=_choice_snapshot(s,user.id,course_id,loaded);items=[]
        for row,item in zip(rows,loaded):
            try:evidence=json.loads(row.source_evidence_json or 'null')
            except (ValueError,TypeError):evidence=None
            is_quiz=bool(item.get('quiz'));stale=isinstance(evidence,dict) and 'quiz' in evidence and not is_quiz
            public=_public(row.id,item['quiz'],choices.get(row.id,{})) if is_quiz else None
            if public:
                for question,original in zip(public['questions'],item['quiz']['questions']):
                    if question['result'] is not None:question.update(rationale=original['rationale'],source=original['source'])
            pdf=str(row.mode).endswith('_PDF');sources=evidence.get('sources',[]) if isinstance(evidence,dict) else evidence if isinstance(evidence,list) else []
            sources=[{k:v for k,v in source.items() if k in {'material_id','page','page_start','page_end','display_name','title','filename','quote','label','url'}} for source in sources if isinstance(source,dict)] if isinstance(sources,list) else []
            items.append({'id':row.id,'role':row.role,'content':'' if is_quiz or pdf else 'Kaynaklar değiştiği için bu soru seti yeniden doğrulanmalı.' if stale else row.content,'created_at':row.created_at,'quiz':public,'quiz_stale':stale,'artifact':pdf_artifact(course_id,row.id,c.title,content=row.content) if pdf else None,'sources':sources,'vote':evidence.get('user_feedback') if isinstance(evidence,dict) else None})
        return {'items':items,'next_before':rows[0].id if more else None}

@router.get('/academic/courses/{course_id}/messages/{message_id}/pdf')
async def answer_pdf(course_id:int,message_id:int,part:int=Query(0,ge=0),token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    response,_=await _call(web.study_answer_pdf,token,course_id,message_id,part,method='GET');response.headers.update(HEADERS);return response


@router.get('/academic/courses/{course_id}/learning')
async def learning(course_id:int,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    _,data=await _call(web.study_learning_status,token,course_id,method='GET');return data

@router.delete('/academic/courses/{course_id}/timeline')
async def clear_history(course_id:int,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    await _call(web.clear_study_ai_chat,token,course_id);return {'ok':True}

@router.get('/academic/courses/{course_id}/materials/{material_id}/pages/{page}/text')
async def source_page(course_id:int,material_id:int,page:int,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    from app import main as web
    if page<1:raise HTTPException(400,'Geçersiz sayfa.')
    _,data=await _call(web.study_material_page_text,token,course_id,material_id,page,method='GET',query='format=json');return data
