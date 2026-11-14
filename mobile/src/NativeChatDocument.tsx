import React,{useEffect,useRef,useState} from "react";
import {ActivityIndicator,AppState,Modal,Pressable,Text,View} from "react-native";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import * as Crypto from "expo-crypto";
import {useAudioPlayer,useAudioPlayerStatus} from "expo-audio";
import {ChatMessage,chatImageSource} from "./modernApi";
import {revalidateSession} from "./sessionExpiry";

function AudioControls({uri}:{uri:string}){
 const player=useAudioPlayer(uri),status=useAudioPlayerStatus(player);
 useEffect(()=>{const stop=AppState.addEventListener("change",state=>{if(state!=="active")player.pause()});return()=>{stop.remove();player.pause()}},[player]);
 return <View><Text style={{marginVertical:12}}>{Math.floor(status.currentTime||0)} / {Math.floor(status.duration||0)} saniye</Text>
 <Pressable accessibilityRole="button" onPress={()=>{if(status.playing)player.pause();else player.play()}} style={{padding:16}}><Text>{status.playing?"Duraklat":"Dinle"}</Text></Pressable>
 <Pressable accessibilityRole="button" onPress={()=>{player.pause();void player.seekTo(0)}} style={{padding:16}}><Text>Başa dön</Text></Pressable></View>;
}
export default function NativeChatDocument({token,caseId,message}:{token:string;caseId:number;message:ChatMessage}){
 const [open,setOpen]=useState(false),[uri,setUri]=useState<string|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const current=useRef(true),local=useRef<string|null>(null),download=useRef<FileSystem.DownloadResumable|null>(null),lock=useRef(false);
 const extension=String(message.content||"").split(".").pop()?.toLowerCase()||"";
 const mime=message.message_type==="FILE"?"application/pdf":extension==="m4a"?"audio/mp4":extension==="wav"?"audio/wav":extension==="ogg"?"audio/ogg":"audio/mpeg";
 useEffect(()=>{current.current=true;return()=>{current.current=false;void download.current?.pauseAsync().catch(()=>{}).finally(()=>{if(local.current)void FileSystem.deleteAsync(local.current,{idempotent:true})});if(local.current)void FileSystem.deleteAsync(local.current,{idempotent:true})}},[token,caseId,message.id]);
 async function prepare(){
  if(lock.current)return;setOpen(true);if(uri)return;lock.current=true;setBusy(true);setError("");
  if(!FileSystem.cacheDirectory){setError("Güvenli dosya önbelleği kullanılamıyor.");setBusy(false);lock.current=false;return}
  const suffix=message.message_type==="FILE"?"pdf":["mp3","m4a","wav","ogg"].includes(extension)?extension:"mp3";
  const destination=FileSystem.cacheDirectory+"dai-chat-"+Crypto.randomUUID()+"."+suffix;local.current=destination;
  try{
   const source=chatImageSource(token,caseId,message.id);
   const task=FileSystem.createDownloadResumable(source.uri,destination,{headers:source.headers});download.current=task;
   const result=await task.downloadAsync();
   if(!current.current){await FileSystem.deleteAsync(destination,{idempotent:true});return}
   if(result?.status===401)await revalidateSession(token);
   if(!result||result.status!==200){await FileSystem.deleteAsync(destination,{idempotent:true});throw Error("download failed")}
   const info=await FileSystem.getInfoAsync(destination);if(!info.exists||info.size>25*1024*1024){await FileSystem.deleteAsync(destination,{idempotent:true});throw Error("invalid file")}
   setUri(result.uri);
  }catch{await FileSystem.deleteAsync(destination,{idempotent:true}).catch(()=>{});if(current.current)setError("Dosya alınamadı. Bağlantınızı ve görüşme erişiminizi kontrol edip tekrar deneyin.")}
  finally{download.current=null;if(current.current){setBusy(false);lock.current=false}}
 }
 async function share(){if(!uri)return;try{if(!await Sharing.isAvailableAsync()){setError("Bu cihazda dosya açma/paylaşma kullanılamıyor.");return}await Sharing.shareAsync(uri,{mimeType:mime,dialogTitle:"Klinik dosyayı aç veya paylaş"})}catch{if(current.current)setError("Dosya açılamadı. Yeniden deneyin.")}}
 return <View><Pressable accessibilityRole="button" onPress={()=>void prepare()} style={{paddingVertical:12}}><Text style={{color:"#1769AA",fontWeight:"700"}}>{message.message_type==="VOICE"?"▶ Ses kaydını dinle":"▤ Dosyayı aç"} · {message.content}</Text></Pressable>
 <Modal visible={open} onRequestClose={()=>setOpen(false)}><View style={{flex:1,padding:24,paddingTop:48}}><Text style={{fontSize:22,fontWeight:"800"}}>{message.message_type==="VOICE"?"Ses kaydı":"Klinik dosya"}</Text><Text style={{marginTop:12}}>{message.content}</Text>
 {busy&&<ActivityIndicator/>}{!!error&&<><Text style={{color:"#B42318",marginTop:12}}>{error}</Text><Pressable onPress={()=>void prepare()} style={{padding:16}}><Text>Tekrar dene</Text></Pressable></>}
 {uri&&message.message_type==="VOICE"&&open&&<AudioControls uri={uri}/>}{uri&&<Pressable accessibilityRole="button" onPress={()=>void share()} style={{padding:16}}><Text>Dosyayı aç / paylaş</Text></Pressable>}
 <Pressable accessibilityRole="button" onPress={()=>setOpen(false)} style={{padding:16}}><Text>Kapat</Text></Pressable></View></Modal></View>;
}
