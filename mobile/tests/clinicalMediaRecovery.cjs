const ts=require('typescript'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
}).outputText,f);
const {classifyClinicalMediaUploadFailure}=require('../src/clinicalMediaRecovery.ts');

test('missing receipt key is a known pre-persistence configuration rejection',()=>{
 assert.equal(classifyClinicalMediaUploadFailure(503), 'CONFIGURATION');
});

test('transport loss and conflict stay ambiguous until the server receipt is checked',()=>{
 for(const status of [0,408,409,429,500,502])assert.equal(classifyClinicalMediaUploadFailure(status),'UNCERTAIN');
 assert.equal(classifyClinicalMediaUploadFailure(undefined),'UNCERTAIN');
});

test('explicit validation and ownership rejections are non-commits',()=>{
 for(const status of [400,403,404,413,422])assert.equal(classifyClinicalMediaUploadFailure(status),'REJECTED');
});

test('local encrypted-vault failures never claim that the server may have stored the file',()=>{
 for(const code of ['SOURCE_MISSING','VAULT_MISSING','KEY_MISSING','KEY_INVALID','AUTH_FAILED','INVALID_VAULT'])
  assert.equal(classifyClinicalMediaUploadFailure(undefined,code),'LOCAL');
});

test('the native gallery explains a missing server key and keeps the encrypted draft',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/failure==='CONFIGURATION'/);
 assert.match(source,/Şifreli taslak cihazda korunuyor/);
 assert.match(source,/Sunucu ayarı düzelene kadar taslağı silmeyin/);
});
