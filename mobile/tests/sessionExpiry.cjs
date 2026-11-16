const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict'),{test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
test('only an expired current session triggers sign-out; delayed old tokens and unsubscribed screens do not',()=>{
 const {subscribeSessionExpiry,reportSessionExpiry}=require('../src/sessionExpiry.ts');
 const events=[];const stop=subscribeSessionExpiry('current',()=>events.push('expired'));
 reportSessionExpiry('old');assert.equal(events.length,0);reportSessionExpiry('current');assert.equal(events.length,1);stop();reportSessionExpiry('current');assert.equal(events.length,1);
});
test('all authenticated JSON clients preserve HTTP status and report 401 only',async()=>{
 const {subscribeSessionExpiry}=require('../src/sessionExpiry.ts'),{ApiError,getMe}=require('../src/api.ts'),modern=require('../src/modernApi.ts'),analysis=require('../src/analysisApi.ts'),social=require('../src/socialApi.ts');
 const original=global.fetch,events=[];const stop=subscribeSessionExpiry('current',()=>events.push('expired'));
 try{
  for(const status of [401,403,429,503]){
   global.fetch=async()=>new Response(JSON.stringify({detail:'synthetic'}),{status});
   for(const call of [()=>getMe('current'),()=>modern.getCourses('current'),()=>analysis.getAnalysis('current',1),()=>social.getFeed('current','discover')])await assert.rejects(call,e=>e instanceof ApiError&&e.status===status);
  }
  assert.equal(events.length,1);
 }finally{stop();global.fetch=original;}
});
