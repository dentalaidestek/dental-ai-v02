import React,{useCallback,useEffect,useState} from "react";
import {ActivityIndicator,Linking,Pressable,ScrollView,Text,TextInput,View} from "react-native";
import {getPatients,Patient} from "./api";

const navy="#071B35",muted="#63748A",line="#E1E7EF";
export default function VoiceExamEntry({token}:{token:string}){
 const [query,setQuery]=useState(""),[patients,setPatients]=useState<Patient[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(""),[selected,setSelected]=useState<Patient|null>(null);
 const load=useCallback(async()=>{setBusy(true);setError("");try{const r=await getPatients(token,query,0);setPatients(r.items)}catch(e){setError(e instanceof Error?e.message:"Hasta listesi alınamadı.")}finally{setBusy(false)}},[token,query]);
 useEffect(()=>{const timer=setTimeout(()=>{void load()},300);return()=>clearTimeout(timer)},[load]);
 async function open(){const url=selected?`https://dentalai.tr/voice-exams/${selected.id}/session`:"https://dentalai.tr/voice-exams";try{await Linking.openURL(url)}catch{setError("Sesli Muayene sayfası açılamadı.")}}
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
   <Pressable onPress={()=>void open()} style={{marginTop:18,backgroundColor:navy,padding:15,borderRadius:13,alignItems:"center"}}><Text style={{color:"white",fontWeight:"800"}}>{selected?"Seçili Hastanın Muayenesini Aç":"Sesli Muayeneyi Aç"}</Text></Pressable>
   <Text style={{fontSize:12,color:muted,marginTop:10,lineHeight:18}}>Bu geçici geçiş web tarayıcısında açılır; web oturumunda giriş gerekebilir. Hasta kaydına otomatik veri yazılmaz.</Text>
  </View>
 </ScrollView>
}
