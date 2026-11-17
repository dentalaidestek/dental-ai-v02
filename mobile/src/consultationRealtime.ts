export type ConsultationRealtimeEvent={
 event_id?:number;id?:number;event_type?:string;type?:string;entity_id?:number|string;payload?:any;
};
export type ConsultationInboxRow={
 id:number;status?:string;last_message?:string|null;last_message_at?:string|null;
 last_message_id?:number;unread_count?:number;
};
export function applyConsultationInboxEvent<T extends ConsultationInboxRow>(
 items:T[],event:ConsultationRealtimeEvent,userId:number
):{items:T[];changed:boolean;refresh:boolean}{
 const type=String(event?.event_type||event?.type||"");
 const payload=event?.payload&&typeof event.payload==="object"?event.payload:{};
 if(type==="CASE_CREATED")return {items,changed:false,refresh:true};
 const caseId=Number(payload.case_id||event?.entity_id||0);
 if(!Number.isSafeInteger(caseId)||caseId<=0)return {items,changed:false,refresh:false};
 const index=items.findIndex(item=>item.id===caseId);
 if(index<0)return {items,changed:false,refresh:false};
 const current=items[index];
 let next:T|null=null;
 if(type==="MESSAGE_CREATED"){
  const messageId=Number(payload.message_id),createdAt=payload.created_at;
  if(!Number.isSafeInteger(messageId)||messageId<=0||typeof createdAt!=="string"||!createdAt||
     typeof payload.is_outgoing!=="boolean"||typeof payload.preview!=="string")
   return {items,changed:false,refresh:true};
  if(messageId<=Number(current.last_message_id||0))return {items,changed:false,refresh:false};
  next={...current,
   last_message_id:messageId,
   last_message:payload.preview.slice(0,90),
   last_message_at:createdAt,
   status:typeof payload.case_status==="string"?payload.case_status:current.status,
   unread_count:Math.max(0,Number(current.unread_count)||0)+(payload.is_outgoing?0:1),
  } as T;
 }else if(type==="CASE_READ"){
  if(Number(payload.user_id)!==userId)return {items,changed:false,refresh:false};
  if(Number(current.unread_count||0)===0)return {items,changed:false,refresh:false};
  next={...current,unread_count:0} as T;
 }else if(type==="CASE_STATUS_UPDATED"){
  if(typeof payload.status!=="string"||!payload.status)return {items,changed:false,refresh:true};
  if(current.status===payload.status)return {items,changed:false,refresh:false};
  next={...current,status:payload.status} as T;
 }else{
  return {items,changed:false,refresh:false};
 }
 const updated=items.slice();updated[index]=next;
 return {items:updated,changed:true,refresh:false};
}
export function applyConsultationChatEvent<T extends Record<string,any>>(
 current:T,event:ConsultationRealtimeEvent,caseId:number,userId:number
):T{
 const type=String(event?.event_type||event?.type||"");
 const payload=event?.payload&&typeof event.payload==="object"?event.payload:{};
 if(Number(payload.case_id||event?.entity_id||0)!==caseId)return current;
 if(type==="CASE_STATUS_UPDATED"&&typeof payload.status==="string"){
  return {...current,...payload};
 }
 if(type==="CASE_READ"&&Number(payload.user_id)!==userId&&typeof payload.at==="string"){
  return {...current,other_read_at:payload.at};
 }
 return current;
}
export function mergeConsultationMessages<T extends {id:number}>(existing:T[],incoming:T[]):T[]{
 const byId=new Map<number,T>();
 for(const item of existing)if(item&&Number.isSafeInteger(item.id)&&item.id>0)byId.set(item.id,item);
 for(const item of incoming)if(item&&Number.isSafeInteger(item.id)&&item.id>0)byId.set(item.id,item);
 return Array.from(byId.values()).sort((a,b)=>a.id-b.id);
}

const CONSULTATION_STATUS_LABELS:Record<string,string>={
 REQUESTED:"Yeni talep",
 PROPOSED:"Onay bekleniyor",
 WAITING_START:"Başlangıç bekleniyor",
 ACTIVE:"Aktif",
 EXPERT_COMPLETED:"Onay bekleniyor",
 COMPLETED:"Tamamlandı",
 DISPUTE:"Sorun bildirildi",
 REJECTED:"Reddedildi",
 PROPOSAL_REJECTED:"Süre onaylanmadı",
 PROPOSAL_EXPIRED:"Süresi doldu",
 EXPERT_TIMEOUT:"Süresi doldu",
};
export function consultationStatusLabel(status?:string|null):string{
 const key=String(status||"").toUpperCase();
 return CONSULTATION_STATUS_LABELS[key]||(status?String(status):"Yükleniyor");
}
export function consultationMessagePreview(message?:{message_type?:string;content?:string|null}|null):string{
 if(!message)return "Mesaj";
 switch(String(message.message_type||"").toUpperCase()){
  case "IMAGE":return "Görsel";
  case "VOICE":return "Sesli mesaj";
  case "FILE":return "Dosya · "+String(message.content||"Belge");
  case "ANNOTATION":return "İşaretlenmiş görüntü";
  default:return String(message.content||"Mesaj").replace(/\\s+/g," ").trim().slice(0,90)||"Mesaj";
 }
}
