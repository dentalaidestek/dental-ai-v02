import * as FileSystem from 'expo-file-system/legacy';
import {createAudioPlayer} from 'expo-audio';
import {isVoiceAudioExtensionForMime,normalizeVoiceAudioMime} from './voiceAudioImport';
import {ApiError} from './api';
import {revalidateSession} from './sessionExpiry';

export class VoiceAsrError extends Error {
 constructor(readonly code:string,readonly status:number,message:string){
  super(message);this.name='VoiceAsrError';
 }
}

const REQUEST_KEY=/^[A-Za-z0-9_-]{16,96}$/;
const BASE='https://dentalai.tr/api/mobile/v1';
const VOICE_FILE=/^[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.(m4a|mp3|wav|webm|ogg)$/i;

export function isPrivateVoiceRecordingUri(
 uri:unknown,cacheDirectory:string|null|undefined=FileSystem.cacheDirectory,mime?:unknown
):uri is string{
 if(typeof uri!=='string'||typeof cacheDirectory!=='string'||
    !cacheDirectory.startsWith('file:///')||!cacheDirectory.endsWith('/'))return false;
 if(!uri.startsWith(cacheDirectory))return false;
 const filename=uri.slice(cacheDirectory.length),match=VOICE_FILE.exec(filename);
 if(!match)return false;
 if(mime===undefined)return match[1].toLowerCase()==='m4a';
 return isVoiceAudioExtensionForMime(match[1],mime);
}

const PRIVATE_CACHE_CHILD=/^[A-Za-z0-9][A-Za-z0-9._-]{0,180}$/;

/**
 * A recorder can create a cache file before its filename/MIME contract is
 * validated. Cleanup may accept any single direct child of the app-private
 * cache, but must never follow a nested path or leave that cache directory.
 */
export function isPrivateVoiceCacheChildUri(
 uri:unknown,cacheDirectory:string|null|undefined=FileSystem.cacheDirectory
):uri is string{
 if(typeof uri!=='string'||typeof cacheDirectory!=='string'||
    !cacheDirectory.startsWith('file:///')||!cacheDirectory.endsWith('/')||
    !uri.startsWith(cacheDirectory))return false;
 const filename=uri.slice(cacheDirectory.length);
 return PRIVATE_CACHE_CHILD.test(filename)&&filename!=='.'&&filename!=='..';
}

/** Remove an untrusted recorder artifact only when it is a direct private-cache child. */
export async function removePrivateVoiceCacheChildFile(
 uri:unknown,cacheDirectory:string|null|undefined=FileSystem.cacheDirectory
):Promise<boolean>{
 if(!isPrivateVoiceCacheChildUri(uri,cacheDirectory))return false;
 try{
  const before=await FileSystem.getInfoAsync(uri);
  if(!before.exists)return true;
  await FileSystem.deleteAsync(uri,{idempotent:true});
  const after=await FileSystem.getInfoAsync(uri);
  return after.exists!==true;
 }catch{return false;}
}

export async function readPrivateVoiceAudioDuration(uri:string,mime:string,timeoutMs=8000):Promise<number>{
 const contentType=normalizeVoiceAudioMime(mime);
 if(!contentType||!isPrivateVoiceRecordingUri(uri,FileSystem.cacheDirectory,contentType))
  throw Error('Ses dosyası uygulamanın özel önbelleğinde doğrulanamadı.');
 const player=createAudioPlayer({uri},{updateInterval:250});
 return await new Promise<number>((resolve,reject)=>{
  let settled=false,timer:ReturnType<typeof setTimeout>|null=null;
  let subscription:{remove:()=>void}|null=null;
  const finish=(error?:Error,duration?:number)=>{
   if(settled)return;settled=true;
   if(timer)clearTimeout(timer);
   try{subscription?.remove()}catch{}
   try{player.remove()}catch{}
   if(error)reject(error);else resolve(duration as number);
  };
  const inspect=(status:any)=>{
   const current=status||player.currentStatus;
   if(typeof current?.error==='string'&&current.error){
    finish(Error('Ses dosyası okunamadı. MP3, WAV, WebM, OGG veya M4A biçimini kontrol edin.'));return;
   }
   if(current?.isLoaded!==true&&player.isLoaded!==true)return;
   const duration=typeof current?.duration==='number'&&current.duration>0?current.duration:player.duration;
   if(!Number.isFinite(duration)||duration<=0){
    finish(Error('Ses dosyasının süresi okunamadı. Daha kısa bir MP3 veya WAV dosyası seçin.'));return;
   }
   if(duration>90.5){
    finish(Error('Ses dosyası en fazla 90 saniye olmalı. Daha kısa bir bölüm seçin.'));return;
   }
   finish(undefined,duration);
  };
  timer=setTimeout(()=>finish(Error('Ses süresi okunamadı. Daha kısa bir ses dosyası seçin.')),timeoutMs);
  try{
   subscription=player.addListener('playbackStatusUpdate',inspect);
   inspect(player.currentStatus);
  }catch{
   finish(Error('Ses dosyasının süresi okunamadı.'));
  }
 });
}

export async function transcribeNativeRecording(
 token:string,patientId:number,uri:string,requestKey:string,signal?:AbortSignal,mime:string='audio/mp4'
):Promise<{transcript:string;revision:string;replayed:boolean}>{
 const contentType=normalizeVoiceAudioMime(mime);
 if(!Number.isSafeInteger(patientId)||patientId<=0||!contentType||!isPrivateVoiceRecordingUri(uri,FileSystem.cacheDirectory,contentType))
  throw Error('Ses kaydı uygulamanın özel önbelleğinde doğrulanamadı veya hasta kimliği geçersiz.');
 if(typeof requestKey!=='string'||!REQUEST_KEY.test(requestKey))
  throw Error('Ses bölümü işlem anahtarı geçersiz; yerel kayıt korundu.');
 const info=await FileSystem.getInfoAsync(uri),size=info.exists===true&&info.isDirectory!==true?info.size:0;
 if(!info.exists||typeof size!=='number'||!Number.isFinite(size)||size<100||size>8*1024*1024)
  throw Error('Ses kaydı okunamadı veya 8 MB sınırını aşıyor. Yerel kaydı kontrol edin.');
 const task=FileSystem.createUploadTask(
  BASE+'/patients/'+patientId+'/voice-exam/audio',
  uri,
  {
   httpMethod:'POST',
   uploadType:FileSystem.FileSystemUploadType.BINARY_CONTENT,
   headers:{
    Authorization:'Bearer '+token,
    Cookie:'',
    'Content-Type':contentType,
    'X-Voice-Consent':'yes',
    'X-Voice-Request-Key':requestKey
   }
  }
 );
 let timedOut=false,rejectAbort:(error:Error)=>void=()=>{};
 const cancelled=new Promise<never>((_,reject)=>{rejectAbort=reject});
 const cancel=()=>{
  void task.cancelAsync().catch(()=>{});
  rejectAbort(new ApiError(408,'Ses aktarımı durduruldu; yerel kayıt korundu.'));
 };
 const timer=setTimeout(()=>{timedOut=true;cancel()},150000);
 if(signal?.aborted){clearTimeout(timer);throw Error('Ses aktarımı durduruldu; yerel kayıt korundu.');}
 signal?.addEventListener('abort',cancel,{once:true});
 try{
  const response=await Promise.race([task.uploadAsync(),cancelled]);
  if(!response||timedOut||signal?.aborted)
   throw new ApiError(408,'Ses aktarımı doğrulanamadı; yerel kayıt korundu.');
  if(response.status===401)await revalidateSession(token);
  let body:any;
  try{body=JSON.parse(response.body)}catch{
   throw new ApiError(502,'Ses aktarımından geçersiz yanıt alındı; yerel kayıt korundu.');
  }
  if(response.status>=400||body?.ok!==true){
   const detail=typeof body?.detail==='string'
    ?body.detail:'Konuşma metni alınamadı; yerel kayıt korundu.';
   if(typeof body?.code==='string')throw new VoiceAsrError(body.code,response.status,detail);
   throw new ApiError(response.status>=400?response.status:502,detail);
  }
  if(typeof body.transcript!=='string'||!body.transcript.trim()||body.transcript.length>18000||
     typeof body.revision!=='string'||!/^[a-f0-9]{64}$/.test(body.revision))
   throw new ApiError(502,'Konuşma metni veya hasta sürümü yanıtı eksik; yerel kayıt korundu.');
  return {transcript:body.transcript,revision:body.revision,replayed:body.replayed===true};
 }finally{
  clearTimeout(timer);
  signal?.removeEventListener('abort',cancel);
 }
}
