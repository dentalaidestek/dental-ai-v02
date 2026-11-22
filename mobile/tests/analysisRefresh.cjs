const ts=require('typescript');
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {test}=require('node:test');
const sessionRenderKeyExports=require('./helpers/sessionRenderKeyModule.cjs');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const refreshExports={};
const refreshSource=ts.transpileModule(fs.readFileSync(require.resolve('../src/analysisRefresh.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
vm.runInNewContext(refreshSource,{exports:refreshExports,Math});
const result=(id=7,status='VISION_READY')=>({analysis:{id,status},assets:[],ai_result:null});
function harness(fetchAnalysis){
 const states=[[],null,null,result(),false,''],previous=[],refs=[],effects=[];
 let stateIndex=0,effectIndex=0,refIndex=0,event={entity_type:'analysis',entity_id:7,event_type:'ANALYSIS_UPDATED',event_id:100},token='synthetic-token',lastSessionKey='';
 const react={useCallback:f=>f,useRef:value=>{const i=refIndex++;return refs[i]??(refs[i]={current:value})},useState:()=>{const i=stateIndex++;return [states[i],value=>{states[i]=value}]},useEffect:(f,deps)=>{const i=effectIndex++;if(!previous[i]||deps.some((v,j)=>!Object.is(v,previous[i].deps[j]))){effects.push(()=>{previous[i]?.cleanup?.();previous[i]={deps,cleanup:f()}})}},createElement:()=>null};react.default=react;
 const useSessionRenderKey=scope=>{const identity=react.useRef(null);identity.current=sessionRenderKeyExports.resolveSessionRenderIdentity(identity.current,scope);lastSessionKey=identity.current.key;return identity.current.key};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeDentalAI.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const exports={};
 vm.runInNewContext(code,{exports,setTimeout:()=>0,clearTimeout:()=>{},require:name=>name==='react'?react:name==='react-native'?{AppState:{addEventListener:()=>({remove(){}}),currentState:'active'}}:name==='@react-navigation/native'?{useIsFocused:()=>true}:name==='./api'?{getPatients:async()=>({items:[]})}:name==='./analysisApi'?{getAnalysis:fetchAnalysis,analysisPatientLabel:patient=>{const name=[patient.first_name,patient.last_name].map(value=>typeof value==='string'?value.trim():'').filter(Boolean).join(' ');return name||patient.anonymous_id||'Hasta #'+patient.id}}:name==='./realtime'?{useRealtime:()=>({lastEvent:event})}:name==='./analysisRefresh'?refreshExports:name==='./useSessionRenderKey'?{__esModule:true,default:useSessionRenderKey}:name==='./appResumeRefresh'?{shouldRefreshOnAppResume:()=>false}:{}});
 const render=()=>{stateIndex=0;effectIndex=0;refIndex=0;exports.default({token});while(effects.length)effects.shift()();};
 return {states,render,getSessionKey:()=>lastSessionKey,setEvent:value=>{event=value;render()},setToken:value=>{token=value;render()},unmount:()=>previous.forEach(x=>x?.cleanup?.())};
}
test('analysis event does not fetch without a verified patient selection',async()=>{
 let requests=0;const h=harness(async()=>{requests++;return result()});
 h.render();await tick();assert.equal(requests,0);
 h.render();await tick();h.render();await tick();assert.equal(requests,0);
 h.setEvent({entity_type:'analysis',entity_id:7,event_id:101});await tick();assert.equal(requests,0);
 h.setEvent({entity_type:'analysis',entity_id:8,event_id:102});await tick();assert.equal(requests,0);
});
test('unrelated event does not trigger a new analysis request',async()=>{
 let requests=0;const h=harness(async()=>{requests++;return result()});
 h.render();await tick();const before=requests;
 h.setEvent({entity_type:'user',entity_id:1,event_type:'PROFILE_UPDATED',event_id:101});
 await tick();assert.equal(requests,before);
});
test('different analysis event cannot trigger a fetch for the selected analysis',async()=>{
 let requests=0;const h=harness(async()=>{requests++;return result()});
 h.render();await tick();const before=requests;
 h.setEvent({entity_type:'analysis',entity_id:8,event_type:'ANALYSIS_UPDATED',event_id:101});
 await tick();assert.equal(requests,before);
});
test('token replacement and unmount do not expose unverified analysis results',async()=>{
 for(const change of ['token','unmount']){
  const h=harness(async()=>result(7,'AI_ANALYZED'));
  h.render();await tick();
  if(change==='token')h.setToken('replacement-token');else h.unmount();
  await tick();
  // No patient was selected, so a result cannot be verified against a patient.
  assert.equal(h.states[7],null);
 }
});


test('analysis workspace rotates an opaque session identity on account credential change and keeps it stable within a session',()=>{
 const h=harness(async()=>result());h.render();
 const first=h.getSessionKey();assert.match(first,/^dai-session-[0-9a-z]+$/);
 h.setToken('replacement-token');const second=h.getSessionKey();
 assert.notEqual(second,first,'credential rotation must remount the account-scoped analysis workspace');
 assert.match(second,/^dai-session-[0-9a-z]+$/);
 assert.ok(!first.includes('synthetic-token')&&!second.includes('replacement-token'));
 h.setToken('replacement-token');assert.equal(h.getSessionKey(),second,'same session scope must keep a stable renderer identity');
});

test('new analysis callback validates patient and account before remembering a job',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativeDentalAI.tsx'),'utf8');
 const start=source.indexOf('async function openUploaded(');
 const end=source.indexOf('async function refresh()',start);
 assert.ok(start>=0&&end>start);
 const callback=source.slice(start,end);
 assert.ok(callback.indexOf('await getAnalysis(token,id)')<callback.indexOf('SecureStore.setItemAsync('),
   'a server-verified patient/analysis pair must precede persistence');
 assert.match(callback,/result\.analysis\.patient_id!==selectedPatient/);
 assert.match(callback,/scope!==sessionScope\.current/);
 assert.match(callback,/selection!==selectionGeneration\.current/);
 assert.match(callback,/selectedRecord\.current\?\.id!==selectedPatient/);
});

test('analysis polling stops at web-visible terminal states and completed work jobs',()=>{
 const {analysisNeedsPolling}=refreshExports;
 for(const status of ['VISION_READY','VISION_ERROR','AI_ANALYZED','AI_FINAL','ANALYSIS_COMPLETE','COMPLETED','FAILED','ERROR','CANCELLED']){
  assert.equal(analysisNeedsPolling({analysis:{status},job:null}),false,status+' must not poll');
 }
 assert.equal(analysisNeedsPolling({analysis:{status:'VISION_PENDING'},job:{status:'QUEUED'}}),true);
 for(const status of ['DONE','FAILED','CANCELLED']){
  assert.equal(analysisNeedsPolling({analysis:{status:'AI_ANALYZING'},job:{status}}),false,status+' job must not poll');
 }
});

test('analysis polling uses bounded exponential backoff, jitter and a finite attempt cap',()=>{
 const {analysisPollDelay,MAX_ANALYSIS_POLL_ATTEMPTS}=refreshExports;
 assert.equal(analysisPollDelay(0,.5),15000);
 assert.equal(analysisPollDelay(1,.5),30000);
 assert.equal(analysisPollDelay(2,.5),60000);
 assert.equal(analysisPollDelay(99,.5),60000);
 assert.equal(analysisPollDelay(0,0),13500);
 assert.equal(analysisPollDelay(0,1),16500);
 assert.equal(MAX_ANALYSIS_POLL_ATTEMPTS,40);
});

test('native analysis refresh is bounded and does not keep a fixed interval after VISION_READY',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativeDentalAI.tsx'),'utf8');
 assert.match(source,/analysisNeedsPolling\(analysis\)/);
 assert.match(source,/MAX_ANALYSIS_POLL_ATTEMPTS/);
 assert.match(source,/analysisPollDelay\(attempt\)/);
 assert.doesNotMatch(source,/setInterval\(/);
 assert.match(source,/request!==refreshGeneration\.current/);
 assert.match(source,/analysisRefreshCanRetry\(e\)/);
});

test('analysis refresh retries transient failures but stops on auth, ownership and validation errors',()=>{
 const {analysisRefreshCanRetry}=refreshExports;
 for(const status of [408,429,500,502,503])assert.equal(analysisRefreshCanRetry({status}),true,String(status));
 for(const status of [400,401,403,404,409,410,422])assert.equal(analysisRefreshCanRetry({status}),false,String(status));
 assert.equal(analysisRefreshCanRetry(new Error('offline')),true);
});
