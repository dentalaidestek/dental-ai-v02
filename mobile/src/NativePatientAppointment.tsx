import React,{useEffect,useRef,useState} from 'react';
import {ActivityIndicator,Pressable,Text,View} from 'react-native';
import {getProgram,ProgramPage} from './programApi';
import NativeProgramEditor from './NativeProgramEditor';
export default function NativePatientAppointment({token,patientId,onSaved}:{token:string;patientId:number;onSaved:()=>void}){
 const [page,setPage]=useState<ProgramPage|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0),active=useRef(true),generation=useRef(0);
 useEffect(()=>{active.current=true;const seq=++generation.current;setPage(null);setError('');if(!Number.isSafeInteger(patientId)||patientId<=0){setError('Geçersiz hasta kimliği.');return}void getProgram(token,'today').then(result=>{if(active.current&&seq===generation.current)setPage(result)}).catch(e=>{if(active.current&&seq===generation.current)setError(e instanceof Error?e.message:'Randevu formu alınamadı.')});return()=>{active.current=false;generation.current++}},[token,patientId,retry]);
 if(!page)return <View style={{padding:22}}>{error?<><Text style={{color:'#B42318'}}>{error}</Text><Pressable onPress={()=>setRetry(value=>value+1)} style={{padding:15}}><Text>Yeniden dene</Text></Pressable></>:<ActivityIndicator/>}</View>;
 return <NativeProgramEditor key={token+':patient:'+patientId} token={token} page={page} initialPatientId={patientId} onSaved={()=>onSaved()} onClose={onSaved}/>;
}
