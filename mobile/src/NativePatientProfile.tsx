import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ActivityIndicator,Alert,AppState,KeyboardAvoidingView,Platform,Pressable,RefreshControl,ScrollView,StyleSheet,Text,TextInput,View} from 'react-native';
import {useIsFocused} from '@react-navigation/native';
import {createTreatment,deletePatient,editPatient,getPatient,PatientDetail,updateTreatment} from './api';
import {useRealtime} from './realtime';
import NativeDateField from './NativeDateField';
import NativePatientHistory from './NativePatientHistory';
import NativePatientMedia from './NativePatientMedia';
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import {chunkedDraftStore} from './socialDraft';
import {parseTreatmentMutationIntent,treatmentMutationStorageKey,type TreatmentMutationIntent} from './treatmentMutation';

const blankTreatment={treatment_name:'',tooth_number:'',treatment_date:'',material:'',doctor_note:'',result:''};
const treatmentStore=chunkedDraftStore(SecureStore,Crypto.randomUUID);
const mutationMayHaveReachedServer=(error:unknown)=>{const status=(error as {status?:number})?.status;return typeof status!=='number'||!Number.isInteger(status)||status===408||status===429||status>=500};
const blankPatient={first_name:'',last_name:'',phone:'',birth_date:'',tc_kimlik_no:'',address:'',chief_complaint:''};
type Actions={chart:()=>void;analysis:()=>void;appointment:()=>void;expert:()=>void;voice:()=>void;analysisResult:(id:number)=>void;deleted:()=>void};
export default function NativePatientProfile({token,userId,patientId,actions}:{token:string;userId:number;patientId:number;actions:Actions}){
 const focused=useIsFocused(),{lastEvent}=useRealtime(),[detail,setDetail]=useState<PatientDetail|null>(null),[loadedScope,setLoadedScope]=useState(''),[error,setError]=useState(''),[refreshing,setRefreshing]=useState(false),[infoOpen,setInfoOpen]=useState(false),[treatmentOpen,setTreatmentOpen]=useState(false),[allTreatments,setAllTreatments]=useState(false),[patientForm,setPatientForm]=useState(blankPatient),[treatment,setTreatment]=useState(blankTreatment),[editingTreatment,setEditingTreatment]=useState<number|null>(null),[editingTreatmentRevision,setEditingTreatmentRevision]=useState<string|null>(null),[pendingTreatment,setPendingTreatment]=useState<TreatmentMutationIntent|null>(null),[busy,setBusy]=useState(false),[mutationError,setMutationError]=useState(''),[uncertain,setUncertain]=useState(false),[revisionConflict,setRevisionConflict]=useState(false);
 const mounted=useRef(true),request=useRef(0),lock=useRef(false),owner=useRef(`${token}:${patientId}`),scope=`${token}:${patientId}`;if(owner.current!==scope){owner.current=scope;request.current++;}
 const current=()=>mounted.current&&owner.current===scope;
 const treatmentKey=treatmentMutationStorageKey(userId,patientId);
 const load=useCallback(async()=>{const seq=++request.current;setRefreshing(true);try{const result=await getPatient(token,patientId);if(!current()||seq!==request.current)return false;setDetail(result);setLoadedScope(scope);setError('');return true}catch(e){if(current()&&seq===request.current)setError(e instanceof Error?e.message:'Hasta alınamadı.');return false}finally{if(current()&&seq===request.current)setRefreshing(false)}},[token,patientId]);
 useEffect(()=>{mounted.current=true;lock.current=false;setBusy(false);setDetail(null);setLoadedScope('');setInfoOpen(false);setTreatmentOpen(false);setEditingTreatment(null);setEditingTreatmentRevision(null);setPendingTreatment(null);setAllTreatments(false);setPatientForm(blankPatient);setTreatment(blankTreatment);setUncertain(false);setRevisionConflict(false);setMutationError('');return()=>{mounted.current=false;request.current++}},[load]);
 useEffect(()=>{let active=true;void(async()=>{try{const raw=await treatmentStore.getItemAsync(treatmentKey);if(!raw||!active||!current())return;const saved=parseTreatmentMutationIntent(raw,userId,patientId);setPendingTreatment(saved);setTreatment(saved.payload);setEditingTreatment(saved.treatmentId);setEditingTreatmentRevision(saved.expectedRevision);setTreatmentOpen(true);setMutationError('Bekleyen tedavi işlemi bulundu. Aynı işlem anahtarıyla sunucuya doğrulatın.')}catch(e){if(active&&current())setMutationError(e instanceof Error?e.message:'Bekleyen tedavi kaydı okunamadı.')}})();return()=>{active=false}},[treatmentKey,token,userId,patientId]);
 useEffect(()=>{if(focused)void load();const listener=AppState.addEventListener('change',state=>{if(state==='active'&&focused)void load()});return()=>listener.remove()},[focused,load]);
 useEffect(()=>{if(!lastEvent||Number(lastEvent.payload?.patient_id||lastEvent.entity_id)!==patientId)return;const type=String(lastEvent.event_type||lastEvent.type);if(type==='PATIENT_DELETED')actions.deleted();else if(['PATIENT_UPDATED','TOOTH_UPDATED','PATIENT_MEDIA_CREATED','PATIENT_MEDIA_DELETED','TREATMENT_CREATED','TREATMENT_UPDATED'].includes(type))void load()},[lastEvent,patientId,load]);
 function toggleInfo(){if(!detail||busy)return;if(!infoOpen){const p=detail.patient;setPatientForm({first_name:p.first_name||'',last_name:p.last_name||'',phone:p.phone||'',birth_date:p.birth_date||'',tc_kimlik_no:p.tc_kimlik_no||'',address:p.address||'',chief_complaint:p.chief_complaint||''})}setInfoOpen(v=>!v)}
 async function savePatient(){
  if(lock.current||uncertain)return;
  if(!patientForm.first_name.trim()||!patientForm.last_name.trim()){setMutationError('Ad ve soyad zorunludur.');return}
  lock.current=true;setBusy(true);setMutationError('');
  try{
   await editPatient(token,patientId,{...patientForm,expected_revision:detail?.edit_revision});
   if(!current())return;
   setInfoOpen(false);setRevisionConflict(false);
   if(!await load())setMutationError('Bilgiler kaydedildi; güncel profil alınamadı. Yenileyin.');
  }catch(e){
   if(current()){
    const status=(e as {status?:number})?.status;
    if(status===409){
     setRevisionConflict(true);
     setMutationError(e instanceof Error?e.message:'Hasta bilgileri başka bir oturumda güncellendi. Güncel kaydı yükleyip değişikliklerinizi yeniden uygulayın.');
    }else{
     setUncertain(mutationMayHaveReachedServer(e));
     setMutationError((e instanceof Error?e.message:'Kaydetme doğrulanamadı.')+(mutationMayHaveReachedServer(e)?' Tekrar göndermeden önce profili yenileyip kaydı kontrol edin.':' Bilgileri düzeltip yeniden deneyin.'));
    }
   }
  }finally{if(current()){lock.current=false;setBusy(false)}}
 }
 async function reloadPatientForConflict(){
  if(lock.current||!current())return;
  lock.current=true;setBusy(true);
  try{
   const latest=await getPatient(token,patientId);
   if(!current())return;
   setDetail(latest);setLoadedScope(scope);
   const p=latest.patient;
   setPatientForm({first_name:p.first_name||'',last_name:p.last_name||'',phone:p.phone||'',birth_date:p.birth_date||'',tc_kimlik_no:p.tc_kimlik_no||'',address:p.address||'',chief_complaint:p.chief_complaint||''});
   setRevisionConflict(false);
   setMutationError('Güncel hasta bilgileri yüklendi. Değişikliklerinizi yeniden uygulayın.');
  }catch(e){if(current())setMutationError(e instanceof Error?e.message:'Güncel hasta bilgileri alınamadı.')}
  finally{if(current()){lock.current=false;setBusy(false)}}
 }
 async function saveTreatment(){
  if(lock.current||uncertain)return;
  if(!pendingTreatment&&!treatment.treatment_name.trim()){setMutationError('Tedavi adı zorunludur.');return}
  lock.current=true;setBusy(true);setMutationError('');let sent=false;
  try{
   let intent=pendingTreatment;
   if(!intent){
    const operation=editingTreatment===null?'CREATE':'UPDATE';
    const candidate={userId,patientId,operation,treatmentId:editingTreatment,requestKey:Crypto.randomUUID(),expectedRevision:editingTreatmentRevision,payload:{...treatment,treatment_name:treatment.treatment_name.trim(),tooth_number:treatment.tooth_number.trim()}};
    intent=parseTreatmentMutationIntent(JSON.stringify(candidate),userId,patientId);
    await treatmentStore.setItemAsync(treatmentKey,JSON.stringify(intent));
    if(!current())return;
    setPendingTreatment(intent);
   }
   sent=true;
   if(intent.operation==='CREATE')await createTreatment(token,patientId,intent.payload,intent.requestKey);
   else await updateTreatment(token,patientId,intent.treatmentId!,intent.payload,intent.requestKey,intent.expectedRevision!);
   await treatmentStore.deleteItemAsync(treatmentKey);
   if(!current())return;
   setPendingTreatment(null);setUncertain(false);setTreatmentOpen(false);setEditingTreatment(null);setEditingTreatmentRevision(null);setTreatment(blankTreatment);
   if(!await load())setMutationError('Tedavi kaydedildi; geçmiş alınamadı. Yenileyin.');
  }catch(e){
   if(!current())return;
   const status=(e as {status?:number})?.status,message=e instanceof Error?e.message:'Tedavi kaydı doğrulanamadı.';
   if(status===409&&message.includes('Tedavi başka bir oturumda güncellendi')){
    await treatmentStore.deleteItemAsync(treatmentKey);setPendingTreatment(null);setTreatmentOpen(false);setEditingTreatment(null);setEditingTreatmentRevision(null);setTreatment(blankTreatment);setUncertain(false);await load();setMutationError('Tedavi başka bir oturumda güncellendi. Güncel geçmiş yüklendi; yeniden düzenleyin.');
   }else if([400,403,404,422].includes(Number(status))){
    await treatmentStore.deleteItemAsync(treatmentKey);setPendingTreatment(null);setUncertain(false);setMutationError(message+' Bilgileri düzeltip yeniden deneyin.');
   }else{
    setUncertain(sent&&mutationMayHaveReachedServer(e));
    setMutationError(message+(sent?' Aynı işlem anahtarı güvenli taslakta korundu; tekrar göndermek yerine aynı kaydı doğrulayın.':' Güvenli taslak kaydedilemedi; sunucuya istek gönderilmedi.'));
   }
  }finally{if(current()){lock.current=false;setBusy(false)}}
 }
 function confirmDelete(){Alert.alert('Hasta kaydı silinsin mi?','Bu işlem geri alınamaz.',[{text:'Vazgeç',style:'cancel'},{text:'Devam',style:'destructive',onPress:()=>Alert.alert('Son onay','Hasta kaydını kalıcı olarak silmek üzeresiniz.',[{text:'Vazgeç',style:'cancel'},{text:'Hasta Kaydını Sil',style:'destructive',onPress:async()=>{if(lock.current)return;lock.current=true;setBusy(true);try{await deletePatient(token,patientId);if(current())actions.deleted()}catch(e){if(current())setMutationError(e instanceof Error?e.message:'Silinemedi.')}finally{if(current()){lock.current=false;setBusy(false)}}}}])}])}
 const button=(label:string,action:()=>void,primary=false,disabled=false)=><Pressable accessibilityRole="button" disabled={disabled||busy} onPress={action} style={[styles.button,primary&&styles.primary,(disabled||busy)&&{opacity:.5}]}><Text style={[styles.buttonText,primary&&{color:'white'}]}>{label}</Text></Pressable>;
 function newTreatment(){if(pendingTreatment){setMutationError('Önce bekleyen tedavi işlemini aynı anahtarla doğrulayın.');return}setEditingTreatment(null);setEditingTreatmentRevision(null);setTreatment(blankTreatment);setTreatmentOpen(true)}
 if(!detail||loadedScope!==scope)return <View style={{padding:24}}>{error?<><Text accessibilityRole="alert" style={styles.error}>{error}</Text>{button('Yeniden dene',()=>void load())}</>:<ActivityIndicator color="#071B35"/>}</View>;
 const p=detail.patient;
 return <KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==='ios'?'padding':undefined}><ScrollView style={styles.page} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" refreshControl={<RefreshControl refreshing={refreshing} onRefresh={()=>void load()}/>}><View style={styles.card}><View style={{alignSelf:'flex-end'}}>{button('Uzmana Danış',actions.expert)}</View><View style={styles.hero}><View style={styles.avatar}><Text style={{fontSize:27,fontWeight:'800',color:'#1769AA'}}>{(p.first_name||'H').slice(0,1)}{(p.last_name||'').slice(0,1)}</Text></View><View style={{flex:1}}><Text style={styles.kicker}>HASTA PROFİLİ</Text><Text style={styles.name}>{p.first_name} {p.last_name}</Text><Text style={styles.meta}>{p.age!==null&&p.age!==undefined?`${p.age} yaş`:'Hasta kaydı'} · {p.phone||'—'}</Text><Text style={styles.meta}>{p.anonymous_id}</Text></View></View><View style={{marginTop:14}}><Text style={styles.meta}>Başvuru şikâyeti</Text><Text style={styles.body}>{p.chief_complaint||'Belirtilmemiş'}</Text></View><View style={styles.actions}>{[['Diş Şeması',actions.chart],['AI Analiz',actions.analysis],['Randevu',actions.appointment],['Tedavi',newTreatment]].map(([label,action])=><View key={String(label)} style={{width:'50%',padding:4}}>{button(String(label),action as ()=>void,label==='Diş Şeması')}</View>)}</View></View>
 <View style={styles.card}><Pressable accessibilityRole="button" accessibilityState={{expanded:infoOpen}} onPress={toggleInfo} style={{flexDirection:'row',justifyContent:'space-between',alignItems:'center',paddingVertical:4}}><View style={{flex:1}}><Text style={styles.section}>Hasta Bilgileri</Text><Text style={styles.meta}>Kimlik, doğum tarihi, telefon ve adres</Text></View><Text style={{fontSize:24,color:'#53657B'}}>{infoOpen?'⌃':'⌄'}</Text></Pressable>{infoOpen&&<View style={{marginTop:14}}>{([['first_name','Ad'],['last_name','Soyad'],['phone','Telefon'],['tc_kimlik_no','TC Kimlik No'],['birth_date','Doğum Tarihi'],['address','Adres'],['chief_complaint','Başvuru şikâyeti']] as const).map(([key,label])=><View key={key} style={{marginBottom:12}}><Text style={styles.label}>{label}</Text>{key==='birth_date'?<NativeDateField label={label} value={patientForm[key]} disabled={busy||uncertain} maxToday onChange={value=>setPatientForm(previous=>({...previous,[key]:value}))}/>:<TextInput accessibilityLabel={label} editable={!busy&&!uncertain} value={patientForm[key]} onChangeText={value=>setPatientForm(previous=>({...previous,[key]:value}))} keyboardType={key==='phone'?'phone-pad':key==='tc_kimlik_no'?'number-pad':'default'} maxLength={key==='tc_kimlik_no'?11:2000} multiline={key==='address'||key==='chief_complaint'} style={styles.input}/>}</View>)}<Text style={styles.meta}>Yaş: {p.age??'—'} · Hasta No: {p.anonymous_id}</Text>{button('Değişiklikleri Kaydet',()=>void savePatient(),true,uncertain)}{revisionConflict&&button('Güncel hasta bilgilerini yükle',()=>void reloadPatientForConflict())}{button('Hasta Kaydını Sil',confirmDelete)}</View>}</View>
 {!!mutationError&&<Text accessibilityRole="alert" style={styles.error}>{mutationError}</Text>}{uncertain&&button('Kaydı kontrol et, formu kapat',()=>{void load();setInfoOpen(false);setTreatmentOpen(false);Alert.alert('Kayıt durumunu kontrol edin','Profil ve geçmişte kaydın bulunmadığını doğrulamadan aynı işlemi tekrarlamayın.',[{text:'Vazgeç',style:'cancel'},{text:'Kontrol ettim',onPress:()=>{setUncertain(false);setMutationError('')}}])})}{!!error&&<View><Text style={styles.error}>{error}</Text>{button('Profili yenile',()=>void load())}</View>}
 <View style={styles.card}><NativePatientMedia key={scope} token={token} userId={userId} patientId={patientId} onAnalysis={actions.analysisResult}/></View>
 <View style={styles.card}><Text style={styles.kicker}>DENTAL AI</Text><NativePatientHistory key={scope} token={token} patientId={patientId} onOpenAnalysis={actions.analysisResult} onNew={actions.analysis}/>{button('Sesli Muayene',actions.voice)}</View>
 <View style={styles.card}><Text style={styles.kicker}>KLİNİK GEÇMİŞ</Text><View style={{flexDirection:'row',justifyContent:'space-between',alignItems:'center'}}><Text style={styles.section}>Tedavi Geçmişi</Text>{button('Yeni Tedavi',newTreatment)}</View>{treatmentOpen&&<View style={{paddingVertical:12}}><Text style={styles.section}>{editingTreatment===null?'Yeni tedavi kaydı':'Tedaviyi düzenle'}</Text>{([['treatment_name','Tedavi adı *'],['tooth_number','FDI diş numarası'],['treatment_date','Tedavi Tarihi'],['material','Kullanılan Materyal'],['result','Sonuç'],['doctor_note','Doktor Notu']] as const).map(([key,label])=><View key={key} style={{marginTop:12}}><Text style={styles.label}>{label}</Text>{key==='treatment_date'?<NativeDateField label={label} value={treatment[key]} disabled={busy||uncertain||!!pendingTreatment} onChange={value=>setTreatment(previous=>({...previous,[key]:value}))}/>:<TextInput accessibilityLabel={label} value={treatment[key]} editable={!busy&&!uncertain&&!pendingTreatment} onChangeText={value=>setTreatment(previous=>({...previous,[key]:value}))} multiline={key==='doctor_note'||key==='result'} style={styles.input}/>}</View>)}{pendingTreatment&&<Text style={styles.meta}>Bu taslak değiştirilemez. Aynı anahtarla sunucu kaydını doğrulayın.</Text>}{button(pendingTreatment?'Bekleyen Tedaviyi Doğrula':editingTreatment===null?'Tedaviyi Kaydet':'Değişiklikleri Kaydet',()=>void saveTreatment(),true,uncertain)}{button('Vazgeç',()=>setTreatmentOpen(false),false,!!pendingTreatment)}</View>}{(allTreatments?detail.treatments:detail.treatments.slice(0,3)).map(item=><View key={item.id} style={{paddingVertical:14,borderBottomWidth:1,borderColor:'#E5EAF0'}}><Text style={styles.label}>{item.treatment_name}</Text><Text style={styles.meta}>Diş {item.tooth_number||'—'} · {item.treatment_date||'—'}{item.material?` · ${item.material}`:''}</Text>{!!item.result&&<Text selectable style={styles.body}>Sonuç: {item.result}</Text>}{!!item.doctor_note&&<Text selectable style={styles.body}>Doktor Notu: {item.doctor_note}</Text>}{button('Düzenle',()=>{setEditingTreatment(item.id);setEditingTreatmentRevision(item.edit_revision||null);setTreatment({treatment_name:item.treatment_name,tooth_number:item.tooth_number||'',treatment_date:item.treatment_date||'',material:item.material||'',doctor_note:item.doctor_note||'',result:item.result||''});setTreatmentOpen(true)})}</View>)}{!detail.treatments.length&&<Text style={styles.meta}>Henüz tedavi kaydı bulunmuyor.</Text>}{detail.treatments.length>3&&button(allTreatments?'Tedavileri gizle':'Diğer tedavileri göster',()=>setAllTreatments(v=>!v))}</View></ScrollView></KeyboardAvoidingView>;
}
const styles=StyleSheet.create({page:{flex:1,backgroundColor:'#F5F7FB'},content:{padding:14,paddingBottom:36,gap:14},card:{backgroundColor:'white',borderWidth:1,borderColor:'#E5EAF0',borderRadius:16,padding:16},hero:{flexDirection:'row',alignItems:'center',gap:14},avatar:{height:66,width:66,borderRadius:20,backgroundColor:'#EDF4FF',alignItems:'center',justifyContent:'center'},kicker:{fontSize:11,fontWeight:'800',color:'#718096',marginBottom:5},name:{fontSize:23,fontWeight:'800',color:'#102033'},meta:{fontSize:13,color:'#64748B',marginTop:5,lineHeight:20},body:{fontSize:14,color:'#102033',marginTop:6,lineHeight:22},section:{fontSize:19,fontWeight:'800',color:'#102033'},actions:{flexDirection:'row',flexWrap:'wrap',marginTop:14,marginHorizontal:-4},button:{padding:12,borderRadius:10,minHeight:44,marginTop:4},primary:{backgroundColor:'#071B35'},buttonText:{color:'#1769AA',fontWeight:'700',textAlign:'center'},label:{color:'#102033',fontWeight:'700',marginBottom:6},input:{padding:12,borderWidth:1,borderColor:'#DCE3EB',borderRadius:10,color:'#102033',backgroundColor:'white'},error:{color:'#B42318',paddingVertical:8}});
