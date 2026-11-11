const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const api=require('../src/socialApi.ts'),{submitDraft,readDraft,draftKey}=require('../src/socialDraft.ts');
test('native social contract uses bearer, explicit states and versioned edits',async()=>{
 const original=global.fetch,calls=[];global.fetch=async(url,init)=>{calls.push({url,...init});return new Response('{}')};
 try{await api.getFeed('secret','discover',12);await api.setPostLike('secret',8,true);await api.setFollow('secret',7,false);await api.patchPost('secret',{id:8,version:3},{pinned:true});
 assert.match(calls[0].url,/feed\/discover\?limit=15&details=true&before=12/);assert.equal(calls[0].headers.Authorization,'Bearer secret');assert.equal(calls[0].credentials,'omit');assert.deepEqual(JSON.parse(calls[1].body),{liked:true});assert.deepEqual(JSON.parse(calls[2].body),{followed:false});assert.deepEqual(JSON.parse(calls[3].body),{version:3,pinned:true});}finally{global.fetch=original;}
});
test('failed commit response and app restart retain the same payload and UUID',async()=>{
 const values=new Map(),store={getItemAsync:async k=>values.get(k)||null,setItemAsync:async(k,v)=>values.set(k,v),deleteItemAsync:async k=>values.delete(k)};
 const key=draftKey(1,'post'),draft={id:'same-uuid',text:'metin',link:'',media_ids:[],attempted:false};
 await assert.rejects(()=>submitDraft(store,key,draft,async()=>{throw new Error('offline')}));
 const saved=await readDraft(store,key);assert.equal(saved.id,draft.id);assert.equal(saved.text,draft.text);assert.equal(saved.attempted,true);assert.equal(await readDraft(store,draftKey(2,'post')),null);
 const result=await submitDraft(store,key,saved,async d=>{assert.equal(d.id,draft.id);return {id:5}});assert.equal(result.id,5);assert.equal(await readDraft(store,key),null);
});
test('storage failure prevents sending an unpersisted mutation',async()=>{
 let sent=false;await assert.rejects(()=>submitDraft({setItemAsync:async()=>{throw Error('full')}},'x',{},async()=>{sent=true}));assert.equal(sent,false);
});
test('validation rejection unlocks the same draft for correction; ambiguous failure stays frozen',async()=>{
 const {ApiError}=require('../src/api.ts');let saved;
 const store={setItemAsync:async(k,v)=>{saved=JSON.parse(v)},deleteItemAsync:async()=>{}};
 const draft={id:'uuid',text:'draft',link:'invalid',media_ids:[],attempted:false};
 await assert.rejects(()=>submitDraft(store,'x',draft,async()=>{throw new ApiError(422,'invalid URL')}));assert.equal(saved.attempted,false);assert.equal(saved.text,'draft');
 await assert.rejects(()=>submitDraft(store,'x',draft,async()=>{throw new ApiError(503,'unavailable')}));assert.equal(saved.attempted,true);
});
test('long Unicode drafts fit small secure-store values and interrupted writes preserve prior intent',async()=>{
 const {chunkedDraftStore}=require('../src/socialDraft.ts');const map=new Map();let fail=false;
 const raw={getItemAsync:async k=>map.get(k)||null,setItemAsync:async(k,v)=>{assert.ok(Buffer.byteLength(v)<=1800);if(fail&&k.endsWith('.1'))throw Error('device full');map.set(k,v)},deleteItemAsync:async k=>map.delete(k)};
 let n=0;const store=chunkedDraftStore(raw,()=>String(++n)),key='draft';const first=JSON.stringify({text:'🦷'.repeat(2000)});
 await store.setItemAsync(key,first);assert.equal(await store.getItemAsync(key),first);
 fail=true;await assert.rejects(()=>store.setItemAsync(key,'çok uzun'.repeat(1000)));assert.equal(await store.getItemAsync(key),first);
 fail=false;await store.deleteItemAsync(key);assert.equal(await store.getItemAsync(key),null);
});
test('successive writers and immediate readers observe the newest complete secure draft',async()=>{
 const {chunkedDraftStore}=require('../src/socialDraft.ts');const values=new Map();let n=0;
 const raw={getItemAsync:async k=>values.get(k)||null,setItemAsync:async(k,v)=>{await new Promise(r=>setTimeout(r,k.includes('.1.')?5:0));values.set(k,v)},deleteItemAsync:async k=>values.delete(k)};
 const store=chunkedDraftStore(raw,()=>String(++n));
 const first=store.setItemAsync('key','first'.repeat(100));const second=store.setItemAsync('key','second');const read=store.getItemAsync('key');await Promise.all([first,second]);assert.equal(await read,'second');assert.equal(await store.getItemAsync('key'),'second');
});

test('social images never send bearer tokens to external or lookalike hosts',()=>{
 const first=api.socialImageSource('/api/expert-social/experts/7/photo','secret');
 assert.equal(first.uri,'https://dentalai.tr/api/expert-social/experts/7/photo');
 assert.equal(first.headers.Authorization,'Bearer secret');
 const legacy=api.socialImageSource('/profile-photo/7','secret');
 assert.equal(legacy.uri,'https://dentalai.tr/api/expert-social/experts/7/photo');
 assert.equal(legacy.headers.Authorization,'Bearer secret');
 for(const url of [
  'https://example.org/photo.jpg',
  'https://dentalai.tr.evil.example/photo.jpg',
  'http://dentalai.tr/photo.jpg',
  'https://dentalai.tr@evil.example/photo.jpg',
 ]){
  const source=api.socialImageSource(url,'secret');
  assert.equal(source.uri,url);
  assert.equal(source.headers,undefined,'unexpected authorization for '+url);
 }
});

test('expert consultation pages reject malformed records and non-progressing cursors',async()=>{
 const {getConsultations}=require('../src/modernApi.ts'),original=global.fetch;
 try{
  for(const payload of [
   {items:null,next_before:null},
   {items:[null],next_before:null},
   {items:[{id:8}],next_before:10},
   {items:[],next_before:4},
  ]){
   global.fetch=async()=>new Response(JSON.stringify(payload),{status:200});
   await assert.rejects(()=>getConsultations('secret',9),/geçersiz liste/);
  }
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:7,other_display_name:'Uzman'}],next_before:6}),{status:200});
  const page=await getConsultations('secret',9);
  assert.equal(page.items[0].other_name,'Uzman');assert.equal(page.next_before,6);
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:8}],next_before:8}),{status:200});
  assert.equal((await getConsultations('secret',9)).next_before,8);
 }finally{global.fetch=original;}
});

test('academic pagination rejects invalid records, stalled cursors and malformed message bodies',async()=>{
 const {getCourses,getAcademicMessages}=require('../src/modernApi.ts'),original=global.fetch;
 try{
  for(const response of [
   {items:null,next_before:null},
   {items:[{id:12}],next_before:13},
   {items:[],next_before:5},
  ]){
   global.fetch=async()=>new Response(JSON.stringify(response),{status:200});
   await assert.rejects(()=>getCourses('secret',13),/geçersiz sayfa/);
  }
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:11,role:'assistant',content:'Yanıt',created_at:'now'}],next_before:10}),{status:200});
  const valid=await getAcademicMessages('secret',2,13);
  assert.equal(valid.items[0].content,'Yanıt');assert.equal(valid.next_before,10);
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:12,title:'Ders'}],next_before:12}),{status:200});
  assert.equal((await getCourses('secret',13)).next_before,12);
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:11,role:'assistant',content:null}],next_before:null}),{status:200});
  await assert.rejects(()=>getAcademicMessages('secret',2,13),/geçersiz kayıt/);
 }finally{global.fetch=original;}
});

test('notification unread badges reject malformed server counts',async()=>{
 const {getNotifications}=require('../src/modernApi.ts'),original=global.fetch;
 try{
  for(const unread of [-1,'NaN',1.5,'Infinity']){
   global.fetch=async()=>new Response(JSON.stringify({items:[],unread}),{status:200});
   await assert.rejects(()=>getNotifications('secret'),/geçersiz okunmamış sayısı/);
  }
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:3,title:'Randevu',message:'Bilgi',created_at:'now',is_read:true}],unread:0}),{status:200});
  const result=await getNotifications('secret');
  assert.equal(result.unread,0);assert.equal(result.items[0].read_at,'now');
 }finally{global.fetch=original;}
});

test('clinical media archive rejects malformed records and stale pagination',async()=>{
 const {getMedia}=require('../src/modernApi.ts'),original=global.fetch;
 let calls=0;
 try{
  global.fetch=async()=>{calls++;return new Response('{}',{status:200})};
  await assert.rejects(()=>getMedia('secret',0),/Geçersiz hasta/);
  await assert.rejects(()=>getMedia('secret',7,-2),/Geçersiz hasta/);
  assert.equal(calls,0,'invalid IDs must not reach the API');
  for(const payload of [
   {items:null,next_before:null},
   {items:[{id:'3'}],next_before:null},
   {items:[{id:5,filename:{unsafe:true}}],next_before:null},
   {items:[],next_before:4},
   {items:[{id:9}],next_before:10},
  ]){
   global.fetch=async()=>new Response(JSON.stringify(payload),{status:200});
   await assert.rejects(()=>getMedia('secret',7,10),/geçersiz liste/);
  }
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:8,original_filename:'scan.png'}],next_before:8}),{status:200});
  const page=await getMedia('secret',7,10);
  assert.equal(page.items[0].filename,'scan.png');
  assert.equal(page.items[0].url,'https://dentalai.tr/api/mobile/v1/patients/7/media/8/file');
  assert.equal(page.next_before,8);
 }finally{global.fetch=original;}
});
