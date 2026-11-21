'use strict';
// Contract tests for the audit fixes (badge gating, inbox propagation,
// CASE_MESSAGES_DELETED, replay guard, read retry, report length, TR labels,
// parseRecoveryLink, setWall guard, pendingNotice, performance-info, deadlines).
const test=require('node:test');
const assert=require('node:assert');
const fs=require('fs');
const path=require('path');
const src=f=>fs.readFileSync(path.join(__dirname,'..','src',f),'utf8');
const app=()=>fs.readFileSync(path.join(__dirname,'..','App.tsx'),'utf8');

test('badge bump is gated on incoming non-replay MESSAGE_CREATED and CASE_READ reseeds',()=>{
	const a=app();
	assert.match(a,/type==="MESSAGE_CREATED"&&Number\(lastEvent\.payload\?\.case_id\|\|0\)>0&&lastEvent\.payload\?\.is_outgoing===false&&!lastEvent\.replay&&!messagesFocused\.current/);
	assert.match(a,/"CASE_READ"/);
	assert.match(a,/getMessagesUnreadCount\(token\)\.then\(r=>\{if\(live\)setMsgUnread\(Math\.min\(99,Number\(r\.count\)\|\|0\)\)\}/);
	assert.match(a,/Math\.min\(99,value\+1\)/);
});

test('realtime exposes replay flag and derives ws url from API_BASE',()=>{
	const r=src('realtime.ts');
	assert.match(r,/replay:evt\.replay===true\|\|evt\.payload\?\.replay===true/);
	assert.doesNotMatch(r,/wss:\/\/dentalai\.tr\/ws\/sync/);
	assert.match(r,/API_BASE\.replace\(\/\^https:\//);
});

test('consultationRealtime propagates status_key/status_label in both branches',()=>{
	const c=src('consultationRealtime.ts');
	const keyParts=c.split('status_key:typeof payload.status_key==="string"?payload.status_key').length-1;
	const labelParts=c.split('status_label:typeof payload.status_label==="string"?payload.status_label').length-1;
	assert.strictEqual(keyParts,2);
	assert.strictEqual(labelParts,2);
});

test('ModernScreens handles CASE_MESSAGES_DELETED and replay guard',()=>{
	const m=src('ModernScreens.tsx');
	assert.match(m,/eventType==="CASE_MESSAGES_DELETED"/);
	assert.match(m,/messages_deleted_at:typeof payload\.deleted_at==="string"\?payload\.deleted_at/);
	assert.match(m,/messages:\[\],next_before:null\}\);/);
	assert.match(m,/if\(lastEvent\.replay===true\)\{if\(gap\)void catchUpMessages\(\);return;\}/);
});

test('read-receipt retry and foreground re-arm',()=>{
	const m=src('ModernScreens.tsx');
	assert.match(m,/if\(n<2\)setTimeout\(\(\)=>attempt\(n\+1\),n===0\?1500:3000\)/);
	assert.match(m,/AppState\.addEventListener\('change',state=>\{/);
});

test('report detail slice is 1000 and inbox pill falls back to consultationStatusLabel',()=>{
	const m=src('ModernScreens.tsx');
	assert.match(m,/detail:reportDetail\.trim\(\)\.slice\(0,1000\)/);
	assert.match(m,/maxLength=\{1000\}/);
	assert.match(m,/consultationStatusLabel\(item\.status_key\|\|item\.status\)/);
});

test('catch-up runs regardless of socket health',()=>{
	const m=src('ModernScreens.tsx');
	assert.match(m,/if\(!isFocused\|\|\(!hasVisibleCase&&!ready\)\)return;/);
	assert.match(m,/if\(isFocused&&hasVisibleCase\)void catchUpMessages\(\)/);
});

test('chat context card and report banner',()=>{
	const m=src('ModernScreens.tsx');
	assert.match(m,/Vaka bilgisi/);
	assert.match(m,/Bu görüşmeyle ilgili bir sorun bildirildi; süreç yönetimde\./);
	assert.match(m,/requester_opinion/);
});

test('notifications auto markAllRead on mount with unread>0',()=>{
	const m=src('ModernScreens.tsx');
	assert.match(m,/autoMarkSeen\.current=true;void markAllRead\(\)/);
});

test('TR status labels wired at the listed call sites',()=>{
	assert.match(app(),/patientAnalysisHistoryStatus\(\{status:item\.status,is_voice_review:\(item as any\)\.is_voice_review\}\)/);
	const m=src('ModernScreens.tsx');
	assert.match(m,/import \{patientAnalysisHistoryStatus\} from "\.\/patientHistoryPresentation";/);
	assert.match(m,/patientAnalysisHistoryStatus\(\{status:item\.status,is_voice_review:item\.is_voice_review\}\)/);
	const d=src('NativeDentalAI.tsx');
	assert.doesNotMatch(d,/,"ANALYSIS_COMPLETED","VISION_READY"/);
	assert.match(d,/shouldRefreshOnAppResume\(previousState,nextState,focused\)/);
	const cr=src('NativeClinicalReview.tsx');
	assert.match(cr,/trClinicalStatus\(data\.status\)/);
	assert.match(cr,/trClinicalStatus\(data\.job\.status\)/);
	const ac=src('NativeAcademic.tsx');
	assert.match(ac,/RUN_STATUS_TR\[run\.status\]\|\|run\.status/);
	assert.match(ac,/RUN_STAGE_TR\[run\.stage\]\|\|run\.stage/);
	assert.match(ac,/INDEX_STATE_TR\[index\.state\]\|\|index\.state/);
	assert.match(ac,/INDEX_STATE_TR\[f\.state\]\|\|f\.state/);
	assert.match(src('NativeConsultationRequest.tsx'),/"Radyograf"/);
	assert.match(src('SocialScreens.tsx'),/Otomatik kontrol yeniden denenecek/);
});

test('parseRecoveryLink accepts any https origin with the reset path',()=>{
	const a=src('authApi.ts');
	assert.doesNotMatch(a,/url\.origin==='https:\/\/dentalai\.tr'/);
	assert.match(a,/url\.protocol==='https:'&&url\.pathname==='\/reset-password'/);
		assert.ok(a.includes("pathname==='/reset-password'"),'reset path enforced');
	assert.ok(a.includes('dentalai:'),'deep-link scheme kept');
	assert.ok(/protocol==='dentalai:'|protocol==="dentalai:"/.test(a),'scheme accepted');
});

test('setWall ignores empty date value',()=>{
	assert.match(src('NativeProgramEditor.tsx'),/if\(part==='date'&&!value\)return;/);
});

test('pendingNotice persisted before signout and read on Login mount',()=>{
	const acc=src('NativeAccount.tsx');
	assert.match(acc,/dai\.pendingNotice/);
	assert.match(acc,/Şifreniz başarıyla değiştirildi\./);
	assert.match(acc,/E-posta adresiniz güncellendi; doğrulama bağlantısını kontrol edin\./);
	assert.match(acc,/Hesabınız kalıcı olarak silindi\./);
	assert.match(src('NativeAuth.tsx'),/dai\.pendingNotice/);
	assert.match(src('NativeAccount.tsx'),/Yönetici hesapları uygulamadan yönetilmez; web panelindeki iki adımlı doğrulamayı kullanın\./);
	assert.match(src('NativeAccount.tsx'),/maxLength=\{80\}/);
});

test('performance-info fetched via api client with hardcoded fallback',()=>{
	const p=src('professionalApi.ts');
	assert.match(p,/\/experts\/performance-info/);
	assert.match(p,/export async function getExpertPerformanceInfo/);
	const n=src('NativeExpertPerformance.tsx');
	assert.match(n,/getExpertPerformanceInfo\(token\)/);
	assert.match(n,/Kullanıcıların gördüğü bilgiler/);
});

test('voice-exam apply deadline is 180000',()=>{
	assert.match(src('api.ts'),/voice-exam\\\/apply/);
	assert.match(src('api.ts'),/\?180000:30000/);
});

test('small UX fixes present',()=>{
	assert.match(src('NativePushSettings.tsx'),/Tekrar dene/);
	assert.match(src('NativeAcademicFile.tsx'),/\(size\|\|0\)>50\*1024\*1024\?600000:180000/);
	const p=src('NativeProgram.tsx');
	assert.doesNotMatch(p,/\{view==='week'&&<Text style=\{\{textAlign:'center',fontSize:12\}\}>\{date\.date\.slice\(8\)\}<\/Text>\}/);
});
