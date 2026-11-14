const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../App.tsx'),'utf8');
test('patient profile appointment action carries selected patient identity',()=>{
 assert.match(source,/title="Randevu"[^\n]*navigate\("Program",\{patientId:p\.id\}\)/);
});
test('program route passes patient context to native screen',()=>{
 assert.match(source,/name="Program"[^\n]*<Program token=\{token\} patientId=\{route\.params\?\.patientId\}/);
});
test('patient appointment uses verified patient ID and appointment event type',()=>{
 assert.match(source,/getPatient\(token,patientId\)/);
 assert.match(source,/event_type:patientId!==undefined\?"APPOINTMENT":"PERSONAL"/);
 assert.match(source,/patient_id:linkedPatient\.id/);
 assert.match(source,/patientId!==undefined&&!linkedPatient/);
});
