"""Extended native mobile API: realtime-friendly feeds, history, media, notices,
expert consultation and Academic AI contracts.

This router intentionally reuses the production models/helpers. It does not
create a second business-logic stack or introduce polling.
"""
from datetime import datetime
from pathlib import Path
import json, shutil, uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile\nfrom fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import JSONResponse
from sqlmodel import Session, select, func
from starlette.requests import Request

from app.main import (
    AdminNotice, Analysis, ConsultationCase, ConsultationMessage, ExpertProfile,
    ExpertReview, Patient, PatientMedia, StudyChatMessage, StudyCourse, StudyMaterial,
    User, engine, storage_persist_file,
)

# Import the actual mobile auth dependency separately to avoid duplicate auth.
from app.mobile_api import _mobile_user
from app.main import study_ai_ask, SESSION_COOKIE, storage_ensure_local

router = APIRouter(prefix="/api/mobile/v1", tags=["mobile-modern"])


def _user_owned_patient(session, user, patient_id):
    p = session.get(Patient, patient_id)
    if not p or (user.role != "ADMIN" and p.owner_user_id != user.id):
        raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
    return p


@router.get("/analyses")
def mobile_analysis_history(user=Depends(_mobile_user), limit: int = 30, offset: int = 0):
    limit=max(1,min(limit,50)); offset=max(0,offset)
    with Session(engine, expire_on_commit=False) as s:
        rows=s.exec(
            select(Analysis, Patient).join(Patient, Patient.id==Analysis.patient_id)
            .where(Patient.owner_user_id==user.id)
            .order_by(Analysis.created_at.desc()).offset(offset).limit(limit)
        ).all()
        total=s.exec(select(func.count()).select_from(Analysis).join(Patient,Patient.id==Analysis.patient_id).where(Patient.owner_user_id==user.id)).one()
        return {"items":[{"id":a.id,"patient_id":p.id,"patient_name":f"{p.first_name or ''} {p.last_name or ''}".strip(),"tooth_number":a.tooth_number,"status":a.status,"clinical_notes":a.clinical_notes,"created_at":a.created_at} for a,p in rows],"total":int(total),"limit":limit,"offset":offset}


@router.get("/patients/{patient_id}/media")
def mobile_patient_media(patient_id:int,user=Depends(_mobile_user),limit:int=60,offset:int=0):
    limit=max(1,min(limit,100)); offset=max(0,offset)
    with Session(engine,expire_on_commit=False) as s:
        _user_owned_patient(s,user,patient_id)
        rows=s.exec(select(PatientMedia).where(PatientMedia.patient_id==patient_id,PatientMedia.owner_user_id==user.id).order_by(PatientMedia.uploaded_at.desc()).offset(offset).limit(limit)).all()
        return {"items":[{"id:m.id,"filename":m.original_filename,"media_type":m.media_type,"tooth_number":m.tooth_number,"note":m.note,"uploaded_at":m.uploaded_at,"url":f"/api/mobile/v1/patients/{patient_id}/media/{m.id}"} for m in rows]}


@router.post("/patients/{patient_id}/media")
async def mobile_upload_media(patient_id:int,user=Depends(_mobile_user),file:UploadFile=File(...),tooth_number:str=Form(""),note:str=Form(""),media_type:str=Form("PHOTO")):
    allowed={".jpg",".jpeg",".png",".webp",".heic"}
    name=Path(file.filename or "").name; ext=Path(name).suffix.lower()
    if ext not in allowed: raise HTTPException(status_code=422,detail="Desteklenmeyen görüntü formatı.")
    with Session(engine,expire_on_commit=False) as s:
        _user_owned_patient(s,user,patient_id)
        stored=f"patient_{patient_id}_{uuid.uuid4().hex}{ext}"
        dest=Path("uploads")/stored; dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open("wb") as out: shutil.copyfileobj(file.file,out)
        storage_persist_file(dest)
        row=PatientMedia(patient_id=patient_id,owner_user_id=user.id,original_filename=name,stored_filename=stored,file_path=str(dest),media_type=(media_type or "PHOTO")[:40],tooth_number=(tooth_number or "").strip() or None,note=(note or "").strip() or None)
        s.add(row); s.commit(); s.refresh(row)
        return {"ok":True,"media":{"id":row.id,"filename":row.original_filename,"media_type":row.media_type}}


@router.get("/patients/{patient_id}/media/{media_id}/file")\ndef mobile_media_file(patient_id:int,media_id:int,user=Depends(_mobile_user)):\n    with Session(engine,expire_on_commit=False) as s:\n        _user_owned_patient(s,user,patient_id)\n        row=s.get(PatientMedia,media_id)\n        if not row or row.patient_id!=patient_id or row.owner_user_id!=user.id: raise HTTPException(status_code=404,detail="Medya bulunamadı.")\n        try: path=storage_ensure_local(row.file_path)\n        except FileNotFoundError: raise HTTPException(status_code=404,detail="Dosya bulunamadı.")\n        types={".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",".webp":"image/webp",".heic":"image/heic"}\n        return FileResponse(path,media_type=types.get(path.suffix.lower(),"application/octet-stream"),filename=row.original_filename)\n\n@router.get("/patients/{patient_id}/media/{media_id}")
def mobile_media_meta(patient_id:int,media_id:int,user=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as s:
        _user_owned_patient(s,user,patient_id)
        row=s.get(PatientMedia,media_id)
        if not row or row.patient_id!=patient_id or row.owner_user_id!=user.id: raise HTTPException(status_code=404,detail="Medya bulunamadı.")
        return {"id":row.id,"filename":row.original_filename,"media_type":row.media_type,"tooth_number":row.tooth_number,"note":row.note,"uploaded_at":row.uploaded_at,"path":row.file_path}


@router.get("/notifications")
def mobile_notifications(user=Depends(_mobile_user),limit:int=40):
    limit=max(1,min(limit,80))
    with Session(engine,expire_on_commit=False) as s:
        rows=s.exec(select(AdminNotice).where(AdminNotice.user_id==user.id,AdminNotice.status=="ACTIVE").order_by(AdminNotice.created_at.desc()).limit(limit)).all()
        unread=s.exec(select(func.count()).select_from(AdminNotice).where(AdminNotice.user_id==user.id,AdminNotice.status=="ACTIVE",AdminNotice.read_at==None)).one()
        return {"items":[{"id:n.id,"title":n.title,"message":n.message,"notice_type":n.notice_type,"target_url":n.target_url,"read_at":n.read_at,"created_at":n.created_at} for n in rows],"unread":int(unread)}


@router.post("/notifications/{notice_id}/read")
def mobile_notification_read(notice_id:int,user=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as s:
        n=s.get(AdminNotice,notice_id)
        if not n or n.user_id!=user.id: raise HTTPException(status_code=404,detail="Bildirim bulunamadı.")
        n.read_at=datetime.utcnow(); n.is_read=True; s.add(n); s.commit()
        return {"ok":True}


@router.get("/experts")
def mobile_experts(user=Depends(_mobile_user),specialty:str="",q:str="",available_only:bool=False):
    with Session(engine,expire_on_commit=False) as s:
        stmt=select(ExpertProfile).where(ExpertProfile.user_id!=user.id,ExpertProfile.application_status=="APPROVED",ExpertProfile.verification_status=="VERIFIED",ExpertProfile.specialty_verified==True,ExpertProfile.credential_document_path!=None,ExpertProfile.phone!=None)
        if specialty: stmt=stmt.where(ExpertProfile.specialty==specialty)
        if available_only: stmt=stmt.where(ExpertProfile.availability=="AVAILABLE")
        profiles=s.exec(stmt.order_by(ExpertProfile.updated_at.desc()).limit(100)).all()
        out=[]
        needle=q.strip().casefold()
        for p in profiles:
            u=s.get(User,p.user_id)
            if not u: continue
            hay=" ".join(filter(None,[u.display_name,p.specialty,p.institution,p.academic_title])).casefold()
            if needle and needle not in hay: continue
            reviews=s.exec(select(ExpertReview).where(ExpertReview.expert_user_id==p.user_id)).all()
            out.append({"user_id":u.id,"display_name":u.display_name,"specialty":p.specialty,"academic_title":p.academic_title,"institution":p.institution,"bio":p.bio,"availability":p.availability,"consultation_price":p.consultation_price,"rating_avg":round(sum(r.rating for r in reviews)/len(reviews),1) if reviews else None,"review_count":len(reviews)})
        return {"items":out}


@router.get("/consultations")
def mobile_consultations(user=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as s:
        cases=s.exec(select(ConsultationCase).where((ConsultationCase.requester_user_id==user.id)|(ConsultationCase.expert_user_id==user.id)).order_by(ConsultationCase.requested_at.desc()).limit(100)).all()
        other_ids={c.expert_user_id if c.requester_user_id==user.id else c.requester_user_id for c in cases}
        users={u.id:u for u in s.exec(select(User).where(User.id.in_(other_ids))).all()} if other_ids else {}
        return {"items":[{"id:c.id,"other_user_id":c.expert_user_id if c.requester_user_id==user.id else c.requester_user_id,"other_name":users.get(c.expert_user_id if c.requester_user_id==user.id else c.requester_user_id).display_name if users.get(c.expert_user_id if c.requester_user_id==user.id else c.requester_user_id) else "Kullanıcı","specialty":c.specialty,"status":c.status,"question":c.question,"clinical_summary":c.clinical_summary,"requested_at":c.requested_at,"expert_response_deadline":c.expert_response_deadline} for c in cases]}


@router.get("/consultations/{case_id}")
def mobile_consultation(case_id:int,user=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as s:
        c=s.get(ConsultationCase,case_id)
        if not c or user.id not in {c.requester_user_id,c.expert_user_id}: raise HTTPException(status_code=404,detail="Danışmanlık bulunamadı.")
        rows=s.exec(select(ConsultationMessage).where(ConsultationMessage.case_id==case_id).order_by(ConsultationMessage.id).limit(500)).all()
        return {"case":{"id":c.id,"status":c.status,"specialty":c.specialty,"question":c.question,"clinical_summary":c.clinical_summary,"requested_at":c.requested_at},"messages":[{"id:m.id,"sender_user_id":m.sender_user_id,"type":m.message_type,"content":m.content,"created_at":m.created_at} for m in rows]}


class MobileMessage:
    pass


@router.post("/consultations/{case_id}/messages")
def mobile_consultation_message(case_id:int,content:str=Form(...),reply_to_message_id:int|None=Form(None),user=Depends(_mobile_user)):
    from app.main import _users_blocked, _contains_profanity, _consultation_event, _record_message_realtime_events, _record_case_status_realtime_events, _resolve_notifications, _record_realtime_event, _publish_realtime_event, _utcnow_naive
    text_value=content.strip()
    if not text_value or len(text_value)>4000: raise HTTPException(status_code=422,detail="Mesaj 1-4000 karakter olmalıdır.")
    now=_utcnow_naive()
    with Session(engine,expire_on_commit=False) as s:
        c=s.get(ConsultationCase,case_id)
        if not c or user.id not in {c.requester_user_id,c.expert_user_id}: raise HTTPException(status_code=404,detail="Danışmanlık bulunamadı.")
        if c.status not in {"ACTIVE","WAITING_START","EXPERT_COMPLETED","DISPUTE"}: raise HTTPException(status_code=409,detail="Bu danışmanlık şu anda mesajlaşmaya açık değil.")
        if _users_blocked(s,user.id,c.expert_user_id if user.id==c.requester_user_id else c.requester_user_id): raise HTTPException(status_code=403,detail="Bu kullanıcıyla mesajlaşma engellenmiş.")
        if _contains_profanity(text_value): raise HTTPException(status_code=422,detail="Mesaj içerik filtresine takıldı.")
        if reply_to_message_id:
            r=s.get(ConsultationMessage,reply_to_message_id)
            if not r or r.case_id!=case_id: reply_to_message_id=None
        m=ConsultationMessage(case_id=case_id,sender_user_id=user.id,content=text_value,reply_to_message_id=reply_to_message_id)
        s.add(m); s.commit(); s.refresh(m)
        sender=s.get(User,user.id)
        events=_record_message_realtime_events(s,c,m,sender)
        s.commit()
    for e in events: 
        try:
            from app.main import on_loop,_publish_realtime_event
            on_loop(_publish_realtime_event,e)
        except Exception: pass
    return {"ok":True,"message":{"id":m.id,"sender_user_id":m.sender_user_id,"content":m.content,"created_at":m.created_at}}


@router.get("/academic/courses")
def mobile_academic_courses(user=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as s:
        courses=s.exec(select(StudyCourse).where(StudyCourse.owner_user_id==user.id).order_by(StudyCourse.updated_at.desc())).all()
        return {"items":[{"id:c.id,"title":c.title,"description":c.description,"updated_at":c.updated_at,"material_count":int(s.exec(select(func.count()).select_from(StudyMaterial).where(StudyMaterial.course_id==c.id,StudyMaterial.owner_user_id==user.id)).one())} for c in courses]}


@router.post("/academic/courses/{course_id}/ask")
def mobile_academic_ask(course_id:int,message:str=Form(...),credentials:HTTPAuthorizationCredentials=Depends(HTTPBearer(auto_error=False)),user=Depends(_mobile_user)):
    if not credentials: raise HTTPException(status_code=401,detail="Oturum geçersiz.")
    token=credentials.credentials
    scope={"type":"http","method":"POST","path":f"/notes/courses/{course_id}/ai/ask","headers":[(b"cookie",f"{SESSION_COOKIE}={token}".encode()),(b"accept",b"application/json")],"query_string":b"","server":("mobile",443)}
    req=Request(scope)
    result=study_ai_ask(req,course_id,BackgroundTasks(),message)
    return result


@router.get("/consultations/{case_id}/media/{message_id}")
def mobile_consultation_message_media(case_id:int,message_id:int,user=Depends(_mobile_user)):
    with Session(engine,expire_on_commit=False) as s:
        c=s.get(ConsultationCase,case_id); m=s.get(ConsultationMessage,message_id)
        if not c or user.id not in {c.requester_user_id,c.expert_user_id} or not m or m.case_id!=case_id or not m.media_path: raise HTTPException(status_code=404,detail="Medya bulunamadı.")
        return {"ok":True,"path":m.media_path}
