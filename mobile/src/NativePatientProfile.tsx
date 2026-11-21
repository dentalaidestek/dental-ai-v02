import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ActivityIndicator,Alert,AppState,KeyboardAvoidingView,Platform,Pressable,RefreshControl,ScrollView,StyleSheet,Text,TextInput,View} from 'react-native';
import {useIsFocused} from '@react-navigation/native';
import {createTreatment,deletePatient,editPatient,getPatient,getPatientTreatments,PatientDetail,updateTreatment} from './api';
import {useRealtime} from './realtime';
import NativeDateField from './NativeDateField';
import NativePatientHistory from './NativePatientHistory';
import NativePatientVoiceHistory from './NativePatientVoiceHistory';
import NativePatientMedia from './NativePatientMedia';
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import {chunkedDraftStore} from './socialDraft';
import {parseTreatmentMutationIntent,treatmentMutationStorageKey,type TreatmentMutationIntent} from './treatmentMutation';
import {createPatientDeleteIntent,parsePatientDeleteIntent,patientDeleteIntentStorageKey,type PatientDeleteIntent} from './patientDeleteIntent';
import {isPatientProfileEditRevision,patientProfileAgeLabel,patientProfileCanDeletePatient,patientProfileEditError,patientProfileEditFields,patientProfileEditMatches,patientProfileEditRevisionError,patientProfileInitials,patientProfileName,patientProfileMergeEditConflict,patientProfileQuickActions,type PatientProfileEditConflict,type PatientProfileEditField} from './patientProfilePresentation';
import {patientTreatmentCanEdit,patientTreatmentDateLabel,patientTreatmentMaterialLabel,patientTreatmentToothLabel} from './patientTreatmentPresentation';
import {patientTreatmentHistoryExpansionAfterRefresh} from './patientTreatmentHistoryExpansion';
import { shouldRefreshOnAppResume } from './appResumeRefresh';
import {nextSessionRenderKey} from './sessionRenderKey';

const blankTreatment={treatment_name:'',tooth_number:'',treatment_date:'',material:'',doctor_note:'',result:''};
const treatmentStore=chunkedDraftStore(SecureStore,Crypto.randomUUID);
const patientDeleteStore=chunkedDraftStore(SecureStore,Crypto.randomUUID);
const mutationMayHaveReachedServer=(error:unknown)=>{const status=(error as {status?:number})?.status;return typeof status!=='number'||!Number.isInteger(status)||status===408||status===429||status>=500};
const blankPatient={first_name:'',last_name:'',phone:'',birth_date:'',tc_kimlik_no:'',address:'',chief_complaint:''};
const quickActions=patientProfileQuickActions();
const actionColors:Record<string,string>={chart:'#1769F5',analysis:'#8B39E8',appointment:'#FF4F60',treatment:'#08B978'};
type Actions={chart:()=>void;analysis:()=>void;appointment:()=>void;expert:()=>void;analysisResult:(id:number)=>void;deleted:()=>void};
export default function NativePatientProfile({token,userId,patientId,actions}:{token:string;userId:number;patientId:number;actions:Actions}){
 const focused=useIsFocused(),{lastEvent}=useRealtime(),[detail,setDetail]=useState<PatientDetail|null>(null),[loadedScope,setLoadedScope]=useState(''),[error,setError]=useState(''),[refreshing,setRefreshing]=useState(false),[infoOpen,setInfoOpen]=useState(false),[treatmentOpen,setTreatmentOpen]=useState(false),[allTreatments,setAllTreatments]=useState(false),[treatmentCursor,setTreatmentCursor]=useState<string|null>(null),[treatmentPageLoading,setTreatmentPageLoading]=useState(false),[treatmentPageError,setTreatmentPageError]=useState(''),[patientForm,setPatientForm]=useState(blankPatient),[patientFormBase,setPatientFormBase]=useState(blankPatient),[profileConflicts,setProfileConflicts]=useState<readonly PatientProfileEditConflict[]>([]),[treatment,setTreatment]=useState(blankTreatment),[editingTreatment,setEditingTreatment]=useState<number|null>(null),[editingTreatmentRevision,setEditingTreatmentRevision]=useState<string|null>(null),[pendingTreatment,setPendingTreatment]=useState<TreatmentMutationIntent|null>(null),[treatmentIntentReady,setTreatmentIntentReady]=useState(false),[treatmentIntentBlocked,setTreatmentIntentBlocked]=useState(false),[busy,setBusy]=useState(false),[mutationError,setMutationError]=useState(''),[profileUncertain,setProfileUncertain]=useState(false),[treatmentUncertain,setTreatmentUncertain]=useState(false),[deleteIntentReady,setDeleteIntentReady]=useState(false),[deleteIntentBlocked,setDeleteIntentBlocked]=useState(false),[pendingDelete,setPendingDelete]=useState<PatientDeleteIntent|null>(null),[revisionConflict,setRevisionConflict]=useState(false);
 const scope=`${userId}:${token}:${patientId}`;
 const profileRenderIdentity=useRef<{scope:string;key:string}|null>(null);
 if(!profileRenderIdentity.current||profileRenderIdentity.current.scope!==scope)profileRenderIdentity.current={scope,key:nextSessionRenderKey()};
 const profileRenderKey=profileRenderIdentity.current.key;
 const mounted=useRef(true),request=useRef(0),treatmentHistoryScope=useRef(scope),treatmentPageRequest=useRef(0),treatmentPageLock=useRef(false),treatmentPageIds=useRef(new Set<number>()),treatmentPageCursors=useRef(new Set<string>()),lock=useRef(false),owner=useRef(scope);const scopeChanged=owner.current!==scope;if(owner.current!==scope){owner.current=scope;request.current++;}if(scopeChanged){treatmentPageRequest.current++;treatmentPageLock.current=false;}
 const editDraftDirty=!patientProfileEditMatches(patientForm,patientFormBase);const profileRevisionError=patientProfileEditRevisionError(detail?.edit_revision);const editSnapshot=useRef<{scope:string;active:boolean;revision?:string;patient:PatientDetail['patient']|null}>({scope,active:false,revision:undefined,patient:null});editSnapshot.current=editSnapshot.current.scope===scope?{scope,active:infoOpen||editDraftDirty||profileConflicts.length>0||revisionConflict,revision:detail?.edit_revision,patient:detail?.patient??null}:{scope,active:false,revision:undefined,patient:null};
 const current=()=>mounted.current&&owner.current===scope;
 const mutationUncertain=profileUncertain||treatmentUncertain;
 const focusedRef=useRef(focused);focusedRef.current=focused;
 const actionsRef=useRef(actions);actionsRef.current=actions;
 const deleteGate=useRef({busy,uncertain:mutationUncertain,profileEditReady:!editDraftDirty&&profileConflicts.length===0&&!revisionConflict,treatmentIntentReady,treatmentIntentBlocked,hasPendingTreatment:pendingTreatment!==null,deleteIntentReady,deleteIntentBlocked,hasPendingDelete:pendingDelete!==null});
 deleteGate.current={busy,uncertain:mutationUncertain,profileEditReady:!editDraftDirty&&profileConflicts.length===0&&!revisionConflict,treatmentIntentReady,treatmentIntentBlocked,hasPendingTreatment:pendingTreatment!==null,deleteIntentReady,deleteIntentBlocked,hasPendingDelete:pendingDelete!==null};
 const canDeletePatient=patientProfileCanDeletePatient(deleteGate.current);
 const canResolvePatientDelete=!busy&&!mutationUncertain&&treatmentIntentReady&&!treatmentIntentBlocked&&!pendingTreatment&&deleteIntentReady&&!deleteIntentBlocked&&pendingDelete!==null;
 const patientMutationBlocked=!deleteIntentReady||deleteIntentBlocked||pendingDelete!==null;
 const canEditTreatment=patientTreatmentCanEdit({busy,profileUncertain,treatmentUncertain,treatmentIntentReady,treatmentIntentBlocked,hasPendingTreatment:pendingTreatment!==null,patientMutationBlocked});
 const treatmentKey=treatmentMutationStorageKey(userId,patientId),deleteKey=patientDeleteIntentStorageKey(userId,patientId);
 const load=useCallback(async()=>{const previousTreatmentScope=treatmentHistoryScope.current;treatmentHistoryScope.current=scope;const seq=++request.current;treatmentPageRequest.current++;treatmentPageLock.current=false;setTreatmentPageLoading(false);setTreatmentPageError('');setRefreshing(true);try{const result=await getPatient(token,patientId);if(!current()||seq!==request.current)return false;if(result.patient.id!==patientId)throw Error('Sunucu farklı bir hasta kaydı döndürdü.');treatmentPageIds.current=new Set(result.treatments.map(item=>item.id));treatmentPageCursors.current.clear();if(result.treatments_next_cursor)treatmentPageCursors.current.add(result.treatments_next_cursor);setTreatmentCursor(result.treatments_next_cursor??null);setAllTreatments(previous=>patientTreatmentHistoryExpansionAfterRefresh(previous,previousTreatmentScope,scope));const editState=editSnapshot.current;const concurrentProfileChange=editState.active&&!!editState.revision&&!!result.edit_revision&&editState.revision!==result.edit_revision&&!!editState.patient;if(concurrentProfileChange){setRevisionConflict(true);setMutationError('Hasta bilgileri başka bir oturumda değişti. Taslağınız korundu; güncel kayıtla birleştirin.');setDetail({...result,patient:editState.patient!,edit_revision:editState.revision})}else setDetail(result);setLoadedScope(scope);setError('');return true}catch(e){if(current()&&seq===request.current){if((e as {status?:number})?.status===404){actionsRef.current.deleted();}else setError(e instanceof Error?e.message:'Hasta alınamadı.');}return false}finally{if(current()&&seq===request.current)setRefreshing(false)}},[token,patientId,userId]);
 useEffect(()=>{mounted.current=true;lock.current=false;treatmentPageRequest.current++;treatmentPageLock.current=false;treatmentPageIds.current.clear();treatmentPageCursors.current.clear();setTreatmentCursor(null);setTreatmentPageLoading(false);setTreatmentPageError('');setBusy(false);setDetail(null);setLoadedScope('');setInfoOpen(false);setTreatmentOpen(false);setEditingTreatment(null);setEditingTreatmentRevision(null);setPendingTreatment(null);setTreatmentIntentReady(false);setTreatmentIntentBlocked(false);setDeleteIntentReady(false);setDeleteIntentBlocked(false);setPendingDelete(null);setAllTreatments(false);setPatientForm(blankPatient);setPatientFormBase(blankPatient);setProfileConflicts([]);setTreatment(blankTreatment);setProfileUncertain(false);setTreatmentUncertain(false);setRevisionConflict(false);setMutationError('');return()=>{mounted.current=false;request.current++;treatmentPageRequest.current++;treatmentPageLock.current=false}},[load,userId]);
 useEffect(()=>{let active=true;void(async()=>{try{const raw=await treatmentStore.getItemAsync(treatmentKey);if(raw&&active&&current()){const saved=parseTreatmentMutationIntent(raw,userId,patientId);setPendingTreatment(saved);setTreatment(saved.payload);setEditingTreatment(saved.treatmentId);setEditingTreatmentRevision(saved.expectedRevision);setTreatmentOpen(true);setMutationError('Bekleyen tedavi işlemi bulundu. Aynı işlem anahtarıyla sunucuya doğrulatın.')}}catch(e){if(active&&current()){setTreatmentIntentBlocked(true);setMutationError(e instanceof Error?e.message:'Bekleyen tedavi kaydı okunamadı.')}}finally{if(active&&current())setTreatmentIntentReady(true)}})();return()=>{active=false}},[treatmentKey,token,userId,patientId]);
 useEffect(()=>{let active=true;void(async()=>{try{const raw=await patientDeleteStore.getItemAsync(deleteKey);if(raw!==null&&active&&current()){const saved=parsePatientDeleteIntent(raw,userId,patientId);setPendingDelete(saved);setMutationError('Bekleyen hasta silme işlemi bulundu. Aynı işlem anahtarıyla doğrulayın.')}}catch(e){if(active&&current()){setDeleteIntentBlocked(true);setMutationError(e instanceof Error?e.message:'Bekleyen hasta silme kaydı okunamadı. Yeni silme işlemi başlatılamaz.')}}finally{if(active&&current())setDeleteIntentReady(true)}})();return()=>{active=false}},[deleteKey,token,userId,patientId]);
 useEffect(()=>{
  if(focused)void load();
  let previousState=AppState.currentState;
  const listener=AppState.addEventListener('change',nextState=>{
   const shouldRefresh=shouldRefreshOnAppResume(previousState,nextState,focused);
   previousState=nextState;
   if(shouldRefresh)void load();
  });
  return()=>listener.remove();
 },[focused,load]);
 useEffect(()=>{if(!lastEvent||Number(lastEvent.payload?.patient_id||lastEvent.entity_id)!==patientId)return;const type=String(lastEvent.event_type||lastEvent.type);if(type==='PATIENT_DELETED')actions.deleted();else if(['PATIENT_UPDATED','TOOTH_UPDATED','PATIENT_MEDIA_CREATED','PATIENT_MEDIA_DELETED','TREATMENT_CREATED','TREATMENT_UPDATED'].includes(type))void load()},[lastEvent,patientId,load]);
 function toggleInfo(){if(!detail||busy)return;if(!infoOpen&&patientProfileEditMatches(patientForm,patientFormBase)&&profileConflicts.length===0&&!revisionConflict){const p=detail.patient;const values={first_name:p.first_name||'',last_name:p.last_name||'',phone:p.phone||'',birth_date:p.birth_date||'',tc_kimlik_no:p.tc_kimlik_no||'',address:p.address||'',chief_complaint:p.chief_complaint||''};setPatientForm(values);setPatientFormBase(values);setProfileConflicts([])}setInfoOpen(v=>!v)}
 async function savePatient(){
  if(profileConflicts.length){setMutationError('Önce başka oturumda değiştirilen alanlar için taslak veya güncel değeri seçin.');return}
  if(revisionConflict){setMutationError('Hasta bilgileri başka bir oturumda değişti. Önce güncel kayıtla taslağı birleştirin.');return}
  if(lock.current||profileUncertain||treatmentUncertain||pendingTreatment||!treatmentIntentReady||treatmentIntentBlocked||patientMutationBlocked)return;
  const validationError=patientProfileEditError(patientForm);if(validationError){setMutationError(validationError);return}
  const expectedRevision=detail?.edit_revision;
  if(!isPatientProfileEditRevision(expectedRevision)){setMutationError(patientProfileEditRevisionError(expectedRevision)||'Hasta kayıt sürümü alınamadı. Profili yenileyip tekrar deneyin.');return}
  lock.current=true;setBusy(true);setMutationError('');
  try{
   await editPatient(token,patientId,{...patientForm,expected_revision:expectedRevision});
   if(!current())return;
   setInfoOpen(false);setRevisionConflict(false);setProfileConflicts([]);setPatientFormBase(patientForm);editSnapshot.current={scope,active:false,revision:undefined,patient:null};
   if(!await load())setMutationError('Bilgiler kaydedildi; güncel profil alınamadı. Yenileyin.');
  }catch(e){
   if(current()){
    const status=(e as {status?:number})?.status;
    if(status===409){
     setRevisionConflict(true);
     setMutationError(e instanceof Error?e.message:'Hasta bilgileri başka bir oturumda güncellendi. Güncel kaydı yükleyip değişikliklerinizi yeniden uygulayın.');
    }else{
     setProfileUncertain(mutationMayHaveReachedServer(e));
     setMutationError((e instanceof Error?e.message:'Kaydetme doğrulanamadı.')+(mutationMayHaveReachedServer(e)?' Tekrar göndermeden önce profili yenileyip kaydı kontrol edin.':' Bilgileri düzeltip yeniden deneyin.'));
    }
   }
  }finally{if(current()){lock.current=false;setBusy(false)}}
 }
 function resolvePatientEditConflict(field:PatientProfileEditField,choice:'draft'|'current'){
  const conflict=profileConflicts.find(item=>item.field===field);
  if(!conflict)return;
  if(choice==='current')setPatientForm(previous=>({...previous,[field]:conflict.currentValue}));
  setProfileConflicts(previous=>previous.filter(item=>item.field!==field));
  setMutationError(profileConflicts.length>1
   ?'Kalan alan çakışmalarını da çözün.'
   :'Alan çakışmaları çözüldü. Güncel kayıt sürümüyle kaydedebilirsiniz.');
 }
 async function reloadPatientForConflict(){
  if(lock.current||!current())return;
  lock.current=true;setBusy(true);
  try{
   const latest=await getPatient(token,patientId);
   if(!current())return;
   if(latest.patient.id!==patientId)throw Error('Sunucu farklı bir hasta kaydı döndürdü.');
   const p=latest.patient;
   const currentForm={first_name:p.first_name||'',last_name:p.last_name||'',phone:p.phone||'',birth_date:p.birth_date||'',tc_kimlik_no:p.tc_kimlik_no||'',address:p.address||'',chief_complaint:p.chief_complaint||''};
   const merged=patientProfileMergeEditConflict(patientFormBase,patientForm,currentForm);
   setDetail(latest);setLoadedScope(scope);
   setPatientFormBase(currentForm);
   setPatientForm(merged.values);
   setProfileConflicts(merged.conflicts);
   setRevisionConflict(false);
   setMutationError(merged.conflicts.length
    ?'Taslağınız korundu. Aynı alanlarda iki oturumun değişiklikleri var; her çakışmayı seçerek çözün.'
    :'Taslağınız korundu ve diğer oturumdaki bağımsız değişikliklerle birleştirildi. Kaydedebilirsiniz.');
  }catch(e){if(current())setMutationError(e instanceof Error?e.message:'Güncel hasta bilgileri alınamadı.')}
  finally{if(current()){lock.current=false;setBusy(false)}}
 }
 async function reconcilePatientEdit(){
  if(lock.current||pendingTreatment||treatmentUncertain||!profileUncertain)return;
  lock.current=true;setBusy(true);setMutationError('');
  try{
   const latest=await getPatient(token,patientId);
   if(!current())return;
   if(latest.patient.id!==patientId)throw Error('Sunucu farklı bir hasta kaydı döndürdü.');
   const p=latest.patient;
   const latestForm={first_name:p.first_name||'',last_name:p.last_name||'',phone:p.phone||'',birth_date:p.birth_date||'',tc_kimlik_no:p.tc_kimlik_no||'',address:p.address||'',chief_complaint:p.chief_complaint||''};
   const merged=patientProfileMergeEditConflict(patientFormBase,patientForm,latestForm);
   setDetail(latest);setLoadedScope(scope);setPatientFormBase(latestForm);setPatientForm(merged.values);setProfileConflicts(merged.conflicts);
   setProfileUncertain(false);setRevisionConflict(false);
   const saved=merged.conflicts.length===0&&patientProfileEditMatches(merged.values,latestForm);
   if(saved){
    setInfoOpen(false);
    setMutationError('Hasta bilgileri sunucuda doğrulandı; profil kaydı tamamlanmış.');
   }else if(merged.conflicts.length){
    setMutationError('Taslağınız korundu. Aynı alanlarda iki oturumun değişiklikleri var; kaydetmeden önce seçim yapın.');
   }else{
    setMutationError('Taslağınız korundu ve güncel sunucu alanlarıyla birleştirildi. Güncel kayıt sürümüyle kaydedebilirsiniz.');
   }
  }catch(e){
   if(current())setMutationError((e instanceof Error?e.message:'Hasta kaydı doğrulanamadı.')+' Belirsizlik korunuyor; tekrar göndermeden önce yeniden kontrol edin.');
  }finally{if(current()){lock.current=false;setBusy(false)}}
 }
 async function saveTreatment(){
  if(lock.current||profileUncertain||(treatmentUncertain&&!pendingTreatment)||patientMutationBlocked)return;
  if(!treatmentIntentReady||treatmentIntentBlocked){setMutationError('Bekleyen tedavi taslağı kontrol edilmeden yeni işlem başlatılamaz.');return}
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
   setPendingTreatment(null);setTreatmentUncertain(false);setTreatmentOpen(false);setEditingTreatment(null);setEditingTreatmentRevision(null);setTreatment(blankTreatment);
   if(!await load())setMutationError('Tedavi kaydedildi; geçmiş alınamadı. Yenileyin.');
  }catch(e){
   if(!current())return;
   const status=(e as {status?:number})?.status,message=e instanceof Error?e.message:'Tedavi kaydı doğrulanamadı.';
   if(status===409&&message.includes('Tedavi başka bir oturumda güncellendi')){
    try{await treatmentStore.deleteItemAsync(treatmentKey)}catch{setTreatmentIntentBlocked(true);setMutationError('Tedavi sürüm çakışması bulundu ancak güvenli taslak temizlenemedi. Yeni işlem başlatmayın; aynı taslağı doğrulamak için ekranı yeniden açın.');return}
    setPendingTreatment(null);setTreatmentOpen(false);setEditingTreatment(null);setEditingTreatmentRevision(null);setTreatment(blankTreatment);setTreatmentUncertain(false);await load();setMutationError('Tedavi başka bir oturumda güncellendi. Güncel geçmiş yüklendi; yeniden düzenleyin.');
   }else if([400,403,404,422].includes(Number(status))){
    try{await treatmentStore.deleteItemAsync(treatmentKey)}catch{setTreatmentIntentBlocked(true);setMutationError('Sunucu isteği reddetti ancak güvenli taslak temizlenemedi. Yeni işlem başlatmayın; ekranı yeniden açıp kaydı doğrulayın.');return}
    setPendingTreatment(null);setTreatmentUncertain(false);setMutationError(message+' Bilgileri düzeltip yeniden deneyin.');
   }else{
    setTreatmentUncertain(sent&&mutationMayHaveReachedServer(e));
    setMutationError(message+(sent?' Aynı işlem anahtarı güvenli taslakta korundu; tekrar göndermek yerine aynı kaydı doğrulayın.':' Güvenli taslak kaydedilemedi; sunucuya istek gönderilmedi.'));
   }
  }finally{if(current()){lock.current=false;setBusy(false)}}
 }
 async function loadMoreTreatments(){
  const cursor=treatmentCursor;
  if(!cursor||treatmentPageLock.current||treatmentPageLoading||!current())return;
  const seq=++treatmentPageRequest.current,requestScope=scope;
  treatmentPageLock.current=true;setTreatmentPageLoading(true);setTreatmentPageError('');
  try{
   const page=await getPatientTreatments(token,patientId,cursor);
   if(!current()||seq!==treatmentPageRequest.current||owner.current!==requestScope)return;
   if(page.items.some(item=>treatmentPageIds.current.has(item.id)))
    throw Error('Tedavi geçmişinde tekrarlanan kayıt algılandı. Mevcut kayıtlar korundu; geçmişi yenileyin.');
   if(page.next_cursor&&(page.next_cursor===cursor||treatmentPageCursors.current.has(page.next_cursor)))
    throw Error('Tedavi geçmişi sayfalama döngüsü algılandı. Mevcut kayıtlar korundu; geçmişi yenileyin.');
   page.items.forEach(item=>treatmentPageIds.current.add(item.id));
   treatmentPageCursors.current.add(cursor);
   if(page.next_cursor)treatmentPageCursors.current.add(page.next_cursor);
   setDetail(previous=>previous&&previous.patient.id===patientId
    ?{...previous,treatments:[...previous.treatments,...page.items]}
    :previous);
   setTreatmentCursor(page.next_cursor);
  }catch(e){
   if(current()&&seq===treatmentPageRequest.current)
    setTreatmentPageError(e instanceof Error?e.message:'Tedavi geçmişi yüklenemedi. Tekrar deneyin.');
  }finally{
   if(seq===treatmentPageRequest.current){treatmentPageLock.current=false;setTreatmentPageLoading(false);}
  }
 }
 async function performPatientDelete(){
  if(!current()||!focusedRef.current)return;
  const allowed=pendingDelete!==null?canResolvePatientDelete:canDeletePatient;
  if(lock.current||!allowed){setMutationError('Hasta silme işlemi için önce profil, tedavi ve güvenli silme kayıtları doğrulanmalıdır.');return}
  lock.current=true;setBusy(true);setMutationError('');
  let intent=pendingDelete;
  try{
   // The web delete form is an explicit destructive action. Native also owns
   // an editable local draft, so when that form is open we re-read the server
   // snapshot immediately before creating a delete intent. A stale snapshot
   // must be reconciled instead of silently discarding local/profile changes.
   if(!intent&&infoOpen){
    let latest:PatientDetail;
    try{latest=await getPatient(token,patientId)}
    catch(e){
     if(current())setMutationError((e instanceof Error?e.message:'Güncel hasta bilgileri alınamadı.')+' Hasta silme isteği gönderilmedi.');
     return;
    }
    if(!current())return;
    if(latest.patient.id!==patientId){setMutationError('Sunucu farklı bir hasta kaydı döndürdü. Hasta silme isteği gönderilmedi.');return}
    const p=latest.patient;
    const latestForm={first_name:p.first_name||'',last_name:p.last_name||'',phone:p.phone||'',birth_date:p.birth_date||'',tc_kimlik_no:p.tc_kimlik_no||'',address:p.address||'',chief_complaint:p.chief_complaint||''};
    if(!patientProfileEditMatches(patientForm,latestForm)){
     setDetail(latest);setLoadedScope(scope);setRevisionConflict(true);
     setMutationError('Hasta bilgileri başka bir oturumda değişti. Silme durduruldu; önce güncel kayıtla karşılaştırın.');
     return;
    }
   }
   if(!intent){
    intent=createPatientDeleteIntent(userId,patientId,Crypto.randomUUID());
    try{await patientDeleteStore.setItemAsync(deleteKey,JSON.stringify(intent))}
    catch{if(current()){setDeleteIntentBlocked(true);setMutationError('Hasta silme işlemi cihazın güvenli alanına kaydedilemedi. Sunucuya istek gönderilmedi.');}return}
    if(!current())return;
    setPendingDelete(intent);
   }
   const result=await deletePatient(token,patientId,intent.requestKey);
   if(!current())return;
   if(result.patient_id!==patientId||result.ok!==true)throw new Error('Hasta silme yanıtı doğrulanamadı.');
   try{await patientDeleteStore.deleteItemAsync(deleteKey)}
   catch{if(current()){setPendingDelete(intent);setMutationError('Hasta kaydı silindi; ancak cihazdaki güvenli işlem kaydı temizlenemedi. Aynı işlemi doğrulayın.');}return}
   setPendingDelete(null);setDeleteIntentBlocked(false);actionsRef.current.deleted();
  }catch(e){
   if(!current())return;
   const status=(e as {status?:number})?.status,message=e instanceof Error?e.message:'Hasta silme işlemi doğrulanamadı.';
   if(status===409){
    try{await patientDeleteStore.deleteItemAsync(deleteKey);setPendingDelete(null);setMutationError(message+' Hasta kaydı silinmedi; klinik geçmişi korundu.');}
    catch{setDeleteIntentBlocked(true);setPendingDelete(intent);setMutationError('Silme isteği reddedildi ancak güvenli taslak temizlenemedi. Aynı işlem anahtarını koruyun; yeni silme isteği oluşturmayın.');}
   }else if(status===404){
    try{await patientDeleteStore.deleteItemAsync(deleteKey)}catch{}
    setPendingDelete(null);actionsRef.current.deleted();
   }else{
    setPendingDelete(intent);
    setMutationError(message+' Aynı işlem anahtarı güvenli alanda korundu. Yeni bir anahtar oluşturmayın; Bekleyen Silme İşlemini Doğrula ile aynı isteği yeniden gönderin.');
   }
  }finally{if(current()){lock.current=false;setBusy(false)}}
 }
 function confirmDelete(){
  if(!current()||!focusedRef.current)return;
  const replay=pendingDelete!==null;
  const allowed=replay?canResolvePatientDelete:canDeletePatient;
  if(lock.current||!allowed){setMutationError('Bekleyen profil, tedavi veya silme işlemi doğrulanmadan yeni silme başlatılamaz.');return}
  Alert.alert(replay?'Bekleyen hasta silme işlemi':'Hasta kaydı silinsin mi?',replay?'Önceki silme isteği aynı anahtarla tekrar doğrulanacak.':'Bu işlem geri alınamaz.',[
   {text:'Vazgeç',style:'cancel'},
   {text:'Devam',style:'destructive',onPress:()=>Alert.alert('Son onay',replay?'Aynı silme isteği sunucuya yeniden gönderilecek.':'Hasta kaydını kalıcı olarak silmek üzeresiniz.',[
    {text:'Vazgeç',style:'cancel'},
    {text:replay?'Aynı İşlemi Doğrula':'Hasta Kaydını Sil',style:'destructive',onPress:()=>void performPatientDelete()}
   ])}
  ]);
 }
 const button=(label:string,action:()=>void,primary=false,disabled=false)=><Pressable accessibilityRole="button" disabled={disabled||busy} onPress={action} style={[styles.button,primary&&styles.primary,(disabled||busy)&&{opacity:.5}]}><Text style={[styles.buttonText,primary&&{color:'white'}]}>{label}</Text></Pressable>;
 function newTreatment(){if(patientMutationBlocked){setMutationError('Önce bekleyen hasta silme işlemini aynı anahtarla doğrulayın.');return}if(profileUncertain||treatmentUncertain){setMutationError('Önce bekleyen profil veya tedavi işlemini sunucuyla doğrulayın.');return}if(!treatmentIntentReady||treatmentIntentBlocked){setMutationError('Önce bekleyen tedavi taslağının kontrolü tamamlanmalı.');return}if(pendingTreatment){setMutationError('Önce bekleyen tedavi işlemini aynı anahtarla doğrulayın.');return}setEditingTreatment(null);setEditingTreatmentRevision(null);setTreatment(blankTreatment);setTreatmentOpen(true)}
 const actionHandlers={chart:actions.chart,analysis:actions.analysis,appointment:actions.appointment,treatment:newTreatment};
 if(!detail||loadedScope!==scope)return <View style={{padding:24}}>{error?<><Text accessibilityRole="alert" style={styles.error}>{error}</Text>{button('Yeniden dene',()=>void load())}</>:<ActivityIndicator color="#071B35"/>}</View>;
 const p=detail.patient;
 // Web-aligned identity summary (bc6ac019 render referenced these without
 // committing their definitions; presentation helpers are the single source).
 const displayName=patientProfileName(p.first_name,p.last_name),initials=patientProfileInitials(p.first_name,p.last_name),ageLabel=patientProfileAgeLabel(p.age);
 return <KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==='ios'?'padding':undefined}><ScrollView style={styles.page} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" refreshControl={<RefreshControl refreshing={refreshing} onRefresh={()=>void load()}/>}><View style={[styles.card,styles.heroCard]}><View style={styles.consultRow}><Pressable accessibilityRole="button" accessibilityLabel="Uzmana Danış" accessibilityHint="Bu hastayla ilgili uzman desteği ekranını açar." disabled={busy||patientMutationBlocked} onPress={actions.expert} style={[styles.consultButton,busy&&{opacity:.5}]}><Text style={styles.consultText}>Uzmana Danış</Text></Pressable></View><View style={styles.hero}>
 <View style={styles.avatar}><Text style={styles.avatarText}>{initials}</Text></View>
 <View style={{flex:1,minWidth:0}}>
  <Text style={styles.kicker}>HASTA PROFİLİ</Text>
  <Text accessibilityRole="header" style={styles.name}>{displayName}</Text>
  <View style={styles.metaRow}>
   <View style={styles.metaChip}><Text numberOfLines={1} style={styles.metaChipText}>{ageLabel}</Text></View>
   <View style={styles.metaChip}><Text numberOfLines={1} style={styles.metaChipText}>{p.phone||'—'}</Text></View>
   <View style={styles.metaChip}><Text numberOfLines={1} style={styles.metaChipText}>{p.anonymous_id}</Text></View>
  </View>
 </View>
</View>
<View style={styles.complaint}><Text style={styles.complaintLabel}>BAŞVURU ŞİKÂYETİ</Text><Text style={styles.complaintText}>{p.chief_complaint?.trim()||'Belirtilmemiş'}</Text></View><View style={styles.actionSection}><Text style={styles.sectionKicker}>HIZLI İŞLEMLER</Text><View style={styles.actions}>{quickActions.map(item=><View key={item.key} style={styles.actionSlot}><Pressable accessibilityRole="button" accessibilityLabel={item.label} accessibilityHint={item.hint} accessibilityState={{disabled:busy||patientMutationBlocked}} disabled={busy||patientMutationBlocked} onPress={actionHandlers[item.key]} style={[styles.actionTile,{backgroundColor:actionColors[item.key]||'#1769F5'}]}><View style={styles.actionIcon}><Text style={styles.actionIconText}>{item.icon}</Text></View><Text numberOfLines={2} style={styles.actionTitle}>{item.label}</Text></Pressable></View>)}</View></View></View>
 <View style={[styles.card,styles.infoCard]}><Pressable accessibilityRole="button" accessibilityState={{expanded:infoOpen}} onPress={toggleInfo} style={styles.infoToggle}><View style={{flex:1}}><Text style={styles.section}>Hasta Bilgileri</Text><Text style={styles.meta}>Kimlik, doğum tarihi, telefon ve adres</Text></View><Text style={{fontSize:24,color:'#53657B'}}>{infoOpen?'⌃':'⌄'}</Text></Pressable>{infoOpen&&<View style={styles.infoContent}>{patientProfileEditFields().map(field=><View key={field.key} style={{marginBottom:12}}><Text style={styles.label}>{field.label}</Text>{field.control==='date'?<NativeDateField label={field.label} value={patientForm[field.key]} disabled={busy||profileUncertain||treatmentUncertain||!!pendingTreatment||!treatmentIntentReady||treatmentIntentBlocked||patientMutationBlocked} maxToday onChange={value=>setPatientForm(previous=>({...previous,[field.key]:value}))}/>:<TextInput accessibilityLabel={field.label} editable={!busy&&!profileUncertain&&!treatmentUncertain&&!pendingTreatment&&treatmentIntentReady&&!treatmentIntentBlocked&&!patientMutationBlocked} value={patientForm[field.key]} onChangeText={value=>setPatientForm(previous=>({...previous,[field.key]:value}))} keyboardType={field.keyboardType||'default'} maxLength={field.maxLength??2000} multiline={field.multiline??false} style={styles.input}/>}</View>)}<Text style={styles.meta}>Yaş: {p.age??'—'} · Hasta No: {p.anonymous_id}</Text>{button('Değişiklikleri Kaydet',()=>void savePatient(),true,profileConflicts.length>0||revisionConflict||!!profileRevisionError||profileUncertain||treatmentUncertain||!!pendingTreatment||!treatmentIntentReady||treatmentIntentBlocked||patientMutationBlocked)}{profileRevisionError&&<Text accessibilityRole="alert" style={styles.error}>{profileRevisionError}</Text>}{profileRevisionError&&button('Profili yenile',()=>void load(),false,busy)}{revisionConflict&&button('Güncel kayıtla taslağı birleştir',()=>void reloadPatientForConflict())}{profileConflicts.length>0&&<View style={{borderWidth:1,borderColor:'#F0C36D',backgroundColor:'#FFF8E8',borderRadius:12,padding:12,marginTop:10}}><Text accessibilityRole="header" style={styles.label}>Eşzamanlı alan değişiklikleri</Text><Text style={styles.meta}>Her alan için hangi değerin korunacağını seçin. Kaydetme, seçimler tamamlanana kadar kapalıdır.</Text>{profileConflicts.map(conflict=><View key={conflict.field} style={{paddingTop:12,borderTopWidth:1,borderColor:'#F3D9A4',marginTop:10}}><Text style={styles.label}>{conflict.label}</Text><Text style={styles.meta}>Taslağınız: {conflict.draftValue||'—'}</Text><Text style={styles.meta}>Güncel kayıt: {conflict.currentValue||'—'}</Text>{button('Taslağımı koru',()=>resolvePatientEditConflict(conflict.field,'draft'))}{button('Güncel değeri kullan',()=>resolvePatientEditConflict(conflict.field,'current'))}</View>)}</View>}{editDraftDirty&&<Text style={styles.meta}>Kaydedilmemiş hasta bilgileri var. Hasta kaydını silmeden önce değişiklikleri kaydedin veya güncel kayıtla karşılaştırıp çözün.</Text>}{revisionConflict&&<Text style={styles.meta}>Hasta bilgileri başka bir oturumda değişti. Güncel kayıt doğrulanmadan silme yapılamaz.</Text>}{!canDeletePatient&&<Text style={styles.meta}>Silme işlemi, profil ve tedavi kayıtlarının güvenli durum kontrolü tamamlanana kadar devre dışıdır.</Text>}{button(pendingDelete?'Bekleyen Silme İşlemini Doğrula':'Hasta Kaydını Sil',confirmDelete,false,pendingDelete?(!canResolvePatientDelete):(!canDeletePatient))}</View>}</View>
 {pendingDelete&&<Text style={styles.meta}>Bekleyen hasta silme isteği aynı anahtarla doğrulanmalıdır. Yeni bir silme anahtarı oluşturulmaz.</Text>}{deleteIntentBlocked&&<Text accessibilityRole="alert" style={styles.error}>Güvenli hasta silme kaydı okunamadı veya temizlenemedi. Yeni bir silme işlemi başlatmayın.</Text>}{!!mutationError&&<Text accessibilityRole="alert" style={styles.error}>{mutationError}</Text>}{profileUncertain&&button('Sunucudaki profil kaydını karşılaştır',()=>void reconcilePatientEdit())}{treatmentUncertain&&pendingTreatment&&<Text style={styles.meta}>Bekleyen tedavi işlemi aynı işlem anahtarıyla doğrulanmalıdır; hasta kaydı silinemez.</Text>}{!!error&&<View><Text style={styles.error}>{error}</Text>{button('Profili yenile',()=>void load())}</View>}
 <View style={[styles.card,styles.sectionCard]}><NativePatientMedia key={profileRenderKey} token={token} userId={userId} patientId={patientId} patient={p} onAnalysis={actions.analysisResult} readOnly={patientMutationBlocked}/></View>
 <View style={[styles.card,styles.sectionCard]}><Text style={styles.kicker}>DENTAL AI</Text><NativePatientHistory key={profileRenderKey} token={token} patientId={patientId} onOpenAnalysis={actions.analysisResult} onNew={patientMutationBlocked?undefined:actions.analysis}/></View>
 <NativePatientVoiceHistory key={profileRenderKey} token={token} patientId={patientId}/>
 <View style={[styles.card,styles.sectionCard]}><Text style={styles.kicker}>KLİNİK GEÇMİŞ</Text><View style={{flexDirection:'row',justifyContent:'space-between',alignItems:'center'}}><Text style={styles.section}>Tedavi Geçmişi</Text>{button('Yeni Tedavi',newTreatment,false,profileUncertain||treatmentUncertain||!treatmentIntentReady||treatmentIntentBlocked||!!pendingTreatment||patientMutationBlocked)}</View>{treatmentOpen&&<View style={{paddingVertical:12}}><Text style={styles.section}>{editingTreatment===null?'Yeni tedavi kaydı':'Tedaviyi düzenle'}</Text>{([['treatment_name','Tedavi adı *'],['tooth_number','FDI diş numarası'],['treatment_date','Tedavi Tarihi'],['material','Kullanılan Materyal'],['result','Sonuç'],['doctor_note','Doktor Notu']] as const).map(([key,label])=><View key={key} style={{marginTop:12}}><Text style={styles.label}>{label}</Text>{key==='treatment_date'?<NativeDateField label={label} value={treatment[key]} disabled={busy||profileUncertain||treatmentUncertain||!!pendingTreatment||patientMutationBlocked} onChange={value=>setTreatment(previous=>({...previous,[key]:value}))}/>:<TextInput accessibilityLabel={label} value={treatment[key]} editable={!busy&&!profileUncertain&&!treatmentUncertain&&!pendingTreatment&&!patientMutationBlocked} onChangeText={value=>setTreatment(previous=>({...previous,[key]:value}))} multiline={key==='doctor_note'||key==='result'} style={styles.input}/>}</View>)}{pendingTreatment&&<Text style={styles.meta}>Bu taslak değiştirilemez. Aynı anahtarla sunucu kaydını doğrulayın.</Text>}{button(pendingTreatment?'Bekleyen Tedaviyi Doğrula':editingTreatment===null?'Tedaviyi Kaydet':'Değişiklikleri Kaydet',()=>void saveTreatment(),true,profileUncertain||(treatmentUncertain&&!pendingTreatment))}{button('Vazgeç',()=>setTreatmentOpen(false),false,!!pendingTreatment)}</View>}{(allTreatments?detail.treatments:detail.treatments.slice(0,3)).map(item=><View key={item.id} style={styles.treatmentCard}>
 <View style={styles.treatmentCardHeader}>
  <Text style={styles.treatmentTitle}>{item.treatment_name}</Text>
  <Pressable accessibilityRole="button" accessibilityLabel={item.treatment_name+" tedavisini düzenle"} accessibilityHint="Tedavi bilgilerini düzenleme formunda açar." accessibilityState={{disabled:!canEditTreatment}} disabled={!canEditTreatment} onPress={()=>{setEditingTreatment(item.id);setEditingTreatmentRevision(item.edit_revision||null);setTreatment({treatment_name:item.treatment_name,tooth_number:item.tooth_number||'',treatment_date:item.treatment_date||'',material:item.material||'',doctor_note:item.doctor_note||'',result:item.result||''});setTreatmentOpen(true)}} style={[styles.treatmentEditButton,!canEditTreatment&&{opacity:.45}]}>
   <Text style={styles.treatmentEditText}>Düzenle</Text>
  </Pressable>
 </View>
 <View style={styles.treatmentMetaRow}>
  <View style={styles.treatmentMetaChip}><Text style={styles.treatmentMetaText}>{patientTreatmentToothLabel(item.tooth_number)}</Text></View>
  <View style={styles.treatmentMetaChip}><Text style={styles.treatmentMetaText}>{patientTreatmentDateLabel(item.treatment_date)}</Text></View>
  {!!patientTreatmentMaterialLabel(item.material)&&<View style={styles.treatmentMetaChip}><Text style={styles.treatmentMetaText}>{patientTreatmentMaterialLabel(item.material)}</Text></View>}
 </View>
 {!!item.result?.trim()&&<View style={styles.treatmentNote}><Text style={styles.treatmentNoteText}><Text style={{fontWeight:'800'}}>Sonuç: </Text>{item.result}</Text></View>}
 {!!item.doctor_note?.trim()&&<View style={styles.treatmentNote}><Text style={styles.treatmentNoteText}><Text style={{fontWeight:'800'}}>Doktor Notu: </Text>{item.doctor_note}</Text></View>}
</View>)}{!detail.treatments.length&&<Text style={styles.meta}>Henüz tedavi kaydı bulunmuyor.</Text>}{allTreatments&&!!treatmentPageError&&<Text accessibilityRole="alert" style={styles.error}>{treatmentPageError}</Text>}{allTreatments&&treatmentPageLoading&&<ActivityIndicator size="small" color="#071B35"/>}{!allTreatments&&(treatmentCursor!==null||detail.treatments.length>3)&&button('Diğer tedavileri göster',()=>{setAllTreatments(true);if(treatmentCursor)void loadMoreTreatments()},false,patientMutationBlocked)}{allTreatments&&treatmentCursor!==null&&button(treatmentPageError?'Tekrar dene':treatmentPageLoading?'Yükleniyor…':'Daha fazla tedavi yükle',()=>void loadMoreTreatments(),false,treatmentPageLoading||patientMutationBlocked)}{allTreatments&&button('Tedavileri gizle',()=>setAllTreatments(false))}</View></ScrollView></KeyboardAvoidingView>;
}
const styles=StyleSheet.create({page:{flex:1,backgroundColor:'#F5F7FB'},content:{padding:12,paddingBottom:90,gap:9},card:{backgroundColor:'white',borderWidth:1,borderColor:'#E5EAF0',borderRadius:18,padding:16},heroCard:{backgroundColor:'#F3F8FF',borderColor:'#DCE7F4',padding:13},infoCard:{padding:0,overflow:'hidden'},infoToggle:{minHeight:54,paddingHorizontal:12,paddingVertical:9,flexDirection:'row',justifyContent:'space-between',alignItems:'center'},infoContent:{padding:12,paddingTop:14},sectionCard:{padding:12},consultRow:{alignItems:'flex-end',marginBottom:4},consultButton:{minHeight:32,paddingHorizontal:10,borderRadius:10,backgroundColor:'#EEF6FF',borderWidth:1,borderColor:'#BFDBFE',justifyContent:'center'},consultText:{color:'#1D4ED8',fontSize:11,fontWeight:'850'},complaint:{marginTop:6,padding:10,borderRadius:12,backgroundColor:'#F2F7FD',borderWidth:1,borderColor:'#E3EDF8',flexDirection:'row',alignItems:'baseline',flexWrap:'wrap',gap:8},complaintLabel:{fontSize:10,fontWeight:'800',letterSpacing:.7,color:'#60748B'},complaintText:{fontSize:12,fontWeight:'700',color:'#102033',lineHeight:18},hero:{flexDirection:'row',alignItems:'center',gap:10},avatar:{height:50,width:50,borderRadius:25,backgroundColor:'#E8F1FF',borderWidth:1,borderColor:'#DBEAFE',alignItems:'center',justifyContent:'center'},avatarText:{fontSize:18,fontWeight:'800',color:'#1769F5'},kicker:{fontSize:10,fontWeight:'800',color:'#718096',marginBottom:3},name:{fontSize:21,lineHeight:23,fontWeight:'800',color:'#102033',marginBottom:5},meta:{fontSize:13,color:'#64748B',marginTop:5,lineHeight:20},metaRow:{flexDirection:'row',flexWrap:'wrap',gap:4},metaChip:{minHeight:24,paddingHorizontal:7,paddingVertical:3,borderRadius:999,backgroundColor:'#F8FAFC',borderWidth:1,borderColor:'#E2E8F0',justifyContent:'center'},metaChipText:{fontSize:10,fontWeight:'700',color:'#64748B'},body:{fontSize:14,color:'#102033',marginTop:6,lineHeight:22},section:{fontSize:16,fontWeight:'800',color:'#102033'},actionSection:{marginTop:12},sectionKicker:{fontSize:10,fontWeight:'800',letterSpacing:.8,color:'#718096',marginBottom:8},actions:{flexDirection:'row',flexWrap:'wrap',marginHorizontal:-3},actionSlot:{width:'25%',padding:3},actionTile:{minHeight:70,flexDirection:'column',alignItems:'center',justifyContent:'center',gap:5,paddingVertical:7,paddingHorizontal:4,borderWidth:0,borderRadius:14,elevation:2,shadowColor:'#0F172A',shadowOpacity:.09,shadowRadius:8,shadowOffset:{width:0,height:4}},actionIcon:{width:30,height:30,borderRadius:15,alignItems:'center',justifyContent:'center',backgroundColor:'rgba(255,255,255,0.18)'},actionIconText:{fontSize:17,fontWeight:'800',color:'white'},actionTitle:{width:'100%',fontSize:10,lineHeight:12,fontWeight:'800',color:'white',textAlign:'center'},button:{padding:12,borderRadius:10,minHeight:44,marginTop:4},primary:{backgroundColor:'#071B35'},buttonText:{color:'#1769AA',fontWeight:'700',textAlign:'center'},label:{color:'#102033',fontWeight:'700',marginBottom:6},input:{padding:12,borderWidth:1,borderColor:'#DCE3EB',borderRadius:10,color:'#102033',backgroundColor:'white'},error:{color:'#B42318',paddingVertical:8},treatmentCard:{padding:14,marginTop:10,borderWidth:1,borderColor:'#E5EAF0',borderRadius:13,backgroundColor:'#FFFFFF'},treatmentCardHeader:{flexDirection:'row',alignItems:'flex-start',justifyContent:'space-between',gap:10},treatmentTitle:{flex:1,fontSize:15,fontWeight:'800',color:'#102033',lineHeight:21},treatmentEditButton:{minHeight:36,paddingHorizontal:11,paddingVertical:8,borderWidth:1,borderColor:'#D7E2EF',borderRadius:9,backgroundColor:'#F8FAFC',justifyContent:'center'},treatmentEditText:{fontSize:12,fontWeight:'800',color:'#1769AA'},treatmentMetaRow:{flexDirection:'row',flexWrap:'wrap',alignItems:'center',marginTop:9,gap:6},treatmentMetaChip:{backgroundColor:'#F1F5F9',borderRadius:7,paddingHorizontal:9,paddingVertical:6},treatmentMetaText:{fontSize:12,color:'#53657B'},treatmentNote:{marginTop:8,padding:10,borderRadius:9,backgroundColor:'#F8FAFC',borderWidth:1,borderColor:'#EEF2F6'},treatmentNoteText:{fontSize:13,color:'#344054',lineHeight:20}});
