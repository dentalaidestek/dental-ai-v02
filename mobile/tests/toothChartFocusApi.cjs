const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');

function loadApi(fetchImpl){
 const source=fs.readFileSync(require.resolve('../src/api.ts'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 const exports={};
 vm.runInNewContext(code,{
  exports,
  require:name=>{
   if(name==='./sessionExpiry')return{reportSessionExpiry(){},revalidateSession:async()=>{}};
   throw Error('unexpected import '+name);
  },
  fetch:fetchImpl,
  AbortController,
  setTimeout,
  clearTimeout
 });
 return exports;
}
function response(payload,status=200){
 return{ok:status>=200&&status<300,status,text:async()=>JSON.stringify(payload)};
}

test('tooth-chart focus requests the authenticated patient endpoint and accepts valid primary FDI',async()=>{
 let observed;
 const api=loadApi(async(url,options)=>{observed={url,options};return response({latest_analysis_tooth:'55'});});
 assert.equal(await api.getToothChartFocus('synthetic-token',8),'55');
 assert.equal(observed.url,'https://dentalai.tr/api/mobile/v1/patients/8/tooth-chart/focus');
 assert.equal(observed.options.headers.Authorization,'Bearer synthetic-token');
 assert.equal(observed.options.credentials,'omit');
});

test('tooth-chart focus rejects invalid patient ids before making a request',async()=>{
 let calls=0;
 const api=loadApi(async()=>{calls++;return response({latest_analysis_tooth:null});});
 await assert.rejects(api.getToothChartFocus('synthetic-token',0),/Geçersiz hasta kimliği/);
 await assert.rejects(api.getToothChartFocus('synthetic-token',8.5),/Geçersiz hasta kimliği/);
 assert.equal(calls,0);
});

test('tooth-chart focus rejects malformed or non-FDI server values',async()=>{
 const api=loadApi(async()=>response({latest_analysis_tooth:'99'}));
 await assert.rejects(api.getToothChartFocus('synthetic-token',8),error=>error.status===502&&/başlangıç dişi/.test(error.message));
});

test('tooth-chart focus accepts an explicit no-analysis response',async()=>{
 const api=loadApi(async()=>response({latest_analysis_tooth:null}));
 assert.equal(await api.getToothChartFocus('synthetic-token',8),null);
});
