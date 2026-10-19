"""Durable, event-woken study requests. No idle API calls or automatic paid retries."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
from sqlalchemy import UniqueConstraint,update,func
from sqlmodel import SQLModel,Field,Session,select
from app.academic_learning import now,get_or_create_state,state


class StudyRun(SQLModel,table=True):
    __table_args__=(UniqueConstraint('owner_user_id','course_id','request_key'),)
    id:int|None=Field(default=None,primary_key=True)
    owner_user_id:int=Field(index=True)
    course_id:int=Field(index=True)
    request_key:str
    epoch:str
    question:str
    status:str=Field(default='QUEUED',index=True)
    stage:str='Sırada'
    partial_text:str=''
    assistant_message_id:int|None=None
    error:str|None=None
    created_at:datetime=Field(default_factory=now)
    updated_at:datetime=Field(default_factory=now)


_pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='academic-study')
_lock=threading.Lock()
_running={}


def enqueue(session,*,owner,course,question,key):
    if session.get_bind().dialect.name=='postgresql':
        from sqlalchemy import text
        session.execute(text('SELECT pg_advisory_xact_lock(:owner,:course)'),{'owner':owner,'course':course})
    existing=session.exec(select(StudyRun).where(StudyRun.owner_user_id==owner,
        StudyRun.course_id==course,StudyRun.request_key==key)).first()
    if existing:
        if existing.question!=question:raise ValueError('İstek anahtarı başka bir çalışma için kullanılmış.')
        return existing
    active=session.exec(select(StudyRun).where(StudyRun.owner_user_id==owner,
        StudyRun.status.in_(['QUEUED','RUNNING']))).all()
    if any(row.course_id==course for row in active) or len(active)>=2:
        raise ValueError('Önce devam eden çalışmanın bitmesini bekle.')
    if session.exec(select(func.count()).select_from(StudyRun).where(StudyRun.status=='QUEUED')).one()>=64:
        raise ValueError('Çalışma sırası dolu. Kısa süre sonra tekrar dene.')
    current=get_or_create_state(session,owner,course)
    run=StudyRun(owner_user_id=owner,course_id=course,request_key=key,epoch=current.epoch,question=question)
    session.add(run);session.flush()
    return run


def claim(engine):
    with Session(engine,expire_on_commit=False) as session:
        row=session.exec(select(StudyRun).where(StudyRun.status=='QUEUED')
            .order_by(StudyRun.created_at,StudyRun.id).with_for_update(skip_locked=True).limit(1)).first()
        if row is None:return None
        row.status='RUNNING';row.stage='Kaynaklar hazırlanıyor';row.updated_at=now()
        session.add(row);session.commit();return row


def complete_in_transaction(session,*,run_id,owner,course,message_id):
    row=session.exec(select(StudyRun).where(StudyRun.id==run_id,StudyRun.owner_user_id==owner,
        StudyRun.course_id==course).with_for_update()).first()
    current=state(session,owner,course)
    if row is None or row.status!='RUNNING' or not current or row.epoch!=current.epoch:
        raise ValueError('Çalışma iptal edildi veya sohbet değişti.')
    row.status='DONE';row.stage='Tamamlandı';row.assistant_message_id=message_id
    row.partial_text='';row.updated_at=now();session.add(row)


def checkpoint(engine,run_id,*,stage,partial=None):
    values={'stage':stage,'updated_at':now()}
    if partial is not None:values['partial_text']=partial[:24000]
    with Session(engine) as session:
        changed=session.execute(update(StudyRun).where(StudyRun.id==run_id,
            StudyRun.status=='RUNNING').values(**values)).rowcount
        session.commit()
    if not changed:raise ValueError('Çalışma artık etkin değil.')


def generation(engine,run_id,iterator,*,pdf=False):
    checkpoint(engine,run_id,stage='PDF hazırlanıyor' if pdf else 'Yanıt hazırlanıyor')
    collected='';last=time.monotonic()
    for part in iterator:
        collected+=part
        if time.monotonic()-last>=2:
            hidden=pdf or collected.startswith('<!--ACADEMIC_') or len(collected)>12000
            checkpoint(engine,run_id,stage='PDF hazırlanıyor' if hidden else 'Yanıt hazırlanıyor',
                partial='' if hidden else collected)
            last=time.monotonic()
        yield part


def _drain(engine):
    from app import main
    from starlette.requests import Request
    from starlette.background import BackgroundTasks
    while True:
        run=claim(engine)
        if run is None:return
        try:
            with Session(engine) as session:
                user=session.get(main.User,run.owner_user_id)
                current=state(session,run.owner_user_id,run.course_id)
                if not user or not user.is_active or not current or current.epoch!=run.epoch:
                    raise ValueError('Çalışmaya erişim artık geçerli değil.')
                session.expunge(user)
            request=Request({'type':'http','headers':[], 'state':{'academic_run_id':run.id}})
            background=BackgroundTasks()
            # Executor threads do not inherit the HTTP storage-reader scope.
            # Pin downloaded files for this job only, including its background
            # tasks, then release readers before claiming another job.
            from app.object_cache import scope
            with scope():
                response=main._run_owned_study_request(request,run.course_id,background,run.question,user=user)
                if background.tasks:
                    import asyncio
                    asyncio.run(background())
            payload=json.loads(response.body)
            with Session(engine) as session:
                row=session.get(StudyRun,run.id)
                if row is not None and row.status=='RUNNING':
                    row.status='FAILED';row.error=payload.get('error','Çalışma tamamlanamadı. Yeniden deneyebilirsin.')
                    row.stage='Tamamlanamadı';row.partial_text='';row.updated_at=now();session.add(row);session.commit()
        except Exception:
            # Do not store provider/user exception text or restart a paid call.
            with Session(engine) as session:
                row=session.get(StudyRun,run.id)
                if row is not None and row.status=='RUNNING':
                    row.status='FAILED';row.error='Çalışma tamamlanamadı. Önceki kayıtların korunuyor.'
                    row.partial_text='';row.updated_at=now();session.add(row);session.commit()


def wake(engine):
    key=id(engine)
    with _lock:
        futures=[future for future in _running.get(key,[]) if not future.done()]
        added=[]
        while len(futures)<2:
            future=_pool.submit(_drain,engine);futures.append(future);added.append(future)
        _running[key]=futures
    def finished(future):
        try:
            with Session(engine) as session:
                pending=session.exec(select(StudyRun.id).where(StudyRun.status=='QUEUED').limit(1)).first()
            if pending:wake(engine)
        except Exception:pass
    for future in added:future.add_done_callback(finished)


def recover(engine):
    # Interrupted work is visible and needs an explicit retry, never silently billed again.
    with Session(engine) as session:
        session.execute(update(StudyRun).where(StudyRun.status=='RUNNING',
            StudyRun.updated_at<now()-timedelta(minutes=15)).values(status='INTERRUPTED',
            error='Sunucu yeniden başladı. Çalışma otomatik tekrarlanmadı; yeniden gönderebilirsin.',partial_text=''))
        session.commit()
    wake(engine)


def erase(session,owner,course=None,*,purge=False):
    from sqlalchemy import delete
    query=delete(StudyRun) if purge else update(StudyRun).values(status='CANCELLED',partial_text='',question='',
        error='Sohbet temizlendi.')
    query=query.where(StudyRun.owner_user_id==owner)
    if course is not None:query=query.where(StudyRun.course_id==course)
    session.execute(query)


def payload(session,row):
    if row.status=='RUNNING' and row.updated_at<now()-timedelta(minutes=15):
        row.status='INTERRUPTED';row.partial_text=''
        row.error='Çalışma kesildi. Otomatik tekrarlanmadı; yeniden gönderebilirsin.'
        session.add(row);session.commit()
    result={'id':row.id,'status':row.status,'stage':row.stage,'question':row.question,
        'partial':row.partial_text,'error':row.error}
    if row.status=='DONE':
        from app import main
        from app.academic_pdf import pdf_artifact
        message=session.exec(select(main.StudyChatMessage).where(main.StudyChatMessage.id==row.assistant_message_id,
            main.StudyChatMessage.owner_user_id==row.owner_user_id,main.StudyChatMessage.course_id==row.course_id)).first()
        if message is None:return {**result,'status':'CANCELLED','error':'Çalışmanın sohbet kaydı artık mevcut değil.'}
        automatic='_LONG_PDF' in message.mode;updated='_EDITED_PDF' in message.mode
        result['answer']=('Yanıt çok uzun olduğu için PDF şeklinde oluşturulmuştur.' if automatic else
            'İstediğin değişiklikler uygulanarak PDF güncellendi.' if updated else 'İstediğin PDF hazır.') if message.mode.endswith('_PDF') else message.content
        result['message_id']=message.id
        if message.mode.endswith('_PDF'):
            result['artifact']=pdf_artifact(row.course_id,message.id,'Ders notları',content=message.content,
                automatic=automatic,updated=updated)
    return result
