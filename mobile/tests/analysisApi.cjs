const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
const api=require('../src/analysisApi.ts');
test('AI rejects invalid patient and missing clinical image without contacting backend',async()=>{
 const original=global.fetch;global.fetch=()=>{throw Error('unexpected network call')};
 try{
  await assert.rejects(()=>api.createAnalysis('token',{patientId:0,images:[{uri:'file:///image.jpg'}]}),/geçerli hasta/);
  await assert.rejects(()=>api.createAnalysis('token',{patientId:5,images:[]}),/en az bir klinik/);
  await assert.rejects(()=>api.createAnalysis('token',{patientId:5,images:[{uri:''}]}),/klinik görüntü/);
 }finally{global.fetch=original}
});
test('AI rejects invalid analysis IDs before a network request',async()=>{
 const original=global.fetch;global.fetch=()=>{throw Error('unexpected network call')};
 try{
  await assert.rejects(()=>api.getAnalysis('token',0),/Geçersiz analiz/);
  await assert.rejects(()=>api.getAnalysis('token',NaN),/Geçersiz analiz/);
  assert.throws(()=>api.startAnalysisAI('token',-3),/Geçersiz analiz/);
 }finally{global.fetch=original}
});
test('AI status and start use authorized mobile API routes',async()=>{
 const original=global.fetch,calls=[];
 global.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify(url.endsWith('/ai')?{ok:true,status:'VISION_READY'}:{analysis:{id:23,patient_id:7,status:'VISION_READY'},patient:{id:7},assets:[]}),{status:200})};
 try{
  await api.getAnalysis('secret',23);
  await api.startAnalysisAI('secret',23);
  assert.match(calls[0].url,/\/api\/mobile\/v1\/analyses\/23$/);
  assert.match(calls[1].url,/\/api\/mobile\/v1\/analyses\/23\/ai$/);
  assert.equal(calls[1].init.method,'POST');
  assert.equal(calls[0].init.headers.Authorization,'Bearer secret');
  assert.equal(calls[1].init.headers.Authorization,'Bearer secret');
 }finally{global.fetch=original}
});

test('AI refuses malformed created-job response instead of persisting an invalid job ID',async()=>{
 const originalFetch=global.fetch,originalFormData=global.FormData;
 class NativeFormStub{append(){}}
 global.FormData=NativeFormStub;
 global.fetch=async()=>new Response(JSON.stringify({ok:true,analysis_id:null,status:'UPLOADED'}),{status:200});
 try{
  await assert.rejects(()=>api.createAnalysis('secret',{patientId:7,images:[{uri:'file:///image.jpg',name:'image.jpg',type:'image/jpeg'}]}),/geçerli bir iş kimliği/);
 }finally{global.fetch=originalFetch;global.FormData=originalFormData}
});

test('AI rejects a result linked to a different patient',async()=>{
 const original=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({analysis:{id:23,patient_id:7,status:'VISION_READY'},patient:{id:8},assets:[]}),{status:200});
 try{await assert.rejects(()=>api.getAnalysis('token',23),/hasta veya iş kimliği uyuşmayan/)}
 finally{global.fetch=original}
});
test('AI rejects a result with a mismatched analysis job ID',async()=>{
 const original=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({analysis:{id:24,patient_id:7,status:'VISION_READY'},patient:{id:7},assets:[]}),{status:200});
 try{await assert.rejects(()=>api.getAnalysis('token',23),/hasta veya iş kimliği uyuşmayan/)}
 finally{global.fetch=original}
});

test('modern API rejects HTML and scalar success payloads instead of silently accepting them',async()=>{
 const {getNotifications}=require('../src/modernApi.ts');
 const original=global.fetch;
 try{
  for(const raw of ['<html>login</html>','null','42','', '   ', '[]']){
   global.fetch=async()=>new Response(raw,{status:200});
   await assert.rejects(()=>getNotifications('token'),error=>error.status===502);
  }
 }finally{global.fetch=original}
});

test('modern API preserves HTTP errors with null or malformed response bodies',async()=>{
 const {getNotifications}=require('../src/modernApi.ts');
 const original=global.fetch;
 try{
  for(const raw of ['null','<html>service unavailable</html>','{"detail":null}']){
   global.fetch=async()=>new Response(raw,{status:503});
   await assert.rejects(()=>getNotifications('token'),error=>error.status===503&&error.name==='ApiError');
  }
  global.fetch=async()=>new Response(JSON.stringify({detail:{message:'Bakım sürüyor'}}),{status:503});
  await assert.rejects(()=>getNotifications('token'),error=>error.status===503&&error.message==='Bakım sürüyor');
 }finally{global.fetch=original}
});
