const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
const {resolveNativeNotificationTarget:resolve}=require('../src/notificationTarget.ts');

test('canonical web consultation case links open the native case chat',()=>{
 for(const url of ['/expert-support/cases/42','/expert-support/cases/42/','/expert-support/cases/42?tab=messages','/expert-support/cases/42/messages','/consultations/42','/expert/consultations/42/messages','/cases/42'])
  assert.deepEqual(resolve(url),{kind:'navigate',route:{screen:'ConsultationChat',params:{id:42}}});
});

test('web consultation inbox links open the native inbox',()=>{
 assert.deepEqual(resolve('/consultations'),{kind:'navigate',route:{screen:'Consultations'}});
 assert.deepEqual(resolve('/expert/consultations?filter=active'),{kind:'navigate',route:{screen:'Consultations'}});
});

test('web expert directory and owned profile links map to their native screens',()=>{
 assert.deepEqual(resolve('/expert-support'),{kind:'navigate',route:{screen:'ExpertDirectory'}});
 assert.deepEqual(resolve('/expert-support/profile'),{kind:'navigate',route:{screen:'ExpertManagement'}});
});

test('web program reminder links open the native program',()=>{
 assert.deepEqual(resolve('/program'),{kind:'navigate',route:{screen:'Program'}});
 assert.deepEqual(resolve('/program?view=week'),{kind:'navigate',route:{screen:'Program'}});
});

test('patient links retain the selected patient identity in the nested native stack',()=>{
 assert.deepEqual(resolve('/patients/23'),{kind:'navigate',route:{screen:'Patients',params:{screen:'PatientDetail',params:{id:23}}}});
});

test('missing target URLs remain actionable as read-only notifications',()=>{
 assert.deepEqual(resolve(null),{kind:'none'});
 assert.deepEqual(resolve('   '),{kind:'none'});
});

test('unsupported routes are explicit instead of opening an unrelated screen',()=>{
 assert.deepEqual(resolve('/support-request'),{kind:'unsupported',path:'/support-request'});
 assert.deepEqual(resolve('/admin'),{kind:'unsupported',path:'/admin'});
});

test('external, protocol-relative and control-character targets are rejected',()=>{
 for(const url of ['https://evil.example','//evil.example/path','/\\evil.example','/program\u0000'])
  assert.equal(resolve(url).kind,'unsupported');
});

test('malformed or oversized identifiers never become navigation params',()=>{
 for(const url of ['/expert-support/cases/0','/expert-support/cases/9007199254740992','/patients/abc','/patients/999999999999999999999'])
  assert.equal(resolve(url).kind,'unsupported');
});

test('notification screen resolves the web route before marking it read',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/ModernScreens.tsx'),'utf8');
 const start=source.indexOf('async function open(item:any){');
 const end=source.indexOf('\n }',start);
 const open=source.slice(start,end);
 assert.ok(open.indexOf('resolveNativeNotificationTarget(item.target_url)')>=0);
 assert.ok(open.indexOf('target.kind==="unsupported"')<open.indexOf('markNotificationRead(token,item.id)'));
 assert.ok(open.includes('Bu bildirimin hedef sayfası henüz mobil uygulamada bulunmuyor'));
});
