export type VoiceSegment={id:string;uri:string;ready:boolean};
export type VoiceDraft={version:1;userId:number;patientId:number;transcript:string;segments:VoiceSegment[];updatedAt:number;ended:boolean;audioStarted?:boolean};
export const VOICE_TEXT_LIMIT=18000;
export const voiceDraftKey=(userId:number,patientId:number)=>`dai.voice.${userId}.${patientId}`;
export function newVoiceDraft(userId:number,patientId:number,now=Date.now()):VoiceDraft{if(!Number.isSafeInteger(userId)||userId<=0||!Number.isSafeInteger(patientId)||patientId<=0)throw Error('Muayene için geçerli hesap ve hasta seçin.');return{version:1,userId,patientId,transcript:'',segments:[],updatedAt:now,ended:false,audioStarted:false};}
export function parseVoiceDraft(raw:string|null,userId:number,patientId:number,now=Date.now()):VoiceDraft|null{
 if(!raw)return null;let p:VoiceDraft;try{p=JSON.parse(raw)}catch{throw Error('Muayene taslağı okunamadı.')}
 if(!p||p.version!==1||p.userId!==userId||p.patientId!==patientId||typeof p.transcript!=='string'||p.transcript.length>72000||!Array.isArray(p.segments)||p.segments.length>8||new Set(p.segments.map(s=>s.id)).size!==p.segments.length||p.segments.some(s=>!s||typeof s.id!=='string'||typeof s.uri!=='string'||!s.uri.startsWith('file://')||typeof s.ready!=='boolean')||!Number.isFinite(p.updatedAt)||typeof p.ended!=='boolean'||p.audioStarted!==undefined&&typeof p.audioStarted!=='boolean')throw Error('Muayene taslağının hesabı, hastası veya içeriği doğrulanamadı.');
 return now-p.updatedAt>24*60*60*1000?null:p;
}
export function appendVoiceSegment(draft:VoiceDraft,id:string,transcript:string):VoiceDraft{
 if(!draft.segments.some(s=>s.id===id))return draft;
 if(!transcript.trim())throw Error('Ses kaydından konuşma metni alınamadı.');
 const next=[draft.transcript.trim(),transcript.trim()].filter(Boolean).join('\n');
 if(next.length>VOICE_TEXT_LIMIT)throw Error('Muayene metni 18.000 karakter sınırına ulaştı. Ses dosyası korunuyor; metni kontrol edip muayeneyi bitirin.');
 return {...draft,transcript:next,segments:draft.segments.filter(s=>s.id!==id),updatedAt:Date.now()};
}
