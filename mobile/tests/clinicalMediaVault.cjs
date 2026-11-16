const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const noble=require('@noble/ciphers/chacha.js');
const utils=require('@noble/ciphers/utils.js');
const source=fs.readFileSync(require.resolve('../src/clinicalMediaVault.ts'),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
function harness(){
 const files=new Map(),keys=new Map(),dirs=new Set(['file:///documents/','file:///cache/']);
 let sequence=0;
 const fsApi={
  documentDirectory:'file:///documents/',cacheDirectory:'file:///cache/',
  copyAsync:async({from,to})=>{if(!files.has(from))throw Error('missing source');files.set(to,{...files.get(from)})},
  getInfoAsync:async uri=>{const file=files.get(uri);return file?{exists:true,size:file.size,modificationTime:file.modificationTime}:{exists:false,size:0}},
  readAsStringAsync:async uri=>{if(!files.has(uri))throw Error('missing file');return files.get(uri).data},
  writeAsStringAsync:async(uri,data,options={})=>{files.set(uri,{data,size:options.encoding==='base64'?Buffer.from(data,'base64').length:Buffer.byteLength(data),modificationTime:Date.now()/1000})},
  makeDirectoryAsync:async uri=>dirs.add(uri),
  deleteAsync:async(uri)=>{files.delete(uri)},
  readDirectoryAsync:async uri=>[...files.keys()].filter(path=>path.startsWith(uri)).map(path=>path.slice(uri.length))
 };
 const secure={WHEN_UNLOCKED_THIS_DEVICE_ONLY:'device-only',getItemAsync:async key=>keys.get(key)||null,setItemAsync:async(key,value)=>keys.set(key,value),deleteItemAsync:async key=>keys.delete(key)};
 const exports={};
 vm.runInNewContext(code,{exports,Error,Date,Number,Math,Uint8Array,Array,Promise,RegExp,JSON,String,Set,Map,require:name=>name==='expo-file-system/legacy'?fsApi:name==='expo-secure-store'?secure:name==='expo-crypto'?{randomUUID:()=> 'synthetic-vault-'+(++sequence)}:name==='@noble/ciphers/chacha.js'?noble:name==='@noble/ciphers/utils.js'?utils:require(name)});
 return {api:exports,files,keys,fsApi};
}
const original=Buffer.from('synthetic dental image bytes; no patient data','utf8');
function addSource(h,uri='file:///photos/synthetic.png',bytes=original){h.files.set(uri,{data:bytes.toString('base64'),size:bytes.length,modificationTime:Date.now()/1000});return uri;}
test('clinical media is encrypted in persistent app storage and round-trips only through a temporary file',async()=>{
 const h=harness(),sourceUri=addSource(h),encrypted=await h.api.encryptClinicalMediaFile(sourceUri,7,8,1024);
 assert.match(encrypted,/file:\/\/\/documents\/dai-clinical-vault\/7\/8\/.+\.dai$/);
 assert.notEqual(h.files.get(encrypted).data,original.toString('base64'));
 assert.ok(!h.files.has('file:///cache/dai-clinical-stage-synthetic-vault-1.bin'));
 const temp=await h.api.decryptClinicalMediaFile(encrypted,7,8,'synthetic.png');
 assert.equal(Buffer.from(h.files.get(temp).data,'base64').toString('utf8'),original.toString('utf8'));
 await h.api.deleteClinicalMediaTemp(temp);
 assert.equal(h.files.has(temp),false);
 assert.equal(h.files.has(sourceUri),true,'the OS picker source is never deleted');
});
test('encrypted media is bound to the owning user and patient scope',async()=>{
 const h=harness(),sourceUri=addSource(h),encrypted=await h.api.encryptClinicalMediaFile(sourceUri,7,8,1024);
 await assert.rejects(()=>h.api.decryptClinicalMediaFile(encrypted,9,8,'synthetic.png'),/yolu doğrulanamadı/);
 await assert.rejects(()=>h.api.decryptClinicalMediaFile(encrypted,7,10,'synthetic.png'),/yolu doğrulanamadı/);
 assert.equal(await h.api.isClinicalMediaVaultUri(encrypted,7,8),true);
 assert.equal(await h.api.isClinicalMediaVaultUri(encrypted,9,8),false);
});
test('tampered ciphertext fails authentication and never returns plaintext',async()=>{
 const h=harness(),sourceUri=addSource(h),encrypted=await h.api.encryptClinicalMediaFile(sourceUri,7,8,1024);
 const file=h.files.get(encrypted),chars=file.data.split('');chars[8]=chars[8]==='A'?'B':'A';file.data=chars.join('');h.files.set(encrypted,file);
 await assert.rejects(()=>h.api.decryptClinicalMediaFile(encrypted,7,8,'synthetic.png'),/şifresi doğrulanamadı/);
});
test('file size is checked before encryption and temporary staging is removed on failure',async()=>{
 const h=harness(),sourceUri=addSource(h,'file:///photos/large.png',Buffer.alloc(2048,7));
 await assert.rejects(()=>h.api.encryptClinicalMediaFile(sourceUri,7,8,1024),/boyutu/);
 assert.equal([...h.files.keys()].some(uri=>uri.includes('dai-clinical-stage-')),false);
 assert.equal([...h.files.keys()].some(uri=>uri.includes('dai-clinical-vault')),false);
});
test('stale plaintext staging and upload files are cleaned without touching recent or source files',async()=>{
 const h=harness(),sourceUri=addSource(h),old='file:///cache/dai-clinical-upload-old.png',recent='file:///cache/dai-clinical-upload-recent.png',stage='file:///cache/dai-clinical-stage-old.bin';
 h.files.set(old,{data:'old',size:3,modificationTime:Date.now()/1000-7200});
 h.files.set(stage,{data:'old',size:3,modificationTime:Date.now()/1000-7200});
 h.files.set(recent,{data:'recent',size:6,modificationTime:Date.now()/1000});
 await h.api.cleanupStaleClinicalMediaTemps();
 assert.equal(h.files.has(old),false);assert.equal(h.files.has(stage),false);assert.equal(h.files.has(recent),true);assert.equal(h.files.has(sourceUri),true);
});
test('vault deletion rejects paths outside its dedicated encrypted directory',async()=>{
 const h=harness();
 await assert.rejects(()=>h.api.deleteClinicalMediaVaultFile('file:///documents/private-patient.jpg'),/Dental AI güvenli/);
});


test('rejects oversized picker sources before copying plaintext into cache staging',async()=>{
 const h=harness(),sourceUri=addSource(h,'file:///photos/oversized.png',Buffer.alloc(2048,7));
 let copies=0;const originalCopy=h.fsApi.copyAsync;
 h.fsApi.copyAsync=async value=>{copies++;return originalCopy(value)};
 await assert.rejects(()=>h.api.encryptClinicalMediaFile(sourceUri,7,8,1024),/boyutu/);
 assert.equal(copies,0,'known oversized source must be rejected before a cache copy');
 assert.equal([...h.files.keys()].some(uri=>uri.includes('dai-clinical-stage-')),false);
});

test('falls back to staged-byte validation when an Android content provider cannot stat its source',async()=>{
 const h=harness(),sourceUri=addSource(h,'content://media/opaque/42',Buffer.from('small synthetic image'));
 const originalInfo=h.fsApi.getInfoAsync;
 h.fsApi.getInfoAsync=async uri=>uri===sourceUri?{exists:false,size:0}:originalInfo(uri);
 const encrypted=await h.api.encryptClinicalMediaFile(sourceUri,7,8,1024);
 assert.equal(h.files.has(encrypted),true);
 assert.equal([...h.files.keys()].some(uri=>uri.includes('dai-clinical-stage-')),false);
});


test('removes crash-orphaned encrypted files while retaining pending files and other patient scopes',async()=>{
 const h=harness(),sourceUri=addSource(h);
 const retained=await h.api.encryptClinicalMediaFile(sourceUri,7,8,1024);
 const orphan=await h.api.encryptClinicalMediaFile(sourceUri,7,8,1024);
 const otherPatient=await h.api.encryptClinicalMediaFile(sourceUri,7,9,1024);
 const removed=await h.api.cleanupOrphanedClinicalMediaVaultFiles(7,8,[retained]);
 assert.equal(removed,1);
 assert.equal(h.files.has(retained),true,'the durable pending intent keeps its encrypted file');
 assert.equal(h.files.has(orphan),false,'unreferenced crash residue is deleted');
 assert.equal(h.files.has(otherPatient),true,'cleanup never crosses patient scope');
});

test('orphan cleanup fails closed on invalid retained references',async()=>{
 const h=harness(),sourceUri=addSource(h),orphan=await h.api.encryptClinicalMediaFile(sourceUri,7,8,1024);
 await assert.rejects(()=>h.api.cleanupOrphanedClinicalMediaVaultFiles(7,8,['file:///documents/private.dai']),/kapsamı doğrulanamadı/);
 assert.equal(h.files.has(orphan),true,'invalid intent must not authorize deletion');
});

test('orphan cleanup leaves files untouched when scoped directory listing fails',async()=>{
 const h=harness(),sourceUri=addSource(h),orphan=await h.api.encryptClinicalMediaFile(sourceUri,7,8,1024);
 h.fsApi.readDirectoryAsync=async()=>{throw Error('synthetic storage listing failure')};
 assert.equal(await h.api.cleanupOrphanedClinicalMediaVaultFiles(7,8,[]),0);
 assert.equal(h.files.has(orphan),true);
});


test('native patient media reconciles vault files from the durable pending intent',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.ok(source.includes('cleanupOrphanedClinicalMediaVaultFiles'));
 assert.ok(source.includes('saved?.files.flatMap(file=>file.encryptedUri?[file.encryptedUri]:[])??[]'));
 assert.ok(source.includes('await cleanupOrphanedClinicalMediaVaultFiles(userId,patientId,files.flatMap(file=>file.encryptedUri?[file.encryptedUri]:[]))'));
});
