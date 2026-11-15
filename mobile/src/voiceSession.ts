export type VoiceSegment={id:string;uri:string;ready:boolean};
export type VoiceDraft={version:1;userId:number;patientId:number;transcript:string;segments:VoiceSegment[];updatedAt:number;ended:boolean;audioStarted?:boolean;elapsedMs?:number};
export const VOICE_TEXT_LIMIT=72000;
export const VOICE_TEXT_BYTE_LIMIT=216000;
export const VOICE_CHUNK_CHAR_LIMIT=12000;
export const VOICE_CHUNK_BYTE_LIMIT=36000;

export function voiceUtf8Bytes(value:string):number{
 let bytes=0;
 for(let i=0;i<value.length;i++){
  const code=value.charCodeAt(i);
  if(code<=0x7f)bytes++;
  else if(code<=0x7ff)bytes+=2;
  else if(code>=0xd800&&code<=0xdbff&&i+1<value.length){
   const next=value.charCodeAt(i+1);
   if(next>=0xdc00&&next<=0xdfff){bytes+=4;i++}else bytes+=3;
  }else bytes+=3;
 }
 return bytes;
}

// Mirrors the web FinishDraft boundaries: bounded requests, Unicode-safe and
// preferentially split at sentence/word boundaries without dropping a character.
export function splitVoiceTranscript(text:string):string[]{
 if(typeof text!=='string')throw Error('Muayene metni doğrulanamadı.');
 if(text.length>VOICE_TEXT_LIMIT||voiceUtf8Bytes(text)>VOICE_TEXT_BYTE_LIMIT)
  throw Error('Görüşme metni 72.000 karakter / 216 KB sınırını aşıyor. Taslak korunuyor.');
 const chunks:string[]=[];let offset=0;
 while(offset<text.length){
  let end=Math.min(offset+VOICE_CHUNK_CHAR_LIMIT,text.length);
  if(end<text.length&&text.charCodeAt(end-1)>=0xd800&&text.charCodeAt(end-1)<=0xdbff)end--;
  while(end>offset&&voiceUtf8Bytes(text.slice(offset,end))>VOICE_CHUNK_BYTE_LIMIT)end--;
  if(end<=offset)throw Error('Muayene metni güvenli bölüm sınırına ayrılamadı.');
  if(end<text.length){
   const candidate=text.slice(offset,end);
   const boundary=Math.max(candidate.lastIndexOf('\n'),candidate.lastIndexOf('. '),candidate.lastIndexOf(' '));
   if(boundary>candidate.length/2)end=offset+boundary+1;
  }
  chunks.push(text.slice(offset,end));offset=end;
 }
 return chunks;
}

export type VoiceExtractionCheckpoint={
 version:1;userId:number;patientId:number;transcriptHash:string;
 cursor:number;revision:string;review:Record<string,unknown>;updatedAt:number;
};
export function parseVoiceExtractionCheckpoint(raw:string|null,userId:number,patientId:number,transcriptHash:string,chunkCount:number,now=Date.now()):VoiceExtractionCheckpoint|null{
 if(!raw)return null;
 try{
  const p=JSON.parse(raw);
  if(!p||p.version!==1||p.userId!==userId||p.patientId!==patientId||
   p.transcriptHash!==transcriptHash||!/^[a-f0-9]{64}$/.test(p.transcriptHash)||
   !Number.isInteger(p.cursor)||p.cursor<1||p.cursor>chunkCount||
   typeof p.revision!=='string'||!/^[a-f0-9]{64}$/.test(p.revision)||
   !p.review||typeof p.review!=='object'||Array.isArray(p.review)||
   !Number.isFinite(p.updatedAt)||now-p.updatedAt>86400000||p.updatedAt>now+60000)return null;
  return p as VoiceExtractionCheckpoint;
 }catch{return null}
}

export const voiceDraftKey=(userId:number,patientId:number)=>`dai.voice.${userId}.${patientId}`;
export function newVoiceDraft(userId:number,patientId:number,now=Date.now()):VoiceDraft{if(!Number.isSafeInteger(userId)||userId<=0||!Number.isSafeInteger(patientId)||patientId<=0)throw Error('Muayene için geçerli hesap ve hasta seçin.');return{version:1,userId,patientId,transcript:'',segments:[],updatedAt:now,ended:false,audioStarted:false,elapsedMs:0};}

export function addVoiceElapsed(draft:VoiceDraft,startedAt:number,endedAt:number):VoiceDraft{
 if(!Number.isFinite(startedAt)||!Number.isFinite(endedAt)||startedAt<0||endedAt<startedAt)throw Error('Muayene süresi doğrulanamadı.');
 const elapsedMs=(draft.elapsedMs??0)+(endedAt-startedAt);
 if(!Number.isFinite(elapsedMs)||elapsedMs>24*60*60*1000)throw Error('Muayene kayıt süresi 24 saati aşamaz.');
 return {...draft,elapsedMs,updatedAt:endedAt};
}

export function formatVoiceElapsed(milliseconds:number):string{
 const total=Math.floor((Number.isFinite(milliseconds)?Math.max(0,milliseconds):0)/1000);
 return String(Math.floor(total/60)).padStart(2,'0')+':'+String(total%60).padStart(2,'0');
}
export function parseVoiceDraft(raw:string|null,userId:number,patientId:number,now=Date.now()):VoiceDraft|null{
 if(!raw)return null;let p:VoiceDraft;try{p=JSON.parse(raw)}catch{throw Error('Muayene taslağı okunamadı.')}
 if(!p||p.version!==1||p.userId!==userId||p.patientId!==patientId||typeof p.transcript!=='string'||p.transcript.length>VOICE_TEXT_LIMIT||voiceUtf8Bytes(p.transcript)>VOICE_TEXT_BYTE_LIMIT||!Array.isArray(p.segments)||p.segments.length>8||new Set(p.segments.map(s=>s.id)).size!==p.segments.length||p.segments.some(s=>!s||typeof s.id!=='string'||typeof s.uri!=='string'||!s.uri.startsWith('file://')||typeof s.ready!=='boolean')||!Number.isFinite(p.updatedAt)||typeof p.ended!=='boolean'||p.audioStarted!==undefined&&typeof p.audioStarted!=='boolean'||p.elapsedMs!==undefined&&(!Number.isFinite(p.elapsedMs)||p.elapsedMs<0||p.elapsedMs>24*60*60*1000))throw Error('Muayene taslağının hesabı, hastası veya içeriği doğrulanamadı.');
 return now-p.updatedAt>24*60*60*1000?null:{...p,elapsedMs:p.elapsedMs??0};
}
export function appendVoiceSegment(draft:VoiceDraft,id:string,transcript:string):VoiceDraft{
 if(!draft.segments.some(s=>s.id===id))return draft;
 if(typeof transcript!=='string'||!transcript.trim())throw Error('Ses kaydından konuşma metni alınamadı.');
 const next=[draft.transcript.trim(),transcript.trim()].filter(Boolean).join('\n');
 if(next.length>VOICE_TEXT_LIMIT||voiceUtf8Bytes(next)>VOICE_TEXT_BYTE_LIMIT)throw Error('Muayene metni 72.000 karakter / 216 KB sınırına ulaştı. Ses dosyası korunuyor; metni kontrol edip muayeneyi bitirin.');
 return {...draft,transcript:next,segments:draft.segments.filter(s=>s.id!==id),updatedAt:Date.now()};
}
