// Mobile-web parity contracts fixed by the audit: login error copy, patient
// delete guard, experts alias filters/ratings, chat report fields, program
// reminder push copy and the performance-info text endpoint.
const fs=require('node:fs'),assert=require('node:assert/strict'),{test}=require('node:test');
const src={
 api:fs.readFileSync(__dirname+'/../../app/mobile_api.py','utf8'),
 push:fs.readFileSync(__dirname+'/../../app/mobile_push.py','utf8'),
 pro:fs.readFileSync(__dirname+'/../../app/mobile_professional_api.py','utf8'),
};

test('mobile login returns the same Turkish copy as the web login for missing/unverified email',()=>{
 assert.ok(src.api.includes("detail='Hesabınızda e-posta adresi bulunmuyor.'"));
 assert.ok(src.api.includes("detail='Doğrulama e-postası gönderilemedi. Lütfen daha sonra tekrar deneyin.'"));
 assert.ok(!src.api.includes('EMAIL_REQUIRED'));
 assert.ok(!src.api.includes('EMAIL_VERIFICATION_SEND_FAILED'));
});

test('mobile patient delete blocks only on an approved anamnesis, like the web route',()=>{
 assert.ok(!src.api.includes('dependent_models = ('));
 assert.ok(!src.api.includes('Hastanın ilişkili klinik kayıtları var. Güvenli silme işlemi henüz desteklenmiyor.'));
 assert.ok(src.api.includes('select(ApprovedAnamnesis.id).where(\n            ApprovedAnamnesis.patient_id == patient_id'));
 assert.ok(src.api.includes('Hastanın hekim onaylı anamnez kayıtları var. Güvenli silme işlemi henüz desteklenmiyor.'));
});

test('mobile experts alias serves specialty/available filters and real review aggregates',()=>{
 assert.ok(src.api.includes('def mobile_experts_alias(user:User=Depends(_mobile_user),q:str=Query("",max_length=120),specialty:str=Query("",max_length=100),available:bool=False)'));
 assert.ok(src.api.includes('if spec:stmt=stmt.where(ExpertProfile.specialty.ilike(f"%{spec}%"))'));
 assert.ok(src.api.includes('if available:stmt=stmt.where(ExpertProfile.availability=="AVAILABLE")'));
 assert.ok(src.api.includes('ExpertReview.expert_user_id,func.count(ExpertReview.id),func.sum(ExpertReview.rating)'));
 assert.ok(src.api.includes('"rating_avg":round(rating_sum/review_count,1) if review_count else None'));
 assert.ok(src.api.includes('"review_count":review_count})'));
});

test('mobile chat context carries chat_reported and the counterparty visible_report like the web case room',()=>{
 assert.ok(src.api.includes('chat_reported = web._consultation_has_report(session, case)'));
 assert.ok(src.api.includes('web.UserReport.reporter_user_id == other_id'));
 assert.ok(src.api.includes('web.UserReport.reported_user_id == user.id'));
 assert.ok(src.api.includes('"chat_reported": chat_reported,'));
 assert.ok(src.api.includes('"visible_report": None if visible_report is None else {'));
});

test('mobile push allowlist delivers the web program reminder copy',()=>{
 assert.ok(src.push.includes('("Dental AI", "Programınızdaki yaklaşan kayıt için hatırlatmanız var."),'));
});

test('expert performance-info text endpoint mirrors the expert-rules reading pattern',()=>{
 assert.ok(src.pro.includes("@router.get('/experts/performance-info')"));
 assert.ok(src.pro.includes("get_source(web.templates.env,'expert_performance_info.html')"));
 assert.ok(src.pro.includes("re.findall(r'<section class=\"expert-rule-card\">(.*?)</section>',source,re.S)"));
 // Native ExpertPerformanceInfo reads title/body/sections; content stays for older clients.
 assert.ok(src.pro.includes("'title':title_parser.text(),'body':plain.text(),'sections':sections,'content':plain.text()"));
});
