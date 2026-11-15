const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const text=n=>typeof n==='string'?n:!n?'':(n.children||[]).map(text).join('');
const button=(t,label)=>t.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(c=>text(c)===label));
test('voice draft is account-patient bound, expires, and appends each segment only once',()=>{
 const api=require('../src/voiceSession.ts'),draft={...api.newVoiceDraft(1,8,1000),segments:[{id:'s1',uri:'file:///cache/audio.m4a',ready:true}]};
 assert.throws(()=>api.parseVoiceDraft(JSON.stringify(draft),2,8,2000),/hesabı/);assert.equal(api.parseVoiceDraft(JSON.stringify(draft),1,8,1000+86400001),null);
 const next=api.appendVoiceSegment(draft,'s1','Synthetic transcript');assert.equal(next.transcript,'Synthetic transcript');assert.equal(next.segments.length,0);assert.equal(api.appendVoiceSegment(next,'s1','Duplicate').transcript,'Synthetic transcript');
 let timed=api.addVoiceElapsed(api.newVoiceDraft(1,8,1000),1000,16000);timed=api.addVoiceElapsed(timed,30000,38000);assert.equal(timed.elapsedMs,23000);assert.equal(api.formatVoiceElapsed(timed.elapsedMs),'00:23');assert.equal(api.parseVoiceDraft(JSON.stringify(timed),1,8,38000).elapsedMs,23000);
 const legacy={...timed};delete legacy.elapsedMs;assert.equal(api.parseVoiceDraft(JSON.stringify(legacy),1,8,38000).elapsedMs,0);assert.equal(api.formatVoiceElapsed(65000),'01:05');assert.throws(()=>api.addVoiceElapsed(timed,200,100),/süresi/);assert.throws(()=>api.parseVoiceDraft(JSON.stringify({...timed,elapsedMs:-1}),1,8,38000),/içeriği/);
});
test('native audio transport sends binary recording with consent and validates receipt',async()=>{
 const exports={},calls=[];const source=ts.transpileModule(fs.readFileSync(require.resolve('../src/nativeVoiceAudio.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const filesystem={getInfoAsync:async()=>({exists:true,size:1024}),FileSystemUploadType:{BINARY_CONTENT:0},createUploadTask:(...args)=>{calls.push(args);return{uploadAsync:async()=>({status:200,body:JSON.stringify({ok:true,revision:'revision',transcript:'Synthetic speech'})}),cancelAsync:async()=>{}}}};
 vm.runInNewContext(source,{exports,setTimeout,clearTimeout,require:n=>n==='expo-file-system/legacy'?filesystem:n==='./api'?{ApiError:class extends Error{constructor(status,message){super(message);this.status=status}}}:{revalidateSession:async()=>{}}});
 const result=await exports.transcribeNativeRecording('token',8,'file:///cache/audio.m4a');assert.equal(result.transcript,'Synthetic speech');assert.equal(calls[0][2].headers['X-Voice-Consent'],'yes');assert.equal(calls[0][2].headers['Content-Type'],'audio/mp4');assert.equal(calls[0][2].headers.Cookie,'');assert.equal(calls[0][2].uploadType,0);
});
function recorderUI({saved=null,transcribe=async()=>({transcript:'Synthetic dictated speech',revision:'r'})}={}){
 const exports={},store=new Map(),calls=[],timers=[],state={isRecording:false,durationMillis:0,mediaServicesDidReset:false},audio={uri:'file:///cache/record.m4a',prepareToRecordAsync:async options=>{if(!options?.extension)throw Error('iOS segment preparation must receive fresh recording options');calls.push('prepare')},record(){state.isRecording=true;calls.push('record')},stop:async()=>{state.isRecording=false;calls.push('stop')}};
 let focused=true,clockNow=Date.now(),nextInterval=0;const intervals=new Map();
 const secure={getItemAsync:async key=>store.get(key)||null,setItemAsync:async(k,v)=>store.set(k,v),deleteItemAsync:async k=>store.delete(k)};
 const native={StyleSheet:{create:x=>x},Alert:{alert(){}},AppState:{currentState:'active',addEventListener:()=>({remove(){}})},...Object.fromEntries(['ActivityIndicator','Pressable','Text','TextInput','View'].map(x=>[x,x]))};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeVoiceRecorder.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,Date:{now:()=>clockNow},setInterval:fn=>{const id=++nextInterval;intervals.set(id,fn);return id},clearInterval:id=>intervals.delete(id),setTimeout:(fn,ms)=>ms===15000?(timers.push(fn),timers.length):setTimeout(fn,ms),clearTimeout:id=>{if(typeof id!=='number')clearTimeout(id)},AbortController,Error,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='expo-audio'?{useAudioRecorder:()=>audio,useAudioRecorderState:()=>state,RecordingPresets:{HIGH_QUALITY:{extension:'.m4a',android:{outputFormat:'mpeg4',audioEncoder:'aac'},ios:{}}},requestRecordingPermissionsAsync:async()=>({granted:true}),setAudioModeAsync:async()=>{}}:n==='expo-file-system/legacy'?{cacheDirectory:'file:///cache/',deleteAsync:async()=>{}}:n==='expo-secure-store'?secure:n==='expo-crypto'?{randomUUID:()=>String(calls.length)+'-synthetic'}:n==='@react-navigation/native'?{useIsFocused:()=>focused,usePreventRemove(){}}:n==='./socialDraft'?{chunkedDraftStore:()=>({getItemAsync:async()=>saved,setItemAsync:async(_k,v)=>{store.set('draft',v)},deleteItemAsync:async()=>{}})}:n==='./voiceSession'?require('../src/voiceSession.ts'):{transcribeNativeRecording:transcribe}});
 return{Component:exports.default,calls,store,timers,focus:value=>{focused=value},advance:ms=>{clockNow+=ms;for(const fn of intervals.values())fn()}};
}
test('native microphone pauses/resumes and only finishes clinical handoff after ASR',async()=>{
 const h=recorderUI(),transcripts=[],finished=[];let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript:v=>transcripts.push(v),onFinished:v=>finished.push(v)})));
 await renderer.act(async()=>button(tree,'Muayeneyi Başlat').props.onPress());assert.ok(h.calls.includes('record'));assert.equal(finished.length,0);
 await renderer.act(async()=>button(tree,'Duraklat').props.onPress());assert.ok(h.calls.includes('stop'));assert.equal(finished.length,0);assert.equal(transcripts.at(-1),'Synthetic dictated speech');
 await renderer.act(async()=>button(tree,'Devam Et').props.onPress());assert.equal(h.calls.filter(x=>x==='record').length,2);await renderer.act(async()=>button(tree,'Muayeneyi Bitir').props.onPress());assert.equal(finished.length,1);assert.ok(finished[0].includes('Synthetic dictated speech'));await renderer.act(async()=>tree.unmount());
});
test('native microphone elapsed time accumulates across recording chunks and pauses',async()=>{
 const h=recorderUI(),finished=[];let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished:v=>finished.push(v)})));
 await renderer.act(async()=>button(tree,'Muayeneyi Başlat').props.onPress());h.advance(4200);await renderer.act(async()=>button(tree,'Duraklat').props.onPress());assert.equal(JSON.parse(h.store.get('draft')).elapsedMs,4200);assert.ok(text(tree.toJSON()).includes('00:04'));
 await renderer.act(async()=>button(tree,'Devam Et').props.onPress());h.advance(2300);await renderer.act(async()=>button(tree,'Muayeneyi Bitir').props.onPress());assert.equal(JSON.parse(h.store.get('draft')).elapsedMs,6500);assert.ok(text(tree.toJSON()).includes('00:06'));assert.equal(finished.length,1);await renderer.act(async()=>tree.unmount());
});

test('pending ASR failure retains recording and never triggers clinical handoff',async()=>{
 const h=recorderUI({transcribe:async()=>{throw Error('Synthetic ASR failure')}}),finished=[];let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished:v=>finished.push(v)})));await renderer.act(async()=>button(tree,'Muayeneyi Başlat').props.onPress());await renderer.act(async()=>button(tree,'Muayeneyi Bitir').props.onPress());assert.equal(finished.length,0);assert.equal(JSON.parse(h.store.get('draft')).segments.length,1);assert.ok(text(tree.toJSON()).includes('Synthetic ASR failure'));await renderer.act(async()=>tree.unmount());
});

function approvalUI(apply,storage=new Map()){
 const exports={},secure={getItemAsync:async key=>storage.get(key)||null,setItemAsync:async(k,v)=>storage.set(k,v),deleteItemAsync:async k=>storage.delete(k)},native={StyleSheet:{create:x=>x},...Object.fromEntries(['ActivityIndicator','Pressable','Text','TextInput','View'].map(x=>[x,x]))};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeVoiceApproval.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,Error,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{usePreventRemove(){}}:n==='expo-secure-store'?secure:n==='expo-crypto'?{randomUUID:()=> '00000000-0000-4000-8000-000000000001'}:n==='./socialDraft'?require('../src/socialDraft.ts'):n==='./NativeDateField'?{default:'NativeDateField'}:n==='./NativeTimeField'?{default:'NativeTimeField'}:n==='./programModel'?require('../src/programModel.ts'):{...require('../src/voiceApi.ts'),applyVoiceReview:apply}});return{Component:exports.default,storage};
}
const review={ok:true,revision:'a'.repeat(64),review:{fields:{chief_complaint:{value:'Synthetic approved complaint',quote:'Synthetic quote'},allergies:{value:'Unselected allergy',quote:'Synthetic quote'}},teeth:[{tooth:'36',status:'CARIES',quote:'Synthetic'}]}};
test('clinician approval selects explicit fields and retries exact persisted intent after uncertain response',async()=>{
 const calls=[],h=approvalUI(async(_token,_patient,payload)=>{calls.push(payload);if(calls.length===1)throw Object.assign(new Error('Uncertain write'),{status:503});return{ok:true,analysis_id:17}});let tree;const props={token:'A',userId:1,patientId:8,review,labels:{chief_complaint:'Şikâyet',allergies:'Alerji'}};
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,props)));assert.equal(button(tree,'Seçili Bilgileri Kaydet').props.disabled,true);
 const boxes=tree.root.findAllByType('Pressable').filter(n=>n.props.accessibilityRole==='checkbox');await renderer.act(async()=>{boxes[0].props.onPress();boxes.at(-1).props.onPress()});await renderer.act(async()=>button(tree,'Seçili Bilgileri Kaydet').props.onPress());assert.equal(calls.length,1);assert.deepEqual(Object.keys(calls[0].fields),['chief_complaint']);assert.equal(calls[0].teeth.length,0);await renderer.act(async()=>tree.unmount());
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{...props,review:{...review,revision:'b'.repeat(64)}})));await renderer.act(async()=>button(tree,'Bekleyen Kaydı Aynı Anahtarla Doğrula').props.onPress());assert.equal(calls[0].request_key,calls[1].request_key);assert.equal(calls[1].revision,'a'.repeat(64));assert.ok(text(tree.toJSON()).includes('#17'));assert.equal(h.storage.size,0);await renderer.act(async()=>tree.unmount());
});
test('secure voice text can survive restart beyond the default social draft chunk limit',async()=>{
 const {chunkedDraftStore}=require('../src/socialDraft.ts'),map=new Map(),raw={getItemAsync:async k=>map.get(k)||null,setItemAsync:async(k,v)=>map.set(k,v),deleteItemAsync:async k=>map.delete(k)},store=chunkedDraftStore(raw,()=> 'revision',300),value='Synthetic voice text '.repeat(3300);
 await store.setItemAsync('voice',value);assert.equal(await store.getItemAsync('voice'),value);assert.ok([...map.values()].every(v=>Buffer.byteLength(v,'utf8')<2048));await store.deleteItemAsync('voice');assert.equal(map.size,0);
});

test('restored voice text is not overwritten by an initially empty parent field',async()=>{
 const saved={version:1,userId:1,patientId:8,transcript:'Restored synthetic speech',segments:[],updatedAt:Date.now(),ended:true,elapsedMs:65000},h=recorderUI({saved:JSON.stringify(saved)}),values=[];let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:false,value:'',onTranscript:v=>values.push(v),onFinished(){}})));assert.equal(values.at(-1),'Restored synthetic speech');assert.ok(text(tree.toJSON()).includes('01:05'));assert.equal(button(tree,'Taslağı ve Yerel Sesleri Sil').props.disabled,false);await renderer.act(async()=>tree.unmount());
});
test('voice appointment is explicit and uses clinician-selected date and time',async()=>{
 const calls=[],h=approvalUI(async(_t,_p,payload)=>{calls.push(payload);return{ok:true,analysis_id:19}});let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,review:{...review,review:{fields:{},appointment:{quote:'Synthetic proposed appointment'}}},labels:{}})));
 const boxes=tree.root.findAllByType('Pressable').filter(n=>n.props.accessibilityRole==='checkbox');await renderer.act(async()=>boxes[0].props.onPress());await renderer.act(async()=>tree.root.findByType('NativeDateField').props.onChange('2030-01-08'));const confirmation=tree.root.findAllByType('Pressable').filter(n=>n.props.accessibilityRole==='checkbox').at(-1);await renderer.act(async()=>confirmation.props.onPress());await renderer.act(async()=>button(tree,'Seçili Bilgileri Kaydet').props.onPress());assert.equal(calls.length,1);assert.equal(calls[0].appointment.start_at,'2030-01-08T09:00');assert.equal(calls[0].appointment.end_at,'2030-01-08T09:30');await renderer.act(async()=>tree.unmount());
});

test('ASR failure during live chunk rotation stops the next microphone chunk',async()=>{
 const h=recorderUI({transcribe:async()=>{throw Error('Synthetic ASR outage')}});let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished(){}})));await renderer.act(async()=>button(tree,'Muayeneyi Başlat').props.onPress());await renderer.act(async()=>{h.timers[0]();await new Promise(r=>setImmediate(r))});assert.equal(h.calls.filter(x=>x==='record').length,2);assert.equal(h.calls.filter(x=>x==='stop').length,2);assert.equal(JSON.parse(h.store.get('draft')).segments.length,2);await renderer.act(async()=>tree.unmount());
});

test('exam entry never performs clinical extraction during live transcription',async()=>{
 const exports={},calls=[],native={StyleSheet:{create:x=>x},Alert:{alert(){}},...Object.fromEntries(['ActivityIndicator','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/VoiceExamEntry.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const secure=new Map();vm.runInNewContext(code,{exports,Error,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{usePreventRemove(){}}:n==='expo-secure-store'?{getItemAsync:async key=>secure.get(key)||null,setItemAsync:async(key,value)=>secure.set(key,value),deleteItemAsync:async key=>secure.delete(key)}:n==='expo-crypto'?{randomUUID:()=> 'voice-checkpoint',CryptoDigestAlgorithm:{SHA256:'SHA-256'},digestStringAsync:async(_algorithm,value)=>'a'.repeat(64)}:n==='./socialDraft'?require('../src/socialDraft.ts'):n==='./voiceSession'?require('../src/voiceSession.ts'):n==='./api'?{getPatient:async()=>({patient:{id:8,anonymous_id:'Synthetic patient'}})}:n==='./voiceApi'?{extractVoice:async(...args)=>{calls.push(args);return review}}:{default:n.slice(2)}});let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(exports.default,{token:'A',userId:1,initialPatientId:8})));await renderer.act(async()=>button(tree,'Muayeneye Devam Et').props.onPress());await renderer.act(async()=>tree.root.findAllByType('Pressable').find(x=>x.props.accessibilityRole==='checkbox').props.onPress());
 await renderer.act(async()=>{tree.root.findByType('NativeVoiceRecorder').props.onSessionState({started:true,finished:false});tree.root.findByType('NativeVoiceRecorder').props.onTranscript('Synthetic speech')});assert.equal(calls.length,0);assert.equal(button(tree,'Muayeneyi Bitir ve Metni Çözümle').props.disabled,true);
 await renderer.act(async()=>tree.root.findByType('NativeVoiceRecorder').props.onFinished('Synthetic speech'));assert.equal(calls.length,1);assert.equal(calls[0][2],'Synthetic speech');await renderer.act(async()=>tree.unmount());
});

test('native audio timeout rejects even if the platform upload never settles',async()=>{
 const exports={};let expire,cancelled=0;const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/nativeVoiceAudio.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 vm.runInNewContext(code,{exports,Error,setTimeout:fn=>{expire=fn;return 1},clearTimeout(){},require:n=>n==='expo-file-system/legacy'?{getInfoAsync:async()=>({exists:true,size:1024}),FileSystemUploadType:{BINARY_CONTENT:0},createUploadTask:()=>({uploadAsync:()=>new Promise(()=>{}),cancelAsync:async()=>{cancelled++}})}:n==='./api'?{ApiError:class extends Error{constructor(status,message){super(message);this.status=status}}}:{revalidateSession:async()=>{}}});const result=exports.transcribeNativeRecording('A',8,'file:///cache/record.m4a');await new Promise(r=>setImmediate(r));expire();await assert.rejects(result,/yerel kayıt/);assert.equal(cancelled,1);
});
test('unreadable approval intent blocks a new clinical write',async()=>{
 const map=new Map([['dai.voice.apply.1.8','not valid JSON']]),h=approvalUI(async()=>{throw Error('must not send')},map);let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,review,labels:{}})));assert.equal(button(tree,'Seçili Bilgileri Kaydet').props.disabled,true);assert.ok(text(tree.toJSON()).includes('Hasta geçmişini kontrol edin'));await renderer.act(async()=>tree.unmount());
});

test('leaving the focused screen stops microphone and retains the pending clip',async()=>{
 const calls=[],h=recorderUI({transcribe:async()=>{calls.push('ASR');return{transcript:'Synthetic',revision:'r'}}});const props={token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished(){}};let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,props)));await renderer.act(async()=>button(tree,'Muayeneyi Başlat').props.onPress());await renderer.act(async()=>{h.focus(false);tree.update(React.createElement(h.Component,props));await new Promise(r=>setImmediate(r))});assert.equal(h.calls.filter(x=>x==='stop').length,1);assert.equal(calls.length,0);assert.equal(JSON.parse(h.store.get('draft')).segments.length,1);await renderer.act(async()=>tree.unmount());
});


test('voice entry mirrors the web new-patient path and reuses its key after an uncertain response',async()=>{
 const exports={},calls=[],secure=new Map();
 const native={StyleSheet:{create:x=>x},Alert:{alert(){}},Linking:{openURL:async()=>{}},...Object.fromEntries(['ActivityIndicator','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/VoiceExamEntry.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,Error,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{usePreventRemove(){}}:n==='expo-secure-store'?{getItemAsync:async key=>secure.get(key)||null,setItemAsync:async(key,value)=>secure.set(key,value),deleteItemAsync:async key=>secure.delete(key)}:n==='expo-crypto'?{randomUUID:()=> '00000000-0000-4000-8000-000000000000'}:n==='./api'?{getPatient:async()=>({patient:{id:8,anonymous_id:'Synthetic patient'}})}:n==='./voiceApi'?{createAnonymousVoicePatient:async(token,key)=>{calls.push({token,key});if(calls.length===1)throw Error('Synthetic lost response');return{patient:{id:42,anonymous_id:'SES-0123456789ABCDEF',first_name:null,last_name:null}}},extractVoice:async()=>review,finalizeVoice:async()=>({final:{}})}:{default:n.slice(2)}});
 let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(exports.default,{token:'A',userId:1})));
 assert.ok(button(tree,'Yeni hastayla başla →'));
 await renderer.act(async()=>{button(tree,'Yeni hastayla başla →').props.onPress();await new Promise(resolve=>setImmediate(resolve))});
 const storedKey=secure.get('dai.voice.patient.create.1');
 assert.equal(storedKey,'0'.repeat(32));assert.equal(calls.length,1);
 await renderer.act(async()=>{button(tree,'Yeni hastayla başla →').props.onPress();await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(calls.length,2);assert.equal(calls[0].key,calls[1].key);
 assert.equal(secure.has('dai.voice.patient.create.1'),false);
 assert.equal(tree.root.findAllByType('NativeVoiceRecorder').length,1);
 assert.ok(text(tree.toJSON()).includes('SES-0123456789ABCDEF'));
 await renderer.act(async()=>tree.unmount());
});

test('native voice transcript matches the web 72k/216KB chunk contract without splitting Unicode',()=>{
 const api=require('../src/voiceSession.ts'),web=require('../../app/static/voice-finish-draft.js'),source=('Çürük 36 yüzeyinde ağrı 🦷. Hasta bugün geldi.\\n').repeat(1400);
 const chunks=api.splitVoiceTranscript(source);assert.deepEqual(chunks,web.splitTranscript(source));
 assert.ok(chunks.length>1);assert.equal(chunks.join(''),source);
 for(const chunk of chunks){assert.ok(chunk.length<=12000);assert.ok(api.voiceUtf8Bytes(chunk)<=36000);assert.ok(!/[\\uD800-\\uDBFF]$/.test(chunk));}
 assert.equal(api.voiceUtf8Bytes('🦷'),4);
 const draft={...api.newVoiceDraft(1,8),segments:[{id:'long',uri:'file:///cache/long.m4a',ready:true}]};
 const appended=api.appendVoiceSegment(draft,'long','a'.repeat(19000));assert.equal(appended.transcript.length,19000);
 const full={...draft,transcript:'a'.repeat(72000)};
 assert.throws(()=>api.appendVoiceSegment(full,'long','b'),/72.000/);
 const cjk='漢'.repeat(72000),webDraft=new web.FinishDraft();assert.equal(api.voiceUtf8Bytes(cjk),216000);assert.equal(api.splitVoiceTranscript(cjk).join(''),cjk);webDraft.set(cjk);assert.deepEqual(api.splitVoiceTranscript(cjk),web.splitTranscript(cjk));assert.throws(()=>api.splitVoiceTranscript('ç'.repeat(72001)),/72.000/);
});

test('voice extraction checkpoint is scoped to account, patient, transcript and expiry',()=>{
 const api=require('../src/voiceSession.ts'),hash='a'.repeat(64),checkpoint={version:1,userId:1,patientId:8,transcriptHash:hash,cursor:2,revision:'b'.repeat(64),review:{fields:{}},updatedAt:100000},raw=JSON.stringify(checkpoint);
 assert.deepEqual(api.parseVoiceExtractionCheckpoint(raw,1,8,hash,3,100001),checkpoint);
 assert.equal(api.parseVoiceExtractionCheckpoint(raw,2,8,hash,3,100001),null);
 assert.equal(api.parseVoiceExtractionCheckpoint(raw,1,9,hash,3,100001),null);
 assert.equal(api.parseVoiceExtractionCheckpoint(raw,1,8,'c'.repeat(64),3,100001),null);
 assert.equal(api.parseVoiceExtractionCheckpoint(raw,1,8,hash,3,100000+86400001),null);
});

test('native extraction processes web-sized chunks sequentially and resumes after the last saved chunk',async()=>{
 const exports={},calls=[],revision='a'.repeat(64),code=ts.transpileModule(fs.readFileSync(require.resolve('../src/voiceApi.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 const fakeFetch=async(url,init)=>{
  const body=JSON.parse(init.body);calls.push({url,body});
  const prior=body.context?.fields?.chief_complaint?.value||'';
  const value=prior?(prior+' | part'+calls.length):'part'+calls.length;
  const payload={ok:true,revision,review:{fields:{chief_complaint:{value,quote:'evidence '+calls.length}},teeth:[],communication:[{category:'PATIENT_RESPONSE',quote:'communication '+calls.length,observation:'observation '+calls.length,suggestion:'suggestion'}],decision_barriers:[{category:'COST',quote:'barrier '+calls.length,observation:'barrier observation'}],follow_up_questions:[{quote:'same quote',question:'same question',reason:'reason',priority:'CLARIFY_NOW',resolved:false}],uncertain:'uncertain '+calls.length,literature_topics:[],source_requests:[]}};
  return{status:200,ok:true,text:async()=>JSON.stringify(payload)};
 };
 vm.runInNewContext(code,{exports,fetch:fakeFetch,setTimeout,clearTimeout,AbortController,Error,require:n=>n==='./sessionExpiry'?{revalidateSession:async()=>{}}:n==='./voiceSession'?require('../src/voiceSession.ts'):{}});
 const transcript='a'.repeat(25000);let saved;
 await assert.rejects(exports.extractVoice('token',8,transcript,{onCheckpoint:async value=>{saved=value;if(value.cursor===1)throw Error('Synthetic interruption')}}),/Synthetic interruption/);
 assert.equal(calls.length,1);assert.equal(saved.cursor,1);saved.review.follow_up_questions[0].resolved=true;
 const result=await exports.extractVoice('token',8,transcript,{resume:saved,onCheckpoint:async value=>{saved=value}});
 assert.equal(calls.length,3);assert.equal(calls[1].body.context.fields.chief_complaint.value,'part1');
 assert.equal(result.review.fields.chief_complaint.value,'part1 | part2 | part3');assert.equal(saved.cursor,3);
 assert.equal(result.review.communication.length,3);assert.equal(result.review.decision_barriers.length,3);assert.equal(result.review.follow_up_questions.length,1);assert.equal(result.review.follow_up_questions[0].resolved,true);assert.equal(result.review.uncertainties.length,3);
});

test('native extraction refuses to merge chunks across a patient revision change',async()=>{
 const exports={},calls=[],first='a'.repeat(64),changed='b'.repeat(64),code=ts.transpileModule(fs.readFileSync(require.resolve('../src/voiceApi.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 const fakeFetch=async(_url,init)=>{const body=JSON.parse(init.body);calls.push(body);const payload={ok:true,revision:calls.length===1?first:changed,review:{fields:{chief_complaint:{value:'Synthetic complaint '+calls.length,quote:'Synthetic evidence'}},teeth:[],communication:[],decision_barriers:[],follow_up_questions:[],literature_topics:[],source_requests:[]}};return{status:200,ok:true,text:async()=>JSON.stringify(payload)}};
 vm.runInNewContext(code,{exports,fetch:fakeFetch,setTimeout,clearTimeout,AbortController,Error,require:n=>n==='./sessionExpiry'?{revalidateSession:async()=>{}}:n==='./voiceSession'?require('../src/voiceSession.ts'):{}});
 let checkpoint;await assert.rejects(exports.extractVoice('token',8,'a'.repeat(25000),{onCheckpoint:async value=>{checkpoint=value}}),/Hasta dosyası görüşme sırasında değişti/);
 assert.equal(calls.length,2);assert.equal(checkpoint.cursor,1);assert.equal(checkpoint.revision,first);
});

test('voice entry deletes a stale secure extraction checkpoint before retry after patient revision conflict',async()=>{
 const exports={},secure=new Map(),calls=[],native={StyleSheet:{create:x=>x},Alert:{alert(){}},Linking:{openURL:async()=>{}},...Object.fromEntries(['ActivityIndicator','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/VoiceExamEntry.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,Error,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{usePreventRemove(){}}:n==='expo-secure-store'?{getItemAsync:async key=>secure.get(key)||null,setItemAsync:async(key,value)=>secure.set(key,value),deleteItemAsync:async key=>secure.delete(key)}:n==='expo-crypto'?{randomUUID:()=> 'checkpoint-id',CryptoDigestAlgorithm:{SHA256:'SHA-256'},digestStringAsync:async()=> 'a'.repeat(64)}:n==='./socialDraft'?require('../src/socialDraft.ts'):n==='./voiceSession'?require('../src/voiceSession.ts'):n==='./api'?{getPatient:async()=>({patient:{id:8,anonymous_id:'Synthetic patient'}})}:n==='./voiceApi'?{extractVoice:async(...args)=>{calls.push(args);if(calls.length===1){await args[3].onCheckpoint({cursor:1,revision:'b'.repeat(64),review:{fields:{}}});throw Error('Hasta dosyası görüşme sırasında değişti.')}assert.equal(args[3].resume,undefined);return review}}:{default:n.slice(2)}});
 let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(exports.default,{token:'A',userId:1,initialPatientId:8})));
 await renderer.act(async()=>{await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>button(tree,'Muayeneye Devam Et').props.onPress());
 await renderer.act(async()=>tree.root.findAllByType('Pressable').find(x=>x.props.accessibilityRole==='checkbox').props.onPress());
 const recorder=tree.root.findByType('NativeVoiceRecorder');
 await renderer.act(async()=>{recorder.props.onTranscript('Synthetic speech');recorder.props.onFinished('Synthetic speech');await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(calls.length,1);assert.ok(secure.has('dai.voice.extraction.1.8'));
 await renderer.act(async()=>button(tree,'Muayeneyi Bitir ve Metni Çözümle').props.onPress());
 assert.equal(calls.length,2);assert.equal(calls[1][3].resume,undefined);assert.equal(secure.has('dai.voice.extraction.1.8'),false);
 await renderer.act(async()=>tree.unmount());
});
