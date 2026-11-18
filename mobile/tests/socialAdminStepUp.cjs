const ts=require('typescript'),assert=require('node:assert/strict'),{test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(require('node:fs').readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
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
 }finally{global.fetch=original;}
});
