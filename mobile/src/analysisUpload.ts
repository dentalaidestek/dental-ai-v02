import {ApiError,request} from './api';
import {normalizeAnalysisImages} from './analysisApi';
import {revalidateSession} from './sessionExpiry';
export type UploadImage={uri:string;name:string;type:string};
export type UploadIntent={userId:number;patientId:number;requestKey:string;toothNumber:string;clinicalNotes:string;images:UploadImage[];existingMediaIds?:number[]};
export type UploadReceipt={analysis_id:number;patient_id:number;job_id:number;status:string};
export function parseUploadIntent(raw:string,userId:number,patientId:number):UploadIntent{
 const v=JSON.parse(raw);if(v.userId!==userId||v.patientId!==patientId||!Number.isSafeInteger(userId)||userId<1||!Number.isSafeInteger(patientId)||patientId<1||typeof v.requestKey!=='string'||!/^[-_A-Za-z0-9]{16,80}$/.test(v.requestKey)||typeof v.toothNumber!=='string'||typeof v.clinicalNotes!=='string'||v.clinicalNotes.length>4000)throw Error('Bekleyen yükleme hesabı veya hasta kaydı doğrulanamadı.');
 validateUploadFields(v.toothNumber,v.clinicalNotes);
 const existingMediaIds=v.existingMediaIds===undefined?[]:v.existingMediaIds;
 if(!Array.isArray(existingMediaIds)||existingMediaIds.length>4||existingMediaIds.some((id:unknown)=>!Number.isSafeInteger(id)||Number(id)<=0)||new Set(existingMediaIds).size!==existingMediaIds.length)throw Error('Bekleyen kayıtlı klinik görüntüler doğrulanamadı.');
 if(!Array.isArray(v.images))throw Error('Bekleyen yeni klinik görüntüler doğrulanamadı.');
 const images=v.images.length?normalizeAnalysisImages(v.images):[];
 const mediaCount=existingMediaIds.length+images.length;if(mediaCount>4)throw Error('Kayıtlı ve yeni görüntülerin toplamı en fazla 4 olabilir.');if(mediaCount===0&&!v.toothNumber.trim()&&!v.clinicalNotes.trim())throw Error('Görüntü olmadan analiz başlatmak için diş numarası veya klinik bilgi girin.');
 if(images.some(i=>!i.uri.startsWith('file://')||i.uri.length>4096||i.uri.split('/').includes('..')||/[\x00-\x1f]/.test(i.uri)))throw Error('Bekleyen yüklemede yalnızca yerel uygulama dosyaları kullanılabilir.');
 return{...v,existingMediaIds,images};
}
export function validateUploadFields(tooth:string,notes:string){const teeth=tooth.split(',').map(t=>t.trim()).filter(Boolean);if(teeth.length>32||new Set(teeth).size!==teeth.length||teeth.some(t=>!/^(?:[1-4][1-8]|[5-8][1-5])$/.test(t)))throw Error('Geçerli FDI diş numaralarını virgülle ayırarak yazın.');if(notes.length>4000)throw Error('Klinik not en fazla 4000 karakter olabilir.');}
export function canStartAnalysis(tooth:string,notes:string,savedIds:number[],files:UploadImage[]){return savedIds.length+files.length>0||Boolean(tooth.trim()||notes.trim());}
function validReceipt(r:any,patientId:number):UploadReceipt{if(!r||!Number.isSafeInteger(r.analysis_id)||r.analysis_id<1||!Number.isSafeInteger(r.job_id)||r.job_id<1||typeof r.status!=='string'||r.patient_id!==patientId)throw new ApiError(502,'Yükleme fişi doğrulanamadı. Aynı yükleme kaydı korundu.');return r}
export async function analysisUploadReceipt(token:string,intent:UploadIntent){const r=await request<{receipt:UploadReceipt|null}>(`/analyses/uploads/receipt?patient_id=${intent.patientId}&request_key=${encodeURIComponent(intent.requestKey)}`,token);return r.receipt===null?null:validReceipt(r.receipt,intent.patientId)}
export function uploadAnalysis(token:string,intent:UploadIntent,progress:(percent:number)=>void,signal?:AbortSignal):Promise<UploadReceipt>{
 parseUploadIntent(JSON.stringify(intent),intent.userId,intent.patientId);
 return new Promise((resolve,reject)=>{
  if(signal?.aborted){reject(new ApiError(408,'Yükleme durduruldu; sunucu fişini kontrol edin.'));return}
  const xhr=new XMLHttpRequest(),body=new FormData();let settled=false;
  body.append('patient_id',String(intent.patientId));body.append('request_key',intent.requestKey);body.append('tooth_number',intent.toothNumber);body.append('clinical_notes',intent.clinicalNotes);if(intent.existingMediaIds?.length)body.append('existing_media_ids',intent.existingMediaIds.join(','));intent.images.forEach(image=>body.append('images',{uri:image.uri,name:image.name,type:image.type} as any));
  const finish=(error?:Error,receipt?:UploadReceipt)=>{if(settled)return;settled=true;clearTimeout(timer);signal?.removeEventListener('abort',cancel);error?reject(error):resolve(receipt!)};
  const uncertain=()=>new ApiError(408,'Aktarım sonucu belirsiz. Aynı yükleme kaydı korunuyor; sunucu fişini kontrol edin.');
  const cancel=()=>{try{xhr.abort()}finally{finish(uncertain())}},timer=setTimeout(cancel,600000);
  xhr.open('POST','https://dentalai.tr/api/mobile/v1/analyses');xhr.withCredentials=false;xhr.timeout=600000;xhr.setRequestHeader('Authorization','Bearer '+token);xhr.setRequestHeader('Cookie','');
  if(xhr.upload)xhr.upload.onprogress=e=>{if(!settled&&e.lengthComputable&&e.total>0)progress(Math.max(0,Math.min(100,Math.round(e.loaded/e.total*100))))};
  xhr.onerror=()=>finish(uncertain());xhr.ontimeout=cancel;xhr.onabort=()=>finish(uncertain());
  xhr.onload=()=>{void(async()=>{try{if(xhr.status===401)await revalidateSession(token);let r:any;try{r=JSON.parse(xhr.responseText)}catch{throw new ApiError(502,'Aktarım fişi okunamadı; aynı yükleme kaydı korundu.')}if(xhr.status<200||xhr.status>=300)throw new ApiError(xhr.status,typeof r.detail==='string'?r.detail:'Görüntü yüklenemedi. Sunucu kaydını kontrol edin.');finish(undefined,validReceipt(r,intent.patientId))}catch(e){finish(e instanceof Error?e:new Error('Aktarım doğrulanamadı.'))}})()};
  signal?.addEventListener('abort',cancel,{once:true});try{xhr.send(body)}catch(e){finish(e instanceof Error?e:uncertain())}
 });
}
