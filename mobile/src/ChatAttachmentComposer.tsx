import React,{useEffect,useRef,useState} from "react";
import {ActivityIndicator,Alert,Image,Pressable,Text,View} from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import {ChatFile,validateChatFile} from "./chatFiles";
import {sendChatFile} from "./modernApi";
import NativeImageEditor from "./NativeImageEditor";

function Button({title,onPress,disabled=false}:{title:string;onPress:()=>void;disabled?:boolean}){return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={{padding:12,minHeight:44,opacity:disabled ? 0.5 : 1}}><Text style={{color:"#071B35",fontWeight:"700"}}>{title}</Text></Pressable>}
export default function ChatAttachmentComposer({token,caseId,replyTo,disabled,onSent,onRefresh,prepared}:{token:string;caseId:number;replyTo:number|null;disabled:boolean;onSent:()=>Promise<void>;onRefresh:()=>Promise<void>;prepared?:{file:ChatFile;nonce:string}|null}){
 const [file,setFile]=useState<ChatFile|null>(null),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),[error,setError]=useState(""),[editing,setEditing]=useState(false);
 const scope=useRef(token+":"+caseId);scope.current=token+":"+caseId;const lock=useRef(false),active=useRef(true);
 useEffect(()=>{active.current=true;return()=>{active.current=false}},[]);
 useEffect(()=>{setFile(null);setBusy(false);setUncertain(false);setError("");setEditing(false);lock.current=false},[token,caseId]);
 useEffect(()=>{if(prepared){setFile(prepared.file);setError("");setEditing(false)}},[prepared?.nonce]);
 useEffect(()=>()=>{if(file?.owned)void FileSystem.deleteAsync(file.uri,{idempotent:true}).catch(()=>{})},[file?.uri]);
 const current=(owner:string)=>active.current&&owner===scope.current;
 function select(value:ChatFile){const checked=validateChatFile(value);setFile(checked);setError("")}
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
  try{await sendChatFile(token,caseId,file,replyTo??undefined);if(!current(owner))return;setFile(null);await onSent()}
  catch{if(current(owner)){setUncertain(true);setError("Gönderim doğrulanamadı. Ek kaydedilmiş olabilir; yeniden göndermeden önce son mesajları kontrol edin.");void onRefresh()}}
  finally{if(current(owner)){lock.current=false;setBusy(false)}}
 }
 const image=!!file?.type.startsWith("image/");
 return <View style={{paddingHorizontal:12,paddingBottom:8}}><View style={{flexDirection:"row",flexWrap:"wrap"}}><Button title="＋ Fotoğraf" disabled={busy||disabled||uncertain} onPress={()=>void choose()}/><Button title="Kamera" disabled={busy||disabled||uncertain} onPress={()=>void choose(true)}/><Button title="PDF / Ses" disabled={busy||disabled||uncertain} onPress={()=>void chooseFile()}/></View>
 {file&&<View>{image?<Image source={{uri:file.uri}} resizeMode="contain" style={{height:130,width:"100%"}}/>:<Text style={{color:"#071B35",padding:12}}>{file.name}</Text>}<Text style={{color:"#63748A"}}>{replyTo?"Alıntılı yanıt olarak gönderilecek.":"Seçilen ek bu görüşmeye gönderilecek."}</Text>
 {image&&<Button title="Görseli düzenle" disabled={busy||uncertain||disabled} onPress={()=>setEditing(true)}/>}<Button title={busy?"Gönderiliyor…":"Eki gönder"} disabled={busy||disabled||uncertain} onPress={()=>void send()}/><Button title="Seçimi kaldır" disabled={busy||uncertain} onPress={()=>setFile(null)}/></View>}
 {busy&&<ActivityIndicator/>}{!!error&&<Text style={{color:"#B42318"}}>{error}</Text>}
 {uncertain&&<><Button title="Son mesajları yenile" onPress={()=>void onRefresh()}/><Button title="Kontrol ettim, seçimi temizle" onPress={()=>Alert.alert("Gönderimi kontrol edin","Ek son mesajlarda görünüyorsa tekrar göndermeyin.",[{text:"Vazgeç",style:"cancel"},{text:"Seçimi temizle",onPress:()=>{setFile(null);setUncertain(false);setError("")}}])}/></>}
 {file&&image&&<NativeImageEditor source={{uri:file.uri}} visible={editing} onClose={()=>setEditing(false)} onPrepared={value=>{if(active.current){select(value);setEditing(false)}}}/>}
 </View>;
}
