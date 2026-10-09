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
 vm.runInNewContext(code,{exports,require:name=>name==='react'?react:name==='./api'?{getPatients:async()=>({items:[]})}:name==='./analysisApi'?{getAnalysis:fetchAnalysis}:name==='./realtime'?{useRealtime:()=>({lastEvent:event})}:{}});
 const render=()=>{stateIndex=0;effectIndex=0;refIndex=0;exports.default({token});while(effects.length)effects.shift()();};
 return {states,render,setEvent:value=>{event=value;render()},setToken:value=>{token=value;render()},unmount:()=>previous.forEach(x=>x?.cleanup?.())};
}
test('one analysis event fetches once; state replacement does not trigger a request loop',async()=>{
 let requests=0;const h=harness(async()=>{requests++;return result()});
 h.render();await tick();assert.equal(requests,1);
 h.render();await tick();h.render();await tick();assert.equal(requests,1);
 h.setEvent({entity_type:'analysis',entity_id:7,event_id:101});await tick();assert.equal(requests,2);
 h.setEvent({entity_type:'analysis',entity_id:8,event_id:102});await tick();assert.equal(requests,2);
});
test('unrelated event does not discard an analysis result already in flight',async()=>{
 let finish;const h=harness(()=>new Promise(resolve=>{finish=resolve}));
 h.render();h.setEvent({entity_type:'user',entity_id:1,event_type:'PROFILE_UPDATED',event_id:101});
 finish(result(7,'AI_ANALYZED'));await tick();
 assert.equal(h.states[3].analysis.status,'AI_ANALYZED');
});
test('newer matching request wins over an out-of-order earlier result',async()=>{
 const pending=[];const h=harness(()=>new Promise(resolve=>pending.push(resolve)));
 h.render();h.setEvent({entity_type:'analysis',entity_id:7,event_id:101});
 pending[1](result(7,'AI_ANALYZED'));await tick();pending[0](result());await tick();
 assert.equal(h.states[3].analysis.status,'AI_ANALYZED');
});
test('analysis selection, token replacement and unmount reject stale results',async()=>{
 for(const change of ['selection','token','unmount']){
  const pending=[];const h=harness(()=>new Promise(resolve=>pending.push(resolve)));
  h.render();
  if(change==='selection'){h.states[3]=result(8);h.render();}
  else if(change==='token')h.setToken('replacement-token');
  else h.unmount();
  const before=h.states[3];pending[0](result(7,'AI_ANALYZED'));await tick();
  assert.equal(h.states[3],before);
 }
});
