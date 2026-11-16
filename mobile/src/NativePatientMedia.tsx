import React,{useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {ActivityIndicator,Alert,AppState,FlatList,Image,Modal,Pressable,ScrollView,Text,TextInput,View} from 'react-native';
import {useIsFocused} from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import * as FS from 'expo-file-system/legacy';
import {getPatientMediaUpload,uploadPatientMedia} from './api';
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import {chunkedDraftStore} from './socialDraft';
import {deleteAllPatientMedia,deleteMedia,getMedia} from './modernApi';
import NativeAnalysisUpload from './NativeAnalysisUpload';
import {cleanupOrphanedClinicalMediaVaultFiles,cleanupStaleClinicalMediaTemps,deleteClinicalMediaTemp,deleteClinicalMediaVaultFile,decryptClinicalMediaFile,encryptClinicalMediaFile,isClinicalMediaVaultUri,validateClinicalMediaVaultFile} from './clinicalMediaVault';
import {useRealtime} from './realtime';
import {CLINICAL_MEDIA_PICKER_MAX_FILES,normalizeClinicalMediaAssets} from './clinicalMediaPicker';
import {CLINICAL_MEDIA_BATCH_ID_PATTERN,ensureClinicalMediaBatchId} from './clinicalMediaBatch';
import {ANALYSIS_MAX_IMAGES} from './analysisApi';
import {CLINICAL_MEDIA_MAX_BATCH_BYTES,CLINICAL_MEDIA_MAX_FILE_BYTES} from './uploadLimits';

type Picked={uri:string;encryptedUri?:string;previewUri?:string;name:string;type:string;requestKey:string};
type PendingUpload={version:1|2|3;batchId?:string;userId:number;patientId:number;mediaType:'PHOTO'|'RADIOGRAPH';files:Picked[];updatedAt:number};
function storedPending(value:PendingUpload):PendingUpload{return {...value,files:value.files.map(({previewUri,...file})=>file)}}
const uploadKeyFor=(userId:number,patientId:number)=>`dai.patient-media.upload.${userId}.${patientId}`;
function parsePendingUpload(raw:string|null,userId:number,patientId:number):PendingUpload|null{
 if(!raw)return null;
 let value:any;try{value=JSON.parse(raw)}catch{throw Error('Bekleyen klinik görüntü taslağı okunamadı.')}
 if(!value||(value.version!==1&&value.version!==2&&value.version!==3)||value.userId!==userId||value.patientId!==patientId||!['PHOTO','RADIOGRAPH'].includes(value.mediaType)||!Array.isArray(value.files)||value.files.length<1||value.files.length>CLINICAL_MEDIA_PICKER_MAX_FILES||!Number.isFinite(value.updatedAt)||value.batchId!==undefined&&(typeof value.batchId!=='string'||!CLINICAL_MEDIA_BATCH_ID_PATTERN.test(value.batchId))||value.files.some((file:any)=>!file||typeof file.uri!=='string'||!file.uri||typeof file.name!=='string'||!file.name||typeof file.type!=='string'||!['image/jpeg','image/png','image/webp'].includes(file.type)||typeof file.requestKey!=='string'||!/^[A-Za-z0-9_-]{16,96}$/.test(file.requestKey)||file.encryptedUri!==undefined&&(typeof file.encryptedUri!=='string'||file.encryptedUri!==file.uri||!isClinicalMediaVaultUri(file.encryptedUri,userId,patientId)))||new Set(value.files.map((file:any)=>file.requestKey)).size!==value.files.length)
  throw Error('Bekleyen klinik görüntü taslağı doğrulanamadı. Yeni yükleme başlatılmadı.');
 if((value.version===2||value.version===3)&&value.files.some((file:any)=>!file.encryptedUri))
  throw Error('Şifreli klinik görüntü taslağı eksik. Yeni yükleme başlatılmadı.');
 return {...value,files:value.files.map(({previewUri,...file}:any)=>file)} as PendingUpload;
}
export default function NativePatientMedia({token,userId,patientId,onAnalysis}:{token:string;userId:number;patientId:number;onAnalysis:(id:number)=>void}){
 const uploadStore=useMemo(()=>chunkedDraftStore(SecureStore,Crypto.randomUUID,300),[]);
 const uploadKey=uploadKeyFor(userId,patientId),focused=useIsFocused();
 const {lastEvent}=useRealtime(),[items,setItems]=useState<any[]>([]),[cursor,setCursor]=useState<number|null>(null),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[open,setOpen]=useState(false),[preview,setPreview]=useState<any>(null),[selected,setSelected]=useState<number[]>([]),[pending,setPending]=useState<Picked[]>([]),[pendingBatchId,setPendingBatchId]=useState(''),[mediaType,setMediaType]=useState<'PHOTO'|'RADIOGRAPH'>('PHOTO'),[progress,setProgress]=useState(''),[uncertain,setUncertain]=useState(false),[zoom,setZoom]=useState(1),[uploadReady,setUploadReady]=useState(false),[uploadBlocked,setUploadBlocked]=useState(false),[byteProgress,setByteProgress]=useState({loaded:0,total:0,lengthComputable:false});
 const [loadedOwner,setLoadedOwner]=useState('');const [pendingOwner,setPendingOwner]=useState(''),[toothNumber,setToothNumber]=useState(''),[clinicalNotes,setClinicalNotes]=useState(''),[composeOpen,setComposeOpen]=useState(false),[composeIds,setComposeIds]=useState<number[]>([]),[composeTooth,setComposeTooth]=useState(''),[composeNotes,setComposeNotes]=useState('');
 const mounted=useRef(true),request=useRef(0),pickerGeneration=useRef(0),loadLock=useRef(false),mutation=useRef(false),scope=useRef(`${userId}:${token}:${patientId}`);const owner=`${userId}:${token}:${patientId}`;scope.current=owner;
 const current=()=>mounted.current&&scope.current===owner;
 const load=useCallback(async(more=false)=>{if(loadLock.current||(more&&(mutation.current||uncertain||loadedOwner!==owner)))return;loadLock.current=true;const sequence=++request.current;setLoading(true);try{const page=await getMedia(token,patientId,more?cursor??undefined:undefined);if(!current()||sequence!==request.current)return;setItems(previous=>more?[...previous,...page.items.filter(x=>!previous.some(y=>y.id===x.id))]:page.items);setCursor(page.next_before);setLoadedOwner(owner);setError('');if(!more){setSelected([]);setPreview(null);setZoom(1)}}catch(e){if(current()&&sequence===request.current){if(!more){setItems([]);setCursor(null);setSelected([]);setPreview(null);setZoom(1)}setLoadedOwner(owner);setError(e instanceof Error?e.message:'Görseller alınamadı.')}}finally{if(current()&&sequence===request.current){loadLock.current=false;setLoading(false)}}},[token,patientId,cursor,uncertain,loadedOwner]);
 const loader=useRef(load);loader.current=load;
 useEffect(()=>{mounted.current=true;request.current++;pickerGeneration.current++;loadLock.current=false;mutation.current=false;setBusy(false);setOpen(false);setComposeOpen(false);setComposeIds([]);setComposeTooth('');setComposeNotes('');setLoading(false);setItems([]);setCursor(null);setLoadedOwner('');setError('');setSelected([]);setPreview(null);setPending([]);setPendingBatchId('');setPendingOwner('');setToothNumber('');setClinicalNotes('');setUncertain(false);setProgress('');setByteProgress({loaded:0,total:0,lengthComputable:false});setUploadReady(false);setUploadBlocked(false);let active=true;void(async()=>{try{await cleanupStaleClinicalMediaTemps();const raw=await uploadStore.getItemAsync(uploadKey);const saved=parsePendingUpload(raw,userId,patientId);if(saved&&active&&current()){const batchId=ensureClinicalMediaBatchId(saved.batchId,Crypto.randomUUID);const version=saved.files.every(file=>!!file.encryptedUri)?3:1;const migrated:PendingUpload={...saved,version,batchId};await uploadStore.setItemAsync(uploadKey,JSON.stringify(storedPending(migrated)));if(!active||!current())return;setPendingBatchId(batchId);setPending(saved.files);setMediaType(saved.mediaType);setPendingOwner(owner);setProgress(`Önceki oturumdan ${saved.files.length} bekleyen klinik görüntü bulundu.`)}if(active&&current())await cleanupOrphanedClinicalMediaVaultFiles(userId,patientId,saved?.files.flatMap(file=>file.encryptedUri?[file.encryptedUri]:[])??[])}catch(e){if(active&&current()){setUploadBlocked(true);setError(e instanceof Error?e.message:'Güvenli klinik görüntü taslağı okunamadı.')}}finally{if(active&&current())setUploadReady(true)}})();return()=>{active=false;mounted.current=false;request.current++;pickerGeneration.current++;loadLock.current=false}},[token,userId,patientId,uploadKey]);
 useEffect(()=>{if(!focused)return;void loader.current();const listener=AppState.addEventListener('change',state=>{if(state==='active'&&focused)void loader.current()});return()=>listener.remove()},[focused,owner]);
 useEffect(()=>{if(lastEvent&&['PATIENT_MEDIA_CREATED','PATIENT_MEDIA_DELETED'].includes(String(lastEvent.event_type||lastEvent.type))&&Number(lastEvent.payload?.patient_id||lastEvent.entity_id)===patientId&&!mutation.current)void loader.current()},[lastEvent,patientId]);
 const visibleItems=loadedOwner===owner?items:[];
 const button=(label:string,action:()=>void,disabled=false)=><Pressable accessibilityRole="button" disabled={disabled} onPress={action} style={{padding:12,minHeight:44,opacity:disabled?.5:1}}><Text style={{color:'#1769AA',fontWeight:'700'}}>{label}</Text></Pressable>;
 async function pick(type:'PHOTO'|'RADIOGRAPH'){
  if(!current()||mutation.current||uncertain||!uploadReady||uploadBlocked||pending.length)return;
  const picker=++pickerGeneration.current;
  try{
   const permission=await ImagePicker.requestMediaLibraryPermissionsAsync();
   if(!current()||picker!==pickerGeneration.current||mutation.current||uncertain)return;
   if(!permission.granted){setError('Klinik görüntü seçmek için fotoğraf izni gerekli.');return}
   const result=await ImagePicker.launchImageLibraryAsync({mediaTypes:['images'],allowsMultipleSelection:true,quality:.9,selectionLimit:CLINICAL_MEDIA_PICKER_MAX_FILES});
   if(!current()||picker!==pickerGeneration.current||mutation.current||uncertain||result.canceled)return;
   if(!result.assets.length||result.assets.length>CLINICAL_MEDIA_PICKER_MAX_FILES)throw Error(`Tek seferde en fazla ${CLINICAL_MEDIA_PICKER_MAX_FILES} klinik görüntü seçebilirsiniz.`);
   const rawFiles:Picked[]=normalizeClinicalMediaAssets(result.assets).map(asset=>({...asset,requestKey:Crypto.randomUUID()}));
   const batchId=ensureClinicalMediaBatchId(undefined,Crypto.randomUUID);
   mutation.current=true;setBusy(true);setError('');setProgress('Görüntüler cihazda şifreleniyor…');
   const encrypted:Picked[]=[];let batchBytes=0;
   try{
    for(const file of rawFiles){
     const encryptedUri=await encryptClinicalMediaFile(file.uri,userId,patientId,CLINICAL_MEDIA_MAX_FILE_BYTES);
     encrypted.push({...file,uri:encryptedUri,encryptedUri,previewUri:file.uri});
     const encryptedInfo=await FS.getInfoAsync(encryptedUri);
     const plainBytes=encryptedInfo.exists&&Number.isFinite(encryptedInfo.size)?encryptedInfo.size-40:0;
     if(plainBytes<1||plainBytes>CLINICAL_MEDIA_MAX_FILE_BYTES)throw Error('Klinik görüntünün gerçek boyutu doğrulanamadı veya 12 MiB sınırını aşıyor.');
     batchBytes+=plainBytes;
     if(batchBytes>CLINICAL_MEDIA_MAX_BATCH_BYTES)throw Error('Tek klinik arşiv yüklemesinde toplam boyut en fazla 96 MiB olabilir.');
     if(!current()||picker!==pickerGeneration.current){await Promise.all(encrypted.map(item=>deleteClinicalMediaVaultFile(item.encryptedUri!).catch(()=>{})));return;}
    }
    const intent:PendingUpload={version:3,batchId,userId,patientId,mediaType:type,files:encrypted,updatedAt:Date.now()};
    await uploadStore.setItemAsync(uploadKey,JSON.stringify(storedPending(intent)));
    if(!current()||picker!==pickerGeneration.current){await Promise.all(encrypted.map(item=>deleteClinicalMediaVaultFile(item.encryptedUri!).catch(()=>{})));return;}
    setMediaType(type);setPendingBatchId(batchId);setPendingOwner(owner);setPending(encrypted);setError('');setProgress('Şifreli yükleme taslağı kaydedildi.');setByteProgress({loaded:0,total:0,lengthComputable:false});
   }catch(error){
    await Promise.all(encrypted.map(item=>deleteClinicalMediaVaultFile(item.encryptedUri!).catch(()=>{})));
    throw error;
   }finally{if(current()){mutation.current=false;setBusy(false)}}
  }catch(e){if(current()&&picker===pickerGeneration.current)setError(e instanceof Error?e.message:'Görüntüler seçilemedi.')}
 }
async function savePending(files:Picked[]){
  if(files.length){
   const batchId=ensureClinicalMediaBatchId(pendingBatchId,Crypto.randomUUID);
   const version=files.every(file=>!!file.encryptedUri)?3:1;
   await uploadStore.setItemAsync(uploadKey,JSON.stringify(storedPending({version,batchId,userId,patientId,mediaType,files,updatedAt:Date.now()})));
  }else await uploadStore.deleteItemAsync(uploadKey);
  await cleanupOrphanedClinicalMediaVaultFiles(userId,patientId,files.flatMap(file=>file.encryptedUri?[file.encryptedUri]:[]));
 }
async function upload(reconcile=false){
  if(!current()||mutation.current||(uncertain&&!reconcile)||pendingOwner!==owner||!pending.length||!uploadReady||uploadBlocked||!CLINICAL_MEDIA_BATCH_ID_PATTERN.test(pendingBatchId))return;
  mutation.current=true;setBusy(true);setError('');setByteProgress({loaded:0,total:0,lengthComputable:false});
  const files=[...pending];let remaining=[...files],completed=0;
  try{
   for(const original of files){
    if(!current())return;
    setProgress(completed+' / '+files.length+' görüntü doğrulandı');
    const receipt=await getPatientMediaUpload(token,patientId,original.requestKey);
    if(!current())return;
    let file=original;
    if(!receipt.found){
     if(!file.encryptedUri){
      const encryptedUri=await encryptClinicalMediaFile(file.uri,userId,patientId,12*1024*1024);
      file={...file,uri:encryptedUri,encryptedUri};
      remaining=remaining.map(item=>item.requestKey===file.requestKey?file:item);
      await savePending(remaining);if(!current())return;setPending(remaining);
     }
     await validateClinicalMediaVaultFile(file.encryptedUri!,userId,patientId,12*1024*1024);
     const tempUri=await decryptClinicalMediaFile(file.encryptedUri!,userId,patientId,file.name);
     try{
      await uploadPatientMedia(token,patientId,{uri:tempUri,name:file.name,type:file.type},undefined,mediaType,file.requestKey,pendingBatchId,value=>{if(current())setByteProgress(value)});
     }finally{await deleteClinicalMediaTemp(tempUri).catch(()=>{});}
    }
    if(!current())return;
    completed++;remaining=remaining.filter(item=>item.requestKey!==file.requestKey);
    await savePending(remaining);if(!current())return;setPending(remaining);
    if(file.encryptedUri)await deleteClinicalMediaVaultFile(file.encryptedUri).catch(()=>{});
    setProgress(completed+' / '+files.length+' görüntü kaydedildi');setByteProgress({loaded:0,total:0,lengthComputable:false});
   }
   if(!remaining.length){setPendingOwner('');setPendingBatchId('');setUncertain(false);setProgress(completed+' görüntü kaydedildi');}
   await loader.current();
  }catch(e){
   if(current()){
    const code=(e as {code?:string})?.code;
    const localFailure=['SOURCE_MISSING','VAULT_MISSING','KEY_MISSING','KEY_INVALID','AUTH_FAILED','INVALID_VAULT'].includes(String(code||''));
    const status=(e as {status?:number})?.status;
    const definiteRejection=typeof status==='number'&&[400,413,422,403,404].includes(status);
    setUncertain(!localFailure&&!definiteRejection);
    setError((e instanceof Error?e.message:'Yükleme tamamlanamadı.')+(localFailure?' Sunucuya yeni dosya gönderilmedi; bekleyen taslağı ve sunucu fişini kontrol edip eksik görüntüyü yeniden seçebilirsiniz.':definiteRejection?' Sunucu yeni kaydı kabul etmedi. Yükleme grubunu temizleyip daha küçük bir grup seçebilirsiniz.':' Aynı işlem anahtarları güvenli taslakta korundu; devam ettiğinizde sunucu fişleri kontrol edilerek eksik dosyalar yüklenir.'));
    void loader.current();
   }
  }finally{if(current()){mutation.current=false;setBusy(false)}}
 }
async function clearPending(){
  if(!current()||mutation.current||uncertain||pendingOwner!==owner||!pending.length||!uploadReady)return;
  mutation.current=true;setBusy(true);setError('');
  try{
   const found:Picked[]=[];
   for(const file of pending){const receipt=await getPatientMediaUpload(token,patientId,file.requestKey);if(!current())return;if(receipt.found)found.push(file);}
   if(found.length){
    const remaining=pending.filter(file=>!found.some(saved=>saved.requestKey===file.requestKey));
    await savePending(remaining);if(!current())return;setPending(remaining);
    await Promise.all(found.filter(file=>file.encryptedUri).map(file=>deleteClinicalMediaVaultFile(file.encryptedUri!).catch(()=>{})));
    setProgress(found.length+' görüntünün sunucu kaydı bulundu; yeniden yüklenmedi.');
    if(!remaining.length){setPendingOwner('');setPendingBatchId('');}
    await loader.current();return;
   }
   await Promise.all(pending.filter(file=>file.encryptedUri).map(file=>deleteClinicalMediaVaultFile(file.encryptedUri!).catch(()=>{})));
   await uploadStore.deleteItemAsync(uploadKey);if(!current())return;
   setPending([]);setPendingBatchId('');setPendingOwner('');setProgress('Bekleyen taslak kaldırıldı.');setError('');
  }catch(e){if(current())setError((e instanceof Error?e.message:'Sunucu fişleri kontrol edilemedi.')+' Taslak korunuyor; bağlantı geldiğinde yeniden kontrol edin.')}
  finally{if(current()){mutation.current=false;setBusy(false)}}
 }
async function remove(id?:number){if(!current()||mutation.current||uncertain||loadedOwner!==owner)return;mutation.current=true;setBusy(true);try{if(id)await deleteMedia(token,patientId,id);else await deleteAllPatientMedia(token,patientId);if(!current())return;setPreview(null);setSelected([]);await loader.current()}catch(e){if(current()){setUncertain(true);setError((e instanceof Error?e.message:'Silme durumu doğrulanamadı.')+' Silme isteği uygulanmış olabilir; tekrar denemeden önce galeriyi kontrol edin.');void loader.current()}}finally{if(current()){mutation.current=false;setBusy(false)}}}
 function confirmDelete(id?:number){if(!current()||mutation.current||uncertain||loadedOwner!==owner)return;Alert.alert(id?'Görsel silinsin mi?':'Tüm görseller silinsin mi?','Bu işlem geri alınamaz.',[{text:'Vazgeç',style:'cancel'},{text:'Sil',style:'destructive',onPress:()=>void remove(id)}])}
 async function analyze(){if(!current()||mutation.current||uncertain||loadedOwner!==owner||!selected.length)return;setComposeIds([...selected]);setComposeTooth(toothNumber);setComposeNotes(clinicalNotes);setComposeOpen(true);setOpen(false)}
 function toggle(id:number){if(!current()||mutation.current||uncertain||loadedOwner!==owner||!visibleItems.some(item=>item.id===id))return;setSelected(previous=>previous.includes(id)?previous.filter(x=>x!==id):previous.length<ANALYSIS_MAX_IMAGES?[...previous,id]:previous)}
 return <View><Text style={{color:'#718096',fontSize:11,fontWeight:'800'}}>KLİNİK ARŞİV</Text><Text style={{fontSize:20,fontWeight:'800',color:'#102033',marginTop:5}}>Klinik Görseller</Text><Text style={{color:'#53657B',marginVertical:8}}>Fotoğraf ve röntgenleri bu hastanın profilinde saklayın.</Text><View style={{flexDirection:'row',flexWrap:'wrap'}}>{button('▦ Röntgen Ekle',()=>void pick('RADIOGRAPH'),busy||uncertain||!uploadReady||uploadBlocked||pending.length>0)}{button('▧ Fotoğraf Ekle',()=>void pick('PHOTO'),busy||uncertain||!uploadReady||uploadBlocked||pending.length>0)}</View>{pendingOwner===owner&&pending.length>0&&<View><Text style={{color:'#53657B'}}>{pending.length} {mediaType==='RADIOGRAPH'?'röntgen':'fotoğraf'} seçildi · güvenli taslakta</Text><ScrollView horizontal>{pending.map(file=><View key={file.requestKey} style={{width:82,height:82,margin:4,borderRadius:8,backgroundColor:'#EEF3FA',alignItems:'center',justifyContent:'center'}}>{file.previewUri||!file.encryptedUri?<Image source={{uri:file.previewUri||file.uri}} style={{width:72,height:72,borderRadius:8}}/>:<><Text style={{fontSize:22}}>🔒</Text><Text style={{fontSize:10,color:'#53657B'}}>Şifreli</Text></>}</View>)}</ScrollView>{button(uncertain?'Bekleyen yüklemeyi güvenle doğrula':'Kaydet',()=>void upload(uncertain),busy||!uploadReady||uploadBlocked)}{!busy&&!uncertain&&button('Seçimi kaldır',()=>void clearPending())}</View>}{!!progress&&<Text style={{color:'#53657B'}}>{progress}</Text>}{uploadBlocked&&<Text accessibilityRole="alert" style={{color:'#B42318'}}>Güvenli taslak okunamadı. Bu oturumda klinik görüntü yüklemesi engellendi.</Text>}{busy&&byteProgress.lengthComputable&&byteProgress.total>0&&<View style={{gap:5,marginVertical:6}}><View style={{height:7,backgroundColor:'#E8EEF5',borderRadius:8,overflow:'hidden'}}><View style={{height:7,width:(Math.min(100,Math.round(byteProgress.loaded/byteProgress.total*100)))+'%',backgroundColor:'#1769AA',borderRadius:8}}/></View><Text style={{color:'#53657B',fontSize:12}}>{Math.min(100,Math.round(byteProgress.loaded/byteProgress.total*100))}% · {Math.ceil(byteProgress.loaded/1024)} / {Math.ceil(byteProgress.total/1024)} KB</Text></View>}{busy&&<ActivityIndicator/>}{!!error&&<Text accessibilityRole="alert" style={{color:'#B42318',marginVertical:8}}>{error}</Text>}
 <Pressable accessibilityRole="button" accessibilityLabel="Klinik görselleri aç" accessibilityState={{disabled:loadedOwner!==owner}} onPress={()=>{if(!current()||loadedOwner!==owner||mutation.current||uncertain)return;setOpen(true);void loader.current()}}><View style={{flexDirection:'row',gap:6,marginTop:10}}>{visibleItems.slice(0,3).map(item=><Image key={item.id} source={{uri:item.url,headers:{Authorization:'Bearer '+token}}} style={{flex:1,height:90,borderRadius:10}}/>)}</View><Text style={{color:'#53657B',fontSize:12,marginTop:8}}>{selected.length} / {ANALYSIS_MAX_IMAGES} AI analiz görüntüsü seçildi</Text><Text style={{color:'#1769AA',paddingVertical:12}} >{visibleItems.length?`${visibleItems.length}${cursor?'+':''} klinik görsel · Tümünü aç ›`:loading||loadedOwner!==owner?'Görseller yükleniyor…':error?'Galeri yeniden dene':'Henüz fotoğraf veya röntgen kaydedilmedi.'}</Text></Pressable>
 <Modal visible={open&&loadedOwner===owner} onRequestClose={()=>preview?setPreview(null):setOpen(false)}><View style={{flex:1,paddingTop:40,backgroundColor:'white'}}><View style={{flexDirection:'row',justifyContent:'space-between',paddingHorizontal:10}}><Text style={{fontSize:20,fontWeight:'800',padding:12,color:'#102033'}}>{preview?'Klinik görsel':'Klinik Görseller'}</Text>{button(preview?'Geri':'Kapat ✕',()=>preview?setPreview(null):setOpen(false))}</View>{preview?<ScrollView contentContainerStyle={{padding:16}}><Text style={{color:'#102033',fontWeight:'700'}}>{preview.media_type==='RADIOGRAPH'?'Röntgen':'Klinik fotoğraf'} · {preview.uploaded_at?new Date(preview.uploaded_at).toLocaleString('tr-TR'):''}</Text><Text style={{color:'#53657B'}}>{preview.tooth_number?`Diş ${preview.tooth_number}`:''}{preview.note?` · ${preview.note}`:''}</Text><View style={{flexDirection:'row'}}>{button('−',()=>setZoom(z=>Math.max(1,z-.5)))}{button('＋',()=>setZoom(z=>Math.min(4,z+.5)))}</View><ScrollView horizontal><Image resizeMode="contain" source={{uri:preview.url,headers:{Authorization:'Bearer '+token}}} style={{width:320*zoom,height:400*zoom}}/></ScrollView>{button('Görseli Sil',()=>confirmDelete(preview.id),busy||uncertain)}</ScrollView>:<><View style={{flexDirection:'row',flexWrap:'wrap',paddingHorizontal:10}}>{button(selected.length?'Seçimi kaldır':`İlk ${ANALYSIS_MAX_IMAGES} Görseli Seç`,()=>{if(!current()||mutation.current||uncertain||loadedOwner!==owner)return;setSelected(selected.length?[]:visibleItems.slice(0,ANALYSIS_MAX_IMAGES).map(x=>x.id))},busy||uncertain||loadedOwner!==owner)}{button('⋮ Tüm Görselleri Sil',()=>confirmDelete(),busy||uncertain||visibleItems.length===0)}</View><Text style={{paddingHorizontal:22,color:'#53657B'}}>{selected.length} seçili · Sunucu bir analizde en fazla {ANALYSIS_MAX_IMAGES} görüntü kabul ediyor.</Text><View style={{paddingHorizontal:16,gap:7}}><Text style={{color:'#102033',fontWeight:'700'}}>Diş numarası (isteğe bağlı)</Text><TextInput accessibilityLabel="Klinik görsel analizi FDI diş numarası" value={toothNumber} onChangeText={setToothNumber} editable={!busy&&!uncertain} maxLength={10} placeholder="Örn: 36 veya 36,46" style={{borderWidth:1,borderColor:'#DCE3EB',borderRadius:9,padding:11,color:'#102033'}}/><Text style={{color:'#102033',fontWeight:'700',marginTop:5}}>Kısa klinik bilgi (isteğe bağlı)</Text><TextInput accessibilityLabel="Klinik görsel analizi klinik bilgisi" value={clinicalNotes} onChangeText={setClinicalNotes} editable={!busy&&!uncertain} maxLength={4000} multiline placeholder="Şikâyet, anamnez ve klinik bulgular" style={{borderWidth:1,borderColor:'#DCE3EB',borderRadius:9,padding:11,minHeight:78,textAlignVertical:'top',color:'#102033'}}/></View>{button('Seçilenleri AI ile Analiz Et',()=>void analyze(),busy||uncertain||!selected.length)}{!!error&&<Text accessibilityRole="alert" style={{paddingHorizontal:22,color:'#B42318'}}>{error}</Text>}{!loading&&!!error&&button('Galeriyi yeniden yükle',()=>void loader.current(),busy)}{!loading&&!error&&items.length===0&&<Text style={{padding:22,color:'#53657B'}}>Bu hastaya ait klinik görsel bulunmuyor.</Text>}<FlatList data={visibleItems} numColumns={2} keyExtractor={item=>String(item.id)} contentContainerStyle={{padding:12}} refreshing={loading} onRefresh={()=>{if(!mutation.current&&!uncertain&&loadedOwner===owner)void loader.current()}} onEndReached={()=>{if(loadedOwner===owner&&cursor&&!loading&&!error&&!uncertain&&!mutation.current)void loader.current(true)}} renderItem={({item})=><View style={{width:'50%',padding:5}}><Pressable accessibilityRole="button" onPress={()=>{if(!current()||loadedOwner!==owner||mutation.current||uncertain)return;setPreview(item);setZoom(1)}}><Image source={{uri:item.url,headers:{Authorization:'Bearer '+token}}} style={{height:130,borderRadius:10}}/><Text style={{color:'#53657B'}}>{item.media_type==='RADIOGRAPH'?'Röntgen':'Fotoğraf'}</Text></Pressable><Pressable accessibilityRole="checkbox" accessibilityState={{checked:selected.includes(item.id)}} disabled={busy||uncertain} onPress={()=>toggle(item.id)} style={{padding:12}}><Text style={{color:'#1769AA'}}>{selected.includes(item.id)?'☑ Seçili':'☐ Analiz için seç'}</Text></Pressable></View>} ListFooterComponent={cursor?button('Diğer görseller',()=>void loader.current(true),loading):null}/></>}</View></Modal><Modal visible={composeOpen&&loadedOwner===owner} onRequestClose={()=>{setComposeOpen(false);setOpen(true)}}><View style={{flex:1,paddingTop:40,backgroundColor:'#F5F7FB'}}><View style={{flexDirection:'row',alignItems:'center',justifyContent:'space-between',paddingHorizontal:16,paddingBottom:10}}><View style={{flex:1}}><Text style={{fontSize:20,fontWeight:'800',color:'#102033'}}>Dental AI Analizi</Text><Text style={{fontSize:13,color:'#53657B'}}>{composeIds.length} / {ANALYSIS_MAX_IMAGES} kayıtlı görüntü · yeni görüntülerle birlikte toplam sınır {ANALYSIS_MAX_IMAGES}</Text></View><Pressable accessibilityRole="button" onPress={()=>{setComposeOpen(false);setOpen(true)}} style={{padding:12}}><Text style={{color:'#1769AA',fontWeight:'800'}}>Geri</Text></Pressable></View><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{padding:14,paddingBottom:36}}><Text style={{color:'#102033',fontWeight:'700',marginBottom:8}}>Seçtiğiniz kayıtlı klinik görüntüler</Text><ScrollView horizontal>{composeIds.map(id=>{const item=visibleItems.find(value=>value.id===id);return <View key={id} style={{width:112,marginRight:8}}>{item?<Image source={{uri:item.url,headers:{Authorization:'Bearer '+token}}} resizeMode="cover" style={{width:104,height:90,borderRadius:10}}/>:<View style={{width:104,height:90,borderRadius:10,backgroundColor:'#E8EEF5',alignItems:'center',justifyContent:'center'}}><Text style={{color:'#53657B'}}>Kayıtlı #{id}</Text></View>}<Text style={{fontSize:11,color:'#53657B'}}>{item?.media_type==='RADIOGRAPH'?'Röntgen':item?'Fotoğraf':'Bekleyen görüntü' } · #{id}</Text></View>})}</ScrollView><NativeAnalysisUpload key={owner} token={token} userId={userId} patientId={patientId} existingMediaIds={composeIds} intentScope="patient-media" onExistingMediaIdsLoaded={ids=>{if(current())setComposeIds(ids)}} initialToothNumber={composeTooth} initialClinicalNotes={composeNotes} onCreated={async id=>{if(!current())return;setComposeOpen(false);setSelected([]);onAnalysis(id)}}/></ScrollView></View></Modal></View>;
}
