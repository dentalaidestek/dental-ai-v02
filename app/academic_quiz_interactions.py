"""Owned, deterministic quiz selection. Reuses stored keys; never calls a model."""
import re
import json
from types import SimpleNamespace
from fastapi import APIRouter,Form,Request
from fastapi.responses import JSONResponse
from sqlmodel import Session,select
from sqlalchemy import or_
from app.academic_learning import StudyAttempt,stamp,remember,get_or_create_state
from app.academic_quiz import restore_quizzes,is_quiz_turn

router=APIRouter()
_HEADERS='| Soru | Yanıtın | Anahtar | Sonuç |\n|---|---|---|---|'
_ROW=re.compile(r'^\|\s*(\d+)\s*\|\s*([A-E])\s*\|\s*([A-E])\s*\|\s*(?:Doğru|Yanlış)\s*\|$',re.M)


def _loaded(rows,versions):
    history=[{'id':row.id,'role':row.role,'content':row.content,'mode':row.mode} for row in rows]
    restore_quizzes(history,rows,versions)
    return history


def _choice_snapshot(session,owner,course,history):
    """One bounded attempt read for all visible sets, not one query per option."""
    quizzes={};receipts=[];current=None
    for item in history:
        if str(item.get('role','')).upper()!='ASSISTANT':continue
        if item.get('quiz'):
            current=item;quizzes[item['id']]=item['quiz'];continue
        if is_quiz_turn(item):current=None
        if not current or not item['content'].lstrip().startswith(_HEADERS):continue
        quiz=current['quiz']
        choices={int(n):choice for n,choice,key in _ROW.findall(item['content'])
                 if 1<=int(n)<=len(quiz['questions']) and quiz['questions'][int(n)-1]['correct']==key}
        if choices:
            key=stamp([current['id'],sorted(choices.items()),[]])
            receipts.append((key,current['id'],choices))
    if not quizzes:return {}
    filters=[StudyAttempt.attempt_key.startswith(f'tap:{mid}:') for mid in quizzes]
    if receipts:filters.append(StudyAttempt.attempt_key.in_([key for key,_,_ in receipts]))
    keys=set(session.exec(select(StudyAttempt.attempt_key).where(
        StudyAttempt.owner_user_id==owner,StudyAttempt.course_id==course,or_(*filters))).all())
    selected={mid:{} for mid in quizzes}
    for key in keys:
        if not key.startswith('tap:'):continue
        try:
            _,mid,n,choice=key.split(':');mid=int(mid);n=int(n)
            if mid in quizzes and 1<=n<=len(quizzes[mid]['questions']) and len(choice)==1 and choice in 'ABCDE':
                selected[mid][n]=choice
        except (ValueError,TypeError):continue
    for key,mid,choices in receipts:
        if key in keys:
            for n,choice in choices.items():selected[mid].setdefault(n,choice)
    return selected


def _saved_choices(session,owner,course,message_id,quiz,versions):
    from app import main
    rows=session.exec(select(main.StudyChatMessage).where(
        main.StudyChatMessage.owner_user_id==owner,main.StudyChatMessage.course_id==course,
        main.StudyChatMessage.role=='ASSISTANT',main.StudyChatMessage.id>message_id)
        .order_by(main.StudyChatMessage.id).limit(100)).all()
    history=[{'id':message_id,'role':'ASSISTANT','quiz':quiz,'content':''}]
    for item in _loaded(rows,versions):
        if item.get('quiz') or is_quiz_turn(item):break
        history.append(item)
    return _choice_snapshot(session,owner,course,history).get(message_id,{})


def _result(question,choice):
    return {'selected':choice,'correct':choice==question['correct'],
            'correct_choice':question['correct']}


def _public(message_id,quiz,selected):
    return {'message_id':message_id,'questions':[
        {'number':n,'stem':question['stem'],'options':question['options'],
         'result':_result(question,selected[n]) if n in selected else None}
        for n,question in enumerate(quiz['questions'],1)]}


@router.get('/notes/courses/{course_id}/ai/quizzes')
def list_quizzes(request:Request,course_id:int):
    from app import main
    user=main.get_current_user(request)
    if not user:return JSONResponse({'ok':False},status_code=401)
    with Session(main.engine) as session:
        if not main._owned_study_course(session,user,course_id):return JSONResponse({'ok':False},status_code=404)
        versions=main._study_source_versions(session,user.id,course_id)
        rows=session.exec(select(main.StudyChatMessage).where(
            main.StudyChatMessage.owner_user_id==user.id,main.StudyChatMessage.course_id==course_id)
            .order_by(main.StudyChatMessage.id.desc()).limit(40)).all()
        history=_loaded(list(reversed(rows)),versions)
        selected=_choice_snapshot(session,user.id,course_id,history)
        quizzes=[_public(item['id'],item['quiz'],selected.get(item['id'],{})) for item in history
                 if item.get('quiz') and not str(item['mode']).endswith('_PDF')]
    return JSONResponse({'ok':True,'quizzes':quizzes},headers={'Cache-Control':'private, no-store'})


@router.post('/notes/courses/{course_id}/ai/quizzes/{message_id}/answers')
def select_answer(request:Request,course_id:int,message_id:int,number:int=Form(...),choice:str=Form(...)):
    from app import main
    user=main.get_current_user(request)
    if not user:return JSONResponse({'ok':False},status_code=401)
    choice=choice.strip().upper()
    if choice not in 'ABCDE' or len(choice)!=1 or number<1:
        return JSONResponse({'ok':False,'error':'Geçerli bir şık seç.'},status_code=400)
    with Session(main.engine) as session:
        # Serialize first selections for this course across tabs and workers.
        course=session.exec(select(main.StudyCourse).where(main.StudyCourse.id==course_id,
            main.StudyCourse.owner_user_id==user.id).with_for_update()).first()
        if not course:return JSONResponse({'ok':False},status_code=404)
        row=session.exec(select(main.StudyChatMessage).where(main.StudyChatMessage.id==message_id,
            main.StudyChatMessage.owner_user_id==user.id,main.StudyChatMessage.course_id==course_id,
            main.StudyChatMessage.role=='ASSISTANT')).first()
        if not row:return JSONResponse({'ok':False},status_code=404)
        versions=main._study_source_versions(session,user.id,course_id,lock=True)
        item=_loaded([row],versions)[0]
        quiz=item.get('quiz')
        if not quiz or number>len(quiz['questions']):
            return JSONResponse({'ok':False,'error':'Bu sorunun kayıtlı anahtarı güncel notlarla doğrulanamadı.'},status_code=409)
        selected=_saved_choices(session,user.id,course_id,message_id,quiz,versions)
        repeated=number in selected
        if not repeated:
            plan=SimpleNamespace(operation='solve',grade_previous_set=True,
                reveal_previous_key=False,quiz_answers=((number,choice),),quiz_key_corrections=())
            remember(session,owner=user.id,course=course_id,assistant_id=message_id,
                plan=plan,quiz=None,history=[item],versions=versions)
            session.add(StudyAttempt(owner_user_id=user.id,course_id=course_id,
                attempt_key=f'tap:{message_id}:{number}:{choice}'))
            selected[number]=choice
        current=get_or_create_state(session,user.id,course_id)
        current.active_quiz_id=message_id
        try:request_data=json.loads(current.active_request_json) if current.source_stamp==stamp(versions) else {}
        except (ValueError,TypeError):request_data={}
        request_data['_quiz_selection']={'message_id':message_id,
            'answers':[{'number':n,'choice':answer} for n,answer in sorted(selected.items())]}
        current.active_request_json=json.dumps(request_data,ensure_ascii=False)
        current.source_stamp=stamp(versions);session.add(current);session.commit()
        result=_result(quiz['questions'][number-1],selected[number])
    return JSONResponse({'ok':True,'result':result,'already_answered':repeated},
                        headers={'Cache-Control':'private, no-store'})


# Message reactions share the existing owned chat metadata; no schema change.
def _feedback_metadata(value):
    if not value:
        return {}
    data=json.loads(value)
    if not isinstance(data,dict):
        raise ValueError('Invalid message metadata')
    return data


@router.get('/notes/courses/{course_id}/ai/feedback')
def list_feedback(request:Request,course_id:int,ids:str=''):
    from app import main
    user=main.get_current_user(request)
    if not user:return JSONResponse({'ok':False},status_code=401)
    parts=ids.split(',') if ids else []
    if len(parts)>100 or any(not p.isdecimal() or len(p)>18 for p in parts):
        return JSONResponse({'ok':False},status_code=400)
    with Session(main.engine) as session:
        if not main._owned_study_course(session,user,course_id):
            return JSONResponse({'ok':False},status_code=404)
        rows=session.exec(select(main.StudyChatMessage).where(
            main.StudyChatMessage.owner_user_id==user.id,
            main.StudyChatMessage.course_id==course_id,
            main.StudyChatMessage.role=='ASSISTANT',
            main.StudyChatMessage.id.in_([int(p) for p in parts]))).all() if parts else []
        votes={}
        for row in rows:
            try:vote=_feedback_metadata(row.source_evidence_json).get('user_feedback')
            except (ValueError,TypeError):continue
            if vote in {'like','dislike'}:votes[str(row.id)]=vote
    return JSONResponse({'ok':True,'votes':votes},headers={'Cache-Control':'private, no-store'})


@router.post('/notes/courses/{course_id}/ai/messages/{message_id}/feedback')
def save_feedback(request:Request,course_id:int,message_id:int,vote:str=Form(...)):
    from app import main
    user=main.get_current_user(request)
    if not user:return JSONResponse({'ok':False},status_code=401)
    if vote not in {'like','dislike','none'}:
        return JSONResponse({'ok':False},status_code=400)
    with Session(main.engine) as session:
        if not main._owned_study_course(session,user,course_id):
            return JSONResponse({'ok':False},status_code=404)
        row=session.exec(select(main.StudyChatMessage).where(
            main.StudyChatMessage.owner_user_id==user.id,
            main.StudyChatMessage.course_id==course_id,
            main.StudyChatMessage.id==message_id,
            main.StudyChatMessage.role=='ASSISTANT').with_for_update()).first()
        if not row:return JSONResponse({'ok':False},status_code=404)
        try:metadata=_feedback_metadata(row.source_evidence_json)
        except (ValueError,TypeError):
            return JSONResponse({'ok':False,'error':'Yanıt değerlendirmesi kaydedilemedi.'},status_code=409)
        if vote=='none':metadata.pop('user_feedback',None)
        else:metadata['user_feedback']=vote
        row.source_evidence_json=json.dumps(metadata,ensure_ascii=False)
        session.add(row);session.commit()
    return JSONResponse({'ok':True,'vote':vote},headers={'Cache-Control':'private, no-store'})
