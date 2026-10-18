const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../app/templates/expert_case_room.html'),'utf8');
const code=source.slice(source.indexOf('let lastReadAcked='),source.indexOf('const currentComposerError'));
function setup(){
 const calls=[],timers=[],queued=[],events=[];
 const c={destroyed:false,suspended:false,lastMessageId:128,
  document:{visibilityState:'visible',hasFocus:()=>true,dispatchEvent:e=>events.push(e)},
  window:{dispatchEvent:e=>events.push(e)},chat:{isConnected:true,getClientRects:()=>[{}],dataset:{caseId:'{{ case.id }}',userId:'3'}},
  URLSearchParams,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options?.detail}},
  setTimeout:(fn,delay)=>{timers.push({fn,delay});return timers.length},clearTimeout:()=>{},queueMicrotask:fn=>queued.push(fn)};
 c.chat.dataset.caseId='19';
 // Render the actual template's case-id constant as the browser does.
 vm.createContext(c);vm.runInContext(code.replaceAll('{{ case.id }}','19'),c);
 c.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({ok:true,case_id:19,user_id:3,through_id:Number(options.body.get('through_id'))})}};
 return {c,calls,timers,queued,events,ack:()=>vm.runInContext('lastReadAcked',c)};
}
(async()=>{
 const a=setup();
 a.c.document.visibilityState='hidden';await a.c.markVisibleChatRead();
 a.c.document.visibilityState='visible';a.c.document.hasFocus=()=>false;await a.c.markVisibleChatRead();
 a.c.document.hasFocus=()=>true;a.c.suspended=true;await a.c.markVisibleChatRead();
 assert.equal(a.calls.length,0);
 a.c.suspended=false;await a.c.markVisibleChatRead();await a.c.markVisibleChatRead();
 assert.equal(a.calls.length,1);assert.equal(a.ack(),128);
 assert.equal(a.calls[0].options.keepalive,true);assert.equal(a.calls[0].options.method,'POST');
 assert.equal(a.events.length,2); // server acknowledgement, not optimistic navigation
 const b=setup();const realFetch=b.c.fetch;let first=true;
 b.c.fetch=async(...args)=>{if(first){first=false;throw Error('transient connection failure')}return realFetch(...args)};
 await b.c.markVisibleChatRead();assert.equal(b.ack(),0);assert.equal(b.timers.length,1);
 await b.timers.shift().fn();assert.equal(b.ack(),128);assert.equal(b.calls.length,1);
 const d=setup();let finish;
 d.c.fetch=(url,options)=>{d.calls.push({url,options});return new Promise(resolve=>{finish=()=>resolve({ok:true,json:async()=>({ok:true,case_id:19,user_id:3,through_id:128})})})};
 const pending=d.c.markVisibleChatRead();await d.c.markVisibleChatRead();assert.equal(d.calls.length,1);
 d.c.lastMessageId=129;finish();await pending;assert.equal(d.ack(),128);assert.equal(d.queued.length,1);
 d.c.fetch=async(url,options)=>{d.calls.push({url,options});return {ok:true,json:async()=>({ok:true,case_id:19,user_id:3,through_id:129})}};
 await d.queued.shift()();assert.equal(d.ack(),129);assert.equal(d.calls.length,2);
 const e=setup();e.c.fetch=async()=>{throw Error('offline')};
 await e.c.markVisibleChatRead();for(let i=0;i<3;i++)await e.timers.shift().fn();
 assert.equal(e.timers.length,0);assert.equal(e.ack(),0);assert.equal(e.events.length,0);
 const f=setup();f.c.fetch=async()=>({ok:true,json:async()=>({ok:true,case_id:20,user_id:3,through_id:128})});
 await f.c.markVisibleChatRead();assert.equal(f.ack(),0);assert.equal(f.events.length,0);
 console.log('PASS: visible-only HTTP read without socket, confirmed dedup, retry bounds, keepalive and in-flight arrival');
})().catch(e=>{console.error(e);process.exit(1)});
