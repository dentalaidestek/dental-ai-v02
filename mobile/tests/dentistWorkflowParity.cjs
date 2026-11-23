'use strict';
// Contract tests for the dentist-workflow UX fixes: voice-exam safety context,
// analysis notes preview, AI preview in the history modal, debounced AI-tab
// patient search, tooth quadrant rows, home recent analyses + upcoming events,
// copy-modal conflict precheck, reminder won't-fire warning, conflict advisory
// rows, push unregister on session expiry, follow-up bridge, phone query
// normalization and dead-end notification targets. The "voice exam quick
// action" audit item is covered by a guard test instead (skipped on re-read).
const test=require('node:test');
const assert=require('node:assert');
const fs=require('fs');
const path=require('path');
const ts=require('typescript');
const src=f=>fs.readFileSync(path.join(__dirname,'..','src',f),'utf8');
const app=()=>fs.readFileSync(path.join(__dirname,'..','App.tsx'),'utf8');

require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);

const {patientProfileQuickActions}=require('../src/patientProfilePresentation.ts');
const {reminderFiresInPast,programConflictRows,programFollowUpDate}=require('../src/programModel.ts');
const {dashboardUpcomingRows}=require('../src/dashboardPresentation.ts');
const {normalizePatientDirectorySearch}=require('../src/patientDirectoryPresentation.ts');
const {resolveNativeNotificationTarget:resolveTarget}=require('../src/notificationTarget.ts');

test('voice exam shows a read-only safety summary fetched silently once per patient',()=>{
	const v=src('VoiceExamEntry.tsx');
	// One silent fetch when the exam stage opens; failure renders nothing.
	assert.match(v,/if\(stage!=="exam"||!selected\)return;const patientId=selected\.id,requestScope=scope\.current,scopeKey=requestScope\+":"+patientId;if\(safetyLoaded\.current===scopeKey\)return;/);
	assert.match(v,/getVoiceHistory\(token,patientId\)\.then\(result=>\{if\(active&&requestScope===scope\.current\)\{safetyLoaded\.current=scopeKey;setSafetyFields\(result\.fields\)\}\}\)\.catch\(\(\)=>\{\}\)/);
	assert.match(v,/setSafetyFields\(result\.fields\)/);
	assert.doesNotMatch(v,/setSafetyError/);
	// Collapsed-by-default read-only rozet under the header.
	assert.match(v,/safetyOpen,setSafetyOpen\]=useState\(false\)/);
	assert.match(v,/Hasta güvenlik özeti \(salt okunur\)/);
	assert.match(v,/\["allergies","Alerji"\],\["medications","İlaç"\],\["medical_history","Sağlık"\]/);
	assert.match(v,/safetySummary\.join\(" \/ "\)/);
	assert.match(v,/safetyOpen\?undefined:2/);
	// Display-only: the rozet must not merge into fields; the manual confirmation gate stays.
	assert.match(v,/if\(!historyConfirmed\)\{setHistoryError\("Önceki bilgileri hastayla doğruladığınızı işaretleyin\."\);return;\}/);
	assert.match(v,/Bu özet yalnızca görüntülenir\. Alanların muayeneye aktarılması için aşağıdaki "hastayla doğruladım" onayı gerekir\./);
	// Age and chief complaint next to the patient name.
	assert.match(v,/selected\.age!==null&&selected\.age!==undefined\?" · "\+selected\.age\+" yaş":""/);
	assert.match(v,/selected\?\.chief_complaint\?\.trim\(\)\?" · "\+selected\.chief_complaint\.trim\(\):""/);
});

test('voice exam entry stays on the dedicated home route; profile quick actions unchanged',()=>{
	// Audit fix "one-tap voice exam from patient profile" was skipped on re-read:
	// the committed contract (patientProfileUI.cjs) requires the patient detail
	// screen to NOT duplicate the voice-exam entry point.
	const keys=patientProfileQuickActions().map(item=>item.key);
	assert.deepEqual(keys,['chart','analysis','appointment','treatment']);
	const profile=src('NativePatientProfile.tsx');
	assert.doesNotMatch(profile,/voice:actions\.voice/);
	assert.doesNotMatch(profile,/Sesli Muayene/);
	const a=app();
	assert.match(a,/VisualFeature title="Sesli Muayene"/);
	assert.match(a,/Stack\.Screen name="VoiceExam"/);
	assert.match(a,/initialPatientId=\{route\.params\?\.patientId\}/);
});

test('history rows preview clinical notes with a two-line fallback label',()=>{
	const h=src('NativePatientHistory.tsx');
	assert.match(h,/<Text numberOfLines=\{2\} style=\{\{color:'#53657B',fontSize:13,marginTop:3\}\}>\{item\.clinical_notes\?\.trim\(\)\|\|'Görüntü analizi'\}<\/Text>/);
});

test('history detail modal previews the AI clinical result and fails silently',()=>{
	const h=src('NativePatientHistory.tsx');
	assert.match(h,/import \{getClinical,ClinicalWorkspace\} from '\.\/clinicalApi';/);
	assert.match(h,/void getClinical\(token,id\)\.then\(result=>\{if\(active\.current===owner&&detailRequest\.current===seq&&result\.analysis_id===id\)setClinical\(result\)\}\)\.catch\(\(\)=>\{\}\)/);
	assert.match(h,/AI ön değerlendirme/);
	assert.match(h,/most_likely/);
	assert.match(h,/\.slice\(0,3\)/);
	// Reset on open, close and scope change.
	assert.match(h,/setClinical\(null\);/);
});

test('AI tab patient search is debounced at 300ms and the manual button is gone',()=>{
	const d=src('NativeDentalAI.tsx');
	assert.match(d,/useEffect\(\(\)=>\{const timer=setTimeout\(\(\)=>setPatientQuery\(patientSearch\.trim\(\)\),300\);return\(\)=>clearTimeout\(timer\)\},\[patientSearch\]\)/);
	assert.doesNotMatch(d,/>Hasta ara<\/Text>/);
	assert.match(d,/onSubmitEditing=\{\(\)=>setPatientQuery\(patientSearch\.trim\(\)\)\}/);
});

test('tooth selection grids render four quadrant rows with right/left labels',()=>{
	for(const file of ['NativeClinicalReview.tsx','NativeVisionViewer.tsx']){
		const s=src(file);
		assert.match(s,/Sağ üst/);
		assert.match(s,/Sol üst/);
		assert.match(s,/Sol alt/);
		assert.match(s,/Sağ alt/);
	}
	// ADULT order 11-18 / 21-28 / 31-38 / 41-48.
	assert.match(src('NativeVisionViewer.tsx'),/\["Sağ üst",\["11","12","13","14","15","16","17","18"\]\],\["Sol üst",\["21","22","23","24","25","26","27","28"\]\],\["Sol alt",\["31","32","33","34","35","36","37","38"\]\],\["Sağ alt",\["41","42","43","44","45","46","47","48"\]\]/);
	const clinical=src('NativeClinicalReview.tsx');
	assert.match(clinical,/teeth=\(primary\?\[5,6,7,8\]:\[1,2,3,4\]\)\.map\(q=>\(\{label:QUADRANT_LABELS\[q\]/);
	// Selection behavior unchanged.
	assert.match(clinical,/old\.includes\(t\)\?old\.filter\(x=>x!==t\):old\.length<32\?\[\.\.\.old,t\]:old/);
	assert.match(src('NativeVisionViewer.tsx'),/old\.includes\(tooth\)\?old\.filter\(x=>x!==tooth\):old\.length<32\?\[\.\.\.old,tooth\]:old/);
});

test('home Son Analizler reads the real analysis history first page',()=>{
	const a=app();
	assert.match(a,/getAnalysisHistory,AnalysisHistory as AnalysisHistoryItem\}from"\.\/src\/modernApi"/);
	assert.match(a,/const page=await getAnalysisHistory\(token\);setRecentAnalyses\(page\.items\.slice\(0,3\)\)/);
	assert.match(a,/\(recentAnalyses\.length\?recentAnalyses:\(d\?\.recent_analyses\|\|\[\]\)\.slice\(0,3\)\)\.map\(item=>/);
	// Voice flag and TR labels still flow through the same row renderer.
	assert.match(a,/patientAnalysisHistoryStatus\(\{status:item\.status,is_voice_review:\(item as any\)\.is_voice_review\}\)/);
	assert.match(a,/nav\.navigate\("AnalysisResult",\{id:item\.id\}\)/);
});

test('home renders upcoming events as compact rows without duplicating the program card',()=>{
	const a=app();
	assert.match(a,/const upcomingRows=dashboardUpcomingRows\(d\?\.upcoming_events,shownProgramEvent\);/);
	assert.match(a,/\{row\.day\} · \{row\.time\} · \{row\.title\}/);
	assert.match(a,/upcomingRows\.map\(row=>/);
	// Dedupe: snapshot event uses its wall time, raw card event uses start_at.
	assert.match(a,/hasProgramSnapshot\n  \?\(d\?\.dashboard_event\?\{title:d\.dashboard_event\.title,start_time:d\.dashboard_event\.start_time\}:null\)/);
	const rows=dashboardUpcomingRows(
		[{title:'Diş kontrolü',start_at:'2026-11-24T09:30:00'},{title:'Diş kontrolü',start_at:'2026-11-24T09:30:00'},{title:'Dolgu',start_at:'2026-11-25T14:05:00'},{title:'Kontrol',start_at:'2026-11-26T10:00:00'},{title:'Sıra dışı',start_at:'not-a-date'}],
		{title:'Diş kontrolü',start_time:'09:30'},
	);
	assert.deepEqual(rows,[
		{key:'Dolgu|2026-11-25T14:05:00',day:'25.11',time:'14:05',title:'Dolgu'},
		{key:'Kontrol|2026-11-26T10:00:00',day:'26.11',time:'10:00',title:'Kontrol'},
	]);
	assert.deepEqual(dashboardUpcomingRows([{title:'Tek kayıt',start_at:'2026-11-24T08:00:00'}],null),[
		{key:'Tek kayıt|2026-11-24T08:00:00',day:'24.11',time:'08:00',title:'Tek kayıt'},
	]);
	assert.deepEqual(dashboardUpcomingRows(undefined,null),[]);
});

test('copy modal prechecks conflicts per target day and warns before confirming',()=>{
	const p=src('NativeProgram.tsx');
	assert.match(p,/checkProgramConflicts,verifyProgramAction\} from '\.\/programApi'/);
	assert.match(p,/function copyDraftFor\(item:ProgramOccurrence,day:string\):ProgramDraft\{/);
	assert.match(p,/await checkProgramConflicts\(token,copyDraftFor\(source,day\)\);total\+=result\.total\|\|0\}catch\{total=0;break\}/);
	// Advisory total is rendered in the modal before the second (confirm) press.
	assert.match(p,/Hedef günlerde \{copyConflictTotal\} kayıt çakışıyor\. Kayıt yine de eklenebilir; onaylamak için tekrar dokunun\./);
	assert.match(p,/if\(copyConflictTotal!==null\)\{void act\(copy,'copy',copyDays\);return\}/);
	// Zero conflicts or a failed check keep the current single-press behavior.
	assert.match(p,/if\(total<=0\)\{void act\(source,'copy',days\);return\}/);
});

test('editor warns when the chosen reminder can no longer fire',()=>{
	const e=src('NativeProgramEditor.tsx');
	assert.match(e,/reminderFiresInPast\(draft\.start_at,draft\.reminder_minutes\)/);
	assert.match(e,/Bu kayıt için hatırlatma oluşmaz; 'Saatinde' seçin\./);
	const morning=new Date(2030,0,7,9,0);
	assert.equal(reminderFiresInPast('2030-01-07T10:00','30',new Date(2030,0,7,9,45)),true,'start 10:00 minus 30min (09:30) already past at 09:45');
	assert.equal(reminderFiresInPast('2030-01-07T10:00','30',morning),false);
	assert.equal(reminderFiresInPast('2030-01-07T10:00','NONE',morning),false);
	assert.equal(reminderFiresInPast('2030-01-07T10:00','1440',new Date(2030,0,7,9,0)),true,'1 day before 10:00 is 2030-01-06 10:00');
	assert.equal(reminderFiresInPast('2030-01-07T10:00','0',new Date(2030,0,7,9,0)),false);
	assert.equal(reminderFiresInPast('not-a-time','30',morning),false);
});

test('conflict advisory dialog lists the intersecting page rows',()=>{
	const e=src('NativeProgramEditor.tsx');
	assert.match(e,/const conflictRows=programConflictRows\(payload,page\.items\);/);
	assert.match(e,/conflictRows\.length\?'\\n'\+conflictRows\.join\('\\n'\):''/);
	const items=[
		{title:'Diş kontrolü',start_local:'2030-01-07T10:00',end_local:'2030-01-07T10:30',patient_name:'Ada Kaya'},
		{title:'Dolgu',start_local:'2030-01-07T11:00',end_local:'2030-01-07T11:30',patient_name:'Ipek Cetin'},
		{title:'Klinik',start_local:'2030-01-07T12:00',end_local:'2030-01-07T13:00',patient_name:null},
		{title:'Uzak',start_local:'2030-01-07T18:00',end_local:'2030-01-07T19:00',patient_name:null},
	];
	const rows=programConflictRows({start_at:'2030-01-07T10:15',end_at:'2030-01-07T12:30'},items);
	assert.deepEqual(rows,['10:00 · Diş kontrolü (Ada Kaya)','11:00 · Dolgu (Ipek Cetin)','12:00 · Klinik']);
	// Maximum three rows and no patient parenthesis when the name is absent.
	assert.equal(rows.length<=3,true);
	const noEnd=programConflictRows({start_at:'2030-01-07T10:00',end_at:''},items);
	assert.deepEqual(noEnd,['10:00 · Diş kontrolü (Ada Kaya)']);
});

test('session expiry unregisters push fire-and-forget before clearing the session',()=>{
	const a=app();
	assert.match(a,/const stop=subscribeSessionExpiry\(token,\(\)=>\{void unregisterNativePushForLogout\(token,userId\)\.catch\(\(\)=>\{\}\);pendingNativeNotificationRoute=null;/);
	assert.match(a,/\[session\?\.token,session\?\.user\.id\]/);
});

test('completing a patient event offers a +7 days control appointment in the editor',()=>{
	const p=src('NativeProgram.tsx');
	assert.match(p,/Kontrol randevusu ekle/);
	assert.match(p,/setEditor\(\{initialPatientId:patientId,initialDate:programFollowUpDate\(item\.start_local\.slice\(0,10\),7\)\}\)/);
	assert.match(p,/initialPatientId=\{editor\.initialPatientId\}/);
	assert.equal(programFollowUpDate('2026-02-25',7),'2026-03-04','+7 days crosses the month end');
	assert.equal(programFollowUpDate('2030-01-07',7),'2030-01-14');
});

test('directory search strips separators from phone-like queries only',()=>{
	assert.equal(normalizePatientDirectorySearch('0532 123 45 67'),'05321234567');
	assert.equal(normalizePatientDirectorySearch('0532-123-45-67'),'05321234567');
	assert.equal(normalizePatientDirectorySearch('05551112222'),'05551112222');
	assert.equal(normalizePatientDirectorySearch('  İpek   Çetin   0555  '),'İpek Çetin 0555');
	assert.equal(normalizePatientDirectorySearch('   '),'');
	const source=src('patientDirectoryPresentation.ts');
	assert.ok(source.includes('/^\\d[\\d\\s().-]{6,}$/'),'phone-like query regex must be present');
});

test('verification and social-admin notification paths navigate instead of dead-ending',()=>{
	assert.deepEqual(resolveTarget('/account/verification'),{kind:'navigate',route:{screen:'ExpertManagement'}});
	assert.deepEqual(resolveTarget('/account/verification?from=email'),{kind:'navigate',route:{screen:'ExpertManagement'}});
	assert.deepEqual(resolveTarget('/admin/social'),{kind:'navigate',route:{screen:'SocialAdmin'}});
	assert.deepEqual(resolveTarget('/admin-center/social/reports'),{kind:'navigate',route:{screen:'SocialAdmin'}});
	assert.deepEqual(resolveTarget('/social'),{kind:'navigate',route:{screen:'SocialAdmin'}});
	// Unsupported fallback is preserved for everything else.
	assert.deepEqual(resolveTarget('/admin'),{kind:'unsupported',path:'/admin'});
	assert.deepEqual(resolveTarget('/admin/users'),{kind:'unsupported',path:'/admin/users'});
	assert.deepEqual(resolveTarget('/program'),{kind:'navigate',route:{screen:'Program'}});
});
