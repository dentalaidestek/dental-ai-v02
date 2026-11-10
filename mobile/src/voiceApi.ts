const BASE="https://dentalai.tr/api/mobile/v1";
async function send<T>(token:string,path:string,payload:unknown):Promise<T>{
 const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),150000);
 try{const response=await fetch(BASE+path,{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify(payload),signal:controller.signal});
 const body=await response.json();if(!response.ok||body.ok===false)throw Error(typeof body.detail==="string"?body.detail:body.error||"Klinik değerlendirme başarısız.");return body as T;
 }finally{clearTimeout(timeout)}
}
export type VoiceField={value:string;quote?:string;edited?:boolean};
export type VoiceExtraction={ok:boolean;revision:string;review:{fields?:Record<string,VoiceField>;teeth?:unknown[];insights?:Record<string,unknown>[];uncertain?:unknown[];literature_topics?:unknown[];source_requests?:unknown[]}};
export const extractVoice=(token:string,patientId:number,transcript:string)=>send<VoiceExtraction>(token,`/patients/${patientId}/voice-exam/text`,{transcript,consent:true});
export const finalizeVoice=(token:string,patientId:number,payload:{context:Record<string,unknown>;insights:Record<string,unknown>[];conversation_text:string})=>send<Record<string,unknown>>(token,`/patients/${patientId}/voice-exam/finalize`,{...payload,consent:true});
