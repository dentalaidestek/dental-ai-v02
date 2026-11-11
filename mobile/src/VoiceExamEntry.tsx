import React,{useCallback,useEffect,useRef,useState} from "react";
import {ActivityIndicator,Alert,Linking,Pressable,ScrollView,Text,TextInput,View} from "react-native";
import {getPatient,getPatients,Patient} from "./api";
import {extractVoice,finalizeVoice,VoiceExtraction} from "./voiceApi";

const navy="#071B35",muted="#63748A",line="#E1E7EF";
const fieldLabels:Record<string,string>={first_name:"Ad",last_name:"Soyad",age:"Yaş",chief_complaint:"Başvuru şikâyeti",medical_history:"Sağlık geçmişi",family_history:"Aile sağlık öyküsü",materials:"Konuşulan materyaller",dental_history:"Önceki diş tedavileri",oral_habits:"Ağız bakımı ve alışkanlıklar",medications:"İlaç bilgileri",allergies:"Alerji bilgileri",clinical_findings:"Muayene bulguları",plan:"Konuşulan tedavi planı"};
const reviewSections:[string,string][]=[["summary","Özet"],["questions","Netleştirilecek sorular"],["contradictions","Çelişkiler"],["clinical_items","Klinik değerlendirmeler"],["references","Kaynaklar"],["unavailable","Doğrulanamayanlar"]];
function readable(value:unknown):string{
 if(typeof value==="string")return value;
 if(typeof value==="number"||typeof value==="boolean")return String(value);
 if(Array.isArray(value))return value.map(readable).filter(Boolean).join(" · ");
 if(value&&typeof value==="object"){const item=value as Record<string,unknown>;return ["text","description","finding","recommendation","reason","quote","status","title","label","url"].filter(k=>item[k]!=null).map(k=>readable(item[k])).filter(Boolean).join(" — ")||"Ayrıntı belirtilmedi";}
 return "";
}
function ResultSection({name,items}:{name:string;items:unknown}){
 const [expanded,setExpanded]=useState(false);const rows=Array.isArray(items)?items:items==null?[]:[items];
 return <View style={{borderWidth:1,borderColor:line,borderRadius:13,marginTop:12,overflow:"hidden"}}>
 <Pressable accessibilityRole="button" accessibilityState={{expanded}} onPress={()=>setExpanded(v=>!v)} style={{padding:14,flexDirection:"row",justifyContent:"space-between",alignItems:"center",backgroundColor:"#F6FAFD"}}>
 <Text style={{fontWeight:"800",color:navy,flex:1}}>{name} ({rows.length})</Text><Text style={{color:navy}}>{expanded?"−":"+"}</Text>
 </Pressable>
 {expanded&&(rows.length?rows.map((item,i)=><View key={i} style={{padding:12,borderTopWidth:1,borderTopColor:line}}><Text selectable style={{color:navy,lineHeight:21}}>{readable(item)}</Text>{item&&typeof item==="object"&&typeof (item as Record<string,unknown>).url==="string"&&<Pressable accessibilityRole="link" onPress={()=>void Linking.openURL(String((item as Record<string,unknown>).url))}><Text style={{color:"#1769AA",marginTop:6}}>Kaynağı aç</Text></Pressable>}</View>):<Text style={{color:muted,padding:12}}>Bu bölümde kayıt yok.</Text>)}
 </View>;
}

export default function VoiceExamEntry({token,initialPatientId}:{token:string;initialPatientId?:number}){
 const [privacyExpanded,setPrivacyExpanded]=useState(false),[processing,setProcessing]=useState(false),[editingFields,setEditingFields]=useState(false),[review,setReview]=useState<VoiceExtraction|null>(null),[finalResult,setFinalResult]=useState<Record<string,unknown>|null>(null),[clinicalError,setClinicalError]=useState(""),[stage,setStage]=useState<"select"|"exam">("select"),[consent,setConsent]=useState(false),[transcript,setTranscript]=useState(""),[query,setQuery]=useState(""),[patients,setPatients]=useState<Patient[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(""),[selected,setSelected]=useState<Patient|null>(null);
 const processingLock=useRef(false),generation=useRef(0),scope=useRef(token+":"+(selected?.id||0));
 scope.current=token+":"+(selected?.id||0);
 useEffect(()=>{generation.current++;processingLock.current=false;setProcessing(false);setReview(null);setFinalResult(null);setClinicalError("");setTranscript("");setConsent(false);setStage("select")},[token,selected?.id]);
 const load=useCallback(async()=>{setBusy(true);setError("");try{const r=await getPatients(token,query,0);setPatients(r.items)}catch(e){setError(e instanceof Error?e.message:"Hasta listesi alınamadı.")}finally{setBusy(false)}},[token,query]);
 useEffect(()=>{const timer=setTimeout(()=>{void load()},300);return()=>clearTimeout(timer)},[load]);
 useEffect(()=>{let active=true;if(initialPatientId){void getPatient(token,initialPatientId).then(r=>{if(active)setSelected(r.patient)}).catch(()=>{if(active)setError("Seçili hasta bulunamadı veya erişim izni yok.")})}return()=>{active=false}},[token,initialPatientId]);
 async function processText(){if(!selected||!consent||!transcript.trim()||processingLock.current)return;if(transcript.length>18000){setClinicalError("Metin çözümleme sınırı 18.000 karakterdir. Uzun görüşmelerin bölümlerini ayrı ayrı işleyin; tamamını silmeyin.");return;}processingLock.current=true;const request=++generation.current,currentScope=scope.current;setProcessing(true);setClinicalError("");try{const result=await extractVoice(token,selected.id,transcript);if(request!==generation.current||currentScope!==scope.current)return;setReview(result);setEditingFields(false);setFinalResult(null)}catch(e){if(request===generation.current&&currentScope===scope.current)setClinicalError(e instanceof Error?e.message:"Muayene değerlendirilemedi.")}finally{if(request===generation.current&&currentScope===scope.current){processingLock.current=false;setProcessing(false)}}}
 async function finalize(){if(!selected||!review||processingLock.current)return;processingLock.current=true;const request=++generation.current,currentScope=scope.current;setProcessing(true);setClinicalError("");try{const data=review.review;const response=await finalizeVoice(token,selected.id,{context:{fields:data.fields||{},teeth:data.teeth||[],literature_topics:data.literature_topics||[],source_requests:data.source_requests||[]},insights:data.insights||[],uncertain:data.uncertain||[],conversation_text:transcript});if(request===generation.current&&currentScope===scope.current)setFinalResult((response.final||{}) as Record<string,unknown>)}catch(e){if(request===generation.current&&currentScope===scope.current)setClinicalError(e instanceof Error?e.message:"Son değerlendirme tamamlanamadı.")}finally{if(request===generation.current&&currentScope===scope.current){processingLock.current=false;setProcessing(false)}}}
 async function open(){const url=selected?`https://dentalai.tr/voice-exams/${selected.id}/session`:"https://dentalai.tr/voice-exams";try{await Linking.openURL(url)}catch{setError("Sesli Muayene sayfası açılamadı.")}}
 if(stage==="exam")return <ScrollView style={{flex:1,backgroundColor:"#F5F7FA"}} contentContainerStyle={{padding:16,paddingBottom:42}}>
  <Pressable accessibilityRole="button" onPress={()=>{if(transcript.trim())Alert.alert("Metin kaybolabilir","Bu ekrandaki muayene metni henüz kalıcı kaydedilmiyor.",[{text:"Vazgeç",style:"cancel"},{text:"Geri dön",style:"destructive",onPress:()=>setStage("select")}]);else setStage("select")}}><Text style={{color:navy,fontWeight:"700"}}>‹ Hasta seçimine dön</Text></Pressable>
  <Text style={{fontSize:25,fontWeight:"800",color:navy,marginTop:16}}>Sesli Muayene</Text>
  <Text style={{color:muted,marginTop:8}}>{selected?[selected.first_name,selected.last_name].filter(Boolean).join(" ")||selected.anonymous_id:"Hasta seçilmedi"}</Text>
  <View style={{backgroundColor:"white",borderRadius:18,padding:16,borderWidth:1,borderColor:line,marginTop:20}}>
   <Text style={{fontSize:17,fontWeight:"800",color:navy}}>Muayene hazırlığı</Text>
   <Text style={{color:muted,marginTop:8}}>Hazırlık · Metin · Klinik değerlendirme · Hekim onayı</Text>
   <Pressable accessibilityRole="checkbox" accessibilityState={{checked:consent}} onPress={()=>setConsent(v=>!v)} style={{flexDirection:"row",alignItems:"flex-start",gap:10,marginTop:18}}>
    <Text style={{fontSize:21,color:navy}}>{consent?"☑":"☐"}</Text><Text style={{flex:1,color:navy,lineHeight:21}}>Hastayı bilgilendirdim. Sesin Gemini ile yazıya çevrilmesini ve klinik metnin Claude ile değerlendirilmesini onaylıyorum.</Text>
   </Pressable>
   <Pressable accessibilityRole="button" accessibilityState={{expanded:privacyExpanded}} onPress={()=>setPrivacyExpanded(v=>!v)} style={{marginTop:14,paddingVertical:10}}><Text style={{fontWeight:"700",color:navy}}>Veriler ve taslak hakkında {privacyExpanded?"−":"+"}</Text></Pressable>
   {privacyExpanded&&<Text style={{color:muted,lineHeight:20}}>Ses dosyası işlenirken Gemini kullanılır; klinik değerlendirme Claude ile yapılır. Ham ses ve tam konuşma metni hasta dosyasına otomatik kaydedilmez. Kimlik ve iletişim bilgilerini konuşma metnine eklemeyin. Bu mobil sürümde metin taslağı kalıcı saklanmaz.</Text>}
   <Text style={{color:muted,lineHeight:20,marginTop:14}}>Native mikrofon henüz bağlanmadı. Klinik değerlendirme için geçici metin alanını kullanabilirsiniz.</Text>
   <Text style={{fontWeight:"800",color:navy,marginTop:20}}>Muayene metni</Text>
   <TextInput multiline maxLength={72000} accessibilityLabel="Muayene metni" placeholder="Muayene notunu buraya yazabilirsiniz." value={transcript} onChangeText={v=>{setTranscript(v);setReview(null);setFinalResult(null)}} style={{marginTop:10,borderWidth:1,borderColor:line,borderRadius:12,minHeight:160,textAlignVertical:"top",padding:12,color:navy}}/>
   <Text style={{color:muted,fontSize:12,marginTop:8}}>{transcript.length}/72000 karakter · Tek seferde çözümleme sınırı 18.000 karakterdir. Metin yalnız değerlendirme düğmesine bastığınızda gönderilir.</Text>
   {!!clinicalError&&<Text style={{color:"#B42318",marginTop:12}}>{clinicalError}</Text>}
   <Pressable accessibilityRole="button" disabled={processing||!consent||!selected||!transcript.trim()||transcript.length>18000} onPress={()=>void processText()} style={{backgroundColor:processing||!consent||!selected||!transcript.trim()||transcript.length>18000?"#9BA7B7":"#1769AA",borderRadius:12,padding:15,alignItems:"center",marginTop:18}}><Text style={{color:"white",fontWeight:"800"}}>{processing?"Değerlendiriliyor…":"Metni Klinik Olarak Çözümle"}</Text></Pressable>
   {review&&<View style={{marginTop:18,borderTopWidth:1,borderTopColor:line,paddingTop:15}}>
    <Text style={{fontSize:17,fontWeight:"800",color:navy}}>Çıkarılan muayene bilgileri</Text>
    <Pressable accessibilityRole="button" onPress={()=>setEditingFields(v=>!v)} style={{paddingVertical:12}}><Text style={{fontWeight:"800",color:"#1769AA"}}>{editingFields?"Düzenlemeyi bitir":"Çıkarılan bilgileri kontrol et / düzenle"}</Text></Pressable>{Object.entries(review.review.fields||{}).map(([name,item])=><View key={name} style={{paddingVertical:9,borderBottomWidth:1,borderBottomColor:line}}><Text style={{fontWeight:"700",color:navy}}>{fieldLabels[name]||name.replace(/_/g," ")}</Text>{editingFields?<TextInput multiline accessibilityLabel={fieldLabels[name]||name} value={item.value} onChangeText={value=>{setReview(previous=>previous?{...previous,review:{...previous.review,fields:{...previous.review.fields,[name]:{...item,value,edited:true}}}}:previous);setFinalResult(null)}} style={{color:navy,borderWidth:1,borderColor:line,borderRadius:9,padding:10,marginTop:6}}/>:<Text style={{color:muted,marginTop:4}}>{item.value}</Text>}</View>)}
    <Text style={{color:muted,marginTop:10}}>Bunlar taslak bilgilerdir; hasta dosyasına kaydedilmedi.</Text>
    <Pressable accessibilityRole="button" disabled={processing} onPress={()=>void finalize()} style={{backgroundColor:navy,padding:15,borderRadius:12,alignItems:"center",marginTop:14}}><Text style={{color:"white",fontWeight:"800"}}>Hekim Kontrolünden Sonra Klinik Değerlendirme</Text></Pressable>
   </View>}
   {finalResult&&<View style={{marginTop:18,borderTopWidth:1,borderTopColor:line,paddingTop:15}}>
    <Text style={{fontSize:18,fontWeight:"800",color:navy}}>Kaynaklı klinik değerlendirme</Text>
    {reviewSections.map(([key,label])=><ResultSection key={key} name={label} items={finalResult[key]}/>)}
    <Text style={{color:"#B42318",marginTop:12}}>Hekim kontrolü gereklidir. Sonuç otomatik olarak hasta dosyasına yazılmaz.</Text>
   </View>}
   <Pressable accessibilityRole="button" disabled={!consent||!selected} onPress={()=>void open()} style={{backgroundColor:consent&&selected?navy:"#9BA7B7",borderRadius:12,padding:15,alignItems:"center",marginTop:18}}><Text style={{color:"white",fontWeight:"800"}}>Webdeki Tam Muayeneyi Aç</Text></Pressable>
   <Text style={{color:muted,fontSize:12,lineHeight:19,marginTop:12}}>Mevcut web değerlendirmesi açılır. Buraya yazdığınız metin web sayfasına otomatik aktarılmaz. Webe geçmeden önce metninizi güvenli bir yere alın; bu alan kalıcı kayıt değildir.</Text>
  </View>
 </ScrollView>;
 return <ScrollView style={{flex:1,backgroundColor:"#F5F7FA"}} contentContainerStyle={{padding:16,paddingBottom:40}}>
  <Text style={{fontSize:25,fontWeight:"800",color:navy}}>Sesli Muayene</Text>
  <Text style={{color:muted,marginTop:7,lineHeight:21}}>Webdeki mevcut muayene akışına hasta seçerek ulaşın. Hasta seçerek muayeneye başlayın. Konuşma metni ve klinik değerlendirme bu ekranda yönetilir.</Text>
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
   <Text style={{fontSize:12,color:muted,marginTop:10,lineHeight:18}}>Muayene bilgileri yalnızca hekim onayıyla hasta dosyasına kaydedilir.</Text>
  </View>
 </ScrollView>
}
