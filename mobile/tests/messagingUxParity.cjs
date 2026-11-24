// Messaging/UX parity contracts for the 2026-11-25 mobile UX round.
// Source-contract style: asserts the shipped client code keeps the
// WhatsApp-grade behaviors without spinning up a RN renderer.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");

const read = (p) => fs.readFileSync(require.resolve(p), "utf8");
const composer = read("../src/ChatAttachmentComposer.tsx");
const modernApi = read("../src/modernApi.ts");
const modernScreens = read("../src/ModernScreens.tsx");
const academic = read("../src/NativeAcademic.tsx");
const apiTs = read("../src/api.ts");
const profile = read("../src/NativePatientProfile.tsx");
const expert = modernScreens; // ExpertDirectory lives in ModernScreens.tsx
const foto = read("../src/NativeFotoFikir.tsx");
const mobileApiPy = read("../../app/mobile_api.py");

test("composer sends text and attachments as one message with a single send button", () => {
  // forwardRef handle the parent send button calls
  assert.match(composer, /React\.forwardRef<ChatComposerHandle,Props>/);
  assert.match(composer, /sendAll:\(text:string\)=>Promise<\{sentFiles:number;textConsumed:boolean\}>/);
  assert.match(composer, /queueCount:\(\)=>filesRef\.current\.length/);
  // caption rides on the FIRST attachment only
  assert.match(composer, /index===0\?caption:undefined/);
  // multi-file queue state, per-file removal, durable batch record
  assert.match(composer, /setFiles\(previous=>previous\.filter/);
  assert.match(composer, /version:2,scope:userId\+":"\+caseId/);
  // the separate "Eki gönder" button is gone
  assert.doesNotMatch(composer, /Eki gönder/);
});

test("upload API carries the optional caption within contract limits", () => {
  assert.match(modernApi, /clientMessageId\?:string,content\?:string/);
  assert.match(modernApi, /if\(caption\)body\.append\("content",caption\)/);
  assert.match(modernApi, /caption\.length>4000/);
  assert.match(modernApi, /message\.content\.length>4000/);
  assert.doesNotMatch(modernApi, /content\.length>180/);
});

test("conversation rows expose a three-dot menu wired to server actions", () => {
  assert.match(modernScreens, /accessibilityLabel="Görüşme işlemleri"/);
  assert.ok(modernScreens.includes('rowAction({action:"report",reason:rowReason'),"report uses the enum reason");
  assert.ok(modernScreens.includes('rowAction({action:rowMenu.blocked_by_me?"unblock":"block"})'),"block toggle follows the stored flag");
  assert.ok(modernScreens.includes('rowAction({action:"delete"})'),"remove-from-inbox is wired");
  // destructive actions require explicit confirmation
  assert.match(modernScreens, /Alert\.alert\("Sorun bildirilsin mi\?"/);
  assert.match(modernScreens, /Engellensin mi\?|Engel kaldırılsın mı\?/);
  assert.match(modernScreens, /Görüşme kaldırılsın mı\?/);
  // the inbox list carries the directional block flag
  assert.match(modernScreens, /rowMenu\.blocked_by_me/);
  assert.match(mobileApiPy, /"blocked_by_me":other_id in blocked_by_me_ids/);
});

test("chat screen routes one send button through queue-aware sendCurrent", () => {
  assert.match(modernScreens, /async function sendCurrent\(\)/);
  assert.match(modernScreens, /composerRef\.current\.queueCount\(\)>0/);
  assert.match(modernScreens, /!text\.trim\(\)&&queueCount===0/);
  // duplicated safety modal is retired; block/report live in the row and header menus
  assert.doesNotMatch(modernScreens, /Güvenlik ve Bloklama/);
  // legacy media bubbles render real captions, not filenames
  assert.match(modernScreens, /function mediaCaptionText\(item:ChatMessage\)/);
  assert.match(modernScreens, /MEDIA_FILE_RE\.test\(item\.content\.trim\(\)\)/);
});

test("academic pending-intent recovery sits next to the composer", () => {
  assert.match(academic, /label="Sonucu Kontrol Et"/);
  assert.match(academic, /label="Aynı İsteği Gönder"/);
  // send no longer silently no-ops on an unresolved load
  assert.match(academic, /Bağlantı tamamlanmadı\. "Durumu Yenile" ile tekrar deneyin\./);
  // index-not-ready explains the grey composer instead of staying silent
  assert.match(academic, /Ders notları hazır olduğunda gönderim açılacak/);
});

test("patient profile degrades web-created rows instead of failing the screen", () => {
  // tolerant getPatient: invalid FDI/revisions sanitized, not fatal
  assert.match(apiTs, /tooth_number:t\.tooth_number!=null&&validFdiTooth\(t\.tooth_number\)\?t\.tooth_number:null/);
  assert.match(apiTs, /edit_revision:typeof t\.edit_revision==="string"&&\/\^\[a-f0-9\]\{64\}\$\/\.test\(t\.edit_revision\)\?t\.edit_revision:""/);
  // corrupt local draft offers a clearing action instead of a permanent lock
  assert.match(profile, /clearBlockedTreatmentDraft/);
  assert.match(profile, /Bozuk tedavi taslağını temizle ve devam et/);
});

test("expert list keeps the card under the filters with distinct states", () => {
  assert.match(expert, /busy&&!data\?<View style=\{s\.center\}>/);
  assert.match(expert, /<FlatList style=\{\{flex:1\}\}/);
  assert.match(expert, /ListEmptyComponent=\{!error&&!busy\?/);
});

test("foto fikir speaks the backend contract", () => {
  // backend emits ASCII DIKKAT levels
  assert.match(foto, /DIKKAT:\{bg:"#FFF7ED"/);
  // reels shot plan is an object from the server, not a string
  assert.match(foto, /typeof row\.shot==="string"\?row\.shot:\[row\.shot\.plan/);
  // selecting an idea flows straight into slide preparation
  assert.match(foto, /async function makeSlides\(topicOverride\?:string\)/);
  assert.match(foto, /void makeSlides\(idea\.title\)/);
});
