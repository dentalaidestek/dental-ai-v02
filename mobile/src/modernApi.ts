import {ChatFile,validateChatFile} from "./chatFiles";
import {ApiError} from './api';
import {revalidateSession} from './sessionExpiry';
const API_BASE="https://dentalai.tr/api/mobile/v1";
async function req<T>(path:string,token:string,init:RequestInit={}):Promise<T>{
 const headers:any={Authorization:"Bearer "+token,...(!(init.body instanceof FormData)?{"Content-Type":"application/json"}:{}),...(init.headers||{})};
 // Bound network waits for notifications, consultations, academic and media screens.
 // Keep the caller's cancellation signal while enforcing a finite deadline.
 const controller=new AbortController();
 const abort=()=>controller.abort();
 // Academic generation can legitimately take minutes; ordinary reads stay bounded at 30 seconds.
 const deadlineMs=/^\/academic\/courses\/\d+\/ask$/.test(path)?180000:/^\/consultations\/\d+\/attachments$/.test(path)?120000:30000;
 const timeout=setTimeout(abort,deadlineMs);
 if(init.signal?.aborted)controller.abort();
 else init.signal?.addEventListener("abort",abort,{once:true});
 try{
  const r=await fetch(API_BASE+path,{...init,credentials:"omit",headers,signal:controller.signal});
  const raw=await r.text(); let b:any={};
  try{b=raw?JSON.parse(raw):{}}catch{
   // Never interpret an HTML login page or proxy error as successful API data.
   if(r.ok)throw new ApiError(502,"Sunucu beklenen JSON yanıtını göndermedi. Lütfen tekrar deneyin.");
  }
  if(r.ok&&(!raw.trim()||!b||typeof b!=="object"||Array.isArray(b)))
   throw new ApiError(502,"Sunucudan geçersiz API yanıtı alındı.");
  if(!r.ok){
   if(r.status===401)await revalidateSession(token);
   const detail=b?.detail;
   throw new ApiError(r.status,typeof detail==="string"?detail:(typeof detail?.message==="string"?detail.message:"İstek başarısız."));
  }
  return b as T;
 }catch(error){
  if(controller.signal.aborted&&!init.signal?.aborted)
   throw new ApiError(408,"Sunucu yanıt vermedi. Bağlantınızı kontrol edip tekrar deneyin.");
  if(error instanceof TypeError)throw new ApiError(503,"Sunucuya bağlanılamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.");
  throw error;
 }finally{
  clearTimeout(timeout);
  init.signal?.removeEventListener("abort",abort);
 }
}
export type Notice={id:number;title:string;message:string;notice_type:string;target_url?:string|null;read_at?:string|null;created_at:string};
export type Expert={user_id:number;display_name:string;specialty:string;academic_title?:string|null;institution?:string|null;bio?:string|null;availability:string;consultation_price:number;rating_avg?:number|null;review_count:number};
export type Consultation={id:number;other_user_id:number;other_display_name:string;specialty:string;tooth_region?:string|null;status:string;question:string;requested_at:string;last_message?:string|null;last_message_at?:string|null;messages_deleted_at?:string|null;unread_count:number};
export type ChatMessage={id:number;sender_user_id:number;message_type:string;content:string;reply_to_message_id?:number|null;created_at:string;has_media?:boolean};
export type AnalysisHistory={id:number;patient_id:number;patient_name:string;tooth_number?:string|null;status:string;clinical_notes?:string|null;created_at:string;is_voice_review?:boolean};
export type Course={id:number;title:string;description?:string|null;updated_at:string;material_count:number};
export const registerPushDevice=(t:string,deviceId:string,expoPushToken:string,platform:"android"|"ios")=>
 req<{ok:boolean}>("/push/devices",t,{method:"POST",body:JSON.stringify({device_id:deviceId,expo_push_token:expoPushToken,platform})});
export const unregisterPushDevice=(t:string,deviceId:string)=>
 req<{ok:boolean}>("/push/devices/"+encodeURIComponent(deviceId),t,{method:"DELETE"});
export const getNotifications=async(t:string)=>{const r=await req<any>("/notifications",t);const items=r?.items??r?.notifications;if(!Array.isArray(items)||items.some((n:unknown)=>!n||typeof n!=="object"||!Number.isSafeInteger((n as Notice).id)||typeof (n as Notice).title!=="string"||typeof (n as Notice).message!=="string"))throw Error("Bildirim sunucusundan geçersiz liste alındı. Tekrar deneyin.");const unread=Number(r?.unread??r?.unread_count??0);if(!Number.isSafeInteger(unread)||unread<0)throw Error("Bildirim sunucusundan geçersiz okunmamış sayısı alındı.");return {items:items.map((n:Notice&{is_read?:boolean})=>({...n,read_at:n.read_at||(n.is_read?n.created_at:null)})) as Notice[],unread}};
export const markNotificationRead=(t:string,id:number)=>{
 if(!Number.isSafeInteger(id)||id<=0)throw Error("Geçersiz bildirim kimliği.");
 return req<{ok:boolean}>("/notifications/"+id+"/read",t,{method:"POST"});
};
export const getAnalysisHistory=async(t:string,before?:number,patientId?:number,toothNumber?:string)=>{
 if(patientId!==undefined&&(!Number.isSafeInteger(patientId)||patientId<=0))throw Error("Geçersiz hasta kimliği.");
 if(toothNumber!==undefined&&!/^(?:[1-4][1-8]|[5-8][1-5])$/.test(toothNumber))throw Error("Geçersiz FDI diş numarası.");
 if(before!==undefined&&(!Number.isSafeInteger(before)||before<=0))throw Error("Geçersiz analiz sayfa kimliği.");
 const r=await req<{items:AnalysisHistory[];total:number;next_before?:number|null}>("/analyses?limit=50"+(before!==undefined?`&before=${encodeURIComponent(before)}`:"")+(patientId!==undefined?`&patient_id=${patientId}`:"")+(toothNumber?`&tooth_number=${toothNumber}`:""),t);
 // Older deployed servers omit next_before; treat this as the final page.
 const next_before=r?.next_before??null;
 if(!Array.isArray(r?.items)||r.items.length>50||
    r.items.some(n=>!n||!Number.isSafeInteger(n.id)||n.id<=0||!Number.isSafeInteger(n.patient_id)||typeof n.status!=="string"||(patientId!==undefined&&n.patient_id!==patientId)||(toothNumber!==undefined&&n.tooth_number!==toothNumber))||
    (r.items.length===0&&next_before!==null)||
    (before!==undefined&&(r.items.some(n=>n.id>=before)||(next_before!==null&&next_before>=before)))||
    (next_before!==null&&(!Number.isSafeInteger(next_before)||next_before<=0))||
    !Number.isSafeInteger(r.total)||r.total<0)
   throw Error("Analiz sunucusundan geçersiz liste alındı. Tekrar deneyin.");
 return {...r,next_before};
};
export const deleteMedia=(t:string,patientId:number,mediaId:number)=>{
 if(!Number.isSafeInteger(patientId)||patientId<=0||!Number.isSafeInteger(mediaId)||mediaId<=0)
  throw Error("Geçersiz hasta veya klinik medya kimliği.");
 return req<{ok:boolean;media_id:number}>(`/patients/${patientId}/media/${mediaId}`,t,{method:"DELETE"});
};
export const getMedia=async(t:string,p:number,before?:number)=>{
 if(!Number.isSafeInteger(p)||p<=0||(before!==undefined&&(!Number.isSafeInteger(before)||before<=0)))
  throw Error("Geçersiz hasta veya sayfa kimliği.");
 const r=await req<{items:any[];next_before?:number|null}>(`/patients/${p}/media`+(before!==undefined?`?before=${encodeURIComponent(before)}`:""),t);
 const cursor=r?.next_before??null;
 if(!Array.isArray(r?.items)||r.items.length>40||
   new Set(r.items.map(m=>m?.id)).size!==r.items.length||
   r.items.some(m=>!m||!Number.isSafeInteger(m.id)||m.id<=0||
      (m.original_filename!=null&&typeof m.original_filename!=="string")||
      (m.filename!=null&&typeof m.filename!=="string"))||
   (cursor!==null&&(!Number.isSafeInteger(cursor)||cursor<=0||!r.items.some(m=>m.id===cursor)))||
   (r.items.length===0&&cursor!==null)||
   (before!==undefined&&(r.items.some(m=>m.id>=before)||(cursor!==null&&cursor>=before))))
  throw Error("Klinik medya sunucusundan geçersiz liste alındı.");
 return {items:r.items.map(m=>({...m,filename:m.filename||m.original_filename||"",url:`${API_BASE}/patients/${p}/media/${m.id}/file`})),next_before:cursor};
};
export const getExperts=(t:string,q="")=>req<{items:Expert[]}>("/experts?q="+encodeURIComponent(q),t);
export type ConsultationRequestPayload={expert_user_id:number;clinical_summary:string;question:string;requester_opinion?:string;tooth_region?:string;patient_id?:number;media_ids?:string;urgency?:string;request_key?:string};
export function createConsultation(t:string,payload:ConsultationRequestPayload){
 if(!Number.isSafeInteger(payload.expert_user_id)||payload.expert_user_id<=0||!payload.question?.trim()||!payload.clinical_summary?.trim()||
    (payload.patient_id!==undefined&&(!Number.isSafeInteger(payload.patient_id)||payload.patient_id<=0))||
    (payload.media_ids!==undefined&&payload.media_ids!==""&&(!payload.patient_id||!/^\d+(,\d+)*$/.test(payload.media_ids)))||
    (payload.request_key!==undefined&&!/^[A-Za-z0-9_-]{8,96}$/.test(payload.request_key)))
  throw Error("Geçersiz uzman, hasta, klinik bilgi veya talep anahtarı.");
 return req<{ok:boolean;case_id:number}>("/consultations",t,{method:"POST",body:JSON.stringify(payload)}).then(result=>{
 if(result.ok!==true||!Number.isSafeInteger(result.case_id)||result.case_id<=0)throw Error("Talep kaydı doğrulanamadı. Yeni talep oluşturmadan önce aynı anahtarla durumunu kontrol edin.");
 return result;
 });
}
export type ConsultationRequestContext={expert:Expert;response_minutes:number;urgencies:Array<{value:string;label:string}>};
export async function getConsultationRequestContext(t:string,expertId:number){
 if(!Number.isSafeInteger(expertId)||expertId<=0)throw Error("Geçersiz uzman.");
 const result=await req<ConsultationRequestContext>(`/consultations/request-context/${expertId}`,t);
 if(result.expert?.user_id!==expertId||typeof result.expert.display_name!=="string"||
    !Number.isFinite(result.expert.consultation_price)||result.expert.consultation_price<0||
    !Array.isArray(result.urgencies)||result.urgencies.some(item=>!item||typeof item.value!=="string"||typeof item.label!=="string")||
    !Number.isSafeInteger(result.response_minutes)||result.response_minutes<=0)throw Error("Uzman talep bilgileri doğrulanamadı.");
 return result;
}
export async function getConsultationRequestStatus(t:string,expertId:number,key:string){
 if(!Number.isSafeInteger(expertId)||expertId<=0||!/^[A-Za-z0-9_-]{8,96}$/.test(key))throw Error("Geçersiz talep anahtarı.");
 const result=await req<{found:boolean;case_id?:number;status?:string}>(`/consultations/request-status/${expertId}/${encodeURIComponent(key)}`,t);
 if(typeof result.found!=="boolean"||result.found&&(!Number.isSafeInteger(result.case_id)||Number(result.case_id)<=0||typeof result.status!=="string"))throw Error("Talep durumu doğrulanamadı.");
 return result;
}
export const getConsultations=async(t:string,before?:number)=>{
 if(before!==undefined&&(!Number.isSafeInteger(before)||before<=0))throw Error("Geçersiz görüşme sayfa kimliği.");
 const r=await req<{items:any[];next_before?:number|null}>("/consultations"+(before!==undefined?"?before="+encodeURIComponent(before):""),t);
 const cursor=r?.next_before??null;
 if(!Array.isArray(r?.items)||r.items.length>50||r.items.some(item=>!item||!Number.isSafeInteger(item.id)||item.id<=0)||
   new Set(r.items.map(item=>item.id)).size!==r.items.length||
   (cursor!==null&&(!Number.isSafeInteger(cursor)||cursor<=0||!r.items.some(item=>item.id===cursor)))||
   (r.items.length===0&&cursor!==null)||
   (before!==undefined&&(r.items.some(item=>item.id===before)||cursor===before)))
  throw Error("Uzman görüşmeleri sunucusundan geçersiz liste alındı. Tekrar deneyin.");
 return {next_before:cursor,items:r.items.map(item=>({...item,other_display_name:String(item.other_display_name||item.other_name||"Kullanıcı"),unread_count:Math.max(0,Number(item.unread_count)||0)})) as Consultation[]};
};
export const getConsultation=async(t:string,id:number,before?:number)=>{
 if(!Number.isSafeInteger(id)||id<=0)throw Error("Geçersiz görüşme kimliği.");
 if(before!==undefined&&(!Number.isSafeInteger(before)||before<=0))throw Error("Geçersiz mesaj sayfası.");
 const result=await req<{case:any;messages:ChatMessage[];next_before?:number|null}>(`/consultations/${id}`+(before!==undefined?`?before=${before}`:""),t);
 const cursor=result?.next_before??null;
 if(!result?.case||result.case.id!==id||!Array.isArray(result.messages)||result.messages.length>100||
  result.messages.some(m=>!m||!Number.isSafeInteger(m.id)||m.id<=0||!Number.isSafeInteger(m.sender_user_id)||m.sender_user_id<=0||
    (m.content!=null&&typeof m.content!=="string")||(before!==undefined&&m.id>=before))||
  result.messages.some((m,i)=>i>0&&m.id<=result.messages[i-1].id)||
  (cursor!==null&&(!Number.isSafeInteger(cursor)||cursor<=0||!result.messages.length||cursor!==result.messages[0].id))||
  (before!==undefined&&cursor!==null&&cursor>=before))
  throw Error("Görüşme sunucusundan geçersiz mesaj sayfası alındı.");
 return {...result,next_before:cursor};
};
export const markConsultationRead=(t:string,id:number,throughId:number)=>{
 if(!Number.isSafeInteger(id)||id<=0||!Number.isSafeInteger(throughId)||throughId<=0)
  throw Error("Geçersiz görüşme veya okundu mesajı.");
 return req<{ok:boolean;through_id:number;at:string}>(`/consultations/${id}/read`,t,{method:"POST",body:JSON.stringify({through_id:throughId})});
};
export const sendConsultationMessage=(t:string,id:number,content:string,clientMessageId:string,replyToMessageId?:number)=>{
 if(!Number.isSafeInteger(id)||id<=0||!content.trim()||!clientMessageId.trim()||(replyToMessageId!==undefined&&(!Number.isSafeInteger(replyToMessageId)||replyToMessageId<=0)))
  throw Error("Geçersiz görüşme, boş mesaj veya eksik istek kimliği.");
 return req<{ok:boolean;message:ChatMessage}>(`/consultations/${id}/messages`,t,{method:"POST",body:JSON.stringify({content,client_message_id:clientMessageId,...(replyToMessageId?{reply_to_message_id:replyToMessageId}:{})})});
};
function validateAcademicPage<T extends {id:number}>(response:{items:T[];next_before?:number|null},before?:number,dateOrdered=false):{items:T[];next_before:number|null}{
 const cursor=response?.next_before??null;
 if(!Array.isArray(response?.items)||
    response.items.some(item=>!item||!Number.isSafeInteger(item.id)||item.id<=0)||
    (cursor!==null&&(!Number.isSafeInteger(cursor)||cursor<=0))||
    (response.items.length===0&&cursor!==null)||
    (new Set(response.items.map(item=>item.id)).size!==response.items.length)||
    (cursor!==null&&!response.items.some(item=>item.id===cursor))||
    (before!==undefined&&(dateOrdered?(cursor===before||response.items.some(item=>item.id===before)):(response.items.some(item=>item.id>=before)||(cursor!==null&&cursor>=before)))))
  throw Error("Akademik kayıt sunucusundan geçersiz sayfa alındı. Tekrar deneyin.");
 return {items:response.items,next_before:cursor};
}
export const getCourses=async(t:string,before?:number)=>{
 if(before!==undefined&&(!Number.isSafeInteger(before)||before<=0))throw Error("Geçersiz ders sayfa kimliği.");
 const r=await req<{items:Course[];next_before?:number|null}>("/academic/courses"+(before!==undefined?"?before="+encodeURIComponent(before):""),t);
 return validateAcademicPage(r,before,true);
};
export const getAcademicMessages=async(t:string,id:number,before?:number)=>{
 if(!Number.isSafeInteger(id)||id<=0||(before!==undefined&&(!Number.isSafeInteger(before)||before<=0)))throw Error("Geçersiz ders veya sayfa kimliği.");
 const r=await req<{items:Array<{id:number;role:string;content:string;created_at:string}>;next_before?:number|null}>(`/academic/courses/${id}/messages`+(before!==undefined?"?before="+encodeURIComponent(before):""),t);
 const page=validateAcademicPage(r,before);
 if(page.items.some((item,index)=>typeof item.role!=="string"||typeof item.content!=="string"||
   (index>0&&item.id<=page.items[index-1].id)))
  throw Error("Akademik mesaj sunucusundan geçersiz kayıt alındı. Tekrar deneyin.");
 return page;
};
export function askAcademic(t:string,courseId:number,message:string){
 if(!Number.isSafeInteger(courseId)||courseId<=0||!message.trim())throw Error("Geçersiz ders veya boş soru.");
 return req<any>(`/academic/courses/${courseId}/ask`,t,{method:"POST",body:JSON.stringify({message})});
}
export function mediaUploadUrl(patientId:number){return API_BASE+`/patients/${patientId}/media`;}


export type ChatAction={
 action:"expert-response"|"proposal"|"complete"|"block"|"unblock"|"report"|"delete"|"restore"|"review";
 decision?:"ACCEPT"|"REJECT";start_option?:"NOW"|"30M"|"1H"|"3H"|"TODAY";proposal_note?:string;
 completion_action?:"COMPLETE"|"CONTINUE"|"DISPUTE";
 reason?:"HARASSMENT"|"PROFANITY"|"SPAM"|"INAPPROPRIATE"|"OTHER";detail?:string;rating?:number;comment?:string;
};
export async function performChatAction(token:string,id:number,payload:ChatAction){
 if(!Number.isSafeInteger(id)||id<=0)throw Error("Geçersiz görüşme.");
 const response=await req<{ok:boolean}>(`/consultations/${id}/actions`,token,{method:"POST",body:JSON.stringify(payload)});
 if(response.ok!==true)throw Error("İşlem doğrulanamadı; görüşmeyi yenileyin.");
 return response;
}
export function chatImageSource(token:string,caseId:number,messageId:number){
 if(!Number.isSafeInteger(caseId)||caseId<=0||!Number.isSafeInteger(messageId)||messageId<=0)throw Error("Geçersiz ek kimliği.");
 return {uri:API_BASE+`/consultations/${caseId}/attachments/${messageId}`,headers:{Authorization:"Bearer "+token}};
}
export function sharedCaseImageSource(token:string,caseId:number,linkId:number){
 if(!Number.isSafeInteger(caseId)||caseId<=0||!Number.isSafeInteger(linkId)||linkId<=0)throw Error("Geçersiz vaka görseli kimliği.");
 return {uri:API_BASE+`/consultations/${caseId}/shared-media/${linkId}`,headers:{Authorization:"Bearer "+token}};
}
export function sendChatImage(token:string,caseId:number,file:ChatFile,replyTo?:number){
 if(!/^image\/(jpeg|png|webp)$/.test(file.type))return Promise.reject(Error("Geçerli bir hasta görüntüsü seçin."));
 return sendChatFile(token,caseId,file,replyTo);
}
export async function sendChatFile(token:string,caseId:number,file:ChatFile,replyTo?:number){
 if(!Number.isSafeInteger(caseId)||caseId<=0||(replyTo!==undefined&&(!Number.isSafeInteger(replyTo)||replyTo<=0)))throw Error("Geçersiz görüşme veya yanıt kimliği.");
 const checked=validateChatFile(file),body=new FormData();
 body.append("file",{uri:checked.uri,name:checked.name,type:checked.type} as any);
 if(replyTo)body.append("reply_to_message_id",String(replyTo));
 const result=await req<{ok:boolean;message:ChatMessage}>(`/consultations/${caseId}/attachments`,token,{method:"POST",body});
 if(result.ok!==true||!Number.isSafeInteger(result.message?.id)||result.message.id<=0)throw Error("Ek kaydı doğrulanamadı. Tekrar göndermeden önce görüşmeyi kontrol edin.");
 return result;
}
export async function getDeletedChats(token:string){
 const result=await req<{items:Array<{id:number;status:string;specialty:string;recover_until:string}>}>("/messages/deleted",token);
 if(!Array.isArray(result.items)||result.items.some(item=>!Number.isSafeInteger(item?.id)||item.id<=0))throw Error("Silinen görüşmeler alınamadı.");
 return result;
}

export async function analyzeSelectedPatientMedia(token:string,patientId:number,mediaIds:number[],toothNumber?:string,clinicalNotes?:string){
 if(!Number.isSafeInteger(patientId)||patientId<=0||!Array.isArray(mediaIds)||mediaIds.length<1||mediaIds.length>4||new Set(mediaIds).size!==mediaIds.length||mediaIds.some(id=>!Number.isSafeInteger(id)||id<=0))throw Error('1 ile 4 arasında farklı klinik görüntü seçin.');
 if(toothNumber!==undefined&&(typeof toothNumber!=="string"||toothNumber.length>10))throw Error('Diş numarası en fazla 10 karakter olabilir.');
 if(clinicalNotes!==undefined&&(typeof clinicalNotes!=="string"||clinicalNotes.length>4000))throw Error('Klinik bilgi en fazla 4000 karakter olabilir.');
 const body:{media_ids:number[];tooth_number?:string;clinical_notes?:string}={media_ids:mediaIds};
 if(toothNumber?.trim())body.tooth_number=toothNumber.trim();
 if(clinicalNotes?.trim())body.clinical_notes=clinicalNotes.trim();
 const result=await req<{ok:boolean;analysis_id:number}>(`/patients/${patientId}/media/analyze`,token,{method:'POST',body:JSON.stringify(body)});
 if(!result.ok||!Number.isSafeInteger(result.analysis_id)||result.analysis_id<=0)throw Error('Analiz kaydı doğrulanamadı. Geçmişi kontrol edin.');
 return result;
}
export async function deleteAllPatientMedia(token:string,patientId:number){
 if(!Number.isSafeInteger(patientId)||patientId<=0)throw Error('Geçersiz hasta kimliği.');
 const result=await req<{ok:boolean}>(`/patients/${patientId}/media`,token,{method:'DELETE'});
 if(result.ok!==true)throw Error('Silme işlemi doğrulanamadı. Galeriyi yenileyin.');
 return result;
}

// Reuse the authenticated multipart transport for native profile documents.
export {req as modernRequest};
