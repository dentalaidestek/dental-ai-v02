import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ActivityIndicator,AppState,Image,Modal,Pressable,ScrollView,Text,View} from 'react-native';
import {useIsFocused} from '@react-navigation/native';
import {AnalysisHistory,PatientAnalysisHistoryCursor,getPatientAnalysisHistoryPage} from './modernApi';
import {getAnalysis,MobileAnalysis} from './analysisApi';
import {useRealtime} from './realtime';
import { shouldRefreshOnAppResume } from './appResumeRefresh';
import {groupPatientAnalysisAssets,shouldShowLegacyPatientRadiograph} from './patientAnalysisPresentation';
import {createPatientAnalysisHistoryImageScope,patientAnalysisHistoryImageKey,patientAnalysisHistoryImageSource} from './patientAnalysisHistoryImages';
import {patientAnalysisHistoryDate,patientAnalysisHistoryStatus,patientAnalysisHistoryStatusTone,patientAnalysisHistoryTitle,patientAnalysisHistoryTooth} from './patientHistoryPresentation';

export function analysisStatus(item:{status:string;is_voice_review?:boolean}){
 return patientAnalysisHistoryStatus(item);
}

export default function NativePatientHistory({token,patientId,toothNumber,onOpenAnalysis,onNew}:{token:string;patientId:number;toothNumber?:string;onOpenAnalysis?:(id:number)=>void;onNew?:()=>void}){
 const focused=useIsFocused(),{lastEvent}=useRealtime(),scope=`${token}:${patientId}:${toothNumber||''}`,active=useRef(scope),generation=useRef(0),detailRequest=useRef(0),locked=useRef(false),refreshPending=useRef(false),focusInitialized=useRef(false),lastEventSeen=useRef(lastEvent);
 const imageScope=useRef<{token:string;scope:string}|null>(null);
 if(!imageScope.current||imageScope.current.token!==token)imageScope.current={token,scope:createPatientAnalysisHistoryImageScope()};
 if(active.current!==scope){active.current=scope;generation.current++;detailRequest.current++}
 const [data,setData]=useState<{scope:string;items:AnalysisHistory[];next:PatientAnalysisHistoryCursor|null}|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[errorMore,setErrorMore]=useState(false),[selected,setSelected]=useState<number|null>(null),[detail,setDetail]=useState<MobileAnalysis|null>(null),[detailError,setDetailError]=useState(''),[zoom,setZoom]=useState(1),[legacyRadiographError,setLegacyRadiographError]=useState(false);
 const visible=data?.scope===scope?data:null;
 const assetGroups=groupPatientAnalysisAssets(detail?.assets);
 const showLegacyRadiograph=detail?shouldShowLegacyPatientRadiograph(detail.analysis.legacy_radiograph_available,detail.assets):false;
 const load=useCallback(async(more=false)=>{if(locked.current){if(!more)refreshPending.current=true;return;}locked.current=true;const seq=++generation.current,owner=scope;setBusy(true);setError('');setErrorMore(false);try{const page=await getPatientAnalysisHistoryPage(token,patientId,toothNumber,more?visible?.next??undefined:undefined);if(active.current!==owner||generation.current!==seq)return;setData(previous=>({scope:owner,items:more&&previous?.scope===owner?[...previous.items,...page.items.filter(x=>!previous.items.some(y=>y.id===x.id))]:page.items,next:page.next}));setError('');setErrorMore(false)}catch(e){if(active.current===owner&&generation.current===seq){setError(e instanceof Error?e.message:'Analiz geçmişi alınamadı.');setErrorMore(more)}}finally{if(active.current===owner&&generation.current===seq){locked.current=false;setBusy(false);if(refreshPending.current){refreshPending.current=false;void Promise.resolve().then(()=>{if(active.current===owner)void loader.current()})}}}},[token,patientId,toothNumber,scope,visible?.next]);
 const loader=useRef(load);loader.current=load;
 useEffect(()=>{locked.current=false;refreshPending.current=false;setData(null);setSelected(null);setDetail(null);setError('');setErrorMore(false);void loader.current();return()=>{generation.current++;detailRequest.current++}},[scope]);
 useEffect(()=>{if(!focusInitialized.current){focusInitialized.current=true;return;}if(focused)void loader.current()},[focused]);
 useEffect(()=>{
  let previousState=AppState.currentState;
  const listener=AppState.addEventListener('change',nextState=>{
   const shouldRefresh=shouldRefreshOnAppResume(previousState,nextState,focused);
   previousState=nextState;
   if(shouldRefresh)void loader.current();
  });
  return()=>listener.remove();
 },[focused]);
 useEffect(()=>{
  if(lastEventSeen.current===lastEvent)return;
  lastEventSeen.current=lastEvent;
  if(lastEvent&&['ANALYSIS_CREATED','ANALYSIS_UPDATED','PATIENT_UPDATED'].includes(String(lastEvent.event_type||lastEvent.type))&&Number(lastEvent.payload?.patient_id||lastEvent.entity_id)===patientId)void loader.current();
 },[lastEvent,patientId]);
 async function open(id:number){
  const seq=++detailRequest.current,owner=scope;setSelected(id);setDetail(null);setDetailError('');setZoom(1);setLegacyRadiographError(false);
  try{const result=await getAnalysis(token,id);if(result.analysis.patient_id!==patientId)throw Error('Analiz bu hastaya ait değil.');if(active.current===owner&&detailRequest.current===seq)setDetail(result)}
  catch(e){if(active.current===owner&&detailRequest.current===seq)setDetailError(e instanceof Error?e.message:'Analiz ayrıntısı alınamadı.')}
 }
 function close(){detailRequest.current++;setSelected(null);setDetail(null);setLegacyRadiographError(false)}
 return <View>
  <View style={{flexDirection:'row',justifyContent:'space-between',alignItems:'center'}}>
   <Text style={{fontSize:20,fontWeight:'800',color:'#102033'}}>Analiz Geçmişi</Text>
   {onNew&&<Pressable onPress={onNew} style={{padding:10}}><Text style={{color:'#1769AA',fontWeight:'700'}}>Yeni Analiz</Text></Pressable>}
  </View>
  {visible?.items.map(item=>{
   const tone=patientAnalysisHistoryStatusTone(item);
   const badge=tone==='success'?{backgroundColor:'#ECFDF3',borderColor:'#A6F4C5',color:'#067647'}:tone==='danger'?{backgroundColor:'#FEF3F2',borderColor:'#FECDCA',color:'#B42318'}:{backgroundColor:'#FFFAEB',borderColor:'#FEDF89',color:'#B54708'};
   const tooth=patientAnalysisHistoryTooth(item);
   return <View key={item.id} style={{backgroundColor:'#FFFFFF',borderWidth:1,borderColor:'#E5EAF0',borderRadius:14,padding:14,marginBottom:10}}>
    <View style={{flexDirection:'row',alignItems:'flex-start',justifyContent:'space-between'}}>
     <View style={{flex:1,paddingRight:10}}>
      <Text style={{fontWeight:'800',fontSize:15,color:'#102033'}}>{patientAnalysisHistoryTitle(item)}</Text>
      <View style={{flexDirection:'row',flexWrap:'wrap',alignItems:'center',marginTop:8}}>
       {!!tooth&&<View style={{backgroundColor:'#F1F5F9',borderRadius:7,paddingHorizontal:8,paddingVertical:5,marginRight:6,marginBottom:5}}><Text style={{fontSize:12,color:'#344054'}}>{tooth}</Text></View>}
       <View style={{backgroundColor:'#F8FAFC',borderRadius:7,paddingHorizontal:8,paddingVertical:5,marginBottom:5}}><Text style={{fontSize:12,color:'#53657B'}}>{patientAnalysisHistoryDate(item.created_at)}</Text></View>
      </View>
     </View>
     <View style={{backgroundColor:badge.backgroundColor,borderColor:badge.borderColor,borderWidth:1,borderRadius:999,paddingHorizontal:9,paddingVertical:5}}>
      <Text style={{fontSize:11,fontWeight:'800',color:badge.color}}>{analysisStatus(item)}</Text>
     </View>
    </View>
    <View style={{alignItems:'flex-end',marginTop:8}}>
     <Pressable accessibilityRole="button" accessibilityLabel={`${patientAnalysisHistoryTitle(item)} detaylarını aç`} onPress={()=>void open(item.id)} style={{backgroundColor:'#071B35',borderRadius:9,paddingHorizontal:16,paddingVertical:9,minWidth:86,alignItems:'center'}}>
      <Text style={{color:'#FFFFFF',fontSize:13,fontWeight:'800'}}>Detay</Text>
     </Pressable>
    </View>
   </View>;
  })}
  {busy&&<ActivityIndicator style={{margin:12}}/>}
  {!busy&&!error&&visible?.items.length===0&&<Text style={{color:'#53657B',paddingVertical:14}}>Henüz analiz bulunmuyor.</Text>}
  {!!error&&<><Text accessibilityRole="alert" style={{color:'#B42318'}}>{error}</Text><Pressable accessibilityRole="button" onPress={()=>void load(errorMore)} style={{padding:12}}><Text>Yeniden dene</Text></Pressable></>}
  {visible?.next&&<Pressable disabled={busy} onPress={()=>void load(true)} style={{padding:12}}><Text style={{color:'#1769AA'}}>Diğer analizleri göster</Text></Pressable>}
  <Modal visible={selected!==null&&data?.scope===scope} onRequestClose={close}>
   <View style={{flex:1,paddingTop:40}}>
    <Pressable onPress={close} style={{padding:16,alignSelf:'flex-end'}}><Text style={{color:'#1769AA'}}>Kapat ✕</Text></Pressable>
    <ScrollView contentContainerStyle={{padding:18,paddingBottom:40}}>
     <Text style={{fontSize:22,fontWeight:'800',color:'#102033'}}>{detail?.analysis.is_voice_review?'Sesli muayene':'Analiz'} #{selected}</Text>
     {!detail&&!detailError&&<ActivityIndicator/>}
     {!!detailError&&<><Text style={{color:'#B42318'}}>{detailError}</Text><Pressable onPress={()=>selected&&void open(selected)} style={{padding:12}}><Text>Yeniden dene</Text></Pressable></>}
     {detail&&<>
      <Text style={{color:'#53657B',marginVertical:12}}>{analysisStatus(detail.analysis)} · {detail.analysis.created_at?new Date(detail.analysis.created_at).toLocaleString('tr-TR'):''}</Text>
      {!!detail.analysis.clinical_notes&&<><Text style={{fontWeight:'800',color:'#102033'}}>Klinik notlar</Text><Text selectable style={{color:'#102033',lineHeight:23,marginVertical:10}}>{detail.analysis.clinical_notes}</Text></>}
      <Text style={{fontSize:18,fontWeight:'800',color:'#102033'}}>Yüklenen görüntüler</Text>
      <View style={{flexDirection:'row'}}>
       <Pressable onPress={()=>setZoom(z=>Math.max(1,z-.5))} style={{padding:12}}><Text>Küçült −</Text></Pressable>
       <Pressable onPress={()=>setZoom(z=>Math.min(3,z+.5))} style={{padding:12}}><Text>Büyüt ＋</Text></Pressable>
      </View>
      {assetGroups.clinical.map(asset=><View key={asset.id} style={{marginBottom:16}}>
       <Text style={{color:'#53657B'}}>Klinik görüntü · {asset.original_filename}</Text>
       <ScrollView horizontal><Image key={patientAnalysisHistoryImageKey(imageScope.current!.scope,detail.analysis.id,asset.id)} testID={patientAnalysisHistoryImageKey(imageScope.current!.scope,detail.analysis.id,asset.id)} source={patientAnalysisHistoryImageSource(token,detail.analysis.id,asset.id)} resizeMode="contain" style={{width:300*zoom,height:240*zoom}}/></ScrollView>
      </View>)}
      {!assetGroups.clinical.length&&<Text style={{color:'#53657B'}}>Yüklenmiş görüntü bulunmuyor.</Text>}
      <Text style={{fontSize:18,fontWeight:'800',color:'#102033',marginTop:12}}>Radyografiler</Text>
      {assetGroups.radiographs.map(asset=><View key={asset.id} style={{marginBottom:16}}>
       <Text style={{color:'#53657B'}}>Radyografi · {asset.original_filename}</Text>
       <ScrollView horizontal><Image key={patientAnalysisHistoryImageKey(imageScope.current!.scope,detail.analysis.id,asset.id)} testID={patientAnalysisHistoryImageKey(imageScope.current!.scope,detail.analysis.id,asset.id)} source={patientAnalysisHistoryImageSource(token,detail.analysis.id,asset.id)} resizeMode="contain" style={{width:300*zoom,height:240*zoom}}/></ScrollView>
      </View>)}
      {!assetGroups.radiographs.length&&showLegacyRadiograph&&<View style={{marginBottom:16}}>
       <Text style={{color:'#53657B'}}>Önceki radyografik görüntü</Text>
       {legacyRadiographError?<Text accessibilityRole="alert" style={{color:'#B42318'}}>Radyografik görüntü alınamadı. Analiz ayrıntısını yenileyin.</Text>:
        <ScrollView horizontal><Image key={patientAnalysisHistoryImageKey(imageScope.current!.scope,detail.analysis.id,null)} testID={patientAnalysisHistoryImageKey(imageScope.current!.scope,detail.analysis.id,null)} source={patientAnalysisHistoryImageSource(token,detail.analysis.id,null)} resizeMode="contain" style={{width:300*zoom,height:240*zoom}} onError={()=>setLegacyRadiographError(true)}/></ScrollView>}
      </View>}
      {!assetGroups.radiographs.length&&!showLegacyRadiograph&&<Text style={{color:'#53657B'}}>Radyografik görüntü bulunmuyor.</Text>}
      {onOpenAnalysis&&<><Text style={{fontSize:18,fontWeight:'800',color:'#102033',marginTop:12}}>Tedavi önerisi</Text><Pressable onPress={()=>{const id=detail.analysis.id;close();onOpenAnalysis(id)}} style={{padding:16,backgroundColor:'#071B35',borderRadius:12}}><Text style={{color:'white',fontWeight:'800',textAlign:'center'}}>Analiz sonucunu aç</Text></Pressable></>}
     </>}
    </ScrollView>
   </View>
  </Modal>
 </View>;
}
