const ts=require('typescript'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const Module=require('node:module');
const {test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
}).outputText,f);

let responseBody={ok:true,revision:'b'.repeat(64),transcript:'Soğukla kısa süreli ağrı.',replayed:false};
let audioStatus={isLoaded:true,duration:45,error:null},playerRemovals=0;
let captured=null,uploads=0,fileReads=0,info={exists:true,size:1024};
const fakeFileSystem={
 cacheDirectory:'file:///cache/',
 FileSystemUploadType:{BINARY_CONTENT:1},
 getInfoAsync:async()=>{fileReads++;return info},
 createUploadTask:(url,uri,options)=>{
  captured={url,uri,options};uploads++;
  return {uploadAsync:async()=>({status:responseBody.status||200,body:JSON.stringify(responseBody)}),cancelAsync:async()=>{}};
 }
};
const originalLoad=Module._load;
Module._load=function(request,parent,isMain){
 if(request==='expo-file-system/legacy')return fakeFileSystem;
 if(request==='expo-audio')return {createAudioPlayer:()=>({isLoaded:audioStatus.isLoaded,duration:audioStatus.duration,currentStatus:audioStatus,addListener:(event,callback)=>{queueMicrotask(()=>callback(audioStatus));return {remove:()=>{}}},remove:()=>{playerRemovals++}})};
 if(request==='./api'&&parent?.filename.endsWith('nativeVoiceAudio.ts')){
  return {ApiError:class ApiError extends Error{constructor(status,message){super(message);this.status=status;this.name='ApiError'}}};
 }
 if(request==='./sessionExpiry'&&parent?.filename.endsWith('nativeVoiceAudio.ts'))return {revalidateSession:async()=>{}};
 return originalLoad.call(this,request,parent,isMain);
};
const api=require('../src/nativeVoiceAudio.ts');
const REQUEST='9d1b45a0-3d25-4d2e-aaf2-74f19c81d89e';

test('native audio import duration inspection is metadata-only and always releases its player',async()=>{
 audioStatus={isLoaded:true,duration:45,error:null};playerRemovals=0;
 const duration=await api.readPrivateVoiceAudioDuration('file:///cache/voice-import-123.mp3','audio/mpeg');
 assert.equal(duration,45);assert.equal(playerRemovals,1);
 audioStatus={isLoaded:true,duration:91,error:null};playerRemovals=0;
 await assert.rejects(()=>api.readPrivateVoiceAudioDuration('file:///cache/voice-import-123.mp3','audio/mpeg'),/90 saniye/);
 assert.equal(playerRemovals,1);
});

test('native ASR upload preserves imported MIME and requires a matching private-cache extension',async()=>{
 responseBody={ok:true,revision:'b'.repeat(64),transcript:'Hasta konuşması.',replayed:false};
 captured=null;
 const result=await api.transcribeNativeRecording('token',42,'file:///cache/voice-import-123.mp3',REQUEST,undefined,'audio/mpeg');
 assert.equal(result.transcript,'Hasta konuşması.');
 assert.equal(captured.options.headers['Content-Type'],'audio/mpeg');
 assert.equal(api.isPrivateVoiceRecordingUri('file:///cache/voice-import-123.mp3','file:///cache/','audio/mpeg'),true);
 assert.equal(api.isPrivateVoiceRecordingUri('file:///cache/voice-import-123.mp3','file:///cache/','audio/wav'),false);
 const before=uploads;
 await assert.rejects(()=>api.transcribeNativeRecording('token',42,'file:///cache/voice-import-123.mp3',REQUEST,undefined,'audio/wav'),/özel önbelleğinde/);
 assert.equal(uploads,before);
});

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

test('ASR upload rejects paths outside the private cache before reading or uploading a file',async()=>{
 const allowed='file:///cache/clip.m4a';
 assert.equal(api.isPrivateVoiceRecordingUri(allowed),true);
 const invalid=[
  'file:///Documents/secret.m4a',
  'file:///cache/../Documents/secret.m4a',
  'file:///cache/%2e%2e/Documents/secret.m4a',
  'file:///cache/nested/clip.m4a',
  'file:///cache-elsewhere/clip.m4a',
  'file:///cache/clip.m4a?download=1',
  'file:///cache/clip.wav'
 ];
 for(const uri of invalid)assert.equal(api.isPrivateVoiceRecordingUri(uri),false,uri);
 assert.equal(api.isPrivateVoiceRecordingUri(allowed,'file:///cache'),false);
 const reads=fileReads,before=uploads;
 for(const uri of invalid)await assert.rejects(
  ()=>api.transcribeNativeRecording('token',42,uri,REQUEST),
  /özel önbelleğinde doğrulanamadı/
 );
 assert.equal(fileReads,reads);
 assert.equal(uploads,before);
});

test('persisted voice drafts reject traversal, encoded paths and malformed segment rows',()=>{
 const session=require('../src/voiceSession.ts');
 const base={...session.newVoiceDraft(1,42,1000),segments:[{id:'segment-1',uri:'file:///cache/clip.m4a',ready:true}]};
 assert.ok(session.parseVoiceDraft(JSON.stringify(base),1,42,2000));
 const invalid=[
  'file:///cache/../Documents/secret.m4a',
  'file:///cache/%2e%2e/Documents/secret.m4a',
  'file:///cache/clip.m4a?x=1',
  'file:///cache/clip.wav',
  'file://relative/cache/clip.m4a'
 ];
 for(const uri of invalid)assert.throws(
  ()=>session.parseVoiceDraft(JSON.stringify({...base,segments:[{...base.segments[0],uri}]}),1,42,2000),
  /içeriği doğrulanamadı/
 );
 assert.throws(()=>session.parseVoiceDraft(JSON.stringify({...base,segments:[null]}),1,42,2000),/içeriği doğrulanamadı/);
});

test('recorder deletion and draft reset use the same MIME-bound private-cache guard',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/NativeVoiceRecorder.tsx'),'utf8');
 assert.match(source,/if\\(!isPrivateVoiceRecordingUri\\(uri,FileSystem\\.cacheDirectory,mime\\)\\)throw Error/);
 assert.match(source,/if\\(!uri\\|\\|!isPrivateVoiceRecordingUri\\(uri\\)\\)throw Error/);
 assert.match(source,/for\\(const segment of draft\\.current\\.segments\\)if\\(isPrivateVoiceRecordingUri\\(segment\\.uri,FileSystem\\.cacheDirectory,segment\\.mime\\)\\)await removeFile\\(segment\\.uri,segment\\.mime\\)/);
 assert.match(source,/Taslak temizlendi\\. Uygulama önbelleği dışında kalan doğrulanamayan dosyaya dokunulmadı\\./);
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
 assert.match(source,/const saved=\{\.\.\.next,updatedAt:Date\.now\(\)\};\s*await store\.setItemAsync\(key,JSON\.stringify\(saved\)\);\s*draft\.current=saved;\s*if\(mounted\.current\)setView\(saved\);\s*setIndeterminateSegmentId\(null\)/);
 assert.match(source,/VOICE_ASR_OUTCOME_UNKNOWN/);
 assert.match(source,/Önceki isteğin sonucu belirsiz/);
 assert.match(source,/Yeni deneme ayrı bir Gemini çağrısı oluşturabilir/);
 assert.match(source,/item\.id===segment\.id\?\{...item,id:Crypto\.randomUUID\(\),ready:true\}:item/);
 assert.match(source,/await store\.setItemAsync\(key,JSON\.stringify\(saved\)\);\s*draft\.current=saved;\s*if\(mounted\.current\)setView\(saved\);\s*setIndeterminateSegmentId\(null\);\s*setError\(''\);\s*await drain\(\)/);
});


test('native voice keeps a durable transcript receipt until private audio deletion is confirmed',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/NativeVoiceRecorder.tsx'),'utf8');
 assert.match(source,/markVoiceSegmentTranscribed/);
 assert.match(source,/const next=markVoiceSegmentTranscribed\(draft\.current,segment\.id,result\.transcript\)/);
 assert.match(source,/await persist\(next\);[\\s\\S]*?await removeFile\(segment\.uri\);[\\s\\S]*?await persist\(removeVoiceSegment\(draft\.current,segment\.id\)\)/);
 assert.match(source,/if\(segment\.transcribed\)[\\s\\S]*?await removeFile\(segment\.uri\);[\\s\\S]*?continue;/);
 assert.match(source,/cleanupTranscribedSegments/);
 assert.match(source,/const remaining=await FileSystem\.getInfoAsync\(uri\)/);
 assert.match(source,/if\(cleanupPending\)setStorageBlocked\(true\)/);
 assert.match(source,/Geçici ses dosyası silinemedi/);
 assert.match(source,/directory:'cache' as const,isMeteringEnabled:true/);
});
