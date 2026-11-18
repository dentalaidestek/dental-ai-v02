import {request} from './api';
export type ClinicalJob={id:number;kind:'VISION'|'PRELIMINARY'|'FINAL';status:string;retryable:boolean};
export type ClinicalResult={status:string;most_likely?:string;findings?:unknown[];treatment_options?:string[];treatment_cautions?:string[];preferred_approach?:string;differential?:string[];recommended_evaluation?:string[];uncertainty?:string;preliminary_assessment?:string;questions?:Array<{question:string;type:string}>};
export type ClinicalWorkspace={analysis_id:number;patient_id:number;patient_anonymous_id:string;status:string;clinical_notes:string|null;tooth_number:string|null;revision:string;result:ClinicalResult|null;job:ClinicalJob|null;assets:Array<{id:number;image_type:string;has_vision:boolean;url:string}>};
export function clinicalAssetLabel(value:string){
 const modality=String(value||'').toUpperCase();
 return modality==='PANORAMIC'?'Panoramik':modality==='BITEWING'?'Bitewing':modality==='PERIAPICAL'?'Periapikal':modality==='INTRAORAL_PHOTO'?'Ağız içi':modality==='RADIOGRAPH'?'Radyografi':modality==='PHOTO'?'Klinik fotoğraf':'Görüntü';
}
export type ClinicalIntent={user:number;analysis:number;revision:string;answers:Record<string,string>};
export type ClinicalNoteIntent={user:number;analysis:number;note:string;finding:string;tooth:string};
export const clinicalNoteIntentKey=(user:number,analysis:number)=>`dai.clinical.note.${Number.isSafeInteger(user)&&user>0?user:'invalid'}.${id(analysis)}`;
export function parseClinicalNoteIntent(raw:string,user:number,analysis:number):ClinicalNoteIntent{
 const value=JSON.parse(raw);
 if(!value||value.user!==user||value.analysis!==analysis||typeof value.note!=='string'||value.note.length>2000||typeof value.finding!=='string'||value.finding.length>500||typeof value.tooth!=='string'||value.tooth.length>2||value.tooth!==''&&!/^(?:[1-4][1-8]|[5-8][1-5])$/.test(value.tooth)||!value.note.trim()&&!value.finding.trim())throw Error('Bekleyen hekim notu doğrulanamadı. Analiz notlarını kontrol edin.');
 return {user,analysis,note:value.note,finding:value.finding,tooth:value.tooth};
}
export function clinicalNoteLine(value:ClinicalNoteIntent){
 const prefix=value.tooth?`[Diş ${value.tooth}] `:'';
 return value.finding?prefix+'Manuel bulgu: '+value.finding+(value.note?' — '+value.note:''):prefix+value.note;
}

export function clinicalNoteIsPresent(notes:unknown,intent:ClinicalNoteIntent):boolean{
 if(typeof notes!=='string'||!notes)return false;
 const expected=clinicalNoteLine(intent);
 return notes.split(/\r?\n/).some(line=>line===expected);
}

const CLINICAL_RESULT_STATUSES=new Set(['INITIAL','ANALYSIS_COMPLETE','FINAL','NEEDS_INFO','READY','AI_ANALYZING','AI_ANALYZED','AI_ERROR','AI_INVALID']);
const CLINICAL_TEXT_LIMITS:Record<string,number>={most_likely:4000,preferred_approach:4000,uncertainty:4000,preliminary_assessment:4000,error:1000};
const CLINICAL_LIST_LIMITS:Record<string,{items:number;chars:number}>={findings:{items:3,chars:2000},treatment_options:{items:3,chars:2000},treatment_cautions:{items:3,chars:2000},differential:{items:2,chars:2000},recommended_evaluation:{items:2,chars:2000}};
function boundedText(value:unknown,limit:number,allowEmpty=false):value is string{
 return typeof value==='string'&&value.length<=limit&&(allowEmpty||!!value.trim());
}
function boundedTextList(value:unknown,items:number,chars:number):value is string[]{
 return Array.isArray(value)&&value.length<=items&&value.every(item=>boundedText(item,chars));
}
function validClinicalResult(value:unknown):value is ClinicalResult|null{
 if(value===null)return true;
 if(!value||typeof value!=='object'||Array.isArray(value))return false;
 const result=value as Record<string,unknown>;
 if(typeof result.status!=='string'||!CLINICAL_RESULT_STATUSES.has(result.status))return false;
 const allowEmpty=['NEEDS_INFO','READY','AI_ANALYZING','AI_ERROR','AI_INVALID'].includes(result.status);
 for(const [field,limit] of Object.entries(CLINICAL_TEXT_LIMITS)){
  if(field in result&&!boundedText(result[field],limit,allowEmpty))return false;
 }
 for(const [field,limit] of Object.entries(CLINICAL_LIST_LIMITS)){
  if(field in result&&!boundedTextList(result[field],limit.items,limit.chars))return false;
 }
 if('questions' in result){
  if(!Array.isArray(result.questions)||result.questions.length>3||result.questions.some(item=>!item||typeof item!=='object'||Array.isArray(item)||!boundedText((item as Record<string,unknown>).question,2000)|| (item as Record<string,unknown>).type!=='TEXT'))return false;
 }
 if(result.status==='INITIAL'||result.status==='ANALYSIS_COMPLETE'){
  if(!boundedText(result.most_likely,4000)||!boundedText(result.preferred_approach,4000)||!boundedText(result.uncertainty,4000)
   ||!boundedTextList(result.findings,3,2000)||!boundedTextList(result.treatment_options,3,2000)
   ||!boundedTextList(result.treatment_cautions,3,2000)||!boundedTextList(result.differential,2,2000)
   ||!boundedTextList(result.recommended_evaluation,2,2000)||!Array.isArray(result.questions))return false;
 }
 if(result.status==='FINAL'){
  if(!boundedText(result.most_likely,4000)||!boundedText(result.preferred_approach,4000)
   ||!boundedTextList(result.findings,3,2000)||!boundedTextList(result.treatment_options,3,2000)
   ||!boundedTextList(result.treatment_cautions,3,2000)||!boundedTextList(result.differential,2,2000))return false;
 }
 return true;
}

const id=(value:number)=>{if(!Number.isSafeInteger(value)||value<1)throw Error('Geçersiz analiz kimliği.');return value};
const path=(analysis:number)=>'/analyses/'+id(analysis);
export async function getClinical(token:string,analysis:number){
 const r=await request<ClinicalWorkspace>(path(analysis)+'/clinical',token);
 const assets=Array.isArray(r?.assets)?r.assets:[];
 const allowedAssetKeys=new Set(['id','image_type','has_vision','url']);
 const validAssets=assets.length<=4&&new Set(assets.map(x=>x?.id)).size===assets.length&&assets.every(x=>x&&typeof x==='object'&&!Array.isArray(x)&&Object.keys(x).every(key=>allowedAssetKeys.has(key))&&Number.isSafeInteger(x.id)&&x.id>0&&typeof x.image_type==='string'&&/^[A-Z][A-Z0-9_]{0,39}$/.test(x.image_type)&&typeof x.has_vision==='boolean'&&typeof x.url==='string'&&x.url===`/api/mobile/v1/analyses/${analysis}/assets/${x.id}`);
 const job=r?.job;
 const validJob=job===null||!!job&&Number.isSafeInteger(job.id)&&job.id>0&&['VISION','PRELIMINARY','FINAL'].includes(job.kind)&&typeof job.status==='string'&&job.status.length>0&&job.status.length<=40&&typeof job.retryable==='boolean';
 if(!r||r.analysis_id!==analysis||!Number.isSafeInteger(r.patient_id)||r.patient_id<1||typeof r.patient_anonymous_id!=='string'||!r.patient_anonymous_id.trim()||r.patient_anonymous_id.length>80||!validAssets||!/^([0-9a-f]{64})$/.test(r.revision)||typeof r.status!=='string'||typeof r.clinical_notes!=='string'&&r.clinical_notes!==null||typeof r.tooth_number!=='string'&&r.tooth_number!==null||!validJob||!validClinicalResult(r.result))throw Error('Klinik sonuç doğrulanamadı.');
 return r;
}
export function parseClinicalIntent(raw:string,user:number,analysis:number):ClinicalIntent{const r=JSON.parse(raw);if(r.user!==user||r.analysis!==analysis||!/^([0-9a-f]{64})$/.test(r.revision)||!r.answers||typeof r.answers!=='object'||Array.isArray(r.answers)||Object.keys(r.answers).length>3||Object.entries(r.answers).some(([k,v])=>!/^answer_[0-2]$/.test(k)||typeof v!=='string'||!v.trim()||v.length>2000))throw Error('Bekleyen klinik cevap kaydı okunamadı. Analiz geçmişini kontrol edin.');return r}
export async function submitClinical(token:string,intent:ClinicalIntent){const r=await request<{ok:boolean;job:ClinicalJob}>(path(intent.analysis)+'/final-review',token,{method:'POST',body:JSON.stringify({revision:intent.revision,answers:intent.answers})});if(r.ok!==true||!r.job||!Number.isSafeInteger(r.job.id)||r.job.id<1||r.job.kind!=='FINAL')throw Error('Nihai iş kaydı doğrulanamadı. Aynı klinik cevap kaydı korundu.');return r}
export const saveClinicalNote=(t:string,a:number,value:{note:string;finding:string;tooth:string})=>request<{ok:boolean}>(path(a)+'/clinical-note',t,{method:'POST',body:JSON.stringify(value)});
export const analyzeTeeth=(t:string,a:number,teeth:string[])=>request<{ok:boolean;job:ClinicalJob}>(path(a)+'/selected-teeth',t,{method:'POST',body:JSON.stringify({teeth})});
export const clinicalJobAction=(t:string,a:number,j:number,action:'cancel'|'retry')=>request<{ok:boolean}>(path(a)+`/jobs/${id(j)}/${action}`,t,{method:'POST'});
export function clinicalImage(token:string,a:number,idValue:number){return{uri:'https://dentalai.tr/api/mobile/v1'+path(a)+'/assets/'+id(idValue),headers:{Authorization:'Bearer '+token,Cookie:''}}}
export const clinicalBusy=(data:ClinicalWorkspace|null)=>!!data?.job&&['QUEUED','RUNNING'].includes(data.job.status);
export async function getVision(token:string,analysis:number,asset:number,modality:string){const r=await request<any>(path(analysis)+`/assets/${id(asset)}/vision`,token);if(r.status==='VISION_PENDING')return{pending:true as const,findings:[]};if(r.ok===false)throw Error('Görüntü bulguları okunamadı. İş durumunu kontrol edin.');const {visionFindings}=await import('./visionModel');return{pending:false as const,findings:visionFindings(r,modality)};}
