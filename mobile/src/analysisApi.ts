import {Patient,ApiError} from "./api";
import {revalidateSession} from './sessionExpiry';

const API_BASE="https://dentalai.tr/api/mobile/v1";


async function call<T>(path:string,token:string,options:RequestInit={}):Promise<T>{
  const controller=new AbortController(),external=options.signal,abort=()=>controller.abort();
  const timeout=setTimeout(abort,options.body instanceof FormData?120000:30000);
  if(external?.aborted)controller.abort();else external?.addEventListener('abort',abort,{once:true});
  try{
    const response=await fetch(API_BASE+path,{...options,credentials:"omit",signal:controller.signal,headers:{Authorization:"Bearer "+token,...(options.headers||{})}});
    const raw=await response.text();let body:any={};try{body=raw?JSON.parse(raw):{}}catch{if(response.ok)throw new ApiError(502,"Sunucu beklenen JSON yanıtını göndermedi.")}
    if(!response.ok){if(response.status===401)await revalidateSession(token);throw new ApiError(response.status,typeof body?.detail==="string"?body.detail:(typeof body?.detail?.message==="string"?body.detail.message:"İstek başarısız."));}
    if(!raw.trim()||!body||typeof body!=="object"||Array.isArray(body))throw new ApiError(502,"Sunucudan geçersiz analiz yanıtı alındı.");
    return body as T;
  }catch(error){if(controller.signal.aborted&&!external?.aborted)throw new ApiError(408,"Analiz isteği zaman aşımına uğradı. Yeniden göndermeden önce geçmişi kontrol edin.");throw error}
  finally{clearTimeout(timeout);external?.removeEventListener('abort',abort)}
}

export type AnalysisPatientSummary=Pick<Patient,'id'|'anonymous_id'|'age'|'chief_complaint'>;
export type MobileAnalysisJob={id:number;kind:'VISION'|'PRELIMINARY'|'FINAL';status:string;retryable:boolean};
export type MobileAnalysis={
  analysis:{id:number;patient_id:number;tooth_number?:string|null;clinical_notes?:string|null;status:string;created_at?:string;is_voice_review?:boolean;legacy_radiograph_available?:boolean};
  patient:AnalysisPatientSummary;
  assets:Array<{id:number;original_filename:string;image_type:string;has_vision:boolean}>;
  job?:MobileAnalysisJob|null;
  ai_result?:any|null;
};
export function analysisPatientLabel(patient:Pick<Patient,'id'|'anonymous_id'|'first_name'|'last_name'>):string{
 const name=[patient.first_name,patient.last_name].map(value=>typeof value==='string'?value.trim():'').filter(Boolean).join(' ');
 return name||patient.anonymous_id||`Hasta #${patient.id}`;
}
function validAnalysisPatient(value:any,expectedId:number):value is AnalysisPatientSummary{
 if(!value||value.id!==expectedId||!Number.isSafeInteger(value.id))return false;
 const allowed=new Set(['id','anonymous_id','age','chief_complaint']);
 if(Object.keys(value).some(key=>!allowed.has(key)))return false;
 return typeof value.anonymous_id==='string'&&value.anonymous_id.length>0&&value.anonymous_id.length<=128&&
  (value.age===null||(Number.isSafeInteger(value.age)&&value.age>=0&&value.age<=130))&&
  (value.chief_complaint===null||(typeof value.chief_complaint==='string'&&value.chief_complaint.length<=4000));
}

const analysisFields=new Set(['id','patient_id','tooth_number','clinical_notes','status','created_at','is_voice_review','legacy_radiograph_available']);
const analysisAssetFields=new Set(['id','original_filename','image_type','has_vision']);
const analysisJobFields=new Set(['id','kind','status','retryable']);
function validAnalysisEnvelope(value:any,expectedId:number):boolean{
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!analysisFields.has(key)))return false;
 return value.id===expectedId&&Number.isSafeInteger(value.id)&&Number.isSafeInteger(value.patient_id)&&value.patient_id>0&&
  typeof value.status==='string'&&value.status.length>0&&value.status.length<=40&&
  (value.tooth_number===undefined||value.tooth_number===null||typeof value.tooth_number==='string'&&value.tooth_number.length<=128)&&
  (value.clinical_notes===undefined||value.clinical_notes===null||typeof value.clinical_notes==='string')&&
  (value.created_at===undefined||typeof value.created_at==='string'&&value.created_at.length<=64)&&
  (value.is_voice_review===undefined||typeof value.is_voice_review==='boolean')&&
  (value.legacy_radiograph_available===undefined||typeof value.legacy_radiograph_available==='boolean');
}
function validAnalysisAsset(value:any):boolean{
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!analysisAssetFields.has(key)))return false;
 return Number.isSafeInteger(value.id)&&value.id>0&&typeof value.original_filename==='string'&&
  value.original_filename.length>0&&value.original_filename.length<=255&&!/[\/\\\x00-\x1f\x7f]/.test(value.original_filename)&&
  typeof value.image_type==='string'&&/^[A-Z][A-Z0-9_]{0,39}$/.test(value.image_type)&&typeof value.has_vision==='boolean';
}
function validAnalysisJob(value:any):boolean{
 if(value===undefined||value===null)return true;
 return !!value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).every(key=>analysisJobFields.has(key))&&
  Number.isSafeInteger(value.id)&&value.id>0&&['VISION','PRELIMINARY','FINAL'].includes(value.kind)&&
  typeof value.status==='string'&&value.status.length>0&&value.status.length<=40&&typeof value.retryable==='boolean';
}

export function normalizeAnalysisImages(images:Array<{uri:string;name?:string;type?:string}>){
  if(!Array.isArray(images)||!images.length||images.length>ANALYSIS_MAX_IMAGES||images.some(i=>!i||typeof i.uri!=="string"||!i.uri))throw Error(`1–${ANALYSIS_MAX_IMAGES} geçerli klinik görüntü seçin.`);
  const allowedTypes=new Set(["image/jpeg","image/png","image/webp"]);
  const allowedExtensions=/\.(?:jpe?g|png|webp)$/i;
  // Never label PNG/WebP bytes as JPEG when the picker omits MIME metadata.
  const mimeForExtension:Record<string,string>={jpg:"image/jpeg",jpeg:"image/jpeg",png:"image/png",webp:"image/webp"};
  const normalizedImages=images.map((image,i)=>{
    // A missing picker filename must not silently turn PNG/WebP into a JPEG.
    const uriPath=image.uri.split(/[?#]/,1)[0];
    const uriExtension=uriPath.match(/\.([a-zA-Z0-9]+)$/)?.[1]?.toLowerCase();
    const declaredMime=typeof image.type==="string"?image.type.trim().toLowerCase():"";
    // Android content:// providers frequently return opaque URIs with no filename.
    // Use a recognized picker MIME only when neither filename nor URI identifies the format.
    const extensionForMime:Record<string,string>={"image/jpeg":"jpg","image/png":"png","image/webp":"webp"};
    const inferredExtension=uriExtension&&Object.prototype.hasOwnProperty.call(mimeForExtension,uriExtension)
      ? uriExtension : (!image.name?.trim()?extensionForMime[declaredMime]:"");
    const inferredName=inferredExtension?"dental-image-"+i+"."+inferredExtension:"";
    const name=image.name?.trim()||inferredName;
    if(/[/\\\x00-\x1f\x7f]/.test(name)||name.length>255)
      throw Error("Klinik görüntü dosya adı geçersiz.");
    const extension=name.match(/\.([^.]+)$/)?.[1]?.toLowerCase()||"";
    const expected=mimeForExtension[extension];
    const declared=typeof image.type==="string"&&image.type.trim()?image.type.trim().toLowerCase():expected;
    if(!allowedExtensions.test(name)||!expected||!allowedTypes.has(declared||"")||declared!==expected)
      throw Error("Yalnızca JPEG, PNG veya WebP klinik görüntüleri yüklenebilir; dosya türü ve uzantısı eşleşmelidir.");
    return {...image,name,type:declared};
  });
  return normalizedImages;
}

export async function createAnalysis(token:string,payload:{patientId:number;toothNumber?:string;clinicalNotes?:string;images:Array<{uri:string;name?:string;type?:string}>}){
  if(!Number.isSafeInteger(payload?.patientId)||payload.patientId<=0||!Array.isArray(payload.images)||!payload.images.length||payload.images.some(image=>!image||typeof image.uri!=="string"||!image.uri.trim()))throw Error("Analiz için geçerli hasta ve en az bir klinik görüntü seçin.");
  // Match the canonical mobile API's 1–4-image contract before any upload.
  if(payload.images.length>ANALYSIS_MAX_IMAGES)throw Error(`Bir analiz için en fazla ${ANALYSIS_MAX_IMAGES} klinik görüntü yüklenebilir.`);
  const normalizedImages=normalizeAnalysisImages(payload.images);
  const form=new FormData();
  form.append("patient_id",String(payload.patientId));
  if(payload.toothNumber)form.append("tooth_number",payload.toothNumber);
  if(payload.clinicalNotes)form.append("clinical_notes",payload.clinicalNotes);
  normalizedImages.forEach((image,i)=>{
    form.append("images",{uri:image.uri,name:image.name,type:image.type} as any);
  });
  const result=await call<{ok:boolean;analysis_id:number;status:string}>("/analyses",token,{method:"POST",body:form});
  if(!result?.ok||!Number.isSafeInteger(result.analysis_id)||result.analysis_id<=0)throw Error("Analiz oluşturuldu ancak sunucu geçerli bir iş kimliği döndürmedi.");
  return result;
}

export async function getAnalysis(token:string,id:number){
 if(!Number.isSafeInteger(id)||id<=0)throw Error("Geçersiz analiz kimliği.");
 const result=await call<MobileAnalysis>("/analyses/"+id,token);
 const topFields=new Set(['analysis','patient','assets','job','ai_result']);
 if(!result||typeof result!=='object'||Array.isArray(result)||Object.keys(result).some(key=>!topFields.has(key))||
    !validAnalysisEnvelope(result.analysis,id)||!validAnalysisPatient(result.patient,result.analysis.patient_id)||
    !Array.isArray(result.assets)||result.assets.length>ANALYSIS_MAX_IMAGES||result.assets.some(asset=>!validAnalysisAsset(asset))||
    new Set(result.assets.map(asset=>asset.id)).size!==result.assets.length||!validAnalysisJob(result.job))
  throw new ApiError(502,"Analiz yanıtı hasta kapsamı veya veri minimizasyonu sözleşmesini karşılamıyor.");
 return result;
}
export function startAnalysisAI(token:string,id:number){if(!Number.isSafeInteger(id)||id<=0)throw Error("Geçersiz analiz kimliği.");return call<{ok:boolean;status:string}>("/analyses/"+id+"/ai",token,{method:"POST"});}

export type AnalysisHistoryItem={id:number;patient_id:number;patient_name:string;tooth_number?:string|null;clinical_notes?:string|null;status:string;created_at:string};
export function getAnalysisHistory(token:string,patientId?:number){
  if(patientId!==undefined&&(!Number.isSafeInteger(patientId)||patientId<=0))throw Error("Geçersiz hasta kimliği.");
  return call<{items:AnalysisHistoryItem[]}>("/analyses"+(patientId!==undefined?"?patient_id="+patientId:""),token).then(result=>{
  if(!Array.isArray(result?.items)||new Set(result.items.map(item=>item?.id)).size!==result.items.length||result.items.some(item=>
    !item||!Number.isSafeInteger(item.id)||item.id<=0||
    !Number.isSafeInteger(item.patient_id)||item.patient_id<=0||
    (patientId!==undefined&&item.patient_id!==patientId)
  ))throw new ApiError(502,"Analiz geçmişinde hasta veya kayıt kimliği uyuşmayan yanıt alındı.");
  return result;
});
}
