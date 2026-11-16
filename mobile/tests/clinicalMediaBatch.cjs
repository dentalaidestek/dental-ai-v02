const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');

require.extensions['.ts']=(module,filename)=>{
 const source=fs.readFileSync(filename,'utf8');
 const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 module._compile(output,filename);
};

const {ensureClinicalMediaBatchId,CLINICAL_MEDIA_BATCH_ID_PATTERN}=require('../src/clinicalMediaBatch.ts');

test('keeps a persisted batch identity unchanged for retries and app restarts',()=>{
 const saved='stable-clinical-media-batch-0001';
 assert.equal(ensureClinicalMediaBatchId(saved,()=>{throw Error('must not regenerate')}),saved);
 assert.equal(CLINICAL_MEDIA_BATCH_ID_PATTERN.test(saved),true);
});

test('assigns a valid batch identity once when migrating a legacy encrypted draft',()=>{
 let generated=0;
 const create=()=>{generated++;return 'migrated-clinical-media-batch-0001'};
 const first=ensureClinicalMediaBatchId(undefined,create);
 const restored=ensureClinicalMediaBatchId(first,create);
 assert.equal(first,restored);
 assert.equal(generated,1);
});

test('rejects malformed persisted batch identities instead of silently creating a new quota group',()=>{
 for(const value of ['short','contains spaces','bad\\u0000id',42,{}]){
  assert.throws(()=>ensureClinicalMediaBatchId(value,()=> 'replacement-clinical-media-batch-0001'),/yükleme grubu doğrulanamadı/);
 }
});

test('fails closed if the UUID provider returns an invalid batch identity',()=>{
 assert.throws(()=>ensureClinicalMediaBatchId(undefined,()=> 'short'),/yükleme grubu oluşturulamadı/);
});
