/* Actual rendered panel + both controllers in one DOM, synthetic media/provider. */
const assert=require('node:assert/strict'),fs=require('node:fs'),{spawnSync}=require('node:child_process');
const {JSDOM,VirtualConsole}=require('jsdom');
const rendered=spawnSync('python',['-c',"from jinja2 import Environment,FileSystemLoader; print(Environment(loader=FileSystemLoader('app/templates')).get_template('voice_exam_panel.html').render(patient={'id':1},user={'id':7}))"],{encoding:'utf8'});
assert.equal(rendered.status,0,rendered.stderr);
const css=fs.readFileSync('app/static/voice-exam.css','utf8');
const tick=()=>new Promise(r=>setTimeout(r,2));
async function until(test,label){for(let i=0;i<200;i++){if(test())return;await tick()}assert.fail('Timed out: '+label)}

async function fixture(seed=null,nativeRestore=false){
  const errors=[],calls=[],deadlines=[];
  const console=new VirtualConsole();console.on('jsdomError',e=>errors.push(e.message));
  const dom=new JSDOM('<!doctype html><style>'+css+'</style><section class="voice-session-page">'+rendered.stdout+'</section>',{url:'https://voice.example/voice-exams/1/session',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:console});
  const w=dom.window,get=s=>w.document.querySelector(s),root=get('#voice-exam');
  w.TextEncoder=TextEncoder;w.TextDecoder=TextDecoder;w.confirm=()=>true;
  if(seed)w.sessionStorage.setItem('dai:voice-draft:v1:7:1',seed);
  let socket,sourceMode='complete',flush=true,stopped=0,hangText=false;
  const nativeTimeout=w.setTimeout.bind(w);w.setTimeout=(fn,ms,...args)=>{deadlines.push(ms);return nativeTimeout(fn,ms===120000?10:ms,...args)};
  class Socket{
    static OPEN=1;
    constructor(){socket=this;this.readyState=1;this.bufferedAmount=0;setImmediate(()=>this.onopen?.())}
    send(body){if(typeof body!=='string')return;const data=JSON.parse(body);if(data.type==='start')setImmediate(()=>this.message({type:'ready'}));if(['pause','finish'].includes(data.type))setImmediate(()=>this.message({type:'ended',flushed:flush}))}
    message(data){this.onmessage?.({data:JSON.stringify(data)})}
    close(){this.readyState=3;setImmediate(()=>this.onclose?.())}
  }
  class Context{constructor(){this.audioWorklet={addModule:async()=>{}};this.destination={}}async resume(){}createMediaStreamSource(){return {connect(){},disconnect(){}}}async close(){}}
  class Worklet{constructor(){this.port={postMessage:()=>setImmediate(()=>this.port.onmessage?.({data:{type:'flushed'}}))}}connect(){}disconnect(){}}
  w.WebSocket=Socket;w.AudioContext=Context;w.AudioWorkletNode=Worklet;
  Object.defineProperty(w.navigator,'mediaDevices',{value:{getUserMedia:async()=>({getTracks:()=>[{stop:()=>stopped++}]})}});
  w.fetch=async(url,options={})=>{
    calls.push({url,body:options.body?JSON.parse(options.body):null});
    if(url.endsWith('/text')&&hangText)return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{const error=new Error('Aborted');error.name='AbortError';reject(error)},{once:true}));
    let body={ok:true,enabled:true,live_enabled:true};
    if(url.endsWith('/text'))body={ok:true,revision:'a'.repeat(64),review:{transcript:JSON.parse(options.body).transcript,fields:{chief_complaint:{value:'Soğukta ağrı',quote:'Soğuk içemiyorum.'}},teeth:[],communication:sourceMode==='overflow'?Array.from({length:25},(_,i)=>({category:'CLINICAL_STATEMENT',quote:'Klinik ifade '+i,observation:'Hekime atfedilen ifade',suggestion:'Kontrol'})):sourceMode==='clinician'?[{category:'CLINICAL_STATEMENT',quote:'Bu işlem kesin risksizdir.',observation:'Hekime atfedilen klinik ifade',suggestion:'Kaynak kapsamı kontrol edilmeli.'}]:[],follow_up_questions:[]}};
    else if(url.endsWith('/finalize')){
      if(sourceMode==='failure')body={ok:false,error:'Synthetic source outage'};
      else if(sourceMode==='unchanged')body={ok:true,revision:'a'.repeat(64),final:{not_modified:true,source_fingerprint:'f'.repeat(64),review_status:{source_retryable:true}}};
      else body={ok:true,revision:'a'.repeat(64),final:{source_fingerprint:'f'.repeat(64),summary:[{field:'chief_complaint',quote:'Soğukta ağrı',text:'Soğukta ağrı'}],questions:[{field:'chief_complaint',quote:'Soğukta ağrı',text:'Ne zamandır?'}],contradictions:[],clinical_items:sourceMode.startsWith('cards')?[{source_id:'test',consideration:'Koşullu klinik kontrol.',missing_information:'Malzeme bilinmiyor.',patient_quote:'Soğukta ağrı',source_quote:'Literal document passage.',alternative:'Hekim malzemeyi doğrulayabilir.'}]:[],clinician_review:sourceMode==='clinician'?[{field:'clinician_0',quote:'Bu işlem kesin risksizdir.',status:'unverified',source_ids:[]}]:[],references:sourceMode.startsWith('cards')?[{id:'test',url:'https://www.ada.org/example',institution:'ADA',title:'Synthetic document',evidence_level:'professional_information'}]:[],unavailable:sourceMode==='partial'?['group:literature']:[],notice:'Synthetic scope',source_coverage:[{topic:'prosth.fixed',label:'Kuron ve köprü',status:sourceMode==='native'?'research_material_unverified':'uncovered',source_ids:[]}],review_status:{source_retryable:sourceMode==='partial'}}};
    }else if(url.endsWith('/clinical'))body={ok:true,items:[],references:[],unavailable:[],notice:'Synthetic clinical review'};
    else if(url.endsWith('/apply'))body={ok:true,patient_url:'/voice-exams/1/session#saved'};
    if(sourceMode.startsWith('cards')&&url.endsWith('/finalize'))body.final.summary=[{field:'chief_complaint',quote:'Soğukta ağrı, gece uykusundan uyandırıyor.',text:'Soğukta ağrı, gece uykusundan uyandırıyor.'}];
    if(sourceMode.startsWith('cards')&&url.endsWith('/finalize'))body.final.review_status.material_evidence=[{topic:'endo.post_core',candidate_source_count:sourceMode==='cards-gap'?0:1,accepted_control_count:0}];
    if(sourceMode.startsWith('cards')&&url.endsWith('/finalize'))body.final.material_review=[{topic:'endo.post_core',label:'Post, kor ve kalan diş dokusu',status:'unverified',source_ids:[]}];
    if(sourceMode==='compact'&&url.endsWith('/text'))body.review.communication=[
      {quote:'Yeni proteze param yok.',observation:'Yeni proteze param yok.',suggestion:'Seçenekleri konuşun.'},
      {category:'COST',quote:'Yeni proteze param yok.',observation:'Hasta maliyet konusunda kaygılı.',question:'Önce hangi seçeneği konuşalım?',explanation:'Maddi kaygı kararı etkiler.'},
      {response_type:'CLINICIAN_RESPONSE',quote:'Önce muayene edelim.',observation:'Görüşmede verilen yanıt: Önce muayene edelim.'}];
    if(sourceMode==='compact'&&url.endsWith('/finalize')){
      body.final.clinical_items=[{source_id:'test',review_topic:'endo.post_core',consideration:'Kalan diş dokusunu değerlendirin.',missing_information:'Duvar kalınlığı ölçülmedi.',patient_quote:'Fiber post düşünüyoruz.',source_quote:'Literal passage.',alternative:'Muayeneyle karar verin.'}];
      body.final.references=[{id:'test',url:'https://www.aae.org/example',institution:'AAE',title:'Post değerlendirmesi'}];
      body.final.material_review=[{topic:'endo.post_core',label:'Post, kor ve kalan diş dokusu',status:'unverified',source_ids:[]}];
      body.final.source_coverage=[{topic:'endo.post_core',label:'Post, kor ve kalan diş dokusu',status:'research_material_unverified',source_ids:[]}];
      body.final.clinician_review=[{field:'clinician_0',quote:'Bu işlem kesin risksiz.',status:'unverified'},{field:'clinician_1',quote:'Bu doz herkese uygundur.',status:'unverified'}];
      body.final.anamnesis_review=[{field:'medications',label:'İlaç kullanımı',state:'recorded'},{field:'allergies',label:'Alerji',state:'not_recorded'}];
      body.final.questions=[{field:'chief_complaint',quote:'Soğukta ağrı',text:'Ne zamandır?'},{field:'chief_complaint',quote:'Soğukta ağrı',text:'Ne zamandır?'}];
    }
    if(sourceMode==='readable'&&url.endsWith('/text'))body.review.fields={medical_history:{value:'Olumsuz beyan: Sistemik rahatsızlık yok\nGeçmiş: Anjiyo öyküsü\nBelirsiz: İşlemin tarihi bilinmiyor',quote:'Rahatsızlığım yok, önceden anjiyo oldum.'},allergies:{value:'Olumsuz beyan: Penisilin alerjisi',quote:'Penisiline alerjim yok.'},dental_history:{value:'Geçmiş: Sol öndeki dişe iki yıl önce kanal yapılmıştı.',quote:'Sol öndeki dişe iki yıl önce kanal yapılmıştı.'},oral_habits:{value:'Güncel: Sigara günde beş tane.',quote:'Sigara günde beş tane.'},family_history:{value:'Güncel: Annem şeker hastası.',quote:'Annem şeker hastası.'},materials:{value:'Belirsiz: Yapıştırıcının markası henüz belli değil.',quote:'Yapıştırıcının markası henüz belli değil.'}};
    if(sourceMode==='readable'&&url.endsWith('/text'))body.review.communication=[{response_type:'CLINICIAN_RESPONSE',quote:'Şu an sökme kararı vermedik.',observation:'Görüşmede verilen yanıt: Şu an sökme kararı vermedik.',suggestion:''}];
    if(sourceMode==='readable'&&url.endsWith('/finalize'))body.final.anamnesis_review=[{field:'family_history',label:'Aile sağlık öyküsü',state:'recorded'},{field:'medications',label:'İlaçların kullanım öyküsü',state:'not_recorded'}];
    if(sourceMode==='readable'&&url.endsWith('/finalize'))body.final.summary=Object.entries(JSON.parse(options.body).context.fields).map(([field,item])=>({field,text:item.value,quote:item.value}));
    return {ok:body.ok,json:async()=>body};
  };
  for(const file of ['voice-finish-draft.js','voice-exam.js','voice-exam-live.js'])w.eval(fs.readFileSync('app/static/'+file,'utf8'));
  if(nativeRestore){get('[data-voice-transcript]').value=nativeRestore==='stale'?'OLD_EXPIRED_TRANSCRIPT':'';get('[data-voice-consent]').checked=true;get('[data-voice-confirm]').checked=true;const input=get('[data-field-row] textarea');if(input)input.value='Tarayıcının eski form değeri'}
  w.dispatchEvent(new w.PageTransitionEvent('pageshow',{persisted:false}));
  await until(()=>!get('[data-live-panel]').hidden,'capabilities');
  await until(()=>!get('[data-voice-transcript]').disabled,'recovered form ready');
  async function begin(){get('[data-voice-consent]').click();get('[data-live-start]').click();await until(()=>root.dataset.liveState==='listening','listen')}
  async function finish(){get('[data-live-finish]').click();get('[data-live-finish]').click();await until(()=>!get('[data-voice-save]').disabled,'finish result')}
  return {w,get,root,calls,errors,deadlines,begin,finish,sessionData:()=>w.sessionStorage.getItem('dai:voice-draft:v1:7:1'),speech:text=>socket.message({type:'final',text}),setMode:mode=>sourceMode=mode,setFlush:value=>flush=value,
    disconnect:()=>socket.onclose(),hangExtraction:value=>hangText=value,stopped:()=>stopped,close(){w.dispatchEvent(new w.Event('pagehide'));w.close()}};
}

(async()=>{
  let f=await fixture(null,true);let restoredSeed;
  try{await tick();assert.equal(f.get('[data-voice-consent]').checked,false,'Native consent must be reset even without a cached draft');assert.equal(f.get('[data-voice-confirm]').checked,false)}finally{f.close()}
  for(const badSeed of [null,'{"broken":true}',JSON.stringify({version:1,savedAt:Date.now()-31*60*1000,text:'Expired source'})]){
    f=await fixture(badSeed,'stale');
    try{await tick();assert.equal(f.get('[data-voice-transcript]').value,'','Native history cannot revive discarded or expired transcript');assert.equal(f.sessionData(),null,'Stale native values must not create a fresh cache')}finally{f.close()}
  }
  f=await fixture();
  try{
    await f.begin();f.speech('Soğuk içemiyorum.');await f.finish();
    f.get('[data-field-row] input').click();f.get('[data-voice-confirm]').click();
    f.w.dispatchEvent(new f.w.Event('pagehide'));
    restoredSeed=f.sessionData();assert.ok(restoredSeed,'Refresh must retain a bounded session draft');
    f.w.dispatchEvent(new f.w.PageTransitionEvent('pageshow',{persisted:true}));
    f.w.dispatchEvent(new f.w.Event('pagehide'));
    assert.equal(f.sessionData(),restoredSeed,'BFCache reload second pagehide must not erase the retained session draft');
    assert.equal(f.get('[data-voice-transcript]').value,'','Pagehide still clears live in-memory transcript and closes media');
  }finally{f.close()}
  f=await fixture(restoredSeed);
  try{
    assert.equal(f.get('[data-voice-transcript]').value,'Soğuk içemiyorum.');
    assert.equal(f.get('[data-voice-consent]').checked,false,'Consent is never restored');
    assert.equal(f.get('[data-voice-confirm]').checked,false,'Physician approval is never restored');
    assert.equal(f.get('[data-field-row] input').checked,false,'Save selections must be reviewed again');
    f.get('[data-voice-consent]').checked=true;f.get('[data-voice-finalize]').click();await tick();
    assert.equal(f.calls.some(c=>c.url.endsWith('/text')||c.url.endsWith('/finalize')),false,'Completed stages survive reload without another model call');
    f.get('[data-voice-discard]').click();assert.equal(f.sessionData(),null,'Discard clears session recovery');
  }finally{f.close()}
  f=await fixture(restoredSeed,true);
  try{
    await tick();
    assert.equal(f.get('[data-voice-transcript]').value,'Soğuk içemiyorum.','Browser native history form restoration cannot wipe the recovered transcript');
    assert.equal(f.get('[data-field-row] textarea').value,'Soğukta ağrı','Recovered fields are reapplied after native form restoration');
    assert.equal(f.get('[data-voice-consent]').checked,false);
    assert.equal(f.get('[data-voice-confirm]').checked,false);
  }finally{f.close()}
  const manyTopics=JSON.parse(restoredSeed);manyTopics.literatureTopics=Array.from({length:24},(_,i)=>({topic:'endo.general',quote:'Dayanak '+i}));
  f=await fixture(JSON.stringify(manyTopics));
  try{assert.equal(f.get('[data-voice-transcript]').value,'Soğuk içemiyorum.','All24 server-supported topic entries retain the draft')}finally{f.close()}
  const shortened=JSON.parse(restoredSeed);shortened.text='Yeni kısa metin.';shortened.checkpoint={text:'Önceki uzun metin. '.repeat(2000),cursor:3,version:1,extractionVersion:1};shortened.unprocessed=true;shortened.final=null;
  f=await fixture(JSON.stringify(shortened));
  try{assert.equal(f.get('[data-voice-transcript]').value,'Yeni kısa metin.','Shortening resets an obsolete chunk cursor, never erases edited text');assert.equal(f.get('[data-voice-save]').disabled,true)}finally{f.close()}
  f=await fixture(restoredSeed);
  try{const now=f.w.Date.now;f.w.Date.now=()=>now()+31*60*1000;f.w.dispatchEvent(new f.w.Event('pagehide'));assert.equal(f.sessionData(),null,'Idle pagehide must not renew an expired unchanged clinical draft')}finally{f.close()}
  const expired=JSON.parse(restoredSeed);expired.savedAt=Date.now()-31*60*1000;
  for(const badSeed of [JSON.stringify(expired),'{"broken":true}']){
    f=await fixture(badSeed,true);
    try{await tick();assert.equal(f.get('[data-voice-consent]').checked,false,'Expired/corrupt drafts must not retain native consent');assert.equal(f.get('[data-voice-confirm]').checked,false)}finally{f.close()}
  }
  f=await fixture(JSON.stringify(expired));
  try{assert.equal(f.get('[data-voice-transcript]').value,'','Expired clinical text is not restored');assert.equal(f.sessionData(),null)}finally{f.close()}
  f=await fixture();
  try{
    f.setMode('compact');await f.begin();f.speech('Soğuk içemiyorum.');await f.finish();
    const results=f.get('[data-voice-final-results]'),cards=Array.from(results.children);
    assert.equal(cards.some(el=>el.querySelector('summary')?.textContent.includes('Görüşme özeti')),false,'A summary identical to an extracted field must not repeat the patient information');
    assert.equal(cards.some(el=>el.classList.contains('voice-material-review')),false,'Material status belongs with clinical controls, not another repeated card');
    const controls=cards.find(el=>el.querySelector('summary')?.textContent.includes('Dikkat edilecekler'));
    assert.ok(controls,'Use a short clear clinical heading');
    assert.ok(controls.textContent.includes('Bu işlem kesin risksiz.'));
    assert.ok(controls.textContent.includes('Bu doz herkese uygundur.'),'Distinct unverified clinician anchors must both remain inspectable');
    assert.ok(controls.textContent.includes('Kalan diş dokusunu değerlendirin.'));
    assert.ok(controls.textContent.includes('Uygunluk doğrulanamadı'),'Unverified material coverage must remain visible');
    const communication=cards.find(el=>el.querySelector('summary')?.textContent.includes('Hastayla iletişim'));
    assert.equal(communication.querySelectorAll(':scope > article').length,1,'Same concern and barrier share one communication item');
    assert.ok(communication.textContent.includes('Önce hangi seçeneği konuşalım?'));
    assert.ok(communication.querySelector('details')?.textContent.includes('Yeni proteze param yok.'));
    const questions=cards.find(el=>el.querySelector('summary')?.textContent.includes('Tamamlanacak bilgiler'));
    assert.equal(questions.querySelectorAll(':scope > article').length,1,'Identical questions appear once');
    assert.ok(results.querySelector('.voice-source-list .voice-topic-coverage'),'Topic coverage remains available under source details');
    assert.equal(controls.querySelector('.voice-topic-coverage'),null,'Source boilerplate must not fill the main clinical result');
    assert.ok(results.querySelector('.voice-anamnesis-review').textContent.includes('Alerji'));
    assert.equal(results.querySelector('.voice-anamnesis-review').textContent.includes('İlaç kullanımı'),false,'Do not repeat already recorded history fields');
    assert.equal(f.calls.filter(c=>c.url.endsWith('/finalize')).length,1);
  }finally{f.close()}
  f=await fixture();
  try{
    await f.begin();f.speech('Soğuk içemiyorum.');
    f.get('[data-live-pause]').click();await until(()=>f.root.dataset.liveState==='paused','pause');
    assert.equal(f.calls.filter(c=>c.url.endsWith('/text')).length,0);
    assert.equal(f.get('[data-voice-transcript]').value,'Soğuk içemiyorum.');
    await f.finish();
    assert.equal(f.calls.filter(c=>c.url.endsWith('/text')).length,1);
    assert.equal(f.calls.filter(c=>c.url.endsWith('/finalize')).length,1);
    assert.equal(f.w.getComputedStyle(f.get('.voice-review')).display,'block','Completed review must be visible');
    assert.ok(f.get('.voice-topic-coverage')?.textContent.includes('Kuron ve köprü: İlgili kaynak bulunamadı'), 'Uncovered non-drug topics must stay visible');
    f.get('[data-field-row] input').click();f.get('[data-voice-confirm]').click();f.get('[data-voice-save]').click();
    await until(()=>f.calls.some(c=>c.url.endsWith('/apply')),'save');await tick();
    const saved=f.calls.find(c=>c.url.endsWith('/apply')).body;
    assert.equal(saved.fields.chief_complaint,'Soğukta ağrı');assert.equal('transcript' in saved,false);
    assert.equal(f.get('[data-voice-transcript]').value,'');assert.equal(f.get('[data-voice-consent]').checked,false);assert.ok(f.stopped()>0);
    assert.deepEqual(f.errors,[]);
  }finally{f.close()}
  f=await fixture();
  try{
    await f.begin();f.speech('Soğuk içemiyorum.');f.disconnect();await until(()=>f.root.dataset.liveState==='error','connection error');
    f.get('[data-live-finish]').click();await tick();
    assert.equal(f.calls.filter(c=>c.url.endsWith('/text')).length,0,'Broken connection must require explicit text review');
    assert.equal(f.w.getComputedStyle(f.get('[data-voice-transcript]').closest('details')).display,'block','Recovery controls must remain reachable');
    f.get('[data-live-review]').click();
    assert.equal(f.get('[data-voice-transcript]').closest('details').open,true,'Review action must open the retained transcript when no summary exists');
    assert.equal(f.w.document.activeElement,f.get('[data-voice-transcript]'),'Recovery must focus the visible transcript');
    assert.equal(f.calls.some(c=>c.url.endsWith('/text')),false,'Opening recovery must not process unconfirmed text');
    f.get('[data-voice-text]').click();
    await until(()=>!f.get('[data-voice-save]').disabled,'manual recovery');assert.deepEqual(f.errors,[]);
  }finally{f.close()}
  f=await fixture();
  try{
    f.setFlush(false);await f.begin();f.speech('Soğuk içemiyorum.');f.get('[data-live-finish]').click();
    await until(()=>f.get('.voice-exam-status').textContent.includes('tamamlandığı doğrulanamadı'),'unconfirmed finish');
    assert.equal(f.get('.voice-review').hidden,true,'No clinical summary exists before extraction');
    f.get('[data-live-review]').click();
    assert.equal(f.get('[data-voice-transcript]').closest('details').open,true,'Unconfirmed finish must reveal recovery instead of scrolling to a hidden summary');
    assert.equal(f.w.document.activeElement,f.get('[data-voice-transcript]'));
    assert.equal(f.calls.some(c=>c.url.endsWith('/text')||c.url.endsWith('/finalize')),false);
    f.get('[data-voice-text]').click();await until(()=>!f.get('[data-voice-save]').disabled,'reviewed unconfirmed text');
    f.get('[data-voice-transcript]').closest('details').open=false;
    f.get('[data-live-review]').click();
    assert.equal(f.get('[data-voice-transcript]').closest('details').open,false,'Completed summary navigation must not reopen transcript recovery');
    assert.equal(f.calls.filter(c=>c.url.endsWith('/text')).length,1);
    assert.equal(f.calls.filter(c=>c.url.endsWith('/finalize')).length,1);
    assert.deepEqual(f.errors,[]);
  }finally{f.close()}
  f=await fixture();
  try{
    f.setMode('partial');await f.begin();f.speech('Soğuk içemiyorum.');await f.finish();
    const prior=f.get('[data-voice-final-results]').textContent;assert.ok(prior.includes('Ne zamandır?'));
    f.setMode('unchanged');f.get('[data-voice-finalize]').click();await until(()=>!f.get('[data-voice-save]').disabled,'unchanged evidence');
    assert.equal(f.get('[data-voice-final-results]').textContent,prior);
    f.setMode('failure');f.get('[data-voice-finalize]').click();await until(()=>!f.get('[data-voice-save]').disabled,'failed partial retry');
    assert.equal(f.get('[data-voice-final-results]').textContent,prior);assert.equal(f.calls.filter(c=>c.url.endsWith('/text')).length,1);
    assert.deepEqual(f.errors,[]);
  }finally{f.close()}
  f=await fixture();
  try{
    f.hangExtraction(true);await f.begin();f.speech('Soğuk içemiyorum.');f.get('[data-live-finish]').click();
    await until(()=>f.get('.voice-exam-status').textContent.includes('zaman aşımına'),'bounded request timeout');
    assert.equal(f.get('[data-voice-transcript]').value,'Soğuk içemiyorum.');
    assert.equal(f.get('[data-voice-text]').disabled,false,'Timeout must release controls for explicit retry');
    f.hangExtraction(false);f.get('[data-voice-text]').click();await until(()=>!f.get('[data-voice-save]').disabled,'timeout recovery');
    assert.deepEqual(f.errors,[]);
  }finally{f.close()}
  f=await fixture();
  try{
    f.get('[data-voice-consent]').checked=true;
    f.deadlines.length=0;f.get('[data-voice-clinical]').click();
    await until(()=>f.calls.some(c=>c.url.endsWith('/clinical')),'manual clinical review');
    assert.equal(f.deadlines[0],120000,'Clinical source/model work needs the extended request budget');
    await until(()=>!f.get('[data-voice-clinical]').disabled,'clinical review completed');
    assert.deepEqual(f.errors,[]);
  }finally{f.close()}
  f=await fixture();
  try{
    f.setMode('native');await f.begin();f.speech('Soğuk içemiyorum.');await f.finish();
    assert.ok(f.get('.voice-topic-coverage').textContent.includes('Konuya özgü dayanak doğrulanmadı'), 'Native research must not imply verified topic evidence');
  }finally{f.close()}
  f=await fixture();
  try{
    f.setMode('clinician');await f.begin();f.speech('Soğuk içemiyorum.');await f.finish();
    assert.ok(f.get('[data-voice-final-results]').textContent.includes('Kaynakla doğrulanamayan hekim ifadeleri'));
    assert.ok(f.get('[data-voice-final-results]').textContent.includes('kaynak kontrolü tamamlanamadı'));
    assert.equal(f.get('[data-voice-communication]').textContent.includes('undefined'),false);
    assert.equal(f.calls.find(c=>c.url.endsWith('/finalize')).body.insights[0].category,'CLINICAL_STATEMENT');
    f.get('[data-field-row] input').click();f.get('[data-voice-confirm]').click();f.get('[data-voice-save]').click();
    await until(()=>f.calls.some(c=>c.url.endsWith('/apply')),'save excludes clinician attribution');
    const saved=f.calls.find(c=>c.url.endsWith('/apply')).body;
    assert.equal(Object.keys(saved.fields).some(k=>k.startsWith('clinician_')),false);
    assert.equal(JSON.stringify(saved).includes('Bu işlem kesin risksizdir.'),false);
  }finally{f.close()}
  f=await fixture();
  try{
    f.setMode('cards');await f.begin();f.speech('Soğuk içemiyorum.');await f.finish();
    const results=f.get('[data-voice-final-results]');
    const clinical=Array.from(results.children).find(el=>el.querySelector('summary')?.textContent.includes('Görüşme özeti'));
    assert.ok(clinical?.tagName==='DETAILS','Clinical summary must be a native collapsible card');
    assert.equal(clinical.open,false);clinical.querySelector('summary').click();assert.equal(clinical.open,true);
    assert.equal(clinical.querySelector('small'),null,'Identical summary/dayanak must not be printed twice');
    const evidence=results.querySelector('.voice-source-evidence');
    assert.ok(evidence,'Every clinical control must expose its own source and literal passage');
    assert.equal(evidence.open,false);evidence.querySelector('summary').click();assert.equal(evidence.open,true);
    assert.ok(evidence.textContent.includes('Literal document passage.'));
    assert.equal(evidence.querySelector('a').href,'https://www.ada.org/example');
    const record=f.get('[data-voice-record-fields]');
    assert.equal(record.tagName,'DETAILS');assert.equal(record.open,false);
    assert.ok(record.contains(f.get('[data-voice-fields]')));
    assert.ok(results.compareDocumentPosition(record)&f.w.Node.DOCUMENT_POSITION_FOLLOWING,'Record choices follow the review');
    assert.ok(results.textContent.includes('Koşullu klinik kontrol.'));
    assert.ok(results.querySelector('.voice-material-gap')?.textContent.includes('Uygunluk doğrulanamadı'),'A general source note must not hide an incomplete material check');
    assert.ok(results.textContent.includes('Malzeme bilinmiyor.'));
    assert.ok(results.textContent.includes('İlgili olabilecek kaynak bölümü var'));
    record.querySelector('summary').click();f.get('[data-field-row] input').click();f.get('[data-voice-confirm]').click();f.get('[data-voice-save]').click();
    await until(()=>f.calls.some(c=>c.url.endsWith('/apply')),'card layout preserves approved save');
    assert.equal(f.calls.filter(c=>c.url.endsWith('/finalize')).length,1,'Opening cards must not call the model again');
    assert.deepEqual(f.errors,[]);
  }finally{f.close()}
  f=await fixture();
  try{
    f.setMode('cards-gap');await f.begin();f.speech('Soğuk içemiyorum.');await f.finish();
    assert.ok(f.get('.voice-material-evidence').textContent.includes('Bu işlem için kaynak parçası seçilemedi'));
  }finally{f.close()}
  f=await fixture();
  try{
    f.setMode('overflow');await f.begin();f.speech('Soğuk içemiyorum.');f.get('[data-live-finish]').click();
    await until(()=>f.get('.voice-exam-status').textContent.includes('Hekim ifadeleri sınırı'),'explicit clinician overflow');
    assert.equal(f.calls.some(c=>c.url.endsWith('/finalize')),false);
    assert.equal(f.get('[data-voice-save]').disabled,true);
    assert.ok(f.get('[data-voice-transcript]').value.includes('Soğuk içemiyorum.'));
  }finally{f.close()}
  f=await fixture();
  try{
    f.setMode('readable');await f.begin();f.speech('Rahatsızlığım yok, önceden anjiyo oldum.');await f.finish();
    const card=f.get('[data-voice-record-fields]');card.querySelector('summary').click();
    const readable=Array.from(card.querySelectorAll('[data-field-row]')).map(row=>row.textContent+' '+row.querySelector('textarea').value).join('\n');
    assert.ok(card.querySelector('[data-field-row=medical_history] label')?.textContent.includes('Sağlık geçmişi'),'Each recorded value needs its clinical field label');
    assert.equal(readable.includes('Olumsuz beyan:'),false,'Internal assertion labels must not be shown to the clinician');
    assert.ok(readable.includes('Sistemik rahatsızlık yok'));
    assert.ok(readable.includes('Olmadığı belirtildi: Penisilin alerjisi'),'A negative noun-only fact must never read as a positive allergy');
    assert.ok(f.get('[data-field-row=allergies] textarea').value.includes('Olmadığı belirtildi: Penisilin alerjisi'));
    assert.ok(readable.includes('Önceden: Anjiyo öyküsü'),'Removing jargon must preserve historical meaning');
    assert.ok(readable.includes('Net değil: İşlemin tarihi bilinmiyor'));
    assert.ok(readable.includes('Önceki diş tedavileri'));
    assert.ok(readable.includes('Ağız bakımı ve alışkanlıklar'));
    assert.ok(readable.includes('Aile sağlık öyküsü'));
    assert.ok(readable.includes('Konuşulan materyaller'));
    assert.ok(f.get('[data-field-row=materials] textarea').value.includes('markası henüz belli değil'));
    const anamnesis=f.get('.voice-anamnesis-review');
    assert.equal(anamnesis.textContent.includes('Aile sağlık öyküsü'),false,'Recorded history is not repeated');
    assert.ok(anamnesis.textContent.includes('dökümde bilgi yok'));
    assert.equal(f.get('[data-voice-communication]').textContent.includes('undefined'),false);
    assert.ok(f.get('[data-voice-communication]').textContent.includes('Şu an sökme kararı vermedik'));
    assert.ok(f.get('[data-field-row=dental_history] textarea').value.includes('iki yıl önce kanal'));
    assert.ok(f.get('[data-field-row=oral_habits] textarea').value.includes('Sigara günde beş tane'));
    assert.ok(f.get('[data-voice-final-results]').textContent.includes('Dikkat edilecekler'));
    const value=f.get('[data-field-row] textarea');
    assert.equal(value.value.includes('Olumsuz beyan:'),false);
    const sent=f.calls.find(c=>c.url.endsWith('/finalize')).body.context.fields.medical_history.value;
    assert.ok(sent.startsWith('Olumsuz beyan:'),'Presentation changes must preserve the original reasoning and quote anchors');
    f.get('[data-field-row] input').click();f.get('[data-voice-confirm]').click();f.get('[data-voice-save]').click();
    await until(()=>f.calls.some(c=>c.url.endsWith('/apply')),'unchanged friendly field save');
    assert.equal(f.calls.find(c=>c.url.endsWith('/apply')).body.fields.medical_history,sent);
  }finally{f.close()}
  console.log('Integrated DOM: live→pause→finish→save, disconnected recovery and partial evidence retry passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
