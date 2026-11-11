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
test('AI rejects invalid analysis IDs before a network request',()=>{
 const original=global.fetch;global.fetch=()=>{throw Error('unexpected network call')};
 try{
  assert.throws(()=>api.getAnalysis('token',0),/Geçersiz analiz/);
  assert.throws(()=>api.getAnalysis('token',NaN),/Geçersiz analiz/);
  assert.throws(()=>api.startAnalysisAI('token',-3),/Geçersiz analiz/);
 }finally{global.fetch=original}
});
test('AI status and start use authorized mobile API routes',async()=>{
 const original=global.fetch,calls=[];
 global.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify({ok:true,status:'VISION_READY'}),{status:200})};
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
