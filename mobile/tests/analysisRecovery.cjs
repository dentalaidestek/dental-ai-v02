const ts=require('typescript'),fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const patient={id:42,anonymous_id:'synthetic-42',first_name:'Test',last_name:'Patient'};
const result={analysis:{id:7,patient_id:42,status:'AI_ANALYZED'},patient,assets:[],ai_result:null};
function harness({props={},fetchAnalysis=async()=>result,fetchPatient=async()=>({patient}),saved=null}={}){
 const states=[],refs=[],callbacks=[],previous=[],effects=[];let si=0,ri=0,ci=0,ei=0,event=null;
 let values={token:'current',userId:1,...props};
 const same=(a,b)=>a&&a.length===b.length&&b.every((v,i)=>Object.is(v,a[i]));
 const react={useState:value=>{const i=si++;if(!(i in states))states[i]=value;return[states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v}]},useRef:value=>{const i=ri++;return refs[i]??(refs[i]={current:value})},useCallback:(f,deps)=>{const i=ci++;if(!same(callbacks[i]?.deps,deps))callbacks[i]={f,deps};return callbacks[i].f},useEffect:(f,deps)=>{const i=ei++;if(!same(previous[i]?.deps,deps))effects.push(()=>{previous[i]?.cleanup?.();previous[i]={deps,cleanup:f()}})},createElement:(type,props,...children)=>({type,props,children})};react.default=react;
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeDentalAI.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 const exports={};vm.runInNewContext(code,{exports,require:name=>name==='react'?react:name==='react-native'?{AppState:{addEventListener:()=>({remove(){}})}}:name==='expo-secure-store'?{getItemAsync:async()=>saved,deleteItemAsync:async()=>{}}:name==='./api'?{getPatients:async()=>({items:[{id:1,anonymous_id:'synthetic-1',first_name:'Other Patient'}],total:1}),getPatient:fetchPatient}:name==='./analysisApi'?{getAnalysis:fetchAnalysis}:name==='./realtime'?{useRealtime:()=>({lastEvent:event})}:name==='./findings'?{displayFindings:()=>[]}:{} });
 const render=()=>{si=ri=ci=ei=0;const tree=exports.default(values);while(effects.length)effects.shift()();return tree};
 const flush=async()=>{for(let i=0;i<4;i++){await tick();render()}};
 return {states,render,flush,change:next=>{values={...values,...next};render()},event:value=>{event=value;render()},unmount:()=>previous.forEach(e=>e.cleanup?.())};
}
test('history result restores its authorized patient without manual patient selection',async()=>{
 const h=harness({props:{initialAnalysisId:7}});h.render();await h.flush();
 assert.equal(h.states[6],42);assert.equal(h.states[8]?.analysis.id,7);assert.match(JSON.stringify(h.render()),/Test.*Patient/);assert.equal(h.states[0].length,1);
});
test('persisted analysis reopens after app restart even when patient is outside first page',async()=>{
 const h=harness({saved:'7'});h.render();await h.flush();
 assert.equal(h.states[6],42);assert.equal(h.states[8]?.analysis.id,7);
 h.event({event_type:'PATIENT_UPDATED',entity_id:1});await h.flush();
 assert.equal(h.states[6],42);assert.equal(h.states[8]?.analysis.patient_id,42);
});
test('patient-profile analysis action selects the requested server-verified patient',async()=>{
 const ids=[];const h=harness({props:{initialPatientId:42},fetchPatient:async(_token,id)=>{ids.push(id);return {patient}}});h.render();await h.flush();
 assert.deepEqual(ids,[42]);assert.equal(h.states[6],42);assert.match(JSON.stringify(h.render()),/Test.*Patient/);assert.equal(h.states[0].length,1);
});
test('late analysis result cannot cross accounts after a token switch',async()=>{
 let resolve;const h=harness({props:{initialAnalysisId:7},fetchAnalysis:()=>new Promise(r=>resolve=r)});h.render();
 h.change({token:'other',initialAnalysisId:undefined});resolve(result);await h.flush();
 assert.equal(h.states[6],null);assert.equal(h.states[8],null);
});
test('explicit patient selection cannot restore a different saved analysis',async()=>{
 const h=harness({props:{initialPatientId:99},saved:'7',fetchPatient:async()=>({patient:{...patient,id:99}})});h.render();await h.flush();
 assert.equal(h.states[6],99);assert.equal(h.states[8],null);
});
test('changing the patient after opening history clears the old job without restoring it again',async()=>{
 let calls=0;const h=harness({props:{initialAnalysisId:7},fetchAnalysis:async()=>{calls++;return result}});h.render();await h.flush();
 const walk=node=>node&&typeof node==='object'?[node,...(node.children||[]).flat(Infinity).flatMap(walk)]:[];
 // The first-page row remains selectable alongside the recovered patient.
 const row=walk(h.render()).find(node=>node.props?.onPress&&JSON.stringify(node.children).includes('Other Patient'));
 assert.ok(row);row.props.onPress();h.render();await h.flush();
 assert.equal(h.states[6],1);assert.equal(h.states[8],null);assert.equal(calls,1);
});
test('deleted selected patient clears clinical selection while unrelated deletions preserve it',async()=>{
 const h=harness({props:{initialAnalysisId:7}});h.render();await h.flush();
 h.event({event_type:'PATIENT_DELETED',entity_id:1});await h.flush();assert.equal(h.states[6],42);
 h.event({event_type:'PATIENT_DELETED',entity_id:42});await h.flush();assert.equal(h.states[6],null);assert.equal(h.states[8],null);
});
