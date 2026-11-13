const ts=require('typescript');
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {test}=require('node:test');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const result=(id=7,status='VISION_READY')=>({analysis:{id,status},assets:[],ai_result:null});
function harness(fetchAnalysis){
 const states=[[],null,null,result(),false,''],previous=[],refs=[],effects=[];
 let stateIndex=0,effectIndex=0,refIndex=0,event={entity_type:'analysis',entity_id:7,event_type:'ANALYSIS_UPDATED',event_id:100},token='synthetic-token';
 const react={useCallback:f=>f,useRef:value=>{const i=refIndex++;return refs[i]??(refs[i]={current:value})},useState:()=>{const i=stateIndex++;return [states[i],value=>{states[i]=value}]},useEffect:(f,deps)=>{const i=effectIndex++;if(!previous[i]||deps.some((v,j)=>!Object.is(v,previous[i].deps[j]))){effects.push(()=>{previous[i]?.cleanup?.();previous[i]={deps,cleanup:f()}})}},createElement:()=>null};react.default=react;
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeDentalAI.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const exports={};
 vm.runInNewContext(code,{exports,require:name=>name==='react'?react:name==='react-native'?{AppState:{addEventListener:()=>({remove(){}})}}:name==='./api'?{getPatients:async()=>({items:[]})}:name==='./analysisApi'?{getAnalysis:fetchAnalysis}:name==='./realtime'?{useRealtime:()=>({lastEvent:event})}:{}});
 const render=()=>{stateIndex=0;effectIndex=0;refIndex=0;exports.default({token});while(effects.length)effects.shift()();};
 return {states,render,setEvent:value=>{event=value;render()},setToken:value=>{token=value;render()},unmount:()=>previous.forEach(x=>x?.cleanup?.())};
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
  assert.equal(h.states[8],null);
 }
});
