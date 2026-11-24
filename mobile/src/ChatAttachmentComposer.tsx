import React,{useEffect,useImperativeHandle,useRef,useState} from "react";
import {ActivityIndicator,Image,Pressable,Text,View} from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";
import {ChatFile,validateChatFile} from "./chatFiles";
import {getConsultationMessageReceipt,sendChatFile} from "./modernApi";
import {isMissingApiRoute404} from "./apiCompatibility";
import type {ChatMessage} from "./modernApi";
import NativeImageEditor from "./NativeImageEditor";

function Button({title,onPress,disabled=false}:{title:string;onPress:()=>void;disabled?:boolean}){return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={{padding:12,minHeight:44,opacity:disabled ? 0.5 : 1}}><Text style={{color:"#071B35",fontWeight:"700"}}>{title}</Text></Pressable>}

type QueueItem={file:ChatFile;id:string};
type PendingItem={id:string;type:string;size:number|null};
type StoredBatch={version:2;scope:string;replyTo:number|null;items:PendingItem[]};
export type ChatComposerHandle={sendAll:(text:string)=>Promise<{sentFiles:number;textConsumed:boolean}>;queueCount:()=>number};

function freshId(){return "native-media-"+Crypto.randomUUID()}
const sameKind=(value:PendingItem,file:ChatFile)=>value.type===file.type&&(value.size===null||file.size===undefined||value.size===file.size);

type Props={token:string;userId:number;caseId:number;replyTo:number|null;disabled:boolean;onSent:(message?:ChatMessage)=>Promise<void>;onRefresh:()=>Promise<void>;prepared?:{file:ChatFile;nonce:string}|null;deleted?:boolean;optionsOpen?:boolean;onQueueChange?:(count:number,busy:boolean)=>void};

const ChatAttachmentComposer=React.forwardRef<ChatComposerHandle,Props>(function ChatAttachmentComposer({token,userId,caseId,replyTo,disabled,onSent,onRefresh,prepared,deleted=false,optionsOpen=true,onQueueChange},ref){
 const [files,setFiles]=useState<QueueItem[]>([]),[batch,setBatch]=useState<StoredBatch|null>(null),[busy,setBusy]=useState(false),[restoring,setRestoring]=useState(true),[restoreAttempt,setRestoreAttempt]=useState(0),[recoveryBlocked,setRecoveryBlocked]=useState(false),[uncertain,setUncertain]=useState(false),[error,setError]=useState(""),[editing,setEditing]=useState<number|null>(null);
 const scope=useRef(token+":"+userId+":"+caseId);scope.current=token+":"+userId+":"+caseId;
 const lock=useRef(false),active=useRef(true),filesRef=useRef<QueueItem[]>([]),recordRef=useRef<StoredBatch|null>(null);
 const pendingKey="dai.consultation.media."+userId+"."+caseId;
 filesRef.current=files;
 useEffect(()=>{onQueueChange?.(files.length,busy)},[files.length,busy,onQueueChange]);
 useEffect(()=>{active.current=true;return()=>{active.current=false}},[]);
 useEffect(()=>()=>{for(const item of filesRef.current){if(item.file.owned)void FileSystem.deleteAsync(item.file.uri,{idempotent:true}).catch(()=>{})}},[]);
 useEffect(()=>{
  let live=true;
  setRestoring(true);setFiles([]);filesRef.current=[];setBusy(false);setUncertain(false);setRecoveryBlocked(false);setError("");setEditing(null);setBatch(null);recordRef.current=null;lock.current=false;
  if(deleted){
   void SecureStore.deleteItemAsync(pendingKey).catch(()=>{}).finally(()=>{if(live)setRestoring(false)});
   return()=>{live=false};
  }
  void SecureStore.getItemAsync(pendingKey).then(async raw=>{
   if(!live||!raw)return;
   let value:any=null;try{value=JSON.parse(raw)}catch{}
   const scopeOk=!!value&&value.scope===userId+":"+caseId&&(value.replyTo===null||Number.isSafeInteger(value.replyTo)&&value.replyTo>0);
   const items:PendingItem[]=value?.version===1&&scopeOk&&typeof value.id==="string"&&/^[A-Za-z0-9_-]{16,96}$/.test(value.id)&&typeof value.type==="string"
    ?[{id:value.id,type:value.type,size:Number.isFinite(value.size)?value.size:null}]
    :value?.version===2&&scopeOk&&Array.isArray(value.items)?value.items.filter((entry:any)=>entry&&typeof entry.id==="string"&&/^[A-Za-z0-9_-]{16,96}$/.test(entry.id)&&typeof entry.type==="string").map((entry:any)=>({id:entry.id,type:entry.type,size:Number.isFinite(entry.size)?entry.size:null}))
    :[];
   if(!scopeOk||!items.length){
    setRecoveryBlocked(true);
    setError("Bekleyen ek kaydı okunamadı. Kayıt temizlenene kadar yeni gönderim kilitli.");
    return;
   }
   const recovered:StoredBatch={version:2,scope:value.scope,replyTo:value.replyTo,items};
   recordRef.current=recovered;setBatch(recovered);
   try{
    const probes=await Promise.allSettled(items.map(entry=>getConsultationMessageReceipt(token,caseId,entry.id)));
    if(!live)return;
    if(probes.some(probe=>probe.status==="rejected"&&isMissingApiRoute404(probe.reason))){
     setRecoveryBlocked(true);
     setError("Sunucu ek makbuz rotasını henüz desteklemiyor (404). Ekler cihazda güvende.");
     return;
    }
    const delivered=new Set<string>();
    probes.forEach((probe,index)=>{if(probe.status==="fulfilled"&&(probe.value.message||probe.value.deleted))delivered.add(items[index].id)});
    const remaining=items.filter(entry=>!delivered.has(entry.id));
    if(delivered.size)await onSent(undefined);
    if(remaining.length!==items.length){
     const next:StoredBatch={...recovered,items:remaining};
     recordRef.current=next.items.length?next:null;setBatch(next.items.length?next:null);
     await (next.items.length?SecureStore.setItemAsync(pendingKey,JSON.stringify(next)):SecureStore.deleteItemAsync(pendingKey).catch(()=>{}));
    }
    if(remaining.length&&!live)return;
    if(remaining.length)setUncertain(true);
   }catch{
    if(live)setUncertain(true);
   }
  }).catch(()=>{
   if(live){setRecoveryBlocked(true);setError("Bekleyen ek kaydı okunamadı. Yeni gönderim için kaydı yeniden kontrol edin.")};
  }).finally(()=>{if(live)setRestoring(false)});
  return()=>{live=false};
 },[token,userId,caseId,pendingKey,deleted,restoreAttempt]);
 useEffect(()=>{if(prepared){try{select(prepared.file);setEditing(null)}catch(e){setError(e instanceof Error?e.message:"Dosya hazırlanamadı.")}}},[prepared?.nonce]);
 useEffect(()=>{if(deleted){setFiles([]);filesRef.current=[];setBatch(null);recordRef.current=null;setUncertain(false);void SecureStore.deleteItemAsync(pendingKey).catch(()=>{})}},[deleted,pendingKey]);
 useEffect(()=>()=>{if(editing!==null&&files[editing]?.file.owned)void FileSystem.deleteAsync(files[editing].file.uri,{idempotent:true}).catch(()=>{})},[editing]);
 const current=(owner:string)=>active.current&&owner===scope.current;
 async function persist(next:StoredBatch|null){
  recordRef.current=next;setBatch(next);
  if(next&&next.items.length)await SecureStore.setItemAsync(pendingKey,JSON.stringify(next));
  else await SecureStore.deleteItemAsync(pendingKey).catch(()=>{});
 }
 function select(value:ChatFile){
  const checked=validateChatFile(value);
  const waiting=(recordRef.current?.items||[]);
  const bind=waiting.findIndex(entry=>sameKind(entry,checked));
  if(waiting.length&&bind<0)throw Error("Bekleyen ek gönderimini tamamlamak için aynı tür ve boyutta dosyayı yeniden seçin.");
  const id=bind>=0?waiting[bind].id:freshId();
  if(bind>=0)void persist({...recordRef.current!,items:waiting.filter((_,index)=>index!==bind)});
  setFiles(previous=>[...previous,{file:checked,id}]);
  setError("");
 }
 function removeAt(index:number){
  const item=files[index];if(!item)return;
  if(item.file.owned)void FileSystem.deleteAsync(item.file.uri,{idempotent:true}).catch(()=>{});
  setFiles(previous=>previous.filter((_,position)=>position!==index));
  if(editing===index)setEditing(null);else if(editing!==null&&editing>index)setEditing(editing-1);
 }
 async function choose(camera=false){
  if(lock.current||restoring||recoveryBlocked||disabled)return;const owner=scope.current;
  try{const permission=camera?await ImagePicker.requestCameraPermissionsAsync():await ImagePicker.requestMediaLibraryPermissionsAsync();if(!current(owner))return;
   if(!permission.granted){setError(camera?"Kamera izni gerekli.":"Galeri izni gerekli.");return}
   const result=camera?await ImagePicker.launchCameraAsync({mediaTypes:["images"],quality:.9}):await ImagePicker.launchImageLibraryAsync({mediaTypes:["images"],quality:.9,allowsMultipleSelection:true});
   if(!current(owner)||result.canceled)return;
   for(const asset of result.assets){
    if(!current(owner))break;
    const type=asset.mimeType||"image/jpeg",extension=type==="image/png"?".png":type==="image/webp"?".webp":".jpg";
    try{select({uri:asset.uri,name:"klinik-goruntu"+extension,type,size:asset.fileSize})}catch(e){if(current(owner))setError(e instanceof Error?e.message:"Görsel eklenemedi.");break}
   }
  }catch(e){if(current(owner))setError(e instanceof Error?e.message:"Görsel seçilemedi.")}
 }
 async function chooseFile(){
  if(lock.current||restoring||recoveryBlocked||disabled)return;const owner=scope.current;
  try{const result=await DocumentPicker.getDocumentAsync({type:["application/pdf","audio/*"],multiple:false,copyToCacheDirectory:true});
   if(result.canceled)return;const asset=result.assets[0];if(!current(owner)){if(asset?.uri)await FileSystem.deleteAsync(asset.uri,{idempotent:true});return}
   if(!asset)return;try{select({uri:asset.uri,name:asset.name,type:asset.mimeType||"application/octet-stream",size:asset.size,owned:true})}catch(e){await FileSystem.deleteAsync(asset.uri,{idempotent:true});throw e}
  }catch(e){if(current(owner))setError(e instanceof Error?e.message:"Dosya seçilemedi.")}
 }
 useImperativeHandle(ref,()=>({
  queueCount:()=>filesRef.current.length,
  async sendAll(text:string){
   if(lock.current||restoring||recoveryBlocked||disabled)return{sentFiles:0,textConsumed:false};
   const caption=(text||"").trim();
   if(caption.length>4000){setError("Ek mesajı 4000 karakteri aşamaz.");return{sentFiles:0,textConsumed:false}}
   const queue=filesRef.current;
   if(!queue.length)return{sentFiles:0,textConsumed:false};
   if(uncertain){setError("Önce bekleyen gönderimin sonucunu kontrol edin.");return{sentFiles:0,textConsumed:false}}
   lock.current=true;const owner=scope.current;setBusy(true);setError("");
   let sent=0,consumed=false;
   try{
    const recordedIds=new Set((recordRef.current?.items||[]).map(entry=>entry.id));
    const missing=queue.filter(entry=>!recordedIds.has(entry.id)).map(entry=>({id:entry.id,type:entry.file.type,size:entry.file.size??null}));
    if(missing.length||!recordRef.current)await persist({version:2,scope:userId+":"+caseId,replyTo,items:[...(recordRef.current?.items||[]),...missing]});
    for(let index=0;index<queue.length;index++){
     const item=queue[index];
     try{
      const result=await sendChatFile(token,caseId,item.file,index===0?(replyTo??undefined):undefined,item.id,index===0?caption:undefined);
      if(!result?.message?.id)throw Error("Ek gönderimi doğrulanamadı.");
      sent++;if(index===0&&caption)consumed=true;
      const remaining=(recordRef.current?.items||[]).filter(entry=>entry.id!==item.id);
      await persist(remaining.length?{version:2,scope:userId+":"+caseId,replyTo:recordRef.current?.replyTo??replyTo,items:remaining}:null);
      if(!current(owner))return{sentFiles:sent,textConsumed:consumed};
      setFiles(previous=>previous.filter(entry=>entry.id!==item.id));
      setUncertain(false);
      await onSent(result.message);
     }catch(sendError){
      let delivered=false,route404=false;
      try{const receipt=await getConsultationMessageReceipt(token,caseId,item.id);delivered=!!(receipt.message||receipt.deleted)}catch(probeError){route404=isMissingApiRoute404(probeError)}
      if(current(owner)&&delivered){
       sent++;if(index===0&&caption)consumed=true;
       const remaining=(recordRef.current?.items||[]).filter(entry=>entry.id!==item.id);
       await persist(remaining.length?{version:2,scope:userId+":"+caseId,replyTo:recordRef.current?.replyTo??replyTo,items:remaining}:null);
       setFiles(previous=>previous.filter(entry=>entry.id!==item.id));
       continue;
      }
      if(current(owner)){
       if(isMissingApiRoute404(sendError)||route404){
        setRecoveryBlocked(true);
        setError("Sunucu ek gönderimini henüz desteklemiyor (404). Ekler cihazda güvende.");
       }else{
        setUncertain(true);
        setError((sendError instanceof Error?sendError.message:"Ek gönderilemedi.")+" Kalan ekler listede; tekrar deneyebilirsiniz.");
        void onRefresh();
       }
      }
      return{sentFiles:sent,textConsumed:consumed};
     }
    }
    return{sentFiles:sent,textConsumed:consumed};
   }finally{if(current(owner)){lock.current=false;setBusy(false)}}
  }
 }),[files,batch,restoring,recoveryBlocked,uncertain,disabled,replyTo,token,caseId,userId]);
 async function probePending(){
  const items=recordRef.current?.items||[];
  if(!items.length){setUncertain(false);setError("");return}
  try{
   const probes=await Promise.allSettled(items.map(entry=>getConsultationMessageReceipt(token,caseId,entry.id)));
   if(probes.some(probe=>probe.status==="rejected"&&isMissingApiRoute404(probe.reason))){setRecoveryBlocked(true);setError("Sunucu ek makbuz rotasını henüz desteklemiyor (404).");return}
   const delivered=new Set<string>();
   probes.forEach((probe,index)=>{if(probe.status==="fulfilled"&&(probe.value.message||probe.value.deleted))delivered.add(items[index].id)});
   const remaining=items.filter(entry=>!delivered.has(entry.id));
   await persist(remaining.length?{version:2,scope:userId+":"+caseId,replyTo:recordRef.current?.replyTo??replyTo,items:remaining}:null);
   if(delivered.size)await onSent(undefined);
   if(!remaining.length){setUncertain(false);setError("")}
   else setError("Sunucuda henüz makbuz yok; aynı anahtarla tekrar deneyebilirsiniz.");
  }catch{setError("Makbuz kontrol edilemedi.")}
 }
 const showQueue=files.length>0;
 if(!optionsOpen&&!showQueue&&!error&&!recoveryBlocked&&!uncertain&&!(busy||restoring))return null;
 return <View style={{paddingHorizontal:12,paddingBottom:8}}>{optionsOpen&&<View style={{flexDirection:"row",flexWrap:"wrap"}}><Button title={restoring?"Bekleyen ek kontrol ediliyor…":"＋ Fotoğraf"} disabled={restoring||recoveryBlocked||busy||disabled} onPress={()=>void choose()}/><Button title="Kamera" disabled={restoring||recoveryBlocked||busy||disabled} onPress={()=>void choose(true)}/><Button title="PDF / Ses" disabled={restoring||recoveryBlocked||busy||disabled} onPress={()=>void chooseFile()}/></View>}
 {showQueue&&<View style={{borderWidth:1,borderColor:"#DCE3EB",borderRadius:14,backgroundColor:"white",padding:10}}>
  <View style={{flexDirection:"row",flexWrap:"wrap",gap:8}}>
   {files.map((item,index)=>{
    const image=item.file.type.startsWith("image/");
    return <View key={item.id} style={{width:64}}>
     {image?<Image source={{uri:item.file.uri}} resizeMode="cover" style={{width:64,height:64,borderRadius:12}}/>:<View style={{width:64,height:64,borderRadius:12,backgroundColor:"#EEF3F8",alignItems:"center",justifyContent:"center"}}><Text style={{fontSize:24}}>{item.file.type.startsWith("audio/")?"🎙":"📄"}</Text></View>}
     <Pressable accessibilityRole="button" accessibilityLabel={item.file.name+" ekini kaldır"} disabled={busy||restoring} onPress={()=>removeAt(index)} style={{position:"absolute",right:-6,top:-6,width:24,height:24,alignItems:"center",justifyContent:"center",borderRadius:12,backgroundColor:"#10233F"}}><Text style={{fontSize:14,color:"white"}}>×</Text></Pressable>
     {image&&<Pressable accessibilityRole="button" disabled={busy||disabled} onPress={()=>setEditing(index)} style={{marginTop:4}}><Text style={{fontSize:10,fontWeight:"800",color:"#071B35"}}>✎ Düzenle</Text></Pressable>}
    </View>;
   })}
  </View>
  <Text style={{color:"#63748A",fontSize:12,marginTop:8}}>{files.length===1?"Ek, gönder butonuyla gönderilir.":files.length+" ek sırayla gönderilir; yazdığın metin ilk ekin mesajına yazılır."}</Text>
 </View>}
 {(recordRef.current?.items.length||0)>0&&!showQueue&&!recoveryBlocked&&<Text style={{color:"#63748A",padding:8}}>Bekleyen ek gönderimi var. Kalan ekleri aynı tür ve boyutta yeniden seçin; aynı anahtarla güvenle tamamlanır.</Text>}
 {(busy||restoring)&&<ActivityIndicator/>}{restoring&&<Text style={{color:"#63748A",padding:8}}>Bekleyen ek kaydı kontrol ediliyor…</Text>}
 {recoveryBlocked&&<Button title="Bekleyen kaydı yeniden kontrol et" disabled={restoring} onPress={()=>setRestoreAttempt(value=>value+1)}/>}
 {!!error&&<Text style={{color:"#B42318"}}>{error}</Text>}
 {uncertain&&<><Button title="Sonucu kontrol et" onPress={()=>void probePending()}/><Button title="Son mesajları yenile" onPress={()=>void onRefresh()}/></>}
 {editing!==null&&files[editing]&&files[editing].file.type.startsWith("image/")&&<NativeImageEditor source={{uri:files[editing].file.uri}} visible={editing!==null} onClose={()=>setEditing(null)} onPrepared={value=>{if(active.current){try{select(value)}catch{}setEditing(null)}}}/>}
 </View>;
});
export default ChatAttachmentComposer;
