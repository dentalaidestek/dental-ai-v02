/* Actual rendered panel + both controllers in one DOM, synthetic media/provider. */
const assert=require('node:assert/strict'),fs=require('node:fs'),{spawnSync}=require('node:child_process');
const {JSDOM,VirtualConsole}=require('jsdom');
const rendered=spawnSync('python',['-c',"from jinja2 import Environment,FileSystemLoader; print(Environment(loader=FileSystemLoader('app/templates')).get_template('voice_exam_panel.html').render(patient={'id':1}))"],{encoding:'utf8'});
assert.equal(rendered.status,0,rendered.stderr);
const css=fs.readFileSync('app/static/voice-exam.css','utf8');
const tick=()=>new Promise(r=>setTimeout(r,2));
async function until(test,label){for(let i=0;i<200;i++){if(test())return;await tick()}assert.fail('Timed out: '+label)}

async function fixture(){
  const errors=[],calls=[],deadlines=[];
  const console=new VirtualConsole();console.on('jsdomError',e=>errors.push(e.message));
  const dom=new JSDOM('<!doctype html><style>'+css+'</style><section class="voice-session-page">'+rendered.stdout+'</section>',{url:'https://voice.example/voice-exams/1/session',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:console});
  const w=dom.window,get=s=>w.document.querySelector(s),root=get('#voice-exam');
  w.TextEncoder=TextEncoder;w.TextDecoder=TextDecoder;
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
    if(url.endsWith('/text'))body={ok:true,revision:'a'.repeat(64),review:{transcript:JSON.parse(options.body).transcript,fields:{chief_complaint:{value:'Soğukta ağrı',quote:'Soğuk içemiyorum.'}},teeth:[],communication:[],follow_up_questions:[]}};
    else if(url.endsWith('/finalize')){
      if(sourceMode==='failure')body={ok:false,error:'Synthetic source outage'};
      else if(sourceMode==='unchanged')body={ok:true,revision:'a'.repeat(64),final:{not_modified:true,source_fingerprint:'f'.repeat(64),review_status:{source_retryable:true}}};
      else body={ok:true,revision:'a'.repeat(64),final:{source_fingerprint:'f'.repeat(64),summary:[{field:'chief_complaint',quote:'Soğukta ağrı',text:'Soğukta ağrı'}],questions:[{field:'chief_complaint',quote:'Soğukta ağrı',text:'Ne zamandır?'}],contradictions:[],clinical_items:[],references:[],unavailable:sourceMode==='partial'?['group:literature']:[],notice:'Synthetic scope',source_coverage:[{topic:'prosth.fixed',label:'Kuron ve köprü',status:'uncovered',source_ids:[]}],review_status:{source_retryable:sourceMode==='partial'}}};
    }else if(url.endsWith('/clinical'))body={ok:true,items:[],references:[],unavailable:[],notice:'Synthetic clinical review'};
    else if(url.endsWith('/apply'))body={ok:true,patient_url:'/voice-exams/1/session#saved'};
    return {ok:body.ok,json:async()=>body};
  };
  for(const file of ['voice-finish-draft.js','voice-exam.js','voice-exam-live.js'])w.eval(fs.readFileSync('app/static/'+file,'utf8'));
  await until(()=>!get('[data-live-panel]').hidden,'capabilities');
  async function begin(){get('[data-voice-consent]').checked=true;get('[data-live-start]').click();await until(()=>root.dataset.liveState==='listening','listen')}
  async function finish(){get('[data-live-finish]').click();get('[data-live-finish]').click();await until(()=>!get('[data-voice-save]').disabled,'finish result')}
  return {w,get,root,calls,errors,deadlines,begin,finish,speech:text=>socket.message({type:'final',text}),setMode:mode=>sourceMode=mode,setFlush:value=>flush=value,
    disconnect:()=>socket.onclose(),hangExtraction:value=>hangText=value,stopped:()=>stopped,close(){w.dispatchEvent(new w.Event('pagehide'));w.close()}};
}

(async()=>{
  let f=await fixture();
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
    f.get('[data-voice-transcript]').closest('details').open=true;f.get('[data-voice-text]').click();
    await until(()=>!f.get('[data-voice-save]').disabled,'manual recovery');assert.deepEqual(f.errors,[]);
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
  console.log('Integrated DOM: live→pause→finish→save, disconnected recovery and partial evidence retry passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
