"""Native clinician approval calls the web's atomic, revision-checked apply flow."""
import json
from fastapi import APIRouter,BackgroundTasks,Depends,HTTPException,Response
from starlette.concurrency import run_in_threadpool
from app.voice_exam import ApplyInput,apply_review
from app.mobile_api import _mobile_access_token,_mobile_request
from app.mobile_account_api import _account_user

router=APIRouter(tags=['mobile-voice-workflow'])

@router.post('/patients/{patient_id}/voice-exam/apply')
async def apply_native_review(patient_id:int,payload:ApplyInput,background_tasks:BackgroundTasks,response:Response,token:str=Depends(_mobile_access_token),user=Depends(_account_user)):
    response.headers['Cache-Control']='private, no-store'
    response.headers['Vary']='Authorization'
    result_response=await run_in_threadpool(apply_review,_mobile_request(token),patient_id,payload,background_tasks)
    result=json.loads(result_response.body)
    if result_response.status_code>=400 or result.get('ok') is not True:
        raise HTTPException(status_code=result_response.status_code if result_response.status_code>=400 else 502,detail=result.get('error','Muayene kaydı doğrulanamadı.'))
    return result
