const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');

const modernApiSource=fs.readFileSync(require.resolve('../src/modernApi.ts'),'utf8');

function loadModernApi(payload){
 const compiled=ts.transpileModule(modernApiSource,{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
 }).outputText;
 const moduleExports={};
 const calls=[];
 class ApiError extends Error{constructor(status,message){super(message);this.status=status;}}
 vm.runInNewContext(compiled,{
  exports:moduleExports,
  require:name=>{
   if(name==='./chatFiles')return {validateChatFile:()=>true};
   if(name==='./api')return {ApiError,API_BASE:'https://dentalai.tr/api/mobile/v1'};
   if(name==='./apiCompatibility')return {MISSING_API_ROUTE_MESSAGE:'Sunucuda istenen API rotası bulunamadı (404). Uygulama güncel olsa bile sunucu API sürümü geride olabilir; güvenli taslakları koruyun ve sunucu güncellenene kadar aynı işlemi yeni bir anahtarla göndermeyin.'};
   if(name==='./sessionExpiry')return {revalidateSession:async()=>{}};
   if(name==='./notificationState')return {normalizeNotificationReadAt:value=>value};
   throw new Error('Unexpected import '+name);
  },
  fetch:async(url,init)=>{calls.push({url,init});return {ok:true,status:200,text:async()=>JSON.stringify(payload)};},
  AbortController,FormData,setTimeout,clearTimeout,Date,Math,Number,String,Array,Object,JSON,Error,Promise,RegExp,encodeURIComponent
 });
 return {api:moduleExports,calls};
}

const item=(id,patientId,tooth='36',isVoiceReview)=>({
 id,patient_id:patientId,patient_name:'Synthetic',tooth_number:tooth,
 status:'FINAL',clinical_notes:'Synthetic clinical note',created_at:'2026-11-20T08:00:00',
 ...(isVoiceReview===undefined?{}:{is_voice_review:isVoiceReview})
});

test('analysis history sends patient and FDI filters with the cursor',async()=>{
 const {api,calls}=loadModernApi({items:[item(100,810,'36',true)],total:2,next_before:100});
 const result=await api.getAnalysisHistory('synthetic-token',101,810,'36');
 assert.equal(calls.length,1);
 assert.equal(calls[0].url,'https://dentalai.tr/api/mobile/v1/analyses?limit=50&before=101&patient_id=810&tooth_number=36');
 assert.equal(calls[0].init.headers.Authorization,'Bearer synthetic-token');
 assert.deepEqual(Array.from(result.items,x=>x.id),[100]);
 assert.equal(result.next_before,100);
 assert.equal(result.items[0].is_voice_review,true);
});

test('analysis history rejects a response containing another patient',async()=>{
 const {api}=loadModernApi({items:[item(200,820)],total:1,next_before:null});
 await assert.rejects(()=>api.getAnalysisHistory('synthetic-token',undefined,810),/geçersiz liste/i);
});

test('analysis history rejects malformed voice-review state but accepts legacy omission',async()=>{
 const {api}=loadModernApi({items:[item(100,810,'36','DONE')],total:1,next_before:null});
 await assert.rejects(()=>api.getAnalysisHistory('synthetic-token',undefined,810),/geçersiz liste/i);
 const legacy=loadModernApi({items:[item(100,810)],total:1,next_before:null});
 const result=await legacy.api.getAnalysisHistory('synthetic-token',undefined,810);
 assert.equal(result.items[0].is_voice_review,undefined);
});

test('analysis history rejects an invalid FDI filter before network access',async()=>{
 const {api,calls}=loadModernApi({items:[],total:0,next_before:null});
 await assert.rejects(()=>api.getAnalysisHistory('synthetic-token',undefined,810,'99'),/FDI/i);
 assert.equal(calls.length,0);
});
