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
  global.fetch=async()=>response('<html>bad gateway</html>',502);await assert.rejects(()=>api.extractVoice('secret',1,'text'),/sunucusuna şu anda ulaşılamıyor/);
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
  const payload={context:{fields:{chief_complaint:{value:'Ağrı',quote:'Dişim ağrıyor'}},teeth:[{tooth:'44',status:'OTHER',quote:'44 numarada klinik bulgu görüşüldü'}],literature_topics:[{topic:'endo.general',quote:'Kanal tedavisi konuşuldu'}]},insights:[{quote:'Dişim ağrıyor',observation:'Ağrı bildirimi',suggestion:'Ağrının süresi sorulmalı'}],uncertain:'Belirsiz ilaç dozu',conversation_text:'Tam görüşme metni'};
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

test('clinical communication coaching from extraction is accepted in final payload',async()=>{
 const original=global.fetch;let finalRequest;
 const communication=[{quote:'Tedaviden çekiniyorum',observation:'Kaygı',suggestion:'Açıklama yap'}];
 global.fetch=async(url,init)=>{
  if(String(url).endsWith('/text'))return response(JSON.stringify({ok:true,revision:'r1',review:{fields:{},communication,decision_barriers:[],follow_up_questions:[]}}));
  finalRequest=JSON.parse(init.body);return response(JSON.stringify({ok:true,final:{summary:[]}}));
 };
 try{
  const extracted=await api.extractVoice('token',4,'Tedaviden çekiniyorum');
  assert.deepEqual(extracted.review.communication,communication);
  await api.finalizeVoice('token',4,{context:{fields:{}},insights:extracted.review.communication,uncertain:'',conversation_text:'Tedaviden çekiniyorum'});
  assert.deepEqual(finalRequest.insights,communication);
 }finally{global.fetch=original}
});

test('native voice audio refuses invalid patient IDs and non-finite sizes before network',async()=>{
 const original=global.fetch;let calls=0;global.fetch=async()=>{calls++;throw Error('unexpected upload')};
 try{
  const blob=new Blob([new Uint8Array(128)],{type:'audio/mp4'});
  for(const id of [0,-1,1.5,Number.NaN])await assert.rejects(()=>api.transcribeVoiceAudio('token',id,blob,'audio/mp4'),/geçerli bir hasta/);
  await assert.rejects(()=>api.transcribeVoiceAudio('token',1,{size:Number.NaN},'audio/mp4'),/8 MB/);
  assert.equal(calls,0);
 }finally{global.fetch=original}
});

test('clinical extraction rejects malformed fields and list shapes before UI use',async()=>{
 const original=global.fetch;
 try{
  for(const review of [
   {fields:{chief_complaint:null}},
   {fields:{chief_complaint:{value:123}}},
   {fields:{},teeth:'44'},
   {fields:{},communication:{}},
   {fields:{},uncertain:['şüpheli']},
   {fields:{},appointment:[]}
  ]){
   global.fetch=async()=>response(JSON.stringify({ok:true,revision:'r1',review}));
   await assert.rejects(()=>api.extractVoice('token',1,'muayene'),/alanları geçersiz/);
  }
 }finally{global.fetch=original}
});

test('native voice audio rejects null, list and primitive server responses safely',async()=>{
 const original=global.fetch;
 try{
  for(const body of ['null','[]','true','42','"unexpected"']){
   global.fetch=async()=>response(body);
   await assert.rejects(()=>api.transcribeVoiceAudio('token',1,new Blob([new Uint8Array(128)]),'audio/mp4'),/geçersiz yanıt/);
  }
 }finally{global.fetch=original}
});

test('clinical text API rejects invalid patient and oversized transcripts before upload',async()=>{
 const original=global.fetch;let calls=0;global.fetch=async()=>{calls++;throw Error('unexpected request')};
 try{
  await assert.rejects(()=>api.extractVoice('token',0,'muayene'),/geçerli bir hasta/);
  await assert.rejects(()=>api.extractVoice('token',3,'   '),/boş olamaz/);
  await assert.rejects(()=>api.extractVoice('token',3,'a'.repeat(18001)),/18.000 karakteri/);
  await assert.rejects(()=>api.finalizeVoice('token',-1,{context:{},insights:[],uncertain:'',conversation_text:'metin'}),/geçerli bir hasta/);
  await assert.rejects(()=>api.finalizeVoice('token',3,{context:{},insights:[],uncertain:'',conversation_text:'a'.repeat(72001)}),/72.000 karakteri/);
  assert.equal(calls,0);
 }finally{global.fetch=original}
});

test('native voice transcription rejects oversized text before it reaches UI',async()=>{
 const original=global.fetch;
 global.fetch=async()=>response(JSON.stringify({ok:true,revision:'r1',transcript:'a'.repeat(72001)}));
 try{
  await assert.rejects(()=>api.transcribeVoiceAudio('token',1,new Blob([new Uint8Array(128)]),'audio/mp4'),/sınır dışında/);
 }finally{global.fetch=original}
});

test('ASR refuses oversized and empty transcription while preserving local audio',async()=>{
 const original=global.fetch;
 try{
  for(const transcript of ['', '   ', 'x'.repeat(18001)]){
   global.fetch=async()=>response(JSON.stringify({ok:true,revision:'r1',transcript}));
   await assert.rejects(()=>api.transcribeVoiceAudio('token',1,new Blob([new Uint8Array(128)]),'audio/mp4'),/sınır dışında/);
  }
  global.fetch=async()=>response(JSON.stringify({ok:true,revision:' ',transcript:'Diş ağrısı'}));
  await assert.rejects(()=>api.transcribeVoiceAudio('token',1,new Blob([new Uint8Array(128)]),'audio/mp4'),/sınır dışında/);
 }finally{global.fetch=original}
});

test('native voice upload rejects missing MIME without throwing a TypeError',async()=>{
 const original=global.fetch;let calls=0;global.fetch=async()=>{calls++;throw Error('unexpected request')};
 try{
  const audio=new Blob([new Uint8Array(128)]);
  for(const mime of [undefined,null,42]){
   await assert.rejects(()=>api.transcribeVoiceAudio('token',1,audio,mime),/Ses biçimi desteklenmiyor/);
  }
  assert.equal(calls,0);
 }finally{global.fetch=original}
});

test('clinical finalization refuses malformed review payload before network',async()=>{
 const original=global.fetch;let calls=0;global.fetch=async()=>{calls++;throw Error('unexpected request')};
 try{
  for(const payload of [
   {context:null,insights:[],uncertain:'',conversation_text:'muayene'},
   {context:[],insights:[],uncertain:'',conversation_text:'muayene'},
   {context:{},insights:{},uncertain:'',conversation_text:'muayene'},
   {context:{},insights:[],uncertain:[],conversation_text:'muayene'}
  ])await assert.rejects(()=>api.finalizeVoice('token',1,payload),/bilgileri geçersiz/);
  assert.equal(calls,0);
 }finally{global.fetch=original}
});

test('voice extraction refuses malformed FDI teeth, communication and evidence',async()=>{
 const original=global.fetch;
 try{
  for(const review of [
   {fields:{},teeth:[{tooth:'99',status:'unknown',quote:'metin'}]},
   {fields:{},teeth:[{tooth:'44',status:'unknown'}]},
   {fields:{},communication:[{quote:'endişeliyim',observation:'kaygı'}]},
   {fields:{},literature_topics:[{topic:42,quote:'muayene'}]},
   {fields:{},source_requests:[{term:'amoxicillin',quote:123}]},
   {fields:{},decision_barriers:[null]}
  ]){
   global.fetch=async()=>response(JSON.stringify({ok:true,revision:'r1',review}));
   await assert.rejects(()=>api.extractVoice('token',4,'muayene'),/alanları geçersiz/);
  }
 }finally{global.fetch=original}
});

test('voice finalization rejects malformed clinician-edited context without network',async()=>{
 const original=global.fetch;let calls=0;global.fetch=async()=>{calls++;throw Error('unexpected clinical request')};
 const base={insights:[],uncertain:'',conversation_text:'Diş ağrısı görüşmesi'};
 try{
  for(const context of [
   {fields:{medications:{value:17}}},
   {fields:{allergies:{value:'Yok',edited:'yes'}}},
   {fields:{},teeth:[{tooth:'99',status:'existing',quote:'ağrı'}]},
   {fields:{},teeth:[{tooth:'44',status:'existing'}]},
   {fields:{},literature_topics:[{topic:123,quote:'kanal'}]},
   {fields:{},source_requests:[{term:'amoxicillin',quote:42}]},
   {fields:{},appointment:[]}
  ])await assert.rejects(()=>api.finalizeVoice('token',4,{...base,context}),/bağlamı geçersiz/);
  await assert.rejects(()=>api.finalizeVoice('token',4,{...base,context:{fields:{}},insights:Array.from({length:25},()=>({quote:'q',observation:'o'}))}),/bağlamı geçersiz/);
  assert.equal(calls,0);
 }finally{global.fetch=original}
});

test('final clinical payload rejects unrecognized fields and malformed appointments locally',async()=>{
 const original=global.fetch;let requests=0;global.fetch=async()=>{requests++;throw Error('unexpected request')};
 const base={insights:[],uncertain:'',conversation_text:'Muayene'};
 try{
  for(const context of [
   {fields:{made_up_field:{value:'veri'}}},
   {fields:{allergies:{value:'yok',unexpected:true}}},
   {fields:{allergies:{value:'x'.repeat(3001)}}},
   {fields:{},appointment:{quote:123}},
   {fields:{},appointment:{quote:'Saat 14',other:'secret'}},
   {fields:{},appointment:{acceptance_quote:'x'.repeat(1501)}}
  ])await assert.rejects(()=>api.finalizeVoice('token',4,{...base,context}),/bağlamı geçersiz/);
  assert.equal(requests,0);
 }finally{global.fetch=original}
});

test('voice extraction rejects unknown fields and oversized evidence before rendering',async()=>{
 const original=global.fetch;
 try{
  for(const review of [
   {fields:{unknown:{value:'test',quote:'test'}}},
   {fields:{allergies:{value:'yok'}}},
   {fields:{allergies:{value:'x'.repeat(3001),quote:'yok'}}},
   {fields:{},teeth:[{tooth:'44',status:'existing',quote:'x'.repeat(1501)}]},
   {fields:{},teeth:Array.from({length:53},()=>({tooth:'44',status:'existing',quote:'ağrı'}))}
  ]){
   global.fetch=async()=>response(JSON.stringify({ok:true,revision:'r1',review}));
   await assert.rejects(()=>api.extractVoice('token',4,'muayene'),/alanları geçersiz/);
  }
 }finally{global.fetch=original}
});

test('voice clinical tooth statuses match server allowlist in both directions',async()=>{
 const original=global.fetch;let calls=0;
 try{
  global.fetch=async()=>{calls++;return response(JSON.stringify({ok:true,revision:'r1',review:{fields:{},teeth:[{tooth:'44',status:'CURRENT',quote:'ağrı'}]}}))};
  await assert.rejects(()=>api.extractVoice('token',4,'görüşme'),/alanları geçersiz/);
  assert.equal(calls,1);
  global.fetch=async()=>{calls++;throw Error('unexpected finalization request')};
  const base={insights:[],uncertain:'',conversation_text:'görüşme'};
  for(const tooth of [
   {tooth:'44',status:'CURRENT',quote:'ağrı'},
   {tooth:'44',status:'OTHER',quote:'ağrı',unexpected:true},
   {tooth:'44',status:'OTHER',quote:'x'.repeat(1501)}
  ])await assert.rejects(()=>api.finalizeVoice('token',4,{...base,context:{fields:{},teeth:[tooth]}}),/bağlamı geçersiz/);
  assert.equal(calls,1);
 }finally{global.fetch=original}
});

test('voice extraction bounds lists and rejects unexpected appointment attributes',async()=>{
 const original=global.fetch;
 try{
  for(const review of [
   {fields:{},source_requests:Array.from({length:7},()=>({term:'amoxicillin',quote:'ilaç'}))},
   {fields:{},literature_topics:Array.from({length:41},()=>({topic:'endo.general',quote:'kanal'}))},
   {fields:{},communication:Array.from({length:25},()=>({quote:'a',observation:'b',suggestion:'c'}))},
   {fields:{},appointment:{quote:'yarın',extra:'not permitted'}},
   {fields:{},appointment:{quote:123}},
   {fields:{},appointment:{quote:'x'.repeat(1501)}}
  ]){
   global.fetch=async()=>response(JSON.stringify({ok:true,revision:'r1',review}));
   await assert.rejects(()=>api.extractVoice('token',4,'görüşme'),/alanları geçersiz/);
  }
 }finally{global.fetch=original}
});

test('final voice review enforces 32KB context and quoted clinician evidence before sending',async()=>{
 const original=global.fetch;let requests=0;global.fetch=async()=>{requests++;throw Error('network should not be called')};
 const base={uncertain:'',conversation_text:'Klinik görüşme'};
 try{
  await assert.rejects(()=>api.finalizeVoice('token',4,{...base,context:{fields:Object.fromEntries(['first_name','last_name','age','chief_complaint','medical_history','family_history','materials','dental_history','oral_habits','medications','allergies','clinical_findings','plan'].map(key=>[key,{value:'ğ'.repeat(1500),quote:'ğ'.repeat(1500)}]))},insights:[]}),/32 KB/);
  await assert.rejects(()=>api.finalizeVoice('token',4,{...base,context:{fields:{}},insights:[{finding:'Öneri'}]}),/kanıtları eksik/);
  assert.equal(requests,0);
 }finally{global.fetch=original}
});
