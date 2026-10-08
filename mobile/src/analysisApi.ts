import {Patient} from "./api";

const API_BASE="https://dentalai.tr/api/mobile/v1";

async function call<T>(path:string,token:string,options:RequestInit={}):Promise<T>{
  const response=await fetch(API_BASE+path,{...options,headers:{Authorization:"Bearer "+token,...(options.headers||{})}});
  const raw=await response.text();let body:any={};try{body=raw?JSON.parse(raw):{}}catch{}
  if(!response.ok)throw new Error(typeof body.detail==="string"?body.detail:(body.detail?.message||"İstek başarısız."));
  return body as T;
}

export type MobileAnalysis={
  analysis:{id:number;patient_id:number;tooth_number?:string|null;clinical_notes?:string|null;status:string;created_at?:string};
  patient:Patient;
  assets:Array<{id:number;original_filename:string;image_type:string;has_vision:boolean}>;
  ai_result?:any|null;
};

export async function createAnalysis(token:string,payload:{patientId:number;toothNumber?:string;clinicalNotes?:string;images:Array<{uri:string;name?:string;type?:string}>}){
  const form=new FormData();
  form.append("patient_id",String(payload.patientId));
  if(payload.toothNumber)form.append("tooth_number",payload.toothNumber);
  if(payload.clinicalNotes)form.append("clinical_notes",payload.clinicalNotes);
  payload.images.forEach((image,i)=>{
    form.append("images",{uri:image.uri,name:image.name||("dental-image-"+i+".jpg"),type:image.type||"image/jpeg"} as any);
  });
  return call<{ok:boolean;analysis_id:number;status:string}>("/analyses",token,{method:"POST",body:form});
}

export function getAnalysis(token:string,id:number){return call<MobileAnalysis>("/analyses/"+id,token);}
export function startAnalysisAI(token:string,id:number){return call<{ok:boolean;status:string}>("/analyses/"+id+"/ai",token,{method:"POST"});}

export type AnalysisHistoryItem={id:number;patient_id:number;patient_name:string;tooth_number?:string|null;clinical_notes?:string|null;status:string;created_at:string};
export function getAnalysisHistory(token:string,patientId?:number){return call<{items:AnalysisHistoryItem[]}>("/analyses"+(patientId?"?patient_id="+patientId:""),token);}
