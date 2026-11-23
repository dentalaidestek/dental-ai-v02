const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{createHash}=require('node:crypto'),{test}=require('node:test');
const source=fs.readFileSync(path.join(__dirname,'../src/academicFileHash.ts'),'utf8');
const compiled=ts.transpileModule(source,{fileName:'academicFileHash.ts',compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const cache='file:///cache/academic/lecture.pdf';
function load(data,options={}){
 let infoReads=0,opens=0,handle;
 const filesystem={cacheDirectory:'file:///cache/',getInfoAsync:async()=>{infoReads++;return{exists:options.exists!==false,size:options.infoSize??data.length}}};
 class FileHandle{
  constructor(){this.offset=0;this.size=options.openSize??data.length;this.closed=false;this.reads=[];handle=this}
  async readBytes(length){
   this.reads.push(length);
   if(options.readError)throw Error('synthetic read failure');
   if(options.truncate&&this.offset>=options.truncateAfter)return new Uint8Array();
   const end=Math.min(this.offset+length,options.truncate?options.truncateAfter:data.length);
   const value=Uint8Array.from(data.subarray(this.offset,end));this.offset+=value.length;return value;
  }
  close(){this.closed=true}
 }
 class File{constructor(uri){this.uri=uri}open(){opens++;return new FileHandle()}}
 const sha256={create(){const digest=createHash('sha256');return{update(bytes){digest.update(Buffer.from(bytes));return this},digest(){return Uint8Array.from(digest.digest())}}}};
 const exports={};
 vm.runInNewContext(compiled,{exports,Uint8Array,Number,decodeURIComponent,require:name=>name==='expo-file-system'?{File}:name==='expo-file-system/legacy'?filesystem:name==='@noble/hashes/sha2.js'?{sha256}:{}});
 return{api:exports,stats:()=>({infoReads,opens,handle})};
}

test('large Academic files are SHA-256 hashed in bounded 1 MiB chunks',async()=>{
 const data=Buffer.alloc(2*1024*1024+123,0x5a),{api,stats}=load(data);
 const result=await api.hashAcademicCacheFile(cache);
 assert.equal(result.size,data.length);
 assert.equal(result.content_sha256,createHash('sha256').update(data).digest('hex'));
 const state=stats();
 assert.deepEqual(state.handle.reads,[1024*1024,1024*1024,123]);
 assert.equal(Math.max(...state.handle.reads),1024*1024);
 assert.equal(state.handle.closed,true);
});

test('outside-cache and encoded traversal paths are rejected before file access',async()=>{
 const {api,stats}=load(Buffer.from('synthetic'));
 for(const uri of ['file:///cache-evil/a.pdf','file:///cache/%2e%2e/private.pdf','file:///cache/a.pdf?download=1','https://example.test/a.pdf'])await assert.rejects(api.hashAcademicCacheFile(uri));
 assert.equal(stats().infoReads,0);assert.equal(stats().opens,0);
});

test('missing cache files return null without opening a file handle',async()=>{
 const {api,stats}=load(Buffer.alloc(0),{exists:false});
 assert.equal(await api.hashAcademicCacheFile(cache),null);
 assert.equal(stats().opens,0);
});

test('oversized and inconsistent file metadata fail before hashing',async()=>{
 const data=Buffer.alloc(32),oversized=load(data,{infoSize:150*1024*1024+1});
 await assert.rejects(oversized.api.hashAcademicCacheFile(cache),/boyutu sınırı/);
 assert.equal(oversized.stats().opens,0);
 const changed=load(data,{openSize:33});
 await assert.rejects(changed.api.hashAcademicCacheFile(cache),/değişti/);
 assert.equal(changed.stats().handle.closed,true);
});

test('a short or failed read closes the private file handle and never returns a partial digest',async()=>{
 const short=load(Buffer.alloc(64),{truncate:true,truncateAfter:12});
 await assert.rejects(short.api.hashAcademicCacheFile(cache),/okunamadı/);
 assert.equal(short.stats().handle.closed,true);
 const failed=load(Buffer.alloc(64),{readError:true});
 await assert.rejects(failed.api.hashAcademicCacheFile(cache),/synthetic read failure/);
 assert.equal(failed.stats().handle.closed,true);
});

test('invalid caller limits fail closed',async()=>{
 const {api,stats}=load(Buffer.from('synthetic'));
 await assert.rejects(api.hashAcademicCacheFile(cache,0));
 await assert.rejects(api.hashAcademicCacheFile(cache,150*1024*1024+1));
 assert.equal(stats().infoReads,0);
});
