const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const api=require('../src/socialApi.ts'),{submitDraft,readDraft,draftKey}=require('../src/socialDraft.ts');
test('owner moderation refresh uses bearer auth and rejects mismatched or malformed post receipts',async()=>{
 const original=global.fetch,calls=[],payload={id:42,author_id:7,author_name:'Verified expert',text:'Pending post',status:'PENDING',version:3,owned:true,pinned:false,comments_closed:false,liked:false,like_count:0,comment_count:0,media:[],created_at:'2026-11-17T13:20:00Z',moderation:{job_id:9,registered:true,content_version:3,revision:2,state:'WAITING_HUMAN',wait_type:'HUMAN_REVIEW',reasons:['IMAGE_REVIEW'],reason:'Görsel yönetici incelemesi bekliyor.',retryable:false}};
 try{
  global.fetch=async(url,init)=>{calls.push({url,...init});return new Response(JSON.stringify(payload),{status:200});};
  const result=await api.getPost('secret',42);
  assert.equal(result.id,42);assert.equal(result.moderation.reason,payload.moderation.reason);
  assert.equal(calls[0].url,'https://dentalai.tr/api/expert-social/posts/42');
  assert.equal(calls[0].credentials,'omit');assert.equal(calls[0].headers.Authorization,'Bearer secret');
  await assert.rejects(()=>api.getPost('secret',0),/kimliği/);
  assert.equal(calls.length,1,'invalid IDs must be rejected before network access');
  global.fetch=async()=>new Response(JSON.stringify({...payload,id:43}),{status:200});
  await assert.rejects(()=>api.getPost('secret',42),/alanları doğrulanamadı/);
  global.fetch=async()=>new Response(JSON.stringify({...payload,moderation:{...payload.moderation,reason:17}}),{status:200});
  await assert.rejects(()=>api.getPost('secret',42),/inceleme durumu doğrulanamadı/);
  global.fetch=async()=>new Response(JSON.stringify({...payload,media:[{id:9,url:'https://evil.example/private.jpg'}]}),{status:200});
  await assert.rejects(()=>api.getPost('secret',42),/alanları doğrulanamadı/);
  global.fetch=async()=>new Response(JSON.stringify({...payload,owned:false}),{status:200});
  await assert.rejects(()=>api.getPost('secret',42),/sahibi doğrulanamadı/);
 }finally{global.fetch=original;}
});

test('moderation status uses the owner-scoped minimal endpoint and rejects malformed receipts',async()=>{
 const original=global.fetch,calls=[];
 const moderation={job_id:9,registered:true,content_version:3,revision:2,state:'WAITING_HUMAN',wait_type:'HUMAN_REVIEW',reasons:['IMAGE_REVIEW'],reason:'Görsel yönetici incelemesi bekliyor.',retryable:false};
 const payload={target_type:'POST',target_id:42,status:'PENDING',version:3,moderation};
 try{
  global.fetch=async(url,init)=>{calls.push({url,...init});return new Response(JSON.stringify(payload),{status:200});};
  const result=await api.getPostModerationStatus('secret',42);
  assert.equal(result.target_id,42);assert.equal(result.status,'PENDING');assert.equal(result.moderation.reason,moderation.reason);
  assert.equal(calls[0].url,'https://dentalai.tr/api/expert-social/moderation-status/POST/42');
  assert.equal(calls[0].credentials,'omit');assert.equal(calls[0].headers.Authorization,'Bearer secret');
  await assert.rejects(()=>api.getPostModerationStatus('secret',0),/kimliği/);
  assert.equal(calls.length,1,'invalid IDs must be rejected before network access');
  global.fetch=async()=>new Response(JSON.stringify({...payload,target_id:43}),{status:200});
  await assert.rejects(()=>api.getPostModerationStatus('secret',42),/alanları doğrulanamadı/);
  global.fetch=async()=>new Response(JSON.stringify({...payload,status:'DELETED'}),{status:200});
  await assert.rejects(()=>api.getPostModerationStatus('secret',42),/alanları doğrulanamadı/);
  global.fetch=async()=>new Response(JSON.stringify({...payload,moderation:{...moderation,reason:17}}),{status:200});
  await assert.rejects(()=>api.getPostModerationStatus('secret',42),/alanları doğrulanamadı/);
 }finally{global.fetch=original;}
});

test('native social contract uses bearer, explicit states and versioned edits',async()=>{
 const original=global.fetch,calls=[];global.fetch=async(url,init)=>{calls.push({url,...init});return new Response('{}')};
 try{await api.getFeed('secret','discover',12);await api.setPostLike('secret',8,true);await api.setFollow('secret',7,false);await api.patchPost('secret',{id:8,version:3},{pinned:true});
 assert.match(calls[0].url,/feed\/discover\?limit=15&details=true&before=12/);assert.equal(calls[0].headers.Authorization,'Bearer secret');assert.equal(calls[0].credentials,'omit');assert.deepEqual(JSON.parse(calls[1].body),{liked:true});assert.deepEqual(JSON.parse(calls[2].body),{followed:false});assert.deepEqual(JSON.parse(calls[3].body),{version:3,pinned:true});}finally{global.fetch=original;}
});
test('native Dental Flow link previews use the safe HTTPS endpoint and retain the server receipt',async()=>{
 const original=global.fetch,calls=[];
 global.fetch=async(url,init)=>{calls.push({url,...init});if(String(url).endsWith('/preview'))return new Response(JSON.stringify({available:true,id:77,url:'https://example.org/article',domain:'example.org',site_name:'Example',title:'Example title',description:'Safe preview',cover:{id:81,url:'/api/expert-social/media/81'}}));return new Response(JSON.stringify({id:5}),{status:201});};
 try{
  const preview=await api.getLinkPreview('secret','https://example.org/article');
  assert.equal(preview.id,77);assert.equal(preview.available,true);
  assert.equal(calls[0].url,'https://dentalai.tr/api/expert-social/preview');
  assert.equal(calls[0].credentials,'omit');
  assert.equal(calls[0].headers.Authorization,'Bearer secret');
  assert.deepEqual(JSON.parse(calls[0].body),{url:'https://example.org/article'});
  await api.createPost('secret',{text:'',link_url:'https://example.org/article',media_ids:[],idempotency_key:'11111111-1111-4111-8111-111111111111',preview_id:77});
  assert.equal(JSON.parse(calls[1].body).preview_id,77);
  assert.equal(JSON.parse(calls[1].body).media_ids.length,0);
  await assert.rejects(()=>api.getLinkPreview('secret','http://example.org/article'),/HTTPS/);
  assert.equal(calls.length,2,'non-HTTPS input must be rejected before network access');
 }finally{global.fetch=original;}
});
test('encrypted Dental Flow drafts restore a bounded preview and reject invalid media IDs',async()=>{
 const valid={id:'same-key',text:'draft',link:'https://example.org/article',media_ids:[11,12],attempted:false,preview_id:77,preview:{available:true,id:77,url:'https://example.org/article',domain:'example.org',title:'Example',cover:{id:81,url:'/api/expert-social/media/81'}}};
 const saved=await readDraft({getItemAsync:async()=>JSON.stringify(valid)},'draft');
 assert.equal(saved.preview_id,77);assert.equal(saved.preview.cover.id,81);assert.deepEqual(saved.media_ids,[11,12]);
 for(const media_ids of [[0],[1,1],[1,2,3,4,5]]){
  await assert.rejects(()=>readDraft({getItemAsync:async()=>JSON.stringify({...valid,media_ids})},'draft'),/Taslak okunamadı/);
 }
 const legacy=await readDraft({getItemAsync:async()=>JSON.stringify({id:'legacy',text:'old',link:'',media_ids:[],attempted:false})},'draft');
 assert.equal(legacy.preview,null);assert.equal(legacy.preview_id,undefined);
});
test('preview receipts reject non-HTTPS restores and mismatched cover IDs',async()=>{
 const base={id:'same-key',text:'draft',link:'https://example.org/article',media_ids:[],attempted:false,preview_id:77,preview:{available:true,id:77,url:'https://example.org/article',cover:{id:81,url:'/api/expert-social/media/82'}}};
 const restored=await readDraft({getItemAsync:async()=>JSON.stringify(base)},'draft');
 assert.equal(restored.preview_id,77);assert.equal(restored.preview.cover,null);
 const unsafe=await readDraft({getItemAsync:async()=>JSON.stringify({...base,link:'http://example.org/article',preview:{...base.preview,url:'http://example.org/article'}})},'draft');
 assert.equal(unsafe.preview_id,undefined);assert.equal(unsafe.preview,null);
 const original=global.fetch;
 global.fetch=async()=>new Response(JSON.stringify({available:true,id:77,url:'https://example.org/article',cover:{id:81,url:'/api/expert-social/media/82'}}));
 try{await assert.rejects(()=>api.getLinkPreview('secret','https://example.org/article'),/Bağlantı görseli doğrulanamadı/);}
 finally{global.fetch=original;}
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
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:7,other_display_name:'Uzman'}],next_before:7}),{status:200});
  const page=await getConsultations('secret',9);
  assert.equal(page.items[0].other_display_name,'Uzman');assert.equal(page.next_before,7);
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
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:11,role:'assistant',content:'Yanıt',created_at:'now'}],next_before:11}),{status:200});
  const valid=await getAcademicMessages('secret',2,13);
  assert.equal(valid.items[0].content,'Yanıt');assert.equal(valid.next_before,11);
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

test('invalid expert and academic identifiers are rejected before any network request',async()=>{
 const {getConsultations,getCourses,getAcademicMessages,askAcademic}=require('../src/modernApi.ts');
 const original=global.fetch;let calls=0;global.fetch=async()=>{calls++;throw Error('network should not be called')};
 try{
  for(const id of [0,-1,1.5,NaN,Infinity]){
   await assert.rejects(()=>getConsultations('secret',id),/Geçersiz/);
   await assert.rejects(()=>getCourses('secret',id),/Geçersiz/);
   await assert.rejects(()=>getAcademicMessages('secret',id),/Geçersiz/);
   await assert.rejects(()=>getAcademicMessages('secret',1,id),/Geçersiz/);
   assert.throws(()=>askAcademic('secret',id,'test'),/Geçersiz/);
  }
  assert.throws(()=>askAcademic('secret',1,'   '),/boş soru/);
  assert.equal(calls,0);
 }finally{global.fetch=original;}
});

test('consultation and notification mutations reject invalid IDs and empty messages without network',async()=>{
 const {markNotificationRead,getConsultation,sendConsultationMessage}=require('../src/modernApi.ts');
 const original=global.fetch;let calls=0;
 global.fetch=async()=>{calls++;return new Response(JSON.stringify({ok:true,message:{id:2}}),{status:200})};
 try{
  for(const id of [0,-1,1.5,NaN,Infinity]){
   assert.throws(()=>markNotificationRead('secret',id),/Geçersiz/);
   await assert.rejects(()=>getConsultation('secret',id),/Geçersiz/);
   assert.throws(()=>sendConsultationMessage('secret',id,'hello','uuid'),/Geçersiz/);
  }
  assert.throws(()=>sendConsultationMessage('secret',7,'  ','uuid'),/boş mesaj/);
  assert.throws(()=>sendConsultationMessage('secret',7,'hello',' '),/eksik istek/);
  assert.equal(calls,0);
  await markNotificationRead('secret',2);
  await sendConsultationMessage('secret',7,'hello','same-uuid');
  assert.equal(calls,2);
 }finally{global.fetch=original;}
});

test('analysis history and clinical media deletion reject malformed IDs before requests',async()=>{
 const {getAnalysisHistory,deleteMedia}=require('../src/modernApi.ts');
 const original=global.fetch;let calls=0;
 global.fetch=async()=>{calls++;return new Response(JSON.stringify({ok:true,media_id:4}),{status:200})};
 try{
  for(const id of [0,-1,1.5,NaN,Infinity]){
   await assert.rejects(()=>getAnalysisHistory('secret',id),/Geçersiz analiz/);
   assert.throws(()=>deleteMedia('secret',id,4),/Geçersiz hasta/);
   assert.throws(()=>deleteMedia('secret',7,id),/Geçersiz hasta/);
  }
  assert.equal(calls,0);
  const result=await deleteMedia('secret',7,4);
  assert.equal(result.media_id,4);assert.equal(calls,1);
 }finally{global.fetch=original;}
});

test('active mobile consultation and academic routes receive JSON payloads',async()=>{
 const {createConsultation,sendConsultationMessage,askAcademic}=require('../src/modernApi.ts');
 const original=global.fetch,calls=[];
 global.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify({ok:true,case_id:7,message:{id:9}}),{status:200})};
 try{
  await createConsultation('secret',{expert_user_id:12,patient_id:4,clinical_summary:'Klinik özet',question:'Öneriniz?'});
  await sendConsultationMessage('secret',7,'Merhaba','stable-client-id');
  await askAcademic('secret',3,'Çene anatomisi');
  assert.equal(calls.length,3);
  for(const call of calls){
   assert.equal(call.init.headers.Authorization,'Bearer secret');
   assert.equal(call.init.headers['Content-Type'],'application/json');
   assert.equal(typeof call.init.body,'string');
  }
  assert.equal(JSON.parse(calls[0].init.body).expert_user_id,12);
  assert.equal(JSON.parse(calls[0].init.body).patient_id,4);
  assert.equal(JSON.parse(calls[1].init.body).client_message_id,'stable-client-id');
  assert.equal(JSON.parse(calls[2].init.body).message,'Çene anatomisi');
  assert.throws(()=>createConsultation('secret',{expert_user_id:0,clinical_summary:'',question:'?'}),/Geçersiz/);
 }finally{global.fetch=original;}
});
test('active mobile media routes and analysis pagination contracts',()=>{
 const client=fs.readFileSync(require('node:path').join(__dirname,'../src/api.ts'),'utf8');
 const active=fs.readFileSync(require('node:path').join(__dirname,'../../app/mobile_api.py'),'utf8');
 const extended=fs.readFileSync(require('node:path').join(__dirname,'../../app/mobile_modern_api_v3.py'),'utf8');
 const main=fs.readFileSync(require('node:path').join(__dirname,'../../app/main.py'),'utf8');
 assert.match(main,/_mobile_mounted_routes/);
 assert.match(client,/body\.append\("file",\{uri:file\.uri/);
 assert.match(active,/file:UploadFile=File\(None\)/);
 assert.match(active,/@router\.delete\("\/patients\/\{patient_id\}\/media\/\{media_id\}"\)/);
 assert.match(active,/PatientMedia\.id < before/);
 assert.match(extended,/def mobile_analysis_history\([^\n]*before: int \| None = None\)/);
 assert.match(extended,/Analysis\.id < before/);
});

test('clinical media upload uses authorized multipart and validates committed response',async()=>{
 const {uploadPatientMedia,ApiError}=require('../src/api.ts');
 const original=global.fetch,calls=[];
 const file={uri:'file:///tmp/clinical.jpg',name:'clinical.jpg',type:'image/jpeg'};
 global.fetch=async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify({media:{id:17,original_filename:'clinical.jpg',media_type:'PHOTO'}}),{status:200})};
 try{
  for(const id of [0,-1,1.5,NaN,Infinity])await assert.rejects(()=>uploadPatientMedia('token',id,file),/Geçersiz hasta/);
  await assert.rejects(()=>uploadPatientMedia('token',5,{uri:'',name:'',type:''}),/Geçerli bir klinik/);
  await assert.rejects(()=>uploadPatientMedia('token',5,file,'99'),/Geçersiz FDI/);
  assert.equal(calls.length,0);
  const result=await uploadPatientMedia('token',5,file,'11','RADIOGRAPH');
  assert.equal(result.media.id,17);assert.equal(calls.length,1);
  assert.equal(calls[0].init.headers.Authorization,'Bearer token');
  assert.equal(calls[0].init.headers['Content-Type'],undefined);
  assert.equal(calls[0].init.body.get('media_type'),'RADIOGRAPH');
  assert.equal(calls[0].init.body.get('tooth_number'),'11');
  assert.ok(calls[0].init.body.get('file'));
  global.fetch=async()=>new Response(JSON.stringify({media:{id:0}}),{status:200});
  await assert.rejects(()=>uploadPatientMedia('token',5,file),/Yeniden yüklemeden önce galeriyi kontrol edin/);
  global.fetch=async()=>new Response(JSON.stringify({detail:'Erişim reddedildi'}),{status:403});
  await assert.rejects(()=>uploadPatientMedia('token',5,file),e=>e instanceof ApiError&&e.status===403);
 }finally{global.fetch=original;}
});

test('Dental Flow requests combine caller cancellation with an internal timeout',async()=>{
 const original=global.fetch;
 const caller=new AbortController();
 let captured;
 try{
  global.fetch=async(url,init)=>{captured=init.signal;return new Promise((resolve,reject)=>{if(init.signal.aborted)return reject(Object.assign(new Error('aborted'),{name:'AbortError'}));init.signal.addEventListener('abort',()=>reject(Object.assign(new Error('aborted'),{name:'AbortError'})),{once:true})})};
  const pending=api.socialRequest('token','/feed/discover',{signal:caller.signal});
  assert.ok(captured&&captured!==caller.signal,'internal timeout signal must not be replaced');
  caller.abort();
  await assert.rejects(pending,/aborted/);
  assert.equal(captured.aborted,true);
 }finally{global.fetch=original}
});

test('Dental Flow rejects successful empty or non-object API responses',async()=>{
 const original=global.fetch;
 try{
  for(const payload of ['', 'null', '[]', '"ok"', '42']){
   global.fetch=async()=>new Response(payload,{status:200});
   await assert.rejects(()=>api.getFeed('token','discover'),error=>error.status===502);
  }
  global.fetch=async()=>new Response(JSON.stringify({items:[],next_cursor:null}),{status:200});
  const page=await api.getFeed('token','discover');
  assert.deepEqual(page.items,[]);
  assert.deepEqual(page.specialties,['Endodonti','Ortodonti','Pedodonti','Periodontoloji','Protetik Diş Tedavisi','Restoratif Diş Tedavisi','Ağız, Diş ve Çene Cerrahisi','Ağız, Diş ve Çene Radyolojisi']);
 }finally{global.fetch=original}
});

test('Dental Flow specialty filters encode Turkish labels and accept server taxonomy',async()=>{
 const original=global.fetch,calls=[];
 try{
  global.fetch=async(url)=>{calls.push(url);return new Response(JSON.stringify({items:[],next_cursor:null,specialties:['Endodonti','Ağız, Diş ve Çene Cerrahisi']}),{status:200})};
  const selected='Ağız, Diş ve Çene Cerrahisi';
  const page=await api.getFeed('token','discover',undefined,selected);
  assert.ok(calls[0].includes('specialty='+encodeURIComponent(selected)));
  assert.deepEqual(page.specialties,['Endodonti',selected]);
 }finally{global.fetch=original}
});

test('Dental Flow supports old feed responses and rejects malformed or stale taxonomy',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>new Response(JSON.stringify({items:[],next_cursor:null}),{status:200});
  const fallback=await api.getFeed('token','following');
  assert.equal(fallback.specialties.length,8);
  global.fetch=async()=>new Response(JSON.stringify({items:[],next_cursor:null,specialties:['Endodonti','Endodonti']}),{status:200});
  await assert.rejects(()=>api.getFeed('token','discover'),error=>error.status===502);
  global.fetch=async()=>new Response(JSON.stringify({items:[],next_cursor:null,specialties:['Endodonti']}),{status:200});
  await assert.rejects(()=>api.getFeed('token','discover',undefined,'Ortodonti'),error=>error.status===422);
 }finally{global.fetch=original}
});

test('Dental Flow cursor pages preserve a server-only selected specialty without resetting filters',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>new Response(JSON.stringify({items:[],next_cursor:null}),{status:200});
  const page=await api.getFeed('token','discover',55,'Restoratif Diş Tedavisi - Özel');
  assert.equal(page.items.length,0);
 }finally{global.fetch=original}
});

test('Dental Flow share URLs use only validated positive record identifiers',()=>{
 assert.equal(api.socialPostUrl(7,42),'https://dentalai.tr/expert-support/expert/7?post=42');
 for(const [author,post] of [[0,1],[1,0],[-1,2],[1,1.5],[NaN,2],[1,Infinity]]){
  assert.throws(()=>api.socialPostUrl(author,post),/Geçersiz gönderi bağlantısı/);
 }
});

test('Dental Flow translates network failures into actionable API errors',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>{throw new TypeError('Failed to fetch')};
  await assert.rejects(()=>api.getFeed('token','discover'),error=>error.status===503&&/bağlanılamadı/.test(error.message));
 }finally{global.fetch=original}
});

test('restored Dental Flow cover must reference one of the saved uploads and an active link',async()=>{
 const base={id:'cover-draft',text:'',link:'https://example.org/article',media_ids:[11,12],attempted:false,preview_id:77,preview:{available:true,id:77,url:'https://example.org/article',cover:null},cover_media_id:12};
 const valid=await readDraft({getItemAsync:async()=>JSON.stringify(base)},'draft');
 assert.equal(valid.cover_media_id,12);
 for(const cover_media_id of [0,13,'12',null]){
  const restored=await readDraft({getItemAsync:async()=>JSON.stringify({...base,cover_media_id})},'draft');
  assert.equal(restored.cover_media_id,undefined);
 }
 const noLink=await readDraft({getItemAsync:async()=>JSON.stringify({...base,link:'',cover_media_id:12,preview_id:undefined,preview:null})},'draft');
 assert.equal(noLink.cover_media_id,undefined);
});


test('Dental Flow custom cover is sent only when it belongs to the post media',async()=>{
 const original=global.fetch,calls=[];
 global.fetch=async(url,init)=>{calls.push({url,...init});return new Response(JSON.stringify({id:90}),{status:201});};
 try{
  await api.createPost('secret',{text:'',link_url:'https://example.org/article',preview_id:77,media_ids:[11,12],idempotency_key:'11111111-1111-4111-8111-111111111111',cover_media_id:12});
  assert.equal(JSON.parse(calls[0].body).cover_media_id,12);
  await assert.rejects(()=>api.createPost('secret',{text:'',link_url:'https://example.org/article',media_ids:[11],idempotency_key:'22222222-2222-4222-8222-222222222222',cover_media_id:12}),/Bağlantı kapağı/);
  assert.equal(calls.length,1,'invalid cover must be rejected before network access');
 }finally{global.fetch=original;}
});

test('Dental Flow feed rejects malformed identity, counters and non-first-party media before rendering',()=>{
 const valid={id:42,author_id:7,author_name:'Uzman',text:'Paylaşım',status:'PUBLISHED',version:1,owned:false,pinned:false,comments_closed:false,liked:false,like_count:3,comment_count:2,media:[{id:9,url:'/api/expert-social/media/9'}],created_at:'2026-11-19T10:00:00Z',author_followed:true};
 assert.equal(api.normalizeSocialFeedPost(valid).id,42);
 for(const bad of [
  {...valid,id:0},
  {...valid,author_id:'7'},
  {...valid,like_count:-1},
  {...valid,comment_count:1.5},
  {...valid,media:[{id:9,url:'https://evil.example/private.jpg'}]},
  {...valid,status:'PENDING',owned:false},
  {...valid,created_at:'not-a-date'},
  {...valid,media:Array.from({length:5},(_,i)=>({id:i+1,url:'/api/expert-social/media/'+(i+1)}))}
 ]) assert.throws(()=>api.normalizeSocialFeedPost(bad),error=>error.status===502);
});
test('Dental Flow feed rejects malformed page cursors and duplicate post IDs',async()=>{
 const original=global.fetch;
 try{
  const row={id:42,author_id:7,author_name:'Uzman',text:'Paylaşım',status:'PUBLISHED',version:1,owned:false,pinned:false,comments_closed:false,liked:false,like_count:0,comment_count:0,media:[],created_at:'2026-11-19T10:00:00Z'};
  global.fetch=async()=>new Response(JSON.stringify({items:[row,row],next_cursor:null}),{status:200});
  await assert.rejects(()=>api.getFeed('token','discover'),error=>error.status===502);
  global.fetch=async()=>new Response(JSON.stringify({items:[row],next_cursor:-1}),{status:200});
  await assert.rejects(()=>api.getFeed('token','discover'),error=>error.status===502);
  global.fetch=async()=>new Response(JSON.stringify({items:[row],next_cursor:null}),{status:200});
  const page=await api.getFeed('token','discover');
  assert.equal(page.items.length,1);assert.equal(page.items[0].id,42);
 }finally{global.fetch=original}
});
