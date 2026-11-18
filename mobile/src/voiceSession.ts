export type VoiceSegment={id:string;uri:string;ready:boolean;transcribed?:boolean};
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
export function isSafeVoiceSegmentUri(uri:unknown):uri is string{
 if(typeof uri!=='string'||!uri.startsWith('file:///')||/[?#%\u0000-\u001f]/.test(uri)||uri.includes('\\'))return false;
 const path=uri.slice('file://'.length);
 if(!path.startsWith('/'))return false;
 const segments=path.split('/').slice(1);
 if(segments.length<2||segments.some(segment=>!segment||segment==='.'||segment==='..'))return false;
 return /^[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.m4a$/i.test(segments[segments.length-1]);
}

export function parseVoiceDraft(raw:string|null,userId:number,patientId:number,now=Date.now()):VoiceDraft|null{
 if(!raw)return null;let p:VoiceDraft;try{p=JSON.parse(raw)}catch{throw Error('Muayene taslağı okunamadı.')}
 if(!p||p.version!==1||p.userId!==userId||p.patientId!==patientId||typeof p.transcript!=='string'||p.transcript.length>VOICE_TEXT_LIMIT||voiceUtf8Bytes(p.transcript)>VOICE_TEXT_BYTE_LIMIT||!Array.isArray(p.segments)||p.segments.length>8||p.segments.some(s=>!s||typeof s.id!=='string'||!isSafeVoiceSegmentUri(s.uri)||typeof s.ready!=='boolean'||s.transcribed!==undefined&&typeof s.transcribed!=='boolean'||s.transcribed===true&&s.ready)||new Set(p.segments.map(s=>s.id)).size!==p.segments.length||!Number.isFinite(p.updatedAt)||typeof p.ended!=='boolean'||p.audioStarted!==undefined&&typeof p.audioStarted!=='boolean'||p.elapsedMs!==undefined&&(!Number.isFinite(p.elapsedMs)||p.elapsedMs<0||p.elapsedMs>24*60*60*1000))throw Error('Muayene taslağının hesabı, hastası veya içeriği doğrulanamadı.');
 return now-p.updatedAt>24*60*60*1000?null:{...p,elapsedMs:p.elapsedMs??0};
}
export function appendVoiceSegment(draft:VoiceDraft,id:string,transcript:string):VoiceDraft{
 if(!draft.segments.some(s=>s.id===id))return draft;
 if(typeof transcript!=='string'||!transcript.trim())throw Error('Ses kaydından konuşma metni alınamadı.');
 const next=[draft.transcript.trim(),transcript.trim()].filter(Boolean).join('\n');
 if(next.length>VOICE_TEXT_LIMIT||voiceUtf8Bytes(next)>VOICE_TEXT_BYTE_LIMIT)throw Error('Muayene metni 72.000 karakter / 216 KB sınırına ulaştı. Ses dosyası korunuyor; metni kontrol edip muayeneyi bitirin.');
 return {...draft,transcript:next,segments:draft.segments.filter(s=>s.id!==id),updatedAt:Date.now()};
}


/**
 * Persist the transcript before deleting its source audio. A transcribed segment
 * remains as a cleanup receipt until the app confirms that the private cache file
 * is gone. Replaying this helper for the same segment never appends text twice.
 */
export function markVoiceSegmentTranscribed(draft:VoiceDraft,id:string,transcript:string):VoiceDraft{
 const segment=draft.segments.find(item=>item.id===id);
 if(!segment||segment.transcribed)return draft;
 if(!segment.ready)throw Error('Ses bölümü tamamlanmadan yazıya çevrilemez.');
 if(typeof transcript!=='string'||!transcript.trim())throw Error('Ses kaydından konuşma metni alınamadı.');
 const next=[draft.transcript.trim(),transcript.trim()].filter(Boolean).join('\n');
 if(next.length>VOICE_TEXT_LIMIT||voiceUtf8Bytes(next)>VOICE_TEXT_BYTE_LIMIT)
  throw Error('Muayene metni 72.000 karakter / 216 KB sınırına ulaştı. Ses dosyası korunuyor; metni kontrol edip muayeneyi bitirin.');
 return {
  ...draft,
  transcript:next,
  segments:draft.segments.map(item=>item.id===id?{...item,ready:false,transcribed:true}:item),
  updatedAt:Date.now()
 };
}

/** Remove only a segment whose transcript has already been persisted. */
export function removeVoiceSegment(draft:VoiceDraft,id:string):VoiceDraft{
 const segment=draft.segments.find(item=>item.id===id);
 if(!segment)return draft;
 if(!segment.transcribed)throw Error('Yazıya çevrilmemiş ses bölümü taslaktan kaldırılamaz.');
 return {...draft,segments:draft.segments.filter(item=>item.id!==id),updatedAt:Date.now()};
}


export type VoiceSegmentFileInfo={exists:boolean;size?:number};

/** Mark a recovered private-cache segment uploadable only after file validation. */
export function markVoiceSegmentReady(draft:VoiceDraft,id:string):VoiceDraft{
 const segment=draft.segments.find(item=>item.id===id);
 if(!segment||segment.ready||segment.transcribed)return draft;
 return {...draft,segments:draft.segments.map(item=>item.id===id?{...item,ready:true}:item),updatedAt:Date.now()};
}

/** Explicitly discard only an interrupted, not-yet-transcribed segment. */
export function discardInterruptedVoiceSegment(draft:VoiceDraft,id:string):VoiceDraft{
 const segment=draft.segments.find(item=>item.id===id);
 if(!segment)return draft;
 if(segment.transcribed)throw Error('Yazıya çevrilmiş ses bölümü temizleme fişi olmadan kaldırılamaz.');
 if(segment.ready)throw Error('Tamamlanmış ses bölümü bu işlemle kaldırılamaz.');
 return {...draft,segments:draft.segments.filter(item=>item.id!==id),updatedAt:Date.now()};
}

/** Recover only a direct private-cache file inside the server's byte contract. */
export function recoverInterruptedVoiceSegment(draft:VoiceDraft,id:string,info:VoiceSegmentFileInfo):VoiceDraft{
 const segment=draft.segments.find(item=>item.id===id);
 if(!segment||segment.ready||segment.transcribed)return draft;
 if(info.exists===false)return discardInterruptedVoiceSegment(draft,id);
 if(info.exists!==true||typeof info.size!=='number'||!Number.isFinite(info.size)||info.size<100||info.size>8*1024*1024)return draft;
 return markVoiceSegmentReady(draft,id);
}
