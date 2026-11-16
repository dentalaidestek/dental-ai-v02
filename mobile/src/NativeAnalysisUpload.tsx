import React,{useEffect,useRef,useState} from 'react';
import {ActivityIndicator,Alert,Image,Pressable,ScrollView,StyleSheet,Text,TextInput,View} from 'react-native';
import * as Picker from 'expo-image-picker';
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import {chunkedDraftStore} from './socialDraft';
import {analysisUploadReceipt,canStartAnalysis,parseUploadIntent,UploadImage,UploadIntent,uploadAnalysis,validateUploadFields} from './analysisUpload';
import {ANALYSIS_MAX_IMAGES} from './analysisApi';
import type {Patient} from './api';
import {cacheAnalysisImages,clearAnalysisImages,cleanupStaleClinicalMediaTemps,ensureEncryptedAnalysisImages,prepareAnalysisUploadImages,validateCachedAnalysisImages} from './nativeAnalysisFiles';
const store=chunkedDraftStore(SecureStore,Crypto.randomUUID);
type Props={token:string;userId:number;patientId:number;patient?:Pick<Patient,'anonymous_id'|'age'|'chief_complaint'>|null;onCreated:(id:number)=>Promise<void>;existingMediaIds?:number[];initialToothNumber?:string;initialClinicalNotes?:string;intentScope?:'ai'|'patient-media';onExistingMediaIdsLoaded?:(ids:number[])=>void};
function storedIntent(intent:UploadIntent):UploadIntent{return {...intent,images:intent.images.map(({previewUri,...image})=>image)}}
export default function NativeAnalysisUpload({token,userId,patientId,patient,onCreated,existingMediaIds=[],initialToothNumber='',initialClinicalNotes='',intentScope='ai',onExistingMediaIdsLoaded}:Props){
 const [files,setFiles]=useState<UploadImage[]>([]),[savedIds,setSavedIds]=useState<number[]>(existingMediaIds),[tooth,setTooth]=useState(initialToothNumber),[notes,setNotes]=useState(initialClinicalNotes),[intent,setIntent]=useState<UploadIntent|null>(null),[busy,setBusy]=useState(false),[ready,setReady]=useState(false),[error,setError]=useState(''),[progress,setProgress]=useState<number|null>(null),[transferBytes,setTransferBytes]=useState({loaded:0,total:0}),[phase,setPhase]=useState(''),[notice,setNotice]=useState(''),[blocked,setBlocked]=useState(false),[blockedIntent,setBlockedIntent]=useState<UploadIntent|null>(null),[createdId,setCreatedId]=useState<number|null>(null);
 const alive=useRef(true),lock=useRef(false),abort=useRef<AbortController|null>(null),key=intentScope==='patient-media'?`dai.analysis.upload.patient-media.${userId}.${patientId}`:`dai.analysis.upload.${userId}.${patientId}`;
 useEffect(()=>{void(async()=>{
  let hadSaved=false;
  try{
   await cleanupStaleClinicalMediaTemps();
   const raw=await store.getItemAsync(key);if(!alive.current)return;
   if(raw){
    hadSaved=true;
    let saved=parseUploadIntent(raw,userId,patientId);
    setBlockedIntent(saved);
    saved={...saved,images:await ensureEncryptedAnalysisImages(saved.images,userId,patientId)};
    if(!alive.current){await clearAnalysisImages(saved.images);return;}
    await store.setItemAsync(key,JSON.stringify(storedIntent(saved)));
    setBlockedIntent(null);setIntent(saved);setFiles(saved.images);setSavedIds(saved.existingMediaIds||[]);onExistingMediaIdsLoaded?.(saved.existingMediaIds||[]);setTooth(saved.toothNumber);setNotes(saved.clinicalNotes);
    const receipt=await analysisUploadReceipt(token,saved);
    if(receipt&&alive.current){
     await store.deleteItemAsync(key);await clearAnalysisImages(saved.images);if(!alive.current)return;
     setCreatedId(receipt.analysis_id);setIntent(null);setFiles([]);await onCreated(receipt.analysis_id);
     if(alive.current)setNotice('Önceki yükleme sunucuda bulundu; mevcut analiz açıldı.');
    }
   }
   if(alive.current)setReady(true);
  }catch(e){if(alive.current){if(hadSaved)setBlocked(true);setReady(true);setError(e instanceof Error?e.message:'Bekleyen yükleme doğrulanamadı.');}}
 })();return()=>{alive.current=false;abort.current?.abort()}},[]);
 async function perform(work:()=>Promise<void>){if(lock.current||!alive.current)return;lock.current=true;setBusy(true);setError('');setNotice('');try{await work()}catch(e){if(alive.current)setError(e instanceof Error?e.message:'Analiz yüklemesi tamamlanamadı.')}finally{lock.current=false;if(alive.current){setBusy(false);abort.current=null}}}
 async function pick(camera:boolean){if(intent||!ready||savedIds.length+files.length>=ANALYSIS_MAX_IMAGES)return;await perform(async()=>{const permission=camera?await Picker.requestCameraPermissionsAsync():await Picker.requestMediaLibraryPermissionsAsync();if(!alive.current)return;if(!permission.granted)throw Error(camera?'Kamera izni gerekli.':'Galeri izni gerekli.');const result=camera?await Picker.launchCameraAsync({mediaTypes:['images'],quality:1}):await Picker.launchImageLibraryAsync({mediaTypes:['images'],quality:1,allowsMultipleSelection:true,selectionLimit:ANALYSIS_MAX_IMAGES-savedIds.length-files.length,orderedSelection:true});if(!alive.current||result.canceled)return;const next=await cacheAnalysisImages(result.assets.map(a=>({uri:a.uri,name:a.fileName||undefined,type:a.mimeType||undefined})),userId,patientId);if(!alive.current){await clearAnalysisImages(next);return}if(savedIds.length+files.length+next.length>ANALYSIS_MAX_IMAGES){await clearAnalysisImages(next);throw Error(`Bir analizde en fazla ${ANALYSIS_MAX_IMAGES} görüntü olabilir.`)}setFiles(old=>[...old,...next])})}
 async function recoverBlockedIntent(){
  await perform(async()=>{
   const pending=blockedIntent;
   if(pending){
    const receipt=await analysisUploadReceipt(token,pending);
    if(!alive.current)return;
    if(receipt){
     await store.deleteItemAsync(key);await clearAnalysisImages(pending.images);if(!alive.current)return;
     setBlockedIntent(null);setBlocked(false);setIntent(null);setFiles([]);setCreatedId(receipt.analysis_id);
     setNotice('Önceki analiz sunucuda bulundu; mevcut kayıt açıldı.');
     await onCreated(receipt.analysis_id);return;
    }
   }
   Alert.alert('Eski yükleme taslağı silinsin mi?',pending?'Sunucuda yükleme fişi bulunamadı. Eksik yerel dosyalar kaldırılacak; görüntüleri yeniden seçmeniz gerekecek.':'Taslak okunamadığı için sunucu fişi kontrol edilemedi. Hasta analiz geçmişini kontrol ettikten sonra bozuk yerel taslağı kaldırabilirsiniz.',[
    {text:'Vazgeç',style:'cancel'},
    {text:'Taslağı Sil',style:'destructive',onPress:()=>{void(async()=>{
     try{await store.deleteItemAsync(key);if(pending)await clearAnalysisImages(pending.images);if(!alive.current)return;setBlockedIntent(null);setBlocked(false);setIntent(null);setFiles([]);setError('Eski taslak kaldırıldı. Görüntüleri yeniden seçebilirsiniz.');}
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
     await store.deleteItemAsync(key);await clearAnalysisImages(pending.images);if(alive.current)setIntent(null);
    }
    throw e;
   }finally{await prepared.cleanup()}
  }
  setPhase('Sunucu yükleme fişi doğrulandı');await store.deleteItemAsync(key);if(!alive.current)return;
  setCreatedId(receipt.analysis_id);setIntent(null);setFiles([]);setSavedIds([]);setProgress(null);setTransferBytes({loaded:0,total:0});
  const hasMedia=(pending.existingMediaIds?.length||0)+pending.images.length>0;
  setNotice('Analiz #'+receipt.analysis_id+(hasMedia?' kaydedildi. Görüntü işleme sunucuda sürer.':' kaydedildi. Klinik ön değerlendirme sunucuda sürer.'));
  await clearAnalysisImages(pending.images);if(alive.current){setPhase('');await onCreated(receipt.analysis_id)}
 })}
 const button=(label:string,action:()=>void,disabled=false)=><Pressable accessibilityRole="button" disabled={busy||!ready||blocked||disabled} onPress={action} style={[s.button,(busy||!ready||blocked||disabled)&&{opacity:.4}]}><Text style={s.action}>{label}</Text></Pressable>;
 return <View style={s.panel}><Text style={s.title}>Dental AI Analizi</Text>{patient&&<View style={s.patientContext}><Text style={s.patientIdentity}>{patient.anonymous_id||`Hasta #${patientId}`} · {patient.age===null||patient.age===undefined?'Hasta kaydı':`${patient.age} yaş`}</Text><Text style={s.meta}>Ana şikâyet: {patient.chief_complaint?.trim()||'Belirtilmemiş'}</Text></View>}<Text style={s.title}>Görüntüler ve Klinik Bilgi</Text><Text style={s.meta}>Görüntü olmadan da diş numarası veya klinik bilgiyle ön değerlendirme başlatabilirsiniz.</Text><Text style={s.meta}>{savedIds.length?`${savedIds.length} kayıtlı klinik görüntü seçildi · `:''}Kayıtlı ve yeni görüntüler birlikte en fazla {ANALYSIS_MAX_IMAGES} JPG/PNG/WebP olabilir. Yeni dosyaların her biri en fazla 15 MiB; yeni dosyaların toplamı en fazla 48 MiB. Kayıtlı görüntüler dört görüntülük seçim sınırına dahildir ancak yeniden yüklenmez.</Text><View style={s.row}>{button('Galeriden Ekle',()=>void pick(false),!!intent||savedIds.length+files.length>=ANALYSIS_MAX_IMAGES)}{button('Kameradan Ekle',()=>void pick(true),!!intent||savedIds.length+files.length>=ANALYSIS_MAX_IMAGES)}</View>{(savedIds.length>0||files.length>0)&&<Text style={s.meta}>Toplam: {savedIds.length+files.length} / {ANALYSIS_MAX_IMAGES} görüntü</Text>}{files.length>0&&<ScrollView horizontal>{files.map((f,i)=><View key={f.uri} style={{width:130,marginRight:10}}>{f.previewUri||!f.encryptedUri?<Image source={{uri:f.previewUri||f.uri}} resizeMode="contain" style={{width:125,height:100}}/>:<View style={s.encryptedPreview}><Text style={{fontSize:24}}>🔒</Text><Text style={s.meta}>Cihazda şifreli</Text></View>}<Text style={s.meta}>{i+1}. {f.name}</Text>{button('Kaldır '+(i+1),()=>{setFiles(old=>old.filter(x=>x.uri!==f.uri));void clearAnalysisImages([f])},!!intent)}</View>)}</ScrollView>}<TextInput accessibilityLabel="Analiz FDI diş numaraları" editable={!busy&&!intent} value={tooth} onChangeText={setTooth} maxLength={95} placeholder="Diş numarası: 36 veya 36,46 (isteğe bağlı)" style={s.input}/><TextInput accessibilityLabel="Analiz klinik bilgileri" editable={!busy&&!intent} value={notes} onChangeText={setNotes} maxLength={4000} multiline placeholder="Şikâyet, anamnez ve klinik bulgular (isteğe bağlı)" style={[s.input,{minHeight:85}]}/>{(!ready||busy)&&<ActivityIndicator/>}{!!phase&&<Text accessibilityRole="status" style={s.meta}>{phase}</Text>}{progress!==null&&<Text accessibilityRole="status" style={s.meta}>Aktarım: %{progress} · {formatBytes(transferBytes.loaded)} / {formatBytes(transferBytes.total)}. %100 aktarım, sunucu kaydının onaylandığı anlamına gelmez.</Text>}{!!error&&<Text accessibilityRole="alert" style={s.error}>{error}</Text>}{!!notice&&<Text accessibilityRole="alert" style={s.meta}>{notice}</Text>}{blocked&&<><Text style={s.error}>Bekleyen eski yükleme dosyası doğrulanamadı. Yeni analiz başlatmadan önce sunucu fişini kontrol edin.</Text><Pressable accessibilityRole="button" disabled={busy||!ready} onPress={()=>void recoverBlockedIntent()} style={[s.button,(busy||!ready)&&{opacity:.4}]}><Text style={s.action}>Eski Taslağı Kontrol Et / Temizle</Text></Pressable></>}{createdId&&button('Analiz #'+createdId+' Kaydını Aç',()=>void perform(async()=>{await onCreated(createdId)}))}{intent?<><Text style={s.meta}>Bekleyen yükleme aynı hasta, dosyalar ve anahtarla korunuyor. Yeni analiz oluşturmadan önce sunucudaki kayıt kontrol edilir.</Text>{button('Yükleme Fişini Kontrol Et',()=>void send(true))}{button('Aynı Yüklemeyi Sürdür',()=>void send(false))}</>:button('Analizi Başlat',()=>void send(),!canStartAnalysis(tooth,notes,savedIds,files))}{busy&&progress!==null&&<Pressable accessibilityRole="button" onPress={()=>abort.current?.abort()} style={s.button}><Text style={s.action}>Aktarımı Durdur</Text></Pressable>}</View>
}
function formatBytes(value:number){if(!Number.isFinite(value)||value<=0)return '0 B';if(value<1024)return `${Math.round(value)} B`;if(value<1024*1024)return `${(value/1024).toFixed(1)} KiB`;return `${(value/(1024*1024)).toFixed(1)} MiB`}
const s=StyleSheet.create({panel:{padding:14,gap:12,marginVertical:14,borderWidth:1,borderColor:'#DCE3EB',borderRadius:12,backgroundColor:'white'},patientContext:{padding:12,gap:5,borderRadius:10,backgroundColor:'#EEF3FA',borderWidth:1,borderColor:'#DCE6F2'},patientIdentity:{fontSize:14,fontWeight:'800',color:'#071B35'},title:{fontSize:17,fontWeight:'800',color:'#102033'},meta:{fontSize:13,lineHeight:21,color:'#53657B'},row:{flexDirection:'row',gap:8,flexWrap:'wrap'},button:{padding:12,minHeight:44,borderRadius:9,backgroundColor:'#E8F0FF'},action:{fontWeight:'700',color:'#1769AA'},input:{padding:12,minHeight:46,borderWidth:1,borderColor:'#DCE3EB',borderRadius:9,color:'#102033'},error:{color:'#B42318',lineHeight:21},encryptedPreview:{width:125,height:100,borderRadius:10,backgroundColor:'#EEF3FA',alignItems:'center',justifyContent:'center',gap:6}});
