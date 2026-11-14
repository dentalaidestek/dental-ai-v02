import {Patient,ApiError} from "./api";
import {revalidateSession} from './sessionExpiry';

const API_BASE="https://dentalai.tr/api/mobile/v1";

async function call<T>(path:string,token:string,options:RequestInit={}):Promise<T>{
  const response=await fetch(API_BASE+path,{...options,headers:{Authorization:"Bearer "+token,...(options.headers||{})}});
  const raw=await response.text();let body:any={};try{body=raw?JSON.parse(raw):{}}catch{}
  if(!response.ok){if(response.status===401)await revalidateSession(token);throw new ApiError(response.status,typeof body?.detail==="string"?body.detail:(body?.detail?.message||"İstek başarısız."));}
  return body as T;
}

export type MobileAnalysis={
  analysis:{id:number;patient_id:number;tooth_number?:string|null;clinical_notes?:string|null;status:string;created_at?:string};
  patient:Patient;
  assets:Array<{id:number;original_filename:string;image_type:string;has_vision:boolean}>;
  ai_result?:any|null;
};

export async function createAnalysis(token:string,payload:{patientId:number;toothNumber?:string;clinicalNotes?:string;images:Array<{uri:string;name?:string;type?:string}>}){
  if(!Number.isSafeInteger(payload?.patientId)||payload.patientId<=0||!Array.isArray(payload.images)||!payload.images.length||payload.images.some(image=>!image||typeof image.uri!=="string"||!image.uri.trim()))throw Error("Analiz için geçerli hasta ve en az bir klinik görüntü seçin.");
  const form=new FormData();
  form.append("patient_id",String(payload.patientId));
  if(payload.toothNumber)form.append("tooth_number",payload.toothNumber);
  if(payload.clinicalNotes)form.append("clinical_notes",payload.clinicalNotes);
  payload.images.forEach((image,i)=>{
    form.append("images",{uri:image.uri,name:image.name||("dental-image-"+i+".jpg"),type:image.type||"image/jpeg"} as any);
  });
  const result=await call<{ok:boolean;analysis_id:number;status:string}>("/analyses",token,{method:"POST",body:form});
  if(!result?.ok||!Number.isSafeInteger(result.analysis_id)||result.analysis_id<=0)throw Error("Analiz oluşturuldu ancak sunucu geçerli bir iş kimliği döndürmedi.");
  return result;
}

export async function getAnalysis(token:string,id:number){if(!Number.isSafeInteger(id)||id<=0)throw Error("Geçersiz analiz kimliği.");const result=await call<MobileAnalysis>("/analyses/"+id,token);if(!result?.analysis||result.analysis.id!==id||!Number.isSafeInteger(result.analysis.patient_id)||result.analysis.patient_id<=0||!result.patient||result.patient.id!==result.analysis.patient_id||!Array.isArray(result.assets))throw Error("Analiz sunucusundan hasta veya iş kimliği uyuşmayan yanıt alındı.");return result;}
export function startAnalysisAI(token:string,id:number){if(!Number.isSafeInteger(id)||id<=0)throw Error("Geçersiz analiz kimliği.");return call<{ok:boolean;status:string}>("/analyses/"+id+"/ai",token,{method:"POST"});}

export type AnalysisHistoryItem={id:number;patient_id:number;patient_name:string;tooth_number?:string|null;clinical_notes?:string|null;status:string;created_at:string};
export function getAnalysisHistory(token:string,patientId?:number){return call<{items:AnalysisHistoryItem[]}>("/analyses"+(patientId?"?patient_id="+patientId:""),token);}
