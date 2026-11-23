// Sesli muayene kaynak akışları: resmî dizin araması + kaynaklı klinik kontrol noktaları.
// Web voice-exam session bölümünün (voice-exam.js sources/clinical) birebir mobil karşılığı.
const fs=require('node:fs'),assert=require('node:assert/strict'),{test}=require('node:test');
const src={
 voice:fs.readFileSync(__dirname+'/../src/voiceApi.ts','utf8'),
 approval:fs.readFileSync(__dirname+'/../src/NativeVoiceApproval.tsx','utf8'),
 backend:fs.readFileSync(__dirname+'/../../app/mobile_api.py','utf8'),
 web:fs.readFileSync(__dirname+'/../../app/static/voice-exam.js','utf8'),
};

test('mobile exposes the official source directory with the same payload contract as web',()=>{
 assert.ok(src.voice.includes('export async function searchVoiceSources'));
 assert.ok(src.voice.includes('voice-exam/sources`'));
 assert.ok(src.voice.includes('{query:query.trim()}'));
 // 3-400 karakter sözleşmesi web SourceInput ile aynı.
 assert.ok(src.voice.includes('query.trim().length<3||query.trim().length>400'));
 assert.ok(src.voice.includes('clinical_use===false'));
});

test('mobile clinical assessment mirrors the web consent and identity cleanup',()=>{
 assert.ok(src.voice.includes('export async function assessVoiceClinical'));
 assert.ok(src.voice.includes('{context:clean,consent:true}'));
 // Web panel ile aynı temizlik: randevu ve kimlik alanları değerlendirmeye girmez.
 assert.ok(src.voice.includes('delete clean.appointment;'));
 assert.ok(src.voice.includes('delete (clean.fields as Record<string,unknown>).first_name'));
 assert.ok(src.voice.includes('delete (clean.fields as Record<string,unknown>).last_name'));
 assert.ok(src.web.includes('/voice-exam/clinical'));
 assert.ok(src.web.includes("delete clinical.appointment"));
});

test('approval card surfaces both source tools without touching the save flow',()=>{
 assert.ok(src.approval.includes('Kaynak Kontrolü'));
 assert.ok(src.approval.includes('Klinik Kaynak Kontrolü'));
 assert.ok(src.approval.includes('Kaynak Ara'));
 assert.ok(src.approval.includes('assessVoiceClinical(token,patientId,voiceClinicalContext(review.review))'));
 assert.ok(src.approval.includes('searchVoiceSources(token,patientId,sourcesQuery)'));
 assert.ok(src.approval.includes('Doğrulanmış bir kontrol noktası üretilemedi'));
 assert.ok(src.approval.includes('dizin eşleşmesi bulunamadı'));
 // Kayıt akışı ve onay anahtarı değişmedi.
 assert.ok(src.approval.includes("key=`dai.voice.apply.${userId}.${patientId}`"));
 assert.ok(src.approval.includes("applyVoiceReview(token,patientId,payload)"));
});

test('mobile backend delegates to the same web engines with no second implementation',()=>{
 assert.ok(src.backend.includes('"/patients/{patient_id}/voice-exam/sources"'));
 assert.ok(src.backend.includes('"/patients/{patient_id}/voice-exam/clinical"'));
 assert.ok(src.backend.includes('from app.voice_exam_sources import retrieve'));
 assert.ok(src.backend.includes('from app.voice_exam_clinical import assess'));
 assert.ok(src.backend.includes('VOICE_CLINICAL_CONSENT_REQUIRED'));
 assert.ok(src.backend.includes('VOICE_CLINICAL_UNAVAILABLE'));
 assert.ok(src.backend.includes('run_in_threadpool(_mobile_voice_patient, user, patient_id)'));
 assert.ok(src.voice.includes('export const voiceClinicalContext=contextFromVoiceReview'));
});
