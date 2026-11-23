const ts=require("typescript"),fs=require("node:fs"),assert=require("node:assert/strict"),{test}=require("node:test");
require.extensions[".ts"]=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const api=require("../src/modernApi.ts");
test('case media URLs accept selected link ids and never patient paths',()=>{
 const source=api.sharedCaseImageSource('synthetic',12,5);
 assert.equal(source.uri,'https://dentalai.tr/api/mobile/v1/consultations/12/shared-media/5');
 assert.equal(source.headers.Authorization,'Bearer synthetic');
 for(const id of [0,-1,'5',NaN])assert.throws(()=>api.sharedCaseImageSource('synthetic',12,id));
});
test("chat images use only the authenticated case/message endpoint",()=>{
 const source=api.chatImageSource("synthetic",12,44);
 assert.equal(source.uri,"https://dentalai.tr/api/mobile/v1/consultations/12/attachments/44");
 assert.equal(source.headers.Authorization,"Bearer synthetic");
 assert.throws(()=>api.chatImageSource("synthetic",0,44));
 assert.throws(()=>api.chatImageSource("synthetic",12,-1));
});
test("native photo rejects wrong MIME, size and reply IDs before sending",async()=>{
 const original=global.fetch;let called=0;global.fetch=()=>{called++;throw Error("Unexpected request")};
 try{for(const file of [
  {uri:"file:///x",name:"x.pdf",type:"application/pdf"},
  {uri:"file:///x",name:"x.png",type:"image/png",size:16*1024*1024},
  {uri:"file:///x",name:"x.png",type:"image/png",size:0}
 ])await assert.rejects(()=>api.sendChatImage("synthetic",12,file));
 await assert.rejects(()=>api.sendChatImage("synthetic",12,{uri:"file:///x",name:"x.png",type:"image/png"},-1));
 assert.equal(called,0);
 }finally{global.fetch=original}
});
test("chat actions preserve the real server lifecycle payload and reject unconfirmed success",async()=>{
 const original=global.fetch;const calls=[];
 try{
 global.fetch=async(url,init)=>{calls.push({url,body:JSON.parse(init.body)});return new Response(JSON.stringify({ok:true}),{status:200})};
 await api.performChatAction("synthetic",12,{action:"complete",completion_action:"CONTINUE"});
 assert.equal(calls[0].url,"https://dentalai.tr/api/mobile/v1/consultations/12/actions");
 assert.deepEqual(calls[0].body,{action:"complete",completion_action:"CONTINUE"});
 global.fetch=async()=>new Response(JSON.stringify({ok:false}),{status:200});
 await assert.rejects(()=>api.performChatAction("synthetic",12,{action:"delete"}),/doğrulanamadı/);
 }finally{global.fetch=original}
});
test("deleted-chat list refuses malformed identities",async()=>{
 const original=global.fetch;
 try{for(const items of [[null],[{id:0}],[{id:"7"}]]){
  global.fetch=async()=>new Response(JSON.stringify({items}),{status:200});
  await assert.rejects(()=>api.getDeletedChats("synthetic"));
 }}finally{global.fetch=original}
});
