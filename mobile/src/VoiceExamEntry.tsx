import React,{useCallback,useEffect,useState} from "react";
import {ActivityIndicator,Linking,Pressable,ScrollView,Text,TextInput,View} from "react-native";
import {getPatient,getPatients,Patient} from "./api";

const navy="#071B35",muted="#63748A",line="#E1E7EF";
export default function VoiceExamEntry({token,initialPatientId}:{token:string;initialPatientId?:number}){
 const [stage,setStage]=useState<"select"|"exam">("select"),[consent,setConsent]=useState(false),[transcript,setTranscript]=useState(""),[query,setQuery]=useState(""),[patients,setPatients]=useState<Patient[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(""),[selected,setSelected]=useState<Patient|null>(null);
 const load=useCallback(async()=>{setBusy(true);setError("");try{const r=await getPatients(token,query,0);setPatients(r.items)}catch(e){setError(e instanceof Error?e.message:"Hasta listesi alınamadı.")}finally{setBusy(false)}},[token,query,initialPatientId]);
 useEffect(()=>{const timer=setTimeout(()=>{void load()},300);return()=>clearTimeout(timer)},[load]);
 useEffect(()=>{let active=true;if(initialPatientId){void getPatient(token,initialPatientId).then(r=>{if(active)setSelected(r.patient)}).catch(()=>{if(active)setError("Seçili hasta bulunamadı veya erişim izni yok.")})}return()=>{active=false}},[token,initialPatientId]);
 async function open(){const url=selected?`https://dentalai.tr/voice-exams/${selected.id}/session`:"https://dentalai.tr/voice-exams";try{await Linking.openURL(url)}catch{setError("Sesli Muayene sayfası açılamadı.")}}
 if(stage==="exam")return <ScrollView style={{flex:1,backgroundColor:"#F5F7FA"}} contentContainerStyle={{padding:16,paddingBottom:42}}>
  <Pressable accessibilityRole="button" onPress={()=>setStage("select")}><Text style={{color:navy,fontWeight:"700"}}>‹ Hasta seçimine dön</Text></Pressable>
  <Text style={{fontSize:25,fontWeight:"800",color:navy,marginTop:16}}>Sesli Muayene</Text>
  <Text style={{color:muted,marginTop:8}}>{selected?[selected.first_name,selected.last_name].filter(Boolean).join(" ")||selected.anonymous_id:"Hasta seçilmedi"}</Text>
  <View style={{backgroundColor:"white",borderRadius:18,padding:16,borderWidth:1,borderColor:line,marginTop:20}}>
   <Text style={{fontSize:17,fontWeight:"800",color:navy}}>Muayene hazırlığı</Text>
   <Pressable accessibilityRole="checkbox" accessibilityState={{checked:consent}} onPress={()=>setConsent(v=>!v)} style={{flexDirection:"row",alignItems:"flex-start",gap:10,marginTop:18}}>
    <Text style={{fontSize:21,color:navy}}>{consent?"☑":"☐"}</Text><Text style={{flex:1,color:navy,lineHeight:21}}>Hastayı bilgilendirdim. Sesin Gemini ile yazıya çevrilmesini ve klinik metnin Claude ile değerlendirilmesini onaylıyorum.</Text>
   </Pressable>
   <Text style={{color:muted,lineHeight:20,marginTop:14}}>Kayıt yalnızca hazır olduğunda başlatılmalı. Bu beta sürümünde native mikrofon henüz bağlanmadı; işlevsiz bir kayıt düğmesi göstermiyoruz.</Text>
   <Text style={{fontWeight:"800",color:navy,marginTop:20}}>Muayene metni</Text>
   <TextInput multiline maxLength={72000} accessibilityLabel="Muayene metni" placeholder="Muayene notunu buraya yazabilirsiniz." value={transcript} onChangeText={setTranscript} style={{marginTop:10,borderWidth:1,borderColor:line,borderRadius:12,minHeight:160,textAlignVertical:"top",padding:12,color:navy}}/>
   <Text style={{color:muted,fontSize:12,marginTop:8}}>{transcript.length}/72000 karakter · Metin henüz sunucuya gönderilmiyor.</Text>
   <Pressable accessibilityRole="button" disabled={!consent||!selected} onPress={()=>void open()} style={{backgroundColor:consent&&selected?navy:"#9BA7B7",borderRadius:12,padding:15,alignItems:"center",marginTop:18}}><Text style={{color:"white",fontWeight:"800"}}>Webdeki Tam Muayeneye Geç</Text></Pressable>
   <Text style={{color:muted,fontSize:12,lineHeight:19,marginTop:12}}>Mevcut web değerlendirmesi açılır. Buraya yazdığınız metin otomatik aktarılmaz. Kaydetmeden ekranı kapatmayın.</Text>
  </View>
 </ScrollView>;
 return <ScrollView style={{flex:1,backgroundColor:"#F5F7FA"}} contentContainerStyle={{padding:16,paddingBottom:40}}>
  <Text style={{fontSize:25,fontWeight:"800",color:navy}}>Sesli Muayene</Text>
  <Text style={{color:muted,marginTop:7,lineHeight:21}}>Webdeki mevcut muayene akışına hasta seçerek ulaşın. Native mikrofon, transkript ve değerlendirme ekranları henüz aktarılmadı.</Text>
  <View style={{backgroundColor:"white",borderRadius:18,padding:16,borderWidth:1,borderColor:line,marginTop:18}}>
   <Text style={{fontWeight:"800",color:navy,marginBottom:9}}>Hasta seçimi</Text>
   <TextInput accessibilityLabel="Hasta ara" value={query} onChangeText={setQuery} placeholder="Ad veya hasta kodu ara" style={{borderWidth:1,borderColor:line,borderRadius:12,padding:12,color:navy}}/>
   {busy&&<ActivityIndicator style={{marginTop:12}} color={navy}/>}
   {!!error&&<Text style={{color:"#B42318",marginTop:10}}>{error}</Text>}
   {!busy&&!patients.length&&!error&&<Text style={{color:muted,marginTop:12}}>Eşleşen hasta bulunamadı.</Text>}
   {patients.map(p=><Pressable accessibilityRole="radio" accessibilityState={{checked:selected?.id===p.id}} key={p.id} onPress={()=>setSelected(p)} style={{paddingVertical:13,borderBottomWidth:1,borderBottomColor:line,flexDirection:"row",alignItems:"center"}}>
    <Text style={{flex:1,color:navy,fontWeight:selected?.id===p.id?"800":"500"}}>{[p.first_name,p.last_name].filter(Boolean).join(" ")||p.anonymous_id}</Text>
    <Text style={{color:navy}}>{selected?.id===p.id?"●":"○"}</Text>
   </Pressable>)}
   <Pressable onPress={()=>{if(selected)setStage("exam");else setError("Önce bir hasta seçin.")}} style={{marginTop:18,backgroundColor:navy,padding:15,borderRadius:13,alignItems:"center"}}><Text style={{color:"white",fontWeight:"800"}}>{selected?"Muayeneye Devam Et":"Hasta Seçerek Devam Et"}</Text></Pressable>
   <Text style={{fontSize:12,color:muted,marginTop:10,lineHeight:18}}>Bu geçici geçiş web tarayıcısında açılır; web oturumunda giriş gerekebilir. Hasta kaydına otomatik veri yazılmaz.</Text>
  </View>
 </ScrollView>
}
