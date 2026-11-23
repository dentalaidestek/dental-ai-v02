const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');

const helperSource=fs.readFileSync(require.resolve('../src/patientTreatmentPresentation.ts'),'utf8');
const helperCode=ts.transpileModule(helperSource,{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
}).outputText;
const helper={};
vm.runInNewContext(helperCode,{exports:helper,Error,String,RegExp});

test('treatment edit stays closed until every durable clinical mutation gate is clear',()=>{
 const ready={busy:false,profileUncertain:false,treatmentUncertain:false,treatmentIntentReady:true,
  treatmentIntentBlocked:false,hasPendingTreatment:false,patientMutationBlocked:false};
 assert.equal(helper.patientTreatmentCanEdit(ready),true);
 for(const patch of [
  {busy:true},{profileUncertain:true},{treatmentUncertain:true},{treatmentIntentReady:false},
  {treatmentIntentBlocked:true},{hasPendingTreatment:true},{patientMutationBlocked:true}
 ]) assert.equal(helper.patientTreatmentCanEdit({...ready,...patch}),false);
});

test('treatment metadata follows the web history fields without inventing missing values',()=>{
 assert.equal(helper.patientTreatmentToothLabel('36'),'Diş 36');
 assert.equal(helper.patientTreatmentToothLabel('19'),'Diş -');
 assert.equal(helper.patientTreatmentToothLabel(null),'Diş -');
 assert.equal(helper.patientTreatmentDateLabel('20.11.2026'),'20.11.2026');
 assert.equal(helper.patientTreatmentDateLabel('  '),'-');
 assert.equal(helper.patientTreatmentMaterialLabel(' Kompozit '),'Kompozit');
 assert.equal(helper.patientTreatmentMaterialLabel('  '),null);
});

test('native treatment cards preserve web fields and disable edit during unresolved intents',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientProfile.tsx'),'utf8');
 assert.match(source,/patientTreatmentCanEdit/);
 assert.match(source,/disabled=\{!canEditTreatment\}/);
 assert.match(source,/accessibilityState=\{\{disabled:!canEditTreatment\}\}/);
 assert.match(source,/styles\.treatmentCard/);
 assert.match(source,/patientTreatmentToothLabel\(item\.tooth_number\)/);
 assert.match(source,/patientTreatmentDateLabel\(item\.treatment_date\)/);
 assert.match(source,/patientTreatmentMaterialLabel\(item\.material\)/);
 assert.match(source,/item\.result\?\.trim\(\)/);
 assert.match(source,/item\.doctor_note\?\.trim\(\)/);
});
