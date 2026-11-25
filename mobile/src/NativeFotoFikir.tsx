// Foto Fikir mobil stüdyosu: SocialDent web akışının birebir mobil karşılığı
// (konu -> metin onayı -> görsel); araçlar (marka kiti, Instagram profili,
// Reels planı, son işlemler) isteğe bağlıdır. UI'da anlatı/teorik metin yoktur.
import * as ImagePicker from "expo-image-picker";
import React,{useCallback,useEffect,useRef,useState}from"react";
import{ActivityIndicator,Image,Modal,Pressable,ScrollView,Text,TextInput,View}from"react-native";
import{
 ffImageSource,getFFBootstrap,suggestFFIdeas,prepareFFSlides,checkFFMevzuat,
 generateFFImages,uploadFFBrandKit,generateFFBrandScene,getFFIgProfile,
 getFFReelsPlan,getFFHistory,
 type FFBootstrap,FFIdea,FFSlide,FFMevzuatResult,FFIgProfile,FFReelsPlan,FFReelsShot,FFJob,FFStyleRecommendation,FFCreativeAudit,
}from"./fotoFikirApi";

const C={navy:"#071B35",bg:"#F5F7FA",white:"#FFF",text:"#102033",muted:"#718096",line:"#E5EAF0",soft:"#EEF3F8",green:"#16803C",red:"#B42318"};
const card={backgroundColor:C.white,borderRadius:18,borderWidth:1,borderColor:C.line,padding:16,marginBottom:12} as any;
const FF_SCENES=["Loupe takarken","Eldivenle kalp yaparken","Ağız içi tarayıcıyla çalışırken","Diş modeliyle anlatırken","Hastayla konuşurken","Resepsiyonda"];
const FF_TONES=[["bilgilendirici","Bilgilendirici"],["samimi","Samimi"],["profesyonel","Profesyonel"],["eğitici","Eğitici"]];
const FF_TONE_LABELS:Record<string,string>=Object.fromEntries(FF_TONES);
const FF_LEVEL_COLORS:Record<string,{bg:string;fg:string}>={OK:{bg:"#ECFDF5",fg:"#047857"},DIKKAT:{bg:"#FFF7ED",fg:"#C2410C"},DİKKAT:{bg:"#FFF7ED",fg:"#C2410C"},KALDIR:{bg:"#FEF2F2",fg:"#B91C1C"}};
function Btn({title,onPress,disabled=false,primary=false}:{title:string;onPress:()=>void;disabled?:boolean;primary?:boolean}){return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={[s.btn,primary&&{backgroundColor:C.navy},disabled&&{opacity:.5}]}><Text style={s.btnT}>{title}</Text></Pressable>}
function Chip({label,active,onPress}:{label:string;active:boolean;onPress:()=>void}){return <Pressable accessibilityRole="button" accessibilityState={{selected:active}} onPress={onPress} style={{paddingVertical:7,paddingHorizontal:12,borderRadius:16,borderWidth:1,borderColor:active?C.navy:C.line,backgroundColor:active?C.navy:C.white,marginRight:8,marginBottom:8}}><Text style={{color:active?C.white:C.navy,fontSize:12,fontWeight:"700"}}>{label}</Text></Pressable>}
function LevelBadge({level}:{level:string}){const v=FF_LEVEL_COLORS[level]||{bg:C.soft,fg:C.navy};return <Text style={{fontSize:10,fontWeight:"800",color:v.fg,backgroundColor:v.bg,paddingHorizontal:8,paddingVertical:4,borderRadius:10}}>{level==="DIKKAT"?"DİKKAT":level}</Text>}
function Section({title,open,onToggle,children}:{title:string;open:boolean;onToggle:()=>void;children:React.ReactNode}){return <View style={card}>
 <Pressable accessibilityRole="button" accessibilityState={{expanded:open}} onPress={onToggle} style={s.row}><Text style={s.title}>{title}</Text><Text style={{color:C.navy,fontWeight:"800"}}>{open?"⌃":"⌄"}</Text></Pressable>
 {open&&<View style={{marginTop:10}}>{children}</View>}
</View>;}

export default function NativeFotoFikir({token}:{token:string}){
 const activeToken=useRef(token);if(activeToken.current!==token)activeToken.current=token;
 const[boot,setBoot]=useState<FFBootstrap|null>(null),[bootErr,setBootErr]=useState("");
 const[step,setStep]=useState(1);
 const[topic,setTopic]=useState(""),[ideas,setIdeas]=useState<FFIdea[]>([]),[ideaTips,setIdeaTips]=useState<string[]>([]);
 const[ideaBusy,setIdeaBusy]=useState(false),[slideBusy,setSlideBusy]=useState(false);
 const[slideCount,setSlideCount]=useState(5),[tone,setTone]=useState("bilgilendirici");
 const[slides,setSlides]=useState<FFSlide[]>([]);
 const[mevzuat,setMevzuat]=useState<Record<number,FFMevzuatResult>>({}),[disclaimer,setDisclaimer]=useState(""),[mevSummary,setMevSummary]=useState("");
 const[mevBusy,setMevBusy]=useState(false),[flowErr,setFlowErr]=useState("");
 const[styleId,setStyleId]=useState(""),[includeName,setIncludeName]=useState(true);
 const[genBusy,setGenBusy]=useState(false),[gallery,setGallery]=useState<Array<{path:string;caption:string}>>([]);
 const[genNote,setGenNote]=useState(""),[genTips,setGenTips]=useState<string[]>([]),[recommendation,setRecommendation]=useState<FFStyleRecommendation|null>(null),[audit,setAudit]=useState<FFCreativeAudit|null>(null);
 const[brandOpen,setBrandOpen]=useState(false),[brandBusy,setBrandBusy]=useState(false),[brandErr,setBrandErr]=useState(""),[brandScene,setBrandScene]=useState(""),[brandSceneErr,setBrandSceneErr]=useState(""),[brandSceneBusy,setBrandSceneBusy]=useState(false);
 const[igOpen,setIgOpen]=useState(false),[igBusy,setIgBusy]=useState(false),[ig,setIg]=useState<FFIgProfile|null>(null),[igErr,setIgErr]=useState("");
 const[reelsOpen,setReelsOpen]=useState(false),[reelsTopic,setReelsTopic]=useState(""),[reelsBusy,setReelsBusy]=useState(false),[reels,setReels]=useState<FFReelsPlan|null>(null),[reelsErr,setReelsErr]=useState("");
 const[histOpen,setHistOpen]=useState(false),[histBusy,setHistBusy]=useState(false),[histErr,setHistErr]=useState(""),[jobs,setJobs]=useState<FFJob[]>([]);
 const[preview,setPreview]=useState<string|null>(null);
 useEffect(()=>{
  let alive=true;
  setBoot(null);setBootErr("");setIdeas([]);setIdeaTips([]);setSlides([]);setMevzuat({});setMevSummary("");setGallery([]);setIg(null);setReels(null);setJobs([]);setStep(1);setStyleId("");setTopic("");setGenNote("");setGenTips([]);setRecommendation(null);setAudit(null);
  void(async()=>{try{
   const data=await getFFBootstrap(token);
   if(!alive||activeToken.current!==token)return;
   setBoot(data);setStyleId(data.styles[0]?.id||"");
  }catch(e){if(alive&&activeToken.current===token)setBootErr(e instanceof Error?e.message:"Foto Fikir açılamadı.")}})();
  return()=>{alive=false};
 },[token]);
 const quota=boot?.quota;
 const refreshHistory=useCallback(async()=>{
  setHistBusy(true);setHistErr("");
  try{const r=await getFFHistory(token);if(activeToken.current===token)setJobs(r.jobs)}
  catch(e){if(activeToken.current===token)setHistErr(e instanceof Error?e.message:"Son işlemler alınamadı.")}
  finally{if(activeToken.current===token)setHistBusy(false)}
 },[token]);
 async function suggestIdeas(){if(ideaBusy)return;setIdeaBusy(true);setFlowErr("");
  try{const r=await suggestFFIdeas(token,topic);if(activeToken.current===token){setIdeas(r.ideas||[]);setIdeaTips(r.tips||[])}}
  catch(e){if(activeToken.current===token)setFlowErr(e instanceof Error?e.message:"Fikir önerileri alınamadı.")}
  finally{if(activeToken.current===token)setIdeaBusy(false)}}
 async function makeSlides(topicOverride?:string){if(slideBusy)return;setSlideBusy(true);setFlowErr("");
  const chosen=(topicOverride??topic).trim();
  try{if(!chosen)throw Error("Önce bir konu yazın veya fikir seçin.");
   const r=await prepareFFSlides(token,chosen,slideCount,tone);if(activeToken.current!==token)return;
   setSlides(r.slides||[]);setMevzuat({});setMevSummary("");setStep(2)}
  catch(e){if(activeToken.current===token)setFlowErr(e instanceof Error?e.message:"Slayt metinleri hazırlanamadı.")}
  finally{if(activeToken.current===token)setSlideBusy(false)}}
 async function runMevzuat(){if(mevBusy||!slides.length)return;setMevBusy(true);setFlowErr("");
  try{const r=await checkFFMevzuat(token,slides.map(slide=>(slide.headline+" "+slide.body).trim()));
   if(activeToken.current!==token)return;
   const map:Record<number,FFMevzuatResult>={};let removeCount=0,warnCount=0;
   for(const row of r.results||[]){map[row.index]=row;if(row.level==="KALDIR")removeCount++;else if(row.level==="DIKKAT")warnCount++}
   setMevzuat(map);setDisclaimer(r.disclaimer||"");
   const parts:string[]=[];
   if(removeCount)parts.push(removeCount+" metin kaldırılmalı");
   if(warnCount)parts.push(warnCount+" metin dikkat gerektiriyor");
   setMevSummary(parts.length?"Kontrol tamamlandı: "+parts.join(", ")+".":"Kontrol tamamlandı: sorun bulunmadı.")}
  catch(e){if(activeToken.current===token)setFlowErr(e instanceof Error?e.message:"Mevzuat kontrolü yapılamadı.")}
  finally{if(activeToken.current===token)setMevBusy(false)}}
 async function generate(){if(genBusy)return;setGenBusy(true);setFlowErr("");
  try{const r=await generateFFImages(token,{topic,styleId,slides,includeName});
   if(activeToken.current!==token)return;
   const styleLabel=r.style||styleId;
   setGallery(previous=>[...previous,...r.images.filter((p:string)=>typeof p==="string").map((p:string,index:number)=>({path:p,caption:"Slayt "+(previous.length+index+1)+" — "+styleLabel}))]);
   setBoot(previous=>previous?{...previous,quota:r.quota}:previous);refreshHistory();
   setRecommendation(r.style_recommendation||r.suggestion||null);
   setGenTips(r.tips||[]);setAudit(r.creative_audit||null);
   setGenNote("Görseller hazır"+(typeof r.uretim_ms==="number"?" ("+(r.uretim_ms/1000).toFixed(1)+" sn)":"")+(r.skipped?" — "+(r.uyari||r.skipped+" slayt atlandı"):""));
  }catch(e){if(activeToken.current===token)setFlowErr(e instanceof Error?e.message:"Görseller üretilemedi.")}
  finally{if(activeToken.current===token)setGenBusy(false)}}
 async function pickBrand(){if(brandBusy)return;
  try{const permission=await ImagePicker.requestMediaLibraryPermissionsAsync();
   if(!permission.granted)throw Error("Marka kiti için galeri izni gerekli.");
   const result=await ImagePicker.launchImageLibraryAsync({mediaTypes:["images"],quality:1,allowsMultipleSelection:true,selectionLimit:3,orderedSelection:true});
   if(result.canceled||!result.assets?.length)return;
   if(activeToken.current!==token)return;
   if(result.assets.length>3)throw Error("En fazla 3 fotoğraf yükleyin.");
   for(const asset of result.assets){
    const mime=String(asset.mimeType||(asset.fileName||"").toLowerCase().endsWith(".png")?"image/png":"image/jpeg");
    if(!/^image\/(png|jpeg)$/.test(mime))throw Error("Yalnızca PNG veya JPEG fotoğraf yükleyin.");
    if(asset.fileSize&&asset.fileSize>8*1024*1024)throw Error("Fotoğraflar en fazla 8 MB olabilir.");
   }
   setBrandBusy(true);setBrandErr("");
   const r=await uploadFFBrandKit(token,result.assets.map(asset=>({uri:asset.uri,name:asset.fileName||"marka.jpg",type:asset.mimeType||"image/jpeg"})));
   if(activeToken.current!==token)return;
   setBoot(previous=>previous?{...previous,brand_kit:{exists:true,photos_count:r.photos_count,photos:r.photos}}:previous);
  }catch(e){if(activeToken.current===token)setBrandErr(e instanceof Error?e.message:"Fotoğraflar yüklenemedi.")}
  finally{if(activeToken.current===token)setBrandBusy(false)}}
 async function makeScene(){if(brandSceneBusy)return;
  if(!boot?.brand_kit?.exists){setBrandSceneErr("Önce marka kiti fotoğrafı yükleyin.");return}
  setBrandSceneBusy(true);setBrandSceneErr("");
  try{const r=await generateFFBrandScene(token,brandScene);if(activeToken.current!==token)return;
   setGallery(previous=>[...previous,{path:r.image_url,caption:"Marka kiti — "+r.scene}]);
   setBoot(previous=>previous?{...previous,quota:r.quota}:previous);refreshHistory();
  }catch(e){if(activeToken.current===token)setBrandSceneErr(e instanceof Error?e.message:"Sahne görseli üretilemedi.")}
  finally{if(activeToken.current===token)setBrandSceneBusy(false)}}
 async function loadIg(){if(igBusy)return;setIgBusy(true);setIgErr("");
  try{const r=await getFFIgProfile(token);if(activeToken.current===token)setIg(r)}
  catch(e){if(activeToken.current===token)setIgErr(e instanceof Error?e.message:"Instagram planı alınamadı.")}
  finally{if(activeToken.current===token)setIgBusy(false)}}
 async function loadReels(){if(reelsBusy)return;setReelsBusy(true);setReelsErr("");
  try{const r=await getFFReelsPlan(token,reelsTopic);if(activeToken.current===token)setReels(r)}
  catch(e){if(activeToken.current===token)setReelsErr(e instanceof Error?e.message:"Reels planı alınamadı.")}
  finally{if(activeToken.current===token)setReelsBusy(false)}}
 const senaryoRows=((reels?.senaryo||[]) as Array<{aralik:string;metin:string;shot:FFReelsShot|string}>).map(row=>({...row,shot:typeof row.shot==="string"?row.shot:[row.shot.plan,row.shot.kamera,row.shot.hareket,row.shot.isik,row.shot.overlay,row.shot.ses_ritim].filter(value=>typeof value==="string"&&value.trim()).join(" · ")}));
 const stepChip=(number:number,title:string)=>(
  <Pressable key={number} accessibilityRole="button" onPress={()=>{if(step>number)setStep(number)}} style={{flexDirection:"row",alignItems:"center",gap:6,flex:1,paddingVertical:8,paddingHorizontal:10,borderRadius:12,borderWidth:1,borderColor:step===number?C.navy:C.line,backgroundColor:step===number?C.navy:C.white,opacity:step>=number?1:.55}}>
   <Text style={{fontSize:11,fontWeight:"800",color:step===number?C.white:C.navy}}>{number}</Text>
   <Text style={{fontSize:12,fontWeight:"700",color:step===number?C.white:C.text}} numberOfLines={1}>{title}</Text>
  </Pressable>);
 return <ScrollView style={s.page} contentContainerStyle={s.pad}>
  <Text style={s.big}>Foto Fikir</Text>
  <Text style={s.muted}>{boot?.profile.display_name||"Hekim"} · Bu ay {quota?quota.used:0}/{quota?quota.limit:30} görsel</Text>
  <View style={{flexDirection:"row",gap:8,marginTop:12,marginBottom:12}}>{stepChip(1,"Konu")}{stepChip(2,"Metin onayı")}{stepChip(3,"Görsel")}</View>
  {!!boot?.mock&&<View style={[card,{backgroundColor:"#FFF7ED",borderColor:"#F2C48D"}]}><Text style={{color:"#C2410C",fontSize:12,fontWeight:"700"}}>Örnek çıktı (mock) modu etkin: sunucu sağlayıcı anahtarları tanımlı değil; içerikler örnek olarak üretilir.</Text></View>}
  {!!bootErr&&<View style={card}><Text style={{color:C.red}}>{bootErr}</Text><Btn title="Tekrar dene" onPress={()=>setBootErr("")}/></View>}
  {step===1&&<View style={card}>
   <Text style={s.title}>1. Konu</Text>
   <TextInput accessibilityLabel="Foto Fikir konusu" style={s.input} value={topic} onChangeText={setTopic} placeholder="Konu yazın (ör. diş fırçalama alışkanlıkları)" placeholderTextColor={C.muted} maxLength={200}/>
   <View style={{flexDirection:"row",flexWrap:"wrap",marginTop:10}}>{ideas.map((idea,index)=><Chip key={index} label={idea.title} active={topic===idea.title} onPress={()=>{setTopic(idea.title);void makeSlides(idea.title)}}/>)}</View>
   {ideas.map((idea,index)=><Text key={"a"+index} style={s.meta}>{idea.title+" — "+idea.angle}{idea.hook?" · Kanca: "+idea.hook:""}</Text>)}
   {!!ideaTips.length&&<Text style={s.meta}>{ideaTips.join(" · ")}</Text>}
   <Btn title={ideaBusy?"Öneriler hazırlanıyor…":"Fikir öner"} disabled={ideaBusy} onPress={()=>void suggestIdeas()}/>
   <Btn title={slideBusy?"Slaytlar hazırlanıyor…":"Slayt metinlerini hazırla"} disabled={slideBusy||!topic.trim()} primary onPress={()=>void makeSlides()}/>
  </View>}
  {step===2&&<View style={card}>
   <Text style={s.title}>2. Metin onayı</Text>
   <Text style={s.meta}>Slayt sayısı</Text>
   <View style={{flexDirection:"row",flexWrap:"wrap",marginTop:6}}>{[3,4,5,6,7,8].map(count=><Chip key={count} label={String(count)} active={slideCount===count} onPress={()=>setSlideCount(count)}/>)}</View>
   <Text style={s.meta}>Ton</Text>
   <View style={{flexDirection:"row",flexWrap:"wrap",marginTop:6}}>{FF_TONES.map(([value,label])=><Chip key={value} label={label} active={tone===value} onPress={()=>setTone(value)}/>)}</View>
   <Btn title={slideBusy?"Slaytlar hazırlanıyor…":"Metinleri yenile"} disabled={slideBusy||!topic.trim()} onPress={()=>void makeSlides()}/>
   {slides.map((slide,index)=><View key={index} style={{marginTop:10,borderTopWidth:index?1:0,borderTopColor:C.line,paddingTop:index?10:0}}>
    <View style={s.row}><Text style={s.meta}>{index+1}. kart</Text>{!!slide.role&&<Text style={{fontSize:10,fontWeight:"800",color:"#2B5CAD",backgroundColor:"#E8EEF9",paddingHorizontal:8,paddingVertical:4,borderRadius:10}}>Görev: {slide.role}</Text>}{mevzuat[index]&&<LevelBadge level={mevzuat[index].level}/>}</View>
    <TextInput accessibilityLabel={"Kart "+(index+1)+" başlığı"} style={s.input} value={slide.headline} onChangeText={v=>setSlides(old=>old.map((item,i)=>i===index?{...item,headline:v}:item))} maxLength={120} placeholder="Başlık" placeholderTextColor={C.muted}/>
    <TextInput accessibilityLabel={"Kart "+(index+1)+" metni"} style={[s.input,{height:90,textAlignVertical:"top"}]} multiline value={slide.body} onChangeText={v=>setSlides(old=>old.map((item,i)=>i===index?{...item,body:v}:item))} maxLength={220} placeholder="Gövde metni" placeholderTextColor={C.muted}/>
    <Text style={[s.meta,{textAlign:"right"}]}>{slide.body.length}/220</Text>
    {!!slide.note&&<Text style={s.meta}>{slide.note}</Text>}
    {mevzuat[index]&&<View style={{marginTop:6}}>
     {!!mevzuat[index].reason&&<Text style={{color:mevzuat[index].level==="KALDIR"?C.red:"#C2410C",fontSize:12}}>{mevzuat[index].reason}</Text>}
     {!!mevzuat[index].suggestion&&<Text style={s.meta}>Öneri: {mevzuat[index].suggestion}</Text>}
     {!!mevzuat[index].creative_alternative&&<Text style={{color:C.navy,fontSize:12,fontWeight:"700",marginTop:4}}>Yaratıcı alternatif: {mevzuat[index].creative_alternative}</Text>}
    </View>}
   </View>)}
   <Btn title={mevBusy?"Mevzuat kontrolü yapılıyor…":"Mevzuat kontrolü yap"} disabled={mevBusy} onPress={()=>void runMevzuat()}/>
   {!!mevSummary&&<Text style={{color:C.navy,fontSize:13,fontWeight:"700",marginTop:8}}>{mevSummary}</Text>}
   {!!disclaimer&&<Text style={[s.meta,{marginTop:6}]}>{disclaimer}</Text>}
   <Btn title="Görsel adımına geç" primary onPress={()=>setStep(3)}/>
   <Btn title="Konu adımına dön" onPress={()=>setStep(1)}/>
  </View>}
  {step===3&&<View style={card}>
   <Text style={s.title}>3. Görsel</Text>
   <View style={{flexDirection:"row",flexWrap:"wrap",marginTop:10,gap:8}}>{(boot?.styles||[]).map(style=>(
    <Pressable key={style.id} accessibilityRole="button" accessibilityState={{selected:styleId===style.id}} onPress={()=>setStyleId(style.id)} style={{width:"47%",flexGrow:1,borderRadius:12,borderWidth:1,borderColor:styleId===style.id?C.navy:C.line,backgroundColor:styleId===style.id?C.soft:C.white,padding:11,marginBottom:2}}>
     <Text style={{fontSize:13,fontWeight:"800",color:C.navy}}>{style.name}</Text>
     {!!style.hint&&<Text style={{fontSize:11,color:C.muted,marginTop:3}}>{style.hint}</Text>}
    </Pressable>))}</View>
   {!!recommendation&&<Pressable accessibilityRole="button" onPress={()=>setStyleId(recommendation.style_id)} style={{marginTop:8}}>
    <Text style={{color:"#1F3F76",fontSize:12,fontWeight:"700",backgroundColor:"#EEF3FB",borderWidth:1,borderColor:"#2B5CAD",borderRadius:16,paddingVertical:7,paddingHorizontal:12,alignSelf:"flex-start"}}>Önerilen stil: {(boot?.styles||[]).find(st=>st.id===recommendation.style_id)?.name||recommendation.style_id} — {recommendation.reason}</Text>
   </Pressable>}
   <Pressable accessibilityRole="checkbox" accessibilityState={{checked:includeName}} onPress={()=>setIncludeName(v=>!v)} style={s.row}>
    <Text style={[s.meta,{fontWeight:"800",color:includeName?C.navy:C.muted}]}>Görselin sağ alt köşesine adım yazılsın</Text>
   </Pressable>
   <Btn title={genBusy?"Görseller üretiliyor…":"Görselleri üret"} disabled={genBusy||!styleId} primary onPress={()=>void generate()}/>
   {!!genNote&&<Text style={{color:C.green,fontSize:13,fontWeight:"700",marginTop:8}}>{genNote}</Text>}
   {!!(audit||genTips.length)&&<View style={{borderWidth:1,borderColor:C.line,borderRadius:13,backgroundColor:C.soft,padding:12,marginTop:10}}>
    {!!audit&&typeof audit.score==="number"&&<Text style={{fontSize:14,fontWeight:"900",color:C.navy}}>Yapı Puanı: {audit.score}/100{audit.level?" — "+audit.level:""}</Text>}
    {!!genTips.length&&<View style={{marginTop:6}}>
     <Text style={{fontSize:13,fontWeight:"800",color:C.text}}>Geliştirme önerileri</Text>
     {genTips.map((tip,index)=><Text key={index} style={s.meta}>{"· "+tip}</Text>)}
    </View>}
   </View>}
   {!!gallery.length&&<View style={{marginTop:12}}>
    <Text style={s.title}>Üretilen görseller</Text>
    <View style={{flexDirection:"row",flexWrap:"wrap",gap:8,marginTop:8}}>{gallery.map((item,index)=><Pressable key={index} accessibilityRole="button" accessibilityLabel={"Görseli aç"} onPress={()=>setPreview(item.path)} style={{width:"47%",flexGrow:1,borderRadius:12,overflow:"hidden",borderWidth:1,borderColor:C.line,marginBottom:8,backgroundColor:C.soft}}>
     <Image source={ffImageSource(token,item.path)} style={{width:"100%",height:150}} accessibilityIgnoresInvertColors/>
     <Text style={{fontSize:11,color:C.muted,padding:8}} numberOfLines={1}>{item.caption}</Text>
    </Pressable>)}</View>
   </View>}
   <Btn title="Metin adımına dön" onPress={()=>setStep(2)}/>
  </View>}
  {!!flowErr&&<Text style={{color:C.red,marginBottom:10}}>{flowErr}</Text>}
  <Section title="Marka Kiti" open={brandOpen} onToggle={()=>setBrandOpen(v=>!v)}>
   {!!boot?.brand_kit?.exists&&<View style={{flexDirection:"row",flexWrap:"wrap",gap:8}}>{(boot.brand_kit.photos||[]).map((path,index)=><Image key={index} source={ffImageSource(token,path)} style={{width:64,height:64,borderRadius:8,borderWidth:1,borderColor:C.line}} accessibilityIgnoresInvertColors/>)}</View>}
   <Btn title={brandBusy?"Fotoğraflar yükleniyor…":"Fotoğraf seç ve yükle"} disabled={brandBusy} onPress={()=>void pickBrand()}/>
   {!!brandErr&&<Text style={{color:C.red,marginTop:6}}>{brandErr}</Text>}
   <View style={{flexDirection:"row",flexWrap:"wrap",marginTop:10}}>{FF_SCENES.map(scene=><Chip key={scene} label={scene} active={brandScene===scene} onPress={()=>setBrandScene(scene)}/>)}</View>
   <Btn title={brandSceneBusy?"Sahne görseli üretiliyor…":"Sahne görseli üret"} disabled={brandSceneBusy||!brandScene} primary onPress={()=>void makeScene()}/>
   {!!brandSceneErr&&<Text style={{color:C.red,marginTop:6}}>{brandSceneErr}</Text>}
  </Section>
  <Section title="Instagram Profili" open={igOpen} onToggle={()=>setIgOpen(v=>{if(!v&&!ig)void loadIg();return !v})}>
   {igBusy&&<ActivityIndicator color={C.navy}/>}
   {ig&&<View>
    <Text style={s.meta}>Bio</Text><Text style={s.body}>{ig.bio}</Text>
    <Text style={[s.meta,{marginTop:8}]}>Öne çıkanlar</Text>
    <View style={{flexDirection:"row",flexWrap:"wrap",marginTop:4}}>{(ig.highlights||[]).map((item,index)=><Chip key={index} label={item} active={false} onPress={()=>{}}/>)}</View>
    <Text style={[s.meta,{marginTop:8}]}>Izgara planı</Text>
    {(ig.grid_plan||[]).map((row,index)=><Text key={index} style={s.body}>{(index+1)+". "+row.idea+" · "+row.format}</Text>)}
   </View>}
   {!!igErr&&<Text style={{color:C.red,marginTop:6}}>{igErr}</Text>}
  </Section>
  <Section title="Reels Çekim Planı" open={reelsOpen} onToggle={()=>setReelsOpen(v=>!v)}>
   <TextInput accessibilityLabel="Reels konusu" style={s.input} value={reelsTopic} onChangeText={setReelsTopic} placeholder="Reels konusu yazın" placeholderTextColor={C.muted} maxLength={200}/>
   <Btn title={reelsBusy?"Plan hazırlanıyor…":"Çekim planı hazırla"} disabled={reelsBusy||!reelsTopic.trim()} primary onPress={()=>void loadReels()}/>
   {reels&&<View style={{marginTop:10}}>
    <Text style={s.meta}>Kancalar</Text>
    <View style={{flexDirection:"row",flexWrap:"wrap",marginTop:4}}>{(reels.hooks||[]).map((hook,index)=><Chip key={index} label={hook} active={false} onPress={()=>{}}/>)}</View>
    <Text style={[s.meta,{marginTop:8}]}>Senaryo</Text>
    {senaryoRows.map((row,index)=><View key={index} style={{marginTop:6}}>
     <Text style={s.body}>{row.aralik} — {row.metin}</Text>
     {!!row.shot&&<Text style={s.meta}>Yönetmenlik: {row.shot}</Text>}
    </View>)}
    <Text style={[s.meta,{marginTop:8}]}>Kurgu adımları (CapCut)</Text>
    {(reels.capcut_adimlari||[]).map((item,index)=><Text key={index} style={s.body}>{(index+1)+". "+item}</Text>)}
    {!!(reels.tips||[]).length&&<Text style={s.meta}>{(reels.tips||[]).join(" · ")}</Text>}
   </View>}
   {!!reelsErr&&<Text style={{color:C.red,marginTop:6}}>{reelsErr}</Text>}
  </Section>
  <Section title="Son İşlemler" open={histOpen} onToggle={()=>setHistOpen(v=>{if(!v)void refreshHistory();return !v})}>
   {histBusy&&<ActivityIndicator color={C.navy}/>}
   {!!histErr&&<Text style={{color:C.red}}>{histErr}</Text>}
   {jobs.map(job=><View key={job.id} style={{borderTopWidth:1,borderTopColor:C.line,paddingTop:8,marginTop:8}}>
    <Text style={s.title}>{job.label} · {job.topic||"Konu yok"}</Text>
    <Text style={s.meta}>{job.created_at}</Text>
    {!!job.image_url&&<Pressable accessibilityRole="button" onPress={()=>setPreview(job.image_url as string)} style={{marginTop:6}}><Text style={{color:C.navy,fontWeight:"800"}}>Görseli aç</Text></Pressable>}
   </View>)}
   {!histBusy&&!jobs.length&&!histErr&&<Text style={s.muted}>Henüz kayıtlı işlem yok.</Text>}
  </Section>
  <Modal visible={preview!==null} transparent animationType="fade" onRequestClose={()=>setPreview(null)}>
   <View style={{flex:1,backgroundColor:"rgba(7,27,53,.85)",justifyContent:"center",alignItems:"center",padding:16}}>
    {preview&&<Image source={ffImageSource(token,preview)} style={{width:"100%",height:"72%",borderRadius:12}} resizeMode="contain" accessibilityIgnoresInvertColors/>}
    <Btn title="Kapat" onPress={()=>setPreview(null)}/>
   </View>
  </Modal>
 </ScrollView>;
}
const s=({page:{flex:1,backgroundColor:C.bg},pad:{padding:16,paddingBottom:110},
 big:{fontSize:27,fontWeight:"900",color:C.navy,marginBottom:5},
 title:{fontSize:16,fontWeight:"900",color:C.text},body:{fontSize:14,color:C.text,lineHeight:20,marginTop:5},
 muted:{fontSize:13,color:C.muted,lineHeight:19},meta:{fontSize:11,color:C.muted,marginTop:7},
 row:{flexDirection:"row",alignItems:"center",gap:10},
 btn:{height:46,borderRadius:13,backgroundColor:C.white,borderWidth:1,borderColor:C.navy,alignItems:"center",justifyContent:"center",marginTop:12},btnT:{color:C.navy,fontWeight:"800"},
 input:{height:50,borderWidth:1,borderColor:C.line,borderRadius:14,backgroundColor:C.white,paddingHorizontal:14,color:C.text,marginTop:10}}) as const;
