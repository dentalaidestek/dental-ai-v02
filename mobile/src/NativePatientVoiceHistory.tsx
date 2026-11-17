import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ActivityIndicator,Pressable,Text,View} from 'react-native';
import {useIsFocused} from '@react-navigation/native';
import {getVoiceHistory} from './voiceApi';
import type {VoiceHistory} from './voiceApi';
import {useRealtime} from './realtime';
import {patientVoiceHistoryRows} from './patientVoiceHistoryPresentation';

export default function NativePatientVoiceHistory({token,patientId}:{token:string;patientId:number}){
 const focused=useIsFocused(),{lastEvent}=useRealtime(),scope=token+':'+patientId;
 const active=useRef(scope),generation=useRef(0);
 if(active.current!==scope){active.current=scope;generation.current++}
 const [data,setData]=useState<{scope:string;history:VoiceHistory}|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const visible=data?.scope===scope?data.history:null;
 const load=useCallback(async()=>{
  const owner=scope,seq=++generation.current;
  setBusy(true);setError('');
  try{
   const history=await getVoiceHistory(token,patientId);
   if(active.current!==owner||generation.current!==seq)return;
   setData({scope:owner,history});
  }catch(e){
   if(active.current===owner&&generation.current===seq)setError(e instanceof Error?e.message:'Hekim onaylı anamnez alınamadı.');
  }finally{
   if(active.current===owner&&generation.current===seq)setBusy(false);
  }
 },[scope,token,patientId]);
 useEffect(()=>{
  if(focused)void load();
  return()=>{generation.current++};
 },[focused,load]);
 useEffect(()=>{
  if(!lastEvent)return;
  const eventPatient=Number(lastEvent.payload?.patient_id||lastEvent.entity_id);
  const type=String(lastEvent.event_type||lastEvent.type);
  if(eventPatient===patientId&&['PATIENT_UPDATED','ANALYSIS_CREATED','ANALYSIS_UPDATED'].includes(type))void load();
 },[lastEvent,patientId,load]);
 const rows=patientVoiceHistoryRows(visible?.fields);
 if(!busy&&!error&&visible&&rows.length===0)return null;
 if(!busy&&!error&&!visible)return null;
 return <View style={{backgroundColor:'white',borderWidth:1,borderColor:'#E5EAF0',borderRadius:16,padding:16,marginBottom:14}}>
  <View style={{flexDirection:'row',justifyContent:'space-between',alignItems:'center',gap:12}}>
   <View style={{flex:1}}>
    <Text style={{fontSize:11,fontWeight:'800',letterSpacing:.7,color:'#718096'}}>SESLİ MUAYENE</Text>
    <Text accessibilityRole="header" style={{fontSize:19,fontWeight:'800',color:'#102033',marginTop:4}}>Hekim Onaylı Anamnez</Text>
   </View>
   {visible&&<Pressable accessibilityRole="button" accessibilityLabel="Anamnezi yenile" disabled={busy} onPress={()=>void load()} style={{padding:10,minHeight:44,justifyContent:'center'}}>
    <Text style={{color:'#1769AA',fontWeight:'700'}}>{busy?'Yükleniyor…':'Yenile'}</Text>
   </Pressable>}
  </View>
  {busy&&!visible&&<ActivityIndicator style={{marginTop:14}} color="#1769AA"/>}
  {!!error&&<Text accessibilityRole="alert" style={{color:'#B42318',lineHeight:20,marginTop:10}}>{error}</Text>}
  {rows.map(row=><View key={row.key} style={{paddingVertical:12,borderBottomWidth:1,borderColor:'#E5EAF0'}}>
   <Text style={{fontSize:13,fontWeight:'800',color:'#53657B'}}>{row.label}</Text>
   <Text selectable style={{fontSize:14,color:'#102033',lineHeight:22,marginTop:5}}>{row.value}</Text>
   <Text style={{fontSize:11,color:'#718096',marginTop:5}}>Kaynak: Sesli muayene #{row.analysisId}</Text>
  </View>)}
  {!!visible&&rows.length>0&&<Text style={{fontSize:12,color:'#8A5A00',lineHeight:19,marginTop:12}}>{visible.notice} Bu beyanları güncel hastalık, ilaç kullanımı veya alerji olarak kabul etmeden yeni işlem öncesi hastayla tekrar doğrulayın.</Text>}
  {!visible&&!!error&&<Pressable accessibilityRole="button" onPress={()=>void load()} disabled={busy} style={{padding:12,marginTop:6,backgroundColor:'#E8F0FF',borderRadius:10}}>
   <Text style={{color:'#1769AA',fontWeight:'800',textAlign:'center'}}>Yeniden dene</Text>
  </Pressable>}
 </View>;
}
