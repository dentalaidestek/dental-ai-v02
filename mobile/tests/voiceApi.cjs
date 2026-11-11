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
 try{await assert.rejects(()=>api.finalizeVoice('secret',1,{context:{},insights:[],uncertain:'',conversation_text:'text'}),/son değerlendirme yanıtı eksik/)}finally{global.fetch=original}
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

test('voice API gives actionable validation feedback',async()=>{
 const original=global.fetch;
 global.fetch=async()=>response(JSON.stringify({detail:[{msg:'Invalid input'}]}),422);
 try{await assert.rejects(()=>api.extractVoice('token',1,'text'),/sunucu tarafından doğrulanamadı/)}finally{global.fetch=original}
});

test('voice API reports aborted clinical requests without discarding transcript',async()=>{
 const original=global.fetch;
 global.fetch=async()=>{const error=new Error('This operation was aborted');error.name='AbortError';throw error};
 try{await assert.rejects(()=>api.extractVoice('token',1,'metin'),/zaman aşımına uğradı.*Metniniz bu ekranda korunuyor/)}finally{global.fetch=original}
});

test('voice extraction retains clinical uncertainty as text for final review',async()=>{
 const original=global.fetch;
 global.fetch=async()=>response(JSON.stringify({ok:true,revision:'r1',review:{fields:{},uncertain:'İlaç dozu doğrulanamadı'}}));
 try{const result=await api.extractVoice('token',9,'muayene');assert.equal(result.review.uncertain,'İlaç dozu doğrulanamadı')}finally{global.fetch=original}
});

test('voice API expires only the matching session on unauthorized clinical requests',async()=>{
 const {subscribeSessionExpiry}=require('../src/sessionExpiry.ts');
 const original=global.fetch,events=[];
 const stopCurrent=subscribeSessionExpiry('current',()=>events.push('current'));
 const stopOther=subscribeSessionExpiry('other',()=>events.push('other'));
 try{
  global.fetch=async()=>response(JSON.stringify({detail:'Oturum süresi doldu'}),401);
  await assert.rejects(()=>api.extractVoice('current',12,'muayene'),/Oturum süresi doldu/);
  assert.deepEqual(events,['current']);
 }finally{stopCurrent();stopOther();global.fetch=original}
});

test('voice API expires matching session even when unauthorized response is HTML',async()=>{
 const {subscribeSessionExpiry}=require('../src/sessionExpiry.ts');
 const original=global.fetch,events=[];
 const stop=subscribeSessionExpiry('current',()=>events.push('expired'));
 try{
  global.fetch=async()=>response('<html>Unauthorized</html>',401);
  await assert.rejects(()=>api.extractVoice('current',12,'muayene'),/geçersiz klinik/);
  assert.deepEqual(events,['expired']);
 }finally{stop();global.fetch=original}
});

test('voice API explains overload and server outages without losing transcript',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>response(JSON.stringify({detail:'rate limited'}),429);
  await assert.rejects(()=>api.extractVoice('token',1,'metin'),/hizmeti şu anda yoğun.*Metniniz korunuyor/);
  global.fetch=async()=>response(JSON.stringify({detail:'internal error'}),503);
  await assert.rejects(()=>api.extractVoice('token',1,'metin'),/sunucusuna şu anda ulaşılamıyor.*Metniniz korunuyor/);
 }finally{global.fetch=original}
});

test('voice API handles HTML gateway failures and rate limits before parsing',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>response('<html>Too Many Requests</html>',429);
  await assert.rejects(()=>api.extractVoice('token',1,'metin'),/hizmeti şu anda yoğun/);
  global.fetch=async()=>response('<html>Bad Gateway</html>',502);
  await assert.rejects(()=>api.extractVoice('token',1,'metin'),/sunucusuna şu anda ulaşılamıyor/);
 }finally{global.fetch=original}
});

test('native voice audio uses raw bounded bytes, consent and patient scoped route',async()=>{
 const original=global.fetch;let call;
 global.fetch=async(url,init)=>{call={url,init};return response(JSON.stringify({ok:true,revision:'rev1',transcript:'Dişim ağrıyor.'}))};
 try{
  const blob=new Blob([new Uint8Array(128)],{type:'audio/mp4'});
  const result=await api.transcribeVoiceAudio('secret',23,blob,'audio/mp4');
  assert.equal(result.transcript,'Dişim ağrıyor.');
  assert.match(call.url,/\/patients\/23\/voice-exam\/audio$/);
  assert.equal(call.init.headers.Authorization,'Bearer secret');
  assert.equal(call.init.headers['X-Voice-Consent'],'yes');
  assert.equal(call.init.headers['Content-Type'],'audio/mp4');
  assert.equal(call.init.body,blob);
 }finally{global.fetch=original}
});
test('native voice audio rejects unsupported formats and oversized files without network requests',async()=>{
 const original=global.fetch;let calls=0;global.fetch=async()=>{calls++;throw Error('should not fetch')};
 try{
  const valid=new Blob([new Uint8Array(128)]);
  await assert.rejects(()=>api.transcribeVoiceAudio('token',1,valid,'application/octet-stream'),/desteklenmiyor/);
  await assert.rejects(()=>api.transcribeVoiceAudio('token',1,new Blob([new Uint8Array(8)]),'audio/mp4'),/8 MB/);
  await assert.rejects(()=>api.transcribeVoiceAudio('token',1,{size:8*1024*1024+1},'audio/mp4'),/8 MB/);
  assert.equal(calls,0);
 }finally{global.fetch=original}
});
test('native voice audio rejects missing transcription and retains actionable error',async()=>{
 const original=global.fetch;
 global.fetch=async()=>response(JSON.stringify({ok:true,revision:'r1'}));
 try{await assert.rejects(()=>api.transcribeVoiceAudio('token',1,new Blob([new Uint8Array(128)]),'audio/mp4'),/yanıtı eksik/)}finally{global.fetch=original}
});
