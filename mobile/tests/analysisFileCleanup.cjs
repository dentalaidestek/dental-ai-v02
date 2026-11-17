const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test');
const compile=f=>ts.transpileModule(fs.readFileSync(require.resolve(f),'utf8'),{fileName:f,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const encrypted='file:///documents/dai-clinical-vault/1/8/legacy.dai';
const legacy='file:///cache/dai-analysis-legacy-12345678.png';
function harness({deleteCache,deleteVault}={}){
 const files=new Map([[legacy,{exists:true,size:512}]]),deleted=[];
 const fileSystem={
  cacheDirectory:'file:///cache/',
  getInfoAsync:async uri=>files.has(uri)?{exists:true,size:files.get(uri).size,modificationTime:Date.now()/1000}:{exists:false,size:0},
  deleteAsync:async(uri)=>{if(deleteCache)await deleteCache(uri);files.delete(uri);deleted.push(uri)},
  readDirectoryAsync:async()=>Array.from(files.keys()).map(uri=>uri.slice('file:///cache/'.length)),
  writeAsStringAsync:async()=>{},
  readAsStringAsync:async()=>''
 };
 const vault={
  cleanupStaleClinicalMediaTemps:async()=>{},
  encryptClinicalMediaFile:async()=>encrypted,
  validateClinicalMediaVaultFile:async()=>{},
  deleteClinicalMediaVaultFile:async uri=>{if(deleteVault)await deleteVault(uri);deleted.push(uri)},
  decryptClinicalMediaFile:async()=>{const uri='file:///cache/dai-clinical-upload-temp.png';files.set(uri,{exists:true,size:512});return uri},
  deleteClinicalMediaTemp:async uri=>{if(deleteCache)await deleteCache(uri);files.delete(uri);deleted.push(uri)}
 };
 const exports={};
 vm.runInNewContext(compile('../src/nativeAnalysisFiles.ts'),{
  exports,Error,Promise,
  require:name=>name==='expo-file-system/legacy'?fileSystem:name==='./clinicalMediaVault'?vault:name==='./analysisApi'?{normalizeAnalysisImages:items=>items}:name==='./uploadLimits'?{ANALYSIS_MAX_IMAGE_BYTES:15*1024*1024,ANALYSIS_MAX_BATCH_BYTES:48*1024*1024}:{}
 });
 return{api:exports,files,deleted};
}
test('legacy plaintext URI remains durable until the encrypted intent can be stored',async()=>{
 const h=harness();
 const result=await h.api.ensureEncryptedAnalysisImages([{uri:legacy,name:'old.png',type:'image/png'}],1,8);
 assert.equal(result[0].uri,encrypted);
 assert.equal(result[0].encryptedUri,encrypted);
 assert.equal(result[0].legacyUri,legacy);
 assert.ok(h.files.has(legacy),'migration must not delete the only old reference before SecureStore is updated');
 assert.deepEqual(h.deleted,[]);
});
test('legacy cache deletion failures remain visible to the caller',async()=>{
 const h=harness({deleteCache:async()=>{throw Error('Synthetic legacy deletion failure')}});
 await assert.rejects(
  h.api.clearLegacyAnalysisSources([{uri:encrypted,encryptedUri:encrypted,legacyUri:legacy}]),
  /Synthetic legacy deletion failure/
 );
 assert.ok(h.files.has(legacy),'failed cleanup must not erase the only retained legacy source');
});
test('encrypted vault cleanup failure is not silently swallowed',async()=>{
 const h=harness({deleteVault:async()=>{throw Error('Synthetic vault deletion failure')}});
 await assert.rejects(
  h.api.clearAnalysisImages([{uri:encrypted,encryptedUri:encrypted,name:'old.png',type:'image/png'}]),
  /Synthetic vault deletion failure/
 );
});
test('final cleanup removes encrypted and legacy copies but never the picker preview',async()=>{
 const h=harness();
 await h.api.clearAnalysisImages([{uri:encrypted,encryptedUri:encrypted,legacyUri:legacy,previewUri:'file:///photos/original.png',name:'old.png',type:'image/png'}]);
 assert.ok(h.deleted.includes(encrypted));
 assert.ok(h.deleted.includes(legacy));
 assert.ok(!h.deleted.includes('file:///photos/original.png'));
});

test('plaintext upload-temp cleanup failures are surfaced instead of silently ignored',async()=>{
 const h=harness({deleteCache:async uri=>{if(uri.includes('dai-clinical-upload-temp'))throw Error('Synthetic plaintext temp cleanup failure')}});
 const prepared=await h.api.prepareAnalysisUploadImages([{uri:encrypted,encryptedUri:encrypted,name:'old.png',type:'image/png'}],1,8);
 await assert.rejects(prepared.cleanup(),/Synthetic plaintext temp cleanup failure/);
});
