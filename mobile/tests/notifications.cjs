const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{
 fileName:filename,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
}).outputText,filename);

const {applyNotificationReadAllSnapshot,parseNotificationTimestamp}=require('../src/notificationState.ts');
const {normalizeNotificationReadAt}=require('../src/notificationState.ts');
const {shouldRefreshHomeUnread}=require('../src/notificationRefresh.ts');
const {isValidExpoPushToken}=require('../src/pushToken.ts');

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
 assert.ok(intro.includes('Profil > Cihaz Bildirimleri'));
 assert.ok(intro.includes('İşletim sistemi izni yalnızca'));
});

test('mobile API validates and calls the cutoff read-all endpoint',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/modernApi.ts'),'utf8');
 assert.ok(source.includes('"/notifications/read-all"'));
 assert.ok(source.includes('seen_before:new Date(timestamp).toISOString()'));
});

test('Expo SDK 54 push registration is explicit, account-scoped and token-safe',()=>{
 const app=fs.readFileSync(path.join(__dirname,'../App.tsx'),'utf8');
 const account=fs.readFileSync(path.join(__dirname,'../src/NativeAccount.tsx'),'utf8');
 const settings=fs.readFileSync(path.join(__dirname,'../src/NativePushSettings.tsx'),'utf8');
 const push=fs.readFileSync(path.join(__dirname,'../src/nativePush.ts'),'utf8');
 const config=fs.readFileSync(path.join(__dirname,'../app.config.js'),'utf8');
 const appJson=JSON.parse(fs.readFileSync(path.join(__dirname,'../app.json'),'utf8'));
 const pkg=JSON.parse(fs.readFileSync(path.join(__dirname,'../package.json'),'utf8'));
 const lock=JSON.parse(fs.readFileSync(path.join(__dirname,'../package-lock.json'),'utf8'));
 assert.equal(pkg.dependencies['expo-notifications'],'~0.32.17');
 assert.equal(pkg.dependencies['expo-constants'],'~18.0.14');
 assert.equal(lock.packages['node_modules/expo-notifications'].version,'0.32.17');
 assert.ok(appJson.expo.plugins.includes('expo-notifications'));
 assert.ok(config.includes('EXPO_PUBLIC_EAS_PROJECT_ID'));
 assert.ok(account.includes('NativePushSettings token={token} userId={user.id}'));
 assert.ok(settings.includes('enableNativePush(token, userId)'));
 assert.ok(settings.includes('disableNativePush(token, userId)'));
 assert.ok(push.includes('Notifications.requestPermissionsAsync()'));
 assert.ok(push.includes('Notifications.getExpoPushTokenAsync({ projectId })'));
 const projectPreflight=push.indexOf('if (!projectId)');
 const permissionRequest=push.indexOf('Notifications.requestPermissionsAsync()');
 assert.ok(projectPreflight>=0&&permissionRequest>projectPreflight);
 assert.ok(push.includes('refreshNativePushRegistration'));
 assert.ok(push.includes('SecureStore.setItemAsync(enabledKey(userId), "1")'));
 assert.ok(push.includes('registerPushDevice(token, registration.deviceId, registration.token, registration.platform, registration.installationProof)'));
 assert.ok(push.includes('registered.delivery_enabled ? "1" : "0"'));
 assert.ok(settings.includes('state.deliveryEnabled'));
 assert.ok(settings.includes('sunucu push dağıtımı henüz etkinleştirilmemiş'));
 assert.ok(!push.includes('console.log'));
 assert.ok(app.includes('subscribeToNativePushResponses'));
 assert.ok(app.includes('refreshNativePushRegistration(token,userId)'));
 assert.ok(app.includes('unregisterNativePushForLogout(session.token,session.user.id)'));
 assert.ok(app.includes('pendingNativeNotificationRoute=null'));
});

test('native push asks permission only after an explicit account action and refreshes on foreground',()=>{
 const push=fs.readFileSync(path.join(__dirname,'../src/nativePush.ts'),'utf8');
 const app=fs.readFileSync(path.join(__dirname,'../App.tsx'),'utf8');
 const intro=app.slice(app.indexOf('function NotificationPermissionIntro('),app.indexOf('function AppContent()',app.indexOf('function NotificationPermissionIntro(')));
 assert.ok(push.includes('export async function enableNativePush'));
 assert.ok(push.includes('export async function refreshNativePushRegistration'));
 assert.ok(push.includes('if ((await SecureStore.getItemAsync(enabledKey(userId))) !== "1") return false'));
 assert.ok(app.includes('state==="active"'));
 assert.ok(!intro.includes('requestPermissionsAsync'));
});


test('Expo push token validation accepts canonical tokens and rejects escaped or malformed values',()=>{
 assert.equal(isValidExpoPushToken('ExpoPushToken[abcdefgh]'),true);
 assert.equal(isValidExpoPushToken('ExponentPushToken[abcdefgh12345678]'),true);
 assert.equal(isValidExpoPushToken('ExpoPushToken['+'a'.repeat(128)+']'),true);
 assert.equal(isValidExpoPushToken('ExpoPushToken['+'a'.repeat(129)+']'),false);
 assert.equal(isValidExpoPushToken('ExpoPushToken[short]'),false);
 assert.equal(isValidExpoPushToken('ExpoPushToken[bad token]'),false);
 assert.equal(isValidExpoPushToken('ExpoPushToken\\[abcdefgh12345678\\]'),false);
 assert.equal(isValidExpoPushToken('OtherPushToken[abcdefgh12345678]'),false);
 assert.equal(isValidExpoPushToken(null),false);
});


test('account login claims the same installation before optional push refresh',()=>{
 const app=fs.readFileSync(path.join(__dirname,'../App.tsx'),'utf8');
 const push=fs.readFileSync(path.join(__dirname,'../src/nativePush.ts'),'utf8');
 const api=fs.readFileSync(path.join(__dirname,'../src/modernApi.ts'),'utf8');
 assert.ok(push.includes('INSTALLATION_PROOF_KEY'));
 assert.ok(push.includes('Crypto.getRandomBytesAsync(32)'));
 assert.ok(push.includes('installationClaimQueue.then(claim, claim)'));
 assert.ok(push.includes('claimPushDevice(token, identity.deviceId, identity.installationProof)'));
 assert.ok(api.includes('"/push/devices/claim"'));
 assert.ok(api.includes('installation_proof:installationProof'));
 const claimIndex=app.indexOf('await claimNativePushDeviceForSession(token,userId)');
 const refreshIndex=app.indexOf('if(active)refresh()',claimIndex);
 assert.ok(claimIndex>=0&&refreshIndex>claimIndex);
 assert.ok(app.includes('claimNativePushDeviceForSession,refreshNativePushRegistration'));
});

test('installation claim does not request notification permission or enable a new account',()=>{
 const push=fs.readFileSync(path.join(__dirname,'../src/nativePush.ts'),'utf8');
 const start=push.indexOf('export function claimNativePushDeviceForSession');
 const end=push.indexOf('/** Refreshes an opted-in token',start);
 const claim=push.slice(start,end);
 assert.ok(claim.includes('claimPushDevice'));
 assert.ok(!claim.includes('requestPermissionsAsync'));
 assert.ok(!claim.includes('registerPushDevice'));
 assert.ok(!claim.includes('setItemAsync(enabledKey(userId), "1")'));
});

test('canonical is_read wins over stale or missing read_at while old responses remain compatible',()=>{
 const created='2026-11-18T10:00:00.000Z';
 assert.equal(normalizeNotificationReadAt({created_at:created,is_read:true,read_at:null}),created);
 assert.equal(normalizeNotificationReadAt({created_at:created,is_read:false,read_at:'2026-11-18T10:01:00.000Z'}),null);
 assert.equal(normalizeNotificationReadAt({created_at:created,read_at:'2026-11-18T10:01:00.000Z'}),'2026-11-18T10:01:00.000Z');
 assert.equal(normalizeNotificationReadAt({created_at:created,is_read:true,read_at:'2026-11-18T10:02:00.000Z'}),'2026-11-18T10:02:00.000Z');
});

test('home unread refresh follows the same notice-only event policy as the web sync handler',()=>{
 for(const type of ['NOTICE_CREATED','NOTICE_RESOLVED','NOTIFICATIONS_READ']){
  assert.equal(shouldRefreshHomeUnread({event_type:type}),true,type);
  assert.equal(shouldRefreshHomeUnread({type:type.toLowerCase()}),true,type+' fallback');
 }
 for(const type of ['PATIENT_CREATED','PATIENT_UPDATED','PATIENT_DELETED','ANALYSIS_CREATED','ANALYSIS_UPDATED','PROGRAM_UPDATED','MESSAGE_CREATED','CASE_CREATED','PROFILE_UPDATED','CASE_STATUS_UPDATED']){
  assert.equal(shouldRefreshHomeUnread({event_type:type}),false,type);
 }
 assert.equal(shouldRefreshHomeUnread(null),false);
 assert.equal(shouldRefreshHomeUnread({event_type:7}),false);
 assert.equal(shouldRefreshHomeUnread({event_type:'PATIENT_UPDATED',type:'NOTICE_CREATED'}),false);
});

test('home badge uses a count-only request and filters unrelated realtime events',()=>{
 const app=fs.readFileSync(path.join(__dirname,'../App.tsx'),'utf8');
 const api=fs.readFileSync(path.join(__dirname,'../src/modernApi.ts'),'utf8');
 const start=app.indexOf('function Home('),end=app.indexOf('\\nfunction ',start+10);
 const home=app.slice(start,end);
 assert.ok(home.includes('getNotificationUnreadCount(token)'));
 assert.ok(home.includes('shouldRefreshHomeUnread(lastEvent)'));
 assert.ok(!home.includes('getNotifications(token)'));
 assert.ok(!home.includes('if(lastEvent)loadUnread()'));
 assert.ok(api.includes('"/notifications/unread-count"'));
 assert.ok(api.includes('normalizeNotificationReadAt(n)'));
});
