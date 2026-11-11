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
 ],next_before:19}),async()=>{
  await assert.rejects(()=>api.getAcademicMessages('token',1,20),/geçersiz sayfa/);
 });
});
