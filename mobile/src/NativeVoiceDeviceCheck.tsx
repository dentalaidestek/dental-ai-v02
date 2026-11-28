import React,{useEffect,useMemo,useRef,useState} from 'react';
import {ActivityIndicator,AppState,Pressable,Text,View} from 'react-native';
import {useIsFocused} from '@react-navigation/native';
import {RecordingPresets,requestRecordingPermissionsAsync,setAudioModeAsync,useAudioRecorder,useAudioRecorderState} from 'expo-audio';
import * as FileSystem from 'expo-file-system/legacy';
import {evaluateVoiceDeviceCheck,isPrivateVoiceDeviceCheckUri,removePrivateVoiceDeviceCheckFile,removePrivateVoiceDeviceCheckCacheChildFile,stopVoiceDeviceRecorderVerified,voiceDeviceSignalLevel,VOICE_DEVICE_CHECK_DURATION_MS} from './voiceDeviceCheck';
import type {VoiceDeviceCheckOutcome} from './voiceDeviceCheck';
import {restoreVoiceAudioMode,waitForVoiceRecorderStarted} from './voiceRecorderLifecycle';

type Phase='idle'|'requesting'|'testing'|'finishing'|'complete';
const navy='#071B35',muted='#63748A',line='#E1E7EF',blue='#1769AA';
type VoiceDeviceCheckUiOutcome=VoiceDeviceCheckOutcome|'recorder_stop_failed';
const resultText:Record<VoiceDeviceCheckUiOutcome,string>={
 permission_denied:'Mikrofon izni verilmedi. Android uygulama izinlerinden veya iOS Ayarlar bölümünden mikrofon erişimini açıp tekrar deneyin.',
 capture_incomplete:'Altı saniyelik test tamamlanamadı. Uygulamayı ön planda tutup yeniden deneyin.',
 no_audio_file:'Cihaz ses dosyası oluşturamadı. Mikrofonu kullanan diğer uygulamaları kapatıp tekrar deneyin.',
 metering_unavailable:'Ses seviyesi bu cihazdan okunamadı. Bu sonuç mikrofonun çalışmadığını kanıtlamaz; gerçek muayene öncesi cihazda ayrıca kontrol edin.',
 low_signal:'Kayıt alındı ancak yeterli ses seviyesi algılanmadı. Mikrofon girişini, Bluetooth kulaklığı ve cihaz sesini kontrol edip tekrar deneyin.',
 cleanup_failed:'Geçici mikrofon dosyasının güvenli konumu veya silinmesi doğrulanamadı. Yalnızca uygulamanın özel önbelleğindeki doğrudan dosyalar silinir; bu uyarı kalkmadan test yeniden başlatılamaz.',
 audio_mode_restore_failed:'Geçici dosya temizlendi ancak cihazın ses yönlendirmesi kayıt modundan çıkarılamadı. Mikrofon testine yeniden başlamadan önce aşağıdaki yeniden deneme düğmesini kullanın.',
 recorder_stop_failed:'Mikrofon kaydının durduğu doğrulanamadı. Geçici dosya silinmedi ve ses yönlendirmesi değiştirilmedi. Aynı durdurma işlemini yeniden deneyin.',
 passed:'Mikrofon izni ve ses kaydı başarılı; cihaz ses yakalıyor. Bu sonuç konuşma tanıma veya Gemini bağlantısını doğrulamaz.'
};

export default function NativeVoiceDeviceCheck({disabled=false,onBusyChange}:{disabled?:boolean;onBusyChange?:(busy:boolean)=>void}){
 const options=useMemo(()=>({...RecordingPresets.HIGH_QUALITY,directory:'cache' as const,isMeteringEnabled:true,numberOfChannels:1}),[]);
 const recorder=useAudioRecorder(options),status=useAudioRecorderState(recorder,100),focused=useIsFocused();
 const [phase,setPhase]=useState<Phase>('idle'),[level,setLevel]=useState(0),[result,setResult]=useState(''),[stopPending,setStopPending]=useState(false),[cleanupPending,setCleanupPending]=useState(false),[audioModeBlocked,setAudioModeBlocked]=useState(false);
 const mounted=useRef(true),running=useRef(false),prepared=useRef(false),uri=useRef<string|null>(null),startedAt=useRef(0),peakDb=useRef<number|null>(null),epoch=useRef(0),timer=useRef<ReturnType<typeof setTimeout>|null>(null),busy=useRef(false),finishing=useRef<Promise<void>|null>(null),cancelRef=useRef<(message?:string)=>Promise<void>>(async()=>{});
 const busyCallback=useRef(onBusyChange);busyCallback.current=onBusyChange;
 function notifyBusy(value:boolean){if(busy.current===value)return;busy.current=value;busyCallback.current?.(value);}
 async function resetAudioMode():Promise<boolean>{
  const restored=await restoreVoiceAudioMode(()=>setAudioModeAsync({allowsRecording:false}));
  if(mounted.current)setAudioModeBlocked(!restored);
  return restored;
 }
 async function removeTemporaryFile(path:string|null):Promise<boolean>{
  if(!path)return true;
  return isPrivateVoiceDeviceCheckUri(path,FileSystem.cacheDirectory)
   ?removePrivateVoiceDeviceCheckFile(path,FileSystem.cacheDirectory,FileSystem)
   :removePrivateVoiceDeviceCheckCacheChildFile(path,FileSystem.cacheDirectory,FileSystem);
 }
 async function stopPreparedRecorder():Promise<boolean>{
  if(!prepared.current)return true;
  const stopped=await stopVoiceDeviceRecorderVerified(recorder);
  if(stopped)prepared.current=false;
  return stopped;
 }
 useEffect(()=>{
  if(phase!=='testing'||typeof status.metering!=='number'||!Number.isFinite(status.metering))return;
  peakDb.current=peakDb.current===null?status.metering:Math.max(peakDb.current,status.metering);
  setLevel(voiceDeviceSignalLevel(status.metering));
 },[phase,status.metering]);
 async function finish(run:number){
  if(run!==epoch.current||!running.current)return;
  if(finishing.current)return finishing.current;
  const work=(async()=>{
   running.current=false;
   if(timer.current){clearTimeout(timer.current);timer.current=null;}
   if(mounted.current)setPhase('finishing');
   const path=uri.current;
   let durationMs=Math.max(0,Date.now()-startedAt.current),fileBytes=0;
   if(prepared.current){
    const stopped=await stopPreparedRecorder();
    if(!stopped){
     if(mounted.current){setStopPending(true);setCleanupPending(false);setPhase('complete');setResult(resultText.recorder_stop_failed);}
     // Keep the recorder, file and recording audio mode intact until a later
     // stop attempt is positively confirmed by Expo's synchronous status.
     notifyBusy(true);
     return;
    }
   }
   try{
    const finalStatus=recorder.getStatus();
    if(Number.isFinite(finalStatus.durationMillis))durationMs=Math.max(durationMs,finalStatus.durationMillis);
    if(path&&isPrivateVoiceDeviceCheckUri(path,FileSystem.cacheDirectory)){
     const info=await FileSystem.getInfoAsync(path);
     if(info.exists&&typeof info.size==='number')fileBytes=info.size;
    }
   }catch{fileBytes=0;}
   const cleanupVerified=await removeTemporaryFile(path);
   if(cleanupVerified)uri.current=null;
   if(mounted.current){setStopPending(false);setCleanupPending(!cleanupVerified);}
   const audioModeRestored=await resetAudioMode();
   notifyBusy(!audioModeRestored);
   if(run!==epoch.current||!mounted.current)return;
   const outcome=evaluateVoiceDeviceCheck({permissionGranted:true,durationMs,fileBytes,peakMeteringDb:peakDb.current,cleanupVerified,audioModeRestored});
   setPhase('complete');setResult(resultText[outcome]);
  })();
  finishing.current=work;
  try{await work;}finally{if(finishing.current===work)finishing.current=null;}
 }
 async function cancel(message='Test durduruldu. Mikrofon kapatıldı.'){
  epoch.current++;
  if(timer.current){clearTimeout(timer.current);timer.current=null;}
  running.current=false;
  if(finishing.current)await finishing.current.catch(()=>{});
  if(prepared.current){
   const stopped=await stopPreparedRecorder();
   if(!stopped){
    if(mounted.current){setPhase('complete');setLevel(0);setStopPending(true);setCleanupPending(false);setResult(resultText.recorder_stop_failed);}
    notifyBusy(true);
    return;
   }
  }
  const cleanupVerified=await removeTemporaryFile(uri.current);
  if(cleanupVerified)uri.current=null;
  const audioModeRestored=await resetAudioMode();
  notifyBusy(!audioModeRestored);
  if(mounted.current){
   setPhase('complete');setLevel(0);setStopPending(false);setCleanupPending(!cleanupVerified);
   setResult(!cleanupVerified?resultText.cleanup_failed:!audioModeRestored?resultText.audio_mode_restore_failed:message);
  }
 }
 cancelRef.current=cancel;
 async function retryCleanup(){
  if(prepared.current){
   const stopped=await stopPreparedRecorder();
   if(!stopped){
    setStopPending(true);setResult(resultText.recorder_stop_failed);notifyBusy(true);return;
   }
   setStopPending(false);
  }
  const path=uri.current;
  const cleaned=await removeTemporaryFile(path);
  if(cleaned)uri.current=null;
  const audioModeRestored=await resetAudioMode();
  setCleanupPending(!cleaned);
  if(!cleaned)setResult(resultText.cleanup_failed);
  else if(!audioModeRestored)setResult(resultText.audio_mode_restore_failed);
  else setResult('Geçici ses dosyası silindi ve cihazın ses yönlendirmesi geri yüklendi. Mikrofon testi yeniden başlatılabilir.');
  notifyBusy(!audioModeRestored);
 }
 async function start(){
  if(disabled||stopPending||cleanupPending||audioModeBlocked||uri.current!==null||running.current||phase==='requesting'||phase==='testing'||phase==='finishing')return;
  const run=++epoch.current;
  running.current=true;peakDb.current=null;startedAt.current=0;setLevel(0);setResult('');setCleanupPending(false);setPhase('requesting');notifyBusy(true);
  try{
   const permission=await requestRecordingPermissionsAsync();
   if(run!==epoch.current)return;
   if(!permission.granted){
    running.current=false;notifyBusy(false);setPhase('complete');setResult(resultText.permission_denied);return;
   }
   await setAudioModeAsync({allowsRecording:true,playsInSilentMode:true,shouldPlayInBackground:false});
   if(run!==epoch.current){
    const restored=await resetAudioMode();
    notifyBusy(!restored);
    if(!restored&&mounted.current){setPhase('complete');setResult(resultText.audio_mode_restore_failed);}
    return;
   }
   await recorder.prepareToRecordAsync(options);
   prepared.current=true;
   const path=recorder.uri;
   const cache=FileSystem.cacheDirectory;
   // Retain even an unexpected recorder URI in memory so cleanup fails closed.
   // The cleanup helper will delete it only if it is a direct child of app cache.
   if(typeof path==='string'&&path)uri.current=path;
   if(!path||!cache||!isPrivateVoiceDeviceCheckUri(path,cache))throw Error('Geçici test kaydı uygulamanın özel önbelleğinde doğrulanamadı; güvenli temizleme tamamlanmadan mikrofon testi engellendi.');
   if(run!==epoch.current){await cancelRef.current();return;}
   startedAt.current=Date.now();
   recorder.record();
   setPhase('testing');
   timer.current=setTimeout(()=>{void finish(run);},VOICE_DEVICE_CHECK_DURATION_MS);
  }catch(error){
   if(run!==epoch.current)return;
   running.current=false;
   const path=uri.current;
   const stopped=await stopPreparedRecorder();
   if(!stopped){
    if(mounted.current){setPhase('complete');setStopPending(true);setCleanupPending(false);setResult(resultText.recorder_stop_failed);}
    notifyBusy(true);
    return;
   }
   const cleanupVerified=await removeTemporaryFile(path);
   if(cleanupVerified)uri.current=null;
   const audioModeRestored=await resetAudioMode();notifyBusy(!audioModeRestored);
   if(mounted.current){setPhase('complete');setStopPending(false);setCleanupPending(!cleanupVerified);setResult(!cleanupVerified?resultText.cleanup_failed:!audioModeRestored?resultText.audio_mode_restore_failed:(error instanceof Error?error.message:'Mikrofon testi başlatılamadı.'));}
  }
 }
 useEffect(()=>{
  const subscription=AppState.addEventListener('change',state=>{
   if(state!=='active'&&running.current)void cancel('Uygulama arka plana geçti. Test iptal edildi ve mikrofon kapatıldı.');
   // Otomatik iptal mesajı ön plana dönüşte temizlenir; sürekli hata ekranında kalmaz.
   if(state==='active'&&mounted.current)setResult(prev=>prev==='Uygulama arka plana geçti. Test iptal edildi ve mikrofon kapatıldı.'?'':prev);
  });
  return()=>subscription.remove();
 },[]);
 useEffect(()=>{if(!focused&&running.current)void cancel('Ekran değişti. Test iptal edildi ve mikrofon kapatıldı.');if(focused&&mounted.current)setResult(prev=>prev==='Ekran değişti. Test iptal edildi ve mikrofon kapatıldı.'?'':prev);},[focused]);
 useEffect(()=>()=>{mounted.current=false;void cancelRef.current('Ekran kapandı. Geçici mikrofon testi temizlendi.');},[]);
 const busyPhase=phase==='requesting'||phase==='testing'||phase==='finishing';
 const buttonLabel=phase==='requesting'?'Mikrofon izni bekleniyor…':phase==='testing'?'Test sürüyor…':'Bu cihazın mikrofonunu test et';
 return <View style={{backgroundColor:'#FFFFFF',borderWidth:1,borderColor:line,borderRadius:16,padding:15,marginTop:14}}>
  <Text style={{fontSize:16,fontWeight:'800',color:navy}}>Mikrofon kontrolü</Text>
  <Text style={{color:muted,lineHeight:20,marginTop:6}}>Muayenede kullanacağınız cihazda altı saniyelik test yapın. Geçici ses dosyası yalnızca uygulamanın özel önbelleğinde tutulur; sunucuya veya yapay zekâya gönderilmez, yazıya çevrilmez ve test sonunda silinir.</Text>
  <View style={{marginTop:14}}>
   <Text style={{color:navy,fontWeight:'700',fontSize:12,marginBottom:7}}>Canlı ses seviyesi</Text>
   <View accessibilityRole="progressbar" accessibilityValue={{min:0,max:100,now:Math.round(level*100)}} style={{height:10,backgroundColor:'#E8EDF3',borderRadius:99,overflow:'hidden'}}>
    <View style={{height:10,width:(Math.round(level*100)+'%') as `${number}%`,backgroundColor:blue,borderRadius:99}}/>
   </View>
  </View>
  <View style={{flexDirection:'row',gap:9,marginTop:14}}>
   <Pressable accessibilityRole="button" disabled={disabled||busyPhase||stopPending||cleanupPending||audioModeBlocked} onPress={()=>void start()} style={{flex:1,backgroundColor:disabled||busyPhase||stopPending||cleanupPending||audioModeBlocked?'#9BA7B7':blue,borderRadius:11,padding:13,alignItems:'center'}}>
    <Text style={{color:'#FFFFFF',fontWeight:'800',textAlign:'center'}}>{buttonLabel}</Text>
   </Pressable>
   {phase==='testing'&&<Pressable accessibilityRole="button" onPress={()=>void cancel()} style={{backgroundColor:'#FEE4E2',borderRadius:11,padding:13,justifyContent:'center'}}><Text style={{color:'#B42318',fontWeight:'800'}}>Durdur</Text></Pressable>}
  </View>
  {busyPhase&&<View style={{flexDirection:'row',alignItems:'center',gap:9,marginTop:10}}><ActivityIndicator color={blue}/><Text accessibilityLiveRegion="polite" style={{color:muted}}>{phase==='testing'?'Birkaç kelime söyleyin. Test altı saniye sonra otomatik kapanır.':'Mikrofon hazırlanıyor…'}</Text></View>}
  {!!result&&<Text accessibilityLiveRegion="polite" accessibilityRole={stopPending||cleanupPending||audioModeBlocked?'alert':undefined} style={{color:phase==='complete'&&result===resultText.passed?'#067647':stopPending||cleanupPending?'#B42318':muted,lineHeight:20,marginTop:12}}>{result}</Text>}
  {(stopPending||cleanupPending||audioModeBlocked)&&<Pressable accessibilityRole="button" disabled={busyPhase} onPress={()=>void retryCleanup()} style={{marginTop:10,borderWidth:1,borderColor:'#B42318',borderRadius:11,padding:12,alignItems:'center'}}>
   <Text style={{color:'#B42318',fontWeight:'800',textAlign:'center'}}>{stopPending?'Mikrofonu güvenle durdurmayı yeniden dene':cleanupPending&&audioModeBlocked?'Geçici ses dosyasını ve cihaz ses yönlendirmesini yeniden dene':cleanupPending?'Geçici ses dosyasını silmeyi yeniden dene':'Cihaz ses yönlendirmesini yeniden dene'}</Text>
  </Pressable>}
 </View>;
}
