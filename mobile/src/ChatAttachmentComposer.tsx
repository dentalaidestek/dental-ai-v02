import React,{useEffect,useRef,useState} from "react";
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
export default function ChatAttachmentComposer({token,userId,caseId,replyTo,disabled,onSent,onRefresh,prepared,deleted=false,optionsOpen=true}:{token:string;userId:number;caseId:number;replyTo:number|null;disabled:boolean;onSent:(message?:ChatMessage)=>Promise<void>;onRefresh:()=>Promise<void>;prepared?:{file:ChatFile;nonce:string}|null;deleted?:boolean;optionsOpen?:boolean}){
 const [file,setFile]=useState<ChatFile|null>(null),[busy,setBusy]=useState(false),[restoring,setRestoring]=useState(true),[restoreAttempt,setRestoreAttempt]=useState(0),[recoveryBlocked,setRecoveryBlocked]=useState(false),[uncertain,setUncertain]=useState(false),[error,setError]=useState(""),[editing,setEditing]=useState(false),[pendingId,setPendingId]=useState<string|null>(null),[pendingMeta,setPendingMeta]=useState<{id:string;scope:string;replyTo:number|null;type:string;size:number|null;createdAt:number}|null>(null);
 const scope=useRef(token+":"+userId+":"+caseId);scope.current=token+":"+userId+":"+caseId;const lock=useRef(false),active=useRef(true),pendingKey="dai.consultation.media."+userId+"."+caseId;
 useEffect(()=>{active.current=true;return()=>{active.current=false}},[]);
 useEffect(()=>{
  let live=true;
  setRestoring(true);setFile(null);setBusy(false);setUncertain(false);setRecoveryBlocked(false);setError("");setEditing(false);setPendingId(null);setPendingMeta(null);lock.current=false;
  if(deleted){
   void SecureStore.deleteItemAsync(pendingKey).catch(()=>{}).finally(()=>{if(live)setRestoring(false)});
   return()=>{live=false};
  }
  void SecureStore.getItemAsync(pendingKey).then(async raw=>{
   if(!live||!raw)return;
   let value:any=null;try{value=JSON.parse(raw)}catch{}
   const valid=!!value&&value.version===1&&typeof value.id==="string"&&/^[A-Za-z0-9_-]{16,96}$/.test(value.id)&&value.scope===userId+":"+caseId&&typeof value.type==="string"&&(value.replyTo===null||Number.isSafeInteger(value.replyTo)&&value.replyTo>0);
   if(!valid){
    setRecoveryBlocked(true);
    setError("Bekleyen ek kaydı doğrulanamadı. Güvenlik için yeni gönderim kilitlendi; kaydı silmeyin.");
    return;
   }
   setPendingId(value.id);setPendingMeta({id:value.id,scope:value.scope,replyTo:value.replyTo,type:value.type,size:Number.isFinite(value.size)?value.size:null,createdAt:Number(value.createdAt)||Date.now()});
   try{
    const receipt=await getConsultationMessageReceipt(token,caseId,value.id);
    if(!live)return;
    if(receipt.deleted||receipt.message){
     await SecureStore.deleteItemAsync(pendingKey).catch(()=>{});
     if(!live)return;
     setPendingId(null);setPendingMeta(null);setFile(null);await onSent(receipt.message||undefined);
    }
   }catch(receiptError){
    if(live&&isMissingApiRoute404(receiptError)){
     setRecoveryBlocked(true);
     setError("Sunucu vaka eki gönderim/makbuz API rotasını desteklemiyor (404). Bekleyen ek güvenli taslakta korunuyor; sunucu güncellenene kadar yeni ek göndermeyin.");
    }
   }
  }).catch(()=>{
   if(live){setRecoveryBlocked(true);setError("Bekleyen ek kaydı okunamadı. Güvenlik için yeni gönderim kilitlendi; tekrar kontrol edin.")};
  }).finally(()=>{if(live)setRestoring(false)});
  return()=>{live=false};
 },[token,userId,caseId,pendingKey,deleted,restoreAttempt]);
 useEffect(()=>{if(prepared){try{select(prepared.file);setEditing(false)}catch(e){setError(e instanceof Error?e.message:"Dosya hazırlanamadı.")}}},[prepared?.nonce]);
 useEffect(()=>{if(pendingMeta&&file&&(file.type!==pendingMeta.type||(pendingMeta.size!==null&&file.size!==undefined&&file.size!==pendingMeta.size))){setFile(null);setError("Bekleyen ek gönderimini tamamlamak için aynı dosyayı yeniden seçin.")}},[pendingMeta,file]);
 useEffect(()=>{if(deleted){setFile(null);setPendingId(null);setPendingMeta(null);setUncertain(false);void SecureStore.deleteItemAsync(pendingKey).catch(()=>{})}},[deleted,pendingKey]);
 useEffect(()=>()=>{if(file?.owned)void FileSystem.deleteAsync(file.uri,{idempotent:true}).catch(()=>{})},[file?.uri]);
 const current=(owner:string)=>active.current&&owner===scope.current;
 function select(value:ChatFile){const checked=validateChatFile(value);if(pendingMeta&&(checked.type!==pendingMeta.type||(pendingMeta.size!==null&&checked.size!==undefined&&checked.size!==pendingMeta.size)))throw Error("Bekleyen ek gönderimini tamamlamak için aynı dosyayı yeniden seçin.");setFile(checked);setError("")}
 async function choose(camera=false){
  if(lock.current||restoring||recoveryBlocked||disabled||uncertain)return;const owner=scope.current;
  try{const permission=camera?await ImagePicker.requestCameraPermissionsAsync():await ImagePicker.requestMediaLibraryPermissionsAsync();if(!current(owner))return;
   if(!permission.granted){setError(camera?"Kamera izni gerekli.":"Galeri izni gerekli.");return}
   const result=camera?await ImagePicker.launchCameraAsync({mediaTypes:["images"],quality:.9}):await ImagePicker.launchImageLibraryAsync({mediaTypes:["images"],quality:.9,allowsMultipleSelection:false});
   if(!current(owner)||result.canceled||!result.assets[0])return;
   const asset=result.assets[0],type=asset.mimeType||"image/jpeg",extension=type==="image/png"?".png":type==="image/webp"?".webp":".jpg";
   select({uri:asset.uri,name:"klinik-goruntu"+extension,type,size:asset.fileSize});
  }catch(e){if(current(owner))setError(e instanceof Error?e.message:"Görsel seçilemedi.")}
 }
 async function chooseFile(){
  if(lock.current||restoring||recoveryBlocked||disabled||uncertain)return;const owner=scope.current;
  try{const result=await DocumentPicker.getDocumentAsync({type:["application/pdf","audio/*"],multiple:false,copyToCacheDirectory:true});
   if(result.canceled)return;const asset=result.assets[0];if(!current(owner)){if(asset?.uri)await FileSystem.deleteAsync(asset.uri,{idempotent:true});return}
   if(!asset)return;try{select({uri:asset.uri,name:asset.name,type:asset.mimeType||"application/octet-stream",size:asset.size,owned:true})}catch(e){await FileSystem.deleteAsync(asset.uri,{idempotent:true});throw e}
  }catch(e){if(current(owner))setError(e instanceof Error?e.message:"Dosya seçilemedi.")}
 }
 async function send(){
  if(!file||lock.current||restoring||recoveryBlocked||disabled||uncertain)return;lock.current=true;const owner=scope.current;setBusy(true);setError("");
  const intent=pendingMeta||{id:"native-media-"+Crypto.randomUUID(),scope:userId+":"+caseId,replyTo,type:file.type,size:file.size??null,createdAt:Date.now()};
  if(intent.scope!==userId+":"+caseId){setError("Bekleyen ek başka bir hesap veya görüşmeye ait.");setBusy(false);lock.current=false;return}
  try{
   if(!pendingMeta){await SecureStore.setItemAsync(pendingKey,JSON.stringify({version:1,...intent}));if(!current(owner))return;setPendingId(intent.id);setPendingMeta(intent)}
   const result=await sendChatFile(token,caseId,file,intent.replyTo??undefined,intent.id);
   if(!current(owner))return;
   if(!result?.message?.id)throw Error("Ek gönderimi doğrulanamadı.");
   await SecureStore.deleteItemAsync(pendingKey).catch(()=>{});setPendingId(null);setPendingMeta(null);setFile(null);setUncertain(false);await onSent(result.message);
  }catch(e){
   if(current(owner)){
    let receiptFailure:unknown=null;
    try{
     const receipt=await getConsultationMessageReceipt(token,caseId,intent.id);
     if(current(owner)&&(receipt.deleted||receipt.message)){
      await SecureStore.deleteItemAsync(pendingKey).catch(()=>{});
      setPendingId(null);setPendingMeta(null);setFile(null);await onSent(receipt.message||undefined);return;
     }
    }catch(receiptError){receiptFailure=receiptError}
    if(current(owner)){
     if(isMissingApiRoute404(e)||isMissingApiRoute404(receiptFailure)){
      setRecoveryBlocked(true);
      setError("Sunucu vaka eki gönderim/makbuz API rotasını desteklemiyor (404). Bekleyen dosya ve aynı istek anahtarı güvenli alanda korunuyor; sunucu güncellenene kadar yeni ek göndermeyin.");
     }else{
      setUncertain(false);
      setError((e instanceof Error?e.message:"Ek gönderilemedi.")+" Aynı dosya ve istek anahtarı korunuyor; tekrar deneyebilirsiniz.");
      void onRefresh();
     }
    }
   }
  }finally{if(current(owner)){lock.current=false;setBusy(false)}}
 }
 const image=!!file?.type.startsWith("image/");
 if(!optionsOpen&&!file&&!pendingId&&!error&&!recoveryBlocked&&!uncertain&&!(busy||restoring))return null;
 return <View style={{paddingHorizontal:12,paddingBottom:8}}>{optionsOpen&&<View style={{flexDirection:"row",flexWrap:"wrap"}}><Button title={restoring?"Bekleyen ek kontrol ediliyor…":"＋ Fotoğraf"} disabled={restoring||recoveryBlocked||busy||disabled||uncertain} onPress={()=>void choose()}/><Button title="Kamera" disabled={restoring||recoveryBlocked||busy||disabled||uncertain} onPress={()=>void choose(true)}/><Button title="PDF / Ses" disabled={restoring||recoveryBlocked||busy||disabled||uncertain} onPress={()=>void chooseFile()}/></View>}
 {file&&<View style={{borderWidth:1,borderColor:"#DCE3EB",borderRadius:14,backgroundColor:"white",padding:10}}>
  <View style={{flexDirection:"row",alignItems:"center",gap:10}}>
   {image?<Image source={{uri:file.uri}} resizeMode="cover" style={{width:64,height:64,borderRadius:12}}/>:<View style={{width:64,height:64,borderRadius:12,backgroundColor:"#EEF3F8",alignItems:"center",justifyContent:"center"}}><Text style={{fontSize:24}}>📄</Text></View>}
   <View style={{flex:1}}>
    <Text numberOfLines={1} style={{fontWeight:"700",color:"#10233F"}}>{file.name}</Text>
    <Text style={{color:"#63748A",fontSize:12,marginTop:2}}>{replyTo?"Alıntılı yanıt olarak gönderilecek.":"Seçilen ek bu görüşmeye gönderilecek."}</Text>
   </View>
   <Pressable accessibilityRole="button" accessibilityLabel="Seçimi kaldır" disabled={restoring||recoveryBlocked||busy||uncertain} onPress={()=>setFile(null)} style={{width:36,height:36,alignItems:"center",justifyContent:"center",borderRadius:18,backgroundColor:"#F1F4F8"}}><Text style={{fontSize:18,color:"#10233F"}}>×</Text></Pressable>
  </View>
  <View style={{flexDirection:"row",gap:10,marginTop:10,flexWrap:"wrap"}}>
   {image&&<Pressable accessibilityRole="button" disabled={busy||uncertain||disabled} onPress={()=>setEditing(true)} style={{paddingVertical:10,paddingHorizontal:14,borderRadius:10,borderWidth:1,borderColor:"#DCE3EB"}}><Text style={{fontWeight:"800",color:"#071B35"}}>✎ Görseli düzenle</Text></Pressable>}
   <Pressable accessibilityRole="button" accessibilityLabel="Eki gönder" disabled={restoring||recoveryBlocked||busy||disabled||uncertain} onPress={()=>void send()} style={{paddingVertical:10,paddingHorizontal:18,borderRadius:10,backgroundColor:"#071B35",opacity:restoring||recoveryBlocked||busy||disabled||uncertain?0.5:1}}><Text style={{fontWeight:"800",color:"white"}}>{busy?"Gönderiliyor…":"Eki gönder"}</Text></Pressable>
  </View>
 </View>}
 {pendingMeta&&!file&&!recoveryBlocked&&<Text style={{color:"#63748A",padding:8}}>Önceki ek gönderiminin sonucu doğrulanıyor. Aynı dosyayı yeniden seçerseniz aynı istek anahtarıyla güvenli biçimde devam edilir.</Text>}{pendingMeta&&!file&&recoveryBlocked&&<Text style={{color:"#B42318",padding:8}}>Sunucu makbuz rotası eksik. Bekleyen ek cihazda korunuyor; sunucu güncellenene kadar dosyayı yeniden göndermeyin.</Text>}
 {pendingId&&file&&<Text style={{color:"#63748A",padding:8}}>Bekleyen ek aynı istek anahtarıyla gönderilecek.</Text>}
 {(busy||restoring)&&<ActivityIndicator/>}{restoring&&<Text style={{color:"#63748A",padding:8}}>Bekleyen ek kaydı kontrol ediliyor; kontrol bitmeden yeni gönderim açılamaz.</Text>}{recoveryBlocked&&<Button title="Bekleyen kaydı yeniden kontrol et" disabled={restoring} onPress={()=>setRestoreAttempt(value=>value+1)}/>} {!!error&&<Text style={{color:"#B42318"}}>{error}</Text>}
 {uncertain&&<><Button title="Son mesajları yenile" onPress={()=>void onRefresh()}/><Button title="Bekleyen gönderimi kontrol et" onPress={()=>{if(pendingId)void getConsultationMessageReceipt(token,caseId,pendingId).then(async receipt=>{if(receipt.deleted||receipt.message){await SecureStore.deleteItemAsync(pendingKey).catch(()=>{});setPendingId(null);setPendingMeta(null);setFile(null);setUncertain(false);await onSent()}else setError("Sunucuda henüz makbuz yok; aynı dosya ve anahtarla tekrar deneyin.")}).catch(()=>setError("Makbuz kontrol edilemedi."))}}/></>}
 {file&&image&&<NativeImageEditor source={{uri:file.uri}} visible={editing} onClose={()=>setEditing(false)} onPrepared={value=>{if(active.current){select(value);setEditing(false)}}}/>}
 </View>;
}
