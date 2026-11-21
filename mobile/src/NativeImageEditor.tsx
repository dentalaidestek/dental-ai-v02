import React,{useEffect,useMemo,useRef,useState} from "react";
import {ActivityIndicator,Image,ImageSourcePropType,Modal,PanResponder,Pressable,Text,View} from "react-native";
import {captureRef,releaseCapture} from "react-native-view-shot";
import {ChatFile,clampChatPoint,fitChatImage} from "./chatFiles";

type Stroke={color:string;width:number;points:Array<[number,number]>};
export default function NativeImageEditor({source,visible,onClose,onPrepared,embedded=false}:{source:ImageSourcePropType;visible:boolean;onClose:()=>void;onPrepared:(file:ChatFile)=>void;embedded?:boolean}){
 const [natural,setNatural]=useState({width:1,height:1}),[available,setAvailable]=useState(300),[loaded,setLoaded]=useState(false),[strokes,setStrokes]=useState<Stroke[]>([]),[color,setColor]=useState("#FF3030"),[pen,setPen]=useState(4),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const surface=useRef<View>(null),active=useRef(true),drawing=useRef(false),pointCount=useRef(0);
 useEffect(()=>{active.current=true;return()=>{active.current=false}},[]);
 useEffect(()=>{if(visible){setLoaded(false);setStrokes([]);pointCount.current=0;drawing.current=false;setError("");setBusy(false)}},[visible]);
 const box=fitChatImage(natural.width,natural.height,available,380);
 const responder=useMemo(()=>PanResponder.create({
  onStartShouldSetPanResponder:()=>loaded&&!busy,onMoveShouldSetPanResponder:()=>loaded&&!busy,
  onPanResponderGrant:event=>{if(pointCount.current>=2000){setError("Çizim sınırına ulaşıldı. Geri al veya temizle ile devam edebilirsiniz.");return}drawing.current=true;pointCount.current++;const point=clampChatPoint(event.nativeEvent.locationX,event.nativeEvent.locationY,box.width,box.height);setStrokes(previous=>[...previous,{color,width:pen,points:[point]}])},
  onPanResponderMove:event=>{if(!drawing.current||pointCount.current>=2000)return;pointCount.current++;const point=clampChatPoint(event.nativeEvent.locationX,event.nativeEvent.locationY,box.width,box.height);setStrokes(previous=>previous.map((stroke,index)=>index===previous.length-1?{...stroke,points:[...stroke.points,point]}:stroke))},
  onPanResponderRelease:()=>{drawing.current=false},onPanResponderTerminate:()=>{drawing.current=false},
 }),[loaded,busy,color,pen,box.width,box.height]);
 async function prepare(){
  if(!surface.current||!loaded||busy||drawing.current)return;setBusy(true);setError("");
  try{
   const uri=await captureRef(surface.current,{format:"jpg",quality:.9,result:"tmpfile",width:box.exportWidth,height:box.exportHeight});
   if(!active.current){releaseCapture(uri);return}
   onPrepared({uri,name:"isaretlenmis-gorsel.jpg",type:"image/jpeg",owned:true});
  }catch{if(active.current)setError("Düzenlenen görsel hazırlanamadı. Çizimleriniz bu ekranda korunuyor.")}
  finally{if(active.current)setBusy(false)}
 }
 const content=<View style={{flex:1,backgroundColor:"#F5F7FA",paddingTop:42,paddingHorizontal:16,paddingBottom:24}} onLayout={event=>setAvailable(Math.max(1,event.nativeEvent.layout.width-32))}>
 <Text style={{fontSize:22,fontWeight:"800",color:"#071B35"}}>Görseli düzenle</Text><Text style={{color:"#63748A",marginVertical:8}}>İşaretlenmiş kopya yeni bir görsel olarak hazırlanır. Asıl görüntü korunur.</Text>
 <View style={{alignItems:"center",marginVertical:12}}><View ref={surface} collapsable={false} style={{width:box.width,height:box.height,backgroundColor:"white",overflow:"hidden"}} {...responder.panHandlers}>
 <View pointerEvents="none" style={{position:"absolute",width:"100%",height:"100%"}}><Image source={source} resizeMode="stretch" style={{position:"absolute",width:"100%",height:"100%"}} onLoad={event=>{const size=event.nativeEvent.source;if(size.width>0&&size.height>0)setNatural(previous=>previous.width===size.width&&previous.height===size.height?previous:{width:size.width,height:size.height});setLoaded(true)}} onError={()=>{setLoaded(false);setError("Görsel yüklenemedi.")}}/></View>
 {strokes.flatMap((stroke,strokeIndex)=>stroke.points.map((point,index)=>{
  const previous=stroke.points[Math.max(0,index-1)],dx=point[0]-previous[0],dy=point[1]-previous[1],length=Math.max(stroke.width,Math.hypot(dx,dy));
  return <View pointerEvents="none" key={strokeIndex+":"+index} style={{position:"absolute",left:(point[0]+previous[0])/2-length/2,top:(point[1]+previous[1])/2-stroke.width/2,width:length,height:stroke.width,backgroundColor:stroke.color,borderRadius:stroke.width/2,transform:[{rotate:Math.atan2(dy,dx)*180/Math.PI+"deg"}]}}/>;
 }))}
 </View></View>
 <View style={{flexDirection:"row",gap:10}}>{["#FF3030","#16803C","#238DE9","#FFD523"].map(value=><Pressable key={value} accessibilityRole="button" accessibilityLabel={"Kalem rengi "+value} accessibilityState={{selected:color===value}} disabled={busy} onPress={()=>setColor(value)} style={{height:40,width:40,borderRadius:20,backgroundColor:value,borderWidth:color===value?3:0,borderColor:"#071B35"}}/>)}</View>
 <View style={{flexDirection:"row",gap:16,marginTop:10}}>{[3,6,10].map(value=><Pressable key={value} disabled={busy} onPress={()=>setPen(value)} style={{padding:12}}><Text style={{fontWeight:pen===value?"900":"400"}}>Kalınlık {value}</Text></Pressable>)}</View>
 <View style={{flexDirection:"row",gap:16}}><Pressable disabled={busy} onPress={()=>setStrokes(previous=>{const next=previous.slice(0,-1);pointCount.current=next.reduce((sum,stroke)=>sum+stroke.points.length,0);return next})} style={{padding:12}}><Text>Geri al</Text></Pressable><Pressable disabled={busy} onPress={()=>{setStrokes([]);pointCount.current=0}} style={{padding:12}}><Text>Temizle</Text></Pressable></View>
 {!!error&&<Text style={{color:"#B42318"}}>{error}</Text>}{busy&&<ActivityIndicator/>}
 <Pressable accessibilityRole="button" disabled={busy||!loaded} onPress={()=>void prepare()} style={{padding:16,backgroundColor:"#071B35",borderRadius:12,marginTop:10}}><Text style={{color:"white",fontWeight:"800",textAlign:"center"}}>Düzenlenen görseli hazırla</Text></Pressable>
 <Pressable accessibilityRole="button" disabled={busy} onPress={onClose} style={{padding:16}}><Text style={{textAlign:"center"}}>Vazgeç</Text></Pressable>
 </View>;
 return embedded?content:<Modal visible={visible} animationType="slide" onRequestClose={()=>{if(!busy)onClose()}}>{content}</Modal>;
}
