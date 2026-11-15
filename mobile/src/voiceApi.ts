import {revalidateSession} from './sessionExpiry';
const BASE="https://dentalai.tr/api/mobile/v1";
async function send<T>(token:string,path:string,payload:unknown):Promise<T>{
 const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),150000);
 try{const response=await fetch(BASE+path,{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify(payload),signal:controller.signal});
 if(response.status===401)await revalidateSession(token);
 if(response.status===429)throw Error("Klinik değerlendirme hizmeti şu anda yoğun. Metniniz korunuyor; biraz sonra tekrar deneyin.");
 if(response.status>=500)throw Error("Klinik değerlendirme sunucusuna şu anda ulaşılamıyor. Metniniz korunuyor; daha sonra tekrar deneyin.");
 const raw=await response.text();
 let body:Record<string,unknown>;
 try {body=raw?JSON.parse(raw):{};} catch {throw Error("Sunucudan geçersiz klinik değerlendirme yanıtı alındı. Metniniz bu ekranda korunuyor.");}
 if(!body||typeof body!=="object"||Array.isArray(body))throw Error("Sunucudan geçersiz klinik değerlendirme yanıtı alındı.");
 if(!response.ok||body.ok===false){
  const detail=typeof body.detail==="string"?body.detail:typeof body.error==="string"?body.error:Array.isArray(body.detail)?"Gönderilen muayene bilgileri sunucu tarafından doğrulanamadı. Metninizi koruyup tekrar deneyin.":"Klinik değerlendirme başarısız.";
  throw Error(detail);
 }
 if(body.ok!==true)throw Error("Klinik değerlendirme yanıtı beklenen başarı durumunu içermiyor. Metninizi koruyup tekrar deneyin.");
 return body as T;
 }catch(error){if(error instanceof Error&&error.name==='AbortError')throw Error('Klinik değerlendirme zaman aşımına uğradı. Metniniz bu ekranda korunuyor; tekrar deneyebilirsiniz.');throw error;
 }finally{clearTimeout(timeout)}
}
export type AnonymousVoicePatient={id:number;anonymous_id:string;first_name:string|null;last_name:string|null;phone?:string|null;birth_date?:string|null;age?:number|null;chief_complaint?:string|null;created_at?:string|null};
export async function createAnonymousVoicePatient(token:string,requestKey:string):Promise<{patient:AnonymousVoicePatient;already_created:boolean}>{
 if(typeof requestKey!=="string"||!/^[a-f0-9]{32}$/.test(requestKey))throw Error("Yeni hasta isteği doğrulanamadı. Güvenli anahtarı yeniden oluşturun.");
 const result=await send<{ok:true;patient:AnonymousVoicePatient;already_created:boolean}>(token,"/voice-exam/anonymous",{request_key:requestKey});
 const patient=result.patient;
 if(result.ok!==true||!patient||!Number.isSafeInteger(patient.id)||patient.id<=0||typeof patient.anonymous_id!=="string"||!/^SES-[A-F0-9]{16}$/.test(patient.anonymous_id)||typeof result.already_created!=="boolean"||(patient.first_name!==null&&typeof patient.first_name!=="string")||(patient.last_name!==null&&typeof patient.last_name!=="string"))
  throw Error("Yeni hasta kaydı sunucu tarafından doğrulanamadı. Aynı isteği güvenli biçimde tekrar deneyin.");
 return {patient,already_created:result.already_created};
}

export type VoiceField={value:string;quote?:string;edited?:boolean};
export type VoiceExtraction={ok:boolean;revision:string;review:{fields?:Record<string,VoiceField>;teeth?:unknown[];insights?:Record<string,unknown>[];communication?:{quote:string;observation:string;suggestion:string}[];decision_barriers?:Record<string,unknown>[];follow_up_questions?:Record<string,unknown>[];uncertain?:string;literature_topics?:unknown[];source_requests?:unknown[];appointment?:{quote?:string;acceptance_quote?:string}}};
export async function extractVoice(token:string,patientId:number,transcript:string):Promise<VoiceExtraction>{
 if(!Number.isSafeInteger(patientId)||patientId<=0)throw Error("Klinik değerlendirme için geçerli bir hasta seçin.");
 if(!transcript.trim()||transcript.length>18000)throw Error("Muayene metni boş olamaz ve 18.000 karakteri aşamaz. Metniniz korunuyor.");
 const result=await send<VoiceExtraction>(token,`/patients/${patientId}/voice-exam/text`,{transcript,consent:true});
 if(!result.review||typeof result.review!=="object"||Array.isArray(result.review))throw Error("Klinik çıkarım yanıtında muayene bilgileri bulunamadı. Metninizi koruyup tekrar deneyin.");
 const review=result.review;
 const allowedFields=new Set(["first_name","last_name","age","chief_complaint","medical_history","family_history","materials","dental_history","oral_habits","medications","allergies","clinical_findings","plan"]);
 const invalidFields=review.fields!==undefined&&(!review.fields||typeof review.fields!=="object"||Array.isArray(review.fields)||Object.entries(review.fields).some(([key,item])=>!allowedFields.has(key)||!item||typeof item!=="object"||Array.isArray(item)||typeof item.value!=="string"||item.value.length>3000||typeof item.quote!=="string"||item.quote.length>3000));
 const maxListSizes:Record<string,number>={teeth:52,communication:24,insights:24,decision_barriers:24,follow_up_questions:24,literature_topics:40,source_requests:6};
 const invalidArrays=Object.entries(maxListSizes).some(([key,limit])=>{const value=(review as Record<string,unknown>)[key];return value!==undefined&&(!Array.isArray(value)||value.length>limit)});
 const isObject=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==="object"&&!Array.isArray(value);
 const allowedToothStates=new Set(["CARIES","FILLING","CROWN","ROOT_CANAL","EXTRACTED","IMPLANT","OTHER"]);
 const invalidTeeth=Array.isArray(review.teeth)&&(review.teeth.length>52||review.teeth.some(tooth=>!isObject(tooth)||!/^([1-4][1-8]|[5-8][1-5])$/.test(String(tooth.tooth))||!allowedToothStates.has(String(tooth.status))||typeof tooth.quote!=="string"||tooth.quote.length>1500));
 const invalidCommunication=Array.isArray(review.communication)&&review.communication.some(item=>!isObject(item)||typeof item.quote!=="string"||typeof item.observation!=="string"||typeof item.suggestion!=="string");
 const invalidSources=(["literature_topics","source_requests"] as const).some(key=>Array.isArray(review[key])&&review[key]!.some(item=>!isObject(item)||typeof item.quote!=="string"||typeof item[key==="literature_topics"?"topic":"term"]!=="string"));
 const invalidListItems=(["decision_barriers","follow_up_questions"] as const).some(key=>Array.isArray(review[key])&&review[key]!.some(item=>!isObject(item)));
 const invalidAppointment=review.appointment!=null&&(!isObject(review.appointment)||Object.keys(review.appointment).some(key=>!["quote","acceptance_quote"].includes(key))||Object.values(review.appointment).some(value=>typeof value!=="string"||value.length>1500));
 if(invalidFields||invalidArrays||invalidTeeth||invalidCommunication||invalidSources||invalidListItems||invalidAppointment||(review.uncertain!==undefined&&typeof review.uncertain!=="string"))throw Error("Klinik çıkarım yanıtının alanları geçersiz. Metniniz korunuyor; tekrar deneyin.");
 return result;
}
export async function finalizeVoice(token:string,patientId:number,payload:{context:Record<string,unknown>;insights:Record<string,unknown>[];uncertain:string;conversation_text:string}):Promise<Record<string,unknown>>{
 if(!Number.isSafeInteger(patientId)||patientId<=0)throw Error("Son değerlendirme için geçerli bir hasta seçin.");
 if(!payload||!payload.context||typeof payload.context!=="object"||Array.isArray(payload.context)||!Array.isArray(payload.insights)||typeof payload.uncertain!=="string")throw Error("Klinik son değerlendirme bilgileri geçersiz. Metniniz korunuyor.");
 if(typeof payload.conversation_text!=="string"||payload.conversation_text.length>72000)throw Error("Görüşme metni 72.000 karakteri aşamaz. Metniniz korunuyor.");
 const fields=(payload.context as Record<string,unknown>).fields;
 const teeth=(payload.context as Record<string,unknown>).teeth;
 const topics=(payload.context as Record<string,unknown>).literature_topics;
 const requests=(payload.context as Record<string,unknown>).source_requests;
 const appointment=(payload.context as Record<string,unknown>).appointment;
 const isRecord=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==="object"&&!Array.isArray(value);
 const allowedFields=new Set(["first_name","last_name","age","chief_complaint","medical_history","family_history","materials","dental_history","oral_habits","medications","allergies","clinical_findings","plan"]);
 const validFields=fields===undefined||(isRecord(fields)&&Object.entries(fields).every(([name,item])=>allowedFields.has(name)&&isRecord(item)&&Object.keys(item).every(key=>["value","quote","edited"].includes(key))&&typeof item.value==="string"&&item.value.length<=3000&&(!("quote" in item)||typeof item.quote==="string"&&item.quote.length<=3000)&&(!("edited" in item)||typeof item.edited==="boolean")));
 const allowedToothStates=new Set(["CARIES","FILLING","CROWN","ROOT_CANAL","EXTRACTED","IMPLANT","OTHER"]);
 const validTeeth=teeth===undefined||(Array.isArray(teeth)&&teeth.length<=52&&teeth.every(item=>isRecord(item)&&/^([1-4][1-8]|[5-8][1-5])$/.test(String(item.tooth))&&allowedToothStates.has(String(item.status))&&typeof item.quote==="string"&&item.quote.length<=1500&&Object.keys(item).every(key=>["tooth","status","quote"].includes(key))));
 const validEvidence=(value:unknown,key:"topic"|"term",limit:number)=>value===undefined||(Array.isArray(value)&&value.length<=limit&&value.every(item=>isRecord(item)&&Object.keys(item).length===2&&Object.keys(item).every(field=>field===key||field==="quote")&&typeof item[key]==="string"&&typeof item.quote==="string"&&item.quote.length<=1000&&(key==="topic"||/^[A-Za-z][A-Za-z -]{2,79}$/.test(item[key] as string))));
 if(!validFields||!validTeeth||!validEvidence(topics,"topic",40)||!validEvidence(requests,"term",6)||(appointment!=null&&(!isRecord(appointment)||Object.keys(appointment).some(key=>!["quote","acceptance_quote"].includes(key))||Object.values(appointment).some(value=>typeof value!=="string"||value.length>1500)))||payload.insights.length>24||payload.uncertain.length>3000)throw Error("Klinik son değerlendirme bağlamı geçersiz veya sınır dışında. Taslağı kontrol edin; metniniz korunuyor.");
 const jsonContext=JSON.stringify(payload.context);
 let contextBytes=0;
 for(const char of jsonContext){
  const point=char.codePointAt(0)!;
  contextBytes+=point<=0x7f?1:point<=0x7ff?2:point<=0xffff?3:4;
 }

 if(contextBytes>32000)throw Error("Klinik bağlam 32 KB sınırını aşıyor. Taslağı kısaltın; görüşme metniniz korunuyor.");
 const allowedInsightKeys=new Set(["quote","observation","suggestion","category","question","explanation","response_type"]);
 const allowedResponseTypes=new Set(["CLINICIAN_RESPONSE","PATIENT_RESPONSE","UNATTRIBUTED_RESPONSE"]);
 if(payload.insights.some(item=>!isRecord(item)||Object.entries(item).some(([key,value])=>!allowedInsightKeys.has(key)||typeof value!=="string"||value.length>1000||(key==="response_type"&&!allowedResponseTypes.has(value)))||typeof item.quote!=="string"||!item.quote.trim()||typeof item.observation!=="string"||!item.observation.trim()))throw Error("Hekim iletişimi kanıtları eksik veya geçersiz. Taslağı kontrol edin; metniniz korunuyor.");
  const result=await send<Record<string,unknown>>(token,`/patients/${patientId}/voice-exam/finalize`,{...payload,consent:true});
 if(!result.final||typeof result.final!=="object"||Array.isArray(result.final))throw Error("Klinik son değerlendirme yanıtı eksik. Metninizi koruyup tekrar deneyin.");
 return result;
}

const AUDIO_MIMES=new Set(["audio/webm","audio/ogg","audio/mp4","audio/mpeg","audio/wav"]);
const MAX_AUDIO_BYTES=8*1024*1024;
export async function transcribeVoiceAudio(token:string,patientId:number,audio:Blob,mime:string):Promise<{ok:true;revision:string;transcript:string}>{
 if(typeof mime!=="string")throw Error("Ses biçimi desteklenmiyor. Geçerli bir ses dosyası seçin.");
 const contentType=mime.split(";")[0].trim().toLowerCase();
 if(!AUDIO_MIMES.has(contentType))throw Error("Ses biçimi desteklenmiyor. WebM, OGG, MP4, MP3 veya WAV kaydı kullanın.");
 if(!Number.isSafeInteger(patientId)||patientId<=0)throw Error("Ses kaydı için geçerli bir hasta seçin.");
 if(!audio||!Number.isFinite(audio.size)||audio.size<100||audio.size>MAX_AUDIO_BYTES)throw Error("Ses kaydı 100 bayttan büyük ve en fazla 8 MB olmalıdır.");
 const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),150000);
 try{
  const response=await fetch(BASE+`/patients/${patientId}/voice-exam/audio`,{method:"POST",headers:{"Content-Type":contentType,"X-Voice-Consent":"yes",Authorization:"Bearer "+token},body:audio,signal:controller.signal});
  if(response.status===401)await revalidateSession(token);
  if(response.status===429||response.status>=500)throw Error("Ses yazıya çevrilemedi; sunucu meşgul. Yerel kaydı silmeden tekrar deneyin.");
  const raw=await response.text();let body:Record<string,unknown>;
  try{body=raw?JSON.parse(raw):{}}catch{throw Error("Ses aktarımından geçersiz yanıt alındı. Yerel kaydı koruyun.");}
  if(!body||typeof body!=="object"||Array.isArray(body))throw Error("Ses aktarımından geçersiz yanıt alındı. Yerel kaydı koruyun.");
  if(!response.ok||body.ok!==true){
   const detail=typeof body.detail==="string"?body.detail:"Ses aktarımı tamamlanamadı. Yerel kaydı koruyun.";
   throw Error(detail);
  }
  if(typeof body.transcript!=="string"||!body.transcript.trim()||body.transcript.length>18000||typeof body.revision!=="string"||!body.revision.trim())throw Error("Ses yazıya çevirme yanıtı eksik veya sınır dışında. Yerel kaydı koruyun.");
  return {ok:true,revision:body.revision,transcript:body.transcript};
 }catch(error){if(error instanceof Error&&error.name==="AbortError")throw Error("Ses aktarımı zaman aşımına uğradı. Yerel kaydı koruyup tekrar deneyin.");throw error;
 }finally{clearTimeout(timeout)}
}

export type VoiceApply={request_key:string;revision:string;confirmed:boolean;fields:Record<string,string>;teeth:Array<{tooth:string;status:string;note:string}>;appointment?:{title:string;start_at:string;end_at:string}};
export function validateVoiceApply(value:VoiceApply):VoiceApply{
 const names=new Set(['first_name','last_name','age','chief_complaint','medical_history','family_history','materials','dental_history','oral_habits','medications','allergies','clinical_findings','plan']);
 if(!value||!value.confirmed||!/^[a-f0-9]{32}$/.test(value.request_key)||!/^[a-f0-9]{64}$/.test(value.revision)||!value.fields||typeof value.fields!=='object'||Array.isArray(value.fields)||Object.entries(value.fields).some(([name,text])=>!names.has(name)||typeof text!=='string'||text.length>3000)||!Array.isArray(value.teeth)||value.teeth.length>52||new Set(value.teeth.map(t=>t.tooth)).size!==value.teeth.length||value.teeth.some(t=>!/^([1-4][1-8]|[5-8][1-5])$/.test(t.tooth)||!['CARIES','FILLING','CROWN','ROOT_CANAL','EXTRACTED','IMPLANT','OTHER'].includes(t.status)||typeof t.note!=='string'||t.note.length>2000))throw Error('Onaylı muayene kaydı bilgileri geçersiz.');return value;
}
export async function applyVoiceReview(token:string,patientId:number,payload:VoiceApply){
 if(!Number.isSafeInteger(patientId)||patientId<=0)throw Error('Hasta kimliği geçersiz.');validateVoiceApply(payload);
 const {request}=await import('./api');const result=await request<{ok:boolean;analysis_id:number;already_saved?:boolean}>(`/patients/${patientId}/voice-exam/apply`,token,{method:'POST',body:JSON.stringify(payload)});
 if(result.ok!==true||!Number.isSafeInteger(result.analysis_id)||result.analysis_id<=0)throw Error('Muayene kayıt sonucu doğrulanamadı. Aynı işlem anahtarı korunuyor.');return result;
}
