const ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(require('node:fs').readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const expiry=require('../src/sessionExpiry.ts');
let revalidationCalls=0;
const originalRevalidate=expiry.revalidateSession;
expiry.revalidateSession=async()=>{revalidationCalls++;return 'valid'};
const api=require('../src/socialApi.ts');

test('native social admin step-up requests use fixed-mailbox OTP and validate scoped grants',async()=>{
 const original=global.fetch,calls=[];
 try{
  global.fetch=async(url,init)=>{calls.push({url,...init});return new Response(JSON.stringify({ok:true,expires_in:600,delivery:'fixed_mailbox'}),{status:200});};
  const started=await api.beginSocialAdminStepUp('native-session');
  assert.deepEqual(started,{expires_in:600});
  assert.equal(calls[0].url,'https://dentalai.tr/api/expert-social/admin/step-up');
  assert.equal(calls[0].credentials,'omit');
  assert.equal(calls[0].headers.Authorization,'Bearer native-session');
  assert.equal(calls[0].headers['X-Dental-Social'],'1');
  assert.equal(calls[0].headers['X-Dental-Social-Admin-Step-Up'],undefined);
  await assert.rejects(()=>api.verifySocialAdminStepUp('native-session','12x456'),/Altı haneli/);
  assert.equal(calls.length,1,'malformed codes must be rejected before network access');
  global.fetch=async(url,init)=>{calls.push({url,...init});return new Response(JSON.stringify({ok:true,token:'s'.repeat(43),expires_in:300,scope:'SOCIAL_MODERATION'}),{status:200});};
  const grant=await api.verifySocialAdminStepUp('native-session','123456');
  assert.equal(grant.scope,'SOCIAL_MODERATION');
  assert.equal(grant.expires_in,300);
  assert.equal(calls[1].url,'https://dentalai.tr/api/expert-social/admin/step-up/verify');
  assert.equal(JSON.parse(calls[1].body).code,'123456');
  assert.equal(calls[1].headers['X-Dental-Social-Admin-Step-Up'],undefined);
  global.fetch=async(url,init)=>{calls.push({url,...init});return new Response(JSON.stringify({ok:true}),{status:200});};
  await api.revokeSocialAdminStepUp('native-session',grant.token);
  assert.equal(calls[2].url,'https://dentalai.tr/api/expert-social/admin/step-up/revoke');
  assert.equal(calls[2].headers['X-Dental-Social-Admin-Step-Up'],grant.token);
  assert.equal(calls[2].credentials,'omit');
  global.fetch=async()=>new Response(JSON.stringify({ok:true,token:'short',expires_in:300,scope:'SOCIAL_MODERATION'}),{status:200});
  await assert.rejects(()=>api.verifySocialAdminStepUp('native-session','123456'),/yetki kapsamı/);
  global.fetch=async()=>new Response(JSON.stringify({ok:true,token:'s'.repeat(42)+'!',expires_in:300,scope:'SOCIAL_MODERATION'}),{status:200});
  await assert.rejects(()=>api.verifySocialAdminStepUp('native-session','123456'),/yetki kapsamı/);
  await assert.rejects(()=>api.revokeSocialAdminStepUp('native-session','s'.repeat(42)+'!'),/Geçersiz yönetici/);
 }finally{global.fetch=original;}
});

test('an invalid OTP does not trigger a bearer-session revalidation probe',async()=>{
 const original=global.fetch,before=revalidationCalls;
 try{
  global.fetch=async()=>new Response(JSON.stringify({detail:'Kod yanlış veya geçersiz.',code:'SOCIAL_ADMIN_OTP_INVALID'}),{status:401});
  await assert.rejects(()=>api.verifySocialAdminStepUp('native-session','123456'));
  assert.equal(revalidationCalls,before,'an OTP typo is not a session-expiry signal');
  global.fetch=async()=>new Response(JSON.stringify({detail:'Üye girişi gerekiyor.'}),{status:401});
  await assert.rejects(()=>api.socialRequest('native-session','/feed/discover'));
  assert.equal(revalidationCalls,before+1,'ordinary 401 responses still revalidate the bearer session');
 }finally{global.fetch=original;}
});

test('native admin queue adapters send the scoped grant and bound every response',async()=>{
 const original=global.fetch,calls=[],stepUp='s'.repeat(43);
 try{
  global.fetch=async(url,init)=>{
   calls.push({url,init});
   const path=String(url);
   let body;
   if(path.includes('/moderation?'))body={items:[{id:7,version:2,status:'PENDING',text:'Synthetic',media:[]}],next_cursor:null,aging:{waiting_human:1,waiting_owner:0,failed:0,over_1h:0,over_24h:0}};
   else if(path.endsWith('/reports'))body={items:[{id:3,target_type:'POST',target_id:7,reason:'PRIVACY'}],next_cursor:null};
   else if(path.endsWith('/moderation/POST/7')&&init.method==='POST')body={ok:true,status:'PUBLISHED',version:3};
   else body={item:{id:7,version:2,status:'PENDING'},history:[],moderation_history:[]};
   return new Response(JSON.stringify(body),{status:200});
  };
  const queue=await api.getSocialAdminQueue('native-session',stepUp,'POST','PENDING');
  assert.equal(queue.items[0].id,7);
  assert.equal(queue.aging.waiting_human,1);
  const reports=await api.getSocialAdminReports('native-session',stepUp);
  assert.equal(reports.items[0].target_id,7);
  const detail=await api.getSocialAdminDetail('native-session',stepUp,'POST',7);
  assert.equal(detail.item.id,7);
  const decision=await api.decideSocialAdminModeration('native-session',stepUp,'POST',7,'PUBLISHED',2,'İnceleme tamamlandı');
  assert.equal(decision.version,3);
  for(const call of calls)assert.equal(call.init.headers['X-Dental-Social-Admin-Step-Up'],stepUp);
  assert.ok(calls.some(call=>call.url.includes('/moderation?kind=POST&status=PENDING')));
  await assert.rejects(()=>api.getSocialAdminQueue('native-session','x'.repeat(43)+'!','POST','PENDING'),/Yönetici doğrulaması/);
  await assert.rejects(()=>api.decideSocialAdminModeration('native-session',stepUp,'POST',7,'PUBLISHED',2,'x'),/Karar bilgilerini/);
 }finally{global.fetch=original;}
});
