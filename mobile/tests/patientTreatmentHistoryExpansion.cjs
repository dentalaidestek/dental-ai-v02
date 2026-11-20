const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');

const helperSource=fs.readFileSync(require.resolve('../src/patientTreatmentHistoryExpansion.ts'),'utf8');
const helperCode=ts.transpileModule(helperSource,{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
}).outputText;
const helper={};
vm.runInNewContext(helperCode,{exports:helper});

test('same-account same-patient refresh preserves an expanded treatment history',()=>{
 assert.equal(helper.patientTreatmentHistoryExpansionAfterRefresh(true,'7:token-a:42','7:token-a:42'),true);
 assert.equal(helper.patientTreatmentHistoryExpansionAfterRefresh(false,'7:token-a:42','7:token-a:42'),false);
});

test('account, session-token or patient changes always collapse the previous history scope',()=>{
 for(const next of ['8:token-a:42','7:token-b:42','7:token-a:43','']){
  assert.equal(helper.patientTreatmentHistoryExpansionAfterRefresh(true,'7:token-a:42',next),false);
 }
 assert.equal(helper.patientTreatmentHistoryExpansionAfterRefresh(true,'',''),false);
});

test('NativePatientProfile preserves expansion on refresh but resets it on scope change',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientProfile.tsx'),'utf8');
 assert.match(source,/patientTreatmentHistoryExpansionAfterRefresh/);
 assert.match(source,/treatmentHistoryScope=useRef\(scope\)/);
 const loadStart=source.indexOf('const load=useCallback(async()=>{');
 const loadEnd=source.indexOf('},[token,patientId,userId]);',loadStart);
 assert.ok(loadStart>=0&&loadEnd>loadStart,'patient profile load callback must be inspectable');
 const load=source.slice(loadStart,loadEnd);
 assert.match(load,/setAllTreatments\(previous=>patientTreatmentHistoryExpansionAfterRefresh\(previous,previousTreatmentScope,scope\)\)/);
 assert.doesNotMatch(load,/setAllTreatments\(false\)/);
 const scopeStart=source.indexOf('useEffect(()=>{mounted.current=true;');
 const scopeEnd=source.indexOf('},[load,userId]);',scopeStart);
 assert.ok(scopeStart>=0&&scopeEnd>scopeStart,'scope reset effect must be inspectable');
 assert.match(source.slice(scopeStart,scopeEnd),/setAllTreatments\(false\)/);
});
