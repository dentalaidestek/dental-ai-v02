import {request} from './api';
import {ProgramDraft,programPayload,validWallTime} from './programModel';
import type {ProgramActionIntent} from './programIntent';
export type ProgramView='today'|'week'|'month';
export type ProgramOccurrence={key:string;event_id:number;event_type:string;title:string;status:string;start_local:string;end_local:string|null;patient_id:number|null;patient_name:string|null;location:string|null;notes:string|null;recurrence_rule:string};
export type ProgramEvent=Omit<ProgramOccurrence,'key'|'event_id'>&{id:number;reminder_minutes:string;recurrence_until:string|null;revision:string};
export type ProgramPage={copy_days:Array<{date:string;label:string}>;month_title:string;view:ProgramView;focus_date:string;today:string;timezone:string;previous_day:string;next_day:string;days:Array<{date:string;label:string;in_month:boolean;count:number;event_types?:string[];has_more?:boolean}>;items:ProgramOccurrence[];total:number;next_offset:number|null;next_cursor?:string|null;event_types:Record<string,string>;reminders:string[];recurrences:string[];suggested_start_local:string;suggested_end_local:string};
const id=(value:number)=>{if(!Number.isSafeInteger(value)||value<=0)throw Error('Geçersiz program kaydı.');return value;};
const PROGRAM_EVENT_TYPES=new Set(['APPOINTMENT','CLASS','CLINIC','EXAM','ASSIGNMENT','THESIS','MEETING','TASK','PERSONAL']);
const PROGRAM_REMINDER_VALUES=new Set(['NONE','0','15','30','60','120','1440']);
const PROGRAM_RECURRENCES=new Set(['NONE','WEEKLY']);
function nullableText(value:unknown,max:number):boolean{return value===null||typeof value==='string'&&value.length<=max;}
function validProgramDay(value:unknown):value is string{
 if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
 const parsed=Date.parse(value+'T00:00:00.000Z');
 return Number.isFinite(parsed)&&new Date(parsed).toISOString().slice(0,10)===value;
}
function eventValid(event:ProgramEvent):boolean{
 if(!event||!Number.isSafeInteger(event.id)||event.id<=0||!PROGRAM_EVENT_TYPES.has(event.event_type)||
    typeof event.title!=='string'||!event.title.trim()||event.title.length>160||
    !['ACTIVE','COMPLETED','DELETED'].includes(event.status)||!validWallTime(event.start_local)||
    !(event.end_local===null||event.end_local===''||validWallTime(event.end_local)&&event.end_local>=event.start_local)||
    !(event.patient_id===null||Number.isSafeInteger(event.patient_id)&&event.patient_id>0)||
    !nullableText(event.patient_name,240)||!nullableText(event.location,160)||!nullableText(event.notes,2000)||
    !PROGRAM_REMINDER_VALUES.has(event.reminder_minutes)||!PROGRAM_RECURRENCES.has(event.recurrence_rule)||
    typeof event.revision!=='string'||!/^[0-9a-f]{64}$/.test(event.revision)||
    !(event.recurrence_until===null||event.recurrence_until===''||validProgramDay(event.recurrence_until)&&event.recurrence_until>=event.start_local.slice(0,10)))return false;
 return true;
}
function occurrenceValid(item:ProgramOccurrence):boolean{
 return !!item&&typeof item.key==='string'&&item.key.length>0&&item.key.length<=512&&
  Number.isSafeInteger(item.event_id)&&item.event_id>0&&PROGRAM_EVENT_TYPES.has(item.event_type)&&
  typeof item.title==='string'&&!!item.title.trim()&&item.title.length<=160&&
  ['ACTIVE','COMPLETED'].includes(item.status)&&validWallTime(item.start_local)&&
  (item.end_local===null||item.end_local===''||validWallTime(item.end_local)&&item.end_local>=item.start_local)&&
  (item.patient_id===null||Number.isSafeInteger(item.patient_id)&&item.patient_id>0)&&
  nullableText(item.patient_name,240)&&nullableText(item.location,160)&&nullableText(item.notes,2000)&&
  PROGRAM_RECURRENCES.has(item.recurrence_rule);
}
const cursorValid=(value:unknown):value is string=>typeof value==='string'&&value.length<=512&&/^[A-Za-z0-9_-]{16,512}$/.test(value);

/** Compare every persisted field, not only the start time and patient ID. */
export function programEventMatchesPayload(event:ProgramEvent,draft:ProgramDraft):boolean{
 let values:ProgramDraft;
 try{values=programPayload(draft)}catch{return false;}
 return eventValid(event)&&event.status!=='DELETED'&&
  event.event_type===values.event_type&&event.title===values.title&&
  event.start_local===values.start_at&&(event.end_local||'')===(values.end_at||'')&&
  (event.patient_id??undefined)===(values.patient_id??undefined)&&
  (event.location||'')===values.location&&(event.notes||'')===values.notes&&
  event.reminder_minutes===values.reminder_minutes&&event.recurrence_rule===values.recurrence_rule&&
  (event.recurrence_until||'')===(values.recurrence_rule==='WEEKLY'?values.recurrence_until:'');
}

export async function getProgram(token:string,view:ProgramView,day?:string,cursor?:string,offset=0){
 if(!['today','week','month'].includes(view)||day!==undefined&&!validProgramDay(day)||!Number.isSafeInteger(offset)||offset<0||cursor!==undefined&&!cursorValid(cursor)||cursor!==undefined&&offset!==0)throw Error('Geçersiz takvim seçimi.');
 const pageQuery=cursor!==undefined?`&cursor=${cursor}`:offset?`&offset=${offset}`:'';
 const result=await request<ProgramPage>(`/program?view=${view}`+pageQuery+(day?`&day=${day}`:''),token);
 const expectedDays=view==='month'?42:view==='week'?7:1;
 if(!result||result.view!==view||day&&result.focus_date!==day||result.timezone!=='Europe/Istanbul'||
    !validProgramDay(result.focus_date)||!validProgramDay(result.today)||!validProgramDay(result.previous_day)||!validProgramDay(result.next_day)||
    !Array.isArray(result.items)||result.items.length>50||new Set(result.items.map(x=>x?.key)).size!==result.items.length||result.items.some(x=>!occurrenceValid(x))||
    !Array.isArray(result.days)||result.days.length!==expectedDays||new Set(result.days.map(d=>d?.date)).size!==result.days.length||
    result.days.some(d=>!d||!validProgramDay(d.date)||typeof d.label!=='string'||d.label.length>32||typeof d.in_month!=='boolean'||
      !Number.isSafeInteger(d.count)||d.count<0||(d.event_types!==undefined&&(!Array.isArray(d.event_types)||d.event_types.length>3||d.event_types.some(type=>typeof type!=='string'||!PROGRAM_EVENT_TYPES.has(type))))||
      (d.has_more!==undefined&&typeof d.has_more!=='boolean'))||
    !Array.isArray(result.copy_days)||result.copy_days.length!==7||new Set(result.copy_days.map(d=>d?.date)).size!==7||
    result.copy_days.some(d=>!d||!validProgramDay(d.date)||typeof d.label!=='string'||d.label.length>32)||
    typeof result.month_title!=='string'||result.month_title.length>80||
    !result.event_types||typeof result.event_types!=='object'||Array.isArray(result.event_types)||
    Object.entries(result.event_types).some(([key,value])=>!PROGRAM_EVENT_TYPES.has(key)||typeof value!=='string'||!value.trim()||value.length>80)||
    !Array.isArray(result.reminders)||result.reminders.some(value=>typeof value!=='string'||!PROGRAM_REMINDER_VALUES.has(value))||
    !Array.isArray(result.recurrences)||result.recurrences.some(value=>typeof value!=='string'||!PROGRAM_RECURRENCES.has(value))||
    !validWallTime(result.suggested_start_local)||!validWallTime(result.suggested_end_local)||result.suggested_end_local<result.suggested_start_local||
    !Number.isSafeInteger(result.total)||result.total<result.items.length||
    (result.next_offset!==null&&(!Number.isSafeInteger(result.next_offset)||result.next_offset<offset+result.items.length||result.items.length===0))||
    (result.next_cursor!==undefined&&result.next_cursor!==null&&(!cursorValid(result.next_cursor)||result.items.length===0||result.next_cursor===cursor)))
  throw Error('Sunucudan geçersiz takvim verisi alındı. Yenileyin.');
 return result;
}
export async function getProgramEvent(token:string,eventId:number){const result=await request<{event:ProgramEvent}>(`/program/events/${id(eventId)}`,token);if(!eventValid(result.event)||result.event.id!==eventId)throw Error('Program kaydı doğrulanamadı.');return result.event;}
const requestKeyValid=(value:string)=>/^[A-Za-z0-9_-]{16,96}$/.test(value);
export type ProgramMutationReceipt={state:'NOT_FOUND'}|{state:'DELETED';event_id:number}|{state:'FOUND';event:ProgramEvent};
export async function getProgramMutation(token:string,requestKey:string):Promise<ProgramMutationReceipt>{
 if(!requestKeyValid(requestKey))throw Error('Geçersiz Program istek anahtarı.');
 const result=await request<ProgramMutationReceipt>(`/program/mutations/${requestKey}`,token);
 if(result.state==='NOT_FOUND')return result;
 if(result.state==='DELETED'&&Number.isSafeInteger(result.event_id)&&result.event_id>0)return result;
 if(result.state==='FOUND'&&eventValid(result.event))return result;
 throw Error('Bekleyen Program kaydı sunucuda doğrulanamadı.');
}
export async function saveProgramEvent(token:string,draft:ProgramDraft,eventId?:number,requestKey?:string,expectedRevision?:string){
 const values=programPayload(draft);
 if(eventId===undefined&&(!requestKey||!requestKeyValid(requestKey)))throw Error('Yeni Program kaydı için güvenli istek anahtarı gerekli.');
 if(eventId!==undefined&&(!expectedRevision||!/^[0-9a-f]{64}$/.test(expectedRevision)))throw Error('Program düzenlemesi için güncel sürüm anahtarı gerekli.');
 const body=eventId===undefined?{...values,request_key:requestKey}:{...values,expected_revision:expectedRevision};
 const result=await request<{event:ProgramEvent}>('/program/events'+(eventId!==undefined?`/${id(eventId)}`:''),token,{method:eventId!==undefined?'PUT':'POST',body:JSON.stringify(body)});
 if(!eventValid(result.event)||eventId!==undefined&&result.event.id!==eventId||!programEventMatchesPayload(result.event,values))
  throw Error('Program kaydı sunucudan doğrulanamadı. Yeniden göndermeden önce takvimi kontrol edin.');
 return result.event;
}
export async function programAction(token:string,eventId:number,action:'complete'|'delete'|'copy',days?:string[]){
 if(action==='copy'&&(!days?.length||days.length>7||days.some(day=>!validProgramDay(day))))throw Error('Kopyalanacak günleri seçin.');
 const result=await request<{ok:boolean}>(`/program/events/${id(eventId)}`+(action==='delete'?'':`/${action}`),token,{method:action==='delete'?'DELETE':'POST',...(action==='copy'?{body:JSON.stringify({days})}:{})});
 if(result.ok!==true)throw Error('Program işlemi doğrulanamadı. Takvimi yenileyin.');
 return result;
}

export async function checkProgramConflicts(token:string,draft:ProgramDraft,eventId?:number){
 const result=await request<{advisory:boolean;total:number}>('/program/conflicts'+(eventId!==undefined?`?exclude_id=${id(eventId)}`:''),token,{method:'POST',body:JSON.stringify(programPayload(draft))});
 if(result.advisory!==true||!Number.isSafeInteger(result.total)||result.total<0)throw Error('Saat çakışması kontrol edilemedi. Yeniden deneyin.');
 return result;
}

export type ProgramActionVerification='APPLIED'|'NOT_APPLIED'|'UNKNOWN';

function expectedCopyEnd(source:ProgramEvent,targetDay:string):string{
 if(!source.end_local)return '';
 const sourceStart=Date.parse(source.start_local+':00Z');
 const sourceEnd=Date.parse(source.end_local+':00Z');
 const targetStart=Date.parse(targetDay+'T'+source.start_local.slice(11)+':00Z');
 if(!Number.isFinite(sourceStart)||!Number.isFinite(sourceEnd)||!Number.isFinite(targetStart)||sourceEnd<sourceStart)throw Error('Kopyalanan program saati doğrulanamadı.');
 return new Date(targetStart+(sourceEnd-sourceStart)).toISOString().slice(0,16);
}

/**
 * A calendar refresh alone is not proof that a timed-out action committed.
 * Verify the exact owned event state; for copies, inspect every requested day
 * through the same stable cursor/legacy offset contract used by the calendar.
 */
export async function verifyProgramAction(token:string,intent:ProgramActionIntent):Promise<ProgramActionVerification>{
 const source=await getProgramEvent(token,intent.event_id);
 if(intent.action==='delete'){
  if(source.status==='DELETED')return 'APPLIED';
  if(source.status==='ACTIVE'||source.status==='COMPLETED')return 'NOT_APPLIED';
  return 'UNKNOWN';
 }
 if(intent.action==='complete'){
  if(source.status==='COMPLETED')return 'APPLIED';
  if(source.status==='ACTIVE')return 'NOT_APPLIED';
  return 'UNKNOWN';
 }
 if(!('days' in intent))return 'UNKNOWN';
 let allFound=true;
 for(const day of intent.days){
  const expectedStart=day+'T'+source.start_local.slice(11);
  const expectedEnd=expectedCopyEnd(source,day);
  let cursor:string|undefined;
  let offset=0;
  let pages=0;
  let found=false;
  while(true){
   const page=await getProgram(token,'today',day,cursor,offset);
   found=page.items.some(item=>
    item.event_type===source.event_type&&item.title===source.title&&
    item.start_local===expectedStart&&item.end_local===expectedEnd&&
    item.patient_id===source.patient_id&&(item.location||'')===(source.location||'')&&
    (item.notes||'')===(source.notes||'')&&item.recurrence_rule==='NONE'
   );
   if(found)break;
   if(page.next_cursor){cursor=page.next_cursor;offset=0;}
   else if(page.next_offset!==null){cursor=undefined;offset=page.next_offset;}
   else break;
   pages++;
   if(pages>=20)return 'UNKNOWN';
  }
  if(!found)allFound=false;
 }
 return allFound?'APPLIED':'NOT_APPLIED';
}

