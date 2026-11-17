const ts=require('typescript');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(
 fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}
).outputText,filename);
const api=require('../src/modernApi.ts');
const json=value=>new Response(JSON.stringify(value),{status:200,headers:{'content-type':'application/json'}});
const withFetch=async(handler,fn)=>{
 const original=global.fetch;
 global.fetch=handler;
 try{return await fn()}finally{global.fetch=original}
};
const consultation=(id,requested_at)=>({
 id,requested_at,status:'ACTIVE',specialty:'Endodonti',question:'Klinik soru',
 other_user_id:19,other_display_name:'Uzman',last_message:null,unread_count:2
});
test('consultation list accepts date-ordered cursor even when IDs are not monotonically decreasing',async()=>{
 await withFetch(async()=>json({items:[consultation(4,'2026-11-11T12:00:00'),consultation(22,'2026-11-10T12:00:00')],next_before:22}),async()=>{
  const page=await api.getConsultations('token',10);
  assert.equal(page.next_before,22);
  assert.equal(page.items[1].other_display_name,'Uzman');
  assert.equal(page.items[1].unread_count,2);
 });
});
test('consultation list normalizes legacy peer name and missing unread count',async()=>{
 await withFetch(async()=>json({items:[{...consultation(5,'2026-11-10'),other_display_name:null,other_name:'Eski API',unread_count:null}],next_before:null}),async()=>{
  const page=await api.getConsultations('token');
  assert.equal(page.items[0].other_display_name,'Eski API');
  assert.equal(page.items[0].unread_count,0);
 });
});
test('consultation list rejects cursor that repeats request anchor',async()=>{
 await withFetch(async()=>json({items:[consultation(5,'2026-11-10')],next_before:10}),async()=>{
  await assert.rejects(()=>api.getConsultations('token',10),/geçersiz liste/);
 });
});
test('read receipt sends validated through_id using bearer authentication',async()=>{
 await withFetch(async(url,init)=>{
  assert.match(url,/\/consultations\/42\/read$/);
  assert.equal(init.method,'POST');
  assert.equal(init.headers.Authorization,'Bearer secret');
  assert.deepEqual(JSON.parse(init.body),{through_id:93});
  return json({ok:true,through_id:93,at:'2026-11-11T12:00:00'});
 },async()=>{
  const receipt=await api.markConsultationRead('secret',42,93);
  assert.equal(receipt.through_id,93);
 });
});
test('read receipt rejects invalid IDs before network request',async()=>{
 await withFetch(async()=>{throw Error('network must not be called')},async()=>{
  assert.throws(()=>api.markConsultationRead('token',-1,1),/Geçersiz/);
  assert.throws(()=>api.markConsultationRead('token',1,0),/Geçersiz/);
 });
});
test('deleted consultation returns empty message page and no cursor',async()=>{
 await withFetch(async()=>json({case:{id:4,messages_deleted_at:'2026-11-11T12:00:00'},messages:[],next_before:null}),async()=>{
  const result=await api.getConsultation('token',4);
  assert.deepEqual(result.messages,[]);
  assert.equal(result.next_before,null);
 });
});

test('academic courses accept a later numeric ID when created_at cursor moves backward',async()=>{
 await withFetch(async()=>json({items:[
  {id:8,title:'Endodonti',material_count:3,updated_at:'2026-11-11'},
  {id:45,title:'Ortodonti',material_count:2,updated_at:'2026-11-10'}
 ],next_before:45}),async()=>{
  const page=await api.getCourses('token',7);
  assert.equal(page.next_before,45);
  assert.equal(page.items.length,2);
 });
});
test('academic course cursor must belong to the returned page',async()=>{
 await withFetch(async()=>json({items:[{id:8,title:'Endodonti'}],next_before:20}),async()=>{
  await assert.rejects(()=>api.getCourses('token'),/geçersiz sayfa/);
 });
});
test('academic chat messages reject out-of-order IDs and nonadvancing cursors',async()=>{
 await withFetch(async()=>json({items:[
  {id:19,role:'assistant',content:'Yanıt',created_at:'2026-11-10'},
  {id:18,role:'user',content:'Soru',created_at:'2026-11-09'}
 ],next_before:18}),async()=>{
  await assert.rejects(()=>api.getAcademicMessages('token',1,20),/geçersiz kayıt/);
 });
});

test('academic course pagination rejects a replayed anchor even when date ordering differs',async()=>{
 await withFetch(async()=>json({items:[{id:7,title:'Tekrar',material_count:0}],next_before:7}),async()=>{
  await assert.rejects(()=>api.getCourses('token',7),/geçersiz sayfa/);
 });
});
test('academic pages reject duplicate records',async()=>{
 await withFetch(async()=>json({items:[
  {id:9,title:'Ders',material_count:1},
  {id:9,title:'Ders',material_count:1}
 ],next_before:9}),async()=>{
  await assert.rejects(()=>api.getCourses('token'),/geçersiz sayfa/);
 });
});

test('consultation list rejects duplicate rows and foreign cursors',async()=>{
 await withFetch(async()=>json({items:[consultation(8,'2026-11-11'),consultation(8,'2026-11-10')],next_before:8}),async()=>{
  await assert.rejects(()=>api.getConsultations('token'),/geçersiz liste/);
 });
 await withFetch(async()=>json({items:[consultation(8,'2026-11-11')],next_before:21}),async()=>{
  await assert.rejects(()=>api.getConsultations('token'),/geçersiz liste/);
 });
});
test('consultation list rejects replay of requested anchor',async()=>{
 await withFetch(async()=>json({items:[consultation(15,'2026-11-11')],next_before:null}),async()=>{
  await assert.rejects(()=>api.getConsultations('token',15),/geçersiz liste/);
 });
});

test('clinical media rejects foreign cursor and duplicate images',async()=>{
 await withFetch(async()=>json({items:[{id:12,filename:'a.png'}],next_before:99}),async()=>{
  await assert.rejects(()=>api.getMedia('token',3),/geçersiz liste/);
 });
 await withFetch(async()=>json({items:[{id:12,filename:'a.png'},{id:12,filename:'b.png'}],next_before:null}),async()=>{
  await assert.rejects(()=>api.getMedia('token',3),/geçersiz liste/);
 });
});
test('clinical media preserves patient-scoped authenticated file URL',async()=>{
 await withFetch(async()=>json({items:[{id:11,filename:'film.png'}],next_before:null}),async()=>{
  const result=await api.getMedia('token',3);
  assert.match(result.items[0].url,/\/patients\/3\/media\/11\/file$/);
 });
});

test('consultation message receipt lookup is account-authenticated and validates the response',async()=>{
 await withFetch(async(url,init)=>{
  assert.ok(url.includes('/consultations/42/message-receipt?client_message_id=native-message-receipt-0001'));
  assert.equal(init.headers.Authorization,'Bearer secret');
  assert.equal(init.method,'GET');
  return json({message:{id:91,sender_user_id:10,message_type:'TEXT',content:'Klinik not',created_at:'2026-11-17T00:00:00'},deleted:false});
 },async()=>{
  const receipt=await api.getConsultationMessageReceipt('secret',42,'native-message-receipt-0001');
  assert.equal(receipt.message.id,91);
  assert.equal(receipt.deleted,false);
 });
});

test('consultation message receipt reports retention deletion without exposing message content',async()=>{
 await withFetch(async()=>json({message:null,deleted:true}),async()=>{
  const receipt=await api.getConsultationMessageReceipt('secret',42,'native-message-receipt-0001');
  assert.equal(receipt.message,null);
  assert.equal(receipt.deleted,true);
 });
});

test('consultation message receipt rejects invalid intent keys before network access',async()=>{
 await withFetch(async()=>{throw Error('network must not be called')},async()=>{
  await assert.rejects(()=>api.getConsultationMessageReceipt('secret',42,'short'),/Geçersiz/);
 });
});

test('consultation text sends carry the stable client intent key and reply target',async()=>{
 await withFetch(async(url,init)=>{
  assert.ok(url.includes('/consultations/42/messages'));
  assert.equal(init.method,'POST');
  assert.deepEqual(JSON.parse(init.body),{content:'Yanıt',client_message_id:'native-message-send-0001',reply_to_message_id:17});
  return json({ok:true,message:{id:92,sender_user_id:10,message_type:'TEXT',content:'Yanıt',created_at:'2026-11-17T00:00:00'}});
 },async()=>{
  const result=await api.sendConsultationMessage('secret',42,'Yanıt','native-message-send-0001',17);
  assert.equal(result.message.id,92);
 });
});

test('consultation media upload carries the persisted client intent key',async()=>{
 const OriginalFormData=global.FormData;
 class TestFormData{constructor(){this.entries=[]}append(name,value){this.entries.push([name,value])}}
 global.FormData=TestFormData;
 try{
  await withFetch(async(url,init)=>{
   assert.ok(url.includes('/consultations/42/attachments'));
   assert.equal(init.method,'POST');
   const entries=init.body.entries;
   assert.ok(entries.some(([name,value])=>name==='client_message_id'&&value==='native-media-send-0001'));
   assert.ok(entries.some(([name,value])=>name==='file'&&value.name==='case.pdf'));
   return json({ok:true,message:{id:93,sender_user_id:10,message_type:'FILE',created_at:'2026-11-17T00:00:00'}});
  },async()=>{
   const result=await api.sendChatFile('secret',42,{uri:'file:///case.pdf',name:'case.pdf',type:'application/pdf',size:120},undefined,'native-media-send-0001');
   assert.equal(result.message.id,93);
  });
 }finally{global.FormData=OriginalFormData}
});

test('native consultation drafts persist one encrypted text copy and a stable intent key',()=>{
 const source=fs.readFileSync(require.resolve('../src/ModernScreens.tsx'),'utf8');
 assert.ok(source.includes('SecureStore.setItemAsync(draftKey,v)'));
 assert.ok(source.includes('SecureStore.setItemAsync(pendingKey,JSON.stringify({version:1,id:intent.id,scope:intent.scope,replyTo:intent.replyTo}))'));
 assert.ok(source.includes('getConsultationMessageReceipt'));
 assert.ok(source.includes('editable={!sendBusy&&!pendingMessage&&canCompose&&draftReady}'));
 const draftDelete=source.indexOf('await SecureStore.deleteItemAsync(draftKey)');
 const pendingDelete=source.indexOf('await SecureStore.deleteItemAsync(pendingKey)');
 assert.ok(draftDelete>=0&&pendingDelete>draftDelete);
 assert.equal(source.includes('content:intent.content'),false);
});

test('native consultation media intent stores no filename and reconciles before retry',()=>{
 const source=fs.readFileSync(require.resolve('../src/ChatAttachmentComposer.tsx'),'utf8');
 assert.ok(source.includes('SecureStore.setItemAsync(pendingKey,JSON.stringify({version:1,...intent}))'));
 assert.ok(source.includes('getConsultationMessageReceipt'));
 assert.equal(source.includes('name:file.name'),false);
 assert.ok(source.includes('Crypto.randomUUID()'));
});

test('web consultation media retries keep the same session-scoped key',()=>{
 const source=fs.readFileSync(require('node:path').join(__dirname,'../../app/templates/expert_case_room.html'),'utf8');
 assert.ok(source.includes('sessionStorage.setItem(mediaIntentStorageKey'));
 assert.ok(source.includes('pendingMediaIntent.key'));
 assert.ok(source.includes('clearAttachment(force=false)'));
});

test('native consultation media blocks camera, document picker and send until receipt recovery finishes',()=>{
 const source=fs.readFileSync(require.resolve('../src/ChatAttachmentComposer.tsx'),'utf8');
 assert.ok(source.includes('[restoring,setRestoring]=useState(true)'));
 assert.ok(source.includes('if(lock.current||restoring||recoveryBlocked||disabled||uncertain)return;'));
 assert.ok(source.includes('if(!file||lock.current||restoring||recoveryBlocked||disabled||uncertain)return;'));
 assert.ok(source.includes('disabled={restoring||recoveryBlocked||busy||disabled||uncertain}'));
 assert.ok(source.includes('Bekleyen ek kaydı kontrol ediliyor; kontrol bitmeden yeni gönderim açılamaz.'));
});

test('corrupt consultation media intent fails closed and offers local recovery without deleting the intent',()=>{
 const source=fs.readFileSync(require.resolve('../src/ChatAttachmentComposer.tsx'),'utf8');
 const invalidStart=source.indexOf('if(!valid){');
 const validNext=source.indexOf('setPendingId(value.id)',invalidStart);
 assert.ok(invalidStart>=0&&validNext>invalidStart);
 const invalidBranch=source.slice(invalidStart,validNext);
 assert.ok(invalidBranch.includes('setRecoveryBlocked(true)'));
 assert.equal(invalidBranch.includes('deleteItemAsync(pendingKey)'),false);
 assert.ok(source.includes('setRestoreAttempt(value=>value+1)'));
});
