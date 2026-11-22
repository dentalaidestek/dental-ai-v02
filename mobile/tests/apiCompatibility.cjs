const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');

require.extensions['.ts']=(module,filename)=>{
 const output=ts.transpileModule(fs.readFileSync(filename,'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
 }).outputText;
 module._compile(output,filename);
};

const compatibility=require('../src/apiCompatibility.ts');
const apiSource=fs.readFileSync(path.join(__dirname,'../src/api.ts'),'utf8');

function loadApi(status,body){
 const compiled=ts.transpileModule(apiSource,{
  fileName:'api.ts',
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
 }).outputText;
 const exports={};
 const dependencies={
  './sessionExpiry':{reportSessionExpiry:()=>{},revalidateSession:async()=>{}},
  './patientDirectoryPresentation':{normalizePatientDirectorySearch:value=>String(value).trim().replace(/\\s+/g,' ')},
  './dashboardPresentation':{isDashboardProgramEvent:()=>true},
  './apiCompatibility':compatibility,
 };
 vm.runInNewContext(compiled,{
  exports,
  require:name=>{
   if(!(name in dependencies))throw new Error('Unexpected API test dependency: '+name);
   return dependencies[name];
  },
  fetch:async()=>({ok:status>=200&&status<300,status,text:async()=>JSON.stringify(body)}),
  AbortController,
  setTimeout,
  clearTimeout,
  URLSearchParams,
  encodeURIComponent,
  Number,
  Math,
  JSON,
  Array,
  Set,
  Map,
  Promise,
  Error,
  Date,
  RegExp,
  String,
  Object,
 });
 return exports;
}

test('bare FastAPI 404 is identified as a missing server route, not an app-update instruction',()=>{
 const error={status:404,message:compatibility.MISSING_API_ROUTE_MESSAGE};
 assert.equal(compatibility.isMissingApiRoute404(error),true);
 assert.match(compatibility.MISSING_API_ROUTE_MESSAGE,/sunucu API sürümü geride olabilir/i);
 assert.doesNotMatch(compatibility.MISSING_API_ROUTE_MESSAGE,/uygulamayı güncelle/i);
});

test('resource-level 404 remains distinct from a missing route',()=>{
 assert.equal(compatibility.isMissingApiRoute404({status:404,message:'Hasta bulunamadı.'}),false);
 assert.equal(compatibility.isMissingApiRoute404({status:403,message:compatibility.MISSING_API_ROUTE_MESSAGE}),false);
 assert.equal(compatibility.isMissingApiRoute404({status:500,message:compatibility.MISSING_API_ROUTE_MESSAGE}),false);
});

test('request maps only a bare 404 Not Found response to the server compatibility hint',async()=>{
 const api=loadApi(404,{detail:'Not Found'});
 await assert.rejects(
  ()=>api.request('/patients/7/media/uploads/key','synthetic-token'),
  error=>error.status===404&&error.message===compatibility.MISSING_API_ROUTE_MESSAGE
 );
});

test('request preserves a specific patient-not-found response instead of labelling it a missing route',async()=>{
 const api=loadApi(404,{detail:'Hasta bulunamadı.'});
 await assert.rejects(
  ()=>api.request('/patients/7','synthetic-token'),
  error=>error.status===404&&error.message==='Hasta bulunamadı.'
 );
});

test('api client imports the shared route compatibility contract',()=>{
 assert.match(apiSource,/MISSING_API_ROUTE_MESSAGE/);
 assert.match(apiSource,/rawDetail===\"Not Found\"/);
});
