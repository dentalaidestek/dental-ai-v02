const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
const api=require('../src/voiceApi.ts');
const response=(body,status=200)=>({ok:status>=200&&status<300,status,text:async()=>body});
test('voice extraction sends consent, bearer and patient path',async()=>{
 const original=global.fetch;let call;global.fetch=async(url,init)=>{call={url,init};return response(JSON.stringify({ok:true,revision:'r1',review:{fields:{}}}))};
 try{const result=await api.extractVoice('secret',12,'muayene konuşması');assert.equal(result.ok,true);assert.match(call.url,/\/patients\/12\/voice-exam\/text$/);assert.equal(call.init.headers.Authorization,'Bearer secret');assert.deepEqual(JSON.parse(call.init.body),{transcript:'muayene konuşması',consent:true})}finally{global.fetch=original}
});
test('voice API surfaces HTTP errors without masking details',async()=>{
 const original=global.fetch;global.fetch=async()=>response(JSON.stringify({detail:'Hasta erişim yetkisi yok'}),403);
 try{await assert.rejects(()=>api.extractVoice('secret',1,'text'),/Hasta erişim yetkisi yok/)}finally{global.fetch=original}
});
test('voice API rejects malformed and ambiguous success payloads',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>response('<html>bad gateway</html>',502);await assert.rejects(()=>api.extractVoice('secret',1,'text'),/geçersiz klinik/);
  global.fetch=async()=>response('{}');await assert.rejects(()=>api.extractVoice('secret',1,'text'),/başarı durumunu/);
 }finally{global.fetch=original}
});

test('voice API rejects successful but incomplete clinical extraction',async()=>{
 const original=global.fetch;global.fetch=async()=>response(JSON.stringify({ok:true}));
 try{await assert.rejects(()=>api.extractVoice('secret',1,'text'),/muayene bilgileri bulunamadı/)}finally{global.fetch=original}
});
test('voice finalization requires a clinical review payload',async()=>{
 const original=global.fetch;global.fetch=async()=>response(JSON.stringify({ok:true}));
 try{await assert.rejects(()=>api.finalizeVoice('secret',1,{context:{},insights:[],uncertain:[],conversation_text:'text'}),/son değerlendirme yanıtı eksik/)}finally{global.fetch=original}
});

test('voice finalization submits full transcript, clinician review and consent',async()=>{
 const original=global.fetch;let call;
 global.fetch=async(url,init)=>{call={url,init};return response(JSON.stringify({ok:true,final:{summary:'Değerlendirme tamamlandı'}}))};
 try{
  const payload={context:{fields:{chief_complaint:{value:'Ağrı'}},teeth:[44],literature_topics:['TOPIC_1']},insights:[{finding:'Ağrı'}],uncertain:'Belirsiz ilaç dozu',conversation_text:'Tam görüşme metni'};
  const result=await api.finalizeVoice('token',44,payload);
  assert.equal(result.final.summary,'Değerlendirme tamamlandı');
  assert.match(call.url,/\/patients\/44\/voice-exam\/finalize$/);
  assert.equal(call.init.headers.Authorization,'Bearer token');
  assert.deepEqual(JSON.parse(call.init.body),{...payload,consent:true});
 }finally{global.fetch=original}
});
