import React,{useEffect,useRef,useState} from "react";
import {ActivityIndicator,Alert,Image,Modal,Pressable,ScrollView,Text,TextInput,View} from "react-native";
import * as ImagePicker from "expo-image-picker";
import {ChatAction,ChatMessage,chatImageSource,getDeletedChats,performChatAction,sendChatImage} from "./modernApi";

const navy="#071B35",muted="#63748A",line="#E1E7EF";
function Button({title,onPress,disabled=false}:{title:string;onPress:()=>void;disabled?:boolean}){
 return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={{padding:12,minHeight:44,borderRadius:10,borderWidth:1,borderColor:line,opacity:disabled ? 0.5 : 1,marginTop:8}}><Text style={{color:navy,fontWeight:"700"}}>{title}</Text></Pressable>;
}
export {default as ChatImage} from "./ChatImageViewer";
export {default as ChatPhotoComposer} from "./ChatAttachmentComposer";
export function ChatActions({token,userId,conversation,onChanged,onDeleted}:{token:string;userId:number;conversation:any;onChanged:()=>Promise<void>;onDeleted:()=>void}){
 const [open,setOpen]=useState(false),[form,setForm]=useState<"report"|"review"|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(""),[detail,setDetail]=useState(""),[reason,setReason]=useState<ChatAction["reason"]>("OTHER"),[rating,setRating]=useState(5),[start,setStart]=useState<ChatAction["start_option"]>("NOW");
 const lock=useRef(false),scope=useRef(token+":"+conversation?.id);scope.current=token+":"+conversation?.id;
 useEffect(()=>{setOpen(false);setForm(null);setError("");setDetail("");setBusy(false);lock.current=false},[token,conversation?.id]);
 const requester=conversation?.requester_user_id===userId,expert=conversation?.expert_user_id===userId,status=conversation?.status;
 async function act(payload:ChatAction){
  if(lock.current||!conversation)return;lock.current=true;setBusy(true);setError("");const expected=scope.current;
  try{await performChatAction(token,conversation.id,payload);if(expected!==scope.current)return;setForm(null);setDetail("");setOpen(false);if(payload.action==="delete")onDeleted();else await onChanged()}
  catch(e){if(expected===scope.current)setError(e instanceof Error?e.message:"İşlem tamamlanamadı.")}
  finally{if(expected===scope.current){lock.current=false;setBusy(false)}}
 }
 const confirm=(title:string,body:string,payload:ChatAction)=>Alert.alert(title,body,[{text:"Vazgeç",style:"cancel"},{text:"Onayla",onPress:()=>void act(payload)}]);
 return <View><Button title="Görüşme işlemleri ⋯" disabled={!conversation} onPress={()=>setOpen(true)}/>
 <Modal visible={open} transparent animationType="slide" onRequestClose={()=>{if(!busy)setOpen(false)}}>
 <View style={{flex:1,backgroundColor:"rgba(7,27,53,.6)",justifyContent:"flex-end"}}><ScrollView keyboardShouldPersistTaps="handled" style={{maxHeight:"85%",backgroundColor:"white",borderTopLeftRadius:20,borderTopRightRadius:20}} contentContainerStyle={{padding:20,paddingBottom:40}}>
 <Text style={{fontSize:20,fontWeight:"800",color:navy}}>Görüşme işlemleri</Text>
 <Button title="Kapat" disabled={busy} onPress={()=>setOpen(false)}/>
 {expert&&status==="REQUESTED"&&<><Text style={{marginTop:14,color:muted}}>Kabul ederseniz başlangıç zamanı</Text>{([["NOW","Şimdi"],["30M","30 dakika"],["1H","1 saat"],["3H","3 saat"],["TODAY","Bugün"]] as const).map(([value,label])=><Button key={value} title={(start===value?"✓ ":"")+label} disabled={busy} onPress={()=>setStart(value)}/>)}<Button title="Talebi kabul et" disabled={busy} onPress={()=>confirm("Talebi kabul et","Webdeki başlangıç süresi ve vaka kapasitesi kuralları uygulanır.",{action:"expert-response",decision:"ACCEPT",start_option:start})}/><Button title="Talebi reddet" disabled={busy} onPress={()=>confirm("Talebi reddet","Bu danışmanlık talebi reddedilecek.",{action:"expert-response",decision:"REJECT"})}/></>}
 {requester&&status==="PROPOSED"&&<><Text style={{color:navy,marginTop:12}}>{conversation.proposed_start_label} {conversation.expert_proposal_note||""}</Text><Button title="Başlangıç önerisini kabul et" disabled={busy} onPress={()=>confirm("Öneriyi kabul et","Uzmanın önerdiği başlangıç süresini kabul ediyorsunuz.",{action:"proposal",decision:"ACCEPT"})}/><Button title="Öneriyi reddet" disabled={busy} onPress={()=>confirm("Öneriyi reddet","Bu başlangıç önerisi reddedilecek.",{action:"proposal",decision:"REJECT"})}/></>}
 {((requester&&["ACTIVE","EXPERT_COMPLETED"].includes(status))||(expert&&status==="ACTIVE"))&&<Button title={expert?"Danışmanlığı tamamlandı işaretle":"Danışmanlığı tamamla"} disabled={busy} onPress={()=>confirm("Tamamlama onayı","Bu işlem webdeki danışmanlık ve ödeme durumunu günceller.",{action:"complete",completion_action:"COMPLETE"})}/>}
 {requester&&status==="EXPERT_COMPLETED"&&<Button title="Görüşmeye devam et" disabled={busy} onPress={()=>void act({action:"complete",completion_action:"CONTINUE"})}/>}
 {conversation?.can_dispute&&<Button title="Danışmanlık için inceleme iste" disabled={busy} onPress={()=>confirm("İnceleme iste","Danışmanlık uyuşmazlık incelemesine alınacak.",{action:"complete",completion_action:"DISPUTE"})}/>}
 {conversation?.can_report&&<><Button title={conversation.blocked_by_me?"Engeli kaldır":"Kullanıcıyı engelle"} disabled={busy} onPress={()=>confirm("Engelleme tercihi","Bu tercih sunucudaki mevcut görüşme kurallarıyla uygulanacak.",{action:conversation.blocked_by_me?"unblock":"block"})}/><Button title="Sorun bildir" disabled={busy} onPress={()=>{setForm("report");setDetail("")}}/></>}
 {requester&&status==="COMPLETED"&&!conversation.review_submitted&&<Button title="Uzmanı değerlendir" disabled={busy} onPress={()=>{setForm("review");setDetail("")}}/>}
 {form==="report"&&<View>{([["HARASSMENT","Taciz"],["PROFANITY","Küfür"],["SPAM","Spam"],["INAPPROPRIATE","Uygunsuz içerik"],["OTHER","Diğer"]] as const).map(([value,label])=><Button key={value} title={(reason===value?"✓ ":"")+label} disabled={busy} onPress={()=>setReason(value)}/>)}<TextInput accessibilityLabel="Bildirim açıklaması" placeholder="Açıklama" multiline maxLength={1000} value={detail} onChangeText={setDetail} style={{padding:12,borderWidth:1,borderColor:line,color:navy}}/><Button title="Bildirimi gönder" disabled={busy} onPress={()=>void act({action:"report",reason,detail})}/></View>}
 {form==="review"&&<View><View style={{flexDirection:"row"}}>{[1,2,3,4,5].map(value=><Button key={value} title={(rating===value?"★ ":"")+value} disabled={busy} onPress={()=>setRating(value)}/>)}</View><TextInput accessibilityLabel="Değerlendirme yorumu" placeholder="Yorum" multiline maxLength={2000} value={detail} onChangeText={setDetail} style={{padding:12,borderWidth:1,borderColor:line,color:navy}}/><Button title="Değerlendirmeyi kaydet" disabled={busy} onPress={()=>void act({action:"review",rating,comment:detail})}/></View>}
 <Button title="Görüşmeyi gelen kutumdan kaldır" disabled={busy} onPress={()=>confirm("Görüşmeyi kaldır","Yalnızca kendi gelen kutunuzdan kaldırılır. Webdeki geri yükleme süresi geçerlidir.",{action:"delete"})}/>
 {busy&&<ActivityIndicator color={navy}/>} {!!error&&<Text style={{color:"#B42318",marginTop:12}}>{error}</Text>}
 </ScrollView></View></Modal></View>;
}
export function DeletedChatButton({token,onRestored}:{token:string;onRestored:()=>Promise<void>}){
 const [open,setOpen]=useState(false),[items,setItems]=useState<Array<{id:number;status:string;specialty:string;recover_until:string}>>([]),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const scope=useRef(token);scope.current=token;const lock=useRef(false);
 useEffect(()=>{setOpen(false);setItems([]);setError("");setBusy(false);lock.current=false},[token]);
 async function load(){const expected=scope.current;setOpen(true);setBusy(true);setError("");try{const result=await getDeletedChats(token);if(expected===scope.current)setItems(result.items)}catch(e){if(expected===scope.current)setError(e instanceof Error?e.message:"Görüşmeler alınamadı.")}finally{if(expected===scope.current)setBusy(false)}}
 async function restore(id:number){if(lock.current)return;lock.current=true;const expected=scope.current;setBusy(true);try{await performChatAction(token,id,{action:"restore"});if(expected!==scope.current)return;await onRestored();await load()}catch(e){if(expected===scope.current)setError(e instanceof Error?e.message:"Geri yüklenemedi.")}finally{if(expected===scope.current){lock.current=false;setBusy(false)}}}
 return <View><Button title="Silinen görüşmeler" onPress={()=>void load()}/><Modal visible={open} onRequestClose={()=>setOpen(false)}><ScrollView contentContainerStyle={{padding:20,paddingTop:48}}><Text style={{fontSize:23,color:navy}}>Silinen görüşmeler</Text><Button title="Kapat" onPress={()=>setOpen(false)}/>{busy&&<ActivityIndicator/>}{items.map(item=><View key={item.id}><Text style={{marginTop:16,color:navy}}>Vaka #{item.id} · {item.specialty}</Text><Text style={{color:muted}}>Son geri yükleme: {new Date(item.recover_until+"Z").toLocaleString("tr-TR")}</Text><Button title="Geri yükle" disabled={busy} onPress={()=>void restore(item.id)}/></View>)}{!busy&&!items.length&&!error&&<Text style={{marginTop:20,color:muted}}>Geri yüklenebilecek görüşme yok.</Text>}{!!error&&<Text style={{color:"#B42318"}}>{error}</Text>}</ScrollView></Modal></View>;
}
