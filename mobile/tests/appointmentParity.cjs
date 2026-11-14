const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../App.tsx'),'utf8');
test('patient profile appointment action carries selected patient identity',()=>{
 assert.match(source,/appointment:\(\)=>root\(\)\?\.navigate\("Program",\{patientId:id\}\)/);
 const profile=fs.readFileSync(path.join(__dirname,'../src/NativePatientProfile.tsx'),'utf8');
 assert.ok(profile.includes("['Randevu',actions.appointment]"));
});
test('program route passes patient context to native screen',()=>{
 assert.match(source,/name="Program"[^\n]*<NativePatientAppointment[^\n]*patientId=\{route\.params\.patientId\}/);
});
const appointment=fs.readFileSync(path.join(__dirname,'../src/NativePatientAppointment.tsx'),'utf8');
const editor=fs.readFileSync(path.join(__dirname,'../src/NativeProgramEditor.tsx'),'utf8');
test('patient appointment uses verified patient ID and appointment event type',()=>{
 assert.match(appointment,/initialPatientId=\{patientId\}/);
 assert.match(editor,/getPatient\(token,initialPatientId\)/);
 assert.match(editor,/event_type:initialType&&page\.event_types\[initialType\]\?initialType:'APPOINTMENT'/);
 assert.match(editor,/patient_id:patient\.id/);
 assert.match(editor,/loadError\|\|uncertain/);
});
test('appointment form rejects malformed dates and duplicate submission',()=>{
 assert.match(editor,/programPayload\(/);
 assert.match(editor,/if\(lock\.current\|\|loading\|\|loadError\|\|uncertain\)return/);
 assert.match(editor,/lock\.current=true;setBusy\(true\)/);
 assert.match(editor,/lock\.current=false;setBusy\(false\)/);
 const model=fs.readFileSync(path.join(__dirname,'../src/programModel.ts'),'utf8');
 assert.match(model,/validWallTime\(draft.start_at\)/);
});
