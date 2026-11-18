const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const text=n=>typeof n==='string'?n:!n?'':(n.children||[]).map(text).join('');
const button=(t,label)=>t.root.findAllByType('Pressable').find(n=>n.findAllByType('Text').some(c=>text(c)===label));

const recorderLifecycle=require('../src/voiceRecorderLifecycle.ts');
test('native voice recorder distinguishes normal chunk rotation from an unexpected microphone stop',()=>{
 assert.equal(recorderLifecycle.isUnexpectedVoiceRecorderStop(true,true,true,true),false,'a stop owned by rotation is expected');
 assert.equal(recorderLifecycle.isUnexpectedVoiceRecorderStop(true,true,true,false),true,'a stop outside rotation must pause the session');
 assert.equal(recorderLifecycle.isUnexpectedVoiceRecorderStop(true,false,true,false),false,'a clinician pause is not an interruption');
 assert.equal(recorderLifecycle.isUnexpectedVoiceRecorderStop(true,true,false,false),false,'a stale status without an active segment is ignored');
 const source=fs.readFileSync(require.resolve('../src/NativeVoiceRecorder.tsx'),'utf8');
 assert.match(source,/wasRecording\.current=false;\s*if\(!stopped\.current\)\{await recorder\.stop\(\)/,'rotation clears the previous recorder marker before Expo Audio publishes the stop');
 assert.match(source,/isUnexpectedVoiceRecorderStop\(wasRecording\.current,wanted\.current,Boolean\(active\.current\),gate\.current\)/);
});

test('voice draft is account-patient bound, expires, and appends each segment only once',()=>{
 const api=require('../src/voiceSession.ts'),draft={...api.newVoiceDraft(1,8,1000),segments:[{id:'s1',uri:'file:///cache/audio.m4a',ready:true}]};
 assert.throws(()=>api.parseVoiceDraft(JSON.stringify(draft),2,8,2000),/hesabı/);assert.equal(api.parseVoiceDraft(JSON.stringify(draft),1,8,1000+86400001),null);
 const next=api.appendVoiceSegment(draft,'s1','Synthetic transcript');assert.equal(next.transcript,'Synthetic transcript');assert.equal(next.segments.length,0);assert.equal(api.appendVoiceSegment(next,'s1','Duplicate').transcript,'Synthetic transcript');
 const receipt=api.markVoiceSegmentTranscribed(draft,'s1','Synthetic transcript');assert.equal(receipt.transcript,'Synthetic transcript');assert.equal(receipt.segments[0].transcribed,true);assert.equal(receipt.segments[0].ready,false);assert.equal(api.markVoiceSegmentTranscribed(receipt,'s1','Duplicate').transcript,'Synthetic transcript');assert.throws(()=>api.removeVoiceSegment(draft,'s1'),/Yazıya çevrilmemiş/);const cleaned=api.removeVoiceSegment(receipt,'s1');assert.equal(cleaned.segments.length,0);assert.equal(api.removeVoiceSegment(cleaned,'s1').segments.length,0);assert.equal(api.parseVoiceDraft(JSON.stringify(receipt),1,8,2000).segments[0].transcribed,true);assert.throws(()=>api.parseVoiceDraft(JSON.stringify({...receipt,segments:[{...receipt.segments[0],ready:true}]}),1,8,2000),/içeriği/);
 let timed=api.addVoiceElapsed(api.newVoiceDraft(1,8,1000),1000,16000);timed=api.addVoiceElapsed(timed,30000,38000);assert.equal(timed.elapsedMs,23000);assert.equal(api.formatVoiceElapsed(timed.elapsedMs),'00:23');assert.equal(api.parseVoiceDraft(JSON.stringify(timed),1,8,38000).elapsedMs,23000);
 const legacy={...timed};delete legacy.elapsedMs;assert.equal(api.parseVoiceDraft(JSON.stringify(legacy),1,8,38000).elapsedMs,0);assert.equal(api.formatVoiceElapsed(65000),'01:05');assert.throws(()=>api.addVoiceElapsed(timed,200,100),/süresi/);assert.throws(()=>api.parseVoiceDraft(JSON.stringify({...timed,elapsedMs:-1}),1,8,38000),/içeriği/);
});
test('native audio transport sends binary recording with consent and validates receipt',async()=>{
 const exports={},calls=[];const source=ts.transpileModule(fs.readFileSync(require.resolve('../src/nativeVoiceAudio.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const filesystem={getInfoAsync:async()=>({exists:true,size:1024}),FileSystemUploadType:{BINARY_CONTENT:0},createUploadTask:(...args)=>{calls.push(args);return{uploadAsync:async()=>({status:200,body:JSON.stringify({ok:true,revision:'revision',transcript:'Synthetic speech'})}),cancelAsync:async()=>{}}}};
 vm.runInNewContext(source,{exports,setTimeout,clearTimeout,require:n=>n==='expo-file-system/legacy'?filesystem:n==='./api'?{ApiError:class extends Error{constructor(status,message){super(message);this.status=status}}}:{revalidateSession:async()=>{}}});
 const result=await exports.transcribeNativeRecording('token',8,'file:///cache/audio.m4a','voice-workflow-audio-00000001');assert.equal(result.transcript,'Synthetic speech');assert.equal(calls[0][2].headers['X-Voice-Consent'],'yes');assert.equal(calls[0][2].headers['Content-Type'],'audio/mp4');assert.equal(calls[0][2].headers.Cookie,'');assert.equal(calls[0][2].uploadType,0);
});

test('voice transcript segments use real line breaks for display and chunk boundaries',()=>{
 const api=require('../src/voiceSession.ts');
 const base={...api.newVoiceDraft(1,8,1000),transcript:'Önceki bölüm',segments:[{id:'segment-1',uri:'file:///cache/segment-1.m4a',ready:true}]};
 const appended=api.appendVoiceSegment(base,'segment-1','Yeni bölüm');
 assert.equal(appended.transcript,'Önceki bölüm\nYeni bölüm');
 assert.equal(appended.transcript.includes('\\n'),false);
 const receipt=api.markVoiceSegmentTranscribed(base,'segment-1','Yeni bölüm');
 assert.equal(receipt.transcript,'Önceki bölüm\nYeni bölüm');
 assert.equal(receipt.transcript.includes('\\n'),false);
 const chunks=api.splitVoiceTranscript('a'.repeat(7000)+'\n'+'b'.repeat(7000));
 assert.equal(chunks[0],'a'.repeat(7000)+'\n');
 assert.equal(chunks[1],'b'.repeat(7000));
});


test('interrupted recovery enforces the native audio byte range and preserves transcript',()=>{
 const api=require('../src/voiceSession.ts');
 const draft={...api.newVoiceDraft(1,8,1000),transcript:'Önceki metin',segments:[{id:'bounded',uri:'file:///cache/bounded.m4a',ready:false}]};
 const tooSmall=api.recoverInterruptedVoiceSegment(draft,'bounded',{exists:true,size:99});
 assert.equal(tooSmall.segments[0].ready,false);
 const tooLarge=api.recoverInterruptedVoiceSegment(draft,'bounded',{exists:true,size:8*1024*1024+1});
 assert.equal(tooLarge.segments[0].ready,false);
 const valid=api.recoverInterruptedVoiceSegment(draft,'bounded',{exists:true,size:100});
 assert.equal(valid.segments[0].ready,true);
 const missing=api.recoverInterruptedVoiceSegment(draft,'bounded',{exists:false});
 assert.equal(missing.segments.length,0);
 assert.equal(missing.transcript,'Önceki metin');
 assert.throws(()=>api.discardInterruptedVoiceSegment(valid,'bounded'),/Tamamlanmış/);
});

function recorderUI({saved=null,transcribe=async()=>({transcript:'Synthetic dictated speech',revision:'r'}),stopFailures=0,stopFailureStopsRecorder=false,stopGate=null,permissionGate=null,restoredFileInfo={exists:true,size:1024}}={}){
 const exports={},store=new Map(),calls=[],timers=[],files=new Map(),state={isRecording:false,durationMillis:0,mediaServicesDidReset:false};
 if(saved){try{for(const segment of JSON.parse(saved).segments||[])files.set(segment.uri,{...restoredFileInfo})}catch{}}
 let audioUri='file:///cache/record-0.m4a',stopFailuresRemaining=stopFailures;
 const audio={get uri(){return audioUri},prepareToRecordAsync:async options=>{if(!options?.extension)throw Error('iOS segment preparation must receive fresh recording options');const index=calls.filter(value=>value==='prepare').length+1;audioUri='file:///cache/record-'+index+'.m4a';files.set(audioUri,{exists:true,size:1024});calls.push('prepare')},record(){state.isRecording=true;calls.push('record')},stop:async()=>{calls.push('stop');if(stopGate)await stopGate();if(stopFailuresRemaining>0){stopFailuresRemaining--;if(stopFailureStopsRecorder)state.isRecording=false;throw Error('Synthetic stop failure')}state.isRecording=false}};
 let focused=true,clockNow=Date.now(),nextInterval=0,appStateListener=null;const intervals=new Map(),appState={currentState:'active',addEventListener:(event,listener)=>{appStateListener=listener;return{remove(){if(appStateListener===listener)appStateListener=null}}}};
 const secure={getItemAsync:async key=>store.get(key)||null,setItemAsync:async(k,v)=>store.set(k,v),deleteItemAsync:async k=>store.delete(k)};
 const native={StyleSheet:{create:x=>x},Alert:{alert(){}},AppState:appState,...Object.fromEntries(['ActivityIndicator','Pressable','Text','TextInput','View'].map(x=>[x,x]))};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeVoiceRecorder.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,Date:{now:()=>clockNow},setInterval:fn=>{const id=++nextInterval;intervals.set(id,fn);return id},clearInterval:id=>intervals.delete(id),setTimeout:(fn,ms)=>ms===15000?(timers.push(fn),timers.length):setTimeout(fn,ms),clearTimeout:id=>{if(typeof id!=='number')clearTimeout(id)},AbortController,Error,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='expo-audio'?{useAudioRecorder:()=>audio,useAudioRecorderState:()=>state,RecordingPresets:{HIGH_QUALITY:{extension:'.m4a',android:{outputFormat:'mpeg4',audioEncoder:'aac'},ios:{}}},requestRecordingPermissionsAsync:async()=>{if(permissionGate)await permissionGate();return{granted:true}},setAudioModeAsync:async()=>{}}:n==='expo-file-system/legacy'?{cacheDirectory:'file:///cache/',deleteAsync:async uri=>files.set(uri,{exists:false,size:0}),getInfoAsync:async uri=>files.get(uri)||{exists:false,size:0}}:n==='expo-secure-store'?secure:n==='expo-crypto'?{randomUUID:()=>String(calls.length)+'-synthetic'}:n==='@react-navigation/native'?{useIsFocused:()=>focused,usePreventRemove(){}}:n==='./socialDraft'?{chunkedDraftStore:()=>({getItemAsync:async()=>saved,setItemAsync:async(_k,v)=>{store.set('draft',v)},deleteItemAsync:async()=>{}})}:n==='./voiceSession'?require('../src/voiceSession.ts'):{transcribeNativeRecording:transcribe}});
 return{Component:exports.default,calls,store,timers,files,focus:value=>{focused=value},background:()=>{appState.currentState='background';appStateListener?.('background')},foreground:()=>{appState.currentState='active';appStateListener?.('active')},advance:ms=>{clockNow+=ms;for(const fn of intervals.values())fn()}};
}
test('native microphone pauses/resumes and only finishes clinical handoff after ASR',async()=>{
 const h=recorderUI(),transcripts=[],finished=[];let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript:v=>transcripts.push(v),onFinished:v=>finished.push(v)})));
 await renderer.act(async()=>button(tree,'Mikrofonu başlat').props.onPress());assert.ok(h.calls.includes('record'));assert.equal(finished.length,0);
 await renderer.act(async()=>button(tree,'Ⅱ  Duraklat').props.onPress());assert.ok(h.calls.includes('stop'));assert.equal(finished.length,0);assert.equal(transcripts.at(-1),'Synthetic dictated speech');
 await renderer.act(async()=>button(tree,'▶  Devam et').props.onPress());assert.equal(h.calls.filter(x=>x==='record').length,2);await renderer.act(async()=>button(tree,'Muayeneyi bitir').props.onPress());assert.equal(finished.length,1);assert.ok(finished[0].includes('Synthetic dictated speech'));await renderer.act(async()=>tree.unmount());
});
test('native microphone elapsed time accumulates across recording chunks and pauses',async()=>{
 const h=recorderUI(),finished=[];let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished:v=>finished.push(v)})));
 await renderer.act(async()=>button(tree,'Mikrofonu başlat').props.onPress());await renderer.act(async()=>h.advance(4200));await renderer.act(async()=>button(tree,'Ⅱ  Duraklat').props.onPress());assert.equal(JSON.parse(h.store.get('draft')).elapsedMs,4200);assert.ok(text(tree.toJSON()).includes('00:04'));
 await renderer.act(async()=>button(tree,'▶  Devam et').props.onPress());await renderer.act(async()=>h.advance(2300));await renderer.act(async()=>button(tree,'Muayeneyi bitir').props.onPress());assert.equal(JSON.parse(h.store.get('draft')).elapsedMs,6500);assert.ok(text(tree.toJSON()).includes('00:06'));assert.equal(finished.length,1);await renderer.act(async()=>tree.unmount());
});

test('pending ASR failure retains recording and never triggers clinical handoff',async()=>{
 const h=recorderUI({transcribe:async()=>{throw Error('Synthetic ASR failure')}}),finished=[];let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished:v=>finished.push(v)})));await renderer.act(async()=>button(tree,'Mikrofonu başlat').props.onPress());await renderer.act(async()=>button(tree,'Muayeneyi bitir').props.onPress());assert.equal(finished.length,0);assert.equal(JSON.parse(h.store.get('draft')).segments.length,1);assert.ok(text(tree.toJSON()).includes('Synthetic ASR failure'));await renderer.act(async()=>tree.unmount());
});


test('backgrounding aborts a pending native ASR upload and replays the same receipt key on resume',async()=>{
 const saved=JSON.stringify({version:1,userId:1,patientId:8,transcript:'Önceki metin',segments:[{id:'stable-background-segment',uri:'file:///cache/background.m4a',ready:true}],updatedAt:Date.now(),ended:false,audioStarted:true,elapsedMs:12000});
 const calls=[],signals=[],finished=[];
 const h=recorderUI({saved,transcribe:async(...args)=>{
  calls.push(args);signals.push(args[4]);
  if(calls.length===1)return await new Promise((resolve,reject)=>args[4].addEventListener('abort',()=>{const error=new Error('Aborted by background');error.name='AbortError';reject(error)},{once:true}));
  return{transcript:'Arka plan sonrası güvenli tekrar',revision:'r'};
 }});
 let tree;const props={token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished:value=>finished.push(value)};
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,props)));
 await renderer.act(async()=>new Promise(resolve=>setImmediate(resolve)));
 await renderer.act(async()=>{button(tree,'Bekleyen sesleri yazıya çevir').props.onPress();await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(calls.length,1);
 await renderer.act(async()=>{h.background();await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(signals[0].aborted,true);
 let draft=JSON.parse(h.store.get('draft'));
 assert.equal(draft.segments[0].id,'stable-background-segment');
 assert.equal(draft.transcript,'Önceki metin');
 assert.equal(finished.length,0);
 await renderer.act(async()=>{h.foreground();await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>{button(tree,'Bekleyen sesleri yazıya çevir').props.onPress();await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(calls.length,2);
 assert.equal(calls[0][3],'stable-background-segment');
 assert.equal(calls[1][3],'stable-background-segment');
 draft=JSON.parse(h.store.get('draft'));
 assert.equal(draft.segments.length,0);
 assert.equal(draft.transcript,'Önceki metin\nArka plan sonrası güvenli tekrar');
 assert.equal(finished.length,0);
 await renderer.act(async()=>tree.unmount());
});


test('leaving the native voice screen aborts a paused-session ASR upload without losing its key',async()=>{
 const saved=JSON.stringify({version:1,userId:1,patientId:8,transcript:'Önceki bölüm',segments:[{id:'stable-blur-segment',uri:'file:///cache/blur.m4a',ready:true}],updatedAt:Date.now(),ended:false,audioStarted:true,elapsedMs:18000});
 const calls=[],signals=[];
 const h=recorderUI({saved,transcribe:async(...args)=>{
  calls.push(args);signals.push(args[4]);
  if(calls.length===1)return await new Promise((resolve,reject)=>args[4].addEventListener('abort',()=>{const error=new Error('Aborted on blur');error.name='AbortError';reject(error)},{once:true}));
  return{transcript:'Ekrana dönünce tamamlandı',revision:'r'};
 }});
 let tree;const props={token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished(){}};
 const element=React.createElement(h.Component,props);
 await renderer.act(async()=>tree=renderer.create(element));
 await renderer.act(async()=>new Promise(resolve=>setImmediate(resolve)));
 await renderer.act(async()=>{button(tree,'Bekleyen sesleri yazıya çevir').props.onPress();await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(calls.length,1);
 await renderer.act(async()=>{h.focus(false);tree.update(element);await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(signals[0].aborted,true);
 let draft=JSON.parse(h.store.get('draft'));
 assert.equal(draft.segments[0].id,'stable-blur-segment');
 assert.equal(draft.transcript,'Önceki bölüm');
 await renderer.act(async()=>{h.focus(true);tree.update(element);await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>{button(tree,'Bekleyen sesleri yazıya çevir').props.onPress();await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(calls.length,2);
 assert.equal(calls[0][3],'stable-blur-segment');
 assert.equal(calls[1][3],'stable-blur-segment');
 draft=JSON.parse(h.store.get('draft'));
 assert.equal(draft.segments.length,0);
 assert.equal(draft.transcript,'Önceki bölüm\nEkrana dönünce tamamlandı');
 await renderer.act(async()=>tree.unmount());
});

test('native recorder stops and keeps its local segment when consent is unchecked',async()=>{const calls=[],h=recorderUI({transcribe:async()=>{calls.push('upload');return{transcript:'not expected',revision:'r'}}}),props={token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished(){}};let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,props)));await renderer.act(async()=>button(tree,'Mikrofonu başlat').props.onPress());await renderer.act(async()=>tree.update(React.createElement(h.Component,{...props,consent:false})));await renderer.act(async()=>new Promise(resolve=>setImmediate(resolve)));const draft=JSON.parse(h.store.get('draft'));assert.equal(h.calls.filter(x=>x==='stop').length,1);assert.equal(calls.length,0);assert.equal(draft.segments.length,1);assert.equal(draft.segments[0].ready,true);await renderer.act(async()=>tree.unmount());});

test('native consent withdrawal aborts an in-flight upload and keeps the same local segment',async()=>{const saved=JSON.stringify({version:1,userId:1,patientId:8,transcript:'Önceki metin',segments:[{id:'same-local-segment',uri:'file:///cache/same-local-segment.m4a',ready:true}],updatedAt:Date.now(),ended:false,audioStarted:true,elapsedMs:15000}),signals=[],h=recorderUI({saved,transcribe:async(...args)=>{signals.push(args[4]);return await new Promise((resolve,reject)=>args[4].addEventListener('abort',()=>{const e=new Error('aborted');e.name='AbortError';reject(e)},{once:true}))}}),props={token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished(){}};let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,props)));await renderer.act(async()=>new Promise(resolve=>setImmediate(resolve)));await renderer.act(async()=>{button(tree,'Bekleyen sesleri yazıya çevir').props.onPress();await new Promise(resolve=>setImmediate(resolve))});assert.equal(signals.length,1);await renderer.act(async()=>tree.update(React.createElement(h.Component,{...props,consent:false})));await renderer.act(async()=>new Promise(resolve=>setImmediate(resolve)));assert.equal(signals[0].aborted,true);assert.equal(JSON.parse(h.store.get('draft')).segments[0].id,'same-local-segment');await renderer.act(async()=>tree.unmount());});

test('native opt-out during finish cut prevents the queued ASR drain',async()=>{let releaseStop;const calls=[],finished=[],h=recorderUI({stopGate:()=>new Promise(resolve=>{releaseStop=resolve}),transcribe:async()=>{calls.push('ASR');return{transcript:'not sent',revision:'r'}}}),props={token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished:value=>finished.push(value)};let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,props)));await renderer.act(async()=>button(tree,'Mikrofonu başlat').props.onPress());await renderer.act(async()=>{button(tree,'Muayeneyi bitir').props.onPress();await new Promise(resolve=>setImmediate(resolve))});assert.equal(typeof releaseStop,'function');await renderer.act(async()=>tree.update(React.createElement(h.Component,{...props,consent:false})));releaseStop();await renderer.act(async()=>new Promise(resolve=>setImmediate(resolve)));const draft=JSON.parse(h.store.get('draft'));assert.equal(calls.length,0);assert.equal(draft.segments[0].ready,true);assert.equal(finished.length,0);await renderer.act(async()=>tree.unmount());});

test('native consent withdrawal while permission is pending never starts the microphone',async()=>{let releasePermission;const h=recorderUI({permissionGate:()=>new Promise(resolve=>{releasePermission=resolve})}),props={token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished(){}};let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,props)));await renderer.act(async()=>{button(tree,'Mikrofonu başlat').props.onPress();await new Promise(resolve=>setImmediate(resolve))});assert.equal(typeof releasePermission,'function');await renderer.act(async()=>tree.update(React.createElement(h.Component,{...props,consent:false})));releasePermission();await renderer.act(async()=>new Promise(resolve=>setImmediate(resolve)));assert.equal(h.calls.filter(x=>x==='prepare').length,0);assert.equal(h.calls.filter(x=>x==='record').length,0);assert.equal(JSON.parse(h.store.get('draft')).segments.length,0);await renderer.act(async()=>tree.unmount());});

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
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:false,value:'',onTranscript:v=>values.push(v),onFinished(){}})));assert.equal(values.at(-1),'Restored synthetic speech');assert.ok(text(tree.toJSON()).includes('01:05'));assert.equal(button(tree,'Taslağı ve yerel sesleri sil').props.disabled,false);await renderer.act(async()=>tree.unmount());
});
test('voice appointment is explicit and uses clinician-selected date and time',async()=>{
 const calls=[],h=approvalUI(async(_t,_p,payload)=>{calls.push(payload);return{ok:true,analysis_id:19}});let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,review:{...review,review:{fields:{},appointment:{quote:'Synthetic proposed appointment'}}},labels:{}})));
 const boxes=tree.root.findAllByType('Pressable').filter(n=>n.props.accessibilityRole==='checkbox');await renderer.act(async()=>boxes[0].props.onPress());await renderer.act(async()=>tree.root.findByType('NativeDateField').props.onChange('2030-01-08'));const confirmation=tree.root.findAllByType('Pressable').filter(n=>n.props.accessibilityRole==='checkbox').at(-1);await renderer.act(async()=>confirmation.props.onPress());await renderer.act(async()=>button(tree,'Seçili Bilgileri Kaydet').props.onPress());assert.equal(calls.length,1);assert.equal(calls[0].appointment.start_at,'2030-01-08T09:00');assert.equal(calls[0].appointment.end_at,'2030-01-08T09:30');await renderer.act(async()=>tree.unmount());
});

test('ASR failure during live chunk rotation stops the next microphone chunk',async()=>{
 const h=recorderUI({transcribe:async()=>{throw Error('Synthetic ASR outage')}});let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished(){}})));await renderer.act(async()=>button(tree,'Mikrofonu başlat').props.onPress());await renderer.act(async()=>{h.timers[0]();await new Promise(r=>setImmediate(r))});assert.equal(h.calls.filter(x=>x==='record').length,2);assert.equal(h.calls.filter(x=>x==='stop').length,2);assert.equal(JSON.parse(h.store.get('draft')).segments.length,2);await renderer.act(async()=>tree.unmount());
});

test('exam entry never extracts during live transcription and persists the checkpoint under its restored exam session',async()=>{
 const exports={},calls=[],sessionId='11111111-1111-4111-8111-111111111111',checkpointKey='dai.voice.extraction.1.8.'+sessionId,activeKey='dai.voice.extraction.active.1.8',native={StyleSheet:{create:x=>x},Alert:{alert(){}},...Object.fromEntries(['ActivityIndicator','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/VoiceExamEntry.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const secure=new Map();vm.runInNewContext(code,{exports,Error,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{usePreventRemove(){}}:n==='expo-secure-store'?{getItemAsync:async key=>secure.get(key)||null,setItemAsync:async(key,value)=>secure.set(key,value),deleteItemAsync:async key=>secure.delete(key)}:n==='expo-crypto'?{randomUUID:()=>sessionId,CryptoDigestAlgorithm:{SHA256:'SHA-256'},digestStringAsync:async(_algorithm,value)=>'a'.repeat(64)}:n==='./socialDraft'?require('../src/socialDraft.ts'):n==='./voiceSession'?require('../src/voiceSession.ts'):n==='./api'?{getPatient:async()=>({patient:{id:8,anonymous_id:'Synthetic patient'}})}:n==='./voiceApi'?{extractVoice:async(...args)=>{calls.push(args);await args[3].onCheckpoint({cursor:1,revision:'b'.repeat(64),review:{fields:{}}});return review}}:{default:n.slice(2)}});let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(exports.default,{token:'A',userId:1,initialPatientId:8})));await renderer.act(async()=>button(tree,'Muayeneye Devam Et').props.onPress());await renderer.act(async()=>tree.root.findAllByType('Pressable').find(x=>x.props.accessibilityRole==='checkbox').props.onPress());
 await renderer.act(async()=>{tree.root.findByType('NativeVoiceRecorder').props.onSessionState({started:true,finished:false,sessionId});tree.root.findByType('NativeVoiceRecorder').props.onTranscript('Synthetic speech')});assert.equal(calls.length,0);assert.equal(button(tree,'Muayeneyi Bitir ve Metni Çözümle').props.disabled,true);
 await renderer.act(async()=>tree.root.findByType('NativeVoiceRecorder').props.onFinished('Synthetic speech',sessionId));assert.equal(calls.length,1);assert.equal(calls[0][2],'Synthetic speech');assert.equal(calls[0][3].sessionId,sessionId);assert.equal(calls[0][3].transcriptHash,'a'.repeat(64));assert.equal(secure.has(activeKey),true);assert.equal(secure.has(checkpointKey),true);await renderer.act(async()=>tree.unmount());
});

test('native audio timeout rejects even if the platform upload never settles',async()=>{
 const exports={};let expire,cancelled=0;const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/nativeVoiceAudio.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 vm.runInNewContext(code,{exports,Error,setTimeout:fn=>{expire=fn;return 1},clearTimeout(){},require:n=>n==='expo-file-system/legacy'?{getInfoAsync:async()=>({exists:true,size:1024}),FileSystemUploadType:{BINARY_CONTENT:0},createUploadTask:()=>({uploadAsync:()=>new Promise(()=>{}),cancelAsync:async()=>{cancelled++}})}:n==='./api'?{ApiError:class extends Error{constructor(status,message){super(message);this.status=status}}}:{revalidateSession:async()=>{}}});const result=exports.transcribeNativeRecording('A',8,'file:///cache/record.m4a','voice-workflow-timeout-00000001');await new Promise(r=>setImmediate(r));expire();await assert.rejects(result,/yerel kayıt/);assert.equal(cancelled,1);
});
test('unreadable approval intent blocks a new clinical write',async()=>{
 const map=new Map([['dai.voice.apply.1.8','not valid JSON']]),h=approvalUI(async()=>{throw Error('must not send')},map);let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,review,labels:{}})));assert.equal(button(tree,'Seçili Bilgileri Kaydet').props.disabled,true);assert.ok(text(tree.toJSON()).includes('Hasta geçmişini kontrol edin'));await renderer.act(async()=>tree.unmount());
});

test('leaving the focused screen stops microphone and retains the pending clip',async()=>{
 const calls=[],h=recorderUI({transcribe:async()=>{calls.push('ASR');return{transcript:'Synthetic',revision:'r'}}});const props={token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished(){}};let tree;await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,props)));await renderer.act(async()=>button(tree,'Mikrofonu başlat').props.onPress());await renderer.act(async()=>{h.focus(false);tree.update(React.createElement(h.Component,props));await new Promise(r=>setImmediate(r))});assert.equal(h.calls.filter(x=>x==='stop').length,1);assert.equal(calls.length,0);assert.equal(JSON.parse(h.store.get('draft')).segments.length,1);await renderer.act(async()=>tree.unmount());
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

test('voice extraction checkpoint is scoped to account, patient, transcript, exam session and expiry',()=>{
 const api=require('../src/voiceSession.ts'),hash='a'.repeat(64),sessionId='11111111-1111-4111-8111-111111111111',otherSession='22222222-2222-4222-8222-222222222222';
 const checkpoint={version:1,userId:1,patientId:8,sessionId,transcriptHash:hash,cursor:2,revision:'b'.repeat(64),review:{fields:{}},updatedAt:100000},raw=JSON.stringify(checkpoint);
 assert.equal(api.newVoiceDraft(1,8,100000,sessionId).sessionId,sessionId);
 assert.deepEqual(api.parseVoiceExtractionCheckpoint(raw,1,8,hash,3,sessionId,100001),checkpoint);
 assert.equal(api.parseVoiceExtractionCheckpoint(raw,1,8,hash,3,otherSession,100001),null);
 assert.equal(api.parseVoiceExtractionCheckpoint(JSON.stringify({...checkpoint,sessionId:undefined}),1,8,hash,3,sessionId,100001),null);
 assert.equal(api.parseVoiceExtractionCheckpoint(raw,2,8,hash,3,sessionId,100001),null);
 assert.equal(api.parseVoiceExtractionCheckpoint(raw,1,9,hash,3,sessionId,100001),null);
 assert.equal(api.parseVoiceExtractionCheckpoint(raw,1,8,'c'.repeat(64),3,sessionId,100001),null);
 assert.equal(api.parseVoiceExtractionCheckpoint(raw,1,8,hash,3,sessionId,100000+86400001),null);
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


test('native voice history is loaded privately, requires patient confirmation, and preserves conflicts',async()=>{
 const exports={},secure=new Map(),historyCalls=[],extractCalls=[];
 const native={StyleSheet:{create:x=>x},Alert:{alert(){}},Linking:{openURL:async()=>{}},...Object.fromEntries(['ActivityIndicator','Pressable','ScrollView','Text','TextInput','View'].map(x=>[x,x]))};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/VoiceExamEntry.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,Error,require:n=>n==='react'?{...React,default:React}:n==='react-native'?native:n==='@react-navigation/native'?{usePreventRemove(){}}:n==='expo-secure-store'?{getItemAsync:async key=>secure.get(key)||null,setItemAsync:async(key,value)=>secure.set(key,value),deleteItemAsync:async key=>secure.delete(key)}:n==='expo-crypto'?{randomUUID:()=> 'voice-history-checkpoint',CryptoDigestAlgorithm:{SHA256:'SHA-256'},digestStringAsync:async()=> 'a'.repeat(64)}:n==='./socialDraft'?require('../src/socialDraft.ts'):n==='./voiceSession'?require('../src/voiceSession.ts'):n==='./api'?{getPatient:async()=>({patient:{id:8,anonymous_id:'Synthetic patient',first_name:'Synthetic',last_name:'Patient'}})}:n==='./voiceApi'?{
  getVoiceHistory:async(token,patientId)=>{historyCalls.push({token,patientId});return{ok:true,revision:'b'.repeat(64),notice:'Önceki hekim onaylı kayıtlar; hastayla doğrulayın.',fields:{medical_history:{value:'Astım beyanı',quote:'Önceki kayıt',analysis_id:17},medications:{value:'Düzenli ilaç beyanı',quote:'Önceki kayıt',analysis_id:17}}}},
  extractVoice:async(token,patientId,transcript)=>{extractCalls.push({token,patientId,transcript});return{ok:true,revision:'c'.repeat(64),review:{fields:{medical_history:{value:'Bu görüşmede astım olmadığını söyledi',quote:'Güncel beyan'}},teeth:[],communication:[],decision_barriers:[],follow_up_questions:[],literature_topics:[],source_requests:[],uncertain:''}}}
}:{default:n.slice(2)}});
 let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(exports.default,{token:'A',userId:1,initialPatientId:8})));
 await renderer.act(async()=>{await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>button(tree,'Muayeneye Devam Et').props.onPress());
 await renderer.act(async()=>{button(tree,'Önceki kayıtları göster').props.onPress();await new Promise(resolve=>setImmediate(resolve))});
 assert.deepEqual(historyCalls,[{token:'A',patientId:8}]);
 assert.ok(text(tree.toJSON()).includes('Astım beyanı'));
 const historyCheck=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityRole==='checkbox'&&text(node).includes('Bu bilgileri hastayla doğruladım.'));
 assert.ok(historyCheck);
 await renderer.act(async()=>historyCheck.props.onPress());
 await renderer.act(async()=>button(tree,'Doğruladığım bilgileri muayeneye ekle').props.onPress());
 const consentCheck=tree.root.findAllByType('Pressable').find(node=>node.props.accessibilityRole==='checkbox'&&text(node).includes('Hastayı bilgilendirdim.'));
 assert.ok(consentCheck);
 await renderer.act(async()=>consentCheck.props.onPress());
 const recorder=tree.root.findByType('NativeVoiceRecorder');
 await renderer.act(async()=>{recorder.props.onTranscript('Güncel sentetik muayene metni');recorder.props.onFinished('Güncel sentetik muayene metni');await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(extractCalls.length,1);
 const rendered=text(tree.toJSON());
 assert.ok(rendered.includes('Düzenli ilaç beyanı'));
 assert.ok(rendered.includes('Bu görüşmede astım olmadığını söyledi'));
 assert.ok(rendered.includes('önceki kayıt'));
 assert.ok(rendered.includes('Önceki ve güncel beyanlar çelişiyorsa ayrıca gösterilir'));
 await renderer.act(async()=>tree.unmount());
});



test('app restart recovers a bounded interrupted private recording with its original request key',async()=>{
 const saved=JSON.stringify({version:1,userId:1,patientId:8,transcript:'Önceki konuşma',segments:[{id:'stable-interrupted-segment',uri:'file:///cache/interrupted.m4a',ready:false}],updatedAt:Date.now(),ended:false,audioStarted:true,elapsedMs:4200});
 const calls=[],transcripts=[],h=recorderUI({saved,transcribe:async(...args)=>{calls.push(args);return{transcript:'Kurtarılan bölüm',revision:'r'}}});let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript:value=>transcripts.push(value),onFinished(){}})));
 await renderer.act(async()=>new Promise(resolve=>setImmediate(resolve)));
 assert.ok(button(tree,'Bekleyen sesleri yazıya çevir'));
 await renderer.act(async()=>button(tree,'Bekleyen sesleri yazıya çevir').props.onPress());
 assert.equal(calls.length,1);assert.equal(calls[0][3],'stable-interrupted-segment');
 assert.equal(transcripts.at(-1),'Önceki konuşma\nKurtarılan bölüm');
 assert.equal(JSON.parse(h.store.get('draft')).segments.length,0);
 await renderer.act(async()=>tree.unmount());
});

test('missing interrupted audio removes only its receipt and preserves earlier transcript',async()=>{
 const saved=JSON.stringify({version:1,userId:1,patientId:8,transcript:'Korunacak önceki metin',segments:[{id:'missing-segment',uri:'file:///cache/missing.m4a',ready:false}],updatedAt:Date.now(),ended:false,audioStarted:true,elapsedMs:1200});
 const h=recorderUI({saved,restoredFileInfo:{exists:false,size:0}}),transcripts=[];let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript:value=>transcripts.push(value),onFinished(){}})));
 await renderer.act(async()=>new Promise(resolve=>setImmediate(resolve)));
 assert.equal(JSON.parse(h.store.get('draft')).segments.length,0);
 assert.equal(JSON.parse(h.store.get('draft')).transcript,'Korunacak önceki metin');
 assert.equal(transcripts.at(-1),'Korunacak önceki metin');
 await renderer.act(async()=>tree.unmount());
});


test('a recorder that stopped before returning an error exposes safe finalization without a second stop',async()=>{
 const asr=[],h=recorderUI({stopFailures:1,stopFailureStopsRecorder:true,transcribe:async(...args)=>{asr.push(args);return{transcript:'Güvenli biçimde tamamlandı',revision:'r'}}});let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished(){}})));
 await renderer.act(async()=>button(tree,'Mikrofonu başlat').props.onPress());
 await renderer.act(async()=>button(tree,'Ⅱ  Duraklat').props.onPress());
 assert.ok(button(tree,'Ses bölümünü güvenle tamamla'));
 await renderer.act(async()=>button(tree,'Ses bölümünü güvenle tamamla').props.onPress());
 assert.equal(h.calls.filter(value=>value==='stop').length,1);
 assert.equal(asr.length,1);
 assert.equal(JSON.parse(h.store.get('draft')).segments.length,0);
 assert.ok(JSON.parse(h.store.get('draft')).transcript.includes('Güvenli biçimde tamamlandı'));
 await renderer.act(async()=>tree.unmount());
});

test('failed recorder stop keeps the same segment active until a later stop and ASR succeed',async()=>{
 const asr=[],h=recorderUI({stopFailures:1,transcribe:async(...args)=>{asr.push(args);return{transcript:'Durdurulduktan sonra yazıldı',revision:'r'}}});let tree;
 await renderer.act(async()=>tree=renderer.create(React.createElement(h.Component,{token:'A',userId:1,patientId:8,consent:true,value:'',onTranscript(){},onFinished(){}})));
 await renderer.act(async()=>button(tree,'Mikrofonu başlat').props.onPress());
 await renderer.act(async()=>button(tree,'Ⅱ  Duraklat').props.onPress());
 assert.equal(h.calls.filter(value=>value==='stop').length,1);assert.ok(text(tree.toJSON()).includes('Synthetic stop failure'));
 await renderer.act(async()=>button(tree,'Ⅱ  Duraklat').props.onPress());
 assert.equal(h.calls.filter(value=>value==='stop').length,2);assert.equal(asr.length,1);
 assert.equal(JSON.parse(h.store.get('draft')).segments.length,0);
 assert.ok(JSON.parse(h.store.get('draft')).transcript.includes('Durdurulduktan sonra yazıldı'));
 await renderer.act(async()=>tree.unmount());
});

test('native voice recorder exposes the web session microphone, timer, meter and transcript preview',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativeVoiceRecorder.tsx'),'utf8');
 assert.match(source,/SESLİ MUAYENE/);
 assert.match(source,/Mikrofonu başlat/);
 assert.match(source,/Duraklat/);
 assert.match(source,/Muayeneyi bitir/);
 assert.match(source,/formatVoiceElapsed\(elapsedMs\)/);
 assert.match(source,/accessibilityRole="progressbar"/);
 assert.match(source,/WAVE_BARS\.map/);
 assert.match(source,/SON ALINAN KONUŞMA METNİ/);
 assert.match(source,/isMeteringEnabled:true/);
 assert.match(source,/voiceDeviceSignalLevel\(status\.metering\)/);
 assert.match(source,/\{view\.audioStarted&&<View style=\{\[s\.micCircle/,'the microphone focal point appears only after recording has started');
 assert.match(source,/\{recording&&<View accessibilityRole="progressbar"/,'the live level meter is shown only while recording');
 assert.match(source,/micCircle:\{width:76,height:76/,'the native microphone stays compact');
 assert.match(source,/controls:\{flexDirection:'column'/,'primary voice actions remain full-width and vertically ordered');
 assert.match(source,/button:\{width:'100%',minHeight:48/);
});
