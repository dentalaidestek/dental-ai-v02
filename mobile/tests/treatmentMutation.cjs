const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');

function compile(path){
 return ts.transpileModule(fs.readFileSync(require.resolve(path),'utf8'),{
  fileName:path,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
 }).outputText;
}
function loadIntent(){
 const exports={};
 vm.runInNewContext(compile('../src/treatmentMutation.ts'),{exports,Error,JSON,Date,Number,RegExp});
 return exports;
}
function loadApi(){
 const exports={};
 vm.runInNewContext(compile('../src/api.ts'),{
  exports,fetch:global.fetch,AbortController,setTimeout,clearTimeout,Error,JSON,Number,Date,Math,
  require:()=>({reportSessionExpiry(){},revalidateSession:async()=>{}})
 });
 return exports;
}
const payload={treatment_name:'Kompozit dolgu',tooth_number:'36',treatment_date:'2026-11-16',material:'Kompozit',doctor_note:'Synthetic note',result:'Tamamlandı'};
const key='synthetic-treatment-request-0001';
const revision='a'.repeat(64);
const receipt={ok:true,treatment_id:17,edit_revision:'b'.repeat(64),replayed:false};

test('treatment intent is scoped to account and patient and preserves one request key',()=>{
 const api=loadIntent();
 const value={userId:1,patientId:8,operation:'CREATE',treatmentId:null,requestKey:key,expectedRevision:null,payload};
 const parsed=api.parseTreatmentMutationIntent(JSON.stringify(value),1,8);
 assert.equal(parsed.requestKey,key);
 assert.equal(parsed.payload.treatment_name,'Kompozit dolgu');
 assert.equal(api.treatmentMutationStorageKey(1,8),'dai.treatment.1.8');
 assert.throws(()=>api.parseTreatmentMutationIntent(JSON.stringify(value),2,8),/hesap/);
 assert.throws(()=>api.parseTreatmentMutationIntent(JSON.stringify(value),1,9),/hasta/);
});

test('treatment update intent requires the exact record id and 64-character revision',()=>{
 const api=loadIntent();
 const value={userId:1,patientId:8,operation:'UPDATE',treatmentId:17,requestKey:key,expectedRevision:revision,payload};
 assert.equal(api.parseTreatmentMutationIntent(JSON.stringify(value),1,8).treatmentId,17);
 assert.throws(()=>api.parseTreatmentMutationIntent(JSON.stringify({...value,expectedRevision:'bad'}),1,8),/sürümü/);
 assert.throws(()=>api.parseTreatmentMutationIntent(JSON.stringify({...value,treatmentId:0}),1,8),/sürümü/);
});

test('treatment intent rejects invalid FDI, impossible dates and oversized clinical notes',()=>{
 const api=loadIntent();
 const value={userId:1,patientId:8,operation:'CREATE',treatmentId:null,requestKey:key,expectedRevision:null,payload};
 for(const patch of [
  {tooth_number:'19'},
  {treatment_date:'2026-02-30'},
  {treatment_date:'2026/02/03'},
  {doctor_note:'x'.repeat(4001)},
  {result:'x'.repeat(1001)},
  {material:'x'.repeat(501)},
 ]) assert.throws(()=>api.parseTreatmentMutationIntent(JSON.stringify({...value,payload:{...payload,...patch}}),1,8));
});

test('native create sends the stable idempotency key and validates the durable receipt',async()=>{
 const original=global.fetch,calls=[];
 global.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify(receipt),{status:201,headers:{'content-type':'application/json'}})};
 try{
  const api=loadApi();
  const result=await api.createTreatment('token',8,payload,key);
  assert.equal(result.treatment_id,17);
  assert.match(calls[0].url,/\/patients\/8\/treatments$/);
  assert.equal(calls[0].init.method,'POST');
  assert.equal(JSON.parse(calls[0].init.body).request_key,key);
  global.fetch=async()=>new Response(JSON.stringify({ok:true,treatment_id:17}),{status:201});
  const broken=loadApi();
  await assert.rejects(()=>broken.createTreatment('token',8,payload,key),/fişi doğrulanamadı/);
 }finally{global.fetch=original}
});

test('native update sends expected revision and idempotency key together',async()=>{
 const original=global.fetch,calls=[];
 global.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify({...receipt,replayed:true}),{status:200,headers:{'content-type':'application/json'}})};
 try{
  const api=loadApi();
  const result=await api.updateTreatment('token',8,17,payload,key,revision);
  const body=JSON.parse(calls[0].init.body);
  assert.equal(result.replayed,true);
  assert.match(calls[0].url,/\/patients\/8\/treatments\/17$/);
  assert.equal(calls[0].init.method,'PUT');
  assert.equal(body.request_key,key);
  assert.equal(body.expected_revision,revision);
  global.fetch=()=>{throw Error('network must not be called')};
  const broken=loadApi();
  assert.throws(()=>broken.updateTreatment('token',8,17,payload,key,'bad'),/sürümü/);
 }finally{global.fetch=original}
});
