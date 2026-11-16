const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');

const helperPath=path.join(__dirname,'../src/voiceEvidencePresentation.ts');
const helperSource=fs.readFileSync(helperPath,'utf8');
const compiled=ts.transpileModule(helperSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const exports={};
vm.runInNewContext(compiled,{exports});
const present=exports.voiceEvidencePresentation;

test('current voice extraction displays the exact bounded interview quote',()=>{
 const result=present({quote:'  Hasta: Soğukta kısa süreli ağrı oluyor.  ',origin:'extraction'});
 assert.equal(result.label,'Bu muayenedeki konuşma dayanağı');
 assert.equal(result.quote,'Hasta: Soğukta kısa süreli ağrı oluyor.');
 assert.equal(result.hasEvidence,true);
 assert.equal(result.edited,false);
});

test('previous approved history is never labelled as a current interview statement',()=>{
 const result=present({quote:'Önceki muayenede astım beyanı.',origin:'history',edited:true});
 assert.equal(result.label,'Önceki hekim onaylı kayıttaki dayanak');
 assert.equal(result.quote,'Önceki muayenede astım beyanı.');
 assert.equal(result.edited,true);
});

test('missing evidence is explicit and does not invent a supporting quote',()=>{
 const result=present({quote:null,origin:'extraction'});
 assert.equal(result.quote,'');
 assert.equal(result.hasEvidence,false);
 assert.equal(result.label,'Bu muayenedeki konuşma dayanağı');
});

test('evidence text is trimmed and capped at the backend field bound',()=>{
 const result=present({quote:'  '+'x'.repeat(3500)+'  '});
 assert.equal(result.quote.length,3000);
 assert.equal(result.hasEvidence,true);
});

test('both native review and final approval render provenance before any save',()=>{
 const entry=fs.readFileSync(path.join(__dirname,'../src/VoiceExamEntry.tsx'),'utf8');
 const approval=fs.readFileSync(path.join(__dirname,'../src/NativeVoiceApproval.tsx'),'utf8');
 assert.match(entry,/voiceEvidencePresentation/);
 assert.match(entry,/<VoiceEvidence item=\{item\}\/>/);
 assert.match(approval,/voiceEvidencePresentation/);
 assert.match(approval,/<VoiceEvidence item=\{item\}\/>/);
 assert.match(approval,/<VoiceEvidence item=\{\{quote:t\.quote\}\}\/>/);
 assert.ok(approval.includes("Object.fromEntries(fields.map(name=>[name,review.review.fields?.[name]?.value||'']))"));
});
