"""Private course continuity and review records; no model calls or OCR."""
import hashlib
import json
import uuid
from datetime import datetime,timedelta,timezone
from sqlmodel import SQLModel,Field,select
from sqlalchemy import UniqueConstraint


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StudyLearningState(SQLModel,table=True):
    __table_args__=(UniqueConstraint('owner_user_id','course_id'),)
    id:int|None=Field(default=None,primary_key=True)
    owner_user_id:int=Field(index=True)
    course_id:int=Field(index=True)
    epoch:str=Field(default_factory=lambda:uuid.uuid4().hex)
    active_quiz_id:int|None=0
    active_request_json:str='{}'
    source_stamp:str=''


class StudyReview(SQLModel,table=True):
    __table_args__=(UniqueConstraint('owner_user_id','course_id','fact_key','source_stamp'),)
    id:int|None=Field(default=None,primary_key=True)
    owner_user_id:int=Field(index=True)
    course_id:int=Field(index=True)
    fact_key:str
    source_stamp:str=Field(index=True)
    fact:str
    source:str
    correct:int=0
    wrong:int=0
    streak:int=0
    due_at:datetime=Field(default_factory=now,index=True)
    updated_at:datetime=Field(default_factory=now)


class StudyAttempt(SQLModel,table=True):
    __table_args__=(UniqueConstraint('owner_user_id','course_id','attempt_key'),)
    id:int|None=Field(default=None,primary_key=True)
    owner_user_id:int=Field(index=True)
    course_id:int=Field(index=True)
    attempt_key:str
    created_at:datetime=Field(default_factory=now)


def stamp(versions):
    return hashlib.sha256(json.dumps(versions,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def state(session,owner,course):
    return session.exec(select(StudyLearningState).where(StudyLearningState.owner_user_id==owner,
        StudyLearningState.course_id==course)).first()


def get_or_create_state(session,owner,course):
    current=state(session,owner,course)
    if current is None:
        current=StudyLearningState(owner_user_id=owner,course_id=course)
        session.add(current);session.flush()
    return current


def quiz_anchor(session,owner,course,versions):
    from app.main import StudyChatMessage
    from app.academic_quiz import restore_quizzes
    current=state(session,owner,course)
    if current and current.active_quiz_id==0:return None
    query=select(StudyChatMessage).where(
        StudyChatMessage.owner_user_id==owner,StudyChatMessage.course_id==course,
        StudyChatMessage.role=='ASSISTANT')
    if current and current.active_quiz_id:query=query.where(StudyChatMessage.id==current.active_quiz_id)
    else:query=query.where(StudyChatMessage.source_evidence_json.contains('"quiz"'))
    row=session.exec(query.order_by(StudyChatMessage.id.desc()).limit(1)).first()
    if row is None:return None
    item={'role':row.role,'content':row.content,'id':row.id,'mode':row.mode}
    restore_quizzes([item],[row],versions)
    return item if item.get('quiz') else None


def context(session,owner,course,versions):
    current=state(session,owner,course)
    try:active=json.loads(current.active_request_json) if current else {}
    except (ValueError,TypeError):active={}
    if current and current.source_stamp!=stamp(versions):active={}
    from sqlalchemy import func,case
    filters=(StudyReview.owner_user_id==owner,StudyReview.course_id==course,StudyReview.source_stamp==stamp(versions))
    count,correct,wrong,due=session.exec(select(func.count(StudyReview.id),func.coalesce(func.sum(StudyReview.correct),0),
        func.coalesce(func.sum(StudyReview.wrong),0),func.coalesce(func.sum(case((StudyReview.due_at<=now(),1),else_=0)),0))
        .where(*filters)).one()
    weak=session.exec(select(StudyReview).where(*filters)
        .order_by((StudyReview.wrong-StudyReview.correct).desc(),StudyReview.due_at).limit(6)).all()
    return {'active_request':active,'practiced_facts':count,'due_count':due,
        'correct':correct,'wrong':wrong,
        'review':[{'fact':row.fact,'source':row.source,'due':row.due_at<=now(),
            'correct':row.correct,'wrong':row.wrong} for row in weak]}


def remember(session,*,owner,course,assistant_id,plan,quiz,history,versions):
    current=get_or_create_state(session,owner,course)
    # A clarification must not erase the task being clarified.
    if plan and plan.operation!='clarify' and not getattr(plan,'grade_previous_set',False) and not getattr(plan,'reveal_previous_key',False):
        keys=('resolved_query','operation','count','difficulty','source_sections','source_files','source_subjects','depth')
        current.active_request_json=json.dumps({key:getattr(plan,key,None) for key in keys},ensure_ascii=False)
        current.source_stamp=stamp(versions)
    if quiz:current.active_quiz_id=assistant_id
    elif not current.active_quiz_id:
        prior=next((item for item in reversed(history) if item.get('quiz') and item.get('id')),None)
        if prior:current.active_quiz_id=prior['id']
    session.add(current)
    if not plan or not getattr(plan,'grade_previous_set',False):return
    prior=next((item for item in reversed(history) if item.get('quiz')),None)
    if not prior or not prior.get('id'):return
    questions=[dict(q) for q in prior['quiz']['questions']]
    answers=dict(plan.quiz_answers)
    if any(type(n) is not int or not 1<=n<=len(questions) or choice not in 'ABCDE' for n,choice in answers.items()):return
    for correction in plan.quiz_key_corrections:
        if not 1<=correction['number']<=len(questions):return
        questions[correction['number']-1]['correct']=correction['choice']
    key=stamp([prior['id'],sorted(answers.items()),list(plan.quiz_key_corrections)])
    if session.exec(select(StudyAttempt).where(StudyAttempt.owner_user_id==owner,
            StudyAttempt.course_id==course,StudyAttempt.attempt_key==key)).first():return
    session.add(StudyAttempt(owner_user_id=owner,course_id=course,attempt_key=key))
    source_stamp=stamp(versions)
    keys={stamp(questions[number-1]['fact'].casefold().strip()) for number in answers}
    reviews={row.fact_key:row for row in session.exec(select(StudyReview).where(
        StudyReview.owner_user_id==owner,StudyReview.course_id==course,
        StudyReview.source_stamp==source_stamp,StudyReview.fact_key.in_(keys))).all()} if keys else {}
    for number,choice in answers.items():
        question=questions[number-1];fact=question['fact'];fact_key=stamp(fact.casefold().strip())
        review=reviews.get(fact_key)
        if review is None:review=StudyReview(owner_user_id=owner,course_id=course,
            fact_key=fact_key,source_stamp=source_stamp,fact=fact,source=question['source'])
        reviews[fact_key]=review
        if choice==question['correct']:
            review.correct+=1;review.streak+=1
            # This is a scheduling heuristic, not a validated mastery score.
            review.due_at=now()+timedelta(days=(1,3,7,14,30)[min(review.streak-1,4)])
        else:
            review.wrong+=1;review.streak=0;review.due_at=now()+timedelta(minutes=10)
        review.updated_at=now();session.add(review)


def erase(session,owner,course=None,*,keep_reviews=False):
    from sqlalchemy import delete
    models=[StudyLearningState] if keep_reviews else [StudyLearningState,StudyReview,StudyAttempt]
    for model in models:
        query=delete(model).where(model.owner_user_id==owner)
        if course is not None:query=query.where(model.course_id==course)
        session.execute(query)
