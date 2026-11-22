const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');

require.extensions['.ts']=(module,filename)=>{
 const output=ts.transpileModule(fs.readFileSync(filename,'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
 }).outputText;
 module._compile(output,filename);
};

const {
 patientMediaSelectAllIds,
 patientMediaSelectAllLabel,
}=require('../src/patientMediaSelection.ts');

const visible=[11,12,13,14,15,16];

test('partial native selection selects the same first capped set as the web gallery',()=>{
 assert.deepEqual(patientMediaSelectAllIds([],visible,4),[11,12,13,14]);
 assert.deepEqual(patientMediaSelectAllIds([12],visible,4),[11,12,13,14]);
 assert.deepEqual(patientMediaSelectAllIds([12,15],visible,4),[11,12,13,14]);
 assert.equal(patientMediaSelectAllLabel([12],visible,4),'İlk 4 Görseli Seç');
});

test('select-all clears only when the selected count already equals the web target count',()=>{
 assert.deepEqual(patientMediaSelectAllIds([11,12,13,14],visible,4),[]);
 assert.deepEqual(patientMediaSelectAllIds([12,13,14,15],visible,4),[]);
 assert.equal(patientMediaSelectAllLabel([12,13,14,15],visible,4),'Seçimi kaldır');
});

test('a gallery with fewer images selects all available images and then clears them',()=>{
 assert.deepEqual(patientMediaSelectAllIds([], [41,42],4),[41,42]);
 assert.deepEqual(patientMediaSelectAllIds([41,42], [41,42],4),[]);
 assert.equal(patientMediaSelectAllLabel([], [41,42],4),'İlk 4 Görseli Seç');
 assert.equal(patientMediaSelectAllLabel([41,42], [41,42],4),'Seçimi kaldır');
});

test('selection is capped, deduplicated and rejects an invalid limit',()=>{
 assert.deepEqual(patientMediaSelectAllIds([], [1,2,2,3,4,5,6],4),[1,2,3,4]);
 assert.throws(()=>patientMediaSelectAllIds([],visible,0),/seçim sınırı/);
 assert.throws(()=>patientMediaSelectAllLabel([],visible,1.5),/seçim sınırı/);
});
