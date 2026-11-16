import NativeAnalysisUpload from './NativeAnalysisUpload';
import NativeClinicalReview from './NativeClinicalReview';
import React,{useCallback,useEffect,useRef,useState}from"react";
import{ActivityIndicator,AppState,Pressable,ScrollView,Text,TextInput,View}from"react-native";
import * as SecureStore from "expo-secure-store";
import{getPatient,getPatients,Patient}from"./api";
import{getAnalysis,startAnalysisAI,MobileAnalysis}from"./analysisApi";
import{useRealtime}from"./realtime";

export default function NativeDentalAI({token,userId,initialAnalysisId,initialPatientId}:{token:string;userId?:number;initialAnalysisId?:number;initialPatientId?:number}){
 const{lastEvent}=useRealtime();
 const[patients,setPatients]=useState<Patient[]>([]),[patientSearch,setPatientSearch]=useState(""),[patientQuery,setPatientQuery]=useState(""),[patientTotal,setPatientTotal]=useState(0),[patientBusy,setPatientBusy]=useState(false),[patientError,setPatientError]=useState(""),[patientId,setPatientId]=useState<number|null>(null),[analysis,setAnalysis]=useState<MobileAnalysis|null>(null),[busy,setBusy]=useState(false),[err,setErr]=useState("");
 const selectedRecord=useRef<Patient|null>(null);const patientsRef=useRef(patients);patientsRef.current=patients;
 const activeId=useRef<number|undefined>(initialAnalysisId), refreshGeneration=useRef(0),patientGeneration=useRef(0),patientPageLock=useRef(false);const actionLock=useRef(false);const actionGeneration=useRef(0);const selectionGeneration=useRef(0);const sessionScope=useRef(`${token}:${userId||0}`);sessionScope.current=`${token}:${userId||0}`;useEffect(()=>{selectionGeneration.current++;actionGeneration.current++;actionLock.current=false;patientGeneration.current++;patientPageLock.current=false;setPatientSearch("");setPatientQuery("");setPatientTotal(0);setPatientBusy(false);setPatientError("");setBusy(false);setPatients([]);selectedRecord.current=null;setPatientId(null);setAnalysis(null);setErr("");activeId.current=initialAnalysisId},[token,userId,initialAnalysisId,initialPatientId]);
 useEffect(()=>{
  let active=true;const generation=++refreshGeneration.current;
  void(async()=>{try{
   // An explicit patient action starts a new analysis; do not restore another
   // patient's remembered job over that action.
   const saved=initialAnalysisId||(!initialPatientId&&userId?Number(await SecureStore.getItemAsync('dai.analysis.'+userId)):0);
   if(!active||generation!==refreshGeneration.current||!saved)return;
   const result=await getAnalysis(token,saved);
   if(!active||generation!==refreshGeneration.current||result.analysis.id!==saved||
      (initialPatientId&&result.analysis.patient_id!==initialPatientId))return;
   activeId.current=saved;selectedRecord.current=result.patient;
   setPatientId(result.patient.id);setAnalysis(result);
  }catch(e){if(active&&generation===refreshGeneration.current)setErr(e instanceof Error?e.message:'Analiz geri yüklenemedi.')}})();
  return()=>{active=false;refreshGeneration.current++};
 },[token,userId,initialAnalysisId,initialPatientId]);
 useEffect(()=>{
  let active=true;
  const subscription=AppState.addEventListener('change',state=>{
   const id=activeId.current;if(state!=='active'||!id||!patientId)return;
   const request=++refreshGeneration.current;
   void getAnalysis(token,id).then(result=>{
    if(active&&request===refreshGeneration.current&&result.analysis.id===id&&result.analysis.patient_id===patientId)setAnalysis(result);
   }).catch(e=>{if(active&&request===refreshGeneration.current)setErr(e instanceof Error?e.message:'Analiz yenilenemedi.')});
  });
  return()=>{active=false;subscription.remove()};
 },[token,patientId]);
 const previousSelectedPatient=useRef<number|null>(null);useEffect(()=>{if(previousSelectedPatient.current!==null&&patientId===null){selectionGeneration.current++;actionGeneration.current++;refreshGeneration.current++;activeId.current=undefined;setAnalysis(null)}previousSelectedPatient.current=patientId},[patientId]);
 const load=useCallback(async(offset=0)=>{if(patientPageLock.current&&offset>0)return;const request=++patientGeneration.current,scope=sessionScope.current;patientPageLock.current=true;setPatientBusy(true);setPatientError("");try{const r=await getPatients(token,patientQuery,offset);if(request!==patientGeneration.current||scope!==sessionScope.current)return;if(!Number.isSafeInteger(r?.total)||r.total<0||!Array.isArray(r.items)||r.items.some(p=>!p||!Number.isSafeInteger(p.id)||p.id<=0)||new Set(r.items.map(p=>p.id)).size!==r.items.length)throw Error("Geçersiz hasta listesi yanıtı.");if(offset>0){if(offset>patientsRef.current.length)throw Error("Hasta sayfalama konumu güncel listeyle eşleşmiyor; listeyi yenile.");if(r.items.some(item=>patientsRef.current.some(old=>old.id===item.id)))throw Error("Tekrarlanan hasta sayfası alındı; mevcut klinik kayıtlar korundu.");if(r.items.length===0&&offset<r.total)throw Error("Eksik hasta sayfası alındı; yeniden dene.");}setPatientTotal(r.total);setPatients(previous=>offset===0?r.items:[...previous,...r.items]);}catch(e){if(request===patientGeneration.current&&scope===sessionScope.current)setPatientError(e instanceof Error?e.message:"Hasta listesi yüklenemedi.")}finally{if(request===patientGeneration.current&&scope===sessionScope.current){patientPageLock.current=false;setPatientBusy(false)}}},[token,patientQuery,userId]);const previousSearchScope=useRef({token,userId,patientQuery});useEffect(()=>{const prior=previousSearchScope.current;const queryChanged=prior.token===token&&prior.userId===userId&&prior.patientQuery!==patientQuery;previousSearchScope.current={token,userId,patientQuery};selectionGeneration.current++;patientGeneration.current++;patientPageLock.current=false;setPatients([]);setPatientTotal(0);setPatientId(null);setAnalysis(null);if(queryChanged){activeId.current=undefined;refreshGeneration.current++}setPatientError("");},[token,userId,patientQuery]);useEffect(()=>{void load();return()=>{patientGeneration.current++;patientPageLock.current=false}},[load]);useEffect(()=>{const e:any=lastEvent;if(!e)return;const t=String(e.event_type||e.type||"");if(t==="PATIENT_DELETED"&&Number(e.payload?.patient_id||e.entity_id)===selectedRecord.current?.id){selectionGeneration.current++;refreshGeneration.current++;selectedRecord.current=null;activeId.current=undefined;setPatientId(null);setAnalysis(null)}if(["PATIENT_CREATED","PATIENT_UPDATED","PATIENT_DELETED"].includes(t))void load()},[lastEvent,load]);
 useEffect(()=>{
  if(!initialPatientId||initialAnalysisId)return;
  let active=true;const selection=selectionGeneration.current;
  void getPatient(token,initialPatientId).then(result=>{
   if(!active||selection!==selectionGeneration.current)return;
   selectedRecord.current=result.patient;setPatientId(result.patient.id);
  }).catch(e=>{if(active)setPatientError(e instanceof Error?e.message:"Seçili hasta yüklenemedi.")});
  return()=>{active=false};
 },[token,userId,initialPatientId,initialAnalysisId]);
 const selectedPatient=selectedRecord.current&&selectedRecord.current.id===patientId?selectedRecord.current:null;
 const choices=selectedRecord.current&&selectedRecord.current.id===patientId&&!patients.some(p=>p.id===patientId)?[selectedRecord.current,...patients]:patients;
 useEffect(()=>()=>{refreshGeneration.current++},[token,analysis?.analysis.id]);
 useEffect(()=>{if(!analysis||!lastEvent)return;const e=lastEvent as any;const id=Number(e.entity_id||e.analysis_id||e.payload?.analysis_id||0);if((e.entity_type==="analysis"||["ANALYSIS_CREATED","ANALYSIS_UPDATED","ANALYSIS_COMPLETED","VISION_READY"].includes(String(e.event_type||e.type)))&&id===analysis.analysis.id){const generation=++refreshGeneration.current,scope=sessionScope.current,selectedPatient=patientId,analysisId=analysis.analysis.id;getAnalysis(token,analysisId).then(result=>{if(generation===refreshGeneration.current&&scope===sessionScope.current&&selectedPatient!==null&&patientId===selectedPatient&&activeId.current===analysisId&&result.analysis.id===analysisId&&result.analysis.patient_id===selectedPatient)setAnalysis(result)}).catch(()=>{})}},[lastEvent,analysis?.analysis.id,token,patientId]);
 useEffect(()=>{const current=analysis?.analysis;if(!current||["AI_ANALYZED","COMPLETED","FAILED","ERROR","CANCELLED"].includes(String(current.status).toUpperCase()))return;let disposed=false,inFlight=false;const scope=sessionScope.current,analysisId=current.id;const timer=setInterval(()=>{if(disposed||inFlight||AppState.currentState!=="active"||scope!==sessionScope.current)return;inFlight=true;const request=++refreshGeneration.current;void getAnalysis(token,analysisId).then(result=>{if(!disposed&&scope===sessionScope.current&&request===refreshGeneration.current&&activeId.current===analysisId&&patientId!==null&&current.patient_id===patientId&&result.analysis.id===analysisId&&result.analysis.patient_id===patientId)setAnalysis(result)}).catch(()=>{}).finally(()=>{inFlight=false})},15000);return()=>{disposed=true;clearInterval(timer)}},[token,analysis?.analysis.id,analysis?.analysis.status,userId,patientId]);
 async function openUploaded(id:number){
  const scope=sessionScope.current,selectedPatient=patientId,selection=selectionGeneration.current;
  if(!selectedPatient||!Number.isSafeInteger(id)||id<=0)return;
  // Do not persist an unverified analysis ID: a delayed upload callback may
  // belong to a patient/account that is no longer selected.
  const result=await getAnalysis(token,id);
  if(scope!==sessionScope.current||selection!==selectionGeneration.current||
     selectedRecord.current?.id!==selectedPatient)return;
  if(result.analysis.id!==id||result.analysis.patient_id!==selectedPatient)
    throw Error('Analiz seçili hasta ile eşleşmiyor.');
  activeId.current=id;
  refreshGeneration.current++;
  setAnalysis(result);setErr('');
  if(userId){
    // A scope change during the secure-store write must not resurrect this ID.
    const key='dai.analysis.'+userId;
    try{
      await SecureStore.setItemAsync(key,String(id));
      // A stale write may finish after a newer selection. Never delete the
      // key here: that could erase the newer selection's receipt.
    }catch{ /* Secure-store failure must not invalidate an authorized on-screen result. */ }
  }
 }
 async function refresh(){if(!analysis||actionLock.current)return;actionLock.current=true;const generation=++actionGeneration.current,scope=sessionScope.current,analysisId=analysis.analysis.id,selectedPatient=patientId;setBusy(true);try{const result=await getAnalysis(token,analysisId);if(generation===actionGeneration.current&&scope===sessionScope.current&&selectedPatient!==null&&patientId===selectedPatient&&result.analysis.id===analysisId&&result.analysis.patient_id===selectedPatient)setAnalysis(result)}catch(e:any){if(generation===actionGeneration.current&&scope===sessionScope.current)setErr(e?.message||"Durum alınamadı.")}finally{if(generation===actionGeneration.current&&scope===sessionScope.current){actionLock.current=false;setBusy(false)}}}
 async function start(){if(!analysis||actionLock.current)return;actionLock.current=true;const generation=++actionGeneration.current,scope=sessionScope.current,analysisId=analysis.analysis.id,selectedPatient=patientId;setBusy(true);setErr("");try{if(selectedPatient===null||analysis.analysis.patient_id!==selectedPatient)throw Error("Analiz kimliği seçili hastayla eşleşmiyor.");await startAnalysisAI(token,analysisId);if(generation!==actionGeneration.current||scope!==sessionScope.current)return;const result=await getAnalysis(token,analysisId);if(generation===actionGeneration.current&&scope===sessionScope.current&&selectedPatient!==null&&patientId===selectedPatient&&result.analysis.id===analysisId&&result.analysis.patient_id===selectedPatient)setAnalysis(result)}catch(e:any){if(generation===actionGeneration.current&&scope===sessionScope.current)setErr(e?.message||"Analiz başlatılamadı.")}finally{if(generation===actionGeneration.current&&scope===sessionScope.current){actionLock.current=false;setBusy(false)}}}
 return <View style={{paddingBottom:30}}>
  <Text style={{fontSize:13,fontWeight:"800",color:"#718096",marginBottom:8}}>Hasta seç</Text>
  <TextInput accessibilityLabel="Analiz için hasta ara" placeholder="Hasta adıyla ara" value={patientSearch} onChangeText={setPatientSearch} onSubmitEditing={()=>setPatientQuery(patientSearch.trim())} returnKeyType="search" style={{backgroundColor:"#FFF",borderWidth:1,borderColor:"#E5EAF0",padding:12,borderRadius:12,marginBottom:8,color:"#102033"}}/><Pressable accessibilityRole="button" onPress={()=>setPatientQuery(patientSearch.trim())} style={{alignSelf:"flex-end",paddingVertical:6,paddingHorizontal:12,marginBottom:8}}><Text style={{fontWeight:"800",color:"#071B35"}}>Hasta ara</Text></Pressable>
  <ScrollView horizontal showsHorizontalScrollIndicator={false}>{choices.map(p=><Pressable key={p.id} onPress={()=>{if(actionLock.current||patientId===p.id)return;selectionGeneration.current++;selectedRecord.current=p;setPatientId(p.id);setAnalysis(null);setErr("");activeId.current=undefined;refreshGeneration.current++;if(userId)void SecureStore.deleteItemAsync("dai.analysis."+userId).catch(()=>{})}} style={{paddingHorizontal:12,paddingVertical:9,borderRadius:12,backgroundColor:patientId===p.id?"#071B35":"#FFF",borderWidth:1,borderColor:"#E5EAF0",marginRight:7}}><Text style={{fontSize:12,fontWeight:"700",color:patientId===p.id?"#FFF":"#102033"}}>{p.first_name} {p.last_name}</Text></Pressable>)}</ScrollView>
  {!!patientError&&<Text style={{color:"#B42318",marginTop:8}}>{patientError}</Text>}
  {patientBusy&&<ActivityIndicator color="#071B35"/>}
  {patients.length<patientTotal&&<Pressable accessibilityRole="button" disabled={patientBusy} onPress={()=>void load(patients.length)} style={{padding:12,marginTop:8,alignSelf:"center"}}><Text style={{fontWeight:"800",color:"#071B35"}}>Daha fazla hasta ({patients.length}/{patientTotal})</Text></Pressable>}
  {patientId&&userId?<NativeAnalysisUpload key={token+':'+userId+':'+patientId} token={token} userId={userId} patientId={patientId} patient={selectedPatient} onCreated={openUploaded}/>:<Text style={{padding:12,color:'#53657B'}}>Devam etmek için gerçek bir hasta kaydı seçin.</Text>}
  {!!err&&<Text style={{color:"#B42318",marginTop:8}}>{err}</Text>}
  {analysis&&<View style={{backgroundColor:"#FFF",borderRadius:18,padding:16,borderWidth:1,borderColor:"#E5EAF0",marginTop:16}}><Text style={{fontSize:16,fontWeight:"900",color:"#102033"}}>Analiz #{analysis.analysis.id}</Text><Text style={{fontSize:13,color:"#718096",marginTop:4}}>Durum: {analysis.analysis.status}</Text><View style={{padding:12,marginTop:10,borderRadius:10,backgroundColor:"#EEF3FA",gap:4}}><Text style={{fontWeight:"800",color:"#071B35"}}>{analysis.patient.anonymous_id||`Hasta #${analysis.patient.id}`} · {analysis.patient.age===null||analysis.patient.age===undefined?"Hasta kaydı":`${analysis.patient.age} yaş`}</Text><Text style={{fontSize:13,lineHeight:20,color:"#53657B"}}>Ana şikâyet: {analysis.patient.chief_complaint?.trim()||"Belirtilmemiş"}</Text></View>{analysis.assets.map(a=><Text key={a.id} style={{fontSize:13,color:"#718096",marginTop:4}}>{a.original_filename} · {a.has_vision?"Görüntü hazır":"Görüntü işleniyor"}</Text>)}{analysis.analysis.status==="VISION_READY"&&<Pressable onPress={start} disabled={busy} style={{height:50,borderRadius:14,backgroundColor:"#071B35",alignItems:"center",justifyContent:"center",marginTop:12}}><Text style={{color:"#FFF",fontWeight:"800"}}>Klinik AI'yi Başlat</Text></Pressable>}{analysis.analysis.status!=="AI_ANALYZED"&&<Pressable onPress={refresh} disabled={busy} style={{height:50,borderRadius:14,backgroundColor:"#FFF",borderWidth:1,borderColor:"#E5EAF0",alignItems:"center",justifyContent:"center",marginTop:12}}><Text style={{color:"#071B35",fontWeight:"800"}}>Sonucu Yenile</Text></Pressable>}<NativeClinicalReview key={token+':'+analysis.analysis.id} token={token} userId={userId} analysisId={analysis.analysis.id}/></View>}
 </View>
}
