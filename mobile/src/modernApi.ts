const API_BASE="https://dentalai.tr/api/mobile/v1";
async function req<T>(path:string,token:string,init:RequestInit={}):Promise<T>{
 const headers:any={"Content-Type":"application/json",Authorization:"Bearer "+token,...(init.headers||{})};
 const r=await fetch(API_BASE+path,{...init,headers});
 const raw=await r.text(); let b:any={}; try{b=raw?JSON.parse(raw):{}}catch{}
 if(!r.ok) throw new Error(typeof b.detail==="string"?b.detail:(b.detail?.message||"İstek başarısız."));
 return b as T;
}
export type Notice={id:number;title:string;message:string;notice_type:string;target_url?:string|null;read_at?:string|null;created_at:string};
export type Expert={user_id:number;display_name:string;specialty:string;academic_title?:string|null;institution?:string|null;bio?:string|null;availability:string;consultation_price:number;rating_avg?:number|null;review_count:number};
export type Consultation={id:number;other_user_id:number;other_name:string;specialty:string;status:string;question:string;clinical_summary:string;requested_at:string;expert_response_deadline:string};
export type ChatMessage={id:number;sender_user_id:number;type:string;content:string;created_at:string};
export type AnalysisHistory={id:number;patient_id:number;patient_name:string;tooth_number?:string|null;status:string;clinical_notes?:string|null;created_at:string};
export type Course={id:number;title:string;description?:string|null;updated_at:string;material_count:number};
export const getNotifications=(t:string)=>req<{items:Notice[];unread:number}>("/notifications",t);
export const markNotificationRead=(t:string,id:number)=>req<{ok:boolean}>("/notifications/"+id+"/read",t,{method:"POST"});
export const getAnalysisHistory=(t:string)=>req<{items:AnalysisHistory[];total:number}>("/analyses",t);
export const getMedia=(t:string,p:number)=>req<{items:Array<{id:number;filename:string;media_type:string;tooth_number?:string|null;note?:string|null;uploaded_at:string;url:string}>}>(`/patients/${p}/media`,t);
export const getExperts=(t:string,q="")=>req<{items:Expert[]}>("/experts?q="+encodeURIComponent(q),t);
export const createConsultation=(t:string,payload:{expert_user_id:number;clinical_summary:string;question:string;requester_opinion?:string;tooth_region?:string;patient_id?:number;media_ids?:string;urgency?:string})=>req<{ok:boolean;case_id:number}>("/consultations",t,{method:"POST",body:JSON.stringify(payload)});
export const getConsultations=(t:string)=>req<{items:Consultation[]}>("/consultations",t);
export const getConsultation=(t:string,id:number)=>req<{case:any;messages:ChatMessage[]}>(`/consultations/${id}`,t);
export const sendConsultationMessage=(t:string,id:number,content:string)=>req<{ok:boolean;message:ChatMessage}>(`/consultations/${id}/messages`,t,{method:"POST",body:JSON.stringify({content})});
export const getCourses=(t:string)=>req<{items:Course[]}>("/academic/courses",t);\nexport const getAcademicMessages=(t:string,id:number)=>req<{items:Array<{id:number;role:string;content:string;created_at:string}>}>(`/academic/courses/${id}/messages`,t);
export async function askAcademic(t:string,courseId:number,message:string){
 const body=JSON.stringify({message});
 const r=await fetch(API_BASE+`/academic/courses/${courseId}/ask`,{method:"POST",headers:{Authorization:"Bearer "+t,"Content-Type":"application/x-www-form-urlencoded",Accept:"application/json"},body:body.toString()});
 const raw=await r.text(); if(!r.ok){let b:any={};try{b=JSON.parse(raw)}catch{};throw new Error(typeof b.detail==="string"?b.detail:(b.error||"Akademik AI isteği başarısız."));}
 try{return JSON.parse(raw)}catch{return {ok:true,raw};}
}
export function mediaUploadUrl(patientId:number){return API_BASE+`/patients/${patientId}/media`;}
