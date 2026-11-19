const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test');

function compile(file){
 return ts.transpileModule(fs.readFileSync(path.join(__dirname,file),'utf8'),{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
}
const apiExports={};
vm.runInNewContext(compile('../src/academicApi.ts'),{exports:apiExports,require:name=>name==='./api'?{request:async()=>({})}:{}});
const queueExports={};
vm.runInNewContext(compile('../src/academicUploadQueue.ts'),{exports:queueExports,require:name=>name==='./academicApi'?apiExports:{}});
const {createAcademicUploadQueue,parseAcademicUploadQueue,replaceAcademicUploadIntent,removeAcademicUploadIntent,serializeAcademicUploadQueue,MAX_ACADEMIC_UPLOAD_QUEUE_ITEMS}=queueExports;
const intent=(n,overrides={})=>({version:2,user:1,course:3,name:`lecture-${n}.pdf`,mime:'application/pdf',uri:`file:///cache/academic/${n}.pdf`,size:100,request_key:`synthetic-upload-key-${String(n).padStart(4,'0')}`,...overrides});

test('Academic upload queue round-trips only within its account and course scope',()=>{
 const queue=createAcademicUploadQueue(1,3,[intent(1),intent(2)]);
 const parsed=parseAcademicUploadQueue(serializeAcademicUploadQueue(queue),1,3);
 assert.deepEqual(parsed.items.map(item=>item.request_key),queue.items.map(item=>item.request_key));
 assert.throws(()=>parseAcademicUploadQueue(serializeAcademicUploadQueue(queue),2,3),/başka hesap veya derse/);
 assert.throws(()=>parseAcademicUploadQueue(serializeAcademicUploadQueue(queue),1,4),/başka hesap veya derse/);
});

test('Academic upload queue rejects malformed manifests, empty queues and more than twelve files',()=>{
 assert.throws(()=>parseAcademicUploadQueue('{',1,3));
 assert.throws(()=>parseAcademicUploadQueue(JSON.stringify({version:2,user:1,course:3,items:[intent(1)]}),1,3));
 assert.throws(()=>createAcademicUploadQueue(1,3,[]));
 assert.throws(()=>createAcademicUploadQueue(1,3,Array.from({length:13},(_,i)=>intent(i+1))));
});

test('Academic upload queue rejects duplicate request keys, URIs and filenames',()=>{
 assert.throws(()=>createAcademicUploadQueue(1,3,[intent(1),intent(2,{request_key:intent(1).request_key})]),/yinelenen/);
 assert.throws(()=>createAcademicUploadQueue(1,3,[intent(1),intent(2,{uri:intent(1).uri})]),/yinelenen/);
 assert.throws(()=>createAcademicUploadQueue(1,3,[intent(1),intent(2,{name:intent(1).name})]),/yinelenen/);
});

test('Academic upload queue upgrades a legacy v2 intent in place without changing its request key',()=>{
 const queue=createAcademicUploadQueue(1,3,[intent(1),intent(2)]);
 const upgraded={...queue.items[0],version:3,content_sha256:'a'.repeat(64)};
 const next=replaceAcademicUploadIntent(queue,upgraded);
 assert.equal(next.items[0].version,3);
 assert.equal(next.items[0].content_sha256,'a'.repeat(64));
 assert.equal(next.items[0].request_key,queue.items[0].request_key);
 assert.equal(next.items[1].request_key,queue.items[1].request_key);
});

test('Academic upload queue appends within the twelve-file limit and rejects a thirteenth item',()=>{
 let queue=createAcademicUploadQueue(1,3,[intent(1)]);
 for(let n=2;n<=MAX_ACADEMIC_UPLOAD_QUEUE_ITEMS;n++)queue=replaceAcademicUploadIntent(queue,intent(n));
 assert.equal(queue.items.length,12);
 assert.throws(()=>replaceAcademicUploadIntent(queue,intent(13)),/en fazla 12/);
});

test('Academic upload queue removes exactly one request and represents an empty queue as null',()=>{
 const queue=createAcademicUploadQueue(1,3,[intent(1),intent(2),intent(3)]);
 const next=removeAcademicUploadIntent(queue,intent(2).request_key);
 assert.deepEqual(next.items.map(item=>item.request_key),[intent(1).request_key,intent(3).request_key]);
 const one=createAcademicUploadQueue(1,3,[intent(1)]);
 assert.equal(removeAcademicUploadIntent(one,intent(1).request_key),null);
});
