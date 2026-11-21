import {sharedCaseImageSource} from "./modernApi";
import NativeChatDocument from "./NativeChatDocument";
import {ChatFile} from "./chatFiles";
import NativeConsultationRequest from "./NativeConsultationRequest";
import {ChatActions,ChatImage,ChatPhotoComposer,DeletedChatButton} from "./NativeChatTools";
import {useNavigation,useIsFocused,useRoute} from "@react-navigation/native";
import React,{useCallback,useEffect,useRef,useState}from"react";

import * as SecureStore from"expo-secure-store";
import * as Crypto from "expo-crypto";
import{ActivityIndicator,Alert,FlatList,Image,KeyboardAvoidingView,Platform,Pressable,RefreshControl,ScrollView,StyleSheet,Text,TextInput,View}from"react-native";
import{getAnalysisHistory,getConsultation,getConsultationUpdates,getConsultations,getCourses,getAcademicMessages,getExperts,getNotifications,markNotificationRead,markAllNotificationsRead,askAcademic,sendConsultationMessage,getConsultationMessageReceipt,markConsultationRead,createConsultation,performChatAction,createAvailabilityWatch,getAvailabilityWatch,AvailabilityWatch,EXPERT_SPECIALTIES,Expert,Consultation,Course,ChatMessage}from"./modernApi";
import{useRealtime}from"./realtime";
import {applyConsultationInboxEvent,applyConsultationChatEvent,mergeConsultationMessages,consultationStatusLabel,consultationMessagePreview} from "./consultationRealtime";
import {usePagedRecords} from "./usePagedRecords";
import {resolveNativeNotificationTarget} from "./notificationTarget";
import {applyNotificationReadAllSnapshot,parseNotificationTimestamp} from "./notificationState";
import {shouldRefreshNotificationList} from "./notificationRefresh";

const C={navy:"#071B35",bg:"#F5F7FA",white:"#FFF",text:"#102033",muted:"#718096",line:"#E5EAF0",soft:"#EEF3F8",green:"#16803C",red:"#B42318"};
const card={backgroundColor:C.white,borderRadius:18,borderWidth:1,borderColor:C.line,padding:16,marginBottom:12} as any;
function Btn({title,onPress,disabled=false}:{title:string;onPress:()=>void;disabled?:boolean}){return <Pressable disabled={disabled} onPress={onPress} style={[s.btn,disabled&&{opacity:.5}]}><Text style={s.btnT}>{title}</Text></Pressable>}
function Empty({title,sub}:{title:string;sub:string}){return <View style={s.empty}><Text style={s.emptyTitle}>{title}</Text><Text style={s.muted}>{sub}</Text></View>}

export function Notifications({token,initialNoticeId}:{token:string;initialNoticeId?:number}){
 const nav:any=useNavigation(),route:any=useRoute();const rawNoticeId=initialNoticeId??route?.params?.noticeId;
 const noticeId=Number.isSafeInteger(rawNoticeId)&&rawNoticeId>0?rawNoticeId as number:undefined;
 const[d,setD]=useState<any>();const{lastEvent}=useRealtime();
 const[busy,setBusy]=useState(false),[markingAll,setMarkingAll]=useState(false),[error,setError]=useState("");
 const requestGeneration=useRef(0),activeToken=useRef(token),autoOpenedNoticeId=useRef<number|null>(null);
 const loadPromise=useRef<Promise<void>|null>(null),loadQueued=useRef(false);
 // Never allow an earlier account or an older refresh to overwrite this account's notifications.
 if(activeToken.current!==token){
  activeToken.current=token;requestGeneration.current++;autoOpenedNoticeId.current=null;
  loadQueued.current=false;loadPromise.current=null;
 }
 const load=useCallback(async()=>{
  if(loadPromise.current){loadQueued.current=true;return loadPromise.current;}
  const task=(async()=>{
   do{
    loadQueued.current=false;
    const request=++requestGeneration.current;setBusy(true);
    try{
     const result=await getNotifications(token,noticeId);
     if(request===requestGeneration.current&&activeToken.current===token){setD({...result,accountToken:token});setError("");}
    }catch(e){
     if(request===requestGeneration.current&&activeToken.current===token)setError(e instanceof Error?e.message:"Bildirimler alınamadı.");
    }finally{
     if(request===requestGeneration.current&&activeToken.current===token)setBusy(false);
    }
   }while(loadQueued.current&&activeToken.current===token);
  })();
  loadPromise.current=task;
  try{await task;}finally{if(loadPromise.current===task)loadPromise.current=null;}
 },[token,noticeId]);
 useEffect(()=>{setD(undefined);setError("");setBusy(false);autoOpenedNoticeId.current=null;return()=>{requestGeneration.current++}},[token,noticeId]);
 useEffect(()=>{void load()},[load]);
 useEffect(()=>{if(shouldRefreshNotificationList(lastEvent))void load()},[lastEvent,load]);
 async function open(item:any){
  const requestToken=token;
  const target=resolveNativeNotificationTarget(item.target_url);
  if(target.kind==="unsupported"){
   Alert.alert("Bağlantı açılamıyor","Bu bildirimin hedef sayfası henüz mobil uygulamada bulunmuyor. Bildirim okunmamış bırakıldı.");
   return;
  }
  if(!item.read_at){
   try{
    await markNotificationRead(token,item.id);
    if(activeToken.current!==requestToken)return;
    setD((old:any)=>old?.accountToken===requestToken?{...old,items:old.items.map((n:any)=>n.id===item.id?{...n,read_at:new Date().toISOString()}:n)}:old);
   }catch(e){
    if(activeToken.current===requestToken)setError(e instanceof Error?e.message:"Bildirim okunmuş olarak işaretlenemedi.");
   }
  }
  if(activeToken.current!==requestToken)return;
  if(target.kind==="navigate"){
   if("params" in target.route)nav.navigate(target.route.screen,target.route.params);
   else nav.navigate(target.route.screen);
  }
 }
 useEffect(()=>{
  if(noticeId===undefined||d?.accountToken!==token||!Array.isArray(d.items)||autoOpenedNoticeId.current===noticeId)return;
  autoOpenedNoticeId.current=noticeId;
  const item=d.items.find((entry:any)=>entry.id===noticeId);
  if(item)void open(item);
  else setError("Bu bildirim artık etkin değil veya hesabınıza ait değil.");
 },[noticeId,d,token]);
 async function markAllRead(){
  if(markingAll||busy||activeToken.current!==token||d?.accountToken!==token||!d?.unread)return;
  const seenBefore=new Date().toISOString();
  setMarkingAll(true);setError("");
  try{
   const result=await markAllNotificationsRead(token,seenBefore);
   if(activeToken.current!==token)return;
   setD((old:any)=>{
    if(old?.accountToken!==token||!Array.isArray(old.items))return old;
    const items=applyNotificationReadAllSnapshot(old.items,seenBefore);
    return {...old,items,unread:result.unread_count};
   });
  }catch(e){
   if(activeToken.current===token)setError(e instanceof Error?e.message:"Bildirimler okundu olarak işaretlenemedi.");
  }finally{
   if(activeToken.current===token)setMarkingAll(false);
  }
 }

 return <FlatList style={s.page} contentContainerStyle={s.pad} data={d?.accountToken===token?d.items:[]} keyExtractor={x=>String(x.id)}
 refreshControl={<RefreshControl refreshing={busy&&(!d||d.accountToken===token)} onRefresh={()=>void load()}/>}
 ListHeaderComponent={<View style={{marginBottom:14}}><Text style={s.big}>Bildirimler</Text><Text style={s.muted}>Yeni mesajlar, danışmanlıklar ve hesap gelişmeleri.</Text>{d?.accountToken===token&&d.unread>0&&<Pressable accessibilityRole="button" accessibilityLabel="Tüm bildirimleri okundu işaretle" disabled={busy||markingAll} onPress={()=>void markAllRead()} style={[s.btn,{marginTop:12,opacity:(busy||markingAll)?0.55:1}]}><Text style={s.btnT}>{markingAll?"Okundu olarak işaretleniyor…":"Tümünü okundu işaretle"}</Text></Pressable>}{!!error&&(!d||d.accountToken===token)&&<Text accessibilityRole="alert" style={{color:C.red,marginTop:10}}>{error}</Text>}</View>}
 renderItem={({item})=><Pressable accessibilityRole="button" style={[card,!item.read_at&&{borderLeftWidth:4,borderLeftColor:C.navy}]} onPress={()=>void open(item)}>
  <View style={s.row}><Text style={[s.title,{flex:1}]}>{item.title}</Text>{!item.read_at&&<Text style={{color:"#1769AA",fontWeight:"800"}}>Yeni</Text>}</View>
  <Text style={s.body}>{item.message}</Text><Text style={s.meta}>{Number.isFinite(parseNotificationTimestamp(item.created_at))?new Date(parseNotificationTimestamp(item.created_at)).toLocaleString("tr-TR"):"—"}</Text>
 </Pressable>} ListEmptyComponent={!busy&&(!d||d.accountToken===token)?<View><Empty title={error?"Bildirimler yüklenemedi":"Bildirim yok"} sub={error?"Bağlantıyı kontrol edip yeniden deneyin.":"Yeni gelişmeler burada görünecek."}/>{!!error&&<Pressable accessibilityRole="button" onPress={()=>void load()} style={s.btn}><Text style={s.btnT}>Yeniden dene</Text></Pressable>}</View>:null}/>;
}

export function AnalysisHistory({token}:{token:string}){const nav:any=useNavigation();const[d,setD]=useState<any>();const{lastEvent}=useRealtime();const[busy,setBusy]=useState(false),[loadingMore,setLoadingMore]=useState(false),[error,setError]=useState("");const loadingMoreRef=useRef(false);const requestGeneration=useRef(0),activeToken=useRef(token);
 if(activeToken.current!==token){activeToken.current=token;requestGeneration.current++;}
 const load=useCallback(async()=>{const request=++requestGeneration.current;loadingMoreRef.current=false;setLoadingMore(false);setBusy(true);try{const result=await getAnalysisHistory(token);if(request===requestGeneration.current&&activeToken.current===token){setD({...result,accountToken:token});setError("")}}catch(e){if(request===requestGeneration.current&&activeToken.current===token)setError(e instanceof Error?e.message:"Analiz geçmişi alınamadı.")}finally{if(request===requestGeneration.current&&activeToken.current===token)setBusy(false)}},[token]);
 useEffect(()=>{setD(undefined);setError("");setBusy(false);setLoadingMore(false);loadingMoreRef.current=false;return()=>{requestGeneration.current++}},[token]);
 useEffect(()=>{void load()},[load]);useEffect(()=>{if(lastEvent&&["ANALYSIS_CREATED","ANALYSIS_UPDATED"].includes(String(lastEvent.event_type||lastEvent.type)))void load()},[lastEvent,load]);
 const loadMore=useCallback(async()=>{if(loadingMoreRef.current||busy||activeToken.current!==token||d?.accountToken!==token||!d.next_before)return;loadingMoreRef.current=true;setLoadingMore(true);const request=requestGeneration.current;try{const next=await getAnalysisHistory(token,d.next_before);if(request!==requestGeneration.current||activeToken.current!==token)return;setD((old:any)=>old?.accountToken===token?{...old,items:[...old.items,...next.items.filter((item:any)=>!old.items.some((existing:any)=>existing.id===item.id))],next_before:next.next_before}:old);setError("")}catch(e){if(request===requestGeneration.current&&activeToken.current===token)setError(e instanceof Error?e.message:"Diğer analizler alınamadı.")}finally{if(request===requestGeneration.current&&activeToken.current===token){loadingMoreRef.current=false;setLoadingMore(false)}}},[token,d,busy]);
 return <FlatList style={s.page} contentContainerStyle={s.pad} data={d?.accountToken===token?d.items:[]} keyExtractor={x=>String(x.id)} refreshControl={<RefreshControl refreshing={busy&&(!d||d.accountToken===token)} onRefresh={()=>void load()}/>} onEndReachedThreshold={0.35} onEndReached={()=>void loadMore()} ListFooterComponent={loadingMore?<Text style={s.muted}>Diğer analizler yükleniyor...</Text>:!!error&&d?.accountToken===token&&d.items?.length>0?<Pressable accessibilityRole="button" onPress={()=>void loadMore()} style={s.btn}><Text style={s.btnT}>Diğer analizleri yeniden dene</Text></Pressable>:null} renderItem={({item})=><Pressable onPress={()=>nav.navigate("AnalysisResult",{id:item.id})} style={card}><View style={s.row}><Text style={s.title}>{item.patient_name||"Hasta"}</Text><Text style={s.pill}>{item.status}</Text></View><Text style={s.body}>{item.tooth_number?"Diş "+item.tooth_number+" · ":""}{item.clinical_notes||"Görüntü analizi"}</Text><Text style={s.meta}>{new Date(item.created_at).toLocaleString("tr-TR")}</Text></Pressable>} ListHeaderComponent={<View style={{marginBottom:12}}><Text style={s.big}>Analiz geçmişi</Text>{!!error&&(!d||d.accountToken===token)&&<Text accessibilityRole="alert" style={{color:C.red,marginTop:8}}>{error}</Text>}</View>} ListEmptyComponent={!busy&&(!d||d.accountToken===token)?<View><Empty title={error?"Analizler yüklenemedi":"Henüz analiz yok"} sub={error?"Bağlantıyı kontrol edip yeniden deneyin.":"Dental AI ile yaptığın analizler burada tutulur."}/>{!!error&&<Pressable accessibilityRole="button" onPress={()=>void load()} style={s.btn}><Text style={s.btnT}>Yeniden dene</Text></Pressable>}</View>:null}/>}

export function ExpertDirectory({token,navigation,patientId}:{token:string;navigation:any;patientId?:number}){
 const{lastEvent}=useRealtime();
 const[data,setData]=useState<{items:Expert[];accountToken:string}|null>(null);
 const[q,setQ]=useState(""),[busy,setBusy]=useState(true),[error,setError]=useState("");
 const[specialtyPick,setSpecialtyPick]=useState(""),[availableOnly,setAvailableOnly]=useState(false);
 const[watches,setWatches]=useState<AvailabilityWatch[]>([]),[watchNotice,setWatchNotice]=useState(""),[watchBusy,setWatchBusy]=useState(false);
 useEffect(()=>{Promise.resolve().then(()=>getAvailabilityWatch(token)).then(v=>{if(activeToken.current===token)setWatches(v)}).catch(()=>{})},[token]);
 function requestWatch(){
  const specialty=q.trim()||specialtyPick;if(!specialty||watchBusy)return;
  setWatchBusy(true);setWatchNotice("");setError("");
  createAvailabilityWatch(token,specialty).then(v=>{if(activeToken.current===token){setWatches(v.watches||[]);setWatchNotice("Bu branşta uzman müsait olduğunda bildirim isteğiniz kaydedildi.")}}).catch(e=>{if(activeToken.current===token)setError(e instanceof Error?e.message:"Bildirim isteği kaydedilemedi.")}).finally(()=>{if(activeToken.current===token)setWatchBusy(false)});
 }
 const seq=useRef(0),activeToken=useRef(token);if(activeToken.current!==token){activeToken.current=token;seq.current++;}
 const load=useCallback(async()=>{
  const request=++seq.current;
  setBusy(true);setError("");
  try{
   const result=await getExperts(token,q.trim(),{specialty:specialtyPick,available:availableOnly});
   if(request===seq.current&&activeToken.current===token)setData({items:result.items,accountToken:token});
  }catch(e){
   if(request===seq.current&&activeToken.current===token)setError(e instanceof Error?e.message:"Uzmanlar yüklenemedi.");
  }finally{
   if(request===seq.current&&activeToken.current===token)setBusy(false);
  }
 },[token,q,specialtyPick,availableOnly]);
 useEffect(()=>{setData(null);setError("");setBusy(true)},[token]);
 useEffect(()=>{
  const timeout=setTimeout(()=>{void load()},q.trim()?300:0);
  return()=>{clearTimeout(timeout);seq.current++};
 },[load]);
 useEffect(()=>{
  if(lastEvent&&["PROFILE_UPDATED","PROFILE_PHOTO_UPDATED"].includes(String(lastEvent.event_type||lastEvent.type)))void load();
 },[lastEvent,load]);
 return <View style={s.page}>
  <View style={s.pad}>
   <Text style={s.big}>Uzmandan Destek Al</Text>
   <Text style={s.muted}>Doğrulanmış uzmanlarla vaka danışmanlığı.</Text>
   <TextInput value={q} onChangeText={setQ} onSubmitEditing={()=>void load()} returnKeyType="search" placeholder="Uzman, branş veya kurum ara" placeholderTextColor={C.muted} style={s.input}/>
   <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{marginVertical:10}}>{["",...(Array.isArray(EXPERT_SPECIALTIES)?EXPERT_SPECIALTIES:[])].map(value=><Pressable key={value||"all"} accessibilityRole="radio" accessibilityState={{checked:specialtyPick===value}} disabled={busy} onPress={()=>setSpecialtyPick(current=>current===value?"":value)} style={{paddingVertical:7,paddingHorizontal:12,borderRadius:16,borderWidth:1,borderColor:specialtyPick===value?C.navy:C.line,backgroundColor:specialtyPick===value?C.soft:C.white,marginRight:8}}><Text style={{color:C.navy,fontSize:12,fontWeight:"700"}}>{value||"Tümü"}</Text></Pressable>)}</ScrollView>
   <Pressable accessibilityRole="switch" accessibilityState={{checked:availableOnly}} disabled={busy} onPress={()=>setAvailableOnly(v=>!v)} style={{flexDirection:"row",alignItems:"center",marginBottom:10}}><Text style={[s.meta,{fontWeight:"800",color:availableOnly?C.navy:C.muted}]}>{availableOnly?"✓ Yalnız müsait uzmanlar":"Yalnız müsait uzmanlar"}</Text></Pressable>
   {!!error&&<View><Text style={{color:C.red,marginBottom:8}}>{error}</Text><Btn title="Tekrar dene" onPress={()=>void load()}/></View>}
  </View>
  {busy?<View style={s.center}><ActivityIndicator color={C.navy}/></View>:
  <FlatList keyboardShouldPersistTaps="handled" contentContainerStyle={s.pad} data={data?.accountToken===token?data.items:[]} keyExtractor={x=>String(x.user_id)}
   refreshControl={typeof RefreshControl!=="undefined"?<RefreshControl refreshing={busy} onRefresh={()=>void load()} tintColor={C.navy}/>:undefined}
   ListEmptyComponent={<View>{(()=>{const inList=Array.isArray(EXPERT_SPECIALTIES)&&EXPERT_SPECIALTIES.includes(q.trim());return <><Empty title={inList?"Bu branşta şu an müsait uzman bulunamadı":"Uzman bulunamadı"} sub="Arama kelimelerini değiştirebilirsin."/>{inList&&<Btn title={watchBusy?"Kaydediliyor…":"Müsait olduğunda haber ver"} disabled={watchBusy} onPress={requestWatch}/>}{!!watchNotice&&<Text style={[s.muted,{textAlign:"center",marginTop:8}]}>{watchNotice}</Text>}{!!watches.length&&!inList&&<Text style={[s.muted,{textAlign:"center",marginTop:8}]}>Aktif bildirim abonelikleriniz: {watches.map(w=>w.specialty).join(", ")}</Text>}</>})()}</View>}
   renderItem={({item})=><Pressable accessibilityRole="button" style={card} onPress={()=>navigation.navigate("ExpertProfile",{id:item.user_id,name:item.display_name,patientId})}>
    <View style={s.row}><View style={{flex:1}}>
     <Text style={s.title}>{item.display_name}</Text>
     <Text style={s.body}>{item.academic_title||"Uzman Diş Hekimi"} · {item.specialty}</Text>
     <Text style={s.meta}>{item.institution||"Kurum belirtilmemiş"}{item.rating_avg?" · ★ "+item.rating_avg:""}</Text>
    </View><Text style={[s.availability,item.availability==="AVAILABLE"&&{color:C.green}]}>{item.availability==="AVAILABLE"?"Müsait":"Pasif"}</Text></View>
   </Pressable>}/>}
 </View>
}

export function NewConsultation(props:{token:string;userId:number;route:any;navigation:any}){return <NativeConsultationRequest {...props}/>}

export 
const CHAT_FILTERS=[{key:"all",label:"Tümü"},{key:"unread",label:"Okunmamış"},{key:"waiting",label:"Bekleyen"},{key:"missed",label:"Kaçırılan"},{key:"history",label:"Geçmiş"}] as const;
type ChatFilter=typeof CHAT_FILTERS[number]["key"];
const normalizeChat=(value:unknown)=>String(value??"").toLocaleLowerCase("tr-TR");
function chatFilterMatch(item:Consultation,filter:ChatFilter){
 const status=String(item.status_key||item.status||"").toUpperCase();
 if(filter==="unread")return Number(item.unread_count||0)>0;
 if(filter==="waiting")return ["WAITING","ACTION_REQUIRED","NEW_REQUEST","REQUESTED","PROPOSED","WAITING_START"].includes(status);
 if(filter==="missed")return ["MISSED","DELAYED","EXPIRED","EXPERT_TIMEOUT","PROPOSAL_EXPIRED"].includes(status);
 if(filter==="history")return ["HISTORY","CLOSED","EXPERT_COMPLETED","COMPLETED","CANCELLED","REJECTED","PROPOSAL_REJECTED"].includes(status);
 return true;
}
export function Consultations({token,userId,navigation}:{token:string;userId:number;navigation:any}){
 const[search,setSearch]=useState(""),[filter,setFilter]=useState<ChatFilter>("all");
 const{lastEvent,lastEventId}=useRealtime(),isFocused=useIsFocused();
 const lastProcessedEventId=useRef(0);
 const pages=usePagedRecords<Consultation>(token,before=>getConsultations(token,before),false,true);
 const{items:data,setItems:setData,refresh:load}=pages;
 useEffect(()=>{if(isFocused)void load()},[isFocused,load]);
 useEffect(()=>{setSearch("");setFilter("all")},[token]);
 useEffect(()=>{
  if(!lastEvent)return;
  const eventId=Number(lastEvent.event_id||lastEvent.id||lastEventId||0);
  if(Number.isSafeInteger(eventId)&&eventId>0){
   if(eventId<=lastProcessedEventId.current)return;
   const gap=lastProcessedEventId.current>0&&eventId>lastProcessedEventId.current+1;
   lastProcessedEventId.current=eventId;
   if(gap){if(isFocused)void load();return;}
  }
  const result=applyConsultationInboxEvent(data,lastEvent,userId);
  if(result.refresh){if(isFocused)void load();return;}
  if(result.changed)setData(result.items);
 },[lastEvent,lastEventId,data,load,setData,userId,isFocused]);
 const items=data.filter(item=>chatFilterMatch(item,filter)&&[item.other_display_name,item.specialty,item.question,item.last_message,String(item.id)].some(value=>normalizeChat(value).includes(normalizeChat(search.trim())))).sort((a,b)=>{
  const priority=(x:Consultation)=>["NEW_REQUEST","ACTION_REQUIRED"].includes(String(x.status_key||x.status).toUpperCase())?1:0;
  return priority(b)-priority(a)||Date.parse(b.last_message_at||b.requested_at||"")-Date.parse(a.last_message_at||a.requested_at||"");
 });
 return <FlatList style={s.page} contentContainerStyle={s.pad} data={items} keyExtractor={x=>String(x.id)}
 ListHeaderComponent={<View><View style={{flexDirection:"row",alignItems:"center",justifyContent:"space-between",marginBottom:12}}><View><Text style={s.big}>Mesajlar</Text><Text style={s.muted}>Uzman desteği · Vaka görüşmeleri</Text></View><Pressable accessibilityRole="button" onPress={()=>navigation.navigate("ExpertDirectory")} style={{backgroundColor:C.navy,borderRadius:12,padding:12}}><Text style={s.btnT}>＋ Uzman bul</Text></Pressable></View><DeletedChatButton token={token} onRestored={load}/><TextInput accessibilityLabel="Sohbetlerde ara" placeholder="Sohbetlerde ara" placeholderTextColor={C.muted} style={[s.input,{marginTop:0,marginBottom:12}]} value={search} onChangeText={setSearch} autoCorrect={false}/><ScrollView horizontal showsHorizontalScrollIndicator={false} style={{marginBottom:16}}>{CHAT_FILTERS.map(f=><Pressable key={f.key} accessibilityRole="button" accessibilityState={{selected:filter===f.key}} onPress={()=>setFilter(f.key)} style={{paddingHorizontal:14,paddingVertical:10,marginRight:7,borderRadius:20,backgroundColor:filter===f.key?C.navy:C.white,borderWidth:1,borderColor:C.line}}><Text style={{color:filter===f.key?C.white:C.text,fontWeight:"700"}}>{f.label}</Text></Pressable>)}</ScrollView></View>}
 ListFooterComponent={<><Text style={{color:C.red}}>{pages.error}</Text>{pages.error&&<Btn title="Tekrar dene" onPress={pages.refresh}/>} {pages.hasMore&&<Btn title={pages.busy?"Yükleniyor…":"Daha fazla görüşme"} disabled={pages.busy} onPress={pages.loadMore}/>}</>}
 refreshControl={<RefreshControl refreshing={pages.busy} onRefresh={load}/>}
 renderItem={({item})=><Pressable accessibilityRole="button" accessibilityLabel={item.other_display_name+" görüşmesini aç"} style={[card,{flexDirection:"row",alignItems:"center",gap:12,paddingVertical:14}]} onPress={()=>navigation.navigate("ConsultationChat",{id:item.id})}><View style={{height:46,width:46,borderRadius:23,backgroundColor:"#E8F0F8",alignItems:"center",justifyContent:"center"}}><Text style={{color:C.navy,fontSize:19,fontWeight:"800"}}>{(item.other_display_name||"U").slice(0,1).toLocaleUpperCase("tr-TR")}</Text></View><View style={{flex:1}}><View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center",gap:6}}><Text style={[s.title,{flexShrink:1}]} numberOfLines={1}>{item.other_display_name||"Kullanıcı"}</Text><Text style={s.meta}>{item.last_message_at?new Date(item.last_message_at).toLocaleTimeString("tr-TR",{hour:"2-digit",minute:"2-digit"}):""}</Text></View><Text style={s.meta} numberOfLines={1}>{item.specialty} · Vaka #{item.id}</Text><Text style={s.body} numberOfLines={2}>{item.last_message||item.question||"Klinik içerik"}</Text><View style={{flexDirection:"row",alignItems:"center",marginTop:5,gap:8}}><Text style={[s.pill,String(item.status_key||item.status).toUpperCase()==="ACTIVE"&&{backgroundColor:"#ECFDF5",color:"#047857"},["NEW_REQUEST","ACTION_REQUIRED"].includes(String(item.status_key||item.status).toUpperCase())&&{backgroundColor:"#FFF7ED",color:"#C2410C"},["MISSED","DELAYED"].includes(String(item.status_key||item.status).toUpperCase())&&{backgroundColor:"#FEF2F2",color:"#B91C1C"}]}>{item.status_label||item.status}</Text>{Number(item.unread_count||0)>0&&<Text style={{color:C.navy,fontWeight:"900"}}>{Number(item.unread_count||0)}</Text>}</View></View></Pressable>}
 ListEmptyComponent={<Empty title={search||filter!=="all"?"Eşleşen görüşme yok":"Henüz görüşmeniz yok"} sub={pages.hasMore?"Diğer görüşmeleri yükleyerek aramaya devam edin.":"Uzman desteği görüşmeleriniz burada görünecek."}/>}/>;
}
const CHAT_REPORT_REASONS=[["HARASSMENT","Taciz"],["PROFANITY","Hakaret veya küfür"],["SPAM","İstenmeyen içerik"],["INAPPROPRIATE","Uygunsuz davranış"],["OTHER","Diğer"]] as const;
type ChatReportReason=(typeof CHAT_REPORT_REASONS)[number][0];
export function ConsultationChat({token,route,userId}:{token:string;route:any;userId:number}){
 const navigation:any=useNavigation();const id=Number(route.params.id),{lastEvent,lastEventId,connected}=useRealtime(),isFocused=useIsFocused();
 const[data,setData]=useState<any>(),[text,setText]=useState(""),[replyTo,setReplyTo]=useState<number|null>(null),[olderBusy,setOlderBusy]=useState(false),[sendBusy,setSendBusy]=useState(false),[sendError,setSendError]=useState(""),[attachOpen,setAttachOpen]=useState(false);
 const[annotateMessage,setAnnotateMessage]=useState<ChatMessage|null>(null),[annotateText,setAnnotateText]=useState(""),[annotateBusy,setAnnotateBusy]=useState(false);
 const[safetyOpen,setSafetyOpen]=useState(false),[safetyBusy,setSafetyBusy]=useState(false),[reportReason,setReportReason]=useState<ChatReportReason|"" >(""),[reportDetail,setReportDetail]=useState("");
 const activeScope=useRef(token+":"+userId+":"+id);activeScope.current=token+":"+userId+":"+id;
 const [preparedAttachment,setPreparedAttachment]=useState<{file:ChatFile;nonce:string;scope:string}|null>(null);
 const requestSeq=useRef(0),sending=useRef(false),draftRevision=useRef(0),pending=useRef<{content:string;id:string;scope:string;replyTo:number|null}|null>(null);
 const draftKey="dai.consultation.draft."+userId+"."+id,pendingKey="dai.consultation.pending."+userId+"."+id,intentScope=userId+":"+id;
 const visibleData=data?.accountScope===activeScope.current?data:null;
 const chatStatus=String(visibleData?.case?.status||"").toUpperCase();
 const waitingStart=chatStatus==="WAITING_START"&&Number(visibleData?.case?.requester_user_id)===userId&&!!visibleData?.case?.consultation_start_deadline&&Date.parse(visibleData.case.consultation_start_deadline)>Date.now();
 const canCompose=!!visibleData&&!visibleData.case?.messages_deleted_at&&!visibleData.case?.inbox_deleted&&!visibleData.case?.blocked_either&&!waitingStart&&["ACTIVE","WAITING_START","EXPERT_COMPLETED","DISPUTE"].includes(chatStatus);
 const [draftReady,setDraftReady]=useState(false),[pendingMessage,setPendingMessage]=useState(false);
 const lastReadRequest=useRef<{scope:string;id:number}|null>(null);
 const catchUpPromise=useRef<Promise<void>|null>(null),catchUpAgain=useRef(false),catchUpRef=useRef<(after?:number,ready?:boolean)=>Promise<void>>(async()=>{});
 const messageCursor=useRef(0),lastProcessedEventId=useRef(0);
 const latestMessageId=visibleData?.messages?.length?visibleData.messages[visibleData.messages.length-1].id:null;
 const hasVisibleCase=!!visibleData?.case;
 const load=useCallback(async()=>{
  const request=++requestSeq.current,scope=activeScope.current;
  try{
   const result=await getConsultation(token,id);
   if(request!==requestSeq.current||scope!==activeScope.current)return;
   const incoming=result.case?.messages_deleted_at?[]:(result.messages||[]);
   const latest=incoming.reduce((max,m)=>Math.max(max,Number(m.id)||0),0);
   messageCursor.current=result.case?.messages_deleted_at?0:Math.max(messageCursor.current,latest);
   setData((previous:any)=>({...result,accountScope:scope,
    messages:mergeConsultationMessages(incoming,previous?.accountScope===scope?previous.messages||[]:[]),
    next_before:result.case?.messages_deleted_at?null:(previous?.accountScope===scope&&previous.next_before!==undefined?previous.next_before:result.next_before)}));
   if(!result.case?.messages_deleted_at)void catchUpRef.current(latest,true);
  }catch(e){if(request===requestSeq.current&&scope===activeScope.current)setSendError(e instanceof Error?e.message:"Görüşme yüklenemedi.")}
 },[token,id,userId]);
 const catchUpMessages=useCallback(async(afterOverride?:number,ready=false)=>{
  if(!isFocused||!connected||(!hasVisibleCase&&!ready))return;
  const activeCatchUp=catchUpPromise.current;
  if(activeCatchUp){catchUpAgain.current=true;return activeCatchUp;}
  const scope=activeScope.current,generation=requestSeq.current;
  catchUpAgain.current=false;
  const task=(async()=>{
   let cursor=Math.max(messageCursor.current,Number.isSafeInteger(afterOverride)?Number(afterOverride):0);
   for(let pageIndex=0;pageIndex<5;pageIndex++){
    const page=await getConsultationUpdates(token,id,cursor);
    if(scope!==activeScope.current||generation!==requestSeq.current)return;
    if(page.case?.messages_deleted_at){
     messageCursor.current=0;
     setData((previous:any)=>previous?.accountScope!==scope?previous:{...previous,case:{...previous.case,...page.case},messages:[],next_before:null});
     break;
    }
    setData((previous:any)=>previous?.accountScope!==scope?previous:{
     ...previous,case:{...previous.case,...page.case},
     messages:mergeConsultationMessages(previous.messages||[],page.messages||[]),
    });
    if(page.has_more){
     if(page.next_after===null||page.next_after<=cursor)throw Error("Yeni mesaj sayfalaması ilerlemedi.");
     cursor=page.next_after;
     messageCursor.current=Math.max(messageCursor.current,cursor);
     if(pageIndex===4)catchUpAgain.current=true;
    }else{
     if(page.messages.length){
      cursor=Math.max(cursor,page.messages[page.messages.length-1].id);
      messageCursor.current=Math.max(messageCursor.current,cursor);
     }
     break;
    }
   }
  })();
  catchUpPromise.current=task;
  try{await task}catch(e){if(scope===activeScope.current)setSendError(e instanceof Error?e.message:"Yeni mesajlar alınamadı. Tekrar deneyin.")}
  finally{
   if(catchUpPromise.current===task)catchUpPromise.current=null;
   if(catchUpAgain.current&&generation===requestSeq.current){catchUpAgain.current=false;void catchUpRef.current();}
  }
 },[token,id,isFocused,connected,hasVisibleCase]);
 catchUpRef.current=catchUpMessages;
 useEffect(()=>{setData(null);setSendError("");setSendBusy(false);setReplyTo(null);setPendingMessage(false);sending.current=false;pending.current=null;messageCursor.current=0;lastProcessedEventId.current=0;catchUpAgain.current=false;void load();return()=>{requestSeq.current++;sending.current=false}},[load]);
 useEffect(()=>{let active=true;const revision=++draftRevision.current;setDraftReady(false);setText("");void Promise.all([SecureStore.getItemAsync(draftKey),SecureStore.getItemAsync(pendingKey)]).then(([draft,raw])=>{if(!active||draftRevision.current!==revision)return;let restored:any=null;try{restored=raw?JSON.parse(raw):null}catch{}if(restored){const valid=restored.version===1&&typeof restored.id==="string"&&/^[A-Za-z0-9_-]{16,96}$/.test(restored.id)&&restored.scope===intentScope&&(restored.replyTo===null||Number.isSafeInteger(restored.replyTo)&&restored.replyTo>0);if(valid){const restoredText=typeof draft==="string"&&draft.length<=4000?draft:"";pending.current={content:restoredText,id:restored.id,scope:intentScope,replyTo:restored.replyTo};setPendingMessage(true);setText(restoredText);setReplyTo(restored.replyTo);if(!restoredText)setSendError("Bekleyen mesaj taslağı bulunamadı. Yeni mesaj göndermeden önce görüşme geçmişini kontrol edin.")}else{setPendingMessage(true);setText(typeof draft==="string"?draft:"");setSendError("Bekleyen mesaj kaydı doğrulanamadı. Yeni gönderim güvenlik için kilitlendi.")}}else{setText(typeof draft==="string"?draft:"");setPendingMessage(false)}setDraftReady(true)}).catch(()=>{if(active&&draftRevision.current===revision)setDraftReady(true)});return()=>{active=false;draftRevision.current++}},[draftKey,pendingKey,intentScope,token]);
 useEffect(()=>{
  if(!isFocused||!latestMessageId||visibleData?.case?.messages_deleted_at)return;
  const scope=activeScope.current;
  if(lastReadRequest.current?.scope===scope&&lastReadRequest.current.id>=latestMessageId)return;
  lastReadRequest.current={scope,id:latestMessageId};
  void markConsultationRead(token,id,latestMessageId).catch(()=>{
   if(lastReadRequest.current?.scope===scope&&lastReadRequest.current.id===latestMessageId)lastReadRequest.current=null;
  });
 },[token,id,isFocused,latestMessageId,visibleData?.case?.messages_deleted_at]);
 async function loadOlder(){const cursor=visibleData?.next_before,scope=activeScope.current;if(!cursor||olderBusy)return;setOlderBusy(true);try{const page=await getConsultation(token,id,cursor);if(scope!==activeScope.current)return;setData((previous:any)=>previous?.accountScope!==scope||previous?.case?.messages_deleted_at?previous:{...previous,next_before:page.next_before??null,messages:mergeConsultationMessages(page.messages,previous.messages||[])});}catch(e){if(scope===activeScope.current)setSendError(e instanceof Error?e.message:"Önceki mesajlar yüklenemedi.")}finally{if(scope===activeScope.current)setOlderBusy(false)}}
 useEffect(()=>{
  if(!lastEvent)return;
  const eventId=Number(lastEvent.event_id||lastEvent.id||lastEventId||0);
  let gap=false;
  if(Number.isSafeInteger(eventId)&&eventId>0){
   if(eventId<=lastProcessedEventId.current)return;
   gap=lastProcessedEventId.current>0&&eventId>lastProcessedEventId.current+1;
   lastProcessedEventId.current=eventId;
  }
  const eventType=String(lastEvent.event_type||lastEvent.type||"");
  const payload=lastEvent.payload||{},eventCase=Number(payload.case_id||lastEvent.entity_id||0);
  if(eventCase===id&&eventType==="MESSAGE_CREATED"){
   const messageId=Number(payload.message_id);
   if(gap||!Number.isSafeInteger(messageId)||messageId>messageCursor.current)void catchUpMessages();
   return;
  }
  if(eventCase===id&&eventType==="CASE_STATUS_UPDATED"){
   setData((previous:any)=>{
    if(previous?.accountScope!==activeScope.current)return previous;
    const nextCase=applyConsultationChatEvent(previous.case||{},lastEvent,id,userId);
    return nextCase.messages_deleted_at?{...previous,case:nextCase,messages:[],next_before:null}:{...previous,case:nextCase};
   });
   if(gap)void catchUpMessages();
   return;
  }
  if(eventCase===id&&eventType==="CASE_READ"){
   setData((previous:any)=>previous?.accountScope!==activeScope.current?previous:{
    ...previous,case:applyConsultationChatEvent(previous.case||{},lastEvent,id,userId)
   });
   if(gap)void catchUpMessages();
   return;
  }
  if(eventCase===id&&["CASE_UPDATED","CASE_REPORT_CREATED"].includes(eventType)){void load();return}
  if(gap)void catchUpMessages();
 },[lastEvent,lastEventId,id,userId,load,catchUpMessages,setData]);
 useEffect(()=>{if(isFocused&&connected&&hasVisibleCase)void catchUpMessages()},[isFocused,connected,hasVisibleCase,catchUpMessages]);
 async function reconcilePending(){
  const intent=pending.current,scope=activeScope.current;if(!intent||intent.scope!==intentScope)return false;
  try{const receipt=await getConsultationMessageReceipt(token,id,intent.id);if(scope!==activeScope.current||pending.current?.id!==intent.id||(!receipt.message&&!receipt.deleted))return false;
   const saved=await SecureStore.getItemAsync(draftKey);if(saved===intent.content)await SecureStore.deleteItemAsync(draftKey);
   await SecureStore.deleteItemAsync(pendingKey);
   pending.current=null;setPendingMessage(false);setText(current=>current===intent.content?"":current);setReplyTo(null);
   if(scope===activeScope.current&&receipt.message){
    messageCursor.current=Math.max(messageCursor.current,receipt.message.id);
    setData((previous:any)=>previous?.accountScope!==scope?previous:{...previous,messages:mergeConsultationMessages(previous.messages||[],[receipt.message!])});
   }else if(scope===activeScope.current&&receipt.deleted)await load();
   return true;
  }catch{return false}
 }
 useEffect(()=>{if(draftReady&&isFocused&&connected&&pending.current)void reconcilePending()},[draftReady,isFocused,connected,token,id]);
 useEffect(()=>{if(visibleData?.case?.messages_deleted_at){pending.current=null;setPendingMessage(false);setText("");setReplyTo(null);void SecureStore.deleteItemAsync(draftKey).then(()=>SecureStore.deleteItemAsync(pendingKey)).catch(()=>{})}},[visibleData?.case?.messages_deleted_at,pendingKey,draftKey]);
 async function send(){
  const scope=activeScope.current,v=text.trim(),reply=replyTo,revisionAtSend=draftRevision.current;if(sending.current||!v||!canCompose||!draftReady)return;
  if(pending.current&&pending.current.scope===intentScope&&(pending.current.content!==v||pending.current.replyTo!==reply)){setSendError("Önce bekleyen mesajın sonucunu doğrulayın.");return}
  if(pendingMessage&&!pending.current){setSendError("Bekleyen mesaj kaydı doğrulanamadı. Önce görüşme geçmişini kontrol edin.");return}
  if(!pending.current||pending.current.scope!==intentScope)pending.current={content:v,scope:intentScope,replyTo:reply,id:"native-"+Crypto.randomUUID()};
  const intent=pending.current,messageId=intent.id;sending.current=true;setSendBusy(true);setPendingMessage(true);setSendError("");
  try{
   await SecureStore.setItemAsync(draftKey,v);
   await SecureStore.setItemAsync(pendingKey,JSON.stringify({version:1,id:intent.id,scope:intent.scope,replyTo:intent.replyTo}));
   if(scope!==activeScope.current)return;
   const result=await sendConsultationMessage(token,id,v,messageId,reply??undefined);
   if(scope!==activeScope.current)return;
   if(!result?.ok||!result?.message?.id)throw Error("Gönderim doğrulanamadı. Aynı mesaj anahtarı korunuyor.");
   const saved=await SecureStore.getItemAsync(draftKey);
   if(scope!==activeScope.current)return;
   if(saved===v&&draftRevision.current===revisionAtSend)await SecureStore.deleteItemAsync(draftKey);
   await SecureStore.deleteItemAsync(pendingKey);
   if(pending.current?.id===messageId)pending.current=null;setPendingMessage(false);
   setText(current=>current===v?"":current);setReplyTo(null);
   messageCursor.current=Math.max(messageCursor.current,result.message.id);
   setData((previous:any)=>previous?.accountScope!==scope?previous:{...previous,messages:mergeConsultationMessages(previous.messages||[],[result.message])});
  }catch(e){if(scope===activeScope.current){setSendError(e instanceof Error?e.message:"Mesaj gönderilemedi. Aynı istek anahtarı korunuyor.");void reconcilePending()}}
  finally{if(scope===activeScope.current){sending.current=false;setSendBusy(false)}}
 }
 async function submitAnnotation(){
  const target=annotateMessage,scope=activeScope.current;
  if(!target||annotateBusy||!annotateText.trim())return;
  const annotation_json=JSON.stringify({v:1,kind:"note",text:annotateText.trim()});
  setAnnotateBusy(true);setSendError("");
  try{
   await performChatAction(token,id,{action:"annotate",message_id:target.id,annotation_json});
   if(scope!==activeScope.current)return;
   setAnnotateMessage(null);setAnnotateText("");
   await load();
  }catch(e){if(scope===activeScope.current)setSendError(e instanceof Error?e.message:"İşaretleme eklenemedi.")}
  finally{if(scope===activeScope.current)setAnnotateBusy(false)}
 }
 async function submitSafety(kind:"block"|"unblock"|"report"){
  const scope=activeScope.current;
  if(safetyBusy)return;
  setSafetyBusy(true);setSendError("");
  try{
   if(kind==="report"){
    if(reportReason==="")return;
    await performChatAction(token,id,{action:"report",reason:reportReason,detail:reportDetail.trim().slice(0,500)});
   }else await performChatAction(token,id,{action:kind});
   if(scope!==activeScope.current)return;
   setSafetyOpen(false);setReportReason("");setReportDetail("");
   await load();
  }catch(e){if(scope===activeScope.current)setSendError(e instanceof Error?e.message:"Güvenlik işlemi tamamlanamadı.")}
  finally{if(scope===activeScope.current)setSafetyBusy(false)}
 }
 function confirmBlock(){
  Alert.alert("Karşılıklı mesajlaşma kapatılsın mı?","Bu görüşmede mesajlar iki taraf için de kapatılır. Bloklama rapor yerine geçmez; uygunsuz davranışı ayrıca raporlayabilirsin.",[{text:"Vazgeç",style:"cancel"},{text:"Kapat",style:"destructive",onPress:()=>void submitSafety("block")}]);
 }
 return <KeyboardAvoidingView style={s.page} behavior={Platform.OS==="ios"?"padding":"height"}>
 <View style={{backgroundColor:C.white,padding:14,borderBottomWidth:1,borderBottomColor:C.line}}><Text style={s.title}>{visibleData?.case?.other_display_name||"Güvenli görüşme"} · Vaka #{id}</Text><ChatActions key={token+":"+id} token={token} userId={userId} conversation={visibleData?.case} onChanged={load} onDeleted={()=>navigation.goBack()}/><Text style={s.muted}>{visibleData?.case?.specialty||"Uzman desteği"} · {consultationStatusLabel(visibleData?.case?.status)}</Text></View>
 {!!visibleData?.case?.shared_media?.length&&<View style={{padding:12}}><Text style={s.title}>Vakaya eklenen klinik görseller</Text><ScrollView horizontal>{visibleData.case.shared_media.map((media:{id:number;media_type:string})=><ChatImage key={token+":"+id+":"+media.id} token={token} caseId={id} message={{id:media.id} as ChatMessage} sourceOverride={sharedCaseImageSource(token,id,media.id)} canEdit={canCompose} onEdited={file=>{setReplyTo(null);setPreparedAttachment({file,nonce:file.uri,scope:activeScope.current})}}/>)}</ScrollView></View>}
 <FlatList style={s.page} contentContainerStyle={[s.pad,{paddingBottom:20}]} data={visibleData?.messages||[]} keyExtractor={(x:ChatMessage)=>String(x.id)} ListHeaderComponent={visibleData?.next_before?<Btn title={olderBusy?"Yükleniyor…":"Önceki mesajları yükle"} disabled={olderBusy} onPress={()=>void loadOlder()}/>:null}
 ListEmptyComponent={<Empty title={visibleData?"Henüz mesaj yok":"Görüşme yükleniyor"} sub="Bu görüşmenin mesajları yalnızca yetkili katılımcılara gösterilir."/>}
 renderItem={({item}:any)=><View style={[s.msg,item.sender_user_id===userId?s.mine:s.theirs]}>{!!item.reply_to_message_id&&<Text style={[s.meta,{color:C.navy,fontWeight:"700"}]}>↩ {consultationMessagePreview(visibleData?.messages?.find((m:ChatMessage)=>m.id===item.reply_to_message_id))}</Text>}{item.message_type==="IMAGE"?<ChatImage token={token} caseId={id} message={item} canEdit={canCompose} onEdited={file=>{setReplyTo(item.id);setPreparedAttachment({file,nonce:file.uri,scope:activeScope.current})}}/>:item.message_type==="ANNOTATION"?<Text style={s.body}>✎ İşaretlenmiş görüntü{(()=>{try{const a=JSON.parse(String((item as any).annotation_json||""));return a&&typeof a.text==="string"&&a.text?" · "+a.text:""}catch{return ""}})()}</Text>:item.message_type==="VOICE"||item.message_type==="FILE"?<NativeChatDocument key={token+":"+id+":"+item.id} token={token} caseId={id} message={item}/>:<Text style={s.body}>{item.content||"Klinik içerik"}</Text>}{item.sender_user_id===userId&&<Text style={s.meta}>{visibleData?.case?.other_read_at&&Date.parse(item.created_at)<=Date.parse(visibleData.case.other_read_at)?"✓✓ Okundu":"✓ Gönderildi"}</Text>}<View style={{flexDirection:"row",alignItems:"center",justifyContent:"space-between",gap:12}}><Text style={s.meta}>{new Date(item.created_at).toLocaleTimeString("tr-TR",{hour:"2-digit",minute:"2-digit"})}</Text><Pressable accessibilityRole="button" accessibilityLabel="Mesajı yanıtla" onPress={()=>setReplyTo(item.id)}><Text style={[s.meta,{color:C.navy,fontWeight:"800"}]}>↩ Yanıtla</Text></Pressable>{item.message_type==="IMAGE"&&canCompose&&<Pressable accessibilityRole="button" accessibilityLabel="Görüntüye işaretleme ekle" onPress={()=>{setAnnotateText("");setAnnotateMessage(item)}}><Text style={[s.meta,{color:C.navy,fontWeight:"800"}]}>✎ İşaretle</Text></Pressable>}</View></View>}/>
 {annotateMessage&&<View style={{position:"absolute",left:0,right:0,top:0,bottom:0,backgroundColor:"rgba(7,27,53,.6)",justifyContent:"flex-end"}}><View style={{backgroundColor:C.white,padding:16,borderTopLeftRadius:18,borderTopRightRadius:18}}><Text style={s.title}>Görüntüye işaretleme ekle</Text><Text style={s.muted}>Mesaj #{annotateMessage.id} için kısa bir işaretleme notu ekleyin; not sunucuda görüntüyle ilişkilendirilir.</Text><TextInput accessibilityLabel="İşaretleme notu" multiline maxLength={2000} value={annotateText} onChangeText={setAnnotateText} placeholder="İşaretleme notu (ör. sağ alt bölgede lezyon)" placeholderTextColor={C.muted} style={[s.input,{height:90,textAlignVertical:"top"}]}/><Btn title={annotateBusy?"Kaydediliyor…":"İşaretlemeyi Kaydet"} disabled={annotateBusy||!annotateText.trim()} onPress={()=>void submitAnnotation()}/><Btn title="Vazgeç" disabled={annotateBusy} onPress={()=>{setAnnotateMessage(null);setAnnotateText("")}}/></View></View>}
 {safetyOpen&&<View style={{position:"absolute",left:0,right:0,top:0,bottom:0,backgroundColor:"rgba(7,27,53,.6)",justifyContent:"flex-end"}}><View style={{backgroundColor:C.white,padding:16,borderTopLeftRadius:18,borderTopRightRadius:18}}><Text style={s.title}>Güvenlik ve Bloklama</Text>{!!visibleData?.case?.blocked_either?<><Text style={s.muted}>Bu görüşmede karşılıklı mesajlaşma kapatıldı. Bloklamayı yalnız siz koymuşsanız kaldırabilirsiniz; karşı tarafın bloklaması kaldırılamaz.</Text><Btn title={safetyBusy?"İşleniyor…":"Bloklamayı Kaldır"} disabled={safetyBusy} onPress={()=>void submitSafety("unblock")}/></>:<><Text style={s.muted}>Uygunsuz davranışı raporlayın; rapor destek sürecine eklenir. Gerekirse karşılıklı mesajlaşmayı da kapatabilirsiniz.</Text><View style={{flexDirection:"row",flexWrap:"wrap",gap:8,marginVertical:10}}>{CHAT_REPORT_REASONS.map(([value,label])=><Pressable key={value} accessibilityRole="radio" accessibilityState={{checked:reportReason===value}} disabled={safetyBusy} onPress={()=>setReportReason(value)} style={{paddingVertical:8,paddingHorizontal:12,borderRadius:16,borderWidth:1,borderColor:reportReason===value?C.navy:C.line,backgroundColor:reportReason===value?C.soft:C.white}}><Text style={{color:C.navy,fontSize:12,fontWeight:"700"}}>{reportReason===value?"✓ ":""}{label}</Text></Pressable>)}</View><TextInput accessibilityLabel="Rapor detayı" multiline maxLength={500} value={reportDetail} onChangeText={setReportDetail} placeholder="Kısa açıklama (isteğe bağlı, en fazla 500 karakter)" placeholderTextColor={C.muted} style={[s.input,{height:80,textAlignVertical:"top"}]}/><Btn title={safetyBusy?"Gönderiliyor…":"Raporu Gönder"} disabled={safetyBusy||!reportReason} onPress={()=>void submitSafety("report")}/><Text style={s.muted}>Karşılıklı mesajlaşmayı kapatmak rapor yerine geçmez.</Text><Btn title="Karşılıklı Mesajlaşmayı Kapat" disabled={safetyBusy} onPress={confirmBlock}/></>}<Btn title="Vazgeç" disabled={safetyBusy} onPress={()=>setSafetyOpen(false)}/></View></View>}
 {waitingStart&&<Text style={{color:C.muted,paddingHorizontal:16,paddingVertical:8}}>Mesajlaşma, belirlenen görüşme başlangıcında açılacak.</Text>}
 {!!visibleData?.case?.messages_deleted_at&&<Text style={{color:C.red,paddingHorizontal:16,paddingVertical:8}}>Bu görüşmenin mesajları kaldırılmış.</Text>}
 {!!pendingMessage&&<Text style={{color:C.muted,paddingHorizontal:16,paddingVertical:5}}>Gönderim sonucu doğrulanıyor; aynı istek anahtarı korunuyor.</Text>}
 {!!sendError&&<Pressable accessibilityRole="button" onPress={()=>void reconcilePending().then(()=>load())}><Text style={{color:C.red,paddingHorizontal:16}}>{sendError} · Gönderim sonucunu kontrol et</Text></Pressable>}
 <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"center",paddingHorizontal:16,paddingVertical:6}}><Pressable accessibilityRole="button" accessibilityLabel="Güvenlik ve bloklama seçenekleri" disabled={safetyBusy} onPress={()=>setSafetyOpen(true)}><Text style={[s.meta,{color:C.navy,fontWeight:"800"}]}>🛡 Güvenlik ve Bloklama</Text></Pressable>{!!visibleData?.case?.blocked_either&&<Text style={[s.meta,{color:C.red,fontWeight:"800"}]}>Karşılıklı mesajlaşma kapalı</Text>}</View>
 {!!replyTo&&<View style={{backgroundColor:C.soft,padding:10,flexDirection:"row",alignItems:"center",justifyContent:"space-between"}}><Text style={{flex:1,color:C.navy}} numberOfLines={2}>↩ {consultationMessagePreview(visibleData?.messages?.find((m:ChatMessage)=>m.id===replyTo))}</Text><Pressable accessibilityRole="button" accessibilityLabel="Yanıtı kaldır" onPress={()=>setReplyTo(null)}><Text style={{fontWeight:"800",color:C.red}}>✕</Text></Pressable></View>}<ChatPhotoComposer key={token+":"+id} token={token} userId={userId} caseId={id} replyTo={replyTo} prepared={preparedAttachment?.scope===activeScope.current?preparedAttachment:null} deleted={!!visibleData?.case?.messages_deleted_at} optionsOpen={attachOpen} disabled={!canCompose||!draftReady||sendBusy} onRefresh={load} onSent={async(message?:ChatMessage)=>{
 setReplyTo(null);
 if(message){
  const scope=activeScope.current;
  messageCursor.current=Math.max(messageCursor.current,message.id);
  setData((previous:any)=>previous?.accountScope!==scope?previous:{...previous,messages:mergeConsultationMessages(previous.messages||[],[message])});
 }else await load();
}}/><View style={s.composer}><Pressable accessibilityRole="button" accessibilityLabel="Dosya ekle" accessibilityHint="Fotoğraf, kamera veya PDF/Ses ekleme seçeneklerini açar ve kapatır" disabled={!canCompose||!draftReady||sendBusy} onPress={()=>setAttachOpen(v=>!v)} style={s.plusBtn}><Text style={s.plusT}>＋</Text></Pressable><TextInput style={[s.input,{flex:1,marginTop:0,maxHeight:120}]} multiline maxLength={4000} value={text} onChangeText={v=>{draftRevision.current++;setText(v);pending.current=null;void SecureStore.setItemAsync(draftKey,v).catch(()=>{})}} editable={!sendBusy&&!pendingMessage&&canCompose&&draftReady} placeholder="Mesaj yaz..." placeholderTextColor={C.muted}/><Pressable accessibilityRole="button" accessibilityLabel="Gönder" accessibilityHint="Mesajı gönderir; bekleyen mesaj varsa aynı anahtarla tekrar dener" style={[s.send,(!canCompose||!draftReady||sendBusy||!text.trim())&&{opacity:.5}]} onPress={()=>void send()} disabled={!canCompose||!draftReady||sendBusy||!text.trim()}><Text style={s.sendArrow}>↑</Text></Pressable></View>
 </KeyboardAvoidingView>;
}

export function Academic({token}:{token:string}){const{lastEvent}=useRealtime();const[course,setCourse]=useState<Course|null>(null),[q,setQ]=useState(""),[answer,setAnswer]=useState(""),[busy,setBusy]=useState(false);const selectedCourse=useRef<number|undefined>(course?.id);selectedCourse.current=course?.id;const academicScope=useRef(token+":"+(course?.id||0));academicScope.current=token+":"+(course?.id||0);const askInFlight=useRef(false);const askRequest=useRef(0);const coursePages=usePagedRecords<Course>(token,before=>getCourses(token,before),false,true);const courses=coursePages.items;useEffect(()=>{setCourse(null);setQ("");setAnswer("")},[token]);useEffect(()=>{if(!course&&courses.length)setCourse(courses[0]);else if(course&&courses.length&&!courses.some(item=>item.id===course.id)&&!coursePages.hasMore)setCourse(courses[0]);else if(course&&!courses.length&&!coursePages.busy&&!coursePages.error)setCourse(null)},[courses,course,coursePages.hasMore,coursePages.busy,coursePages.error]);const messagePages=usePagedRecords(token+":"+(course?.id||0),before=>course?getAcademicMessages(token,course.id,before):Promise.resolve({items:[],next_before:null}),true);const messages=messagePages.items;useEffect(()=>{askRequest.current++;askInFlight.current=false;setBusy(false);setAnswer("")},[token,course?.id]);useEffect(()=>{const type=String(lastEvent?.event_type||lastEvent?.type||"");const courseId=Number(lastEvent?.payload?.course_id||lastEvent?.entity_id||0);if(["STUDY_MATERIAL_CREATED","STUDY_MATERIAL_UPDATED","STUDY_COURSE_UPDATED"].includes(type)){coursePages.refresh();return}if(type==="ACADEMIC_MESSAGE_CREATED"&&course?.id===courseId)messagePages.refresh()},[lastEvent,coursePages.refresh,messagePages.refresh,course?.id]);async function ask(){if(!course||!q.trim()||askInFlight.current)return;askInFlight.current=true;const request=++askRequest.current,scope=academicScope.current,courseId=course.id,question=q.trim();setBusy(true);setAnswer("");try{const r=await askAcademic(token,courseId,question);if(request!==askRequest.current||scope!==academicScope.current)return;const next=r.answer||r.message||r.raw||JSON.stringify(r);setAnswer(next);messagePages.refresh()}catch(e:any){if(request===askRequest.current&&scope===academicScope.current)setAnswer(e?.message||"Yanıt alınamadı.")}finally{if(request===askRequest.current&&scope===academicScope.current){askInFlight.current=false;setBusy(false)}}}return <ScrollView style={s.page} contentContainerStyle={s.pad}><Text style={s.big}>Akademik AI</Text><Text style={s.muted}>Kendi diş hekimliği notların üzerinden çalışan Academic V2.</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} style={{marginVertical:14}}>{courses.map(x=><Pressable key={x.id} onPress={()=>setCourse(x)} style={[s.course,course?.id===x.id&&s.courseActive]}><Text style={s.courseT}>{x.title}</Text><Text style={s.meta}>{x.material_count} kaynak</Text></Pressable>)}</ScrollView>{!!coursePages.error&&<><Text style={{color:C.red}}>{coursePages.error}</Text><Btn title="Dersleri tekrar yükle" onPress={coursePages.refresh}/></>}{coursePages.hasMore&&<Btn title={coursePages.busy?"Yükleniyor…":"Daha fazla ders"} disabled={coursePages.busy} onPress={coursePages.loadMore}/>} {!course?<Empty title="Ders bulunamadı" sub="Önce akademik ders notu ekle."/>:<><TextInput value={q} onChangeText={setQ} multiline placeholder="Notlarından ne öğrenmek istiyorsun?" placeholderTextColor={C.muted} style={[s.input,{height:110,textAlignVertical:"top"}]}/><Btn title={busy?"Yanıt hazırlanıyor...":"Sor"} disabled={busy} onPress={ask}/>{!!messagePages.error&&<><Text style={{color:C.red}}>{messagePages.error}</Text><Btn title="Mesajları tekrar yükle" onPress={messagePages.refresh}/></>}{messagePages.hasMore&&<Btn title={messagePages.busy?"Yükleniyor…":"Önceki mesajları yükle"} disabled={messagePages.busy} onPress={messagePages.loadMore}/>} {messages.length>0&&<View style={{marginTop:14}}>{messages.map(x=><View key={x.id} style={[card,x.role==="user"&&{backgroundColor:C.soft}]}><Text style={s.title}>{x.role==="user"?"Sen":"Akademik AI"}</Text><Text style={s.body}>{x.content}</Text></View>)}</View>}{!!answer&&!messages.some(message=>message.role.toLowerCase()==="assistant"&&message.content===answer)&&<View style={card}><Text style={s.title}>Akademik AI</Text><Text style={s.body}>{answer}</Text></View>}</>}</ScrollView>}

export function RealtimeBadge({onEvent}:{token?:string;onEvent:(e:any)=>void}){const{lastEvent}=useRealtime();useEffect(()=>{if(lastEvent)onEvent(lastEvent)},[lastEvent,onEvent]);return null}
const s=StyleSheet.create({page:{flex:1,backgroundColor:C.bg},pad:{padding:16,paddingBottom:110},center:{flex:1,alignItems:"center",justifyContent:"center"},big:{fontSize:27,fontWeight:"900",color:C.navy,marginBottom:5},title:{fontSize:16,fontWeight:"900",color:C.text},body:{fontSize:14,color:C.text,lineHeight:20,marginTop:5},muted:{fontSize:13,color:C.muted,lineHeight:19},meta:{fontSize:11,color:C.muted,marginTop:7},row:{flexDirection:"row",alignItems:"center",gap:10},pill:{fontSize:10,fontWeight:"800",color:C.navy,backgroundColor:C.soft,paddingHorizontal:8,paddingVertical:5,borderRadius:10},btn:{height:46,borderRadius:13,backgroundColor:C.navy,alignItems:"center",justifyContent:"center",marginTop:12},btnT:{color:C.white,fontWeight:"800"},input:{height:50,borderWidth:1,borderColor:C.line,borderRadius:14,backgroundColor:C.white,paddingHorizontal:14,color:C.text,marginTop:14},empty:{alignItems:"center",justifyContent:"center",padding:35},emptyTitle:{fontSize:18,fontWeight:"900",color:C.navy,marginBottom:5},availability:{fontSize:11,fontWeight:"800",color:C.muted},msg:{maxWidth:"82%",padding:12,borderRadius:16,marginBottom:9,backgroundColor:C.white,alignSelf:"flex-start"},mine:{alignSelf:"flex-end",backgroundColor:"#E8F0F8"},theirs:{alignSelf:"flex-start"},composer:{flexDirection:"row",gap:8,padding:10,borderTopWidth:1,borderTopColor:C.line,backgroundColor:C.white},send:{width:42,height:42,minWidth:42,borderRadius:21,backgroundColor:"#2563eb",alignItems:"center",justifyContent:"center"},sendArrow:{fontSize:24,lineHeight:26,color:"#fff",fontWeight:"800"},plusBtn:{width:42,height:42,minWidth:42,borderRadius:21,backgroundColor:"#eff6ff",alignItems:"center",justifyContent:"center"},plusT:{fontSize:24,color:"#2563eb"},course:{padding:12,borderRadius:14,backgroundColor:C.white,borderWidth:1,borderColor:C.line,marginRight:8,minWidth:120},courseActive:{borderColor:C.navy,backgroundColor:C.soft},courseT:{fontWeight:"800",color:C.text},mediaCard:{width:"48%",backgroundColor:C.white,borderRadius:15,padding:7,marginBottom:10},media:{width:"100%",height:150,borderRadius:10,backgroundColor:C.soft}});

