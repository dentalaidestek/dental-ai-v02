import {request} from './api';
export type ClinicalJob={id:number;kind:'VISION'|'PRELIMINARY'|'FINAL';status:string;retryable:boolean};
export type ClinicalResult={status:string;most_likely?:string;findings?:unknown[];treatment_options?:string[];treatment_cautions?:string[];preferred_approach?:string;differential?:string[];recommended_evaluation?:string[];uncertainty?:string;preliminary_assessment?:string;questions?:Array<{question:string;type:string}>};
export type ClinicalWorkspace={analysis_id:number;patient_id:number;patient_anonymous_id:string;status:string;clinical_notes:string|null;tooth_number:string|null;revision:string;result:ClinicalResult|null;job:ClinicalJob|null;assets:Array<{id:number;name:string;image_type:string;has_vision:boolean;url:string}>};
export type ClinicalIntent={user:number;analysis:number;revision:string;answers:Record<string,string>};
const id=(value:number)=>{if(!Number.isSafeInteger(value)||value<1)throw Error('Geçersiz analiz kimliği.');return value};
const path=(analysis:number)=>'/analyses/'+id(analysis);
export async function getClinical(token:string,analysis:number){
 const r=await request<ClinicalWorkspace>(path(analysis)+'/clinical',token);
 const assets=Array.isArray(r?.assets)?r.assets:[];
 const validAssets=assets.length<=4&&new Set(assets.map(x=>x?.id)).size===assets.length&&assets.every(x=>x&&Number.isSafeInteger(x.id)&&x.id>0&&typeof x.name==='string'&&x.name.length<=255&&typeof x.image_type==='string'&&x.image_type.length<=40&&typeof x.has_vision==='boolean'&&typeof x.url==='string'&&x.url===`/api/mobile/v1/analyses/${analysis}/assets/${x.id}`);
 const job=r?.job;
 const validJob=job===null||!!job&&Number.isSafeInteger(job.id)&&job.id>0&&['VISION','PRELIMINARY','FINAL'].includes(job.kind)&&typeof job.status==='string'&&job.status.length>0&&job.status.length<=40&&typeof job.retryable==='boolean';
 if(!r||r.analysis_id!==analysis||!Number.isSafeInteger(r.patient_id)||r.patient_id<1||typeof r.patient_anonymous_id!=='string'||!r.patient_anonymous_id.trim()||r.patient_anonymous_id.length>80||!validAssets||!/^([0-9a-f]{64})$/.test(r.revision)||typeof r.status!=='string'||typeof r.clinical_notes!=='string'&&r.clinical_notes!==null||typeof r.tooth_number!=='string'&&r.tooth_number!==null||!validJob||r.result!==null&&(!r.result||typeof r.result!=='object'||typeof r.result.status!=='string'))throw Error('Klinik sonuç doğrulanamadı.');
 return r;
}
export function parseClinicalIntent(raw:string,user:number,analysis:number):ClinicalIntent{const r=JSON.parse(raw);if(r.user!==user||r.analysis!==analysis||!/^([0-9a-f]{64})$/.test(r.revision)||!r.answers||typeof r.answers!=='object'||Array.isArray(r.answers)||Object.keys(r.answers).length>3||Object.entries(r.answers).some(([k,v])=>!/^answer_[0-2]$/.test(k)||typeof v!=='string'||!v.trim()||v.length>2000))throw Error('Bekleyen klinik cevap kaydı okunamadı. Analiz geçmişini kontrol edin.');return r}
export async function submitClinical(token:string,intent:ClinicalIntent){const r=await request<{ok:boolean;job:ClinicalJob}>(path(intent.analysis)+'/final-review',token,{method:'POST',body:JSON.stringify({revision:intent.revision,answers:intent.answers})});if(r.ok!==true||!r.job||!Number.isSafeInteger(r.job.id)||r.job.id<1||r.job.kind!=='FINAL')throw Error('Nihai iş kaydı doğrulanamadı. Aynı klinik cevap kaydı korundu.');return r}
export const saveClinicalNote=(t:string,a:number,value:{note:string;finding:string;tooth:string})=>request<{ok:boolean}>(path(a)+'/clinical-note',t,{method:'POST',body:JSON.stringify(value)});
export const analyzeTeeth=(t:string,a:number,teeth:string[])=>request<{ok:boolean;job:ClinicalJob}>(path(a)+'/selected-teeth',t,{method:'POST',body:JSON.stringify({teeth})});
export const clinicalJobAction=(t:string,a:number,j:number,action:'cancel'|'retry')=>request<{ok:boolean}>(path(a)+`/jobs/${id(j)}/${action}`,t,{method:'POST'});
export function clinicalImage(token:string,a:number,idValue:number){return{uri:'https://dentalai.tr/api/mobile/v1'+path(a)+'/assets/'+id(idValue),headers:{Authorization:'Bearer '+token,Cookie:''}}}
export const clinicalBusy=(data:ClinicalWorkspace|null)=>!!data?.job&&['QUEUED','RUNNING'].includes(data.job.status);
export async function getVision(token:string,analysis:number,asset:number){const r=await request<any>(path(analysis)+`/assets/${id(asset)}/vision`,token);if(r.status==='VISION_PENDING')return{pending:true as const,findings:[]};if(r.ok===false)throw Error('Görüntü bulguları okunamadı. İş durumunu kontrol edin.');const {visionFindings}=await import('./visionModel');return{pending:false as const,findings:visionFindings(r)};}
