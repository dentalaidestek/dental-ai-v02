import React,{useEffect,useState} from "react";
import {Image,Modal,Pressable,ScrollView,Text,View} from "react-native";
import {ChatMessage,chatImageSource} from "./modernApi";
import {ChatFile} from "./chatFiles";
import NativeImageEditor from "./NativeImageEditor";

export default function ChatImageViewer({token,caseId,message,canEdit=false,onEdited,sourceOverride}:{token:string;caseId:number;message:ChatMessage;canEdit?:boolean;onEdited?:(file:ChatFile)=>void;sourceOverride?:{uri:string;headers:{Authorization:string}}}){
 const [open,setOpen]=useState(false),[zoom,setZoom]=useState(1),[failed,setFailed]=useState(false),[editing,setEditing]=useState(false);
 useEffect(()=>{setOpen(false);setZoom(1);setFailed(false);setEditing(false)},[token,caseId,message.id]);
 const source=sourceOverride||chatImageSource(token,caseId,message.id);
 return <View><Pressable accessibilityRole="button" accessibilityLabel="Klinik görüntüyü aç" onPress={()=>{setZoom(1);setOpen(true)}}><Image source={source} resizeMode="contain" onLoad={()=>setFailed(false)} onError={()=>setFailed(true)} style={{width:220,maxWidth:"100%",height:160,borderRadius:10}}/>{failed&&<Text style={{color:"#B42318"}}>Görsel alınamadı. Görüşmeyi yenileyin.</Text>}</Pressable>
 <Modal visible={open} animationType="fade" onRequestClose={()=>{if(editing)setEditing(false);else setOpen(false)}}>
 {editing?<NativeImageEditor embedded source={source} visible={open} onClose={()=>setEditing(false)} onPrepared={file=>{onEdited?.(file);setEditing(false);setOpen(false)}}/>:<View style={{flex:1,backgroundColor:"#071B35",paddingTop:36,paddingBottom:24}}>
 <View style={{flexDirection:"row",justifyContent:"space-around"}}><Pressable onPress={()=>setOpen(false)} style={{padding:16}}><Text style={{color:"white"}}>Kapat</Text></Pressable><Pressable accessibilityLabel="Küçült" onPress={()=>setZoom(value=>Math.max(1,value-.5))} style={{padding:16}}><Text style={{color:"white"}}>−</Text></Pressable><Pressable accessibilityLabel="Büyüt" onPress={()=>setZoom(value=>Math.min(4,value+.5))} style={{padding:16}}><Text style={{color:"white"}}>＋</Text></Pressable>{canEdit&&onEdited&&<Pressable onPress={()=>setEditing(true)} style={{padding:16}}><Text style={{color:"white"}}>Düzenle</Text></Pressable>}</View>
 <ScrollView horizontal contentContainerStyle={{flexGrow:1}}><ScrollView contentContainerStyle={{flexGrow:1,justifyContent:"center",alignItems:"center"}}><Image source={source} resizeMode="contain" style={{width:320*zoom,height:480*zoom}}/></ScrollView></ScrollView>
 </View>}
 </Modal></View>;
}
