import React,{useEffect,useRef,useState} from "react";
import {ActivityIndicator,Alert,Image,Pressable,Text,View} from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import * as SecureStore from "expo-secure-store";
import {ChatFile,validateChatFile} from "./chatFiles";
import {getConsultationMessageReceipt,sendChatFile} from "./modernApi";
import NativeImageEditor from "./NativeImageEditor";

function Button({title,onPress,disabled=false}:{title:string;onPress:()=>void;disabled?:boolean}){return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={{padding:12,minHeight:44,opacity:disabled ? 0.5 : 1}}><Text style={{color:"#071B35",fontWeight:"700"}}>{title}</Text></Pressable>}
export default function ChatAttachmentComposer({token,userId,caseId,replyTo,disabled,onSent,onRefresh,prepared,deleted=false}:{token:string;userId:number;caseId:number;replyTo:number|null;disabled:boolean;onSent:()=>Promise<void>;onRefresh:()=>Promise<void>;prepared?:{file:ChatFile;nonce:string}|null;deleted?:boolean}){
 const [file,setFile]=useState<ChatFile|null>(null),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),[error,setError]=useState(""),[editing,setEditing]=useState(false),[pendingId,setPendingId]=useState<string|null>(null),[pendingMeta,setPendingMeta]=useState<{id:string;scope:string;replyTo:number|null;name:string;type:string;size:number|null;createdAt:number}|null>(null);
 const scope=useRef(token+":"+userId+":"+caseId);scope.current=token+":"+userId+":"+caseId;const lock=useRef(false),active=useRef(true),pendingKey="dai.consultation.media."+userId+"."+caseId;
 useEffect(()=>{active.current=true;return()=>{active.current=false}},[]);
 useEffect(()=>{let live=true;setFile(null);setBusy(false);setUncertain(false);setError("");setEditing(false);setPendingId(null);setPendingMeta(null);lock.current=false;
  void SecureStore.getItemAsync(pendingKey).then(async raw=>{if(!raw)return;let value:any=null;try{value=JSON.parse(raw)}catch{}if(!value||value.version!==1||typeof value.id!=="string"||!/^[A-Za-z0-9_-]{16,96}$/.test(value.id)||value.scope!==userId+":"+caseId||typeof value.name!=="string"||typeof value.type!=="string"||(value.replyTo!==null&&!Number.isSafeInteger(value.replyTo)))return;
   if(!live)return;setPendingId(value.id);setPendingMeta({id:value.id,scope:value.scope,replyTo:value.replyTo,name:value.name,type:value.type,size:Number.isFinite(value.size)?value.size:null,createdAt:Number(value.createdAt)||Date.now()});
   try{const receipt=await getConsultationMessageReceipt(token,caseId,value.id);if(live&&(receipt.deleted||receipt.message)){await SecureStore.deleteItemAsync(pendingKey).catch(()=>{});setPendingId(null);setPendingMeta(null);setFile(null);await onSent()}}
   catch{/* Keep the encrypted intent for an explicit same-key retry. */}
  }).catch(()=>{if(live)setError("Bekleyen ek kaydı okunamadı. Güvenli taslak korunuyor.")});
  return()=>{live=false};
 },[token,userId,caseId,pendingKey]);
 useEffect(()=>{if(prepared){try{select(prepared.file);setEditing(false)}catch(e){setError(e instanceof Error?e.message:"Dosya hazırlanamadı.")}}},[prepared?.nonce]);
 useEffect(()=>{if(pendingMeta&&file&&(file.name!==pendingMeta.name||file.type!==pendingMeta.type||(pendingMeta.size!==null&&file.size!==undefined&&file.size!==pendingMeta.size))){setFile(null);setError("Bekleyen ek gönderimini tamamlamak için aynı dosyayı yeniden seçin.")}},[pendingMeta,file]);
 useEffect(()=>{if(deleted){setFile(null);setPendingId(null);setPendingMeta(null);setUncertain(false);void SecureStore.deleteItemAsync(pendingKey).catch(()=>{})}},[deleted,pendingKey]);
 useEffect(()=>()=>{if(file?.owned)void FileSystem.deleteAsync(file.uri,{idempotent:true}).catch(()=>{})},[file?.uri]);
 const current=(owner:string)=>active.current&&owner===scope.current;
 function select(value:ChatFile){const checked=validateChatFile(value);if(pendingMeta&&(checked.name!==pendingMeta.name||checked.type!==pendingMeta.type||(pendingMeta.size!==null&&checked.size!==undefined&&checked.size!==pendingMeta.size)))throw Error("Bekleyen ek gönderimini tamamlamak için aynı dosyayı yeniden seçin.");setFile(checked);setError("")}
 async function choose(camera=false){
  if(lock.current||disabled||uncertain)return;const owner=scope.current;
  try{const permission=camera?await ImagePicker.requestCameraPermissionsAsync():await ImagePicker.requestMediaLibraryPermissionsAsync();if(!current(owner))return;
   if(!permission.granted){setError(camera?"Kamera izni gerekli.":"Galeri izni gerekli.");return}
   const result=camera?await ImagePicker.launchCameraAsync({mediaTypes:["images"],quality:.9}):await ImagePicker.launchImageLibraryAsync({mediaTypes:["images"],quality:.9,allowsMultipleSelection:false});
   if(!current(owner)||result.canceled||!result.assets[0])return;
   const asset=result.assets[0],type=asset.mimeType||"image/jpeg",extension=type==="image/png"?".png":type==="image/webp"?".webp":".jpg";
   select({uri:asset.uri,name:"klinik-goruntu"+extension,type,size:asset.fileSize});
  }catch(e){if(current(owner))setError(e instanceof Error?e.message:"Görsel seçilemedi.")}
 }
 async function chooseFile(){
  if(lock.current||disabled||uncertain)return;const owner=scope.current;
  try{const result=await DocumentPicker.getDocumentAsync({type:["application/pdf","audio/*"],multiple:false,copyToCacheDirectory:true});
   if(result.canceled)return;const asset=result.assets[0];if(!current(owner)){if(asset?.uri)await FileSystem.deleteAsync(asset.uri,{idempotent:true});return}
   if(!asset)return;try{select({uri:asset.uri,name:asset.name,type:asset.mimeType||"application/octet-stream",size:asset.size,owned:true})}catch(e){await FileSystem.deleteAsync(asset.uri,{idempotent:true});throw e}
  }catch(e){if(current(owner))setError(e instanceof Error?e.message:"Dosya seçilemedi.")}
 }
 async function send(){
  if(!file||lock.current||disabled||uncertain)return;lock.current=true;const owner=scope.current;setBusy(true);setError("");
  const intent=pendingMeta||{id:"native-media-"+Date.now().toString(36)+"-"+Math.random().toString(36).slice(2),scope:userId+":"+caseId,replyTo,name:file.name,type:file.type,size:file.size??null,createdAt:Date.now()};
  if(intent.scope!==userId+":"+caseId){setError("Bekleyen ek başka bir hesap veya görüşmeye ait.");setBusy(false);lock.current=false;return}
  try{
   if(!pendingMeta){await SecureStore.setItemAsync(pendingKey,JSON.stringify({version:1,...intent}));if(!current(owner))return;setPendingId(intent.id);setPendingMeta(intent)}
   const result=await sendChatFile(token,caseId,file,intent.replyTo??undefined,intent.id);
   if(!current(owner))return;
   if(!result?.message?.id)throw Error("Ek gönderimi doğrulanamadı.");
   await SecureStore.deleteItemAsync(pendingKey).catch(()=>{});setPendingId(null);setPendingMeta(null);setFile(null);setUncertain(false);await onSent();
  }catch(e){
   if(current(owner)){
    try{const receipt=await getConsultationMessageReceipt(token,caseId,intent.id);if(current(owner)&&(receipt.deleted||receipt.message)){await SecureStore.deleteItemAsync(pendingKey).catch(()=>{});setPendingId(null);setPendingMeta(null);setFile(null);await onSent();return}}catch{}
    if(current(owner)){setUncertain(false);setError((e instanceof Error?e.message:"Ek gönderilemedi.")+" Aynı dosya ve istek anahtarı korunuyor; tekrar deneyebilirsiniz.");void onRefresh()}
   }
  }finally{if(current(owner)){lock.current=false;setBusy(false)}}
 }
 const image=!!file?.type.startsWith("image/");
 return <View style={{paddingHorizontal:12,paddingBottom:8}}><View style={{flexDirection:"row",flexWrap:"wrap"}}><Button title="＋ Fotoğraf" disabled={busy||disabled||uncertain} onPress={()=>void choose()}/><Button title="Kamera" disabled={busy||disabled||uncertain} onPress={()=>void choose(true)}/><Button title="PDF / Ses" disabled={busy||disabled||uncertain} onPress={()=>void chooseFile()}/></View>
 {file&&<View>{image?<Image source={{uri:file.uri}} resizeMode="contain" style={{height:130,width:"100%"}}/>:<Text style={{color:"#071B35",padding:12}}>{file.name}</Text>}<Text style={{color:"#63748A"}}>{replyTo?"Alıntılı yanıt olarak gönderilecek.":"Seçilen ek bu görüşmeye gönderilecek."}</Text>
 {image&&<Button title="Görseli düzenle" disabled={busy||uncertain||disabled} onPress={()=>setEditing(true)}/>}<Button title={busy?"Gönderiliyor…":"Eki gönder"} disabled={busy||disabled||uncertain} onPress={()=>void send()}/><Button title="Seçimi kaldır" disabled={busy||uncertain} onPress={()=>setFile(null)}/></View>}
 {pendingMeta&&!file&&<Text style={{color:"#63748A",padding:8}}>Önceki ek gönderiminin sonucu doğrulanıyor. Aynı dosyayı yeniden seçerseniz aynı istek anahtarıyla güvenli biçimde devam edilir.</Text>}
 {pendingId&&file&&<Text style={{color:"#63748A",padding:8}}>Bekleyen ek aynı istek anahtarıyla gönderilecek.</Text>}
 {busy&&<ActivityIndicator/>}{!!error&&<Text style={{color:"#B42318"}}>{error}</Text>}
 {uncertain&&<><Button title="Son mesajları yenile" onPress={()=>void onRefresh()}/><Button title="Bekleyen gönderimi kontrol et" onPress={()=>{if(pendingId)void getConsultationMessageReceipt(token,caseId,pendingId).then(async receipt=>{if(receipt.deleted||receipt.message){await SecureStore.deleteItemAsync(pendingKey).catch(()=>{});setPendingId(null);setPendingMeta(null);setFile(null);setUncertain(false);await onSent()}else setError("Sunucuda henüz makbuz yok; aynı dosya ve anahtarla tekrar deneyin.")}).catch(()=>setError("Makbuz kontrol edilemedi."))}}/></>}
 {file&&image&&<NativeImageEditor source={{uri:file.uri}} visible={editing} onClose={()=>setEditing(false)} onPrepared={value=>{if(active.current){select(value);setEditing(false)}}}/>}
 </View>;
}
