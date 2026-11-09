const API_BASE = "https://dentalai.tr/api/mobile/v1";

export type User={id:number;username:string;email?:string|null;display_name:string;role:string;is_active:boolean;email_verified_at?:string|null;professional_title?:string|null;specialty?:string|null;university?:string|null};
export type Patient={id:number;anonymous_id:string;first_name?:string|null;last_name?:string|null;phone?:string|null;birth_date?:string|null;age?:number|null;chief_complaint?:string|null;created_at?:string};
export type Dashboard={user:User;stats:{patient_count:number;analysis_count:number;upcoming_event_count:number};recent_patients:Patient[];upcoming_events:Array<{id:number;event_type:string;title:string;start_at:string;end_at?:string|null;patient_id?:number|null;location?:string|null;status:string}>};
export type PatientDetail={patient:Patient;teeth:Array<{id:number;tooth_number:string;status:string;note?:string|null}>;surfaces:Array<{id:number;tooth_number:string;surface:string;status:string;note?:string|null}>;treatments:Array<{id:number;tooth_number?:string|null;treatment_name:string;treatment_date?:string|null;material?:string|null;doctor_note?:string|null;result?:string|null}>;media:Array<{id:number;original_filename:string;file_path:string;media_type:string;tooth_number?:string|null;note?:string|null;uploaded_at?:string}>};

export class ApiError extends Error {
 readonly status:number;
 constructor(status:number,message:string){super(message);this.name="ApiError";this.status=status;}
}

async function request<T>(path:string,token?:string,options:RequestInit={}):Promise<T>{
 const response=await fetch(API_BASE+path,{...options,headers:{"Content-Type":"application/json",...(token?{Authorization:"Bearer "+token}:{}),...(options.headers||{})}});
 const raw=await response.text(); let body:any={}; try{body=raw?JSON.parse(raw):{}}catch{}
 if(!response.ok){const detail=body.detail;throw new ApiError(response.status,typeof detail==="string"?detail:(detail?.message||"İstek başarısız."));}
 return body as T;
}
export function login(loginValue:string,password:string,renewEmailCode=false){return request<{access_token:string|null;token_type:string;expires_at:string;challenge_token?:string}>("/auth/login",undefined,{method:"POST",body:JSON.stringify({login:loginValue,password,renew_email_code:renewEmailCode})});}
export function verifyEmail(challengeToken:string,code:string){return request<{access_token:string;token_type:string;expires_at:string}>("/auth/verify-email",undefined,{method:"POST",body:JSON.stringify({challenge_token:challengeToken,code})});}
export function logout(token:string){return request<{ok:boolean}>("/auth/logout",token,{method:"POST"});}
export function getMe(token:string){return request<{user:User}>("/me",token);}
export function getDashboard(token:string){return request<Dashboard>("/dashboard",token);}
export function getPatients(token:string,q="",offset=0){return request<{items:Patient[];total:number}>("/patients?limit=30&offset="+offset+"&q="+encodeURIComponent(q),token);}
export function getPatient(token:string,id:number){return request<PatientDetail>("/patients/"+id,token);}

export type ScheduleEvent={id:number;event_type:string;title:string;start_at:string;end_at?:string|null;patient_id?:number|null;location?:string|null;notes?:string|null;status:string;reminder_minutes?:number|null;notification_enabled?:boolean;recurrence_rule?:string};
export async function createPatient(token:string,payload:{first_name:string;last_name:string;birth_date?:string;phone?:string;tc_kimlik_no?:string;address?:string;chief_complaint?:string;force_create?:boolean}){return request<{patient:Patient}>("/patients",token,{method:"POST",body:JSON.stringify(payload)});}
export async function getSchedule(token:string){return request<{items:ScheduleEvent[];event_types:Record<string,string>}>("/schedule",token);}
export async function createSchedule(token:string,payload:{event_type:string;title:string;start_at:string;end_at?:string;patient_id?:number;location?:string;notes?:string;reminder_minutes?:number;notification_enabled?:boolean;recurrence_rule?:string;recurrence_until?:string}){return request<{event:ScheduleEvent}>("/schedule",token,{method:"POST",body:JSON.stringify(payload)});}


export type ToothStatusCode="HEALTHY"|"CARIES"|"FILLING"|"CROWN"|"ROOT_CANAL"|"EXTRACTED"|"IMPLANT"|"OTHER";
export type ToothSurfaceCode="OCCLUSAL"|"INCISAL"|"MESIAL"|"DISTAL"|"BUCCAL"|"LINGUAL";
export function updateTooth(token:string,patientId:number,toothNumber:string,payload:{status:ToothStatusCode;note?:string;surface?:ToothSurfaceCode}){return request<{ok:boolean;tooth_number:string;status:string;surface?:string}>(`/patients/${patientId}/teeth/${toothNumber}`,token,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});}

export type NotificationItem={id:number;title:string;message:string;notice_type?:string;target_url?:string|null;is_read:boolean;created_at:string};
export type Expert={id:number;display_name:string;specialty?:string|null;academic_title?:string|null;institution?:string|null;availability:string;consultation_price?:number|null};
export type Consultation={id:number;status:string;specialty?:string|null;tooth_region?:string|null;question:string;requested_at:string;other_user_id:number;other_display_name:string;last_message?:string|null;last_message_at?:string|null};
export type ConsultationDetail={case:{id:number;status:string;specialty?:string|null;tooth_region?:string|null;clinical_summary?:string|null;requester_opinion?:string|null;question:string;requested_at:string;expert_user_id:number;requester_user_id:number};messages:Array<{id:number;sender_user_id:number;message_type:string;content?:string|null;reply_to_message_id?:number|null;created_at:string}>};
export type AcademicCourse={id:number;title:string;created_at:string};
export type AcademicMessage={id:number;role:string;content:string;created_at:string};

export const getNotifications=(token:string)=>request<{unread_count:number;notifications:NotificationItem[]}>("/notifications",token);
export const markNotificationRead=(token:string,id:number)=>request<{ok:boolean}>(`/notifications/${id}/read`,token,{method:"POST"});
export const getExperts=(token:string,available=false)=>request<{items:Expert[]}>(`/consultations/experts?available=${available}`,token);
export const getConsultations=(token:string)=>request<{items:Consultation[]}>("/consultations",token);
export const getConsultation=(token:string,id:number)=>request<ConsultationDetail>(`/consultations/${id}`,token);
export const getAcademicCourses=(token:string)=>request<{items:AcademicCourse[]}>("/academic/courses",token);
export const getAcademicMessages=(token:string,id:number)=>request<{items:AcademicMessage[]}>(`/academic/courses/${id}/messages`,token);
export const askAcademic=(token:string,id:number,message:string)=>request<any>(`/academic/courses/${id}/ask`,token,{method:"POST",body:JSON.stringify({message})});
export const uploadPatientMedia=async(token:string,patientId:number,file:{uri:string;name:string;type:string},toothNumber?:string)=>{
 const body=new FormData(); body.append("image",{uri:file.uri,name:file.name,type:file.type} as any); if(toothNumber) body.append("tooth_number",toothNumber);
 const response=await fetch(API_BASE+`/patients/${patientId}/media`,{method:"POST",headers:{Authorization:"Bearer "+token},body});
 const raw=await response.text(); let data:any={}; try{data=raw?JSON.parse(raw):{}}catch{} if(!response.ok)throw new Error(data.detail||"Görüntü yüklenemedi."); return data;
};

export async function createConsultation(token:string,payload:{expert_user_id:number;clinical_summary:string;requester_opinion?:string;question:string;tooth_region?:string;patient_id?:number;media_ids?:string;urgency?:string}){return request<{ok:boolean;case_id:number}>("/consultations",token,{method:"POST",body:JSON.stringify(payload)});}
export async function sendConsultationMessage(token:string,caseId:number,content:string){return request<any>("/consultations/"+caseId+"/messages",token,{method:"POST",body:JSON.stringify({content})});}
export type E2EEDeviceKey={device_id:string;public_key:string;algorithm:string;key_version:string};
export const registerE2EEDevice=(token:string,payload:{device_id:string;public_key:string;algorithm?:string;key_version?:string})=>request<{ok:boolean;device_id:string;public_key:string;algorithm:string;key_version:string}>("/e2ee/device",token,{method:"PUT",body:JSON.stringify(payload)});
export const getE2EEUserKeys=(token:string,userId:number)=>request<{items:E2EEDeviceKey[]}>(`/e2ee/users/${userId}/keys`,token);
export const revokeE2EEDevice=(token:string,deviceId:string)=>request<{ok:boolean;device_id:string;revoked:boolean}>(`/e2ee/device/${encodeURIComponent(deviceId)}`,token,{method:"DELETE"});


