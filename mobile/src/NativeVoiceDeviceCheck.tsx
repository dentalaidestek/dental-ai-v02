import React,{useEffect,useMemo,useRef,useState} from 'react';
import {ActivityIndicator,AppState,Pressable,Text,View} from 'react-native';
import {useIsFocused} from '@react-navigation/native';
import {RecordingPresets,requestRecordingPermissionsAsync,setAudioModeAsync,useAudioRecorder,useAudioRecorderState} from 'expo-audio';
import * as FileSystem from 'expo-file-system/legacy';
import {evaluateVoiceDeviceCheck,isPrivateVoiceDeviceCheckUri,removePrivateVoiceDeviceCheckFile,voiceDeviceSignalLevel,VOICE_DEVICE_CHECK_DURATION_MS} from './voiceDeviceCheck';
import type {VoiceDeviceCheckOutcome} from './voiceDeviceCheck';

type Phase='idle'|'requesting'|'testing'|'finishing'|'complete';
const navy='#071B35',muted='#63748A',line='#E1E7EF',blue='#1769AA';
const resultText:Record<VoiceDeviceCheckOutcome,string>={
 permission_denied:'Mikrofon izni verilmedi. Android uygulama izinlerinden veya iOS Ayarlar bölümünden mikrofon erişimini açıp tekrar deneyin.',
 capture_incomplete:'Altı saniyelik test tamamlanamadı. Uygulamayı ön planda tutup yeniden deneyin.',
 no_audio_file:'Cihaz ses dosyası oluşturamadı. Mikrofonu kullanan diğer uygulamaları kapatıp tekrar deneyin.',
 metering_unavailable:'Ses seviyesi bu cihazdan okunamadı. Bu sonuç mikrofonun çalışmadığını kanıtlamaz; gerçek muayene öncesi cihazda ayrıca kontrol edin.',
 low_signal:'Kayıt alındı ancak yeterli ses seviyesi algılanmadı. Mikrofon girişini, Bluetooth kulaklığı ve cihaz sesini kontrol edip tekrar deneyin.',
 cleanup_failed:'Geçici mikrofon ses dosyasının silindiği doğrulanamadı. Test başarılı sayılmıyor; dosyayı silmeyi yeniden deneyin. Dosya yalnızca uygulamanın özel önbelleğinde aranır.',
 passed:'Mikrofon izni, yerel ses yakalama ve ses seviyesi kontrolü başarılı. Bu sonuç konuşma tanıma veya Gemini bağlantısını doğrulamaz.'
};

export default function NativeVoiceDeviceCheck({disabled=false,onBusyChange}:{disabled?:boolean;onBusyChange?:(busy:boolean)=>void}){
 const options=useMemo(()=>({...RecordingPresets.HIGH_QUALITY,directory:'cache' as const,isMeteringEnabled:true,numberOfChannels:1}),[]);
 const recorder=useAudioRecorder(options),status=useAudioRecorderState(recorder,100),focused=useIsFocused();
 const [phase,setPhase]=useState<Phase>('idle'),[level,setLevel]=useState(0),[result,setResult]=useState(''),[cleanupPending,setCleanupPending]=useState(false);
 const mounted=useRef(true),running=useRef(false),prepared=useRef(false),uri=useRef<string|null>(null),startedAt=useRef(0),peakDb=useRef<number|null>(null),epoch=useRef(0),timer=useRef<ReturnType<typeof setTimeout>|null>(null),busy=useRef(false),finishing=useRef<Promise<void>|null>(null),cancelRef=useRef<(message?:string)=>Promise<void>>(async()=>{});
 const busyCallback=useRef(onBusyChange);busyCallback.current=onBusyChange;
 function notifyBusy(value:boolean){if(busy.current===value)return;busy.current=value;busyCallback.current?.(value);}
 async function resetAudioMode(){await setAudioModeAsync({allowsRecording:false}).catch(()=>{});}
 async function removeTemporaryFile(path:string|null):Promise<boolean>{
  if(!path)return true;
  return removePrivateVoiceDeviceCheckFile(path,FileSystem.cacheDirectory,FileSystem);
 }
 useEffect(()=>{
  if(phase!=='testing'||typeof status.metering!=='number'||!Number.isFinite(status.metering))return;
  peakDb.current=peakDb.current===null?status.metering:Math.max(peakDb.current,status.metering);
  setLevel(voiceDeviceSignalLevel(status.metering));
 },[phase,status.metering]);
 async function finish(run:number){
  if(run!==epoch.current||!running.current)return;
  if(finishing.current)return finishing.current;
  let cleanupVerified=true;
  const work=(async()=>{
   running.current=false;
   if(timer.current){clearTimeout(timer.current);timer.current=null;}
   if(mounted.current)setPhase('finishing');
   const path=uri.current;
   let durationMs=Math.max(0,Date.now()-startedAt.current),fileBytes=0;
   try{
    if(prepared.current){await recorder.stop();prepared.current=false;}
    const finalStatus=recorder.getStatus();
    if(Number.isFinite(finalStatus.durationMillis))durationMs=Math.max(durationMs,finalStatus.durationMillis);
    if(path&&isPrivateVoiceDeviceCheckUri(path,FileSystem.cacheDirectory)){
     const info=await FileSystem.getInfoAsync(path);
     if(info.exists&&typeof info.size==='number')fileBytes=info.size;
    }
   }catch{fileBytes=0;}
   finally{
    prepared.current=false;
    cleanupVerified=await removeTemporaryFile(path);
    if(cleanupVerified)uri.current=null;
    if(mounted.current)setCleanupPending(!cleanupVerified);
    await resetAudioMode();
    notifyBusy(false);
   }
   if(run!==epoch.current||!mounted.current)return;
   const outcome=evaluateVoiceDeviceCheck({permissionGranted:true,durationMs,fileBytes,peakMeteringDb:peakDb.current,cleanupVerified});
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
  else{
   try{if(prepared.current)await recorder.stop();}catch{}
   prepared.current=false;
  }
  const cleanupVerified=await removeTemporaryFile(uri.current);
  if(cleanupVerified)uri.current=null;
  await resetAudioMode();
  notifyBusy(false);
  if(mounted.current){
   setPhase('complete');setLevel(0);setCleanupPending(!cleanupVerified);
   setResult(cleanupVerified?message:resultText.cleanup_failed);
  }
 }
 cancelRef.current=cancel;
 async function retryCleanup(){
  const path=uri.current;
  const cleaned=await removeTemporaryFile(path);
  if(cleaned){uri.current=null;setCleanupPending(false);setResult('Geçici ses dosyasının silindiği doğrulandı. Mikrofon testi yeniden başlatılabilir.');}
  else{setCleanupPending(true);setResult(resultText.cleanup_failed);}
 }
 async function start(){
  if(disabled||cleanupPending||uri.current!==null||running.current||phase==='requesting'||phase==='testing'||phase==='finishing')return;
  const run=++epoch.current;
  running.current=true;peakDb.current=null;startedAt.current=0;setLevel(0);setResult('');setCleanupPending(false);setPhase('requesting');notifyBusy(true);
  try{
   const permission=await requestRecordingPermissionsAsync();
   if(run!==epoch.current)return;
   if(!permission.granted){
    running.current=false;notifyBusy(false);setPhase('complete');setResult(resultText.permission_denied);return;
   }
   await setAudioModeAsync({allowsRecording:true,playsInSilentMode:true,shouldPlayInBackground:false});
   if(run!==epoch.current){await resetAudioMode();return;}
   await recorder.prepareToRecordAsync(options);
   prepared.current=true;
   const path=recorder.uri;
   const cache=FileSystem.cacheDirectory;
   if(!path||!cache||!path.startsWith(cache))throw Error('Geçici test kaydı uygulamanın özel önbelleğine oluşturulamadı.');
   uri.current=path;
   if(!isPrivateVoiceDeviceCheckUri(path,cache))throw Error('Geçici test kaydı özel önbellekte beklenen dosya biçiminde değil; güvenli temizleme doğrulanmadan test tamamlanmayacak.');
   if(run!==epoch.current){await cancelRef.current();return;}
   startedAt.current=Date.now();
   recorder.record();
   setPhase('testing');
   timer.current=setTimeout(()=>{void finish(run);},VOICE_DEVICE_CHECK_DURATION_MS);
  }catch(error){
   if(run!==epoch.current)return;
   running.current=false;
   const path=uri.current;
   try{if(prepared.current)await recorder.stop();}catch{}
   prepared.current=false;
   const cleanupVerified=await removeTemporaryFile(path);
   if(cleanupVerified)uri.current=null;
   await resetAudioMode();notifyBusy(false);
   if(mounted.current){setPhase('complete');setCleanupPending(!cleanupVerified);setResult(cleanupVerified?(error instanceof Error?error.message:'Mikrofon testi başlatılamadı.'):resultText.cleanup_failed);}
  }
 }
 useEffect(()=>{
  const subscription=AppState.addEventListener('change',state=>{
   if(state!=='active'&&running.current)void cancel('Uygulama arka plana geçti. Test iptal edildi ve mikrofon kapatıldı.');
  });
  return()=>subscription.remove();
 },[]);
 useEffect(()=>{if(!focused&&running.current)void cancel('Ekran değişti. Test iptal edildi ve mikrofon kapatıldı.');},[focused]);
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
   <Pressable accessibilityRole="button" disabled={disabled||busyPhase||cleanupPending} onPress={()=>void start()} style={{flex:1,backgroundColor:disabled||busyPhase||cleanupPending?'#9BA7B7':blue,borderRadius:11,padding:13,alignItems:'center'}}>
    <Text style={{color:'#FFFFFF',fontWeight:'800',textAlign:'center'}}>{buttonLabel}</Text>
   </Pressable>
   {phase==='testing'&&<Pressable accessibilityRole="button" onPress={()=>void cancel()} style={{backgroundColor:'#FEE4E2',borderRadius:11,padding:13,justifyContent:'center'}}><Text style={{color:'#B42318',fontWeight:'800'}}>Durdur</Text></Pressable>}
  </View>
  {busyPhase&&<View style={{flexDirection:'row',alignItems:'center',gap:9,marginTop:10}}><ActivityIndicator color={blue}/><Text accessibilityLiveRegion="polite" style={{color:muted}}>{phase==='testing'?'Birkaç kelime söyleyin. Test altı saniye sonra otomatik kapanır.':'Mikrofon hazırlanıyor…'}</Text></View>}
  {!!result&&<Text accessibilityLiveRegion="polite" accessibilityRole={cleanupPending?'alert':undefined} style={{color:phase==='complete'&&result===resultText.passed?'#067647':cleanupPending?'#B42318':muted,lineHeight:20,marginTop:12}}>{result}</Text>}
  {cleanupPending&&<Pressable accessibilityRole="button" disabled={disabled||busyPhase} onPress={()=>void retryCleanup()} style={{marginTop:10,borderWidth:1,borderColor:'#B42318',borderRadius:11,padding:12,alignItems:'center'}}>
   <Text style={{color:'#B42318',fontWeight:'800',textAlign:'center'}}>Geçici ses dosyasını silmeyi yeniden dene</Text>
  </Pressable>}
 </View>;
}
