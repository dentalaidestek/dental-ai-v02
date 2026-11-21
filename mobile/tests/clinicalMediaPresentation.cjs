const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');

function loadPresentation(){
 const source=fs.readFileSync(path.join(__dirname,'../src/clinicalMediaPresentation.ts'),'utf8');
 const compiled=ts.transpileModule(source,{fileName:'clinicalMediaPresentation.ts',compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 const exports={};
 vm.runInNewContext(compiled,{exports,Error,Number,RegExp,require:name=>{
  if(name==='./api')return{API_BASE:'https://dentalai.tr/api/mobile/v1'};
  throw Error('Unexpected import '+name);
 }});
 return exports;
}

test('private clinical image cache identity changes across authenticated owner and session scopes',()=>{
 const api=loadPresentation();
 const oldKey=api.clinicalMediaImageKey('opaque-scope-1',42,'thumbnail');
 const newKey=api.clinicalMediaImageKey('opaque-scope-2',42,'thumbnail');
 const originalKey=api.clinicalMediaImageKey('opaque-scope-1',42,'original');
 assert.notEqual(oldKey,newKey);
 assert.notEqual(oldKey,originalKey);
 assert.equal(oldKey.includes('token'),false,'React image keys must never contain a bearer token');
 assert.throws(()=>api.clinicalMediaImageKey('owner',0,'thumbnail'),/kapsamı doğrulanamadı/);
 assert.throws(()=>api.clinicalMediaImageKey('owner',42,'unknown'),/kapsamı doğrulanamadı/);
});

test('private clinical image requests carry the current bearer token and force revalidation',()=>{
 const api=loadPresentation();
 const uri='https://dentalai.tr/api/mobile/v1/patients/8/media/42/thumbnail';
 const source=api.clinicalMediaImageSource(uri,'synthetic-bearer-token');
 assert.equal(source.uri,uri);
 assert.equal(source.headers.Authorization,'Bearer synthetic-bearer-token');
 assert.equal(source.cache,'reload');
});

test('private clinical image source rejects external, malformed and unscoped URLs',()=>{
 const api=loadPresentation();
 for(const uri of [
  'https://attacker.invalid/api/mobile/v1/patients/8/media/42/thumbnail',
  'https://dentalai.tr/api/mobile/v1/patients/8/media/42/thumbnail?shared=1',
  'https://dentalai.tr/api/mobile/v1/patients/8/media/42',
  'https://dentalai.tr/api/mobile/v1/patients/8/media/0/file'
 ]){
  assert.throws(()=>api.clinicalMediaImageSource(uri,'token'),/adresi veya oturumu doğrulanamadı/);
 }
 assert.throws(()=>api.clinicalMediaImageSource('https://dentalai.tr/api/mobile/v1/patients/8/media/42/file',''),/adresi veya oturumu doğrulanamadı/);
});

test('native clinical gallery uses scoped keys and private image source helper on every remote image',()=>{
 const native=fs.readFileSync(path.join(__dirname,'../src/NativePatientMedia.tsx'),'utf8');
 assert.match(native,/clinicalMediaImageKey\(imageScope,item\.id,'thumbnail'\)/);
 assert.match(native,/clinicalMediaImageKey\(imageScope,preview\.id,'original'\)/);
 assert.match(native,/clinicalMediaImageSource\(preview\.url,token\)/);
 assert.match(native,/keyExtractor=\{item=>clinicalMediaImageKey\(imageScope,item\.id,'thumbnail'\)\}/);
});
