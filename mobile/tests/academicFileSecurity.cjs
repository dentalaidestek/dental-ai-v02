const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test');

const source=fs.readFileSync(path.join(__dirname,'../src/nativeAcademicFiles.ts'),'utf8');
const compiled=ts.transpileModule(source,{fileName:'nativeAcademicFiles.ts',compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
function load(fsapi,timers={}){
 const exports={};
 class ApiError extends Error{constructor(status,message){super(message);this.status=status}}
 vm.runInNewContext(compiled,{
  exports,AbortController,
  setTimeout:timers.setTimeout||setTimeout,
  clearTimeout:timers.clearTimeout||clearTimeout,
  require:name=>name==='expo-file-system/legacy'?fsapi:name==='./api'?{ApiError}:{revalidateSession:async()=>{}}
 });
 return exports;
}
function filesystem(overrides={}){
 return {
  cacheDirectory:'file:///cache/',
  FileSystemUploadType:{MULTIPART:1},
  getInfoAsync:async()=>({exists:true,size:1024}),
  deleteAsync:async()=>{},
  createUploadTask:()=>({uploadAsync:async()=>({status:200,body:'{"ok":true}'}),cancelAsync:async()=>{}}),
  ...overrides
 };
}
const valid={uri:'file:///cache/academic/lecture.pdf',name:'lecture.pdf',mimeType:'application/pdf'};

test('Academic uploads accept only normalized files inside the Expo private cache',()=>{
 const api=load(filesystem());
 assert.equal(api.isPrivateAcademicCacheUri(valid.uri),true);
 for(const uri of [
  'file:///cache-evil/lecture.pdf',
  'file:///Documents/lecture.pdf',
  'file:///cache/../Documents/lecture.pdf',
  'file:///cache/%2e%2e/Documents/lecture.pdf',
  'file:///cache/lecture.pdf?download=1',
  'file:///cache/lecture.pdf#fragment',
  'https://example.test/lecture.pdf'
 ])assert.equal(api.isPrivateAcademicCacheUri(uri),false,uri);
});

test('outside-cache and traversal URIs are rejected before file metadata or upload access',async()=>{
 let reads=0,uploads=0;
 const api=load(filesystem({getInfoAsync:async()=>{reads++;return{exists:true,size:10}},createUploadTask:()=>{uploads++;throw Error('must not upload')}}));
 await assert.rejects(api.uploadAcademic('token',3,{...valid,uri:'file:///cache-backup/private.pdf'},10000,()=>{}),/özel önbellek/);
 await assert.rejects(api.uploadAcademic('token',3,{...valid,uri:'file:///cache/%2e%2e/private.pdf'},10000,()=>{}),/özel önbellek/);
 assert.equal(reads,0);
 assert.equal(uploads,0);
});

test('path-like filenames and extension/MIME mismatches are rejected before reading',async()=>{
 let reads=0;
 const api=load(filesystem({getInfoAsync:async()=>{reads++;return{exists:true,size:10}}}));
 await assert.rejects(api.uploadAcademic('token',3,{...valid,name:'../lecture.pdf'},10000,()=>{}),/dosya adı/);
 await assert.rejects(api.uploadAcademic('token',3,{...valid,mimeType:'image/png'},10000,()=>{}),/eşleşmiyor/);
 assert.equal(reads,0);
});

test('a confirmed Academic upload deletes only its private temporary copy',async()=>{
 const deleted=[],calls=[];
 const api=load(filesystem({
  deleteAsync:async(uri,options)=>deleted.push([uri,options]),
  createUploadTask:(url,uri,options,onProgress)=>{calls.push({url,uri,options});onProgress({totalBytesSent:512,totalBytesExpectedToSend:1024});return{uploadAsync:async()=>({status:200,body:'{"ok":true}'}),cancelAsync:async()=>{}}}
 }));
 const progress=[];
 await api.uploadAcademic('token',3,valid,10000,value=>progress.push(value));
 assert.equal(calls.length,1);
 assert.equal(calls[0].options.mimeType,'application/pdf');
 assert.equal(calls[0].options.headers.Cookie,'');
 assert.equal(calls[0].options.parameters.original_filename,'lecture.pdf');
 assert.deepEqual(progress,[0.5]);
 assert.deepEqual(deleted,[[valid.uri,{idempotent:true}]]);
});

test('an ambiguous timeout preserves the local file for receipt reconciliation',async()=>{
 let expire,cancelled=0,deleted=0;
 const api=load(filesystem({
  deleteAsync:async()=>{deleted++},
  createUploadTask:()=>({uploadAsync:()=>new Promise(()=>{}),cancelAsync:async()=>{cancelled++}})
 }),{setTimeout:fn=>{expire=fn;return 1},clearTimeout:()=>{}});
 const pending=api.uploadAcademic('token',3,valid,10000,()=>{});
 await new Promise(resolve=>setImmediate(resolve));
 expire();
 await assert.rejects(pending,/sonucu belirsiz/);
 assert.equal(cancelled,1);
 assert.equal(deleted,0);
});
