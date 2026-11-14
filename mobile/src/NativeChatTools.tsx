import React,{useEffect,useRef,useState} from "react";
import {ActivityIndicator,Alert,Image,Modal,Pressable,ScrollView,Text,TextInput,View} from "react-native";
import * as ImagePicker from "expo-image-picker";
import {ChatAction,ChatMessage,chatImageSource,getDeletedChats,performChatAction,sendChatImage} from "./modernApi";

const navy="#071B35",muted="#63748A",line="#E1E7EF";
function Button({title,onPress,disabled=false}:{title:string;onPress:()=>void;disabled?:boolean}){
 return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={{padding:12,minHeight:44,borderRadius:10,borderWidth:1,borderColor:line,opacity:disabled ? 0.5 : 1,marginTop:8}}><Text style={{color:navy,fontWeight:"700"}}>{title}</Text></Pressable>;
}
export function ChatImage({token,caseId,message}:{token:string;caseId:number;message:ChatMessage}){
 const [open,setOpen]=useState(false),[zoom,setZoom]=useState(1),[failed,setFailed]=useState(false);
 useEffect(()=>{setOpen(false);setZoom(1);setFailed(false)},[token,caseId,message.id]);
 const source=chatImageSource(token,caseId,message.id);
 return <View><Pressable accessibilityRole="button" accessibilityLabel="Klinik görüntüyü aç" onPress={()=>{setZoom(1);setOpen(true)}}>
  <Image source={source} resizeMode="contain" onError={()=>setFailed(true)} style={{width:220,maxWidth:"100%",height:160,borderRadius:10}}/>
  {failed&&<Text style={{color:"#B42318"}}>Görüntü alınamadı. Görüşmeyi yenileyin.</Text>}
 </Pressable><Modal visible={open} animationType="fade" onRequestClose={()=>setOpen(false)}>
 <View style={{flex:1,backgroundColor:"#071B35",paddingTop:36,paddingBottom:24}}>
 <View style={{flexDirection:"row",justifyContent:"space-around"}}>{[["Kapat",()=>setOpen(false)],["−",()=>setZoom(v=>Math.max(1,v-.5))],["+",()=>setZoom(v=>Math.min(4,v+.5))]] .map(([title,action])=><Pressable key={String(title)} accessibilityRole="button" accessibilityLabel={String(title)} onPress={action as ()=>void} style={{padding:16}}><Text style={{color:"white",fontSize:20}}>{String(title)}</Text></Pressable>)}</View>
 <ScrollView horizontal contentContainerStyle={{flexGrow:1}}><ScrollView contentContainerStyle={{flexGrow:1,justifyContent:"center",alignItems:"center"}}><Image source={source} resizeMode="contain" style={{width:320*zoom,height:480*zoom}}/></ScrollView></ScrollView>
 </View></Modal></View>;
}
export function ChatPhotoComposer({token,caseId,replyTo,disabled,onSent,onRefresh}:{token:string;caseId:number;replyTo:number|null;disabled:boolean;onSent:()=>Promise<void>;onRefresh:()=>Promise<void>}){
 const [file,setFile]=useState<{uri:string;name:string;type:string;size?:number}|null>(null),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),[error,setError]=useState("");
 const scope=useRef(token+":"+caseId);scope.current=token+":"+caseId;
 const lock=useRef(false);
 useEffect(()=>{setFile(null);setBusy(false);setUncertain(false);setError("");lock.current=false},[token,caseId]);
 async function choose(camera=false){
  if(lock.current||disabled)return;const expected=scope.current;
  try{
   const permission=camera?await ImagePicker.requestCameraPermissionsAsync():await ImagePicker.requestMediaLibraryPermissionsAsync();
   if(expected!==scope.current)return;
   if(!permission.granted){setError(camera?"Kamera izni gerekli.":"Galeri izni gerekli.");return}
   const result=camera?await ImagePicker.launchCameraAsync({mediaTypes:["images"],quality:.9}):await ImagePicker.launchImageLibraryAsync({mediaTypes:["images"],quality:.9,allowsMultipleSelection:false});
   if(expected!==scope.current||result.canceled||!result.assets[0])return;
   const asset=result.assets[0],type=asset.mimeType||"image/jpeg",extension=type==="image/png"?".png":type==="image/webp"?".webp":".jpg";
   if(!["image/jpeg","image/png","image/webp"].includes(type)||asset.fileSize!==undefined&&asset.fileSize>15*1024*1024){setError("JPG, PNG veya WEBP seçin; sınır 15 MB.");return}
   setFile({uri:asset.uri,name:"klinik-goruntu"+extension,type,size:asset.fileSize});setError("");
  }catch(e){if(expected===scope.current)setError(e instanceof Error?e.message:"Görsel seçilemedi.")}
 }
 async function send(){
  if(!file||lock.current||disabled||uncertain)return;lock.current=true;const expected=scope.current;
  setBusy(true);setError("");
  try{await sendChatImage(token,caseId,file,replyTo??undefined);if(expected!==scope.current)return;setFile(null);await onSent()}
  catch(e){if(expected===scope.current){setUncertain(true);setError((e instanceof Error?e.message:"Aktarım doğrulanamadı.")+" Görsel kaydedilmiş olabilir; yeniden göndermeden önce son mesajları kontrol edin.");void onRefresh()}}
  finally{if(expected===scope.current){lock.current=false;setBusy(false)}}
 }
 return <View style={{paddingHorizontal:12,paddingBottom:8}}>
 <View style={{flexDirection:"row",gap:8}}><Button title="＋ Fotoğraf" disabled={busy||disabled||uncertain} onPress={()=>void choose()}/><Button title="Kamera" disabled={busy||disabled||uncertain} onPress={()=>void choose(true)}/></View>
 {file&&<View><Image source={{uri:file.uri}} resizeMode="contain" style={{height:140,width:"100%",marginTop:8}}/><Text style={{color:muted}}>Seçilen görüntü {replyTo?"alıntılı yanıt olarak ":""}gönderilecek.</Text>
 <Button title={busy?"Gönderiliyor…":"Görseli gönder"} disabled={busy||disabled||uncertain} onPress={()=>void send()}/><Button title="Seçimi kaldır" disabled={busy||uncertain} onPress={()=>setFile(null)}/></View>}
 {!!error&&<Text style={{color:"#B42318",marginTop:8}}>{error}</Text>}
 {uncertain&&<><Button title="Son mesajları yenile" onPress={()=>void onRefresh()}/><Button title="Kontrol ettim, seçimi temizle" onPress={()=>Alert.alert("Gönderimi kontrol edin","Görsel son mesajlarda görünüyorsa tekrar göndermeyin.",[{text:"Vazgeç",style:"cancel"},{text:"Seçimi temizle",onPress:()=>{setFile(null);setUncertain(false);setError("")}}])}/></>}
 </View>;
}
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
