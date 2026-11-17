const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{
 fileName:filename,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
}).outputText,filename);

const {applyNotificationReadAllSnapshot,parseNotificationTimestamp}=require('../src/notificationState.ts');

test('mark-all snapshot reads only notices created at or before the captured cutoff',()=>{
 const items=[
  {id:1,created_at:'2026-11-17T00:59:00.000Z',read_at:null},
  {id:2,created_at:'2026-11-17T01:00:01.000Z',read_at:null},
  {id:3,created_at:'2026-11-17T00:30:00.000Z',read_at:'2026-11-17T00:40:00.000Z'},
  {id:4,created_at:'invalid-date',read_at:null},
 ];
 const result=applyNotificationReadAllSnapshot(items,'2026-11-17T01:00:00.000Z');
 assert.equal(result[0].read_at,'2026-11-17T01:00:00.000Z');
 assert.equal(result[1].read_at,null);
 assert.equal(result[2].read_at,'2026-11-17T00:40:00.000Z');
 assert.equal(result[3].read_at,null);
});

test('naive backend datetimes are interpreted as UTC rather than device-local time',()=>{
 assert.equal(parseNotificationTimestamp('2026-11-17T04:30:00'),Date.parse('2026-11-17T04:30:00.000Z'));
 assert.equal(parseNotificationTimestamp('2026-11-17T04:30:00+03:00'),Date.parse('2026-11-17T01:30:00.000Z'));
});

test('mark-all snapshot rejects an invalid cutoff instead of reading everything',()=>{
 assert.throws(()=>applyNotificationReadAllSnapshot([{created_at:'2026-11-17T00:00:00Z'}],'not-a-date'),/zaman sınırı/);
});

test('native notification center exposes explicit mark-all and reconciles remote read events',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/ModernScreens.tsx'),'utf8');
 assert.ok(source.includes('markAllNotificationsRead(token,seenBefore)'));
 assert.ok(source.includes('"NOTIFICATIONS_READ"'));
 assert.ok(source.includes('Tümünü okundu işaretle'));
 assert.ok(source.includes('applyNotificationReadAllSnapshot'));
 assert.ok(source.includes('unread:result.unread_count'));
});

test('home unread badge refreshes when returning from notification center',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../App.tsx'),'utf8');
 const start=source.indexOf('function Home('),end=source.indexOf('\nfunction ',start+10);
 const home=source.slice(start,end);
 assert.ok(home.includes('useIsFocused()'));
 assert.ok(home.includes('if(focused)loadUnread()'));
});

test('native onboarding does not request OS permission before push token registration exists',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../App.tsx'),'utf8');
 const start=source.indexOf('function NotificationPermissionIntro('),end=source.indexOf('function AppContent()',start);
 const intro=source.slice(start,end);
 assert.ok(!intro.includes('PermissionsAndroid.request'));
 assert.ok(!source.includes('PermissionsAndroid'));
 assert.ok(intro.includes('Expo push token kaydı'));
 assert.ok(intro.includes('henüz bağlanmadı'));
});

test('mobile API validates and calls the cutoff read-all endpoint',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/modernApi.ts'),'utf8');
 assert.ok(source.includes('"/notifications/read-all"'));
 assert.ok(source.includes('seen_before:new Date(timestamp).toISOString()'));
});
