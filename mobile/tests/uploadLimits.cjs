const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);

const MIB=1024*1024;
const limits=require('../src/uploadLimits.ts');
test('native and backend upload budgets use the shared binary MiB contract',()=>{
 assert.equal(limits.CLINICAL_MEDIA_MAX_FILES,12);
 assert.equal(limits.CLINICAL_MEDIA_MAX_FILE_BYTES,12*MIB);
 assert.equal(limits.CLINICAL_MEDIA_MAX_BATCH_BYTES,96*MIB);
 assert.equal(limits.ANALYSIS_MAX_IMAGES,4);
 assert.equal(limits.ANALYSIS_MAX_IMAGE_BYTES,15*MIB);
 assert.equal(limits.ANALYSIS_MAX_BATCH_BYTES,48*MIB);
});

function loadNativeFiles(sizeByUri){
 const source=fs.readFileSync(require.resolve('../src/nativeAnalysisFiles.ts'),'utf8');
 const output=ts.transpileModule(source,{fileName:'nativeAnalysisFiles.ts',compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 const exports={},deleted=[],encrypted=[];
 const fsApi={cacheDirectory:'file:///cache/',getInfoAsync:async uri=>({exists:true,size:sizeByUri.get(uri)??1024}),deleteAsync:async uri=>deleted.push(uri)};
 const vault={
  cleanupStaleClinicalMediaTemps:async()=>{},
  deleteClinicalMediaTemp:async uri=>deleted.push(uri),
  deleteClinicalMediaVaultFile:async uri=>deleted.push(uri),
  decryptClinicalMediaFile:async uri=>{const temp='file:///cache/decrypted-'+encrypted.length+'.png';return temp},
  encryptClinicalMediaFile:async uri=>{const target='file:///vault/'+encrypted.length+'.dai';encrypted.push(target);return target},
  validateClinicalMediaVaultFile:async()=>{}
 };
 vm.runInNewContext(output,{exports,Error,require:name=>name==='expo-file-system/legacy'?fsApi:name==='./analysisApi'?{normalizeAnalysisImages:items=>items}:name==='./clinicalMediaVault'?vault:name==='./uploadLimits'?limits:{}});
 return {api:exports,deleted,encrypted};
}

test('native analysis staging rejects actual aggregate bytes above 48 MiB and cleans encrypted files',async()=>{
 const sizes=new Map(Array.from({length:4},(_,i)=>['file:///source/'+i+'.png',13*MIB]));
 const h=loadNativeFiles(sizes);
 await assert.rejects(h.api.cacheAnalysisImages(Array.from({length:4},(_,i)=>({uri:'file:///source/'+i+'.png',name:i+'.png',type:'image/png'})),1,9),/48 MiB/);
 assert.equal(h.encrypted.length,3);
 assert.equal(h.deleted.length,3);
});

test('native analysis staging accepts exactly 48 MiB across four files',async()=>{
 const values=[15,15,15,3],sizes=new Map(values.map((n,i)=>['file:///source/'+i+'.png',n*MIB]));
 const h=loadNativeFiles(sizes);
 const result=await h.api.cacheAnalysisImages(values.map((_,i)=>({uri:'file:///source/'+i+'.png',name:i+'.png',type:'image/png'})),1,9);
 assert.equal(result.length,4);
 assert.equal(h.encrypted.length,4);
});

test('restored encrypted analysis drafts are measured after decryption before upload',async()=>{
 const sizes=new Map(Array.from({length:4},(_,i)=>['file:///cache/decrypted-'+i+'.png',13*MIB]));
 const h=loadNativeFiles(sizes);
 const images=Array.from({length:4},(_,i)=>({uri:'file:///vault/'+i+'.dai',encryptedUri:'file:///vault/'+i+'.dai',name:i+'.png',type:'image/png'}));
 await assert.rejects(h.api.prepareAnalysisUploadImages(images,1,9),/48 MiB/);
 assert.equal(h.deleted.length,4);
});
