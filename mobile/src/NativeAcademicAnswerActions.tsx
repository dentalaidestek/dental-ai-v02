import React,{useEffect,useState} from 'react';
import {Pressable,Share,Text,View} from 'react-native';
import {feedback,type AcademicVote} from './academicApi';
import {normalizeAcademicVote,toggleAcademicVote} from './academicAnswerActions';

type Props={
 token:string;
 course:number;
 messageId:number;
 content:string;
 vote:string|null;
 disabled?:boolean;
 onVote:(vote:AcademicVote)=>void;
};

export default function NativeAcademicAnswerActions({token,course,messageId,content,vote,onVote,disabled=false}:Props){
 const [current,setCurrent]=useState<AcademicVote>(()=>normalizeAcademicVote(vote));
 const [saving,setSaving]=useState(false);
 const [notice,setNotice]=useState('');
 useEffect(()=>{setCurrent(normalizeAcademicVote(vote))},[vote]);

 async function rate(selected:'like'|'dislike'){
  if(disabled||saving)return;
  const previous=current,next=toggleAcademicVote(current,selected);
  setCurrent(next);setSaving(true);setNotice('');
  try{
   const result=await feedback(token,course,messageId,next);
   if(!result||result.ok!==true||result.vote!==next)throw Error('Yanıt değerlendirmesi doğrulanamadı.');
   const confirmed=normalizeAcademicVote(result.vote);
   setCurrent(confirmed);onVote(confirmed);
   setNotice(confirmed==='none'?'Değerlendirme kaldırıldı':'Değerlendirme kaydedildi');
  }catch{
   setCurrent(previous);setNotice('Kaydedilemedi. Tekrar dene.');
  }finally{setSaving(false)}
 }

 async function share(){
  if(disabled||!content.trim())return;
  setNotice('');
  try{
   await Share.share({message:content,title:'Dental AI Akademik'});
   setNotice('Paylaşım menüsü açıldı.');
  }catch{setNotice('Paylaşım açılamadı.')}
 }

 const buttonStyle={minHeight:40,paddingHorizontal:12,paddingVertical:8,borderRadius:9,borderWidth:1,borderColor:'#DCE3EB',backgroundColor:'#FFFFFF',justifyContent:'center' as const};
 const textStyle={fontSize:13,fontWeight:'700' as const,color:'#1769AA'};
 return <View style={{gap:6,marginTop:8}}>
  <View style={{flexDirection:'row',flexWrap:'wrap',alignItems:'center',gap:8}}>
   <Pressable accessibilityRole="button" accessibilityLabel="Yanıtı paylaş" accessibilityState={{disabled:disabled||!content.trim()}} disabled={disabled||!content.trim()} onPress={()=>void share()} style={buttonStyle}>
    <Text style={textStyle}>Paylaş</Text>
   </Pressable>
   <Pressable accessibilityRole="button" accessibilityLabel="Beğen" accessibilityState={{selected:current==='like',disabled:disabled||saving}} disabled={disabled||saving} onPress={()=>void rate('like')} style={[buttonStyle,current==='like'&&{backgroundColor:'#E8F0FF',borderColor:'#8DAFE2'}]}>
    <Text style={textStyle}>{current==='like'?'✓ Beğendin':'Beğen'}</Text>
   </Pressable>
   <Pressable accessibilityRole="button" accessibilityLabel="Beğenme" accessibilityState={{selected:current==='dislike',disabled:disabled||saving}} disabled={disabled||saving} onPress={()=>void rate('dislike')} style={[buttonStyle,current==='dislike'&&{backgroundColor:'#E8F0FF',borderColor:'#8DAFE2'}]}>
    <Text style={textStyle}>{current==='dislike'?'✓ Beğenmedin':'Beğenme'}</Text>
   </Pressable>
  </View>
  {!!notice&&<Text accessibilityRole="text" accessibilityLiveRegion="polite" style={{fontSize:12,color:'#53657B'}}>{notice}</Text>}
 </View>;
}
