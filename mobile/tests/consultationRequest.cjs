const ts=require("typescript"),fs=require("node:fs"),assert=require("node:assert/strict"),{test}=require("node:test");
require.extensions[".ts"]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const api=require("../src/modernApi.ts");
const request={expert_user_id:2,patient_id:11,clinical_summary:"Synthetic",requester_opinion:"Synthetic opinion",question:"Synthetic question",tooth_region:"46",urgency:"ASAP",media_ids:"17",request_key:"11111111-1111-4111-8111-111111111111"};
test("native request forwards every web field and preserves the stable key",async()=>{
 const original=global.fetch;const sent=[];
 try{global.fetch=async(url,init)=>{sent.push({url,body:JSON.parse(init.body)});return new Response(JSON.stringify({ok:true,case_id:91}))};
 assert.equal((await api.createConsultation("synthetic",request)).case_id,91);
 assert.equal(sent[0].url,"https://dentalai.tr/api/mobile/v1/consultations");assert.deepEqual(sent[0].body,request);
 }finally{global.fetch=original}
});
test("invalid patient/media selection and empty clinical summary never send",async()=>{
 const original=global.fetch;let count=0;
 try{global.fetch=async()=>{count++;throw Error("unexpected")};
 for(const invalid of [{...request,clinical_summary:" "},{...request,patient_id:0},{...request,media_ids:"17,bad"},{...request,request_key:"bad"}])await assert.rejects(()=>api.createConsultation("synthetic",invalid));
 assert.equal(count,0);
 }finally{global.fetch=original}
});
test("unconfirmed creation stays an error while a private receipt can reopen its case",async()=>{
 const original=global.fetch;
 try{global.fetch=async()=>new Response(JSON.stringify({ok:true,case_id:null}));
 await assert.rejects(()=>api.createConsultation("synthetic",request),/doğrulanamadı/);
 global.fetch=async url=>{assert.ok(url.endsWith("/consultations/request-status/2/"+request.request_key));return new Response(JSON.stringify({found:true,case_id:91,status:"REQUESTED"}))};
 assert.equal((await api.getConsultationRequestStatus("synthetic",2,request.request_key)).case_id,91);
 }finally{global.fetch=original}
});
