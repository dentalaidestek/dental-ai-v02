const API_BASE = "https://dentalai.tr/api/mobile/v1";

export type User={id:number;username:string;email?:string|null;display_name:string;role:string;is_active:boolean;professional_title?:string|null;specialty?:string|null;university?:string|null};
export type Patient={id:number;anonymous_id:string;first_name?:string|null;last_name?:string|null;phone?:string|null;birth_date?:string|null;age?:number|null;chief_complaint?:string|null;created_at?:string};
export type Dashboard={user:User;stats:{patient_count:number;analysis_count:number;upcoming_event_count:number};recent_patients:Patient[];upcoming_events:Array<{id:number;event_type:string;title:string;start_at:string;end_at?:string|null;patient_id?:number|null;location?:string|null;status:string}>};
export type PatientDetail={patient:Patient;teeth:Array<{id:number;tooth_number:string;status:string;note?:string|null}>;surfaces:Array<{id:number;tooth_number:string;surface:string;status:string;note?:string|null}>;treatments:Array<{id:number;tooth_number?:string|null;treatment_name:string;treatment_date?:string|null;material?:string|null;doctor_note?:string|null;result?:string|null}>;media:Array<{id:number;original_filename:string;file_path:string;media_type:string;tooth_number?:string|null;note?:string|null;uploaded_at?:string}>};

async function request<T>(path:string,token?:string,options:RequestInit={}):Promise<T>{
 const response=await fetch(API_BASE+path,{...options,headers:{"Content-Type":"application/json",...(token?{Authorization:"Bearer "+token}:{}),...(options.headers||{})}});
 const raw=await response.text(); let body:any={}; try{body=raw?JSON.parse(raw):{}}catch{}
 if(!response.ok)throw new Error(body.detail||"İstek başarısız.");
 return body as T;
}
export function login(loginValue:string,password:string){return request<{access_token:string;token_type:string;expires_at:string}>("/auth/login",undefined,{method:"POST",body:JSON.stringify({login:loginValue,password})});}
export function logout(token:string){return request<{ok:boolean}>("/auth/logout",token,{method:"POST"});}
export function getMe(token:string){return request<{user:User}>("/me",token);}
export function getDashboard(token:string){return request<Dashboard>("/dashboard",token);}
export function getPatients(token:string,q=""){return request<{items:Patient[];total:number}>("/patients?q="+encodeURIComponent(q),token);}
export function getPatient(token:string,id:number){return request<PatientDetail>("/patients/"+id,token);}
