import React,{useCallback,useEffect,useState} from 'react';
import {ActivityIndicator,FlatList,Modal,Pressable,Text,TextInput,View} from 'react-native';
import {getPatients,Patient} from './api';
import {usePagedRecords} from './usePagedRecords';
import {
 normalizePatientSelectQuery,
 PATIENT_SELECT_QUERY_MAX_LENGTH,
 patientSelectEmptyState,
 patientSelectRowDetails,
} from './patientSelectPresentation';

function Search({token,onSelect,onClose,searchTitle,searchHint,searchPlaceholder}:{token:string;onSelect:(patient:Patient)=>void;onClose:()=>void;searchTitle:string;searchHint:string;searchPlaceholder:string}){
 const [text,setText]=useState(''),[query,setQuery]=useState(''),[queryError,setQueryError]=useState('');
 const applySearch=useCallback(()=>{
  try{
   setQuery(normalizePatientSelectQuery(text));
   setQueryError('');
  }catch(error){
   setQuery('');
   setQueryError(error instanceof Error?error.message:'Arama metnini kontrol edin.');
  }
 },[text]);
 useEffect(()=>{const timer=setTimeout(applySearch,300);return()=>clearTimeout(timer)},[applySearch]);
 const pages=usePagedRecords<Patient>(token+':appointment-patient:'+query,async offset=>{
  const page=await getPatients(token,query,offset||0);
  const next=(offset||0)+page.items.length;
  return {items:page.items,next_before:next<page.total?next:null};
 },false,true,'offset');
 const emptyMessage=patientSelectEmptyState(query,pages.busy,pages.error||queryError);
 return <View style={{flex:1,paddingTop:40,backgroundColor:'#F7F9FC'}}>
  <View style={{paddingHorizontal:18,paddingBottom:12,flexDirection:'row',alignItems:'center',justifyContent:'space-between'}}>
   <View><Text style={{fontSize:22,fontWeight:'800',color:'#102033'}}>{searchTitle}</Text><Text style={{fontSize:12,color:'#64748B',marginTop:3}}>{searchHint}</Text></View>
   <Pressable accessibilityRole="button" accessibilityLabel="Hasta seçimini kapat" onPress={onClose} style={{padding:10}}><Text style={{color:'#1769AA',fontWeight:'800'}}>Kapat ✕</Text></Pressable>
  </View>
  <View style={{marginHorizontal:16,marginBottom:12,paddingHorizontal:13,flexDirection:'row',alignItems:'center',borderWidth:1,borderColor:'#DCE3EB',borderRadius:12,backgroundColor:'#FFFFFF'}}>
   <Text style={{fontSize:17,color:'#64748B'}}>⌕</Text>
   <TextInput
    accessibilityLabel="Hasta ara: ad, soyad, hasta numarası, telefon veya TC"
    value={text}
    onChangeText={setText}
    onSubmitEditing={applySearch}
    placeholder={searchPlaceholder}
    autoCorrect={false}
    autoCapitalize="none"
    returnKeyType="search"
    maxLength={PATIENT_SELECT_QUERY_MAX_LENGTH}
    style={{flex:1,marginLeft:9,paddingVertical:13,color:'#102033'}}
   />
   {!!text&&<Pressable accessibilityRole="button" accessibilityLabel="Hasta aramasını temizle" onPress={()=>{setText('');setQuery('');setQueryError('')}} style={{padding:8}}><Text style={{color:'#1769AA',fontWeight:'800'}}>Temizle</Text></Pressable>}
  </View>
  {!!queryError&&<Text accessibilityRole="alert" style={{color:'#B42318',marginHorizontal:18,marginBottom:8}}>{queryError}</Text>}
  <FlatList
   data={pages.items}
   keyExtractor={item=>String(item.id)}
   contentContainerStyle={{paddingHorizontal:16,paddingBottom:28,flexGrow:1}}
   keyboardShouldPersistTaps="handled"
   refreshing={pages.busy}
   onRefresh={pages.refresh}
   onEndReached={()=>{if(pages.hasMore&&!pages.busy)void pages.loadMore()}}
   onEndReachedThreshold={0.4}
   renderItem={({item})=>{
    const details=patientSelectRowDetails(item);
    const name=`${item.first_name||'İsimsiz'} ${item.last_name||'Hasta'}`.trim();
    return <Pressable
     accessibilityRole="button"
     accessibilityLabel={`${name}, ${details.join(', ')}`}
     onPress={()=>onSelect(item)}
     style={{padding:15,marginBottom:8,borderWidth:1,borderColor:'#E5EAF0',borderRadius:13,backgroundColor:'#FFFFFF',flexDirection:'row',alignItems:'center'}}
    >
     <View style={{width:42,height:42,borderRadius:13,backgroundColor:'#EAF2FC',alignItems:'center',justifyContent:'center',marginRight:12}}>
      <Text style={{fontWeight:'900',fontSize:15,color:'#173B61'}}>{((item.first_name?.[0]||'')+(item.last_name?.[0]||'')).toLocaleUpperCase('tr-TR')||'H'}</Text>
     </View>
     <View style={{flex:1,minWidth:0}}>
      <Text numberOfLines={1} style={{fontWeight:'800',color:'#102033'}}>{name}</Text>
      {details.map((value,index)=><Text key={index} numberOfLines={1} style={{fontSize:12,color:'#64748B',marginTop:3}}>{value}</Text>)}
     </View>
     <Text style={{fontSize:20,color:'#1769AA',marginLeft:8}}>›</Text>
    </Pressable>;
   }}
   ListEmptyComponent={<View style={{alignItems:'center',padding:24,flexGrow:1,justifyContent:'center'}}>
    {pages.busy&&<ActivityIndicator color="#1769AA" style={{marginBottom:10}}/>}
    <Text style={{color:'#64748B',textAlign:'center'}}>{emptyMessage}</Text>
    {!!query&&!pages.busy&&!pages.error&&!queryError&&<Pressable accessibilityRole="button" onPress={()=>{setText('');setQuery('')}} style={{padding:12}}><Text style={{color:'#1769AA',fontWeight:'800'}}>Aramayı temizle</Text></Pressable>}
    {!!(pages.error||queryError)&&<Pressable accessibilityRole="button" onPress={()=>{if(queryError)applySearch();else void pages.refresh()}} style={{padding:12}}><Text style={{color:'#B42318',fontWeight:'800'}}>Yeniden dene</Text></Pressable>}
   </View>}
   ListFooterComponent={<View style={{paddingVertical:12,alignItems:'center'}}>
    {pages.busy&&pages.items.length>0&&<ActivityIndicator color="#1769AA"/>}
    {!!pages.error&&<Pressable accessibilityRole="button" onPress={()=>void pages.loadMore()} style={{padding:12}}><Text style={{color:'#B42318'}}>Sonraki sayfa alınamadı · Yeniden dene</Text></Pressable>}
    {pages.hasMore&&!pages.busy&&!pages.error&&<Pressable accessibilityRole="button" onPress={()=>void pages.loadMore()} style={{padding:12}}><Text style={{color:'#1769AA',fontWeight:'800'}}>Daha fazla hasta</Text></Pressable>}
   </View>}
  />
 </View>;
}

export default function NativePatientSelect({token,value,onChange,disabled=false,searchTitle='Hasta Seç',searchHint='Randevuya bağlanacak hastayı bulun',emptyLabel='Hasta seç (isteğe bağlı)　⌕',searchPlaceholder='Ad, soyad, hasta no, telefon veya TC ile ara'}:{token:string;value:Patient|null;onChange:(patient:Patient|null)=>void;disabled?:boolean;searchTitle?:string;searchHint?:string;emptyLabel?:string;searchPlaceholder?:string}){
 const [open,setOpen]=useState(false);
 return <View>
  <Pressable accessibilityRole="button" accessibilityState={{disabled}} disabled={disabled} onPress={()=>setOpen(true)} style={{padding:13,borderWidth:1,borderColor:'#DCE3EB',borderRadius:10,backgroundColor:'#FFFFFF'}}>
   <Text style={{color:'#102033'}}>{value?`${value.first_name||''} ${value.last_name||''} · ${value.anonymous_id||'Hasta'}`:emptyLabel}</Text>
  </Pressable>
  {value&&<Pressable accessibilityRole="button" disabled={disabled} onPress={()=>onChange(null)} style={{padding:10}}><Text style={{color:'#1769AA'}}>Hasta bağlantısını kaldır</Text></Pressable>}
  <Modal visible={open} animationType="slide" presentationStyle="fullScreen" onRequestClose={()=>setOpen(false)}>
   {open&&<Search token={token} onClose={()=>setOpen(false)} onSelect={patient=>{onChange(patient);setOpen(false)}} searchTitle={searchTitle} searchHint={searchHint} searchPlaceholder={searchPlaceholder}/>}
  </Modal>
 </View>;
}
