import React,{useEffect,useMemo,useRef,useState} from 'react';
import {ActivityIndicator,Alert,AppState,Pressable,StyleSheet,Text,View} from 'react-native';
import {useIsFocused,usePreventRemove} from '@react-navigation/native';
import {RecordingPresets,requestRecordingPermissionsAsync,setAudioModeAsync,useAudioRecorder,useAudioRecorderState} from 'expo-audio';
import * as FileSystem from 'expo-file-system/legacy';
import * as DocumentPicker from 'expo-document-picker';
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import {chunkedDraftStore} from './socialDraft';
import {addVoiceElapsed,discardInterruptedVoiceSegment,formatVoiceElapsed,markVoiceSegmentReady,markVoiceSegmentTranscribed,newVoiceDraft,canResumeVoiceDraft,parseVoiceDraft,recoverInterruptedVoiceSegment,removeVoiceSegment,VoiceDraft,voiceDraftKey} from './voiceSession';
import {isPrivateVoiceRecordingUri,readPrivateVoiceAudioDuration,transcribeNativeRecording,VoiceAsrError} from './nativeVoiceAudio';
import {resolveVoiceAudioAsset,validateVoiceAudioBytes,validateVoiceAudioDuration} from './voiceAudioImport';
import {voiceDeviceSignalLevel} from './voiceDeviceCheck';
import {isUnexpectedVoiceRecorderStop} from './voiceRecorderLifecycle';
import {isVoiceDraftScopeCurrent} from './voiceDraftScope';

const WAVE_BARS=[5,9,14,19,12,23,16,28,17,24,13,20,11,26,15,22,12,18,9,14,6];
export default function NativeVoiceRecorder({token,userId,patientId,consent,value,disabled=false,onTranscript,onFinished,onBusyChanged,onSessionState}:{token:string;userId:number;patientId:number;consent:boolean;value:string;disabled?:boolean;onTranscript:(text:string)=>void;onFinished:(text:string,sessionId:string)=>void;onBusyChanged?:(busy:boolean)=>void;onSessionState?:(state:{started:boolean;finished:boolean;sessionId:string})=>void}){
 const options={...RecordingPresets.HIGH_QUALITY,directory:'cache' as const,isMeteringEnabled:true,numberOfChannels:1,bitRate:64000,android:{...RecordingPresets.HIGH_QUALITY.android,maxFileSize:8*1024*1024}},recorder=useAudioRecorder(options),status=useAudioRecorderState(recorder,250);
 const store=useMemo(()=>chunkedDraftStore(SecureStore,Crypto.randomUUID,300),[]),key=voiceDraftKey(userId,patientId),draft=useRef<VoiceDraft>(newVoiceDraft(userId,patientId,Date.now(),Crypto.randomUUID())),mounted=useRef(true),wanted=useRef(false),active=useRef<string|null>(null),stopped=useRef(true),timer=useRef<ReturnType<typeof setTimeout>|null>(null),gate=useRef(false),cutting=useRef<Promise<void>|null>(null),draining=useRef<Promise<void>|null>(null),controller=useRef<AbortController|null>(null),lastInput=useRef(value),wasRecording=useRef(false);
 const scopeRef=useRef(key),scopeCleanup=useRef<Promise<void>>(Promise.resolve());scopeRef.current=key;
 const scopeIsCurrent=(expectedKey:string)=>isVoiceDraftScopeCurrent(expectedKey,scopeRef.current);
 const transcriptCallback=useRef(onTranscript),finishCallback=useRef(onFinished);transcriptCallback.current=onTranscript;finishCallback.current=onFinished;
 const consentRef=useRef(consent);consentRef.current=consent;
 const [view,setView]=useState(draft.current),[ready,setReady]=useState(false),[recording,setRecording]=useState(false),[elapsedMs,setElapsedMs]=useState(0),[level,setLevel]=useState(0),[working,setWorking]=useState(false),[transcribing,setTranscribing]=useState(false),[error,setError]=useState(''),[storageBlocked,setStorageBlocked]=useState(false),[indeterminateSegmentId,setIndeterminateSegmentId]=useState<string|null>(null);
 const chunkStartedAt=useRef<number|null>(null);
 const focused=useIsFocused(),focus=useRef(focused);focus.current=focused;
 const occupied=recording||working||transcribing;
 useEffect(()=>{if(!recording||chunkStartedAt.current===null)return;const interval=setInterval(()=>{if(mounted.current&&chunkStartedAt.current!==null)setElapsedMs((draft.current.elapsedMs||0)+Date.now()-chunkStartedAt.current)},1000);return()=>clearInterval(interval)},[recording]);
 useEffect(()=>{setLevel(recording?voiceDeviceSignalLevel(status.metering):0)},[recording,status.metering]);
 useEffect(()=>{onSessionState?.({started:view.audioStarted===true||view.ended,finished:view.ended&&view.segments.length===0,sessionId:view.sessionId||''})},[view,onSessionState]);
 useEffect(()=>{onBusyChanged?.(occupied||!ready||storageBlocked);return()=>onBusyChanged?.(false)},[occupied,ready,storageBlocked,onBusyChanged]);
 usePreventRemove(occupied,()=>Alert.alert('Muayene sürüyor','Önce muayeneyi duraklatın veya bitirin.'));
 // Consent withdrawal is immediate: stop capture and abort any pending ASR upload.
 // pause(true) preserves the private local segment and deliberately skips transcription.
 useEffect(()=>{
  if(consent)return;
  controller.current?.abort();
  if(wanted.current||(active.current!==null&&!stopped.current))void pause(true);
 },[consent]);
 async function persist(next:VoiceDraft,expectedKey=key){if(!scopeIsCurrent(expectedKey))return false;const saved={...next,updatedAt:Date.now()};await store.setItemAsync(expectedKey,JSON.stringify(saved));if(!scopeIsCurrent(expectedKey))return false;draft.current=saved;if(mounted.current)setView(saved);return true;}
 async function removeFile(uri:string,mime?:string){
  if(!isPrivateVoiceRecordingUri(uri,FileSystem.cacheDirectory,mime))throw Error('Ses dosyası uygulamanın özel önbelleğinde doğrulanamadı; dış konuma dokunulmadı.');
  await FileSystem.deleteAsync(uri,{idempotent:true});
  const remaining=await FileSystem.getInfoAsync(uri);
  if(remaining.exists)throw Error('Geçici ses dosyasının silindiği doğrulanamadı. Aynı ses yeniden gönderilmeyecek.');
 }
 async function discardUnstartedSegment(id:string,uri:string){
  if(!isPrivateVoiceRecordingUri(uri))throw Error('Yarım kalan ses bölümü özel önbellekte doğrulanamadı.');
  const info=await FileSystem.getInfoAsync(uri);
  if(info.exists)await removeFile(uri);
  await persist(discardInterruptedVoiceSegment(draft.current,id));
  if(active.current===id){active.current=null;chunkStartedAt.current=null;stopped.current=true;}
 }
 async function cleanupTranscribedSegments(expectedKey=key){
  const completed=draft.current.segments.filter(segment=>segment.transcribed===true);
  for(const segment of completed){
   if(!scopeIsCurrent(expectedKey))return;
   await removeFile(segment.uri,segment.mime);
   if(!scopeIsCurrent(expectedKey))return;
   await persist(removeVoiceSegment(draft.current,segment.id),expectedKey);
  }
  const hasUntrusted=draft.current.segments.some(segment=>!isPrivateVoiceRecordingUri(segment.uri,FileSystem.cacheDirectory,segment.mime));
  if(scopeIsCurrent(expectedKey)&&mounted.current&&!hasUntrusted&&!draft.current.segments.some(segment=>segment.transcribed))setStorageBlocked(false);
 }
 useEffect(()=>{
  const effectKey=key;let effectActive=true;
  const isActive=()=>effectActive&&isVoiceDraftScopeCurrent(effectKey,scopeRef.current);
  const previousCleanup=scopeCleanup.current;
  mounted.current=true;setReady(false);setStorageBlocked(false);setRecording(false);setTranscribing(false);setElapsedMs(0);setLevel(0);setIndeterminateSegmentId(null);setError('');
  setView(newVoiceDraft(userId,patientId,Date.now(),Crypto.randomUUID()));
  void(async()=>{
   try{
    await previousCleanup.catch(()=>{});
    if(!isActive())return;
    const raw=await store.getItemAsync(effectKey);
    if(!isActive())return;
    const saved=parseVoiceDraft(raw,userId,patientId,0);
    if(saved&&Date.now()-saved.updatedAt>86400000){
     for(const segment of saved.segments){
      if(!isActive())return;
      if(isPrivateVoiceRecordingUri(segment.uri,FileSystem.cacheDirectory,segment.mime))await removeFile(segment.uri,segment.mime);
      if(!isActive())return;
     }
     await store.deleteItemAsync(effectKey);
     if(!isActive())return;
     if(saved.segments.some(segment=>!isPrivateVoiceRecordingUri(segment.uri,FileSystem.cacheDirectory,segment.mime)))setError('Süresi dolmuş taslak temizlendi; doğrulanamayan dosyaya dokunulmadı.');
     const fresh=newVoiceDraft(userId,patientId,Date.now(),Crypto.randomUUID());
     draft.current=fresh;await persist(fresh,effectKey);
    }else if(saved){
     let restored=saved;if(!restored.sessionId)restored={...restored,sessionId:Crypto.randomUUID()};let untrustedAudio=false,interruptedUnverified=false;
     for(const segment of saved.segments){
      if(!isActive())return;
      if(segment.ready||segment.transcribed)continue;
      if(!isPrivateVoiceRecordingUri(segment.uri,FileSystem.cacheDirectory,segment.mime)){untrustedAudio=true;continue;}
      try{
       const info=await FileSystem.getInfoAsync(segment.uri);
       if(!isActive())return;
       const next=recoverInterruptedVoiceSegment(restored,segment.id,{exists:info.exists===true,size:info.size});
       if(next!==restored)restored=next;
       else if(info.exists)interruptedUnverified=true;
      }catch{if(!isActive())return;interruptedUnverified=true;}
     }
     if(!isActive())return;
     draft.current=restored;
     setView(restored);setElapsedMs(restored.elapsedMs||0);transcriptCallback.current(restored.transcript);
     if(restored!==saved)await persist(restored,effectKey);
     if(!isActive())return;
     if(restored.segments.some(segment=>segment.transcribed))await cleanupTranscribedSegments(effectKey);
     if(!isActive())return;
     if(restored.segments.some(segment=>!segment.transcribed))setError('Bekleyen ses kaydı bulundu. Yazıya çevirmeden önce yarım kalan bölümü kontrol edin.');
     if(interruptedUnverified)setError('Kesintiye uğrayan ses dosyası 100 bayt–8 MB aralığında doğrulanamadı. Bu bölümü kaldırabilir veya taslağı temizleyebilirsiniz.');
     if(untrustedAudio){setStorageBlocked(true);setError('Taslakta uygulama önbelleği dışındaki veya güvenli biçimde doğrulanamayan ses yolu var. Dosya yüklenmeyecek ya da silinmeyecek; taslağı temizleyebilirsiniz.');}
    }else{
     const fresh=newVoiceDraft(userId,patientId,Date.now(),Crypto.randomUUID());draft.current=fresh;await persist(fresh,effectKey);
    }
   }catch(error){if(isActive()){setStorageBlocked(true);setError(error instanceof Error?error.message:'Muayene taslağı alınamadı.');}}
   finally{if(isActive())setReady(true);}
  })();
  return()=>{
   effectActive=false;if(scopeIsCurrent(effectKey))mounted.current=false;
   wanted.current=false;if(timer.current)clearTimeout(timer.current);controller.current?.abort();
   const pendingDrain=draining.current,priorCleanup=scopeCleanup.current;
   const cleanupWork=(async()=>{
    if(pendingDrain)await pendingDrain.catch(()=>{});
    const id=active.current;if(!id)return;
    const startedAt=chunkStartedAt.current,base=draft.current;
    if(!stopped.current){await recorder.stop();stopped.current=true;}
    const segment=base.segments.find(item=>item.id===id);
    if(!segment){if(active.current===id){active.current=null;chunkStartedAt.current=null;}return;}
    let next=base;
    if(startedAt===null){
     if(!isPrivateVoiceRecordingUri(segment.uri,FileSystem.cacheDirectory,segment.mime))return;
     const info=await FileSystem.getInfoAsync(segment.uri);if(info.exists)await removeFile(segment.uri,segment.mime);
     next=discardInterruptedVoiceSegment(base,id);
    }else{
     const info=await FileSystem.getInfoAsync(segment.uri);
     next=addVoiceElapsed(base,startedAt,Date.now());
     if(!info.exists)next=discardInterruptedVoiceSegment(next,id);
     else if(typeof info.size==='number'&&info.size>=100&&info.size<=8*1024*1024)next=markVoiceSegmentReady(next,id);
    }
    const savedDraft={...next,updatedAt:Date.now()};
    await store.setItemAsync(effectKey,JSON.stringify(savedDraft));
    if(scopeIsCurrent(effectKey)){draft.current=savedDraft;if(mounted.current)setView(savedDraft);}
    if(active.current===id){active.current=null;chunkStartedAt.current=null;}
   })();
   scopeCleanup.current=Promise.all([priorCleanup,cleanupWork]).then(()=>undefined).catch(()=>undefined);
  };
 },[key]);
useEffect(()=>{if(value===lastInput.current)return;lastInput.current=value;if(ready&&!storageBlocked&&value!==draft.current.transcript){void persist({...draft.current,transcript:value}).catch(()=>{if(mounted.current)setError('Metin bu cihazda saklanamadı. Ekrandan ayrılmadan önce bağlantıyı ve cihazı kontrol edin.')})}},[value,ready,storageBlocked]);
 function drain():Promise<void>{
  if(draining.current)return draining.current;
  const drainKey=key;
  const work=(async()=>{
   if(scopeIsCurrent(drainKey)&&mounted.current)setTranscribing(true);
   let failedSegmentId:string|null=null;
   let requestController:AbortController|null=null;
   try{
    while(scopeIsCurrent(drainKey)&&mounted.current&&consentRef.current&&AppState.currentState==='active'&&draft.current.segments.some(s=>s.ready||s.transcribed)){
     const segment=draft.current.segments.find(s=>s.transcribed)??draft.current.segments.find(s=>s.ready)!;
     failedSegmentId=segment.id;
     if(segment.transcribed){
      await removeFile(segment.uri,segment.mime);
      if(!scopeIsCurrent(drainKey))return;
      await persist(removeVoiceSegment(draft.current,segment.id),drainKey);
      failedSegmentId=null;
      continue;
     }
     if(!consentRef.current)break;
     requestController=new AbortController();controller.current=requestController;
     const result=await transcribeNativeRecording(token,patientId,segment.uri,segment.id,requestController.signal,segment.mime||'audio/mp4');
     if(!scopeIsCurrent(drainKey)||!mounted.current)return;
     const next=markVoiceSegmentTranscribed(draft.current,segment.id,result.transcript);
     await persist(next,drainKey);
     if(!scopeIsCurrent(drainKey)||!mounted.current)return;
     setIndeterminateSegmentId(null);
     transcriptCallback.current(draft.current.transcript);
     failedSegmentId=null;
     await removeFile(segment.uri,segment.mime);
     if(!scopeIsCurrent(drainKey))return;
     await persist(removeVoiceSegment(draft.current,segment.id),drainKey);
    }
    if(scopeIsCurrent(drainKey)&&mounted.current&&!draft.current.segments.some(segment=>segment.transcribed))setStorageBlocked(false);
   }catch(e){
    if(!scopeIsCurrent(drainKey))return;
    wanted.current=false;
    try{await cut()}catch{}
    if(scopeIsCurrent(drainKey)&&mounted.current){
     const cleanupPending=draft.current.segments.some(segment=>segment.transcribed===true);
     if(cleanupPending)setStorageBlocked(true);
     if(!cleanupPending&&e instanceof VoiceAsrError&&
        (e.code==='VOICE_ASR_OUTCOME_UNKNOWN'||e.code==='VOICE_ASR_EXPIRED'))
      setIndeterminateSegmentId(failedSegmentId);
     setError(cleanupPending
      ?'Konuşma metni güvenli taslağa kaydedildi; geçici ses dosyası silinemedi. Temizliği yeniden deneyin. Aynı ses yeniden AI hizmetine gönderilmeyecek.'
      :e instanceof Error?e.message:'Ses yazıya çevrilemedi. Yerel kayıt korundu.');
    }
   }finally{
    if(controller.current===requestController)controller.current=null;
    if(scopeIsCurrent(drainKey)&&mounted.current)setTranscribing(false);
   }
  })();
  draining.current=work;
  void work.finally(()=>{if(draining.current===work)draining.current=null});
  return work;
 }
 function discardInterruptedSegment(id:string){
  const segment=draft.current.segments.find(item=>item.id===id);
  if(!segment||segment.ready||segment.transcribed||occupied||disabled||!ready)return;
  if(!isPrivateVoiceRecordingUri(segment.uri,FileSystem.cacheDirectory,segment.mime)){setStorageBlocked(true);setError('Ses yolu doğrulanamadı; dış konuma dokunulmadı.');return;}
  Alert.alert('Yarım kalan ses bölümü kaldırılsın mı?','Yalnızca bu kesintiye uğramış ses dosyası kaldırılır; önceki konuşma metni korunur.',[
   {text:'Vazgeç',style:'cancel'},
   {text:'Ses bölümünü kaldır',style:'destructive',onPress:()=>void(async()=>{
    const info=await FileSystem.getInfoAsync(segment.uri);
    if(info.exists)await removeFile(segment.uri,segment.mime);
    await persist(discardInterruptedVoiceSegment(draft.current,id));
    const hasUntrusted=draft.current.segments.some(item=>!isPrivateVoiceRecordingUri(item.uri,FileSystem.cacheDirectory,item.mime));
    const hasCleanupPending=draft.current.segments.some(item=>item.transcribed);
    if(!hasUntrusted&&!hasCleanupPending)setStorageBlocked(false);
    setError('');
   })().catch(()=>setError('Yarım kalan ses bölümü kaldırılamadı. Dosya ve önceki metin korundu.'))}
  ]);
 }
 function retryWithNewKey(){
  const segment=draft.current.segments.find(s=>s.id===indeterminateSegmentId&&s.ready);
  if(!segment)return;
  Alert.alert(
   'Yeni ses çözümleme denemesi',
   'Önceki isteğin sonucu belirsiz. Yeni anahtar aynı ses dosyasını yeniden Gemini’ye gönderir; ek bir AI çağrısı ve ücret oluşturabilir. Yalnızca açık onay verirsen devam eder.',
   [
    {text:'Vazgeç',style:'cancel'},
    {text:'Yeni deneme',style:'destructive',onPress:()=>void(async()=>{
     const next={...draft.current,segments:draft.current.segments.map(item=>
      item.id===segment.id?{...item,id:Crypto.randomUUID(),ready:true}:item)};
     const saved={...next,updatedAt:Date.now()};
     await store.setItemAsync(key,JSON.stringify(saved));
     draft.current=saved;
     if(mounted.current)setView(saved);
     setIndeterminateSegmentId(null);
     setError('');
     await drain();
    })().catch(()=>setError('Yeni deneme anahtarı güvenli biçimde kaydedilemedi. Yerel ses korunuyor.'))}
   ]
  );
 }
 async function importAudioFile(){
  if(gate.current||occupied||disabled||!ready||!consentRef.current||draft.current.ended)return;
  if(draft.current.segments.length>=5){setError('Bekleyen sesler işleniyor. Önce mevcut bölümü yazıya çevirin.');return;}
  gate.current=true;setWorking(true);setError('');
  let copiedUri:string|null=null,copiedMime:string|undefined,pickerUri:string|null=null;
  try{
   const selection=await DocumentPicker.getDocumentAsync({
    type:['audio/mpeg','audio/wav','audio/webm','audio/ogg','audio/mp4'],
    copyToCacheDirectory:true,multiple:false
   });
   if(selection.canceled||!selection.assets?.length)return;
   if(!consentRef.current)throw Error('Ses aktarımı onayı geri çekildi; dosya gönderilmedi.');
   const asset=selection.assets[0];
   pickerUri=asset.uri;
   const resolved=resolveVoiceAudioAsset(asset.mimeType,asset.name);
   const sourceInfo=await FileSystem.getInfoAsync(asset.uri);
   validateVoiceAudioBytes(sourceInfo.size);
   const cacheDirectory=FileSystem.cacheDirectory;
   if(typeof cacheDirectory!=='string'||!cacheDirectory.startsWith('file:///')||!cacheDirectory.endsWith('/'))
    throw Error('Uygulamanın özel ses önbelleği kullanılamıyor.');
   const id=Crypto.randomUUID(),uri=cacheDirectory+'voice-import-'+id+'.'+resolved.extension;
   copiedUri=uri;copiedMime=resolved.mime;
   await FileSystem.copyAsync({from:asset.uri,to:uri});
   if(!isPrivateVoiceRecordingUri(uri,cacheDirectory,resolved.mime))
    throw Error('Seçilen ses dosyası uygulamanın özel önbelleğine güvenli biçimde kopyalanamadı.');
   const copiedInfo=await FileSystem.getInfoAsync(uri);
   validateVoiceAudioBytes(copiedInfo.size);
   if(pickerUri&&pickerUri!==uri&&pickerUri.startsWith(cacheDirectory)){
    await FileSystem.deleteAsync(pickerUri,{idempotent:true});pickerUri=null;
   }
   const duration=await readPrivateVoiceAudioDuration(uri,resolved.mime);
   validateVoiceAudioDuration(duration);
   if(!consentRef.current)throw Error('Ses aktarımı onayı geri çekildi; dosya gönderilmedi.');
   if(!scopeIsCurrent(key))throw Error('Hasta veya hesap değişti; ses dosyası aktarılmadı.');
   const segment={id,uri,ready:true,mime:resolved.mime};
   const saved=await persist({...draft.current,audioStarted:true,ended:false,segments:[...draft.current.segments,segment]});
   if(!saved)throw Error('Ses taslağı güvenli biçimde kaydedilemedi; dosya gönderilmedi.');
   copiedUri=null;
   setError('Ses dosyası güvenli taslağa eklendi. Yazıya çevriliyor…');
   await drain();
  }catch(error){
   if(copiedUri)await removeFile(copiedUri,copiedMime).catch(()=>{});
   if(mounted.current)setError(error instanceof Error?error.message:'Ses dosyası işlenemedi. Yerel kopya korunuyor.');
  }finally{
   const cacheDirectory=FileSystem.cacheDirectory;
   if(pickerUri&&typeof cacheDirectory==='string'&&pickerUri.startsWith(cacheDirectory))
    await FileSystem.deleteAsync(pickerUri,{idempotent:true}).catch(()=>{});
   gate.current=false;
   if(mounted.current)setWorking(false);
  }
 }
 async function startChunk(){
  if(!wanted.current||!mounted.current||!focus.current)return;
  if(draft.current.segments.length>=5){wanted.current=false;setError('Bekleyen sesler işleniyor. Kayıtlar yazıya çevrildikten sonra devam edin.');setRecording(false);return;}
  await recorder.prepareToRecordAsync(options);
  const uri=recorder.uri;if(!uri||!isPrivateVoiceRecordingUri(uri))throw Error('Mikrofon kayıt dosyası uygulamanın özel önbelleğinde doğrulanamadı.');
  const id=Crypto.randomUUID();active.current=id;stopped.current=true;chunkStartedAt.current=null;
  try{await persist({...draft.current,ended:false,audioStarted:true,segments:[...draft.current.segments,{id,uri,ready:false}]});}
  catch(error){active.current=null;try{await removeFile(uri);}catch{}throw error;}
  if(!wanted.current||!mounted.current||AppState.currentState!=='active'||!focus.current){await discardUnstartedSegment(id,uri);return;}
  try{stopped.current=false;recorder.record();chunkStartedAt.current=Date.now();setElapsedMs(draft.current.elapsedMs||0);setRecording(true);timer.current=setTimeout(()=>void rotate(),15000);}
  catch(error){try{await recorder.stop();stopped.current=true;await discardUnstartedSegment(id,uri);}catch{}throw error;}
 }
 function cut():Promise<void>{
  if(cutting.current)return cutting.current;
  const work=(async()=>{
   if(timer.current){clearTimeout(timer.current);timer.current=null;}
   const id=active.current;if(!id)return;
   const startedAt=chunkStartedAt.current;
   // A false recorder status is expected during this stop/start rotation.
   // Clear the old recording marker before Expo Audio can publish that state.
   wasRecording.current=false;
   if(!stopped.current){await recorder.stop();stopped.current=true;}
   const segment=draft.current.segments.find(item=>item.id===id);
   if(!segment){active.current=null;chunkStartedAt.current=null;return;}
   if(startedAt===null){await discardUnstartedSegment(id,segment.uri);wasRecording.current=false;if(!wanted.current)await setAudioModeAsync({allowsRecording:false});if(mounted.current)setRecording(false);return;}
   const info=await FileSystem.getInfoAsync(segment.uri);
   let next=addVoiceElapsed(draft.current,startedAt,Date.now());
   if(!info.exists)next=discardInterruptedVoiceSegment(next,id);
   else if(typeof info.size==='number'&&info.size>=100&&info.size<=8*1024*1024)next=markVoiceSegmentReady(next,id);
   await persist(next);
   active.current=null;chunkStartedAt.current=null;stopped.current=true;wasRecording.current=false;
   if(mounted.current)setElapsedMs(next.elapsedMs||0);
   if(!wanted.current)await setAudioModeAsync({allowsRecording:false});
   if(mounted.current){setRecording(false);if(info.exists&&!next.segments.some(item=>item.id===id&&item.ready))setError('Ses bölümü boş veya 8 MB sınırını aşıyor. Yarım kalan bölümü kaldırıp yeniden kaydedin.');}
  })();
  cutting.current=work;void work.finally(()=>{if(cutting.current===work)cutting.current=null}).catch(()=>{});return work;
 }
 async function rotate(){if(gate.current||!wanted.current)return;gate.current=true;try{await cut();if(wanted.current)await startChunk();void drain()}catch(e){wanted.current=false;if(mounted.current){if(active.current&&!status.isRecording){stopped.current=true;setRecording(false)}else if(!active.current)setRecording(false);setError(e instanceof Error?e.message:'Mikrofon kesildi; yerel kayıtları kontrol edin.')}}finally{gate.current=false}}
 async function start(){if(gate.current||disabled||storageBlocked||!consent||!ready||!canResumeVoiceDraft(draft.current))return;gate.current=true;setWorking(true);setError('');try{const permission=await requestRecordingPermissionsAsync();if(!permission.granted)throw Error('Muayene kaydı için mikrofon izni verin.');if(!mounted.current||!consentRef.current)return;await setAudioModeAsync({allowsRecording:true,playsInSilentMode:true,shouldPlayInBackground:false});if(!consentRef.current){await setAudioModeAsync({allowsRecording:false});return}if(AppState.currentState!=='active'||!focus.current)throw Error('Kayıt için uygulamayı ön plana getirin.');if(!consentRef.current)return;wanted.current=true;await startChunk()}catch(e){wanted.current=false;if(mounted.current){if(active.current&&!status.isRecording){stopped.current=true;setRecording(false)}else setRecording(Boolean(active.current));setError(e instanceof Error?e.message:'Mikrofon başlatılamadı.')}}finally{gate.current=false;if(mounted.current)setWorking(false)}}
 async function pause(background=false){wanted.current=false;if(background)controller.current?.abort();if(gate.current)return;gate.current=true;if(mounted.current)setWorking(true);try{await cut();if(!background&&consentRef.current)await drain();else if(background&&mounted.current)setError('Uygulama arka plana alındı; kayıt durdu. Bekleyen sesleri kontrol ederek devam edin.');else if(mounted.current)setError('Onay geri çekildi; bekleyen ses bölümü cihazda korundu ve aktarılmadı.')}catch(e){if(mounted.current){if(active.current&&!status.isRecording){stopped.current=true;setRecording(false)}setError(e instanceof Error?e.message:'Kayıt durdurulamadı; ses dosyası korunuyor.')}}finally{gate.current=false;if(mounted.current)setWorking(false)}}
 async function finish(){if(gate.current||disabled||draft.current.ended)return;wanted.current=false;gate.current=true;setWorking(true);setError('');try{await cut();if(!consentRef.current){setError('Onay geri çekildi; bekleyen ses bölümü cihazda korundu. Klinik değerlendirme başlatılmadı.');return}await drain();if(!consentRef.current){setError('Onay geri çekildi; klinik değerlendirme başlatılmadı.');return}if(draft.current.segments.some(segment=>segment.transcribed)){setStorageBlocked(true);setError('Konuşma metni güvenli taslağa kaydedildi ancak geçici ses dosyası silinemedi. Temizliği yeniden deneyin; aynı ses yeniden AI hizmetine gönderilmeyecek.');return}if(draft.current.segments.length){setError(previous=>previous||'Bekleyen sesler yazıya çevrilmeden klinik değerlendirme başlatılamaz.');return}if(!draft.current.transcript.trim())throw Error('Muayene metni henüz yok.');await persist({...draft.current,ended:true});if(mounted.current)finishCallback.current(draft.current.transcript,draft.current.sessionId||'')}catch(e){if(mounted.current)setError(e instanceof Error?e.message:'Muayene bitirilemedi; taslak korundu.')}finally{gate.current=false;if(mounted.current)setWorking(false)}}
 useEffect(()=>{if(!focused){controller.current?.abort();if(wanted.current)void pause(true)}},[focused]);
 useEffect(()=>{const listener=AppState.addEventListener('change',state=>{if(state!=='active'){controller.current?.abort();if(wanted.current)void pause(true)}});return()=>listener.remove()},[]);
 useEffect(()=>{
  const unexpectedStop=isUnexpectedVoiceRecorderStop(wasRecording.current,wanted.current,Boolean(active.current),gate.current);
  wasRecording.current=status.isRecording;
  if(unexpectedStop){wanted.current=false;void pause(true);setError('Mikrofon kaydı kesildi. Ses dosyasını ve mikrofon bağlantısını kontrol edin.');}
  if(status.mediaServicesDidReset&&wanted.current){wanted.current=false;void pause(true);}
 },[status.isRecording,status.mediaServicesDidReset]);
 async function clear(){if(occupied||disabled)return;try{const untrustedAudio=draft.current.segments.some(segment=>!isPrivateVoiceRecordingUri(segment.uri,FileSystem.cacheDirectory,segment.mime));for(const segment of draft.current.segments)if(isPrivateVoiceRecordingUri(segment.uri,FileSystem.cacheDirectory,segment.mime))await removeFile(segment.uri,segment.mime);await store.deleteItemAsync(key);draft.current=newVoiceDraft(userId,patientId,Date.now(),Crypto.randomUUID());setView(draft.current);setElapsedMs(0);setStorageBlocked(false);setIndeterminateSegmentId(null);transcriptCallback.current('');setError(untrustedAudio?'Taslak temizlendi. Uygulama önbelleği dışında kalan doğrulanamayan dosyaya dokunulmadı.':'')}catch{setError('Taslak tamamen temizlenemedi. Yeniden deneyin.')}}
 const button=(label:string,action:()=>void,blocked=false,primary=false)=><Pressable accessibilityRole="button" disabled={blocked||storageBlocked||disabled||!consent||!ready} onPress={action} style={[s.button,primary&&s.primaryButton,(blocked||storageBlocked||disabled||!consent||!ready)&&s.disabledButton]}><Text style={[s.action,primary&&s.primaryAction]}>{label}</Text></Pressable>;
 const phaseLabel=recording?'Dinleniyor':transcribing?'Konuşma yazıya çevriliyor':working?'İşlem sürüyor':view.ended?'Muayene tamamlandı':view.audioStarted?'Duraklatıldı':'Başlamaya hazır';
 const transcriptPreview=value.trim()?value.trim().split('\n').slice(-3).join('\n').slice(-600):'';
 return <View style={s.card}>
  <View style={s.header}>
   <View style={s.headerCopy}><Text style={s.eyebrow}>SESLİ MUAYENE</Text><Text style={s.title}>Görüşme kaydı</Text></View>
   {view.audioStarted&&<View style={s.timerPill}><Text style={s.timer}>{formatVoiceElapsed(elapsedMs)}</Text></View>}
  </View>
  <View style={s.hero}>
   {view.audioStarted&&<View style={[s.micCircle,recording&&s.micCircleActive]}><Text style={s.micGlyph}>🎙</Text></View>}
   <Text accessibilityLiveRegion="polite" style={s.phase}>{phaseLabel}</Text>
   <Text style={s.meta}>{recording?'Mikrofon açık':transcribing?'Ses bölümleri güvenli şekilde yazıya çevriliyor':view.ended?'Mikrofon kapalı · Görüşme bitti':view.audioStarted?'Mikrofon kapalı · Devam edebilirsiniz':'Mikrofon kapalı · Yalnızca başlattığınızda açılır'}</Text>
   {recording&&<View accessibilityRole="progressbar" accessibilityLabel="Mikrofon ses seviyesi" accessibilityValue={{min:0,max:100,now:Math.round(level*100)}} style={s.levelTrack}><View style={[s.levelFill,{width:(Math.round(level*100)+'%') as `${number}%`}]} /></View>}
   {recording&&<View style={s.wave} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">{WAVE_BARS.map((height,index)=><View key={index} style={[s.waveBar,{height:Math.max(5,Math.round(height*(0.25+level)))}]} />)}</View>}
  </View>
  <Text style={s.helper}>Konuşma, kısa ses bölümleri tamamlandıkça yazıya çevrilir. Klinik değerlendirme yalnızca “Muayeneyi bitir” işleminden sonra başlar. Ham ses ve tam konuşma metni hasta dosyasına otomatik kaydedilmez.</Text>
  {transcriptPreview?<View style={s.preview}><Text style={s.previewLabel}>SON ALINAN KONUŞMA METNİ</Text><Text selectable numberOfLines={4} style={s.previewText}>{transcriptPreview}</Text></View>:null}
  {!ready&&<ActivityIndicator color="#1769AA"/>}
  <View style={s.controls}>
   {recording?button('Ⅱ  Duraklat',()=>void pause(),working,true):button(view.ended?'Muayene tamamlandı':view.audioStarted?'▶  Devam et':'Mikrofonu başlat',()=>void start(),occupied||view.segments.length>0||view.ended,true)}
   {active.current&&stopped.current&&!recording&&button('Ses bölümünü güvenle tamamla',()=>void(async()=>{await cut();await drain()})().catch(error=>setError(error instanceof Error?error.message:'Ses bölümü tamamlanamadı; yerel kayıt korundu.')),occupied)}
   {button('Muayeneyi bitir',()=>void finish(),working||view.ended||!recording&&!view.transcript&&!view.segments.length,true)}
  </View>
  {button('Ses dosyası seç',()=>void importAudioFile(),occupied||view.ended||view.segments.length>0)}
  <Text style={s.helper}>Web ile aynı sınırlar: MP3, WAV, WebM, OGG veya M4A · en fazla 90 saniye ve 8 MB. Ses yalnızca yazıya çevrilir; klinik değerlendirme “Muayeneyi bitir” işleminde başlar.</Text>
  {view.segments.some(segment=>segment.ready)&&!recording&&button('Bekleyen sesleri yazıya çevir',()=>{setError('');void(async()=>{await persist({...draft.current,segments:draft.current.segments.map(s=>s.transcribed?s:{...s,ready:true})});await drain()})().catch(()=>setError('Ses taslağı güncellenemedi.'))},occupied)}
  {view.segments.filter(segment=>!segment.ready&&!segment.transcribed&&isPrivateVoiceRecordingUri(segment.uri,FileSystem.cacheDirectory,segment.mime)).map(segment=><Pressable key={segment.id} accessibilityRole="button" disabled={occupied||disabled||!ready} onPress={()=>discardInterruptedSegment(segment.id)} style={[s.cleanupButton,(occupied||disabled||!ready)&&s.disabledButton]}><Text style={s.cleanupText}>Yarım kalan ses bölümünü kaldır</Text></Pressable>)}
  {view.segments.some(segment=>segment.transcribed)&&<Pressable accessibilityRole="button" disabled={occupied||disabled||!ready} onPress={()=>void cleanupTranscribedSegments().then(()=>setError('')).catch(()=>{setStorageBlocked(true);setError('Geçici ses dosyası hâlâ silinemedi. Metin korundu; temizliği yeniden deneyin.')})} style={[s.cleanupButton,(occupied||disabled||!ready)&&s.disabledButton]}><Text style={s.cleanupText}>Geçici ses dosyasını temizlemeyi yeniden dene</Text></Pressable>}
  {indeterminateSegmentId&&<View style={s.retryNotice}><Text style={s.retryText}>Önceki isteğin sonucu kesinleşmedi. Aynı anahtarla ikinci AI çağrısı yapılmaz. Yeni deneme ayrı bir Gemini çağrısı oluşturabilir.</Text>{button('Yeni anahtarla yeniden dene',retryWithNewKey,occupied)}</View>}
  <Pressable accessibilityRole="button" disabled={occupied||disabled||!ready} onPress={()=>Alert.alert('Muayene taslağı silinsin mi?','Bu cihazdaki metin ve bekleyen sesler temizlenir. Hasta dosyasına kaydedilen onaylı bilgiler bu işlemle silinmez.',[{text:'Vazgeç',style:'cancel'},{text:'Sil',style:'destructive',onPress:()=>void clear()}])} style={s.clearButton}><Text style={s.clearText}>Taslağı ve yerel sesleri sil</Text></Pressable>
  {!!error&&<Text accessibilityRole="alert" style={s.error}>{error}</Text>}
 </View>;
}
const s=StyleSheet.create({
 card:{marginTop:16,padding:16,borderWidth:1,borderColor:'#DCE4ED',borderRadius:20,backgroundColor:'#FFFFFF',gap:12},
 header:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:12},
 headerCopy:{flex:1,gap:3},eyebrow:{fontSize:10,fontWeight:'800',letterSpacing:1.3,color:'#397C98'},
 title:{fontSize:18,fontWeight:'800',color:'#071B35'},timerPill:{backgroundColor:'#EAF2F8',borderRadius:12,paddingHorizontal:13,paddingVertical:8},
 timer:{fontVariant:['tabular-nums'],fontSize:18,fontWeight:'800',color:'#102A46'},
 hero:{alignItems:'center',paddingVertical:8,gap:8},micCircle:{width:76,height:76,borderRadius:38,backgroundColor:'#102A46',alignItems:'center',justifyContent:'center',borderWidth:4,borderColor:'#EAF2F8'},
 micCircleActive:{backgroundColor:'#1769AA',borderColor:'#D8ECFA'},micGlyph:{fontSize:30,color:'#FFFFFF'},phase:{fontSize:18,fontWeight:'800',color:'#102A46'},
 meta:{color:'#63748A',lineHeight:20,textAlign:'center'},levelTrack:{height:5,width:'78%',backgroundColor:'#E8EDF3',borderRadius:99,overflow:'hidden'},
 levelFill:{height:5,backgroundColor:'#2B82B8',borderRadius:99},wave:{height:24,flexDirection:'row',alignItems:'center',justifyContent:'center',gap:5},
 waveBar:{width:4,borderRadius:4,backgroundColor:'#2B82B8'},helper:{color:'#63748A',lineHeight:20,fontSize:13},
 preview:{padding:12,borderRadius:12,backgroundColor:'#F4F8FB',borderWidth:1,borderColor:'#DCE8F0',gap:6},
 previewLabel:{fontSize:10,fontWeight:'800',letterSpacing:0.7,color:'#397C98'},previewText:{color:'#102A46',lineHeight:20},
 controls:{flexDirection:'column',gap:9},button:{width:'100%',minHeight:48,padding:13,borderRadius:12,backgroundColor:'#E8F0FF',alignItems:'center',justifyContent:'center'},
 primaryButton:{backgroundColor:'#102A46'},disabledButton:{opacity:0.42},action:{color:'#1769AA',fontWeight:'800',textAlign:'center'},primaryAction:{color:'#FFFFFF'},
 cleanupButton:{padding:12,borderRadius:10,borderWidth:1,borderColor:'#DCE4ED',alignItems:'center'},cleanupText:{color:'#1769AA',fontWeight:'700',textAlign:'center'},
 retryNotice:{padding:10,borderRadius:10,backgroundColor:'#FFF7E8',gap:8},retryText:{color:'#8A4B0F',lineHeight:20},
 clearButton:{paddingVertical:9,alignItems:'center'},clearText:{color:'#63748A',fontWeight:'700'},error:{color:'#B42318',lineHeight:21}
});
