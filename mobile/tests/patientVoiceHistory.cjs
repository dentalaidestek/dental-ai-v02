const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test'),React=require('react'),renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
const presentation={},resumePolicy={};
const helperCode=ts.transpileModule(fs.readFileSync(require.resolve('../src/patientVoiceHistoryPresentation.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
vm.runInNewContext(helperCode,{exports:presentation});
const refreshCode=ts.transpileModule(fs.readFileSync(require.resolve('../src/patientVoiceHistoryRefresh.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
vm.runInNewContext(refreshCode,{exports:resumePolicy});
const history=(value='Olumsuz beyan: sistemik rahatsızlık yok')=>({ok:true,revision:'a'.repeat(64),notice:'Önceki hekim onaylı sesli muayene kayıtlarıdır.',fields:{medical_history:{value,quote:'',analysis_id:17},medications:{value:'Metformin beyanı',quote:'',analysis_id:17},allergies:{value:'Olmadığı belirtildi: penisilin alerjisi',quote:'',analysis_id:17}}});
function mount(getVoiceHistory,initialAppState='active'){
 const source=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativePatientVoiceHistory.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}}).outputText;
 const exports={},listeners=new Set(),focusState={current:true};
 const native={
  ActivityIndicator:'ActivityIndicator',Pressable:'Pressable',Text:'Text',View:'View',
  AppState:{
   currentState:initialAppState,
   addEventListener:(event,listener)=>{
    assert.equal(event,'change');listeners.add(listener);
    return {remove:()=>listeners.delete(listener)};
   }
  }
 };
 let event=null;
 vm.runInNewContext(source,{exports,require:name=>name==='react'?{...React,default:React}:name==='react-native'?native:name==='@react-navigation/native'?{useIsFocused:()=>focusState.current}:name==='./voiceApi'?{getVoiceHistory}:name==='./realtime'?{useRealtime:()=>({lastEvent:event})}:name==='./patientVoiceHistoryPresentation'?presentation:name==='./patientVoiceHistoryRefresh'?resumePolicy:{default:name.slice(2)}});
 return {
  Component:exports.default,
  setEvent:value=>{event=value},
  setAppState:state=>{native.AppState.currentState=state;for(const listener of [...listeners])listener(state)},
  setFocused:value=>{focusState.current=value},
  listenerCount:()=>listeners.size,
 };
}
const content=node=>typeof node==='string'?node:Array.isArray(node)?node.map(content).join(''):node?.children?node.children.map(content).join(''):'';
const press=(tree,label)=>tree.root.findAllByType('Pressable').find(node=>node.findAllByType('Text').some(item=>content(item)===label));
test('approved anamnesis rows preserve negative statements and stable clinical ordering',()=>{
 const rows=presentation.patientVoiceHistoryRows({allergies:{value:'Alerjim yok',quote:'Alerjim yok',analysis_id:4},medical_history:{value:'Diyabet öyküsü',quote:'Şekerim var',analysis_id:3},medications:{value:'Metformin',quote:'Metformin',analysis_id:3}});
 assert.deepEqual(rows.map(row=>row.key),['medical_history','medications','allergies']);
 assert.equal(rows[2].value,'Alerjim yok');
 assert.equal(rows[0].analysisId,3);
 assert.deepEqual(presentation.patientVoiceHistoryRows({unknown:{value:'private',quote:'private',analysis_id:1}}),[]);
 assert.deepEqual(presentation.patientVoiceHistoryRows(null),[]);
});
test('patient profile shows only server-approved fields with source ids and a current-status warning',async()=>{
 const api=mount(async()=>history());let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 const rendered=content(tree.toJSON());
 assert.ok(rendered.includes('Hekim Onaylı Anamnez'));
 assert.ok(rendered.includes('Olumsuz beyan: sistemik rahatsızlık yok'));
 assert.ok(rendered.includes('Metformin beyanı'));
 assert.ok(rendered.includes('Olmadığı belirtildi: penisilin alerjisi'));
 assert.ok(rendered.includes('Sesli muayene #17'));
 assert.ok(rendered.includes('güncel hastalık'));
 await renderer.act(async()=>tree.unmount());
});
test('empty approved history does not add an empty anamnesis card',async()=>{
 const api=mount(async()=>({ok:true,revision:'a'.repeat(64),notice:'no history',fields:{}}));let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(tree.toJSON(),null);
 await renderer.act(async()=>tree.unmount());
});
test('anamnesis request errors expose a retry without showing cached data',async()=>{
 let calls=0;const api=mount(async()=>{calls++;if(calls===1)throw Error('Yetkili hasta geçmişi alınamadı');return history()});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 assert.ok(content(tree.toJSON()).includes('Yetkili hasta geçmişi alınamadı'));
 await renderer.act(async()=>{press(tree,'Yeniden dene').props.onPress();await new Promise(resolve=>setImmediate(resolve))});
 assert.ok(content(tree.toJSON()).includes('Hekim Onaylı Anamnez'));
 assert.equal(calls,2);
 await renderer.act(async()=>tree.unmount());
});
test('switching patient invalidates a late anamnesis response from the previous profile',async()=>{
 let resolveOld;const api=mount((_token,id)=>id===8?new Promise(resolve=>{resolveOld=resolve}):Promise.resolve(history('B hesabına ait olmayan farklı hasta verisi')));let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>{tree.update(React.createElement(api.Component,{token:'owner-token',patientId:9}));await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>{resolveOld(history('Eski hasta özel anamnez metni'));await new Promise(resolve=>setImmediate(resolve))});
 const rendered=content(tree.toJSON());
 assert.ok(rendered.includes('B hesabına ait olmayan farklı hasta verisi'));
 assert.equal(rendered.includes('Eski hasta özel anamnez metni'),false);
 await renderer.act(async()=>tree.unmount());
});
test('failed profile refresh hides the previously loaded clinical values',async()=>{
 let calls=0;const api=mount(async()=>{calls++;if(calls===1)return history('Önceki onaylı ilaç beyanı');throw Error('Güncel anamnez yenilenemedi')});let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 assert.ok(content(tree.toJSON()).includes('Önceki onaylı ilaç beyanı'));
 await renderer.act(async()=>{press(tree,'Anamnezi yenile').props.onPress();await new Promise(resolve=>setImmediate(resolve))});
 const rendered=content(tree.toJSON());
 assert.ok(rendered.includes('Güncel anamnez yenilenemedi'));
 assert.equal(rendered.includes('Önceki onaylı ilaç beyanı'),false);
 await renderer.act(async()=>tree.unmount());
});

test('resume policy refreshes only a focused screen after background or inactive transitions',()=>{
 const shouldRefresh=resumePolicy.shouldRefreshPatientVoiceHistoryOnResume;
 assert.equal(shouldRefresh('background','active',true),true);
 assert.equal(shouldRefresh('inactive','active',true),true);
 assert.equal(shouldRefresh('active','active',true),false);
 assert.equal(shouldRefresh('background','active',false),false);
 assert.equal(shouldRefresh('active','background',true),false);
 assert.equal(shouldRefresh('background','inactive',true),false);
 assert.equal(shouldRefresh(null,'active',true),false);
});

test('approved anamnesis refreshes once when the focused app returns from background',async()=>{
 let calls=0;const api=mount(async()=>history('foreground snapshot '+(++calls)));let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(calls,1);
 await renderer.act(async()=>{
  api.setAppState('background');
  api.setAppState('active');
  api.setAppState('active');
  await new Promise(resolve=>setImmediate(resolve));
 });
 assert.equal(calls,2,'repeated active notifications must not create duplicate reads');
 assert.ok(content(tree.toJSON()).includes('foreground snapshot 2'));
 await renderer.act(async()=>tree.unmount());
});

test('a blurred patient profile does not refresh on app resume and refreshes when focused again',async()=>{
 let calls=0;const api=mount(async()=>history('focus snapshot '+(++calls)));let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 api.setFocused(false);
 await renderer.act(async()=>tree.update(React.createElement(api.Component,{token:'owner-token',patientId:8})));
 await renderer.act(async()=>{
  api.setAppState('background');api.setAppState('active');
  await new Promise(resolve=>setImmediate(resolve));
 });
 assert.equal(calls,1,'a non-visible patient screen must not fetch clinical history');
 api.setFocused(true);
 await renderer.act(async()=>{tree.update(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(calls,2,'navigation focus still refreshes the selected patient');
 await renderer.act(async()=>tree.unmount());
});

test('a late resume response cannot replace anamnesis after switching patient',async()=>{
 let patientEightCalls=0,resolveResume;
 const api=mount(async(_token,id)=>{
  if(id===8){patientEightCalls++;if(patientEightCalls===1)return history('patient eight initial');return new Promise(resolve=>{resolveResume=resolve});}
  return history('patient nine current');
 });
 let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>{
  api.setAppState('background');api.setAppState('active');
  await Promise.resolve();
 });
 assert.equal(typeof resolveResume,'function');
 await renderer.act(async()=>{tree.update(React.createElement(api.Component,{token:'owner-token',patientId:9}));await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>{resolveResume(history('private patient eight late response'));await new Promise(resolve=>setImmediate(resolve))});
 const rendered=content(tree.toJSON());
 assert.ok(rendered.includes('patient nine current'));
 assert.equal(rendered.includes('private patient eight late response'),false);
 await renderer.act(async()=>tree.unmount());
});

test('anamnesis AppState listener is removed when the patient profile unmounts',async()=>{
 let calls=0;const api=mount(async()=>history('only current '+(++calls)));let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(api.listenerCount(),1);
 await renderer.act(async()=>tree.unmount());
 assert.equal(api.listenerCount(),0);
 api.setAppState('background');api.setAppState('active');
 assert.equal(calls,1,'an unmounted patient screen must not issue background clinical reads');
});

test('switching account invalidates a late anamnesis response for the same patient id',async()=>{
 let resolveOld;
 const api=mount((token,id)=>token==='A'?new Promise(resolve=>{resolveOld=resolve}):Promise.resolve(history('Yeni hesabın onaylı beyanı')));let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'A',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>{tree.update(React.createElement(api.Component,{token:'B',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 await renderer.act(async()=>{resolveOld(history('Önceki hesaba ait özel anamnez'));await new Promise(resolve=>setImmediate(resolve))});
 const rendered=content(tree.toJSON());
 assert.ok(rendered.includes('Yeni hesabın onaylı beyanı'));
 assert.equal(rendered.includes('Önceki hesaba ait özel anamnez'),false);
 await renderer.act(async()=>tree.unmount());
});

test('approved anamnesis refreshes on the matching patient update event only',async()=>{
 let calls=0;const api=mount(async()=>history('Onaylı sürüm '+(++calls)));let tree;
 await renderer.act(async()=>{tree=renderer.create(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 api.setEvent({entity_id:9,event_type:'PATIENT_UPDATED',payload:{patient_id:9}});
 await renderer.act(async()=>{tree.update(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(calls,1);
 api.setEvent({entity_id:8,event_type:'PATIENT_UPDATED',payload:{patient_id:8}});
 await renderer.act(async()=>{tree.update(React.createElement(api.Component,{token:'owner-token',patientId:8}));await new Promise(resolve=>setImmediate(resolve))});
 assert.equal(calls,2);
 assert.ok(content(tree.toJSON()).includes('Onaylı sürüm 2'));
 await renderer.act(async()=>tree.unmount());
});
