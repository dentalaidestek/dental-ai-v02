const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');
require.extensions['.ts']=(module,filename)=>module._compile(
 ts.transpileModule(fs.readFileSync(filename,'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
 }).outputText,filename
);
const api=require('../src/modernApi.ts');
const stableCursor='YXNkZmdoaWprbG1ub3BxcnN0dXZ3eHl6';
const item=(id,patientId=8,tooth='36',createdAt='2026-11-20T10:00:00')=>({
 id,patient_id:patientId,patient_name:'SYNTHETIC',tooth_number:tooth,
 status:'FINAL',created_at:createdAt,is_voice_review:false
});
const json=(body,status=200)=>new Response(JSON.stringify(body),{
 status,headers:{'content-type':'application/json'}
});

test('native patient history requests web-order cursor pages and continues with the opaque cursor',async()=>{
 const original=global.fetch,calls=[];
 const firstItems=Array.from({length:50},(_,index)=>item(100-index,8,'36','2026-11-20T10:00:00'));
 global.fetch=async(url,init)=>{calls.push({url:String(url),init});return calls.length===1
  ?json({items:firstItems,total:51,next_cursor:stableCursor,next_before:null})
  :json({items:[item(50,8,'36','2026-11-20T08:00:00')],total:51,next_cursor:null,next_before:null});};
 try{
  const first=await api.getPatientAnalysisHistoryPage('token',8,'36');
  assert.deepEqual(first.next,{kind:'stable',value:stableCursor});
  assert.match(calls[0].url,/stable_order=true/);
  assert.match(calls[0].url,/patient_id=8/);
  assert.match(calls[0].url,/tooth_number=36/);
  const second=await api.getPatientAnalysisHistoryPage('token',8,'36',first.next);
  assert.equal(second.next,null);
  assert.match(calls[1].url,/before_cursor=/);
  assert.doesNotMatch(calls[1].url,/(?:\\?|&)before=/);
  assert.match(calls[1].url,/stable_order=true/);
 }finally{global.fetch=original}
});

test('native patient history rejects cross-patient rows and duplicate IDs',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>json({items:[item(1,9)],total:1,next_cursor:null,next_before:null});
  await assert.rejects(()=>api.getPatientAnalysisHistoryPage('token',8),/hasta kapsamı/);
  global.fetch=async()=>json({items:[item(1),item(1)],total:2,next_cursor:null,next_before:null});
  await assert.rejects(()=>api.getPatientAnalysisHistoryPage('token',8),/tekrarlanan kayıt/);
 }finally{global.fetch=original}
});

test('native patient history rejects malformed FDI, cursor shapes and cursor loops before accepting a page',async()=>{
 const original=global.fetch;let calls=0;
 global.fetch=async()=>{calls++;return json({items:[item(1)],total:1,next_cursor:'!',next_before:null});};
 try{
  await assert.rejects(()=>api.getPatientAnalysisHistoryPage('token',8,'19'),/FDI/);
  assert.equal(calls,0);
  await assert.rejects(()=>api.getPatientAnalysisHistoryPage('token',8,undefined,{kind:'stable',value:'!'}),/imleci/);
  assert.equal(calls,0);
  await assert.rejects(()=>api.getPatientAnalysisHistoryPage('token',8,undefined,{kind:'stable',value:stableCursor}),/kararlı sayfalama/);
  assert.equal(calls,1);
 }finally{global.fetch=original}
});

test('legacy servers fall back to bounded numeric cursors without changing the new stable path',async()=>{
 const original=global.fetch,calls=[];
 const firstItems=Array.from({length:50},(_,index)=>item(100-index));
 global.fetch=async(url)=>{calls.push(String(url));return calls.length===1
  ?json({items:firstItems,total:51,next_before:51})
  :json({items:[item(50)],total:51,next_before:null});};
 try{
  const first=await api.getPatientAnalysisHistoryPage('token',8);
  assert.deepEqual(first.next,{kind:'legacy',value:51});
  assert.match(calls[0],/stable_order=true/);
  const second=await api.getPatientAnalysisHistoryPage('token',8,undefined,first.next);
  assert.equal(second.next,null);
  assert.match(calls[1],/(?:\\?|&)before=51/);
  assert.doesNotMatch(calls[1],/stable_order=true/);
 }finally{global.fetch=original}
});

test('stable cursor response must not also expose a numeric cursor or a short continuation page',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>json({items:[item(42)],total:2,next_cursor:stableCursor,next_before:41});
  await assert.rejects(()=>api.getPatientAnalysisHistoryPage('token',8),/kararlı sayfalama/);
  global.fetch=async()=>json({items:[item(42)],total:2,next_cursor:stableCursor,next_before:null});
  await assert.rejects(()=>api.getPatientAnalysisHistoryPage('token',8),/kararlı sayfalama/);
 }finally{global.fetch=original}
});
