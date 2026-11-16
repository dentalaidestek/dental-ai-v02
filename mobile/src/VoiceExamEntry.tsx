import NativeVoiceRecorder from './NativeVoiceRecorder';
import NativeVoiceDeviceCheck from './NativeVoiceDeviceCheck';
import NativeVoiceApproval from './NativeVoiceApproval';
import NativePatientSelect from './NativePatientSelect';
import {usePreventRemove} from '@react-navigation/native';
import React,{useCallback,useEffect,useMemo,useRef,useState} from "react";
import {ActivityIndicator,Alert,Linking,Pressable,ScrollView,Text,TextInput,View} from "react-native";
import {getPatient,getPatients,Patient} from "./api";
import {createAnonymousVoicePatient,extractVoice,finalizeVoice,getVoiceHistory,VoiceExtraction,VoiceHistoryField} from "./voiceApi";
import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";
import {chunkedDraftStore} from "./socialDraft";
import {parseVoiceExtractionCheckpoint,splitVoiceTranscript} from "./voiceSession";
import {voiceEvidencePresentation} from "./voiceEvidencePresentation";

const navy="#071B35",muted="#63748A",line="#E1E7EF";
const fieldLabels:Record<string,string>={first_name:"Ad",last_name:"Soyad",age:"Yaş",chief_complaint:"Başvuru şikâyeti",medical_history:"Sağlık geçmişi",family_history:"Aile sağlık öyküsü",materials:"Konuşulan materyaller",dental_history:"Önceki diş tedavileri",oral_habits:"Ağız bakımı ve alışkanlıklar",medications:"İlaç bilgileri",allergies:"Alerji bilgileri",clinical_findings:"Muayene bulguları",plan:"Konuşulan tedavi planı"};
const reviewSections:[string,string][]=[["summary","Özet"],["anamnesis_review","Anamnez kontrolü"],["questions","Netleştirilecek sorular"],["contradictions","Çelişkiler"],["clinical_items","Klinik değerlendirmeler"],["material_review","Materyal değerlendirmesi"],["references","Kaynaklar"],["source_coverage","Kaynak kapsamı"],["unavailable","Doğrulanamayanlar"],["notice","Kaynak ve değerlendirme uyarısı"]];
function readable(value:unknown):string{
 if(typeof value==="string")return value;
 if(typeof value==="number"||typeof value==="boolean")return String(value);
 if(Array.isArray(value))return value.map(readable).filter(Boolean).join(" · ");
 if(value&&typeof value==="object"){const item=value as Record<string,unknown>;return Object.entries(item).slice(0,30).map(([key,val])=>key.replace(/_/g," ")+": "+readable(val)).filter(Boolean).join("\n")||"Ayrıntı belirtilmedi";}
 return "";
}
function VoiceEvidence({item}:{item:{quote?:string;origin?:string;edited?:boolean}}){
 const evidence=voiceEvidencePresentation(item);
 return <View style={{marginTop:7,padding:10,borderRadius:9,backgroundColor:"#F6FAFD",borderWidth:1,borderColor:line}}>
  <Text style={{fontSize:12,fontWeight:"800",color:muted}}>{evidence.label}</Text>
  {evidence.hasEvidence?<Text selectable style={{color:navy,lineHeight:19,marginTop:4}}>{evidence.quote}</Text>:<Text style={{color:"#9A6700",lineHeight:19,marginTop:4}}>Dayanak metni sunulmadı; kaydetmeden önce alanı doğrulayın.</Text>}
  {evidence.edited&&<Text style={{color:"#9A6700",lineHeight:18,marginTop:5}}>Bu alan hekim tarafından düzenlendi. Kaydetmeden önce dayanakla karşılaştırın.</Text>}
 </View>;
}

function ResultSection({name,items}:{name:string;items:unknown}){
 const [expanded,setExpanded]=useState(false);const rows=Array.isArray(items)?items:items==null?[]:[items];
 return <View style={{borderWidth:1,borderColor:line,borderRadius:13,marginTop:12,overflow:"hidden"}}>
 <Pressable accessibilityRole="button" accessibilityState={{expanded}} onPress={()=>setExpanded(v=>!v)} style={{padding:14,flexDirection:"row",justifyContent:"space-between",alignItems:"center",backgroundColor:"#F6FAFD"}}>
 <Text style={{fontWeight:"800",color:navy,flex:1}}>{name} ({rows.length})</Text><Text style={{color:navy}}>{expanded?"−":"+"}</Text>
 </Pressable>
 {expanded&&(rows.length?rows.map((item,i)=><View key={i} style={{padding:12,borderTopWidth:1,borderTopColor:line}}><Text selectable style={{color:navy,lineHeight:21}}>{readable(item)}</Text>{item&&typeof item==="object"&&typeof (item as Record<string,unknown>).url==="string"&&<Pressable accessibilityRole="link" onPress={()=>{const url=String((item as Record<string,unknown>).url);if(!/^https:\/\/[^\s/?#]+(?:[/?#]|$)/i.test(url)){Alert.alert("Güvensiz bağlantı","Yalnızca HTTPS kaynak bağlantıları açılabilir.");return;}void Linking.openURL(url).catch(()=>Alert.alert("Bağlantı açılamadı","Kaynağa şu anda ulaşılamıyor."));}}><Text style={{color:"#1769AA",marginTop:6}}>Kaynağı aç</Text></Pressable>}</View>):<Text style={{color:muted,padding:12}}>Bu bölümde kayıt yok.</Text>)}
 </View>;
}


function mergeVoiceHistory(result:VoiceExtraction,history:Record<string,VoiceHistoryField>):VoiceExtraction{
 const fields={...(result.review.fields||{})};
 const conflicts:string[]=[];
 for(const [name,item] of Object.entries(history)){
  const current=fields[name];
  if(!current)fields[name]={value:item.value,quote:item.quote,origin:"history"};
  else if(current.value.trim()!==item.value.trim())conflicts.push((fieldLabels[name]||name)+": önceki kayıt — "+item.value+"; bu görüşme — "+current.value);
 }
 const prior=result.review.uncertainties||String(result.review.uncertain||"").split(" · ").filter(Boolean);
 const uncertainties=Array.from(new Set([...prior,...conflicts].map(value=>value.trim()).filter(Boolean))).slice(-8);
 return {...result,review:{...result.review,fields,uncertainties,uncertain:uncertainties.join(" · ")}};
}

function ReviewRemovableSection({name,items,onRemove,disabled}:{name:string;items:unknown[]|undefined;onRemove:(index:number)=>void;disabled:boolean}){
 const [expanded,setExpanded]=useState(false);
 const rows=Array.isArray(items)?items:[];
 return <View style={{borderWidth:1,borderColor:line,borderRadius:13,marginTop:12,overflow:"hidden"}}>
  <Pressable accessibilityRole="button" accessibilityState={{expanded}} onPress={()=>setExpanded(v=>!v)} style={{padding:14,backgroundColor:"#F6FAFD",flexDirection:"row",justifyContent:"space-between"}}>
   <Text style={{fontWeight:"800",color:navy}}>{name} ({rows.length})</Text><Text style={{color:navy}}>{expanded?"−":"+"}</Text>
  </Pressable>
  {expanded&&(rows.length?rows.map((item,index)=><View key={index} style={{padding:12,borderTopWidth:1,borderTopColor:line}}>
   <Text style={{color:navy,lineHeight:20}}>{readable(item)}</Text>
   <Pressable accessibilityRole="button" accessibilityLabel={name+" kaydını çıkar "+(index+1)} disabled={disabled} onPress={()=>onRemove(index)} style={{paddingVertical:10,alignSelf:"flex-start"}}>
    <Text style={{color:disabled?muted:"#B42318",fontWeight:"700"}}>Yanlış çıkarımı kaldır</Text>
   </Pressable>
  </View>):<Text style={{color:muted,padding:12}}>Bu bölümde kayıt yok.</Text>)}
 </View>;
}

export default function VoiceExamEntry({token,userId,initialPatientId}:{token:string;userId?:number;initialPatientId?:number}){
 const [audioBusy,setAudioBusy]=useState(false),[deviceCheckBusy,setDeviceCheckBusy]=useState(false),[applyBusy,setApplyBusy]=useState(false),[audioSession,setAudioSession]=useState({started:false,finished:false});
 const [privacyExpanded,setPrivacyExpanded]=useState(false),[processing,setProcessing]=useState(false),[editingFields,setEditingFields]=useState(false),[review,setReview]=useState<VoiceExtraction|null>(null),[finalResult,setFinalResult]=useState<Record<string,unknown>|null>(null),[clinicalError,setClinicalError]=useState(""),[stage,setStage]=useState<"select"|"exam">("select"),[consent,setConsent]=useState(false),[transcript,setTranscript]=useState(""),[creatingAnonymous,setCreatingAnonymous]=useState(false),[error,setError]=useState(""),[selected,setSelected]=useState<Patient|null>(null);
 const [extractionProgress,setExtractionProgress]=useState("");
 const [historyFields,setHistoryFields]=useState<Record<string,VoiceHistoryField>>({}),[historyNotice,setHistoryNotice]=useState(""),[historyError,setHistoryError]=useState(""),[historyLoading,setHistoryLoading]=useState(false),[historyConfirmed,setHistoryConfirmed]=useState(false),[historyApplied,setHistoryApplied]=useState(false);
 const extractionStore=useMemo(()=>chunkedDraftStore(SecureStore,Crypto.randomUUID,512),[]);
 usePreventRemove(processing||audioBusy||deviceCheckBusy||applyBusy,()=>Alert.alert("İşlem sürüyor","Muayene veya kayıt tamamlanana kadar bekleyin."));
 const [lastRemoved,setLastRemoved]=useState<{key:"teeth"|"literature_topics"|"source_requests"|"communication"|"decision_barriers"|"follow_up_questions";index:number;item:unknown}|null>(null);
 const processingLock=useRef(false),processingOwner=useRef(0),generation=useRef(0),scope=useRef(token+":"+(selected?.id||0)),anonymousLock=useRef<string|null>(null),startAfterSelection=useRef(false),accountScope=useRef(token+":"+(userId||0));
 const forceFreshExtraction=useRef(false);
 scope.current=token+":"+(selected?.id||0);accountScope.current=token+":"+(userId||0);
 useEffect(()=>{const enterExam=startAfterSelection.current;startAfterSelection.current=false;generation.current++;processingLock.current=false;setProcessing(false);setReview(null);setLastRemoved(null);setFinalResult(null);setClinicalError("");setTranscript("");setConsent(false);setHistoryFields({});setHistoryNotice("");setHistoryError("");setHistoryLoading(false);setHistoryConfirmed(false);setHistoryApplied(false);setStage(enterExam?"exam":"select")},[token,selected?.id]);
 useEffect(()=>{setCreatingAnonymous(false);setSelected(null);setAudioBusy(false);setApplyBusy(false)},[token]);
 useEffect(()=>{let active=true;if(initialPatientId){void getPatient(token,initialPatientId).then(r=>{if(active)setSelected(r.patient)}).catch(()=>{if(active)setError("Seçili hasta bulunamadı veya erişim izni yok.")})}return()=>{active=false}},[token,initialPatientId]);
 async function createAnonymousPatient(){
  if(!userId)return;
  const requestScope=token+":"+userId;
  if(anonymousLock.current===requestScope)return;
  anonymousLock.current=requestScope;setCreatingAnonymous(true);setError("");
  const storageKey="dai.voice.patient.create."+userId;
  try{
   let requestKey=await SecureStore.getItemAsync(storageKey);
   if(!requestKey){requestKey=Crypto.randomUUID().replace(/-/g,"");await SecureStore.setItemAsync(storageKey,requestKey);}
   const result=await createAnonymousVoicePatient(token,requestKey);
   if(accountScope.current!==requestScope)return;
   await SecureStore.deleteItemAsync(storageKey);
   startAfterSelection.current=true;setSelected(result.patient);
  }catch(e){if(accountScope.current===requestScope)setError(e instanceof Error?e.message:"Yeni hasta oluşturulamadı. Aynı istek güvenle tekrar denenebilir.");}
  finally{if(anonymousLock.current===requestScope)anonymousLock.current=null;if(accountScope.current===requestScope)setCreatingAnonymous(false);}
 }
 async function loadPreviousVoiceHistory(){
  if(!selected||historyLoading||processingLock.current||audioBusy||deviceCheckBusy||applyBusy||audioSession.started&&!audioSession.finished)return;
  const requestScope=scope.current,patientId=selected.id;setHistoryLoading(true);setHistoryError("");
  try{
   const result=await getVoiceHistory(token,patientId);
   if(requestScope!==scope.current)return;
   setHistoryFields(result.fields);setHistoryNotice(result.notice);setHistoryConfirmed(false);setHistoryApplied(false);
   if(!Object.keys(result.fields).length)setHistoryNotice(result.notice+" Aktarılabilecek önceki alan bulunamadı; hasta arşivinin diğer bölümlerini ayrıca kontrol edin.");
  }catch(e){if(requestScope===scope.current)setHistoryError(e instanceof Error?e.message:"Önceki hekim onaylı bilgiler getirilemedi.");}
  finally{if(requestScope===scope.current)setHistoryLoading(false);}
 }
 function applyPreviousVoiceHistory(){
  if(!historyConfirmed){setHistoryError("Önceki bilgileri hastayla doğruladığınızı işaretleyin.");return;}
  if(!Object.keys(historyFields).length||historyApplied)return;
  setHistoryApplied(true);setHistoryError("");
  if(review){setReview(mergeVoiceHistory(review,historyFields));setFinalResult(null);setClinicalError("");}
 }
 async function processText(completeText?:string){
  const text=completeText??transcript;
  if(!selected||!consent||!text.trim()||processingLock.current||(audioBusy||deviceCheckBusy||audioSession.started&&!audioSession.finished)&&!completeText)return;
  if(text.length>72000){setClinicalError("Muayene metni 72.000 karakter sınırını aşıyor. Yerel taslak korunuyor.");return;}
  processingLock.current=true;
  const request=++generation.current,currentScope=scope.current,patientId=selected.id;
  processingOwner.current=request;setProcessing(true);setClinicalError("");setExtractionProgress("");
  try{
   const chunks=splitVoiceTranscript(text);
   const transcriptHash=await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,text);
   const checkpointKey=userId?`dai.voice.extraction.${userId}.${patientId}`:"";
   let resume: {cursor:number;revision:string;review:VoiceExtraction["review"]}|undefined;
   if(userId){
    if(forceFreshExtraction.current){await extractionStore.deleteItemAsync(checkpointKey);forceFreshExtraction.current=false;}
    else{
     const raw=await extractionStore.getItemAsync(checkpointKey);
     const saved=parseVoiceExtractionCheckpoint(raw,userId,patientId,transcriptHash,chunks.length);
     if(saved)resume={cursor:saved.cursor,revision:saved.revision,review:saved.review as VoiceExtraction["review"]};
     else if(raw)await extractionStore.deleteItemAsync(checkpointKey);
    }
   }
   const result=await extractVoice(token,patientId,text,{
    resume,
    onProgress:(completed,total)=>{if(request===generation.current&&currentScope===scope.current)setExtractionProgress(`Görüşme bölümleri işleniyor: ${completed}/${total}`);},
    onCheckpoint:async checkpoint=>{
     if(request!==generation.current||currentScope!==scope.current)throw Error("Hesap veya hasta değişti. Muayene taslağı korunuyor.");
     if(userId)await extractionStore.setItemAsync(checkpointKey,JSON.stringify({version:1,userId,patientId,transcriptHash,...checkpoint,updatedAt:Date.now()}));
    }
   });
   if(request!==generation.current||currentScope!==scope.current)return;
   setReview(historyApplied?mergeVoiceHistory(result,historyFields):result);setLastRemoved(null);setEditingFields(false);setFinalResult(null);
   setExtractionProgress(`\u2713 ${chunks.length} bölüm tamamlandı. Tüm görüşme tek klinik değerlendirme için hazır.`);
  }catch(e){
   if(request===generation.current&&currentScope===scope.current){
    const message=e instanceof Error?e.message:"Muayene değerlendirilemedi.";
    if(message.includes("Hasta dosyası görüşme sırasında değişti")){
     forceFreshExtraction.current=true;
     setExtractionProgress("Hasta kaydı değişti; yeniden denemede eski bölümler atılıp tüm görüşme baştan işlenecek.");
    }
    setClinicalError(message);
   }
  }finally{
   if(processingOwner.current===request){processingLock.current=false;processingOwner.current=0;setProcessing(false);}
  }
 }
 function removeExtractedItem(key:"teeth"|"literature_topics"|"source_requests"|"communication"|"decision_barriers"|"follow_up_questions",index:number){
  if(processingLock.current)return;
  generation.current++;
  const current=review?.review[key];
  if(!Array.isArray(current)||index<0||index>=current.length)return;
  setLastRemoved({key,index,item:current[index]});
  setReview(previous=>{
   if(!previous)return previous;
   const latest=previous.review[key];
   if(!Array.isArray(latest)||index>=latest.length)return previous;
   return {...previous,review:{...previous.review,[key]:latest.filter((_,i)=>i!==index)}};
  });
  setFinalResult(null);
 }
 function undoRemovedItem(){
  if(processingLock.current||!lastRemoved||!review)return;
  generation.current++;
  const {key,index,item}=lastRemoved;
  setReview(previous=>{
   if(!previous)return previous;
   const current=previous.review[key];
   if(!Array.isArray(current))return previous;
   const restored=[...current];restored.splice(Math.min(index,restored.length),0,item as never);
   return {...previous,review:{...previous.review,[key]:restored}};
  });
  setLastRemoved(null);setFinalResult(null);
 }
 async function recheckVoice(){
  if(!selected)return;
  forceFreshExtraction.current=true;
  await processText();
 }
 async function finalize(){if(!selected||!consent||!review||processingLock.current||audioBusy||deviceCheckBusy||audioSession.started&&!audioSession.finished)return;processingLock.current=true;const request=++generation.current,currentScope=scope.current;processingOwner.current=request;setProcessing(true);setClinicalError("");try{const data=review.review;const response=await finalizeVoice(token,selected.id,{context:{fields:data.fields||{},teeth:data.teeth||[],literature_topics:data.literature_topics||[],source_requests:data.source_requests||[],...(data.appointment?{appointment:data.appointment}:{})},insights:data.communication||data.insights||[],uncertain:(data.uncertain||'').slice(0,3000),conversation_text:transcript});if(request===generation.current&&currentScope===scope.current)setFinalResult(response.final as Record<string,unknown>)}catch(e){if(request===generation.current&&currentScope===scope.current)setClinicalError(e instanceof Error?e.message:"Son değerlendirme tamamlanamadı.")}finally{if(processingOwner.current===request){processingLock.current=false;processingOwner.current=0;setProcessing(false)}}}
 
 if(stage==="exam")return <ScrollView style={{flex:1,backgroundColor:"#F5F7FA"}} contentContainerStyle={{padding:16,paddingBottom:42}}>
  <Pressable accessibilityRole="button" disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onPress={()=>{const back=()=>{generation.current++;processingLock.current=false;setProcessing(false);setStage("select")};if(transcript.trim())Alert.alert("Muayeneden ayrıl","Muayene metni bu hesaba ve hastaya bağlı cihaz taslağında korunur. Hasta dosyasına yalnız onaylanan alanlar kaydedilir.",[{text:"Vazgeç",style:"cancel"},{text:"Geri dön",style:"destructive",onPress:back}]);else back()}}><Text style={{color:navy,fontWeight:"700"}}>‹ Hasta seçimine dön</Text></Pressable>
  <Text style={{fontSize:25,fontWeight:"800",color:navy,marginTop:16}}>Sesli Muayene</Text>
  <Text style={{color:muted,marginTop:8}}>{selected?[selected.first_name,selected.last_name].filter(Boolean).join(" ")||selected.anonymous_id:"Hasta seçilmedi"}</Text>
  <View style={{backgroundColor:"white",borderRadius:18,padding:16,borderWidth:1,borderColor:line,marginTop:20}}>
   <Text style={{fontSize:17,fontWeight:"800",color:navy}}>Muayene hazırlığı</Text>
   <Text style={{color:muted,marginTop:8}}>Hazırlık · Metin · Klinik değerlendirme · Hekim onayı</Text>
   <NativeVoiceDeviceCheck disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onBusyChange={setDeviceCheckBusy}/>
   <View style={{marginTop:14,paddingTop:14,borderTopWidth:1,borderTopColor:line}}>
    <Text style={{fontWeight:"800",color:navy}}>Önceki hekim onaylı bilgiler</Text>
    <Text style={{color:muted,lineHeight:20,marginTop:6}}>Yalnızca önceki sesli muayenede hekim tarafından kaydedilen hastalık, ilaç ve alerji beyanları getirilir. Güncel olduklarını hastayla doğrulamadan kullanmayın.</Text>
    <Pressable accessibilityRole="button" disabled={historyLoading||processing||audioBusy||deviceCheckBusy||applyBusy} onPress={()=>void loadPreviousVoiceHistory()} style={{marginTop:10,padding:12,borderRadius:10,backgroundColor:"#E8F0FF",alignItems:"center"}}>
     <Text style={{color:"#1769AA",fontWeight:"800"}}>{historyLoading?"Önceki kayıtlar getiriliyor…":"Önceki kayıtları göster"}</Text>
    </Pressable>
    {!!historyNotice&&<Text style={{color:muted,lineHeight:20,marginTop:9}}>{historyNotice}</Text>}
    {Object.entries(historyFields).map(([name,item])=><View key={name} style={{paddingVertical:8,borderBottomWidth:1,borderBottomColor:line}}>
     <Text style={{fontWeight:"700",color:navy}}>{fieldLabels[name]||name.replace(/_/g," ")}</Text>
     <Text selectable style={{color:muted,marginTop:3}}>{item.value} · Önceki muayene #{item.analysis_id}</Text>
    </View>)}
    {!!historyError&&<Text accessibilityRole="alert" style={{color:"#B42318",marginTop:9}}>{historyError}</Text>}
    {Object.keys(historyFields).length>0&&!historyApplied&&<>
     <Pressable accessibilityRole="checkbox" accessibilityState={{checked:historyConfirmed,disabled:processing||audioBusy||deviceCheckBusy||applyBusy}} disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onPress={()=>setHistoryConfirmed(v=>!v)} style={{flexDirection:"row",alignItems:"center",gap:9,paddingVertical:10}}>
      <Text style={{fontSize:20,color:navy}}>{historyConfirmed?"☑":"☐"}</Text>
      <Text style={{color:navy,flex:1}}>Bu bilgileri hastayla doğruladım.</Text>
     </Pressable>
     <Pressable accessibilityRole="button" disabled={!historyConfirmed||processing||audioBusy||deviceCheckBusy||applyBusy} onPress={applyPreviousVoiceHistory} style={{padding:13,borderRadius:10,backgroundColor:historyConfirmed?"#071B35":"#9BA7B7",alignItems:"center"}}>
      <Text style={{color:"white",fontWeight:"800"}}>Doğruladığım bilgileri muayeneye ekle</Text>
     </Pressable>
    </>}
    {historyApplied&&<Text style={{color:"#1769AA",marginTop:9}}>Doğruladığınız bilgiler muayene taslağına eklendi. Önceki ve güncel beyanlar çelişiyorsa ayrıca gösterilir; hiçbir alan otomatik kaydedilmez.</Text>}
   </View>
   <Pressable accessibilityRole="checkbox" accessibilityState={{checked:consent,disabled:processing||audioBusy||deviceCheckBusy||applyBusy}} disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onPress={()=>{if(consent){generation.current++;processingLock.current=false;setProcessing(false);setReview(null);setLastRemoved(null);setFinalResult(null);setClinicalError("")}setConsent(v=>!v)}} style={{flexDirection:"row",alignItems:"flex-start",gap:10,marginTop:18}}>
    <Text style={{fontSize:21,color:navy}}>{consent?"☑":"☐"}</Text><Text style={{flex:1,color:navy,lineHeight:21}}>Hastayı bilgilendirdim. Sesimin yazıya çevrilmesine ve muayene bittiğinde metnin klinik yapay zekâ hizmetiyle değerlendirilmesine onay veriyorum.</Text>
   </Pressable>
   <Pressable accessibilityRole="button" accessibilityState={{expanded:privacyExpanded}} onPress={()=>setPrivacyExpanded(v=>!v)} style={{marginTop:14,paddingVertical:10}}><Text style={{fontWeight:"700",color:navy}}>Veriler ve taslak hakkında {privacyExpanded?"−":"+"}</Text></Pressable>
   {privacyExpanded&&<Text style={{color:muted,lineHeight:20}}>Kayıt sırasında ses parçaları konuşma metni için işlenir. Klinik çıkarım yalnız muayeneyi bitirdiğinizde veya metni değerlendirdiğinizde yapılır. Metin cihazın güvenli deposunda, bekleyen sesler özel uygulama alanında tutulur. Ham ses ve tam konuşma metni hasta dosyasına otomatik yazılmaz. Gereksiz kimlik bilgilerini konuşmayın. Taslağı bu ekrandan temizleyebilirsiniz.</Text>}
   {!!userId&&<NativeVoiceRecorder key={token+":"+selected?.id} token={token} userId={userId} patientId={selected!.id} consent={consent} value={transcript} disabled={processing||applyBusy||deviceCheckBusy} onBusyChanged={setAudioBusy} onSessionState={setAudioSession} onTranscript={v=>{generation.current++;setTranscript(v);setReview(null);setLastRemoved(null);setFinalResult(null)}} onFinished={v=>{setTranscript(v);void processText(v)}}/>}
   <Text style={{fontWeight:"800",color:navy,marginTop:20}}>Muayene metni</Text>
   <TextInput multiline maxLength={72000} accessibilityLabel="Muayene metni" placeholder="Muayene notunu buraya yazabilirsiniz." value={transcript} editable={!processing&&!audioBusy&&!deviceCheckBusy&&!applyBusy} onChangeText={v=>{generation.current++;setClinicalError("");setTranscript(v);setReview(null);setLastRemoved(null);setFinalResult(null)}} style={{marginTop:10,borderWidth:1,borderColor:line,borderRadius:12,minHeight:160,textAlignVertical:"top",padding:12,color:navy}}/>
   <Text style={{color:muted,fontSize:12,marginTop:8}}>{transcript.length}/72000 karakter · Uzun görüşmeler 12.000 karakterlik güvenli bölümlere ayrılır; tamamlanan bölümler cihazın şifreli taslağında korunur.</Text>
   {!!extractionProgress&&<Text accessibilityLiveRegion="polite" style={{color:muted,marginTop:10}}>{extractionProgress}</Text>}
   {!!clinicalError&&<Text style={{color:"#B42318",marginTop:12}}>{clinicalError}</Text>}
   <Pressable accessibilityRole="button" disabled={processing||audioBusy||deviceCheckBusy||applyBusy||audioSession.started&&!audioSession.finished||!consent||!selected||!transcript.trim()||transcript.length>72000} onPress={()=>void processText()} style={{backgroundColor:processing||audioBusy||deviceCheckBusy||!consent||!selected||!transcript.trim()||transcript.length>72000?"#9BA7B7":"#1769AA",borderRadius:12,padding:15,alignItems:"center",marginTop:18}}><Text style={{color:"white",fontWeight:"800"}}>{processing?"Değerlendiriliyor…":"Muayeneyi Bitir ve Metni Çözümle"}</Text></Pressable>
   {review&&<View style={{marginTop:18,borderTopWidth:1,borderTopColor:line,paddingTop:15}}>
    <Text style={{fontSize:17,fontWeight:"800",color:navy}}>Çıkarılan muayene bilgileri</Text>
    <Pressable accessibilityRole="button" disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onPress={()=>setEditingFields(v=>!v)} style={{paddingVertical:12}}><Text style={{fontWeight:"800",color:"#1769AA"}}>{editingFields?"Düzenlemeyi bitir":"Çıkarılan bilgileri kontrol et / düzenle"}</Text></Pressable>{Object.entries(review.review.fields||{}).map(([name,item])=><View key={name} style={{paddingVertical:9,borderBottomWidth:1,borderBottomColor:line}}><Text style={{fontWeight:"700",color:navy}}>{fieldLabels[name]||name.replace(/_/g," ")}</Text>{editingFields?<TextInput multiline accessibilityLabel={fieldLabels[name]||name} value={item.value} editable={!processing&&!audioBusy&&!deviceCheckBusy&&!applyBusy} onChangeText={value=>{generation.current++;setReview(previous=>previous?{...previous,review:{...previous.review,fields:{...previous.review.fields,[name]:{...previous.review.fields?.[name],value,edited:true}}}}:previous);setFinalResult(null)}} style={{color:navy,borderWidth:1,borderColor:line,borderRadius:9,padding:10,marginTop:6}}/>:<Text style={{color:muted,marginTop:4}}>{item.value}</Text>}<VoiceEvidence item={item}/></View>)}
    <ReviewRemovableSection name="Hasta iletişimi ve hekim önerileri" items={review.review.communication} disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onRemove={index=>removeExtractedItem("communication",index)}/>
    <ReviewRemovableSection name="Karar verme engelleri" items={review.review.decision_barriers} disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onRemove={index=>removeExtractedItem("decision_barriers",index)}/>
    <ReviewRemovableSection name="Netleştirilmesi gereken takip soruları" items={review.review.follow_up_questions} disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onRemove={index=>removeExtractedItem("follow_up_questions",index)}/>
    <ReviewRemovableSection name="Diş bazlı çıkarımlar" items={review.review.teeth} disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onRemove={index=>removeExtractedItem("teeth",index)}/>
    <ReviewRemovableSection name="Kaynak tarama konuları" items={review.review.literature_topics} disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onRemove={index=>removeExtractedItem("literature_topics",index)}/>
    <ReviewRemovableSection name="Kaynak terimi adayları" items={review.review.source_requests} disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onRemove={index=>removeExtractedItem("source_requests",index)}/>
    {!!review.review.appointment&&<View style={{marginTop:12}}>
     <ResultSection name="Konuşulan randevu" items={review.review.appointment}/>
     <Pressable accessibilityRole="button" disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onPress={()=>{generation.current++;setReview(previous=>previous?{...previous,review:{...previous.review,appointment:undefined}}:previous);setFinalResult(null)}} style={{paddingVertical:12}}>
      <Text style={{color:processing?muted:"#B42318",fontWeight:"700"}}>Randevu doğrulanmadı — taslaktan çıkar</Text>
     </Pressable>
    </View>}
    {!!review.review.uncertain&&<ResultSection name="Belirsiz / doğrulanmamış beyanlar" items={review.review.uncertain}/>}
    {!!review.review.appointment&&<Text style={{color:"#9A6700",marginTop:10,lineHeight:20}}>Randevu konuşmada geçiyor olabilir; kabul veya kesinleşme hekim tarafından ayrıca doğrulanmalıdır. Onay bölümünde tarih/saat seçilmeden randevu oluşturulmaz.</Text>}
    {!!lastRemoved&&<Pressable accessibilityRole="button" disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onPress={undoRemovedItem} style={{paddingVertical:12}}><Text style={{color:"#1769AA",fontWeight:"800"}}>Son kaldırılan bulguyu geri al</Text></Pressable>}
    <Text style={{color:muted,marginTop:10}}>Bunlar taslak bilgilerdir; hasta dosyasına kaydedilmedi.</Text>
    <Pressable accessibilityRole="button" disabled={processing||audioBusy||deviceCheckBusy||applyBusy} onPress={()=>void finalize()} style={{backgroundColor:navy,padding:15,borderRadius:12,alignItems:"center",marginTop:14}}><Text style={{color:"white",fontWeight:"800"}}>Hekim Kontrolünden Sonra Klinik Değerlendirme</Text></Pressable>
   </View>}
   {finalResult&&<View style={{marginTop:18,borderTopWidth:1,borderTopColor:line,paddingTop:15}}>
    <Text style={{fontSize:18,fontWeight:"800",color:navy}}>Kaynaklı klinik değerlendirme</Text>
    {reviewSections.map(([key,label])=><ResultSection key={key} name={label} items={finalResult[key]}/>)}
    <Text style={{color:"#B42318",marginTop:12}}>Hekim kontrolü gereklidir. Sonuç otomatik olarak hasta dosyasına yazılmaz.</Text>
   </View>}
   {finalResult&&review&&selected&&userId&&(!audioSession.started||audioSession.finished)&&<NativeVoiceApproval key={token+":"+selected.id+":"+review.revision} token={token} userId={userId} patientId={selected.id} review={review} labels={fieldLabels} onBusyChanged={setApplyBusy} onRecheck={()=>void recheckVoice()}/>}
  </View>
 </ScrollView>;
 return <ScrollView style={{flex:1,backgroundColor:"#F5F7FA"}} contentContainerStyle={{padding:16,paddingBottom:40}}>
  <Text style={{fontSize:25,fontWeight:"800",color:navy}}>Sesli Muayene</Text>
  <Text style={{color:muted,marginTop:7,lineHeight:21}}>Hastayı seçin, kaydı başlatın ve canlı konuşma metnini izleyin. Klinik çıkarım muayene bitince, kayıt ise hekim onayıyla yapılır.</Text>
  <View style={{backgroundColor:"white",borderRadius:18,padding:16,borderWidth:1,borderColor:line,marginTop:18}}>
   <Text style={{fontWeight:"800",color:navy,marginBottom:9}}>Hasta seçimi</Text>
   <Pressable accessibilityRole="button" accessibilityState={{busy:creatingAnonymous,disabled:creatingAnonymous||!userId}} disabled={creatingAnonymous||!userId} onPress={()=>void createAnonymousPatient()} style={{backgroundColor:"#1769AA",padding:15,borderRadius:13,alignItems:"center",opacity:(creatingAnonymous||!userId)?0.5:1}}>
    {creatingAnonymous?<ActivityIndicator color="white"/>:<Text style={{color:"white",fontWeight:"800"}}>Yeni hastayla başla →</Text>}
   </Pressable>
   <Text style={{color:muted,textAlign:"center",marginVertical:12}}>veya mevcut hastayı seç</Text>
   <NativePatientSelect key={token} token={token} value={selected} onChange={setSelected} disabled={creatingAnonymous}/>
   {!!error&&<Text accessibilityRole="alert" style={{color:"#B42318",marginTop:10,lineHeight:20}}>{error}</Text>}
   <Pressable accessibilityRole="button" disabled={creatingAnonymous} onPress={()=>{if(selected)setStage("exam");else setError("Önce bir hasta seçin.")}} style={{marginTop:18,backgroundColor:navy,padding:15,borderRadius:13,alignItems:"center",opacity:creatingAnonymous?0.5:1}}><Text style={{color:"white",fontWeight:"800"}}>{selected?"Muayeneye Devam Et":"Hasta Seçerek Devam Et"}</Text></Pressable>
   <Text style={{fontSize:12,color:muted,marginTop:10,lineHeight:18}}>Muayene bilgileri yalnızca hekim onayıyla hasta dosyasına kaydedilir. Yeni hasta kaydı boş bir klinik dosya açar; bilgileri yalnızca hekim onayıyla eklersiniz.</Text>
  </View>
 </ScrollView>
}
