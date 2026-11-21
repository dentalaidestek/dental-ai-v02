import React,{useEffect,useRef,useState} from "react";
import {ActivityIndicator,Image,Pressable,ScrollView,Text,TextInput,View} from "react-native";
import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";
import {ApiError,getPatient,getPatients,Patient} from "./api";
import {ConsultationRequestContext,ConsultationRequestPayload,createConsultation,getConsultationRequestContext,getConsultationRequestStatus,getMedia} from "./modernApi";
import {usePagedRecords} from "./usePagedRecords";

const color={navy:"#071B35",muted:"#63748A",line:"#E1E7EF",red:"#B42318"};
type Draft={summary:string;opinion:string;question:string;tooth:string;urgency:string;patientId:number|null;mediaIds:number[];pending?:ConsultationRequestPayload};
const blank=(patientId:number|null):Draft=>({summary:"",opinion:"",question:"",tooth:"",urgency:"NORMAL",patientId,mediaIds:[]});
function Button({title,onPress,disabled=false}:{title:string;onPress:()=>void;disabled?:boolean}){
 return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={{padding:13,minHeight:44,borderWidth:1,borderColor:color.line,borderRadius:12,marginTop:8,opacity:disabled ? 0.5 : 1}}><Text style={{color:color.navy,fontWeight:"700"}}>{title}</Text></Pressable>;
}
export default function NativeConsultationRequest({token,userId,route,navigation}:{token:string;userId:number;route:any;navigation:any}){
 const expertId=Number(route.params?.expert?.user_id||0);
 const initialId=Number.isSafeInteger(route.params?.patientId)&&route.params.patientId>0?route.params.patientId:null;
 const key="dai.consultation.request."+userId+"."+expertId;
 const expectedScope=token+":"+userId+":"+expertId;
 const scope=useRef(expectedScope);scope.current=expectedScope;
 const [draft,setDraft]=useState<Draft>(blank(initialId)),[ready,setReady]=useState(false),[context,setContext]=useState<ConsultationRequestContext|null>(null),[contextError,setContextError]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState(""),[draftWarning,setDraftWarning]=useState(""),[patient,setPatient]=useState<Patient|null>(null),[patientError,setPatientError]=useState(""),[patientSearch,setPatientSearch]=useState(""),[search,setSearch]=useState(""),[picker,setPicker]=useState(false);
 const lock=useRef(false),writes=useRef<Promise<void>>(Promise.resolve()),pending=useRef<ConsultationRequestPayload|undefined>(undefined),contextSeq=useRef(0);
 const patients=usePagedRecords<Patient>(expectedScope+":"+search,async offset=>{
  const result=await getPatients(token,search,offset||0),next=(offset||0)+result.items.length;
  return {items:result.items,next_before:next<result.total?next:null};
 },false,true,"offset");
 const media=usePagedRecords<any>(expectedScope+":"+(draft.patientId||0),before=>draft.patientId?getMedia(token,draft.patientId,before):Promise.resolve({items:[],next_before:null}),false,true);
 function persist(value:Draft){
  const owner=scope.current;
  const next=writes.current.catch(()=>{}).then(async()=>{if(scope.current===owner)await SecureStore.setItemAsync(key,JSON.stringify(value))});
  writes.current=next;return next;
 }
 async function loadContext(){
  const owner=scope.current,sequence=++contextSeq.current;setContext(null);setContextError("");
  try{const result=await getConsultationRequestContext(token,expertId);if(scope.current===owner&&sequence===contextSeq.current)setContext(result)}
  catch(e){if(scope.current===owner&&sequence===contextSeq.current)setContextError(e instanceof Error?e.message:"Uzman bilgileri alınamadı.")}
 }
 useEffect(()=>{
  let active=true;const owner=expectedScope;
  setReady(false);setBusy(false);setContext(null);setError("");setDraftWarning("");setPatient(null);setPatientError("");setPicker(false);lock.current=false;pending.current=undefined;
  void(async()=>{
   let restored=blank(initialId);
   try{
    const raw=await SecureStore.getItemAsync(key);
    if(raw){
     const value=JSON.parse(raw);
     if(value&&["summary","opinion","question","tooth","urgency"].every(field=>typeof value[field]==="string")&&
        (value.patientId===null||Number.isSafeInteger(value.patientId)&&value.patientId>0)&&
        Array.isArray(value.mediaIds)&&value.mediaIds.every((id:unknown)=>Number.isSafeInteger(id)&&Number(id)>0)&&
        (!initialId||value.patientId===initialId)){
      restored=value;
      if(value.pending&&(!/^[A-Za-z0-9_-]{8,96}$/.test(value.pending.request_key||"")||value.pending.expert_user_id!==expertId))delete restored.pending;
     }
    }
   }catch{if(active&&scope.current===owner)setDraftWarning("Önceki taslak okunamadı. Göndermeden önce bilgileri kontrol edin.")}
   if(!active||scope.current!==owner)return;
   pending.current=restored.pending;setDraft(restored);setReady(true);void loadContext();
  })();
  return()=>{active=false};
 },[token,userId,expertId,initialId]);
 useEffect(()=>{if(!ready)return;const owner=expectedScope;void persist(draft).then(()=>{if(scope.current===owner)setDraftWarning("")}).catch(()=>{if(scope.current===owner)setDraftWarning("Taslak güvenli kaydedilemedi. Uygulamayı kapatmadan önce yeniden deneyin.")})},[draft,ready,key,expectedScope]);
 useEffect(()=>{
  let active=true;const id=draft.patientId,owner=expectedScope;setPatient(null);setPatientError("");
  if(id)void getPatient(token,id).then(result=>{if(active&&scope.current===owner)setPatient(result.patient)}).catch(e=>{if(active&&scope.current===owner)setPatientError(e instanceof Error?e.message:"Hasta doğrulanamadı.")});
  return()=>{active=false};
 },[token,draft.patientId,expectedScope]);
 const frozen=busy||!!draft.pending;
 function change(field:"summary"|"opinion"|"question"|"tooth"|"urgency",value:string){if(frozen)return;setError("");setDraft(previous=>({...previous,[field]:value}))}
 function choosePatient(value:Patient|null){if(frozen)return;setPatient(value);setPatientError("");setPicker(false);setDraft(previous=>({...previous,patientId:value?.id||null,mediaIds:[]}))}
 async function send(){
  if(lock.current||!ready)return;
  if(!pending.current&&(!context||!draft.summary.trim()||!draft.question.trim())){setError("Klinik bilgi ve uzmana sorunuz zorunlu; uzman bilgileri doğrulanmalıdır.");return}
  if(!pending.current&&draft.patientId&&patient?.id!==draft.patientId){setError("Seçili hasta henüz doğrulanmadı.");return}
  if(!pending.current&&!draft.patientId&&draft.mediaIds.length){setError("Görüntüler için bir hasta seçin.");return}
  const owner=expectedScope;lock.current=true;setBusy(true);setError("");
  try{
   if(pending.current){
    const status=await getConsultationRequestStatus(token,expertId,pending.current.request_key!);
    if(scope.current!==owner)return;
    if(status.found){await finish(status.case_id!);return}
   }
   const payload=pending.current||{expert_user_id:expertId,clinical_summary:draft.summary.trim(),requester_opinion:draft.opinion.trim(),question:draft.question.trim(),tooth_region:draft.tooth.trim(),urgency:draft.urgency,...(draft.patientId?{patient_id:draft.patientId}:{}),media_ids:[...new Set(draft.mediaIds)].sort((a,b)=>a-b).join(","),request_key:Crypto.randomUUID()};
   pending.current=payload;const sealed={...draft,pending:payload};setDraft(sealed);
   // Persist the key and exact payload before the request so restart/retry
   // cannot accidentally submit a second consultation.
   await persist(sealed);if(scope.current!==owner)return;
   const result=await createConsultation(token,payload);if(scope.current!==owner)return;
   await finish(result.case_id);
  }catch(e){
   if(scope.current!==owner)return;
   if(e instanceof ApiError&&e.status<500&&e.status!==408&&e.status!==429){pending.current=undefined;setDraft(previous=>{const next={...previous};delete next.pending;return next})}
   setError(e instanceof Error?e.message:"Talep sonucu doğrulanamadı. Aynı talebin durumunu kontrol edin.");
  }finally{if(scope.current===owner){lock.current=false;setBusy(false)}}
 }
 async function finish(caseId:number){
  try{await writes.current;await SecureStore.deleteItemAsync(key)}catch{}
  if(scope.current!==expectedScope)return;
  pending.current=undefined;navigation.replace("ConsultationChat",{id:caseId});
 }
 if(!expertId)return <View style={{padding:20}}><Text style={{color:color.red}}>Önce bir uzman seçin.</Text><Button title="Uzmanlara git" onPress={()=>navigation.replace("ExpertDirectory",{patientId:initialId})}/></View>;
 return <ScrollView style={{flex:1,backgroundColor:"#F5F7FA"}} keyboardShouldPersistTaps="handled" contentContainerStyle={{padding:18,paddingBottom:60}}>
 <Text style={{fontSize:27,fontWeight:"800",color:color.navy}}>Vaka Gönder</Text>
 {!ready&&<ActivityIndicator/>}
 {context?<Text style={{marginTop:10,color:color.navy}}>{context.expert.display_name} · {context.expert.specialty} · {context.expert.consultation_price} TL</Text>:<View>{!!contextError&&<Text style={{color:color.red}}>{contextError}</Text>}<Button title="Uzman uygunluğunu yeniden kontrol et" disabled={busy} onPress={()=>void loadContext()}/></View>}
 <Text style={{fontWeight:"800",color:color.navy,marginTop:22}}>Hasta bağlantısı (isteğe bağlı)</Text>
 <Text style={{color:color.muted,marginTop:6}}>{patient?[patient.first_name,patient.last_name].filter(Boolean).join(" ")+" · "+patient.anonymous_id:draft.patientId?"Seçili hasta doğrulanıyor…":"Hasta bağlanmadı"}</Text>
 <Button title={picker?"Hasta seçimini kapat":"Kayıtlı hastalarımdan seç"} disabled={frozen||!ready} onPress={()=>setPicker(v=>!v)}/>
 {draft.patientId&&<Button title="Hasta bağlantısını kaldır" disabled={frozen} onPress={()=>choosePatient(null)}/>}
 {picker&&<View><TextInput accessibilityLabel="Talep için hasta ara" placeholder="Hasta adı, soyadı veya hasta no" value={patientSearch} onChangeText={setPatientSearch} onSubmitEditing={()=>setSearch(patientSearch.trim())} editable={!frozen} style={{padding:12,borderWidth:1,borderColor:color.line,color:color.navy}}/><Button title="Ara" disabled={frozen} onPress={()=>setSearch(patientSearch.trim())}/>
 {patients.items.map(row=><Button key={row.id} title={[row.first_name,row.last_name].filter(Boolean).join(" ")+" · "+row.anonymous_id} disabled={frozen} onPress={()=>choosePatient(row)}/>)}
 {patients.busy&&<ActivityIndicator/>}{!!patients.error&&<><Text style={{color:color.red}}>{patients.error}</Text><Button title="Hastaları yeniden yükle" onPress={()=>void patients.refresh()}/></>}{patients.hasMore&&<Button title="Daha fazla hasta" disabled={patients.busy} onPress={()=>void patients.loadMore()}/>}</View>}
 {!!patientError&&<Text style={{color:color.red}}>{patientError}</Text>}
 {!!draft.patientId&&<View style={{backgroundColor:"white",padding:14,borderRadius:14,marginTop:14}}>
 <Text style={{fontWeight:"800",color:color.navy}}>🔒 Uzmanla paylaşılacak bilgiler</Text>
 <Text style={{color:color.navy,marginTop:8}}>Vaka no: {patient?.anonymous_id||"Doğrulanıyor"}{patient?.age?" · "+patient.age+" yaş":""}</Text>
 <Text style={{color:color.muted,marginTop:8}}>Uzman diş/bölgeyi, yazdığınız klinik bilgileri ve yalnızca seçtiğiniz görüntüleri görür. Ad soyad, telefon, kimlik ve adres bilgileri paylaşılmaz. Dental AI sonucu otomatik paylaşılmaz. Yazdığınız metinlere de kimlik bilgisi eklemeyin.</Text>
 <Text style={{fontWeight:"800",color:color.navy,marginTop:14}}>Vakayla paylaşılacak görüntüler · {draft.mediaIds.length} seçili</Text>
 {media.items.map(item=><Pressable key={item.id} accessibilityRole="checkbox" accessibilityState={{checked:draft.mediaIds.includes(item.id),disabled:frozen}} disabled={frozen} onPress={()=>setDraft(previous=>({...previous,mediaIds:previous.mediaIds.includes(item.id)?previous.mediaIds.filter(id=>id!==item.id):[...previous.mediaIds,item.id]}))} style={{padding:12,borderBottomWidth:1,borderBottomColor:color.line}}><Text style={{color:color.navy}}>{draft.mediaIds.includes(item.id)?"☑":"☐"} {item.media_type} · {item.filename}</Text><Image source={{uri:item.url,headers:{Authorization:"Bearer "+token}}} resizeMode="contain" style={{height:80,width:120,marginTop:6}}/></Pressable>)}
 {media.busy&&<ActivityIndicator/>}{!!media.error&&<><Text style={{color:color.red}}>{media.error}</Text><Button title="Görüntüleri yeniden yükle" onPress={()=>void media.refresh()}/></>}{media.hasMore&&<Button title="Daha fazla görüntü" disabled={media.busy} onPress={()=>void media.loadMore()}/>}
 </View>}
 <Text style={{fontWeight:"800",color:color.navy,marginTop:20}}>Öncelik</Text>
 {(context?.urgencies||[]).map(item=><Button key={item.value} title={(draft.urgency===item.value?"✓ ":"")+item.label} disabled={frozen||!ready} onPress={()=>change("urgency",item.value)}/>)}
 {([["tooth","Diş / bölge","Örn. 46",false],["summary","Klinik bilgi","Vakayı anlamak için gerekli kısa klinik bilgi",true],["opinion","Kendi düşünceniz","Varsa ön değerlendirmeniz",true],["question","Uzmana sorunuz","Net olarak neyi değerlendirmesini istiyorsunuz?",true]] as const).map(([field,label,placeholder,multiline])=><View key={field}><Text style={{fontWeight:"800",color:color.navy,marginTop:18}}>{label}</Text><TextInput accessibilityLabel={label} placeholder={placeholder} value={draft[field]} onChangeText={value=>change(field,value)} editable={!frozen&&ready} multiline={multiline} style={{minHeight:multiline?100:48,borderWidth:1,borderColor:color.line,borderRadius:12,padding:12,color:color.navy,textAlignVertical:"top",marginTop:6}}/></View>)}
 {!!draftWarning&&<Text style={{color:color.red,marginTop:12}}>{draftWarning}</Text>}{!!error&&<Text style={{color:color.red,marginTop:12}}>{error}</Text>}
 {draft.pending&&<Text style={{color:color.muted,marginTop:12}}>Son gönderimin sonucu kontrol edilmeli. Form korundu; aynı talep anahtarıyla kontrol edilip yeniden denenecek.</Text>}
 <Button title={busy?"Kontrol ediliyor / gönderiliyor…":draft.pending?"Aynı talebin durumunu kontrol et ve yeniden dene":"Talebi Gönder"} disabled={busy||!ready||!context&&!draft.pending} onPress={()=>void send()}/>
 <Text style={{color:color.muted,marginTop:10}}>Uzmanın talebe yanıt vermesi için {context?.response_minutes||10} dakikası vardır.</Text>
 </ScrollView>;
}
