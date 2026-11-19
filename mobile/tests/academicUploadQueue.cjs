const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test');

function compile(file){
 return ts.transpileModule(fs.readFileSync(path.join(__dirname,file),'utf8'),{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
}
const apiExports={};
vm.runInNewContext(compile('../src/academicApi.ts'),{exports:apiExports,require:name=>name==='./api'?{request:async()=>({})}:{}});
const queueExports={};
vm.runInNewContext(compile('../src/academicUploadQueue.ts'),{exports:queueExports,require:name=>name==='./academicApi'?apiExports:{}});
const {createAcademicUploadQueue,parseAcademicUploadQueue,replaceAcademicUploadIntent,mergeAcademicUploadIntent,removeAcademicUploadIntent,serializeAcademicUploadQueue,MAX_ACADEMIC_UPLOAD_QUEUE_ITEMS}=queueExports;
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


test('legacy v2 upload receipt merges into an already upgraded v3 queue without downgrading its digest',()=>{
 const legacy=intent(1),upgraded={...legacy,version:3,content_sha256:'a'.repeat(64)},queue=createAcademicUploadQueue(1,3,[upgraded]);
 const merged=mergeAcademicUploadIntent(queue,legacy);
 assert.equal(merged.items[0].version,3);
 assert.equal(merged.items[0].content_sha256,upgraded.content_sha256);
});

test('a v3 legacy upload receipt upgrades a matching v2 queue entry without changing its request key',()=>{
 const legacy=intent(1),queue=createAcademicUploadQueue(1,3,[legacy]),upgraded={...legacy,version:3,content_sha256:'b'.repeat(64)};
 const merged=mergeAcademicUploadIntent(queue,upgraded);
 assert.equal(merged.items[0].version,3);
 assert.equal(merged.items[0].request_key,legacy.request_key);
});

test('queue migration rejects different content digests or a changed file identity under one key',()=>{
 const legacy=intent(1),v3={...legacy,version:3,content_sha256:'a'.repeat(64)};
 assert.throws(()=>mergeAcademicUploadIntent(createAcademicUploadQueue(1,3,[v3]),{...v3,content_sha256:'c'.repeat(64)}),/farklı içerik/);
 assert.throws(()=>mergeAcademicUploadIntent(createAcademicUploadQueue(1,3,[legacy]),{...legacy,name:'other.pdf'}),/çelişiyor/);
 assert.throws(()=>replaceAcademicUploadIntent(createAcademicUploadQueue(1,3,[v3]),{...v3,uri:'file:///cache/other.pdf'}),/kimliği değiştirilemez/);
});

test('native multi-file picker persists the whole queue before the first upload begins',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/NativeAcademic.tsx'),'utf8');
 const pick=source.slice(source.indexOf('async function pick()'),source.indexOf('const disabled='));
 assert.ok(pick.includes('multiple:true'));
 assert.ok(pick.indexOf('await persistUploadQueue(queue.items)')>=0);
 assert.ok(pick.indexOf('await persistUploadQueue(queue.items)')<pick.indexOf('await processUploadQueue(queue.items)'));
 assert.ok(source.includes('store.setItemAsync(uploadQueueKey,serializeAcademicUploadQueue(queue))'));
 assert.doesNotMatch(source,/SecureStore\.setItemAsync\(uploadKey/);
});

test('native Academic recovery migrates the old single-file intent before deleting it and resumes the queue sequentially',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/NativeAcademic.tsx'),'utf8');
 const restore=source.slice(source.indexOf('async function restoreUpload()'),source.indexOf('async function processUploadQueue('));
 assert.ok(restore.indexOf('await persistUploadQueue(queue?.items||[])')<restore.indexOf('await SecureStore.deleteItemAsync(uploadKey)'));
 assert.ok(restore.includes('mergeAcademicUploadIntent'));
 const process=source.slice(source.indexOf('async function processUploadQueue('),source.indexOf('async function retryUpload('));
 assert.ok(process.includes('for(const original of [...initial])'));
 assert.ok(process.includes('await persistUploadQueue(remaining)'));
 assert.ok(process.includes('bound.content_sha256!'));
});


test('Academic upload queue helper and native screen have no TypeScript parser diagnostics',()=>{
 for(const file of ['../src/academicUploadQueue.ts','../src/NativeAcademic.tsx']){
  const source=fs.readFileSync(path.join(__dirname,file),'utf8');
  const result=ts.transpileModule(source,{fileName:file,reportDiagnostics:true,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}});
  const errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).map(d=>ts.flattenDiagnosticMessageText(d.messageText,' '));
  assert.deepEqual(errors,[],file+': '+errors.join('; '));
 }
});


test('fresh Academic batches avoid a redundant receipt read while recovery always reconciles first',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/NativeAcademic.tsx'),'utf8');
 const pick=source.slice(source.indexOf('async function pick()'),source.indexOf('const disabled='));
 const process=source.slice(source.indexOf('async function processUploadQueue('),source.indexOf('async function retryUpload('));
 assert.ok(pick.includes('isPrivateAcademicCacheUri(asset.uri)'));
 assert.ok(pick.includes('await processUploadQueue(queue.items,false)'));
 assert.ok(process.includes('reconcileFirst=true'));
 assert.ok(process.includes('if(reconcileFirst&&await reconcileUpload(pending))'));
});
