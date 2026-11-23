// Sohbet güvenlik aksiyonları: bloklama/blok kaldırma ve raporlama yüzeyi.
// Web vaka sayfasındaki /block,/unblock,/report form akışının birebir mobil karşılığı;
// backend dispatch (mobile_api actions map) zaten web fonksiyonlarına delege eder.
const fs=require('node:fs'),assert=require('node:assert/strict'),{test}=require('node:test');
const src={
 screens:fs.readFileSync(__dirname+'/../src/ModernScreens.tsx','utf8'),
 modern:fs.readFileSync(__dirname+'/../src/modernApi.ts','utf8'),
 backend:fs.readFileSync(__dirname+'/../../app/mobile_api.py','utf8'),
 webRoom:fs.readFileSync(__dirname+'/../../app/templates/expert_case_room.html','utf8'),
};

test('chat exposes the five report reasons web sends',()=>{
 assert.ok(src.screens.includes('["HARASSMENT","Taciz"]'));
 assert.ok(src.screens.includes('["PROFANITY","Hakaret veya küfür"]'));
 assert.ok(src.screens.includes('["SPAM","İstenmeyen içerik"]'));
 assert.ok(src.screens.includes('["INAPPROPRIATE","Uygunsuz davranış"]'));
 assert.ok(src.screens.includes('["OTHER","Diğer"]'));
 assert.ok(src.modern.includes('reason?:"HARASSMENT"|"PROFANITY"|"SPAM"|"INAPPROPRIATE"|"OTHER"'));
});

test('report payload matches the web form fields exactly',()=>{
 assert.ok(src.screens.includes('{action:"report",reason:reportReason,detail:reportDetail.trim().slice(0,1000)}'));
 // Blok/kaldır ve backend delegasyonu değişmeden korunuyor.
 assert.ok(src.screens.includes('void submitSafety("unblock")'));
 assert.ok(src.screens.includes('confirmBlock()'));
 assert.ok(src.backend.includes('"block": (web.consultation_block_user, ())'));
 assert.ok(src.backend.includes('"unblock": (web.consultation_unblock_user, ())'));
 assert.ok(src.backend.includes('"report": (web.consultation_report_user, (payload.reason, payload.detail))'));
});

test('safety surface is reachable from the chat and shows the blocked state',()=>{
 assert.ok(src.screens.includes('🛡 Güvenlik ve Bloklama'));
 assert.ok(src.screens.includes('Karşılıklı mesajlaşma kapalı'));
 assert.ok(src.screens.includes('Raporu Gönder'));
 assert.ok(src.screens.includes('Karşılıklı Mesajlaşmayı Kapat'));
 assert.ok(src.screens.includes('Bloklamayı Kaldır'));
 assert.ok(src.screens.includes('Bloklama rapor yerine geçmez'));
 // Bloklu görüşmede kompozisyon zaten kapalı; yüzey her durumda erişilebilir.
 assert.ok(src.screens.includes('!visibleData.case?.blocked_either&&!waitingStart'));
});

test('block and report forms exist on the web case room for parity',()=>{
 assert.ok(src.webRoom.includes('/block')||src.webRoom.includes('"/block'));
 assert.ok(src.webRoom.includes('/report'));
});
