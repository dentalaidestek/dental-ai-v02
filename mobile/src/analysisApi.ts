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

export type MobileAnalysis={
  analysis:{id:number;patient_id:number;tooth_number?:string|null;clinical_notes?:string|null;status:string;created_at?:string;is_voice_review?:boolean};
  patient:Patient;
  assets:Array<{id:number;original_filename:string;image_type:string;has_vision:boolean}>;
  ai_result?:any|null;
};

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

export async function getAnalysis(token:string,id:number){if(!Number.isSafeInteger(id)||id<=0)throw Error("Geçersiz analiz kimliği.");const result=await call<MobileAnalysis>("/analyses/"+id,token);if(!result?.analysis||result.analysis.id!==id||!Number.isSafeInteger(result.analysis.patient_id)||result.analysis.patient_id<=0||!result.patient||result.patient.id!==result.analysis.patient_id||!Array.isArray(result.assets)||result.assets.some(asset=>!asset||!Number.isSafeInteger(asset.id)||asset.id<=0)||new Set(result.assets.map(asset=>asset.id)).size!==result.assets.length)throw Error("Analiz sunucusundan hasta veya iş kimliği uyuşmayan yanıt alındı.");return result;}
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
