import {parseClinicalDate} from './clinicalDate';
export type ProgramDraft={event_type:string;title:string;start_at:string;end_at:string;patient_id?:number;location:string;notes:string;reminder_minutes:string;recurrence_rule:string;recurrence_until:string};
const PROGRAM_REMINDER_VALUES=new Set(['NONE','0','15','30','60','120','1440']);

export function programTitleCopy(type:string){
 const labels:Record<string,{label:string;placeholder:string}>={
  APPOINTMENT:{label:'Randevu başlığı',placeholder:'Örn. Kontrol randevusu'},
  CLASS:{label:'Ders adı',placeholder:'Örn. Ortodonti'},
  CLINIC:{label:'Klinik / pratik başlığı',placeholder:'Örn. Endodonti kliniği'},
  EXAM:{label:'Sınav adı',placeholder:'Örn. Ortodonti sınavı'},
  ASSIGNMENT:{label:'Ödev başlığı',placeholder:'Örn. Vaka sunumu'},
  THESIS:{label:'Tez çalışması',placeholder:'Örn. Literatür taraması'},
  MEETING:{label:'Toplantı başlığı',placeholder:'Örn. Bölüm toplantısı'},
  TASK:{label:'Görev başlığı',placeholder:'Örn. Hasta dosyalarını tamamla'},
  PERSONAL:{label:'Kişisel plan',placeholder:'Örn. Spor'}
 };
 return labels[type]||{label:'Başlık',placeholder:'Program başlığı'};
}

export function validWallTime(value:string){if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value))return false;return !!parseClinicalDate(value.slice(0,10))&&Number(value.slice(11,13))<24&&Number(value.slice(14,16))<60;}
export function programPayload(draft:ProgramDraft):ProgramDraft{
 if(!draft.title.trim()||draft.title.trim().length<2||draft.title.trim().length>160||!validWallTime(draft.start_at)||draft.end_at&&(!validWallTime(draft.end_at)||draft.end_at<draft.start_at))throw Error('Başlık ve başlangıç/bitiş tarihlerini kontrol edin.');
 if(draft.location.length>160)throw Error('Konum en fazla 160 karakter olabilir.');
 if(draft.notes.length>2000)throw Error('Notlar en fazla 2000 karakter olabilir.');
 if(!PROGRAM_REMINDER_VALUES.has(draft.reminder_minutes))throw Error('Hatırlatma seçimini kontrol edin.');
 if(!['NONE','WEEKLY'].includes(draft.recurrence_rule))throw Error('Tekrarlama seçeneğini kontrol edin.');
 if(draft.recurrence_rule==='WEEKLY'&&draft.recurrence_until&&(!parseClinicalDate(draft.recurrence_until)||draft.recurrence_until<draft.start_at.slice(0,10)))throw Error('Tekrar bitişi başlangıç tarihinden önce olamaz.');
 const {patient_id,...rest}=draft;
 if(patient_id!==undefined&&(!Number.isSafeInteger(patient_id)||patient_id<=0))throw Error('Gerçek bir hasta kaydı seçin.');
 return {...rest,title:draft.title.trim(),recurrence_until:draft.recurrence_rule==='WEEKLY'?draft.recurrence_until:'',...(['APPOINTMENT','CLINIC'].includes(draft.event_type)&&patient_id!==undefined?{patient_id}:{})};
}
export function wallTimeLabel(value:string){return validWallTime(value)?value.slice(11,16):'—';}
export function dayTitle(value:string){if(!parseClinicalDate(value))return value;const [year,month,day]=value.split('-');return `${day}.${month}.${year}`;}

/**
 * A reminder chosen as "N minutes before" can no longer fire when the fire
 * time (start minus N minutes) has already passed. Pure client computation
 * from the editor draft; wall-clock strings are local Europe/Istanbul times.
 */
export function reminderFiresInPast(startLocal:string,reminderMinutes:string,now:Date=new Date()):boolean{
 if(reminderMinutes==='NONE'||!/^\d{1,5}$/.test(reminderMinutes))return false;
 if(!validWallTime(startLocal))return false;
 const [datePart,timePart]=startLocal.split('T'),[year,month,day]=datePart.split('-').map(Number),[hour,minute]=timePart.split(':').map(Number);
 const start=new Date(year,month-1,day,hour,minute).getTime();
 return start-Number(reminderMinutes)*60000<now.getTime();
}

/**
 * Client-side rendering of the advisory rows: the intersecting calendar items
 * ("ss:dd · başlık (hasta)") for the conflict confirmation dialog, derived
 * from the already-loaded week page. Purely informative; the authoritative
 * total still comes from the server advisory.
 */
export function programConflictRows(draft:Pick<ProgramDraft,'start_at'|'end_at'>,items:Array<{title:string;start_local:string;end_local:string|null;patient_name:string|null}>,limit=3):string[]{
 if(!validWallTime(draft.start_at))return [];
 const endRef=draft.end_at&&validWallTime(draft.end_at)&&draft.end_at>=draft.start_at?draft.end_at:draft.start_at;
 const rows:string[]=[];
 for(const item of items||[]){
  if(!item||typeof item.title!=='string'||!item.title.trim()||!validWallTime(item.start_local))continue;
  const itemEnd=item.end_local&&validWallTime(item.end_local)&&item.end_local>=item.start_local?item.end_local:item.start_local;
  if(item.start_local<=endRef&&itemEnd>draft.start_at){
   rows.push(wallTimeLabel(item.start_local)+' · '+item.title+(item.patient_name?' ('+item.patient_name+')':''));
   if(rows.length>=limit)break;
  }
 }
 return rows;
}

/** Follow-up control appointment date: completed event's day + N days. */
export function programFollowUpDate(value:string,days:number):string{
 if(!parseClinicalDate(value)||!Number.isInteger(days)||days<=0)return value;
 const [year,month,day]=value.split('-').map(Number);
 const next=new Date(Date.UTC(year,month-1,day));
 next.setUTCDate(next.getUTCDate()+days);
 return next.toISOString().slice(0,10);
}
