const ts=require('typescript'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const Module=require('node:module');
const {test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
}).outputText,f);

let responseBody={ok:true,revision:'b'.repeat(64),transcript:'Soğukla kısa süreli ağrı.',replayed:false};
let captured=null,uploads=0,info={exists:true,size:1024};
const fakeFileSystem={
 FileSystemUploadType:{BINARY_CONTENT:1},
 getInfoAsync:async()=>info,
 createUploadTask:(url,uri,options)=>{
  captured={url,uri,options};uploads++;
  return {uploadAsync:async()=>({status:responseBody.status||200,body:JSON.stringify(responseBody)}),cancelAsync:async()=>{}};
 }
};
const originalLoad=Module._load;
Module._load=function(request,parent,isMain){
 if(request==='expo-file-system/legacy')return fakeFileSystem;
 if(request==='./api'&&parent?.filename.endsWith('nativeVoiceAudio.ts')){
  return {ApiError:class ApiError extends Error{constructor(status,message){super(message);this.status=status;this.name='ApiError'}}};
 }
 if(request==='./sessionExpiry'&&parent?.filename.endsWith('nativeVoiceAudio.ts'))return {revalidateSession:async()=>{}};
 return originalLoad.call(this,request,parent,isMain);
};
const api=require('../src/nativeVoiceAudio.ts');
const REQUEST='9d1b45a0-3d25-4d2e-aaf2-74f19c81d89e';

test('native ASR upload binds the persisted segment key to the patient-scoped binary request',async()=>{
 responseBody={ok:true,revision:'b'.repeat(64),transcript:'Soğukla kısa süreli ağrı.',replayed:true};
 captured=null;
 const result=await api.transcribeNativeRecording('token',42,'file:///cache/clip.m4a',REQUEST);
 assert.equal(result.transcript,'Soğukla kısa süreli ağrı.');
 assert.equal(result.replayed,true);
 assert.match(captured.url,/\/patients\/42\/voice-exam\/audio$/);
 assert.equal(captured.options.headers['X-Voice-Request-Key'],REQUEST);
 assert.equal(captured.options.headers['X-Voice-Consent'],'yes');
 assert.equal(captured.options.headers.Authorization,'Bearer token');
 assert.equal(captured.options.uploadType,1);
 assert.equal(captured.url.includes(REQUEST),false);
});

test('invalid segment key or local audio never starts an upload',async()=>{
 const before=uploads;
 await assert.rejects(()=>api.transcribeNativeRecording('token',42,'file:///cache/clip.m4a','bad'),/işlem anahtarı/);
 info={exists:false,size:0};
 await assert.rejects(()=>api.transcribeNativeRecording('token',42,'file:///cache/missing.m4a',REQUEST),/8 MB sınırını/);
 assert.equal(uploads,before);
 info={exists:true,size:1024};
});

test('ambiguous server result is surfaced as a typed error for explicit re-key confirmation',async()=>{
 responseBody={ok:false,code:'VOICE_ASR_OUTCOME_UNKNOWN',detail:'Sonuç kesinleşmedi.',status:409};
 await assert.rejects(
  ()=>api.transcribeNativeRecording('token',42,'file:///cache/clip.m4a',REQUEST),
  error=>error.name==='VoiceAsrError'&&error.code==='VOICE_ASR_OUTCOME_UNKNOWN'&&error.status===409
 );
});

test('server receipt replay must include a valid patient revision and bounded transcript',async()=>{
 responseBody={ok:true,revision:'invalid',transcript:'Metin',replayed:true};
 await assert.rejects(()=>api.transcribeNativeRecording('token',42,'file:///cache/clip.m4a',REQUEST),/hasta sürümü yanıtı eksik/);
 responseBody={ok:true,revision:'b'.repeat(64),transcript:'x'.repeat(18001),replayed:true};
 await assert.rejects(()=>api.transcribeNativeRecording('token',42,'file:///cache/clip.m4a',REQUEST),/hasta sürümü yanıtı eksik/);
});

test('native recorder retries the same segment key and only creates a new key after an explicit warning',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/NativeVoiceRecorder.tsx'),'utf8');
 assert.match(source,/transcribeNativeRecording\(token,patientId,segment\.uri,segment\.id,/);
 assert.match(source,/VOICE_ASR_OUTCOME_UNKNOWN/);
 assert.match(source,/Önceki isteğin sonucu belirsiz/);
 assert.match(source,/Yeni deneme ayrı bir Gemini çağrısı oluşturabilir/);
 assert.match(source,/item\.id===segment\.id\?\{...item,id:Crypto\.randomUUID\(\),ready:true\}:item/);
 assert.match(source,/await persist\(next\);\s*setIndeterminateSegmentId\(null\);\s*setError\(''\);\s*await drain\(\)/);
});
