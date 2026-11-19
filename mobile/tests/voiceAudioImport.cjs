const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const {test}=require('node:test');
const api=require('../src/voiceAudioImport.ts');

test('web-supported voice formats resolve to canonical MIME and private-cache extensions',()=>{
 const cases=[
  ['audio/mpeg','exam.mp3','audio/mpeg','mp3'],
  ['audio/wav','exam.wav','audio/wav','wav'],
  ['audio/x-wav','exam.wav','audio/wav','wav'],
  ['audio/webm','exam.webm','audio/webm','webm'],
  ['audio/ogg','exam.ogg','audio/ogg','ogg'],
  ['audio/mp4','exam.m4a','audio/mp4','m4a'],
  ['audio/x-m4a','exam.m4a','audio/mp4','m4a'],
  ['audio/m4a','exam.m4a','audio/mp4','m4a'],
  ['application/octet-stream','exam.m4a','audio/mp4','m4a'],
  [null,'exam.mp4','audio/mp4','m4a']
 ];
 for(const [mime,name,expectedMime,extension] of cases){
  assert.deepEqual(api.resolveVoiceAudioAsset(mime,name),{mime:expectedMime,extension});
 }
});

test('voice import rejects MIME and extension mismatches and unsupported formats',()=>{
 assert.throws(()=>api.resolveVoiceAudioAsset('audio/mpeg','exam.wav'),/eşleşmiyor/);
 assert.throws(()=>api.resolveVoiceAudioAsset('video/mp4','exam.m4a'),/MP3, WAV/);
 assert.throws(()=>api.resolveVoiceAudioAsset(null,'exam.aac'),/biçimi doğrulanamadı/);
 assert.throws(()=>api.resolveVoiceAudioAsset('audio/aac','exam.aac'),/MP3, WAV/,'audio/* picker discovery must still reject unsupported AAC');
 assert.equal(api.isVoiceAudioExtensionForMime('mp3','audio/mpeg'),true);
 assert.equal(api.isVoiceAudioExtensionForMime('wav','audio/mpeg'),false);
});

test('voice import enforces the same 100-byte and 8-MiB contract as web',()=>{
 assert.equal(api.validateVoiceAudioBytes(100),100);
 assert.equal(api.validateVoiceAudioBytes(8*1024*1024),8*1024*1024);
 assert.throws(()=>api.validateVoiceAudioBytes(99),/100 bayttan/);
 assert.throws(()=>api.validateVoiceAudioBytes(8*1024*1024+1),/8 MB/);
});

test('voice import enforces a finite positive duration no longer than 90.5 seconds',()=>{
 assert.equal(api.validateVoiceAudioDuration(90.5),90.5);
 assert.equal(api.validateVoiceAudioDuration(45),45);
 for(const duration of [0,-1,90.51,Infinity,NaN,'90'])assert.throws(()=>api.validateVoiceAudioDuration(duration),/90 saniye/);
});
