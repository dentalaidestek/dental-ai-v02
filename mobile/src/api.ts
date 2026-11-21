import {reportSessionExpiry,revalidateSession} from './sessionExpiry';
import {normalizePatientDirectorySearch} from './patientDirectoryPresentation';
import {isDashboardProgramEvent} from './dashboardPresentation';
import type {DashboardProgramEvent} from './dashboardPresentation';
export const API_BASE = "https://dentalai.tr/api/mobile/v1";

export type User={id:number;username:string;email?:string|null;display_name:string;role:string;is_active:boolean;email_verified_at?:string|null;professional_title?:string|null;specialty?:string|null;university?:string|null};
export type Patient={id:number;tc_kimlik_no?:string|null;address?:string|null;anonymous_id:string;first_name?:string|null;last_name?:string|null;phone?:string|null;birth_date?:string|null;age?:number|null;chief_complaint?:string|null;created_at?:string};
export type DashboardAnalysis={id:number;patient_id:number;patient_name:string;tooth_number?:string|null;status:string;created_at:string};
export type Dashboard={user:User;stats:{patient_count:number;analysis_count:number;upcoming_event_count:number};recent_patients:Patient[];upcoming_events:Array<{id:number;event_type:string;title:string;start_at:string;end_at?:string|null;patient_id?:number|null;location?:string|null;status:string}>;recent_analyses?:DashboardAnalysis[];dashboard_event?:DashboardProgramEvent|null;dashboard_event_label?:string};
export type PatientTreatment={id:number;tooth_number?:string|null;treatment_name:string;treatment_date?:string|null;material?:string|null;doctor_note?:string|null;result?:string|null;edit_revision:string;analysis_id?:number|null;created_at:string};
export type PatientDetail={patient:Patient;edit_revision?:string;teeth:Array<{id:number;tooth_number:string;status:string;note?:string|null;updated_at?:string|null;revision:string}>;surfaces:Array<{id:number;tooth_number:string;surface:string;status:string;note?:string|null;updated_at?:string|null;revision:string}>;treatments:PatientTreatment[];treatments_next_cursor?:string|null;media:Array<{id:number;original_filename:string;file_path:string;media_type:string;tooth_number?:string|null;note?:string|null;uploaded_at?:string}>};

export class ApiError extends Error {
 readonly status:number;
 readonly duplicatePatientId?:number;
 constructor(status:number,message:string,duplicatePatientId?:number){super(message);this.name="ApiError";this.status=status;this.duplicatePatientId=duplicatePatientId;}
}

export async function request<T>(path:string,token?:string,options:RequestInit={}):Promise<T>{
 // A stalled mobile connection must not leave clinical screens loading forever.
 const controller=new AbortController();
 // Academic answers can take longer than a normal list request.
 const deadlineMs=/^\/academic\/courses\/\d+\/ask$/.test(path)?180000:30000;
 const timeout=setTimeout(()=>controller.abort(),deadlineMs);
 const externalSignal=options.signal;
 const abort=()=>controller.abort();
 if(externalSignal?.aborted)controller.abort();
 else externalSignal?.addEventListener("abort",abort,{once:true});
 try{
  const response=await fetch(API_BASE+path,{...options,credentials:"omit",signal:controller.signal,headers:{"Content-Type":"application/json",...(token?{Authorization:"Bearer "+token}:{}),...(options.headers||{})}});
  const raw=await response.text();let body:any={};
  try{body=raw?JSON.parse(raw):{}}catch{
   // A reverse proxy or expired web session may return HTML with HTTP 200.
   // Never treat that as a successful clinical API response.
   if(response.ok)throw new ApiError(502,"Sunucu beklenen JSON yanıtını göndermedi. Lütfen tekrar deneyin.");
  }
  if(response.ok&&(!raw.trim()||!body||typeof body!=="object"||Array.isArray(body)))throw new ApiError(502,"Sunucudan geçersiz API yanıtı alındı.");
  if(!response.ok){if(response.status===401&&token){if(path==="/me")reportSessionExpiry(token);else await revalidateSession(token)}const detail=body?.detail;const duplicateId=path==="/patients"&&response.status===409&&Number.isSafeInteger(detail?.patient_id)&&detail.patient_id>0?detail.patient_id:undefined;throw new ApiError(response.status,typeof detail==="string"?detail:(typeof detail?.message==="string"?detail.message:"İstek başarısız."),duplicateId);}
  return body as T;
 }catch(error){
  if(controller.signal.aborted&&!externalSignal?.aborted)throw new ApiError(408,"Sunucu yanıt vermedi. Bağlantınızı kontrol edip tekrar deneyin.");
  if(error instanceof TypeError)throw new ApiError(503,"Sunucuya bağlanılamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.");
  throw error;
 }finally{
  clearTimeout(timeout);
  externalSignal?.removeEventListener("abort",abort);
 }
}
export function login(loginValue:string,password:string,renewEmailCode=false){return request<{access_token:string|null;token_type:string;expires_at:string;challenge_token?:string}>("/auth/login",undefined,{method:"POST",body:JSON.stringify({login:loginValue,password,renew_email_code:renewEmailCode})});}
export function verifyEmail(challengeToken:string,code:string){return request<{access_token:string;token_type:string;expires_at:string}>("/auth/verify-email",undefined,{method:"POST",body:JSON.stringify({challenge_token:challengeToken,code})});}
export function logout(token:string){return request<{ok:boolean}>("/auth/logout",token,{method:"POST"});}
export function getMe(token:string){return request<{user:User}>("/me",token);}
export async function getDashboard(token:string){
 const result=await request<Dashboard>("/dashboard",token);
 const analyses=result?.recent_analyses;
 const analysisFields=new Set(["id","patient_id","patient_name","tooth_number","status","created_at"]);
 if(analyses!==undefined&&(!Array.isArray(analyses)||analyses.length>3||
    analyses.some(item=>!item||typeof item!=="object"||Array.isArray(item)||
      Object.keys(item).some(key=>!analysisFields.has(key))||
      !Number.isSafeInteger(item.id)||item.id<=0||
      !Number.isSafeInteger(item.patient_id)||item.patient_id<=0||
      typeof item.patient_name!=="string"||item.patient_name.length>256||
      !(item.tooth_number===undefined||item.tooth_number===null||typeof item.tooth_number==="string"&&item.tooth_number.length<=32)||
      typeof item.status!=="string"||!item.status||item.status.length>40||
      typeof item.created_at!=="string"||!item.created_at||item.created_at.length>64)||
    new Set(analyses.map(item=>item.id)).size!==analyses.length))
  throw new ApiError(502,"Ana sayfa analiz özeti beklenen veri minimizasyonu sözleşmesini karşılamıyor.");
 if(result?.dashboard_event!==undefined&&result.dashboard_event!==null&&!isDashboardProgramEvent(result.dashboard_event))
  throw new ApiError(502,"Ana sayfa program özeti doğrulanamadı.");
 if(result?.dashboard_event_label!==undefined&&!["Bugün","Yaklaşan Program"].includes(result.dashboard_event_label))
  throw new ApiError(502,"Ana sayfa program etiketi doğrulanamadı.");
 return result;
}
export async function getPatients(token:string,q="",offset=0){
 if(!Number.isSafeInteger(offset)||offset<0)throw Error("Geçersiz hasta sayfası.");
 // Keep the native query identical to the web form's trim/whitespace behavior while
 // retaining the server's 100-character guard for direct callers and deep links.
 if(typeof q!=="string")throw Error("Hasta araması en fazla 100 karakter olabilir.");
 const search=normalizePatientDirectorySearch(q);
 if(search.length>100)throw Error("Hasta araması en fazla 100 karakter olabilir.");
 const result=await request<{items:Patient[];total:number}>("/patients?limit=30&offset="+offset+"&q="+encodeURIComponent(search),token);
 if(!Array.isArray(result?.items)||result.items.length>30||!Number.isSafeInteger(result.total)||result.total<0||
    result.items.some(p=>!p||!Number.isSafeInteger(p.id)||p.id<=0)||
    new Set(result.items.map(p=>p.id)).size!==result.items.length||
    (result.total<offset+result.items.length)||
    (result.items.length===0&&offset<result.total))
  throw Error("Hasta sunucusundan geçersiz liste alındı. Yeniden deneyin.");
 return result;
}
const validTreatmentHistoryCursor=(value:unknown):value is string=>typeof value==="string"&&/^[A-Za-z0-9_-]{24,512}$/.test(value);
export async function getPatient(token:string,id:number,includeChart=false,includeMedia=false){
 if(!Number.isSafeInteger(id)||id<=0)throw Error("Geçersiz hasta kimliği.");
 // Current native screens opt into only the data they render. Legacy clients
 // that omit these query flags keep the original full detail response.
 const path="/patients/"+id+"?include_chart="+(includeChart?"true":"false")+"&include_media="+(includeMedia?"true":"false");
 const result=await request<PatientDetail>(path,token);
 if(!result?.patient||result.patient.id!==id||
    (result.edit_revision!==undefined&&(typeof result.edit_revision!=="string"||!/^[a-f0-9]{64}$/.test(result.edit_revision)))||
    !Array.isArray(result.teeth)||!Array.isArray(result.surfaces)||!Array.isArray(result.treatments)||result.treatments.length>3||!Array.isArray(result.media)||
    (result.treatments_next_cursor!==undefined&&result.treatments_next_cursor!==null&&(!validTreatmentHistoryCursor(result.treatments_next_cursor)||result.treatments.length!==3))||
    result.teeth.some(t=>!t||!validFdiTooth(t.tooth_number)||!validToothStatuses.has(t.status as ToothStatusCode))||
    result.surfaces.some(s=>!s||!validFdiTooth(s.tooth_number)||!validToothSurfaces.has(s.surface as ToothSurfaceCode)||!validToothStatuses.has(s.status as ToothStatusCode)||(s.updated_at!=null&&typeof s.updated_at!=="string"))||
    result.treatments.some(t=>!t||!Number.isSafeInteger(t.id)||t.id<=0||typeof t.treatment_name!=="string"||(t.tooth_number!=null&&!validFdiTooth(t.tooth_number))||typeof t.edit_revision!=="string"||!/^[a-f0-9]{64}$/.test(t.edit_revision)||typeof t.created_at!=="string")||
    result.media.some(m=>!m||!Number.isSafeInteger(m.id)||m.id<=0||typeof m.original_filename!=="string"||(m.tooth_number!=null&&!validFdiTooth(m.tooth_number))))
  throw Error("Hasta sunucusundan beklenmeyen profil alındı. Yeniden deneyin.");
 return result;
}
export type PatientTreatmentPage={items:PatientTreatment[];next_cursor:string|null};
export async function getPatientTreatments(token:string,id:number,cursor:string):Promise<PatientTreatmentPage>{
 if(!Number.isSafeInteger(id)||id<=0)throw new Error("Geçersiz hasta kimliği.");
 if(!validTreatmentHistoryCursor(cursor))throw new Error("Tedavi geçmişi sayfalama imleci geçersiz.");
 const result=await request<PatientTreatmentPage>(`/patients/${id}/treatments?cursor=${encodeURIComponent(cursor)}`,token);
 if(!Array.isArray(result?.items)||result.items.length>20||
    result.items.some(item=>!item||!Number.isSafeInteger(item.id)||item.id<=0||typeof item.treatment_name!=="string"||
      (item.tooth_number!=null&&!validFdiTooth(item.tooth_number))||
      typeof item.edit_revision!=="string"||!/^[a-f0-9]{64}$/.test(item.edit_revision)||
      typeof item.created_at!=="string"||
      (item.analysis_id!=null&&(!Number.isSafeInteger(item.analysis_id)||item.analysis_id<=0)))||
    new Set(result.items.map(item=>item.id)).size!==result.items.length||
    !(result.next_cursor===null||validTreatmentHistoryCursor(result.next_cursor))||
    (result.next_cursor!==null&&(result.next_cursor===cursor||result.items.length!==20)))
  throw new ApiError(502,"Tedavi geçmişi sayfası doğrulanamadı. Geçmişi yenileyin.");
 return result;
}

export async function getToothTreatments(
 token:string,id:number,toothNumber:string,cursor?:string,
):Promise<PatientTreatmentPage>{
 if(!Number.isSafeInteger(id)||id<=0)throw new Error("Geçersiz hasta kimliği.");
 if(!validFdiTooth(toothNumber))throw new Error("Geçersiz FDI diş numarası.");
 if(cursor!==undefined&&!validTreatmentHistoryCursor(cursor))throw new Error("Diş tedavi geçmişi sayfalama imleci geçersiz.");
 const query=cursor!==undefined?"?cursor="+encodeURIComponent(cursor):"";
 const result=await request<PatientTreatmentPage>(`/patients/${id}/teeth/${toothNumber}/treatments${query}`,token);
 if(!Array.isArray(result?.items)||result.items.length>20||
    result.items.some(item=>!item||!Number.isSafeInteger(item.id)||item.id<=0||
      item.tooth_number!==toothNumber||typeof item.treatment_name!=="string"||
      typeof item.edit_revision!=="string"||!/^[a-f0-9]{64}$/.test(item.edit_revision)||
      typeof item.created_at!=="string"||
      (item.analysis_id!=null&&(!Number.isSafeInteger(item.analysis_id)||item.analysis_id<=0)))||
    new Set(result.items.map(item=>item.id)).size!==result.items.length||
    !(result.next_cursor===null||validTreatmentHistoryCursor(result.next_cursor))||
    (result.next_cursor!==null&&(result.next_cursor===cursor||result.items.length!==20))||
    (result.items.length===0&&result.next_cursor!==null))
  throw new ApiError(502,"Diş tedavi geçmişi sayfası doğrulanamadı. Geçmişi yenileyin.");
 return result;
}

export type TreatmentPayload={treatment_name:string;tooth_number?:string;treatment_date?:string;material?:string;doctor_note?:string;result?:string};
export type TreatmentMutationResult={ok:boolean;treatment_id:number;edit_revision:string;replayed:boolean};
function validateTreatmentTarget(patientId:number,payload:TreatmentPayload,treatmentId:number|undefined,requestKey:string,expectedRevision?:string){
 if(!Number.isSafeInteger(patientId)||patientId<=0||(treatmentId!==undefined&&(!Number.isSafeInteger(treatmentId)||treatmentId<=0)))
  throw new Error("Geçersiz hasta veya tedavi kimliği.");
 if(!payload||typeof payload.treatment_name!=="string"||!payload.treatment_name.trim())
  throw new Error("Tedavi adı zorunludur.");
 if(payload.treatment_name.trim().length>200)throw new Error("Tedavi adı en fazla 200 karakter olabilir.");
 if(!/^[A-Za-z0-9_-]{16,80}$/.test(requestKey))throw new Error("Geçersiz tedavi işlem anahtarı.");
 if(expectedRevision!==undefined&&!/^[a-f0-9]{64}$/.test(expectedRevision))throw new Error("Tedavi kayıt sürümü geçersiz.");
 if(payload.treatment_date){
  const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(payload.treatment_date);
  const y=m?Number(m[1]):0,month=m?Number(m[2]):0,day=m?Number(m[3]):0;
  const leap=y%4===0&&(y%100!==0||y%400===0),days=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31];
  const valid=!!m&&y>=1&&month>=1&&month<=12&&day>=1&&day<=days[month-1];
  if(!valid)throw new Error("Tedavi tarihi YYYY-AA-GG biçiminde geçerli bir tarih olmalıdır.");
 }
 if(payload.tooth_number&&(!validFdiTooth(payload.tooth_number)))
  throw new Error("Geçersiz FDI diş numarası.");
}
async function treatmentMutationRequest(path:string,token:string,body:Record<string,unknown>):Promise<TreatmentMutationResult>{
 const result=await request<TreatmentMutationResult>(path,token,{method:path.endsWith("/treatments")?"POST":"PUT",body:JSON.stringify(body)});
 if(!result||result.ok!==true||!Number.isSafeInteger(result.treatment_id)||result.treatment_id<1||
    typeof result.edit_revision!=="string"||!/^[a-f0-9]{64}$/.test(result.edit_revision)||typeof result.replayed!=="boolean")
  throw new ApiError(502,"Tedavi işlem fişi doğrulanamadı. Aynı güvenli taslak korunuyor.");
 return result;
}
export function createTreatment(token:string,patientId:number,payload:TreatmentPayload,requestKey:string){
 validateTreatmentTarget(patientId,payload,undefined,requestKey);
 return treatmentMutationRequest(`/patients/${patientId}/treatments`,token,{...payload,request_key:requestKey});
}
export function updateTreatment(token:string,patientId:number,treatmentId:number,payload:TreatmentPayload,requestKey:string,expectedRevision:string){
 validateTreatmentTarget(patientId,payload,treatmentId,requestKey,expectedRevision);
 return treatmentMutationRequest(`/patients/${patientId}/treatments/${treatmentId}`,token,{...payload,request_key:requestKey,expected_revision:expectedRevision});
}
export type PatientDeleteResult={ok:boolean;patient_id:number;already_deleted?:boolean};
export async function deletePatient(token:string,id:number,requestKey?:string):Promise<PatientDeleteResult>{
 if(!Number.isSafeInteger(id)||id<=0)throw new Error("Geçersiz hasta kimliği.");
 if(requestKey!==undefined&&!/^[A-Za-z0-9_-]{16,96}$/.test(requestKey))throw new Error("Hasta silme işlem anahtarı geçersiz.");
 const path=`/patients/${id}`+(requestKey!==undefined?`?request_key=${encodeURIComponent(requestKey)}`:"");
 const result=await request<PatientDeleteResult>(path,token,{method:"DELETE"});
 if(!result||result.ok!==true||result.patient_id!==id||
    (requestKey!==undefined&&typeof result.already_deleted!=="boolean")||
    (result.already_deleted!==undefined&&typeof result.already_deleted!=="boolean"))
  throw new ApiError(502,"Hasta silme işlem fişi doğrulanamadı. Aynı güvenli taslak korunuyor.");
 return result;
}
export async function editPatient(token:string,id:number,payload:{first_name:string;last_name:string;phone?:string;birth_date?:string;tc_kimlik_no?:string;address?:string;chief_complaint?:string;expected_revision:string}){
 if(!/^[a-f0-9]{64}$/.test(payload.expected_revision))throw new Error("Hasta kayıt sürümü geçersiz.");
 const result=await request<{ok:boolean;patient:Patient;edit_revision:string}>(`/patients/${id}`,token,{method:"PUT",body:JSON.stringify(payload)});
 if(!result||result.ok!==true||!result.patient||result.patient.id!==id||typeof result.edit_revision!=="string"||!/^[a-f0-9]{64}$/.test(result.edit_revision))
  throw new ApiError(502,"Hasta güncelleme yanıtı doğrulanamadı. Profili yenileyin.");
 return result;
}

export type ScheduleEvent={id:number;event_type:string;title:string;start_at:string;end_at?:string|null;patient_id?:number|null;location?:string|null;notes?:string|null;status:string;reminder_minutes?:number|null;notification_enabled?:boolean;recurrence_rule?:string};
export async function createPatient(token:string,payload:{first_name:string;last_name:string;birth_date?:string;phone?:string;tc_kimlik_no?:string;address?:string;chief_complaint?:string;force_create?:boolean}){return request<{patient:Patient}>("/patients",token,{method:"POST",body:JSON.stringify(payload)});}
export async function getSchedule(token:string){
 const result=await request<{items:ScheduleEvent[];event_types:Record<string,string>}>("/schedule",token);
 if(!Array.isArray(result?.items)||!result.event_types||typeof result.event_types!=="object"||Array.isArray(result.event_types)||
    result.items.some(event=>!event||!Number.isSafeInteger(event.id)||event.id<=0||
      typeof event.event_type!=="string"||typeof event.title!=="string"||typeof event.start_at!=="string"||
      (event.patient_id!=null&&(!Number.isSafeInteger(event.patient_id)||event.patient_id<=0)))||
    new Set(result.items.map(event=>event.id)).size!==result.items.length)
  throw new Error("Program sunucusundan geçersiz randevu listesi alındı. Yeniden deneyin.");
 return result;
}
export async function completeSchedule(token:string,id:number){return request<{ok:boolean;status:string}>(`/schedule/${id}/complete`,token,{method:"POST"});}
export async function deleteSchedule(token:string,id:number){return request<{ok:boolean}>(`/schedule/${id}`,token,{method:"DELETE"});}

export async function createSchedule(token:string,payload:{event_type:string;title:string;start_at:string;end_at?:string;patient_id?:number;location?:string;notes?:string;reminder_minutes?:number;notification_enabled?:boolean;recurrence_rule?:string;recurrence_until?:string}){
 if(!payload||typeof payload.event_type!=="string"||!payload.event_type.trim()||
    typeof payload.title!=="string"||!payload.title.trim()||typeof payload.start_at!=="string"||!payload.start_at.trim()||
    (payload.patient_id!==undefined&&(!Number.isSafeInteger(payload.patient_id)||payload.patient_id<=0)))
  throw new Error("Geçersiz randevu bilgisi veya hasta kimliği.");
 const result=await request<{event:ScheduleEvent}>("/schedule",token,{method:"POST",body:JSON.stringify(payload)});
 if(!result?.event||!Number.isSafeInteger(result.event.id)||result.event.id<=0||
    (payload.patient_id!==undefined&&result.event.patient_id!==payload.patient_id))
  throw new Error("Randevu kaydı doğrulanamadı. Yeniden oluşturmadan önce programı kontrol edin.");
 return result;
}


export type ToothStatusCode="HEALTHY"|"CARIES"|"FILLING"|"CROWN"|"ROOT_CANAL"|"EXTRACTED"|"IMPLANT"|"OTHER";
export type ToothSurfaceCode="OCCLUSAL"|"INCISAL"|"MESIAL"|"DISTAL"|"BUCCAL"|"LINGUAL";
const validFdiTooth=(value:string)=>/^(?:[1-4][1-8]|[5-8][1-5])$/.test(value);
function validateToothTarget(patientId:number,toothNumber:string){
 if(!Number.isSafeInteger(patientId)||patientId<=0)throw new Error("Geçersiz hasta kimliği.");
 if(typeof toothNumber!=="string"||!validFdiTooth(toothNumber))throw new Error("Geçersiz FDI diş numarası.");
}
const validToothStatuses=new Set<ToothStatusCode>(["HEALTHY","CARIES","FILLING","CROWN","ROOT_CANAL","EXTRACTED","IMPLANT","OTHER"]);
const validToothSurfaces=new Set<ToothSurfaceCode>(["OCCLUSAL","INCISAL","MESIAL","DISTAL","BUCCAL","LINGUAL"]);

export type ToothChartFocus={latest_analysis_tooth:string|null};
export async function getToothChartFocus(token:string,patientId:number):Promise<string|null>{
 if(!Number.isSafeInteger(patientId)||patientId<=0)throw new Error("Geçersiz hasta kimliği.");
 const result=await request<ToothChartFocus>(`/patients/${patientId}/tooth-chart/focus`,token);
 if(!result||!Object.prototype.hasOwnProperty.call(result,"latest_analysis_tooth")||
    (result.latest_analysis_tooth!==null&&(typeof result.latest_analysis_tooth!=="string"||!validFdiTooth(result.latest_analysis_tooth))))
  throw new ApiError(502,"Diş şeması başlangıç dişi doğrulanamadı.");
 return result.latest_analysis_tooth;
}
function validateToothPayload(payload:{status:ToothStatusCode;note?:string;surface?:ToothSurfaceCode;surfaces?:ToothSurfaceCode[];surface_revisions?:Record<string,string|null>}){
 if(!payload||!validToothStatuses.has(payload.status))throw new Error("Geçersiz diş durumu.");
 if(payload.surface!==undefined&&!validToothSurfaces.has(payload.surface))throw new Error("Geçersiz diş yüzeyi.");
 if(payload.surfaces!==undefined&&(!Array.isArray(payload.surfaces)||payload.surfaces.some(s=>!validToothSurfaces.has(s))))throw new Error("Geçersiz diş yüzeyi.");
 if(payload.surfaces?.length){
  if(!payload.surface_revisions||Object.keys(payload.surface_revisions).length!==payload.surfaces.length||
     payload.surfaces.some(surface=>!Object.prototype.hasOwnProperty.call(payload.surface_revisions,surface)||
       (payload.surface_revisions![surface]!==null&&!/^[a-f0-9]{64}$/.test(payload.surface_revisions![surface]||""))))
   throw new Error("Seçilen diş yüzeylerinin sürümü alınamadı; şemayı yenileyin.");
 }
}
export function updateToothSurface(token:string,patientId:number,toothNumber:string,surface:ToothSurfaceCode,payload:{status:ToothStatusCode;note?:string;expected_revision:string|null}){validateToothTarget(patientId,toothNumber);if(!validToothSurfaces.has(surface))throw new Error("Geçersiz diş yüzeyi.");validateToothPayload(payload);if(payload.expected_revision!==undefined&&payload.expected_revision!==null&&!/^[a-f0-9]{64}$/.test(payload.expected_revision))throw new Error("Diş yüzeyi sürümü alınamadı; şemayı yenileyin.");return request<{ok:boolean;tooth_number:string;surface:string;status:string;revision:string}>(`/patients/${patientId}/teeth/${toothNumber}/surfaces/${surface}`,token,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});}
export function updateTooth(token:string,patientId:number,toothNumber:string,payload:{status:ToothStatusCode;note?:string;surface?:ToothSurfaceCode;surfaces?:ToothSurfaceCode[];surface_revisions?:Record<string,string|null>;expected_revision:string|null}){validateToothTarget(patientId,toothNumber);validateToothPayload(payload);if(payload.expected_revision!==undefined&&payload.expected_revision!==null&&!/^[a-f0-9]{64}$/.test(payload.expected_revision))throw new Error("Diş şeması sürümü alınamadı; şemayı yenileyin.");return request<{ok:boolean;tooth_number:string;status:string;surface?:string;revision:string}>(`/patients/${patientId}/teeth/${toothNumber}`,token,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});}

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
export type PatientMediaUploadProgress={loaded:number;total:number;lengthComputable:boolean};
export type PatientMediaUploadResult={media:{id:number;original_filename:string;media_type:string;tooth_number?:string|null;note?:string|null;uploaded_at?:string};replayed:boolean};
export async function getPatientMediaUpload(token:string,patientId:number,requestKey:string):Promise<{found:boolean;media?:PatientMediaUploadResult["media"]|null}>{
 if(!Number.isSafeInteger(patientId)||patientId<=0)throw new Error("Geçersiz hasta kimliği.");
 if(!/^[A-Za-z0-9_-]{16,96}$/.test(requestKey))throw new Error("Geçersiz klinik görüntü işlem anahtarı.");
 const result=await request<{found:boolean;media?:PatientMediaUploadResult["media"]|null}>(`/patients/${patientId}/media/uploads/${encodeURIComponent(requestKey)}`,token);
 if(!result||typeof result.found!=="boolean"||(result.found&&(!result.media||!Number.isSafeInteger(result.media.id)||result.media.id<=0||typeof result.media.original_filename!=="string")))
  throw new ApiError(502,"Klinik görüntü işlem fişi doğrulanamadı.");
 return result;
}

// XHR tabanlı klinik görüntü yükleme: multipart byte progress raporlar ve
// Content-Type boundary'sini katmanın kendisine bırakır (fetch'te yapılamaz).
function uploadPatientMediaViaXHR(token:string,patientId:number,form:FormData,onProgress?:(progress:PatientMediaUploadProgress)=>void):Promise<PatientMediaUploadResult>{
 return new Promise((resolve,reject)=>{
  const xhr=new XMLHttpRequest();
  let timeoutId:any;
  const finishError=(error:unknown)=>{clearTimeout(timeoutId);reject(error instanceof ApiError?error:new ApiError(503,"Görüntü aktarım bağlantısı kesildi. Yeniden denemeden önce galerisini kontrol edin."))};
  timeoutId=setTimeout(()=>{xhr.abort();finishError(new ApiError(503,"Görüntü aktarım bağlantısı kesildi. Yeniden denemeden önce galerisini kontrol edin."))},120000);
  xhr.open("POST",API_BASE+`/patients/${patientId}/media`);
  xhr.withCredentials=false;
  xhr.setRequestHeader("Authorization","Bearer "+token);
  if(onProgress)xhr.upload.onprogress=event=>{onProgress({loaded:event.loaded,total:event.total,lengthComputable:!!event.lengthComputable})};
  xhr.onerror=()=>finishError(new ApiError(503,"Görüntü aktarım bağlantısı kesildi. Yeniden denemeden önce galerisini kontrol edin."));
  xhr.ontimeout=()=>finishError(new ApiError(503,"Görüntü aktarım bağlantısı kesildi. Yeniden denemeden önce galerisini kontrol edin."));
  xhr.onload=()=>{void (async()=>{
   try{
    const status=xhr.status,raw=xhr.responseText||"";let data:any={};
    try{data=raw?JSON.parse(raw):{}}catch{if(status>=200&&status<300)throw new ApiError(502,"Sunucu beklenen klinik görüntü yanıtını göndermedi.")}
    if(status===401)await revalidateSession(token);
    if(status<200||status>=300){
     const detail=typeof data?.detail==="string"?data.detail:(typeof data?.detail?.message==="string"?data.detail.message:"Görüntü yüklenemedi.");
     throw new ApiError(status,detail);
    }
    if(!data?.media||!Number.isSafeInteger(data.media.id)||data.media.id<=0||typeof data.media.original_filename!=="string"||typeof data.media.media_type!=="string"||(data.replayed!==undefined&&typeof data.replayed!=="boolean"))throw new ApiError(502,"Görüntü kayıt fişi doğrulanamadı. Aynı işlem anahtarı korunuyor.");
    clearTimeout(timeoutId);resolve(data as PatientMediaUploadResult);
   }catch(error){finishError(error)}
  })()};
  xhr.send(form);
 });
}

export const uploadPatientMedia=async(
 token:string,
 patientId:number,
 file:{uri:string;name:string;type:string},
 toothNumber?:string,
 mediaType:"PHOTO"|'RADIOGRAPH'='PHOTO',
 requestKey?:string,
 batchId?:string,
 onProgress?:(progress:PatientMediaUploadProgress)=>void,
 note?:string,
):Promise<PatientMediaUploadResult>=>{
 if(!Number.isSafeInteger(patientId)||patientId<=0)throw new Error("Geçersiz hasta kimliği.");
 if(!file?.uri||!file.name||!file.type)throw new Error("Geçerli bir klinik görüntü seçin.");
 if(!["PHOTO","RADIOGRAPH"].includes(mediaType))throw new Error("Geçersiz görüntü türü.");
 if(requestKey!==undefined&&typeof requestKey!=='string')throw new Error("Geçersiz klinik görüntü işlem anahtarı.");
 if(requestKey&&!/^[A-Za-z0-9_-]{16,96}$/.test(requestKey))throw new Error("Geçersiz klinik görüntü işlem anahtarı.");
 if(batchId!==undefined&&typeof batchId!=='string')throw new Error("Geçersiz klinik görüntü yükleme grubu.");
 if(batchId&&!/^[A-Za-z0-9_-]{16,96}$/.test(batchId))throw new Error("Geçersiz klinik görüntü yükleme grubu.");
 if(toothNumber!==undefined&&!validFdiTooth(toothNumber))throw new Error("Geçersiz FDI diş numarası.");
 const body=new FormData();
 body.append("media_type",mediaType);
 if(requestKey)body.append("request_key",requestKey);
 if(batchId)body.append("batch_id",batchId);
 body.append("file",{uri:file.uri,name:file.name,type:file.type} as any);
 if(toothNumber)body.append("tooth_number",toothNumber);
 if(note?.trim())body.append("note",note.trim().slice(0,2000));
 // Gerçek cihazda XMLHttpRequest mevcuttur: byte progress + otomatik multipart boundary.
 // Node test ortamlarında XHR yoktur: fetch yolu çalışır.
 if(typeof XMLHttpRequest==='function')return uploadPatientMediaViaXHR(token,patientId,body,onProgress);
 const controller=new AbortController();
 const timeout=setTimeout(()=>controller.abort(),120000);
 try{
  const response=await fetch(API_BASE+`/patients/${patientId}/media`,{method:"POST",body,credentials:"omit",headers:{Authorization:"Bearer "+token},signal:controller.signal});
  const raw=await response.text();let data:any={};
  try{data=raw?JSON.parse(raw):{}}catch{
   if(response.ok)throw new ApiError(502,"Sunucu beklenen klinik görüntü yanıtını göndermedi.");
  }
  if(response.status===401)await revalidateSession(token);
  if(response.status<200||response.status>=300){
   const detail=typeof data?.detail==="string"?data.detail:(typeof data?.detail?.message==="string"?data.detail.message:"Görüntü yüklenemedi.");
   throw new ApiError(response.status,detail);
  }
  if(!data?.media||!Number.isSafeInteger(data.media.id)||data.media.id<=0||typeof data.media.original_filename!=="string"||typeof data.media.media_type!=="string"||(data.replayed!==undefined&&typeof data.replayed!=="boolean"))
   throw new ApiError(502,"Görüntü kayıt fişi doğrulanamadı. Aynı işlem anahtarı korunuyor.");
  return data as PatientMediaUploadResult;
 }catch(error){
  if(error instanceof ApiError)throw error;
  throw new ApiError(503,"Görüntü aktarım bağlantısı kesildi. Yeniden denemeden önce galerisini kontrol edin.");
 }finally{clearTimeout(timeout)}
};

export async function createConsultation(token:string,payload:{expert_user_id:number;clinical_summary:string;requester_opinion?:string;question:string;tooth_region?:string;patient_id?:number;media_ids?:string;urgency?:string}){return request<{ok:boolean;case_id:number}>("/consultations",token,{method:"POST",body:JSON.stringify(payload)});}
export async function sendConsultationMessage(token:string,caseId:number,content:string){return request<any>("/consultations/"+caseId+"/messages",token,{method:"POST",body:JSON.stringify({content})});}
export type E2EEDeviceKey={device_id:string;public_key:string;algorithm:string;key_version:string};
export const registerE2EEDevice=(token:string,payload:{device_id:string;public_key:string;algorithm?:string;key_version?:string})=>request<{ok:boolean;device_id:string;public_key:string;algorithm:string;key_version:string}>("/e2ee/device",token,{method:"PUT",body:JSON.stringify(payload)});
export const getE2EEUserKeys=(token:string,userId:number)=>request<{items:E2EEDeviceKey[]}>(`/e2ee/users/${userId}/keys`,token);
export const revokeE2EEDevice=(token:string,deviceId:string)=>request<{ok:boolean;device_id:string;revoked:boolean}>(`/e2ee/device/${encodeURIComponent(deviceId)}`,token,{method:"DELETE"});
