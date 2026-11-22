const ts=require('typescript'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
}).outputText,f);
const {classifyClinicalMediaUploadFailure}=require('../src/clinicalMediaRecovery.ts');

test('missing receipt key is a known pre-persistence configuration rejection',()=>{
 assert.equal(classifyClinicalMediaUploadFailure(503), 'CONFIGURATION');
});

test('transport loss and conflict stay ambiguous until the server receipt is checked',()=>{
 for(const status of [0,408,409,429,500,502])assert.equal(classifyClinicalMediaUploadFailure(status),'UNCERTAIN');
 assert.equal(classifyClinicalMediaUploadFailure(undefined),'UNCERTAIN');
});

test('a missing receipt route is configuration while a patient-specific 404 stays rejected',()=>{
 assert.equal(classifyClinicalMediaUploadFailure(404,undefined,true),'CONFIGURATION');
 assert.equal(classifyClinicalMediaUploadFailure(404),'REJECTED');
 for(const status of [400,403,413,422])assert.equal(classifyClinicalMediaUploadFailure(status),'REJECTED');
});

test('local encrypted-vault failures never claim that the server may have stored the file',()=>{
 for(const code of ['SOURCE_MISSING','VAULT_MISSING','KEY_MISSING','KEY_INVALID','AUTH_FAILED','INVALID_VAULT'])
  assert.equal(classifyClinicalMediaUploadFailure(undefined,code),'LOCAL');
});

test('the native gallery explains a missing server key and keeps the encrypted draft',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/failure==='CONFIGURATION'/);
 assert.match(source,/Şifreli taslak cihazda korunuyor/);
 assert.match(source,/Sunucu güncellenene kadar taslağı silmeyin/);
 assert.match(source,/isMissingApiRoute404\(e\)/);
});

const vm=require('node:vm');
function loadModernApiWithDeleteResponse(body,status=200){
 const source=fs.readFileSync(path.join(__dirname,'../src/modernApi.ts'),'utf8');
 const compiled=ts.transpileModule(source,{fileName:'modernApi.ts',compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020
 }}).outputText;
 const exports={};
 class ApiError extends Error{constructor(code,message){super(message);this.status=code}}
 vm.runInNewContext(compiled,{
  exports,Error,AbortController,setTimeout,clearTimeout,FormData:class FormData{},
  fetch:async()=>({ok:status>=200&&status<300,status,text:async()=>JSON.stringify(body)}),
  require:name=>{
   if(name==='./chatFiles')return{validateChatFile:()=>true};
   if(name==='./api')return{ApiError};
   if(name==='./sessionExpiry')return{revalidateSession:async()=>{}};
   if(name==='./notificationState')return require('../src/notificationState.ts');
   throw Error('Unexpected module '+name);
  }
 });
 return exports;
}

test('native media delete accepts only the exact media receipt, including an idempotent replay',async()=>{
 const api=loadModernApiWithDeleteResponse({
  ok:true,media_id:42,already_deleted:true,storage_cleanup_pending:null
 });
 const result=await api.deleteMedia('synthetic-token',7,42);
 assert.equal(result.ok,true);
 assert.equal(result.media_id,42);
 assert.equal(result.already_deleted,true);
});

test('native media delete rejects a mismatched ID, false success or malformed optional receipt fields',async()=>{
 const invalid=[
  {ok:true,media_id:43},
  {ok:false,media_id:42},
  {ok:true,media_id:42,already_deleted:'yes'},
  {ok:true,media_id:42,storage_cleanup_pending:'pending'}
 ];
 for(const body of invalid){
  const api=loadModernApiWithDeleteResponse(body);
  await assert.rejects(
   ()=>api.deleteMedia('synthetic-token',7,42),
   /Klinik görsel silme yanıtı doğrulanamadı/
  );
 }
});
