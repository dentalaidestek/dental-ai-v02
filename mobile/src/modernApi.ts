import {ChatFile,validateChatFile} from "./chatFiles";
import {ApiError,API_BASE} from './api';
import {revalidateSession} from './sessionExpiry';
import {MISSING_API_ROUTE_MESSAGE} from './apiCompatibility';
import {normalizeNotificationReadAt} from "./notificationState";
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
   const rawDetail=typeof b?.detail==="string"?b.detail:(typeof b?.detail?.message==="string"?b.detail.message:"");
   // Mirror api.ts: a bare 404 "Not Found" means the deployed server predates this route.
   const detail=(r.status===404&&(!rawDetail||rawDetail==="Not Found"))?MISSING_API_ROUTE_MESSAGE:(rawDetail||"İstek başarısız.");
   throw new ApiError(r.status,detail);
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
export type SupportTicketStatus="OPEN"|"IN_PROGRESS"|"USER_REPLIED"|"ANSWERED"|"CLOSED";
export type SupportTicket={id:number;subject:string;initial_message:string;status:SupportTicketStatus;created_at:string;updated_at:string;last_message?:string;unread_count:number;can_reply:boolean};
export type SupportMessage={id:number;sender_role:"USER"|"ADMIN";message:string;created_at:string};
export type SupportReport={id:number;case_id:number|null;reason:string;detail:string;status:string;created_at:string;ticket_id:number|null;unread_count:number};
export type SupportConversationOption={id:number;other_display_name:string;status:string};
const supportStatuses:readonly SupportTicketStatus[]=["OPEN","IN_PROGRESS","USER_REPLIED","ANSWERED","CLOSED"];
const supportStatusValid=(value:unknown):value is SupportTicketStatus=>typeof value==="string"&&supportStatuses.includes(value as SupportTicketStatus);
const supportIdValid=(value:unknown):value is number=>typeof value==="number"&&Number.isSafeInteger(value)&&value>0;
const supportDateValid=(value:unknown):value is string=>typeof value==="string"&&value.length<=64&&Number.isFinite(Date.parse(value));
const supportCountValid=(value:unknown):value is number=>typeof value==="number"&&Number.isSafeInteger(value)&&value>=0;
const supportRequestKeyValid=(value:unknown):value is string=>typeof value==="string"&&/^[A-Za-z0-9_-]{16,96}$/.test(value);
const supportTicketSummaryValid=(value:unknown):value is SupportTicket=>{
 if(!value||typeof value!=="object")return false;
 const x=value as Record<string,unknown>;
 return supportIdValid(x.id)&&typeof x.subject==="string"&&x.subject.length<=160&&
  typeof x.initial_message==="string"&&x.initial_message.length<=4000&&supportStatusValid(x.status)&&
  supportDateValid(x.created_at)&&supportDateValid(x.updated_at)&&
  (x.last_message===undefined||(typeof x.last_message==="string"&&x.last_message.length<=4000))&&
  supportCountValid(x.unread_count)&&typeof x.can_reply==="boolean";
};
const supportMessageValid=(value:unknown):value is SupportMessage=>{
 if(!value||typeof value!=="object")return false;
 const x=value as Record<string,unknown>;
 return supportIdValid(x.id)&&(x.sender_role==="USER"||x.sender_role==="ADMIN")&&
  typeof x.message==="string"&&x.message.length<=4000&&supportDateValid(x.created_at);
};
const supportKey=()=>("support_"+Date.now().toString(36)+"_"+Math.random().toString(36).slice(2,18)).replace(/[^A-Za-z0-9_-]/g,"");
export const getSupportTickets=async(t:string,before?:number)=>{
 if(before!==undefined&&!supportIdValid(before))throw Error("Geçersiz destek sayfa kimliği.");
 const r=await req<any>("/support/tickets?limit=50"+(before!==undefined?"&before_id="+encodeURIComponent(before):""),t);
 if(!Array.isArray(r?.items)||r.items.length>50||!supportCountValid(r.total)||r.total!==r.items.length||
    typeof r.has_more!=="boolean"||r.items.some((x:unknown)=>!supportTicketSummaryValid(x)))
  throw Error("Destek talepleri doğrulanamadı.");
 const ids=(r.items as SupportTicket[]).map(x=>x.id);
 if(new Set(ids).size!==ids.length||ids.some((id:number,index:number)=>index>0&&id>=ids[index-1])||
    (before!==undefined&&ids.some((id:number)=>id>=before)))
  throw Error("Destek talebi sırası veya hesap kapsamı doğrulanamadı.");
 const next=r.next_before_id;
 if(r.has_more?(!supportIdValid(next)||ids.length===0||next!==ids[ids.length-1]||(before!==undefined&&next>=before)):next!==null)
  throw Error("Destek talepleri sayfalama imleci ilerlemiyor.");
 return r as {items:SupportTicket[];total:number;has_more:boolean;next_before_id:number|null};
};
export const getSupportReports=async(t:string)=>{
 const r=await req<any>("/support/reports",t);
 if(!Array.isArray(r?.items)||r.items.length>100||!supportCountValid(r.total)||r.total!==r.items.length||
    r.items.some((x:unknown)=>{if(!x||typeof x!=="object")return true;const v=x as Record<string,unknown>;return !supportIdValid(v.id)||
      !(v.case_id===null||supportIdValid(v.case_id))||typeof v.reason!=="string"||v.reason.length>120||
      typeof v.detail!=="string"||v.detail.length>4000||typeof v.status!=="string"||!supportDateValid(v.created_at)||
      !(v.ticket_id===null||supportIdValid(v.ticket_id))||!supportCountValid(v.unread_count)}))
  throw Error("Bildirimler doğrulanamadı.");
 const ids=r.items.map((x:any)=>x.id);
 if(new Set(ids).size!==ids.length||ids.some((id:number,index:number)=>index>0&&id>=ids[index-1]))
  throw Error("Bildirim sırası doğrulanamadı.");
 return r as {items:SupportReport[];total:number};
};
export const getSupportConversationOptions=async(t:string)=>{
 const r=await req<any>("/support/conversation-options",t);
 if(!Array.isArray(r?.items)||r.items.length>100||r.items.some((x:unknown)=>!x||typeof x!=="object"||
    !supportIdValid((x as Record<string,unknown>).id)||typeof (x as Record<string,unknown>).other_display_name!=="string"||
    ((x as Record<string,unknown>).other_display_name as string).length>160||typeof (x as Record<string,unknown>).status!=="string"))
  throw Error("Konuşma listesi doğrulanamadı.");
 const ids=r.items.map((x:any)=>x.id);
 if(new Set(ids).size!==ids.length)throw Error("Konuşma listesinde yinelenen kayıt var.");
 return r as {items:SupportConversationOption[]};
};
export const createSupportTicket=async(t:string,subject:string,message:string,key=supportKey(),caseId?:number)=>{
 if(!subject.trim()||subject.trim().length>160||!message.trim()||message.trim().length>4000||
    !supportRequestKeyValid(key)||(caseId!==undefined&&!supportIdValid(caseId)))
  throw Error("Konu, açıklama veya konuşma seçimini kontrol edin.");
 const r=await req<any>("/support/tickets",t,{method:"POST",body:JSON.stringify({subject:subject.trim(),message:message.trim(),request_key:key,case_id:caseId??null})});
 if(!r?.ok||!supportIdValid(r.ticket_id)||!(r.status==="OPEN"||r.status==="REPLAYED")||typeof r.replayed!=="boolean")
  throw Error("Destek talebi kayıt makbuzu doğrulanamadı.");
 return r as {ok:boolean;ticket_id:number;status:string;replayed:boolean};
};
export const getSupportTicket=async(t:string,id:number,before?:number)=>{
 if(!supportIdValid(id)||(before!==undefined&&!supportIdValid(before)))throw Error("Geçersiz destek talebi.");
 const r=await req<any>("/support/tickets/"+id+(before!==undefined?"?before_id="+encodeURIComponent(before):""),t);
 const ticket=r?.ticket;
 if(!ticket||ticket.id!==id||typeof ticket.subject!=="string"||ticket.subject.length>160||
    typeof ticket.initial_message!=="string"||ticket.initial_message.length>4000||!supportStatusValid(ticket.status)||
    !supportDateValid(ticket.created_at)||!supportDateValid(ticket.updated_at)||typeof ticket.can_reply!=="boolean"||
    !Array.isArray(r.messages)||r.messages.length>20||r.messages.some((m:unknown)=>!supportMessageValid(m))||
    typeof r.has_more!=="boolean"||!supportCountValid(r.unread_count))
  throw Error("Destek konuşması doğrulanamadı.");
 const ids=(r.messages as SupportMessage[]).map(m=>m.id);
 if(new Set(ids).size!==ids.length||ids.some((messageId:number,index:number)=>index>0&&messageId<=ids[index-1])||
    (before!==undefined&&ids.some((messageId:number)=>messageId>=before)))
  throw Error("Destek mesaj sırası veya sayfa kapsamı doğrulanamadı.");
 if(r.has_more?(!supportIdValid(r.next_before_id)||ids.length!==20||r.next_before_id!==ids[0]||(before!==undefined&&r.next_before_id>=before)):r.next_before_id!==null)
  throw Error("Destek mesajı sayfalama imleci ilerlemiyor.");
 return r as {ticket:SupportTicket;messages:SupportMessage[];has_more:boolean;next_before_id:number|null;unread_count:number};
};
export const markSupportTicketRead=async(t:string,id:number,through?:number)=>{
 if(!supportIdValid(id)||(through!==undefined&&!supportIdValid(through)))throw Error("Geçersiz destek okuma sınırı.");
 const r=await req<any>("/support/tickets/"+id+"/read"+(through!==undefined?"?through_message_id="+encodeURIComponent(through):""),t,{method:"POST"});
 if(!r?.ok||r.ticket_id!==id||!supportCountValid(r.unread_count))throw Error("Destek okundu makbuzu doğrulanamadı.");
 return r as {ok:boolean;ticket_id:number;unread_count:number};
};
export const replySupportTicket=async(t:string,id:number,message:string,key=supportKey())=>{
 if(!supportIdValid(id)||!message.trim()||message.trim().length>4000||!supportRequestKeyValid(key))
  throw Error("Yanıt alanını kontrol edin.");
 const r=await req<any>("/support/tickets/"+id+"/reply",t,{method:"POST",body:JSON.stringify({message:message.trim(),request_key:key})});
 if(!r?.ok||r.ticket_id!==id||!supportIdValid(r.message_id)||
    !(r.status==="USER_REPLIED"||r.status==="REPLAYED")||typeof r.replayed!=="boolean")
  throw Error("Destek yanıtı kayıt makbuzu doğrulanamadı.");
 return r as {ok:boolean;ticket_id:number;message_id:number;status:string;replayed:boolean};
};

export type Notice={id:number;title:string;message:string;notice_type:string;target_url?:string|null;read_at?:string|null;is_read?:boolean;created_at:string};
export type Expert={user_id:number;display_name:string;specialty:string;academic_title?:string|null;institution?:string|null;bio?:string|null;availability:string;consultation_price:number;rating_avg?:number|null;review_count:number};
export type Consultation={id:number;other_user_id:number;other_display_name:string;specialty:string;tooth_region?:string|null;status:string;status_key?:string;status_label?:string;question:string;requested_at:string;last_message?:string|null;last_message_at?:string|null;last_message_id?:number;messages_deleted_at?:string|null;unread_count:number};
export type ChatMessage={id:number;sender_user_id:number;message_type:string;content:string;reply_to_message_id?:number|null;created_at:string;has_media?:boolean;client_message_id?:string};
export type AnalysisHistory={id:number;patient_id:number;patient_name:string;tooth_number?:string|null;status:string;clinical_notes?:string|null;created_at:string;is_voice_review?:boolean};
export type Course={id:number;title:string;description?:string|null;updated_at:string;material_count:number};
export const registerPushDevice=(t:string,deviceId:string,expoPushToken:string,platform:"android"|"ios",installationProof:string)=>{
 if(!/^[0-9a-f]{64}$/.test(installationProof))throw Error("Geçersiz cihaz kurulum doğrulaması.");
 return req<{ok:boolean;delivery_enabled?:boolean}>("/push/devices",t,{method:"POST",body:JSON.stringify({device_id:deviceId,expo_push_token:expoPushToken,platform,installation_proof:installationProof})});
};
export const claimPushDevice=(t:string,deviceId:string,installationProof:string)=>{
 if(!/^[0-9a-f]{64}$/.test(installationProof))throw Error("Geçersiz cihaz kurulum doğrulaması.");
 return req<{ok:boolean;revoked_previous_owners:number}>("/push/devices/claim",t,{method:"POST",body:JSON.stringify({device_id:deviceId,installation_proof:installationProof})});
};
export const unregisterPushDevice=(t:string,deviceId:string)=>
 req<{ok:boolean}>("/push/devices/"+encodeURIComponent(deviceId),t,{method:"DELETE"});
export const getNotifications=async(t:string,noticeId?:number)=>{
 if(noticeId!==undefined&&(!Number.isSafeInteger(noticeId)||noticeId<=0))throw Error("Geçersiz bildirim kimliği.");
 const r=await req<any>("/notifications"+(noticeId!==undefined?"?notice_id="+encodeURIComponent(noticeId):""),t);
 const items=r?.items??r?.notifications;
 if(!Array.isArray(items)||items.some((n:unknown)=>!n||typeof n!=="object"||!Number.isSafeInteger((n as Notice).id)||typeof (n as Notice).title!=="string"||typeof (n as Notice).message!=="string"||((n as Notice).is_read!==undefined&&typeof (n as Notice).is_read!=="boolean")))
  throw Error("Bildirim sunucusundan geçersiz liste alındı. Tekrar deneyin.");
 const unread=Number(r?.unread??r?.unread_count??0);
 if(!Number.isSafeInteger(unread)||unread<0)throw Error("Bildirim sunucusundan geçersiz okunmamış sayısı alındı.");
 return {items:items.map((n:Notice)=>({...n,read_at:normalizeNotificationReadAt(n)})) as Notice[],unread};
};
export const getNotificationUnreadCount=async(t:string)=>{
 const result=await req<{unread_count:number}>("/notifications/unread-count",t);
 if(!Number.isSafeInteger(result?.unread_count)||result.unread_count<0)
  throw Error("Bildirim sayısı doğrulanamadı.");
 return result.unread_count;
};
export const getMessagesUnreadCount=async(t:string)=>{
 // Web /messages/unread-count parity: red count badge on the Mesajlar tab.
 const result=await req<{count:number}>("/messages/unread-count",t);
 return {count:Number.isSafeInteger(result?.count)&&result.count>0?result.count:0};
};
export const markNotificationRead=(t:string,id:number)=>{
 if(!Number.isSafeInteger(id)||id<=0)throw Error("Geçersiz bildirim kimliği.");
 return req<{ok:boolean}>("/notifications/"+id+"/read",t,{method:"POST"});
};
export const markAllNotificationsRead=async(t:string,seenBefore:string)=>{
 const timestamp=Date.parse(seenBefore);
 if(!Number.isFinite(timestamp))throw Error("Geçersiz bildirim zaman sınırı.");
 const result=await req<{ok:boolean;read_count:number;unread_count:number}>("/notifications/read-all",t,{
  method:"POST",body:JSON.stringify({seen_before:new Date(timestamp).toISOString()})
 });
 if(!result?.ok||!Number.isSafeInteger(result.read_count)||result.read_count<0||!Number.isSafeInteger(result.unread_count)||result.unread_count<0)
  throw Error("Bildirimlerin okundu durumu doğrulanamadı.");
 return result;
};
export const getAnalysisHistory=async(t:string,before?:number,patientId?:number,toothNumber?:string)=>{
 if(patientId!==undefined&&(!Number.isSafeInteger(patientId)||patientId<=0))throw Error("Geçersiz hasta kimliği.");
 if(toothNumber!==undefined&&!/^(?:[1-4][1-8]|[5-8][1-5])$/.test(toothNumber))throw Error("Geçersiz FDI diş numarası.");
 if(before!==undefined&&(!Number.isSafeInteger(before)||before<=0))throw Error("Geçersiz analiz sayfa kimliği.");
 const r=await req<{items:AnalysisHistory[];total:number;next_before?:number|null}>("/analyses?limit=50"+(before!==undefined?`&before=${encodeURIComponent(before)}`:"")+(patientId!==undefined?`&patient_id=${patientId}`:"")+(toothNumber?`&tooth_number=${toothNumber}`:""),t);
 // Older deployed servers omit next_before; treat this as the final page.
 const next_before=r?.next_before??null;
 if(!Array.isArray(r?.items)||r.items.length>50||
    r.items.some(n=>!n||!Number.isSafeInteger(n.id)||n.id<=0||!Number.isSafeInteger(n.patient_id)||typeof n.status!=="string"||(n.is_voice_review!==undefined&&typeof n.is_voice_review!=="boolean")||(patientId!==undefined&&n.patient_id!==patientId)||(toothNumber!==undefined&&n.tooth_number!==toothNumber))||
    (r.items.length===0&&next_before!==null)||
    (before!==undefined&&(r.items.some(n=>n.id>=before)||(next_before!==null&&next_before>=before)))||
    (next_before!==null&&(!Number.isSafeInteger(next_before)||next_before<=0))||
    !Number.isSafeInteger(r.total)||r.total<0)
   throw Error("Analiz sunucusundan geçersiz liste alındı. Tekrar deneyin.");
 return {...r,next_before};
};

export type PatientAnalysisHistoryCursor=
 | {kind:"stable";value:string}
 | {kind:"legacy";value:number};
export type PatientAnalysisHistoryPage={items:AnalysisHistory[];total:number;next:PatientAnalysisHistoryCursor|null};
const validStableAnalysisHistoryCursor=(value:unknown):value is string=>
 typeof value==="string"&&value.length>=24&&value.length<=192&&/^[A-Za-z0-9_-]+$/.test(value);

/**
 * Web-parity patient history uses the same descending (created_at, id)
 * boundary as patient_detail. Numeric-ID pagination remains a compatibility
 * fallback for older deployed API servers.
 */
export const getPatientAnalysisHistoryPage=async(
 t:string,patientId:number,toothNumber?:string,cursor?:PatientAnalysisHistoryCursor
):Promise<PatientAnalysisHistoryPage>=>{
 if(!Number.isSafeInteger(patientId)||patientId<=0)throw Error("Geçersiz hasta kimliği.");
 if(toothNumber!==undefined&&!/^(?:[1-4][1-8]|[5-8][1-5])$/.test(toothNumber))throw Error("Geçersiz FDI diş numarası.");
 if(cursor!==undefined&&(!cursor||typeof cursor!=="object"||
    (cursor.kind==="stable"&&!validStableAnalysisHistoryCursor(cursor.value))||
    (cursor.kind==="legacy"&&(!Number.isSafeInteger(cursor.value)||cursor.value<=0))||
    (cursor.kind!=="stable"&&cursor.kind!=="legacy")))
  throw Error("Analiz geçmişi sayfalama imleci geçersiz.");
 const stableRequest=cursor?.kind!=="legacy";
 const beforeQuery=cursor?.kind==="stable"
  ?"&before_cursor="+encodeURIComponent(cursor.value)
  :cursor?.kind==="legacy"
   ?"&before="+encodeURIComponent(cursor.value)
   :"";
 const r=await req<{items:AnalysisHistory[];total:number;next_cursor?:string|null;next_before?:number|null}>(
  "/analyses?limit=50"+(stableRequest?"&stable_order=true":"")+
  "&patient_id="+encodeURIComponent(patientId)+
  (toothNumber?"&tooth_number="+encodeURIComponent(toothNumber):"")+beforeQuery,t
 );
 if(!Array.isArray(r?.items)||r.items.length>50||
    !Number.isSafeInteger(r.total)||r.total<0||r.total<r.items.length)
  throw Error("Analiz sunucusundan geçersiz liste alındı. Tekrar deneyin.");
 const ids=new Set<number>();
 for(const item of r.items){
  if(!item||!Number.isSafeInteger(item.id)||item.id<=0||ids.has(item.id)||
     !Number.isSafeInteger(item.patient_id)||item.patient_id!==patientId||
     typeof item.status!=="string"||
     (item.is_voice_review!==undefined&&typeof item.is_voice_review!=="boolean")||
     (toothNumber!==undefined&&item.tooth_number!==toothNumber))
   throw Error("Analiz sunucusundan hasta kapsamı dışında veya tekrarlanan kayıt alındı.");
  ids.add(item.id);
 }
 let next:PatientAnalysisHistoryCursor|null=null;
 const legacyFieldFallback=stableRequest&&cursor===undefined&&r.next_cursor===null&&r.next_before!==undefined&&r.next_before!==null;
 if(stableRequest&&Object.prototype.hasOwnProperty.call(r,"next_cursor")&&!legacyFieldFallback){
  if((r.next_before!==undefined&&r.next_before!==null)||
     (r.next_cursor!==null&&!validStableAnalysisHistoryCursor(r.next_cursor))||
     (r.next_cursor!==null&&r.items.length!==50)||
     (cursor?.kind==="stable"&&r.next_cursor===cursor.value))
   throw Error("Analiz sunucusundan geçersiz kararlı sayfalama imleci alındı.");
  next=r.next_cursor===null?null:{kind:"stable",value:r.next_cursor};
 }else{
  if(cursor?.kind==="stable")throw Error("Analiz sunucusu kararlı geçmiş imlecini devam ettiremedi.");
  const legacy=r.next_before??null;
  const lastId=r.items.length?r.items[r.items.length-1].id:null;
  if((legacy!==null&&(!Number.isSafeInteger(legacy)||legacy<=0||r.items.length!==50||lastId!==legacy))||
     (legacy!==null&&cursor?.kind==="legacy"&&legacy>=cursor.value)||
     (cursor?.kind==="legacy"&&r.items.some(item=>item.id>=cursor.value)))
   throw Error("Analiz sunucusundan geçersiz eski sayfalama imleci alındı.");
  next=legacy===null?null:{kind:"legacy",value:legacy};
 }
 if(r.items.length===0&&next!==null)throw Error("Boş analiz sayfası devam imleci içeremez.");
 return {items:r.items,total:r.total,next};
};

export type DeleteMediaResult={
 ok:true;
 media_id:number;
 already_deleted?:boolean;
 storage_cleanup_pending?:boolean|null;
};
export const deleteMedia=async(t:string,patientId:number,mediaId:number):Promise<DeleteMediaResult>=>{
 if(!Number.isSafeInteger(patientId)||patientId<=0||!Number.isSafeInteger(mediaId)||mediaId<=0)
  throw Error("Geçersiz hasta veya klinik medya kimliği.");
 const result=await req<DeleteMediaResult>(`/patients/${patientId}/media/${mediaId}`,t,{method:"DELETE"});
 if(!result||result.ok!==true||result.media_id!==mediaId||
    (result.already_deleted!==undefined&&typeof result.already_deleted!=="boolean")||
    (result.storage_cleanup_pending!==undefined&&result.storage_cleanup_pending!==null&&typeof result.storage_cleanup_pending!=="boolean"))
  throw Error("Klinik görsel silme yanıtı doğrulanamadı. Galeriyi yenileyip durumu kontrol edin.");
 return result;
};
export type PatientMediaGalleryItem={
 id:number;
 filename:string;
 media_type:"PHOTO"|"RADIOGRAPH";
 tooth_number?:string|null;
 note?:string|null;
 uploaded_at?:string|null;
 url:string;
 thumbnail_url:string;
};
export const getMedia=async(t:string,p:number,before?:number):Promise<{items:PatientMediaGalleryItem[];next_before:number|null}>=>{
 if(!Number.isSafeInteger(p)||p<=0||(before!==undefined&&(!Number.isSafeInteger(before)||before<=0)))
  throw Error("Geçersiz hasta veya sayfa kimliği.");
 const r=await req<{items:any[];next_before:number|null}>(`/patients/${p}/media?limit=40`+(before!==undefined?`&before=${encodeURIComponent(before)}`:""),t);
 const rawCursor=r?.next_before;
 const items=r?.items;
 if(!r||!Object.prototype.hasOwnProperty.call(r,"next_before")||
   !(rawCursor===null||(typeof rawCursor==="number"&&Number.isSafeInteger(rawCursor)&&rawCursor>0))||
   !Array.isArray(items)||items.length>40||
   new Set(items.map(m=>m?.id)).size!==items.length)
  throw Error("Klinik medya sunucusundan geçersiz liste alındı.");
 const cursor:number|null=rawCursor;
 let previousId=before??Number.MAX_SAFE_INTEGER;
 for(const media of items){
  if(!media||!Number.isSafeInteger(media.id)||media.id<=0||media.id>=previousId||
    !["PHOTO","RADIOGRAPH"].includes(media.media_type)||
    (media.filename!=null&&typeof media.filename!=="string")||
    (media.original_filename!=null&&typeof media.original_filename!=="string")||
    (media.note!=null&&(typeof media.note!=="string"||media.note.length>2000))||
    (media.tooth_number!=null&&(typeof media.tooth_number!=="string"||media.tooth_number.length>10))||
    (media.uploaded_at!=null&&typeof media.uploaded_at!=="string"))
   throw Error("Klinik medya sunucusundan geçersiz liste alındı.");
  previousId=media.id;
 }
 if(cursor!==null&&(!items.length||cursor!==items[items.length-1].id))
  throw Error("Klinik medya sunucusundan geçersiz liste alındı. Sayfalama imleci doğrulanamadı.");
 return {items:items.map(media=>({
  // Keep the client model to the fields used by the clinical gallery. Never
  // propagate accidental server additions such as owner IDs or storage keys.
  id:media.id,
  filename:media.filename||media.original_filename||"",
  media_type:media.media_type,
  tooth_number:media.tooth_number??null,
  note:media.note??null,
  uploaded_at:media.uploaded_at??null,
  // Ignore server-provided URLs; only same-origin authenticated API paths are used.
  url:`${API_BASE}/patients/${p}/media/${media.id}/file`,
  thumbnail_url:`${API_BASE}/patients/${p}/media/${media.id}/thumbnail`
 })),next_before:cursor};
};
export const getExperts=(t:string,q="",opts?:{specialty?:string;available?:boolean})=>req<{items:Expert[]}>("/experts?q="+encodeURIComponent(q)+(opts&&opts.specialty?"&specialty="+encodeURIComponent(opts.specialty):"")+(opts&&opts.available?"&available=true":""),t);
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
 if(!Array.isArray(r?.items)||r.items.length>50||r.items.some(item=>!item||!Number.isSafeInteger(item.id)||item.id<=0||
   (item.last_message_id!==undefined&&(!Number.isSafeInteger(item.last_message_id)||item.last_message_id<0)))||
   new Set(r.items.map(item=>item.id)).size!==r.items.length||
   (cursor!==null&&(!Number.isSafeInteger(cursor)||cursor<=0||!r.items.some(item=>item.id===cursor)))||
   (r.items.length===0&&cursor!==null)||
   (before!==undefined&&(r.items.some(item=>item.id===before)||cursor===before)))
  throw Error("Uzman görüşmeleri sunucusundan geçersiz liste alındı. Tekrar deneyin.");
 return {next_before:cursor,items:r.items.map(item=>({...item,other_display_name:String(item.other_display_name||item.other_name||"Kullanıcı"),last_message_id:Number.isSafeInteger(item.last_message_id)?item.last_message_id:0,unread_count:Math.max(0,Number(item.unread_count)||0)})) as Consultation[]};
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
export const getConsultationUpdates=async(t:string,id:number,afterId:number)=>{
 if(!Number.isSafeInteger(id)||id<=0||!Number.isSafeInteger(afterId)||afterId<0)
  throw Error("Geçersiz görüşme veya devam mesajı.");
 const result=await req<{case:any;messages:ChatMessage[];has_more:boolean;next_after?:number|null}>(`/consultations/${id}/messages-live?after_id=${encodeURIComponent(afterId)}`,t,{method:'GET'});
 const cursor=result?.next_after??null;
 if(!result?.case||result.case.id!==id||typeof result.case.status!=="string"||
    !Array.isArray(result.messages)||result.messages.length>100||typeof result.has_more!=="boolean"||
    result.messages.some((m,i)=>!m||!Number.isSafeInteger(m.id)||m.id<=afterId||
      !Number.isSafeInteger(m.sender_user_id)||m.sender_user_id<=0||
      typeof m.message_type!=="string"||typeof m.created_at!=="string"||
      (m.content!==null&&m.content!==undefined&&typeof m.content!=="string")||
      (m.reply_to_message_id!==null&&m.reply_to_message_id!==undefined&&(!Number.isSafeInteger(m.reply_to_message_id)||m.reply_to_message_id<=0))||
      (i>0&&m.id<=result.messages[i-1].id))||
    new Set(result.messages.map(m=>m.id)).size!==result.messages.length||
    (result.has_more&&(cursor===null||!result.messages.length||!Number.isSafeInteger(cursor)||cursor!==result.messages[result.messages.length-1].id||cursor<=afterId))||
    (!result.has_more&&cursor!==null))
  throw Error("Görüşme yeni mesaj akışından geçersiz sayfa alındı.");
 return {...result,next_after:cursor};
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
export const getConsultationMessageReceipt=async(t:string,id:number,clientMessageId:string)=>{
 if(!Number.isSafeInteger(id)||id<=0||!/^[A-Za-z0-9_-]{16,96}$/.test(clientMessageId||""))
  throw Error("Geçersiz görüşme veya mesaj istek anahtarı.");
 const result=await req<{message:({case_id:number;client_message_id:string;id:number;sender_user_id:number;message_type:string;content:string;reply_to_message_id:number|null;created_at:string;has_media:boolean})|null;deleted:boolean}>(`/consultations/${id}/message-receipt?client_message_id=${encodeURIComponent(clientMessageId)}`,t);
 if(!result||typeof result.deleted!=="boolean"||(result.deleted&&result.message!==null))
  throw Error("Mesaj gönderim makbuzu doğrulanamadı.");
 if(result.message!==null){
  const message:any=result.message;
  const allowed=new Set(["case_id","client_message_id","id","sender_user_id","message_type","content","reply_to_message_id","created_at","has_media"]);
  if(!message||typeof message!=="object"||Array.isArray(message)||Object.keys(message).some(key=>!allowed.has(key))||
     message.case_id!==id||message.client_message_id!==clientMessageId||
     !Number.isSafeInteger(message.id)||message.id<=0||
     !Number.isSafeInteger(message.sender_user_id)||message.sender_user_id<=0||
     typeof message.message_type!=="string"||!message.message_type||message.message_type.length>24||
     (typeof message.content!=="string"||message.content.length>4000)||
     !(message.reply_to_message_id===null||Number.isSafeInteger(message.reply_to_message_id)&&message.reply_to_message_id>0)||
     typeof message.created_at!=="string"||!Number.isFinite(Date.parse(message.created_at))||
     typeof message.has_media!=="boolean")
   throw Error("Mesaj gönderim makbuzu doğrulanamadı.");
 }
 return {message:result.message,deleted:result.deleted};
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
 action:"expert-response"|"proposal"|"complete"|"block"|"unblock"|"report"|"delete"|"restore"|"review"|"annotate";
 decision?:"ACCEPT"|"REJECT";start_option?:"NOW"|"30M"|"1H"|"3H"|"TODAY";proposal_note?:string;
 completion_action?:"COMPLETE"|"CONTINUE"|"DISPUTE";
 reason?:"HARASSMENT"|"PROFANITY"|"SPAM"|"INAPPROPRIATE"|"OTHER";detail?:string;rating?:number;comment?:string;
 message_id?:number;annotation_json?:string;
};
export async function performChatAction(token:string,id:number,payload:ChatAction){
 if(!Number.isSafeInteger(id)||id<=0)throw Error("Geçersiz görüşme.");
 const response=await req<{ok:boolean}>(`/consultations/${id}/actions`,token,{method:"POST",body:JSON.stringify(payload)});
 if(response.ok!==true)throw Error("İşlem doğrulanamadı; görüşmeyi yenileyin.");
 return response;
}
export type AvailabilityWatch={id:number;specialty:string};
// Web EXPERT_SPECIALTIES (app/main.py:6653) birebir; watch doğrulaması sunucuda tekrar yapılır.
export const EXPERT_SPECIALTIES:string[]=["Endodonti","Ortodonti","Pedodonti","Periodontoloji","Protetik Diş Tedavisi","Restoratif Diş Tedavisi","Ağız, Diş ve Çene Cerrahisi","Ağız, Diş ve Çene Radyolojisi"];
export async function getAvailabilityWatch(token:string){
 const v=await req<{ok:boolean;watches?:AvailabilityWatch[]}>("/expert-support/availability-watch",token);
 if(v.ok!==true||!Array.isArray(v.watches))throw Error("Bildirim abonelikleri doğrulanamadı.");
 return v.watches;
}
export async function createAvailabilityWatch(token:string,specialty:string){
 if(!specialty.trim())throw Error("Branş seçin.");
 const v=await req<{ok:boolean;specialty?:string;watches?:AvailabilityWatch[]}>("/expert-support/availability-watch",token,{method:"POST",body:JSON.stringify({specialty})});
 if(v.ok!==true||!Array.isArray(v.watches))throw Error("Bildirim isteği kaydedilemedi.");
 return v;
}
export function chatImageSource(token:string,caseId:number,messageId:number){
 if(!Number.isSafeInteger(caseId)||caseId<=0||!Number.isSafeInteger(messageId)||messageId<=0)throw Error("Geçersiz ek kimliği.");
 return {uri:API_BASE+`/consultations/${caseId}/attachments/${messageId}`,headers:{Authorization:"Bearer "+token}};
}
export function sharedCaseImageSource(token:string,caseId:number,linkId:number){
 if(!Number.isSafeInteger(caseId)||caseId<=0||!Number.isSafeInteger(linkId)||linkId<=0)throw Error("Geçersiz vaka görseli kimliği.");
 return {uri:API_BASE+`/consultations/${caseId}/shared-media/${linkId}`,headers:{Authorization:"Bearer "+token}};
}
export function sendChatImage(token:string,caseId:number,file:ChatFile,replyTo?:number,clientMessageId?:string){
 if(!/^image\/(jpeg|png|webp)$/.test(file.type))return Promise.reject(Error("Geçerli bir hasta görüntüsü seçin."));
 return sendChatFile(token,caseId,file,replyTo,clientMessageId);
}
export async function sendChatFile(token:string,caseId:number,file:ChatFile,replyTo?:number,clientMessageId?:string){
 if(!Number.isSafeInteger(caseId)||caseId<=0||(replyTo!==undefined&&(!Number.isSafeInteger(replyTo)||replyTo<=0)))throw Error("Geçersiz görüşme veya yanıt kimliği.");
 const key=clientMessageId||("native-media-"+Date.now().toString(36)+"-"+Math.random().toString(36).slice(2));
 if(!/^[A-Za-z0-9_-]{16,96}$/.test(key))throw Error("Geçersiz ek istek anahtarı.");
 const checked=validateChatFile(file),body=new FormData();
 body.append("file",{uri:checked.uri,name:checked.name,type:checked.type} as any);
 body.append("client_message_id",key);
 if(replyTo)body.append("reply_to_message_id",String(replyTo));
 const result=await req<{ok:boolean;message:ChatMessage;replayed?:boolean}>(`/consultations/${caseId}/attachments`,token,{method:"POST",body});
 const message:any=result?.message;
 if(result?.ok!==true||!Number.isSafeInteger(message?.id)||message.id<=0||
    message.client_message_id!==key||message.has_media!==true||
    !["IMAGE","FILE","VOICE"].includes(message.message_type)||
    typeof message.content!=="string"||message.content.length>180||
    typeof message.created_at!=="string"||!Number.isFinite(Date.parse(message.created_at))||
    (result.replayed!==undefined&&typeof result.replayed!=="boolean"))
  throw Error("Ek kaydı doğrulanamadı. Tekrar göndermeden önce görüşmeyi kontrol edin.");
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
