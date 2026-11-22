// Transport resilience contracts fixed by the adversarial audit: bounded
// attachment deadlines, offline-vs-HTTP error separation, proxy HTML error
// pages and the no-JSON-Content-Type multipart house pattern.
const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict'),{test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const api=require('../src/api.ts'),modern=require('../src/modernApi.ts');
const html=status=>new Response('<html>proxy error page</html>',{status,headers:{'content-type':'text/html'}});

test('chat attachment uploads abort at 120s with the Turkish stalled-transfer copy',async t=>{
 const original=global.fetch;
 try{
  t.mock.timers.enable({apis:['setTimeout']});
  global.fetch=(_url,init)=>new Promise((_,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('aborted'))));
  const body=new FormData();body.append('file',{uri:'file:///f.png',name:'f.png',type:'image/png'});
  const pending=assert.rejects(()=>modern.modernRequest('/consultations/3/attachments','tok',{method:'POST',body}),
   error=>error instanceof api.ApiError&&error.status===408&&/Sunucu yanıt vermedi/.test(error.message));
  t.mock.timers.tick(120000);
  await pending;
 }finally{global.fetch=original;t.mock.timers.reset()}
});

test('offline fetch failures stay a distinct 503 and non-transport errors keep their identity',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>{throw new TypeError('Network request failed')};
  await assert.rejects(()=>api.getPatients('tok'),error=>error instanceof api.ApiError&&error.status===503&&/bağlanılamadı/.test(error.message));
  await assert.rejects(()=>modern.getNotifications('tok'),error=>error instanceof api.ApiError&&error.status===503&&/bağlanılamadı/.test(error.message));
  global.fetch=async()=>{throw new Error('socket hang up')};
  await assert.rejects(()=>api.getPatients('tok'),error=>!(error instanceof api.ApiError)&&error.message==='socket hang up');
 }finally{global.fetch=original}
});

test('proxy HTML error pages surface Turkish copy instead of crashing either client',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>html(502);
  await assert.rejects(()=>api.getDashboard('tok'),error=>error instanceof api.ApiError&&error.status===502&&error.message.length>0);
  await assert.rejects(()=>modern.getNotifications('tok'),error=>error instanceof api.ApiError&&error.status===502);
  global.fetch=async()=>html(200);
  await assert.rejects(()=>api.getDashboard('tok'),error=>error.status===502&&/beklenen JSON/.test(error.message));
  await assert.rejects(()=>modern.getNotifications('tok'),error=>error.status===502&&/beklenen JSON/.test(error.message));
  global.fetch=async()=>html(500);
  await assert.rejects(()=>api.uploadPatientMedia('tok',9,{uri:'file:///k.jpeg',name:'k.jpeg',type:'image/jpeg'}),
   error=>error instanceof api.ApiError&&error.status===500&&/Görüntü yüklenemedi/.test(error.message));
 }finally{global.fetch=original}
});

test('multipart bodies never carry the JSON Content-Type header',async()=>{
 const original=global.fetch;const seen=[];
 try{
  global.fetch=async(url,init)=>{seen.push(init);return new Response(JSON.stringify(seen.length===1
   ?{ok:true,message:{id:4,sender_user_id:2,message_type:'FILE',content:'r',created_at:'2026-11-01T00:00:00'}}
   :{media:{id:7,original_filename:'k.jpeg',media_type:'PHOTO'},replayed:false}),{status:200})};
  await modern.sendChatFile('tok',3,{uri:'file:///f.png',name:'f.png',type:'image/png'});
  assert.equal(seen[0].headers['Content-Type'],undefined);
  assert.equal(seen[0].headers.Authorization,'Bearer tok');
  await api.uploadPatientMedia('tok',9,{uri:'file:///k.jpeg',name:'k.jpeg',type:'image/jpeg'},undefined,'PHOTO','key-request-key-16');
  assert.equal(seen[1].headers['Content-Type'],undefined);
  assert.equal(seen[1].headers.Authorization,'Bearer tok');
  assert.ok(seen[1].body instanceof FormData);
  assert.equal(seen[1].body.get('media_type'),'PHOTO');
  assert.equal(seen[1].body.get('request_key'),'key-request-key-16');
 }finally{global.fetch=original}
});
