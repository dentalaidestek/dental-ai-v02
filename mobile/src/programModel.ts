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
