const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict'),{test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const session=require('../src/sessionExpiry.ts');
const api=require('../src/api.ts'),modern=require('../src/modernApi.ts'),social=require('../src/socialApi.ts'),analysis=require('../src/analysisApi.ts');
const reply=(status,body={detail:'synthetic'})=>({ok:status>=200&&status<300,status,text:async()=>JSON.stringify(body)});
const clients=[()=>api.getPatients('expired'),()=>modern.getCourses('expired'),()=>social.getFeed('expired','discover'),()=>analysis.getAnalysis('expired',7)];
test('each protected client checks canonical session after 401 and expires only confirmed invalid tokens',async()=>{
 const original=global.fetch;
 try{for(const call of clients){let probes=0,expired=0;const stop=session.subscribeSessionExpiry('expired',()=>expired++);
  global.fetch=async url=>{if(url.endsWith('/me'))probes++;return reply(401)};
  await assert.rejects(call);assert.equal(probes,1);assert.equal(expired,1);stop();
 }}finally{global.fetch=original}
});
test('feature-specific 401 with valid session never signs out or retries a mutation',async()=>{
 const original=global.fetch;let probes=0,expired=0,calls=0;const stop=session.subscribeSessionExpiry('expired',()=>expired++);
 global.fetch=async url=>{calls++;if(url.endsWith('/me')){probes++;return reply(200,{user:{id:1,is_active:true}})}return reply(401)};
 try{for(const call of clients)await assert.rejects(call);assert.equal(probes,clients.length);assert.equal(expired,0);assert.equal(calls,clients.length*2)}finally{stop();global.fetch=original}
});
test('simultaneous expired screens share one session probe and issue one expiry notification',async()=>{
 const original=global.fetch;let probes=0,expired=0,finish;const stop=session.subscribeSessionExpiry('expired',()=>expired++);
 global.fetch=async url=>{if(url.endsWith('/me')){probes++;return new Promise(resolve=>{finish=()=>resolve(reply(401))})}return reply(401)};
 try{const requests=Promise.allSettled(clients.map(call=>call()));await new Promise(resolve=>setImmediate(resolve));assert.equal(probes,1);finish();await requests;assert.equal(expired,1)}finally{stop();global.fetch=original}
});
test('transient session-probe failure preserves login and 403 never requests a session check',async()=>{
 const original=global.fetch;let expired=0,probes=0;const stop=session.subscribeSessionExpiry('expired',()=>expired++);
 try{for(const probe of [()=>reply(503),()=>reply(200,{html:'wrong schema'}),()=>{throw new TypeError('offline')}]){
  global.fetch=async url=>{if(url.endsWith('/me')){probes++;return probe()}return reply(401)};
  await assert.rejects(()=>api.getPatients('expired'));
 }assert.equal(probes,3);assert.equal(expired,0);
 global.fetch=async url=>{assert.ok(!url.endsWith('/me'));return reply(403)};
 await assert.rejects(()=>api.getPatients('expired'));assert.equal(expired,0);
 }finally{stop();global.fetch=original}
});
