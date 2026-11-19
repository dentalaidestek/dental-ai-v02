import React,{useEffect,useRef,useState} from 'react';
import {ActivityIndicator,Alert,Image,Pressable,ScrollView,StyleSheet,Text,TextInput,View} from 'react-native';
import * as Picker from 'expo-image-picker';
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import {chunkedDraftStore} from './socialDraft';
import {analysisUploadReceipt,canStartAnalysis,parseUploadIntent,UploadImage,UploadIntent,uploadAnalysis,validateUploadFields} from './analysisUpload';
import {ANALYSIS_MAX_IMAGES} from './analysisApi';
import {ANALYSIS_COMPOSER_SAFETY_NOTE,analysisComposerImageCountLabel,analysisComposerSteps} from './analysisComposerPresentation';
import type {Patient} from './api';
import {cacheAnalysisImages,clearAnalysisImages,clearLegacyAnalysisSources,cleanupStaleClinicalMediaTemps,ensureEncryptedAnalysisImages,prepareAnalysisUploadImages,validateCachedAnalysisImages} from './nativeAnalysisFiles';
const store=chunkedDraftStore(SecureStore,Crypto.randomUUID);
type Props={token:string;userId:number;patientId:number;patient?:Pick<Patient,'anonymous_id'|'age'|'chief_complaint'>|null;onCreated:(id:number)=>Promise<void>;existingMediaIds?:number[];initialToothNumber?:string;initialClinicalNotes?:string;intentScope?:'ai'|'patient-media';onExistingMediaIdsLoaded?:(ids:number[])=>void};
function storedIntent(intent:UploadIntent):UploadIntent{return {...intent,images:intent.images.map(({previewUri,...image})=>image)}}
export default function NativeAnalysisUpload({token,userId,patientId,patient,onCreated,existingMediaIds=[],initialToothNumber='',initialClinicalNotes='',intentScope='ai',onExistingMediaIdsLoaded}:Props){
 const [files,setFiles]=useState<UploadImage[]>([]),[savedIds,setSavedIds]=useState<number[]>(existingMediaIds),[tooth,setTooth]=useState(initialToothNumber),[notes,setNotes]=useState(initialClinicalNotes),[intent,setIntent]=useState<UploadIntent|null>(null),[busy,setBusy]=useState(false),[ready,setReady]=useState(false),[error,setError]=useState(''),[progress,setProgress]=useState<number|null>(null),[transferBytes,setTransferBytes]=useState({loaded:0,total:0}),[phase,setPhase]=useState(''),[notice,setNotice]=useState(''),[blocked,setBlocked]=useState(false),[blockedIntent,setBlockedIntent]=useState<UploadIntent|null>(null),[createdId,setCreatedId]=useState<number|null>(null);
 const alive=useRef(true),lock=useRef(false),abort=useRef<AbortController|null>(null),key=intentScope==='patient-media'?`dai.analysis.upload.patient-media.${userId}.${patientId}`:`dai.analysis.upload.${userId}.${patientId}`;
 useEffect(()=>{void(async()=>{
   let hadSaved=false,cleanupCompleted=false;
   try{
    await cleanupStaleClinicalMediaTemps();
    const raw=await store.getItemAsync(key);if(!alive.current)return;
    if(raw){
     hadSaved=true;
     let saved=parseUploadIntent(raw,userId,patientId);
     setBlockedIntent(saved);
     // A server receipt is authoritative even when the app crashed after
     // deleting its encrypted local files but before deleting this intent.
     // Reconcile it before touching local image storage.
     const recoveredReceipt=await analysisUploadReceipt(token,saved);
     if(recoveredReceipt){
      await clearAnalysisImages(saved.images);
      await store.deleteItemAsync(key);
      cleanupCompleted=true;
      if(!alive.current)return;
      setBlockedIntent(null);setCreatedId(recoveredReceipt.analysis_id);setIntent(null);setFiles([]);
      setReady(true);
      await onCreated(recoveredReceipt.analysis_id);
      if(alive.current)setNotice('Önceki yükleme sunucuda bulundu; mevcut analiz açıldı.');
      return;
     }
     saved={...saved,images:await ensureEncryptedAnalysisImages(saved.images,userId,patientId)};
     // Persist encrypted references before removing any legacy plaintext source.
     if(!alive.current)return;
     await store.setItemAsync(key,JSON.stringify(storedIntent(saved)));
     setBlockedIntent(saved);
     await clearLegacyAnalysisSources(saved.images);
     if(saved.images.some(image=>!!image.legacyUri)){
      saved={...saved,images:saved.images.map(({legacyUri,...image})=>image)};
      await store.setItemAsync(key,JSON.stringify(storedIntent(saved)));
     }
     if(!alive.current)return;
     setBlockedIntent(saved);setIntent(saved);setFiles(saved.images);setSavedIds(saved.existingMediaIds||[]);onExistingMediaIdsLoaded?.(saved.existingMediaIds||[]);setTooth(saved.toothNumber);setNotes(saved.clinicalNotes);
     // No server receipt exists yet; the encrypted local intent remains
     // available for an explicit same-key retry.
     setBlockedIntent(null);
    }
    if(alive.current)setReady(true);
   }catch(e){if(alive.current){if(hadSaved&&!cleanupCompleted)setBlocked(true);setReady(true);setError(e instanceof Error?e.message:'Bekleyen yükleme doğrulanamadı.');}}
  })();return()=>{alive.current=false;abort.current?.abort()}},[]);
  async function perform(work:()=>Promise<void>){if(lock.current||!alive.current)return;lock.current=true;setBusy(true);setError('');setNotice('');try{await work()}catch(e){if(alive.current)setError(e instanceof Error?e.message:'Analiz yüklemesi tamamlanamadı.')}finally{lock.current=false;if(alive.current){setBusy(false);abort.current=null}}}
 async function pick(camera:boolean){if(intent||!ready||savedIds.length+files.length>=ANALYSIS_MAX_IMAGES)return;await perform(async()=>{const permission=camera?await Picker.requestCameraPermissionsAsync():await Picker.requestMediaLibraryPermissionsAsync();if(!alive.current)return;if(!permission.granted)throw Error(camera?'Kamera izni gerekli.':'Galeri izni gerekli.');const result=camera?await Picker.launchCameraAsync({mediaTypes:['images'],quality:1}):await Picker.launchImageLibraryAsync({mediaTypes:['images'],quality:1,allowsMultipleSelection:true,selectionLimit:ANALYSIS_MAX_IMAGES-savedIds.length-files.length,orderedSelection:true});if(!alive.current||result.canceled)return;const next=await cacheAnalysisImages(result.assets.map(a=>({uri:a.uri,name:a.fileName||undefined,type:a.mimeType||undefined})),userId,patientId);if(!alive.current){await clearAnalysisImages(next);return}if(savedIds.length+files.length+next.length>ANALYSIS_MAX_IMAGES){await clearAnalysisImages(next);throw Error(`Bir analizde en fazla ${ANALYSIS_MAX_IMAGES} görüntü olabilir.`)}setFiles(old=>[...old,...next])})}
 async function recoverBlockedIntent(){
   await perform(async()=>{
    let pending=blockedIntent;
    if(pending){
     await clearLegacyAnalysisSources(pending.images);
     if(pending.images.some(image=>!!image.legacyUri)){
      pending={...pending,images:pending.images.map(({legacyUri,...image})=>image)};
      await store.setItemAsync(key,JSON.stringify(storedIntent(pending)));
      if(!alive.current)return;
      setBlockedIntent(pending);
     }
     const receipt=await analysisUploadReceipt(token,pending);
     if(!alive.current)return;
     if(receipt){
      await clearAnalysisImages(pending.images);
      await store.deleteItemAsync(key);
      if(!alive.current)return;
      setBlockedIntent(null);setBlocked(false);setIntent(null);setFiles([]);setCreatedId(receipt.analysis_id);
      setNotice('Önceki analiz sunucuda bulundu; mevcut kayıt açıldı.');
      await onCreated(receipt.analysis_id);return;
     }
    }
    Alert.alert('Eski yükleme taslağı silinsin mi?',pending?'Sunucuda yükleme fişi bulunamadı. Şifreli ve eski geçici dosyalar kaldırılacak; görüntüleri yeniden seçmeniz gerekecek.':'Taslak okunamadığı için sunucu fişi kontrol edilemedi. Hasta analiz geçmişini kontrol ettikten sonra bozuk yerel taslağı kaldırabilirsiniz.',[
     {text:'Vazgeç',style:'cancel'},
     {text:'Taslağı Sil',style:'destructive',onPress:()=>{void(async()=>{
      try{if(pending)await clearAnalysisImages(pending.images);await store.deleteItemAsync(key);if(!alive.current)return;setBlockedIntent(null);setBlocked(false);setIntent(null);setFiles([]);setError('Eski taslak kaldırıldı. Görüntüleri yeniden seçebilirsiniz.');}
      catch(e){if(alive.current)setError(e instanceof Error?e.message:'Eski taslak kaldırılamadı.');}
     })()}}
    ]);
   });
  }
  async function send(checkOnly=false){await perform(async()=>{
  setPhase('Sunucudaki mevcut yükleme kaydı kontrol ediliyor');setProgress(null);setTransferBytes({loaded:0,total:0});
  let pending=intent;
  if(!pending){
   validateUploadFields(tooth,notes);
   const encryptedImages=await ensureEncryptedAnalysisImages(files,userId,patientId);
   pending=parseUploadIntent(JSON.stringify({userId,patientId,requestKey:Crypto.randomUUID(),toothNumber:tooth.trim(),clinicalNotes:notes.trim(),existingMediaIds:savedIds,images:encryptedImages}),userId,patientId);
   await store.setItemAsync(key,JSON.stringify(storedIntent(pending)));
   if(!alive.current)return;setIntent(pending);
  }
  if(pending.images.some(image=>!!image.legacyUri)){
    await clearLegacyAnalysisSources(pending.images);
    pending={...pending,images:pending.images.map(({legacyUri,...image})=>image)};
    await store.setItemAsync(key,JSON.stringify(storedIntent(pending)));
    if(!alive.current)return;
    setIntent(pending);setFiles(pending.images);
   }
   const known=await analysisUploadReceipt(token,pending);if(!alive.current)return;
  if(!known&&checkOnly){setPhase('');setNotice('Sunucuda henüz fiş bulunamadı. İsterseniz aynı anahtar ve şifreli dosyalarla yüklemeyi sürdürebilirsiniz.');return}
  let receipt=known;
  if(!receipt){
   setPhase('Şifreli görüntüler doğrulanıyor');await validateCachedAnalysisImages(pending.images,userId,patientId);if(!alive.current)return;
   const prepared=await prepareAnalysisUploadImages(pending.images,userId,patientId);
   abort.current=new AbortController();setProgress(0);setTransferBytes({loaded:0,total:0});setPhase('Görüntüler ve klinik bilgi aktarılıyor');
   try{receipt=await uploadAnalysis(token,{...pending,images:prepared.images},(p,loaded,total)=>{if(alive.current){setProgress(p);if(Number.isFinite(loaded)&&Number.isFinite(total))setTransferBytes({loaded:Math.max(0,loaded),total:Math.max(0,total)})}},abort.current.signal)}
   catch(e){
    if(typeof e==='object'&&e!==null&&'status' in e&&[400,404,413,415,422].includes(Number(e.status))){
     await clearAnalysisImages(pending.images);await store.deleteItemAsync(key);if(alive.current){setIntent(null);setBlockedIntent(null)}
    }
    throw e;
   }finally{await prepared.cleanup()}
  }
  setPhase('Sunucu yükleme fişi doğrulandı');
  await clearAnalysisImages(pending.images);
  await store.deleteItemAsync(key);
  if(!alive.current)return;
  setCreatedId(receipt.analysis_id);setIntent(null);setBlockedIntent(null);setFiles([]);setSavedIds([]);setProgress(null);setTransferBytes({loaded:0,total:0});
  const hasMedia=(pending.existingMediaIds?.length||0)+pending.images.length>0;
  setNotice('Analiz #'+receipt.analysis_id+(hasMedia?' kaydedildi. Görüntü işleme sunucuda sürer.':' kaydedildi. Klinik ön değerlendirme sunucuda sürer.'));
  setPhase('');await onCreated(receipt.analysis_id)
 })}
 const button=(label:string,action:()=>void,disabled=false,primary=false)=><Pressable accessibilityRole="button" disabled={busy||!ready||blocked||disabled} onPress={action} style={[s.button,primary&&s.primaryButton,(busy||!ready||blocked||disabled)&&{opacity:.4}]}><Text style={[s.action,primary&&s.primaryAction]}>{label}</Text></Pressable>;
 const steps=analysisComposerSteps(savedIds.length),toothStep=steps[0]!,clinicalStep=steps[1]!,imageStep=steps[2]!;
 const imageCountLabel=analysisComposerImageCountLabel(savedIds.length,files.length);
 return (
  <View style={s.panel}>
   <Text style={s.title}>Dental AI Analizi</Text>
   {patient&&<View style={s.patientContext}>
    <Text style={s.patientIdentity}>{patient.anonymous_id||`Hasta #${patientId}`} · {patient.age===null||patient.age===undefined?'Hasta kaydı':`${patient.age} yaş`}</Text>
    <Text style={s.meta}>Ana şikâyet: {patient.chief_complaint?.trim()||'Belirtilmemiş'}</Text>
   </View>}
   <View style={s.intro}>
    <Text style={s.sectionTitle}>Klinik değerlendirme</Text>
    <Text style={s.meta}>Diş, hekim notu ve görüntüleri aynı analizde birleştirebilirsiniz.</Text>
   </View>
   <View style={s.stepBlock}>
    <View style={s.stepHeading}>
     <View style={s.stepNumber}><Text style={s.stepNumberText}>{toothStep.number}</Text></View>
     <Text style={s.stepTitle}>{toothStep.title}</Text>
    </View>
    <Text style={s.fieldLabel}>{toothStep.label}</Text>
    <TextInput accessibilityLabel={toothStep.accessibilityLabel} editable={!busy&&!intent} value={tooth} onChangeText={setTooth} maxLength={95} placeholder={toothStep.placeholder} style={s.input}/>
   </View>
   <View style={s.stepBlock}>
    <View style={s.stepHeading}>
     <View style={s.stepNumber}><Text style={s.stepNumberText}>{clinicalStep.number}</Text></View>
     <Text style={s.stepTitle}>{clinicalStep.title}</Text>
    </View>
    <Text style={s.fieldLabel}>{clinicalStep.label}</Text>
    <TextInput accessibilityLabel={clinicalStep.accessibilityLabel} editable={!busy&&!intent} value={notes} onChangeText={setNotes} maxLength={4000} multiline placeholder={clinicalStep.placeholder} style={[s.input,{minHeight:85,textAlignVertical:'top'}]}/>
    {!!clinicalStep.helper&&<Text style={s.fieldHelp}>{clinicalStep.helper}</Text>}
   </View>
   <View style={[s.stepBlock,s.lastStepBlock]}>
    <View style={s.stepHeading}>
     <View style={s.stepNumber}><Text style={s.stepNumberText}>{imageStep.number}</Text></View>
     <Text style={s.stepTitle}>{imageStep.title}</Text>
    </View>
    <Text style={s.fieldLabel}>{imageStep.label}</Text>
    {!!imageStep.helper&&<Text style={s.fieldHelp}>{imageStep.helper}</Text>}
    <Text style={s.imageCount}>{imageCountLabel}</Text>
    <View style={s.row}>
     {button('Galeriden Ekle',()=>void pick(false),!!intent||savedIds.length+files.length>=ANALYSIS_MAX_IMAGES)}
     {button('Kameradan Ekle',()=>void pick(true),!!intent||savedIds.length+files.length>=ANALYSIS_MAX_IMAGES)}
    </View>
    {files.length>0&&<ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.previewRow}>
     {files.map((f,i)=><View key={f.uri} style={s.previewItem}>
      {f.previewUri||!f.encryptedUri
       ?<Image source={{uri:f.previewUri||f.uri}} resizeMode="contain" style={s.previewImage}/>
       :<View style={s.encryptedPreview}><Text style={{fontSize:24}}>🔒</Text><Text style={s.meta}>Cihazda şifreli</Text></View>}
      <Text numberOfLines={2} style={s.meta}>{i+1}. {f.name}</Text>
      {button('Kaldır '+(i+1),()=>void perform(async()=>{await clearAnalysisImages([f]);if(alive.current)setFiles(old=>old.filter(x=>x.uri!==f.uri))}),!!intent)}
     </View>)}
    </ScrollView>}
   </View>
   <View style={s.safetyNote}><Text style={s.safetyText}>{ANALYSIS_COMPOSER_SAFETY_NOTE}</Text></View>
   {(!ready||busy)&&<ActivityIndicator/>}
   {!!phase&&<Text style={s.meta}>{phase}</Text>}
   {progress!==null&&<Text style={s.meta}>Aktarım: %{progress} · {formatBytes(transferBytes.loaded)} / {formatBytes(transferBytes.total)}. %100 aktarım, sunucu kaydının onaylandığı anlamına gelmez.</Text>}
   {!!error&&<Text accessibilityRole="alert" style={s.error}>{error}</Text>}
   {!!notice&&<Text accessibilityRole="alert" style={s.meta}>{notice}</Text>}
   {blocked&&<>
    <Text style={s.error}>Bekleyen eski yükleme dosyası doğrulanamadı. Yeni analiz başlatmadan önce sunucu fişini kontrol edin.</Text>
    <Pressable accessibilityRole="button" disabled={busy||!ready} onPress={()=>void recoverBlockedIntent()} style={[s.button,(busy||!ready)&&{opacity:.4}]}>
     <Text style={s.action}>Eski Taslağı Kontrol Et / Temizle</Text>
    </Pressable>
   </>}
   {createdId&&button('Analiz #'+createdId+' Kaydını Aç',()=>void perform(async()=>{await onCreated(createdId)}))}
   {intent
    ?<>
      <Text style={s.meta}>Bekleyen yükleme aynı hasta, dosyalar ve anahtarla korunuyor. Yeni analiz oluşturmadan önce sunucudaki kayıt kontrol edilir.</Text>
      {button('Yükleme Fişini Kontrol Et',()=>void send(true))}
      {button('Aynı Yüklemeyi Sürdür',()=>void send(false))}
     </>
    :button('Analizi Başlat',()=>void send(),!canStartAnalysis(tooth,notes,savedIds,files),true)}
   {busy&&progress!==null&&<Pressable accessibilityRole="button" onPress={()=>abort.current?.abort()} style={s.button}><Text style={s.action}>Aktarımı Durdur</Text></Pressable>}
  </View>
 );
}
function formatBytes(value:number){if(!Number.isFinite(value)||value<=0)return '0 B';if(value<1024)return `${Math.round(value)} B`;if(value<1024*1024)return `${(value/1024).toFixed(1)} KiB`;return `${(value/(1024*1024)).toFixed(1)} MiB`}
const s=StyleSheet.create({panel:{padding:14,gap:12,marginVertical:14,borderWidth:1,borderColor:'#DCE3EB',borderRadius:12,backgroundColor:'white'},patientContext:{padding:12,gap:5,borderRadius:10,backgroundColor:'#EEF3FA',borderWidth:1,borderColor:'#DCE6F2'},patientIdentity:{fontSize:14,fontWeight:'800',color:'#071B35'},title:{fontSize:20,fontWeight:'850',color:'#102033'},intro:{paddingTop:2,paddingBottom:3},sectionTitle:{fontSize:16,fontWeight:'800',color:'#172033'},stepBlock:{paddingVertical:11,borderBottomWidth:1,borderBottomColor:'rgba(15,23,42,.08)'},lastStepBlock:{borderBottomWidth:0,paddingBottom:3},stepHeading:{flexDirection:'row',alignItems:'center',gap:8,marginBottom:8},stepNumber:{width:25,height:25,borderRadius:8,backgroundColor:'#EFF6FF',alignItems:'center',justifyContent:'center'},stepNumberText:{fontSize:12,fontWeight:'850',color:'#1D4ED8'},stepTitle:{fontSize:18,fontWeight:'800',color:'#172033'},fieldLabel:{fontSize:13,fontWeight:'700',color:'#172033',marginBottom:6},fieldHelp:{fontSize:12,lineHeight:18,color:'#64748B',marginTop:6},imageCount:{fontSize:12,fontWeight:'700',color:'#53657B',marginTop:8,marginBottom:5},meta:{fontSize:13,lineHeight:21,color:'#53657B'},row:{flexDirection:'row',gap:8,flexWrap:'wrap'},button:{padding:12,minHeight:44,borderRadius:9,backgroundColor:'#E8F0FF'},primaryButton:{width:'100%',minHeight:50,borderRadius:12,backgroundColor:'#071B35',justifyContent:'center',alignItems:'center'},action:{fontWeight:'700',color:'#1769AA'},primaryAction:{fontWeight:'800',color:'#FFFFFF'},input:{padding:12,minHeight:46,borderWidth:1,borderColor:'#DCE3EB',borderRadius:9,color:'#102033',backgroundColor:'#FFFFFF'},previewRow:{paddingVertical:6},previewItem:{width:130,marginRight:10},previewImage:{width:125,height:100,borderRadius:10},safetyNote:{marginTop:2,padding:10,borderRadius:11,borderWidth:1,borderColor:'rgba(15,23,42,.08)',backgroundColor:'#FBFCFE'},safetyText:{fontSize:12,lineHeight:18,color:'#64748B'},error:{color:'#B42318',lineHeight:21},encryptedPreview:{width:125,height:100,borderRadius:10,backgroundColor:'#EEF3FA',alignItems:'center',justifyContent:'center',gap:6}});
