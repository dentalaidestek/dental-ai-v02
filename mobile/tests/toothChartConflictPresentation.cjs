const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');

require.extensions['.ts']=(module,filename)=>module._compile(
  ts.transpileModule(fs.readFileSync(filename,'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
  }).outputText,
  filename
);

const {
  toothChartConflictTitle,
  toothChartConflictMessage
}=require('../src/toothChartConflictPresentation.ts');

test('whole-tooth conflict identifies only the selected FDI tooth',()=>{
  assert.equal(toothChartConflictTitle({
    kind:'tooth',toothNumber:'36',refreshed:false
  }),'Diş 36');
});

test('surface conflict uses the anatomical surface label',()=>{
  assert.equal(toothChartConflictTitle({
    kind:'surface',toothNumber:'11',surface:'INCISAL',refreshed:false
  }),'Diş 11 · İnsizal');
  assert.equal(toothChartConflictTitle({
    kind:'surface',toothNumber:'36',surface:'OCCLUSAL',refreshed:false
  }),'Diş 36 · Oklüzal');
});

test('unrefreshed conflict never suggests retrying with the stale revision',()=>{
  const message=toothChartConflictMessage({
    kind:'tooth',toothNumber:'36',refreshed:false
  });
  assert.match(message,/başka bir oturumda değiştirildi/);
  assert.match(message,/önce güncel kaydı yükleyin/);
  assert.match(message,/tekrar kaydetme kapalı/);
});

test('refreshed conflict shows the server snapshot and says the local draft is preserved',()=>{
  const message=toothChartConflictMessage({
    kind:'surface',toothNumber:'11',surface:'INCISAL',refreshed:true,
    latestStatus:'FILLING',latestNote:'Remote clinical note'
  });
  assert.match(message,/Sunucudaki son durum: Dolgu/);
  assert.match(message,/Not: Remote clinical note/);
  assert.match(message,/Formdaki taslağınız korunuyor/);
  assert.match(message,/yeniden kaydedebilirsiniz/);
});

test('missing and unknown server values remain explicit rather than being guessed',()=>{
  assert.match(toothChartConflictMessage({
    kind:'tooth',toothNumber:'11',refreshed:true,latestStatus:null,latestNote:null
  }),/Kayıtlı durum yok/);
  assert.match(toothChartConflictMessage({
    kind:'tooth',toothNumber:'11',refreshed:true,latestStatus:'UNRECOGNIZED',latestNote:''
  }),/Durum bilinmiyor/);
  assert.match(toothChartConflictMessage({
    kind:'tooth',toothNumber:'11',refreshed:true,latestStatus:'HEALTHY',latestNote:''
  }),/Not yok/);
});
