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

test('mobile lists reject malformed server data before rendering clinical or account records',async()=>{
 const modern=require('../src/modernApi.ts'),original=global.fetch;
 try{
  for(const body of [{}, {items:null}, {items:{}}, {items:[null]}, {items:[{id:'bad',title:'Test',message:'Test'}]}]){
   global.fetch=async()=>new Response(JSON.stringify(body),{status:200});
   await assert.rejects(()=>modern.getNotifications('current'),/geçersiz liste/);
  }
  for(const body of [{}, {items:{}}, {items:[null]}, {items:[{id:'bad',patient_id:1,status:'ready'}]}]){
   global.fetch=async()=>new Response(JSON.stringify(body),{status:200});
   await assert.rejects(()=>modern.getAnalysisHistory('current'),/geçersiz liste/);
  }
  global.fetch=async()=>new Response(JSON.stringify({items:[],total:0}),{status:200});
  assert.equal((await modern.getAnalysisHistory('current')).items.length,0);
  global.fetch=async()=>new Response(JSON.stringify({notifications:[],unread_count:0}),{status:200});
  assert.equal((await modern.getNotifications('current')).items.length,0);
 }finally{global.fetch=original}
});

test('mobile notifications and analyses accept the actual FastAPI response contracts',async()=>{
 const modern=require('../src/modernApi.ts'),original=global.fetch;
 try{
  global.fetch=async()=>new Response(JSON.stringify({
   unread_count:1,unread:1,
   notifications:[{id:11,title:'Klinik',message:'Yeni mesaj',notice_type:'MESSAGE',is_read:false,read_at:null,created_at:'2026-11-11T07:00:00'}],
   items:[{id:11,title:'Klinik',message:'Yeni mesaj',notice_type:'MESSAGE',read_at:null,created_at:'2026-11-11T07:00:00'}]
  }),{status:200});
  const notices=await modern.getNotifications('current');
  assert.equal(notices.items.length,1);assert.equal(notices.unread,1);assert.equal(notices.items[0].read_at,null);
  global.fetch=async()=>new Response(JSON.stringify({total:1,items:[{id:14,patient_id:9,patient_name:'Hasta',tooth_number:'46',clinical_notes:'Kontrol',status:'AI_ANALYZED',created_at:'2026-11-11T07:00:00'}]}),{status:200});
  const analyses=await modern.getAnalysisHistory('current');
  assert.equal(analyses.total,1);assert.equal(analyses.items[0].patient_id,9);
 }finally{global.fetch=original}
});

test('analysis history uses a bounded cursor and preserves valid empty final pages',async()=>{
 const modern=require('../src/modernApi.ts'),original=global.fetch,urls=[];
 try{
  global.fetch=async url=>{urls.push(String(url));return new Response(JSON.stringify({total:0,next_before:null,items:[]}),{status:200})};
  await modern.getAnalysisHistory('current');
  await modern.getAnalysisHistory('current',123);
  assert.match(urls[0],/\/analyses\?limit=50$/);
  assert.match(urls[1],/\/analyses\?limit=50&before=123$/);
 }finally{global.fetch=original}
});

test('analysis pagination rejects invalid cursor metadata and oversized pages',async()=>{
 const modern=require('../src/modernApi.ts'),original=global.fetch;
 const row=id=>({id,patient_id:1,status:'READY'});
 try{
  for(const body of [
   {items:[],total:0,next_before:-1},
   {items:[],total:0,next_before:'bad'},
   {items:[],total:-1,next_before:null},
   {items:[],total:0,next_before:42},
   {items:[],total:'zero',next_before:null},
   {items:Array.from({length:51},(_,i)=>row(i+1)),total:51,next_before:null}
  ]){
   global.fetch=async()=>new Response(JSON.stringify(body),{status:200});
   await assert.rejects(()=>modern.getAnalysisHistory('current'),/geçersiz liste/);
  }
 }finally{global.fetch=original}
});

test('analysis history rejects non-advancing cursors and repeated boundary rows',async()=>{
 const modern=require('../src/modernApi.ts'),original=global.fetch;
 try{
  for(const body of [
   {items:[{id:123,patient_id:1,status:'READY'}],total:1,next_before:null},
   {items:[{id:122,patient_id:1,status:'READY'}],total:1,next_before:123},
   {items:[{id:124,patient_id:1,status:'READY'}],total:1,next_before:null}
  ]){
   global.fetch=async()=>new Response(JSON.stringify(body),{status:200});
   await assert.rejects(()=>modern.getAnalysisHistory('current',123),/geçersiz liste/);
  }
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:122,patient_id:1,status:'READY'}],total:1,next_before:122}),{status:200});
  const page=await modern.getAnalysisHistory('current',123);
  assert.equal(page.next_before,122);
 }finally{global.fetch=original}
});

test('analysis history rejects null records even with a cursor and accepts legacy terminal pages',async()=>{
 const modern=require('../src/modernApi.ts'),original=global.fetch;
 try{
  global.fetch=async()=>new Response(JSON.stringify({items:[null],total:1,next_before:12}),{status:200});
  await assert.rejects(()=>modern.getAnalysisHistory('current',50),/geçersiz liste/);
  global.fetch=async()=>new Response(JSON.stringify({items:[],total:0}),{status:200});
  const result=await modern.getAnalysisHistory('current');
  assert.equal(result.next_before,null);
 }finally{global.fetch=original}
});

test('clinical media rejects malformed private image pages and stale cursors',async()=>{
 const modern=require('../src/modernApi.ts'),original=global.fetch;
 try{
  for(const body of [
   {items:[null],next_before:null},
   {items:[{id:'bad'}],next_before:null},
   {items:[],next_before:5},
   {items:[{id:42}],next_before:null},
   {items:[{id:41}],next_before:42}
  ]){
   global.fetch=async()=>new Response(JSON.stringify(body),{status:200});
   await assert.rejects(()=>modern.getMedia('current',1,42),/geçersiz liste/);
  }
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:41,original_filename:'x.jpg'}],next_before:null}),{status:200});
  const page=await modern.getMedia('current',1,42);
  assert.equal(page.items[0].filename,'x.jpg');
  assert.equal(page.next_before,null);
 }finally{global.fetch=original}
});
