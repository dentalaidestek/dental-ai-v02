import {ApiError} from './api';
const API_BASE="https://dentalai.tr/api/mobile/v1";
async function req<T>(path:string,token:string,init:RequestInit={}):Promise<T>{
 const headers:any={"Content-Type":"application/json",Authorization:"Bearer "+token,...(init.headers||{})};
 const r=await fetch(API_BASE+path,{...init,headers});
 const raw=await r.text(); let b:any={}; try{b=raw?JSON.parse(raw):{}}catch{}
 if(!r.ok){
  // A feature-specific 401 must not invalidate the global login; /me validates sessions.
  throw new ApiError(r.status,typeof b.detail==="string"?b.detail:(b.detail?.message||"İstek başarısız."));
 }
 return b as T;
}
export type Notice={id:number;title:string;message:string;notice_type:string;target_url?:string|null;read_at?:string|null;created_at:string};
export type Expert={user_id:number;display_name:string;specialty:string;academic_title?:string|null;institution?:string|null;bio?:string|null;availability:string;consultation_price:number;rating_avg?:number|null;review_count:number};
export type Consultation={id:number;other_user_id:number;other_name:string;specialty:string;status:string;question:string;clinical_summary:string;requested_at:string;expert_response_deadline:string;last_message?:string|null;last_message_at?:string|null};
export type ChatMessage={id:number;sender_user_id:number;type:string;content:string;created_at:string};
export type AnalysisHistory={id:number;patient_id:number;patient_name:string;tooth_number?:string|null;status:string;clinical_notes?:string|null;created_at:string};
export type Course={id:number;title:string;description?:string|null;updated_at:string;material_count:number};
export const registerPushDevice=(t:string,deviceId:string,expoPushToken:string,platform:"android"|"ios")=>
 req<{ok:boolean}>("/push/devices",t,{method:"POST",body:JSON.stringify({device_id:deviceId,expo_push_token:expoPushToken,platform})});
export const unregisterPushDevice=(t:string,deviceId:string)=>
 req<{ok:boolean}>("/push/devices/"+encodeURIComponent(deviceId),t,{method:"DELETE"});
export const getNotifications=async(t:string)=>{const r=await req<any>("/notifications",t);const items=r?.items??r?.notifications;if(!Array.isArray(items)||items.some((n:unknown)=>!n||typeof n!=="object"||!Number.isSafeInteger((n as Notice).id)||typeof (n as Notice).title!=="string"||typeof (n as Notice).message!=="string"))throw Error("Bildirim sunucusundan geçersiz liste alındı. Tekrar deneyin.");return {items:items.map((n:Notice&{is_read?:boolean})=>({...n,read_at:n.read_at||(n.is_read?n.created_at:null)})) as Notice[],unread:Number(r.unread??r.unread_count??0)}};
export const markNotificationRead=(t:string,id:number)=>req<{ok:boolean}>("/notifications/"+id+"/read",t,{method:"POST"});
export const getAnalysisHistory=async(t:string,before?:number)=>{const r=await req<{items:AnalysisHistory[];total:number;next_before:number|null}>("/analyses?limit=50"+(before?`&before=${encodeURIComponent(before)}`:""),t);if(!Array.isArray(r?.items)||r.items.some(n=>!n||!Number.isSafeInteger(n.id)||!Number.isSafeInteger(n.patient_id)||typeof n.status!=="string"))throw Error("Analiz sunucusundan geçersiz liste alındı. Tekrar deneyin.");return r;};
export const deleteMedia=(t:string,patientId:number,mediaId:number)=>req<{ok:boolean;media_id:number}>(`/patients/${patientId}/media/${mediaId}`,t,{method:"DELETE"});
export const getMedia=async(t:string,p:number,before?:number)=>{const r=await req<{items:any[];next_before:number|null}>(`/patients/${p}/media`+(before?`?before=${before}`:""),t);return {items:r.items.map(m=>({...m,filename:m.filename||m.original_filename,url:`${API_BASE}/patients/${p}/media/${m.id}/file`})),next_before:r.next_before}};
export const getExperts=(t:string,q="")=>req<{items:Expert[]}>("/experts?q="+encodeURIComponent(q),t);
export const createConsultation=(t:string,payload:{expert_user_id:number;clinical_summary:string;question:string;requester_opinion?:string;tooth_region?:string;patient_id?:number;media_ids?:string;urgency?:string})=>req<{ok:boolean;case_id:number}>("/consultations",t,{method:"POST",body:JSON.stringify(payload)});
export const getConsultations=async(t:string,before?:number)=>{const r=await req<{items:any[];next_before:number|null}>("/consultations"+(before?"?before="+before:""),t);return {next_before:r.next_before,items:r.items.map(c=>({...c,other_name:c.other_name||c.other_display_name||"",clinical_summary:c.clinical_summary||""})) as Consultation[]}};
export const getConsultation=(t:string,id:number)=>req<{case:any;messages:ChatMessage[]}>(`/consultations/${id}`,t);
export const sendConsultationMessage=(t:string,id:number,content:string,clientMessageId:string)=>req<{ok:boolean;message:ChatMessage}>(`/consultations/${id}/messages`,t,{method:"POST",body:JSON.stringify({content,client_message_id:clientMessageId})});
export const getCourses=(t:string,before?:number)=>req<{items:Course[];next_before:number|null}>("/academic/courses"+(before?"?before="+before:""),t);
export const getAcademicMessages=(t:string,id:number,before?:number)=>req<{next_before:number|null;items:Array<{id:number;role:string;content:string;created_at:string}>}>(`/academic/courses/${id}/messages`+(before?"?before="+before:""),t);
export function askAcademic(t:string,courseId:number,message:string){
 return req<any>(`/academic/courses/${courseId}/ask`,t,{method:"POST",body:JSON.stringify({message})});
}
export function mediaUploadUrl(patientId:number){return API_BASE+`/patients/${patientId}/media`;}

