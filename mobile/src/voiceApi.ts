import {reportSessionExpiry} from './sessionExpiry';
const BASE="https://dentalai.tr/api/mobile/v1";
async function send<T>(token:string,path:string,payload:unknown):Promise<T>{
 const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),150000);
 try{const response=await fetch(BASE+path,{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify(payload),signal:controller.signal});
 if(response.status===401)reportSessionExpiry(token);
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
export type VoiceField={value:string;quote?:string;edited?:boolean};
export type VoiceExtraction={ok:boolean;revision:string;review:{fields?:Record<string,VoiceField>;teeth?:unknown[];insights?:Record<string,unknown>[];communication?:{quote:string;observation:string;suggestion:string}[];decision_barriers?:Record<string,unknown>[];follow_up_questions?:Record<string,unknown>[];uncertain?:string;literature_topics?:unknown[];source_requests?:unknown[];appointment?:{quote?:string;acceptance_quote?:string}}};
export async function extractVoice(token:string,patientId:number,transcript:string):Promise<VoiceExtraction>{
 const result=await send<VoiceExtraction>(token,`/patients/${patientId}/voice-exam/text`,{transcript,consent:true});
 if(!result.review||typeof result.review!=="object"||Array.isArray(result.review))throw Error("Klinik çıkarım yanıtında muayene bilgileri bulunamadı. Metninizi koruyup tekrar deneyin.");
 return result;
}
export async function finalizeVoice(token:string,patientId:number,payload:{context:Record<string,unknown>;insights:Record<string,unknown>[];uncertain:string;conversation_text:string}):Promise<Record<string,unknown>>{
 const result=await send<Record<string,unknown>>(token,`/patients/${patientId}/voice-exam/finalize`,{...payload,consent:true});
 if(!result.final||typeof result.final!=="object"||Array.isArray(result.final))throw Error("Klinik son değerlendirme yanıtı eksik. Metninizi koruyup tekrar deneyin.");
 return result;
}

const AUDIO_MIMES=new Set(["audio/webm","audio/ogg","audio/mp4","audio/mpeg","audio/wav"]);
const MAX_AUDIO_BYTES=8*1024*1024;
export async function transcribeVoiceAudio(token:string,patientId:number,audio:Blob,mime:string):Promise<{ok:true;revision:string;transcript:string}>{
 const contentType=mime.split(";")[0].trim().toLowerCase();
 if(!AUDIO_MIMES.has(contentType))throw Error("Ses biçimi desteklenmiyor. WebM, OGG, MP4, MP3 veya WAV kaydı kullanın.");
 if(!Number.isSafeInteger(patientId)||patientId<=0)throw Error("Ses kaydı için geçerli bir hasta seçin.");
 if(!audio||!Number.isFinite(audio.size)||audio.size<100||audio.size>MAX_AUDIO_BYTES)throw Error("Ses kaydı 100 bayttan büyük ve en fazla 8 MB olmalıdır.");
 const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),150000);
 try{
  const response=await fetch(BASE+`/patients/${patientId}/voice-exam/audio`,{method:"POST",headers:{"Content-Type":contentType,"X-Voice-Consent":"yes",Authorization:"Bearer "+token},body:audio,signal:controller.signal});
  if(response.status===401)reportSessionExpiry(token);
  if(response.status===429||response.status>=500)throw Error("Ses yazıya çevrilemedi; sunucu meşgul. Yerel kaydı silmeden tekrar deneyin.");
  const raw=await response.text();let body:Record<string,unknown>;
  try{body=raw?JSON.parse(raw):{}}catch{throw Error("Ses aktarımından geçersiz yanıt alındı. Yerel kaydı koruyun.");}
  if(!response.ok||body.ok!==true){
   const detail=typeof body.detail==="string"?body.detail:"Ses aktarımı tamamlanamadı. Yerel kaydı koruyun.";
   throw Error(detail);
  }
  if(typeof body.transcript!=="string"||!body.transcript.trim()||typeof body.revision!=="string")throw Error("Ses yazıya çevirme yanıtı eksik. Yerel kaydı koruyun.");
  return {ok:true,revision:body.revision,transcript:body.transcript};
 }catch(error){if(error instanceof Error&&error.name==="AbortError")throw Error("Ses aktarımı zaman aşımına uğradı. Yerel kaydı koruyup tekrar deneyin.");throw error;
 }finally{clearTimeout(timeout)}
}
