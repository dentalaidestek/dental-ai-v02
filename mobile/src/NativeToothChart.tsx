import React,{useCallback,useEffect,useMemo,useState}from"react";
import{ActivityIndicator,Pressable,ScrollView,Text,View}from"react-native";
import{getPatient,PatientDetail,ToothStatusCode,ToothSurfaceCode,updateTooth}from"./api";
import{useRealtime}from"./realtime";

const ADULT=["18","17","16","15","14","13","12","11","21","22","23","24","25","26","27","28","48","47","46","45","44","43","42","41","31","32","33","34","35","36","37","38"];
const PRIMARY=["55","54","53","52","51","61","62","63","64","65","85","84","83","82","81","71","72","73","74","75"];
const STATUS:[ToothStatusCode,string][]=[["HEALTHY","Sağlıklı"],["CARIES","Çürük"],["FILLING","Dolgu"],["CROWN","Kron"],["ROOT_CANAL","Kanal"],["EXTRACTED","Çekilmiş"],["IMPLANT","İmplant"],["OTHER","Diğer"]];
const SURFACES:[ToothSurfaceCode,string][]=[["OCCLUSAL","Oklüzal"],["INCISAL","İnsizal"],["MESIAL","Mesial"],["DISTAL","Distal"],["BUCCAL","Bukkal"],["LINGUAL","Lingual"]];
const statusShort:any={HEALTHY:"✓",CARIES:"Ç",FILLING:"D",CROWN:"K",ROOT_CANAL:"KT",EXTRACTED:"×",IMPLANT:"İ",OTHER:"•"};

export default function NativeToothChart({token,patientId}:{token:string;patientId:number}){
 const{lastEvent}=useRealtime();const[d,setD]=useState<PatientDetail|null>(null),[selected,setSelected]=useState(""),[status,setStatus]=useState<ToothStatusCode>("HEALTHY"),[surface,setSurface]=useState<ToothSurfaceCode|undefined>(),[busy,setBusy]=useState(false),[err,setErr]=useState("");
 const load=useCallback(()=>{let active=true;setD(null);setSelected("");setSurface(undefined);setErr("");getPatient(token,patientId).then(result=>{if(active)setD(result)}).catch(e=>{if(active)setErr(e?.message||"Diş verileri alınamadı.")});return()=>{active=false}},[token,patientId]);useEffect(()=>load(),[load]);useEffect(()=>{if(lastEvent&&Number(lastEvent.entity_id)===patientId&&lastEvent.event_type==="TOOTH_UPDATED"){const p=lastEvent.payload||{};setD(v=>v?{...v,teeth:v.teeth.map(t=>t.tooth_number===String(p.tooth_number)?{...t,status:p.status}:t)}:v)}},[lastEvent,patientId]);
 const map=useMemo(()=>new Map((d?.teeth||[]).map(t=>[t.tooth_number,t.status as ToothStatusCode])),[d]);
 useEffect(()=>{if(selected)setStatus(map.get(selected)||"HEALTHY")},[selected,map]);
 // A surface belongs to a specific tooth; never carry it into another tooth record.
 useEffect(()=>{setSurface(undefined)},[selected,patientId]);
 async function save(){if(!selected)return;setBusy(true);setErr("");try{await updateTooth(token,patientId,selected,{status,note:undefined,surface});setD(v=>v?{...v,teeth:v.teeth.some(t=>t.tooth_number===selected)?v.teeth.map(t=>t.tooth_number===selected?{...t,status}:t):[...v.teeth,{id:-Date.now(),tooth_number:selected,status}]}:v)}catch(e:any){setErr(e?.message||"Diş durumu kaydedilemedi.")}finally{setBusy(false)}}
 if(!d)return <View style={{padding:30,alignItems:"center"}}>{err?<><Text accessibilityRole="alert" style={{color:"#B42318",textAlign:"center"}}>{err}</Text><Pressable accessibilityRole="button" onPress={()=>{setErr("");load()}} style={{padding:14,marginTop:12}}><Text style={{color:"#1769AA",fontWeight:"800"}}>Tekrar dene</Text></Pressable></>:<ActivityIndicator color="#071B35"/>}</View>;
 // Keep FDI quadrants together on every screen width; never wrap 16 teeth into arbitrary rows.
 const row=(numbers:string[],label:string)=><View style={{marginTop:16}}>
  <Text style={{fontSize:13,fontWeight:"800",color:"#53657B",marginBottom:10}}>{label}</Text>
  <View style={{flexDirection:"row",gap:5}}>
   {[numbers.slice(0,numbers.length/2),numbers.slice(numbers.length/2)].map((quadrant,index)=>
    <View key={index} style={{flex:1,flexDirection:"row",gap:3,justifyContent:index===0?"flex-end":"flex-start"}}>
     {quadrant.map(n=>{const st=map.get(n)||"HEALTHY";const active=selected===n;return <Pressable
      accessibilityRole="button" accessibilityLabel={`Diş ${n}, ${STATUS.find(x=>x[0]===st)?.[1]||"Durum bilinmiyor"}`}
      accessibilityState={{selected:active}} key={n} disabled={busy} onPress={()=>{if(!busy)setSelected(n)}}
      style={{flex:1,minWidth:0,maxWidth:44,height:54,borderRadius:9,borderWidth:1,borderColor:active?"#071B35":"#DCE3EB",backgroundColor:active?"#071B35":"#FFF",alignItems:"center",justifyContent:"center"}}>
      <Text style={{fontSize:11,fontWeight:"800",color:active?"#FFF":"#102033"}}>{n}</Text>
      <Text style={{fontSize:12,fontWeight:"800",color:active?"#FFF":"#718096",marginTop:3}}>{statusShort[st]||"•"}</Text>
     </Pressable>})}
    </View>)}
  </View>
 </View>;
 return <ScrollView contentContainerStyle={{paddingBottom:30}}><View style={{backgroundColor:"#FFF",borderRadius:18,padding:12,borderWidth:1,borderColor:"#E5EAF0"}}>{row(ADULT.slice(0,16),"Üst çene · Daimi")}{row(ADULT.slice(16),"Alt çene · Daimi")}{row(PRIMARY.slice(0,10),"Üst çene · Süt")}{row(PRIMARY.slice(10),"Alt çene · Süt")}</View>{selected&&<View style={{backgroundColor:"#FFF",borderRadius:18,padding:15,borderWidth:1,borderColor:"#E5EAF0",marginTop:12}}><Text style={{fontSize:18,fontWeight:"900",color:"#102033"}}>Diş {selected}</Text><Text style={{fontSize:12,color:"#718096",marginTop:3}}>Durum</Text><View style={{flexDirection:"row",flexWrap:"wrap",gap:7,marginTop:8}}>{STATUS.map(([v,l])=><Pressable key={v} onPress={()=>setStatus(v)} style={{paddingHorizontal:11,paddingVertical:9,borderRadius:11,backgroundColor:status===v?"#071B35":"#F5F7FA"}}><Text style={{fontSize:11,fontWeight:"800",color:status===v?"#FFF":"#102033"}}>{l}</Text></Pressable>)}</View><Text style={{fontSize:12,color:"#718096",marginTop:14}}>Yüzey</Text><View style={{flexDirection:"row",flexWrap:"wrap",gap:7,marginTop:8}}>{SURFACES.map(([v,l])=><Pressable key={v} onPress={()=>setSurface(surface===v?undefined:v)} style={{paddingHorizontal:11,paddingVertical:9,borderRadius:11,backgroundColor:surface===v?"#DCE7F3":"#F5F7FA"}}><Text style={{fontSize:11,fontWeight:"800",color:"#102033"}}>{l}</Text></Pressable>)}</View>{!!err&&<Text style={{color:"#B42318",marginTop:10}}>{err}</Text>}<Pressable onPress={save} disabled={busy} style={{height:50,borderRadius:14,backgroundColor:"#071B35",alignItems:"center",justifyContent:"center",marginTop:14}}>{busy?<ActivityIndicator color="#fff"/>:<Text style={{color:"#FFF",fontWeight:"800"}}>Durumu Kaydet</Text>}</Pressable></View>}</ScrollView>
}
