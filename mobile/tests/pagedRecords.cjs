const ts=require('typescript'),fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {test}=require('node:test');const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(fetchPage,replaceOnRefresh=false,ascending=true,cursorMode="id"){
 const states=[],refs=[],previous=[],callbacks=[],effects=[];let si=0,ri=0,ei=0,ci=0,scope='owner:course1',current;
 const same=(a,b)=>a&&a.length===b.length&&b.every((v,i)=>Object.is(v,a[i]));
 const react={useState:value=>{const i=si++;if(!(i in states))states[i]=value;return[states[i],v=>states[i]=typeof v==='function'?v(states[i]):v]},useRef:value=>{const i=ri++;return refs[i]??(refs[i]={current:value})},useCallback:(f,deps)=>{const i=ci++;if(!same(callbacks[i]?.deps,deps))callbacks[i]={f,deps};return callbacks[i].f},useEffect:(f,deps)=>{const i=ei++;if(!same(previous[i]?.deps,deps))effects.push(()=>{previous[i]?.cleanup?.();previous[i]={deps,cleanup:f()}})}};
 const exports={};const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/usePagedRecords.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 vm.runInNewContext(code,{exports,Error,require:()=>react});
 const render=()=>{si=ri=ei=ci=0;current=exports.usePagedRecords(scope,fetchPage,ascending,replaceOnRefresh,cursorMode);while(effects.length)effects.shift()();return current};
 return {render,get current(){return current},changeScope:s=>{scope=s;render()},unmount:()=>previous.forEach(e=>e.cleanup?.())};
}
const row=id=>({id,content:'answer-'+id});
test('mutable list refresh removes deleted or inaccessible rows and resets pagination',async()=>{
 let changed=false;const h=harness(async before=>before?{items:[row(1)],next_before:null}:changed?{items:[row(3)],next_before:3}:{items:[row(2),row(3)],next_before:2},true);
 h.render();await tick();h.render();await h.current.loadMore();h.render();assert.equal(h.current.items.length,3);
 changed=true;await h.current.refresh();h.render();assert.equal(h.current.items.map(x=>x.id).join(','),'3');assert.equal(h.current.hasMore,true);
});
test('older pages remain readable after realtime refresh; duplicates merge and double taps fetch once',async()=>{
 const calls=[];const h=harness(async before=>{calls.push(before);return before?{items:[row(1),row(2)],next_before:null}:{items:[row(3),row(4)],next_before:3}});
 h.render();await tick();h.render();assert.equal(h.current.hasMore,true);
 const first=h.current.loadMore();const duplicate=h.current.loadMore();await Promise.all([first,duplicate]);h.render();
 assert.equal(calls.length,2);assert.equal(h.current.items.map(x=>x.id).join(','),'1,2,3,4');
 await h.current.refresh();h.render();assert.equal(h.current.items.map(x=>x.id).join(','),'1,2,3,4');assert.equal(h.current.hasMore,false);
});
test('failed page preserves content and cursor, permits retry without data loss',async()=>{
 let fail=true;const h=harness(async before=>{if(before&&fail)throw Error('offline');return before?{items:[row(1)],next_before:null}:{items:[row(2)],next_before:2}});
 h.render();await tick();h.render();await h.current.loadMore();h.render();
 assert.equal(h.current.items[0].id,2);assert.equal(h.current.error,'offline');assert.equal(h.current.hasMore,true);
 fail=false;await h.current.loadMore();h.render();assert.equal(h.current.items.map(x=>x.id).join(','),'1,2');assert.equal(h.current.error,'');
});
test('course/account switch discards delayed old records; unmount rejects stale writes',async()=>{
 const pending=[];const h=harness(()=>new Promise(resolve=>pending.push(resolve)));h.render();h.changeScope('other:course2');
 pending[1]({items:[row(8)],next_before:null});await tick();h.render();pending[0]({items:[row(1)],next_before:null});await tick();h.render();assert.equal(h.current.items[0].id,8);
 const refresh=h.current.refresh();h.unmount();pending[2]({items:[row(9)],next_before:null});await refresh;h.render();assert.equal(h.current.items[0].id,8);
});

test('large reconnect burst resets cursor so intervening messages remain reachable',async()=>{
 let burst=false;const h=harness(async before=>before?{items:[row(1)],next_before:null}:burst?{items:[row(200),row(201)],next_before:200}:{items:[row(2),row(3)],next_before:2});
 h.render();await tick();h.render();await h.current.loadMore();h.render();assert.equal(h.current.hasMore,false);
 burst=true;await h.current.refresh();h.render();assert.equal(h.current.hasMore,true);assert.equal(h.current.items.map(x=>x.id).join(','),'1,2,3,200,201');
});


test('newest-first pagination appends older rows without replacing fresh records',async()=>{
 const h=harness(async before=>before?{items:[{id:8,content:'stale-8'},row(7)],next_before:null}:{items:[row(10),{id:8,content:'fresh-8'},row(9)],next_before:8},false,false);
 h.render();await tick();h.render();await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'10,8,9,7');
 assert.equal(h.current.items.find(x=>x.id===8).content,'fresh-8');
});

test('invalid ID cursor preserves verified rows and allows a corrected retry',async()=>{
 let calls=0,broken=true;
 const h=harness(async before=>{
  calls++;
  if(before===undefined)return {items:[row(4)],next_before:4};
  return broken?{items:[row(2)],next_before:4}:{items:[row(2)],next_before:null};
 },false,false);
 h.render();await tick();h.render();assert.equal(h.current.hasMore,true);
 await h.current.loadMore();h.render();
 assert.equal(h.current.hasMore,true);
 assert.match(h.current.error,/Geçersiz sayfalama imleci/);
 assert.equal(h.current.items.map(x=>x.id).join(','),'4');
 broken=false;await h.current.loadMore();h.render();
 assert.equal(h.current.hasMore,false);
 assert.equal(h.current.error,'');
 assert.equal(h.current.items.map(x=>x.id).join(','),'4,2');
 assert.equal(calls,3);
});

test('invalid initial cursors do not expose endless pagination after refresh',async()=>{
 for(const cursor of [NaN,Infinity,-1,6,7,1.5]){
  let calls=0;
  const h=harness(async()=>{calls++;return {items:[row(4),row(5)],next_before:cursor}},true,false);
  h.render();await tick();h.render();
  assert.equal(h.current.hasMore,false,'cursor '+cursor+' should be rejected');
  await h.current.loadMore();assert.equal(calls,1);
 }
});
test('valid initial cursor remains available for older pages',async()=>{
 const h=harness(async before=>before?{items:[row(1)],next_before:null}:{items:[row(4),row(5)],next_before:5},true,false);
 h.render();await tick();h.render();assert.equal(h.current.hasMore,true);
 await h.current.loadMore();h.render();assert.equal(h.current.items.map(x=>x.id).join(','),'1');
});

test('date-ordered cursor may increase in numeric ID across older pages',async()=>{
 const calls=[];
 const h=harness(async before=>{
  calls.push(before);
  if(before===undefined)return {items:[row(4),row(10)],next_before:10};
  if(before===10)return {items:[row(31),row(24)],next_before:24};
  return {items:[row(2)],next_before:null};
 },false,false);
 h.render();await tick();h.render();
 assert.equal(h.current.hasMore,true);
 await h.current.loadMore();h.render();
 assert.equal(h.current.hasMore,true);
 await h.current.loadMore();h.render();
 assert.deepEqual(calls,[undefined,10,24]);
 assert.equal(h.current.items.length,5);
});
test('repeated cursor cycle preserves verified records and permits corrected retry',async()=>{
 let broken=true;
 const h=harness(async before=>before===undefined?{items:[row(4)],next_before:4}:before===4?{items:[row(9)],next_before:9}:broken?{items:[row(3)],next_before:4}:{items:[row(3)],next_before:null},false,false);
 h.render();await tick();h.render();
 await h.current.loadMore();h.render();
 assert.equal(h.current.hasMore,true);
 await h.current.loadMore();h.render();
 assert.equal(h.current.hasMore,true);
 assert.match(h.current.error,/Geçersiz sayfalama döngüsü/);
 assert.equal(h.current.items.map(x=>x.id).join(','),'4,9');
 broken=false;
 await h.current.loadMore();h.render();
 assert.equal(h.current.hasMore,false);
 assert.equal(h.current.error,'');
 assert.equal(h.current.items.map(x=>x.id).join(','),'4,9,3');
});

test('offset pagination loads all patient pages even when offset is not a record ID',async()=>{
 const calls=[];
 const h=harness(async offset=>{
  calls.push(offset);
  if(offset===undefined)return {items:[row(901),row(902)],next_before:2};
  if(offset===2)return {items:[row(903),row(904)],next_before:4};
  return {items:[row(905)],next_before:null};
 },true,false,'offset');
 h.render();await tick();h.render();
 assert.equal(h.current.hasMore,true);
 await h.current.loadMore();h.render();
 assert.equal(h.current.hasMore,true);
 await h.current.loadMore();h.render();
 assert.equal(h.current.hasMore,false);
 assert.equal(h.current.items.map(x=>x.id).join(','),'901,902,903,904,905');
 assert.deepEqual(calls,[undefined,2,4]);
});
test('offset cursor cycles are rejected without corrupting patient rows',async()=>{
 const h=harness(async offset=>offset===undefined?{items:[row(30)],next_before:1}:{items:[row(29)],next_before:1},true,false,'offset');
 h.render();await tick();h.render();
 await h.current.loadMore();h.render();
 assert.equal(h.current.hasMore,true);
 assert.match(h.current.error,/Geçersiz sayfalama ilerlemesi/);
 assert.equal(h.current.items.map(x=>x.id).join(','),'30');
});

test('malformed refresh does not expose invalid patient rows',async()=>{
 const h=harness(async()=>({items:[null],next_before:1}),true,false,'offset');
 h.render();await tick();h.render();
 assert.equal(h.current.items.length,0);
 assert.match(h.current.error,/Geçersiz sayfa/);
 assert.equal(h.current.hasMore,false);
});
test('malformed next page preserves prior clinical records and permits retry',async()=>{
 let malformed=true;
 const h=harness(async offset=>offset===undefined?{items:[row(10)],next_before:1}:malformed?{items:[null],next_before:2}:{items:[row(9)],next_before:null},true,false,'offset');
 h.render();await tick();h.render();
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'10');
 assert.match(h.current.error,/Geçersiz sayfa/);
 assert.equal(h.current.hasMore,true);
 malformed=false;
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'10,9');
 assert.equal(h.current.hasMore,false);
});

test('duplicate patient IDs in a page are rejected before replacing existing clinical rows',async()=>{
 let invalid=false;
 const h=harness(async()=>invalid?{items:[row(9),row(9)],next_before:2}:{items:[row(4)],next_before:1},true,false,'offset');
 h.render();await tick();h.render();invalid=true;
 await h.current.refresh();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'4');
 assert.match(h.current.error,/Geçersiz sayfa/);
});
test('offset pagination rejects a backward cursor without losing prior patient records',async()=>{
 const h=harness(async offset=>offset===undefined?{items:[row(101),row(102)],next_before:2}:{items:[row(103)],next_before:1},true,false,'offset');
 h.render();await tick();h.render();
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'101,102');
 assert.match(h.current.error,/Geçersiz sayfalama ilerlemesi/);
});

test('stalled offset does not poison retry: corrected server page is accepted',async()=>{
 let stale=true;
 const h=harness(async offset=>offset===undefined
  ?{items:[row(101),row(102)],next_before:2}
  :stale?{items:[row(103)],next_before:2}:{items:[row(103)],next_before:null},
  true,false,'offset');
 h.render();await tick();h.render();
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'101,102');
 assert.equal(h.current.hasMore,true);
 assert.match(h.current.error,/Geçersiz sayfalama ilerlemesi/);
 stale=false;
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'101,102,103');
 assert.equal(h.current.hasMore,false);
 assert.equal(h.current.error,'');
});

test('old patient pagination response cannot overwrite a switched account',async()=>{
 let resolveOld;
 const h=harness(before=>before===1
  ?new Promise(resolve=>{resolveOld=resolve})
  :Promise.resolve({items:[row(11)],next_before:1}),true,false,'offset');
 h.render();await tick();h.render();
 const oldRequest=h.current.loadMore();
 h.changeScope('another-account');
 await tick();h.render();
 resolveOld({items:[row(99)],next_before:null});
 await oldRequest;h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'11');
 assert.equal(h.current.hasMore,true);
 assert.equal(h.current.error,'');
});

test('overlapping offset page cannot replace an existing patient and permits retry',async()=>{
 let overlapping=true;
 const h=harness(async offset=>offset===undefined
  ?{items:[{id:101,content:'verified-clinical-record'}],next_before:1}
  :overlapping?{items:[{id:101,content:'stale-record'},row(102)],next_before:3}
   :{items:[row(102)],next_before:null},true,false,'offset');
 h.render();await tick();h.render();
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.length,1);
 assert.equal(h.current.items[0].content,'verified-clinical-record');
 assert.match(h.current.error,/Tekrarlanan hasta sayfası/);
 assert.equal(h.current.hasMore,true);
 overlapping=false;
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'101,102');
 assert.equal(h.current.error,'');
});

test('malformed initial cursor reports error rather than silently hiding remaining patients',async()=>{
 const h=harness(async()=>({items:[row(1)],next_before:undefined}),true,false,'offset');
 h.render();await tick();h.render();
 assert.equal(h.current.items.length,0);
 assert.match(h.current.error,/Geçersiz sayfa/);
});
test('malformed next-page cursor retains existing patients and permits corrected retry',async()=>{
 let invalid=true;
 const h=harness(async offset=>offset===undefined
  ?{items:[row(10)],next_before:1}
  :invalid?{items:[row(11)],next_before:undefined}:{items:[row(11)],next_before:null},true,false,'offset');
 h.render();await tick();h.render();
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'10');
 assert.match(h.current.error,/Geçersiz sayfa/);
 assert.equal(h.current.hasMore,true);
 invalid=false;await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'10,11');
 assert.equal(h.current.error,'');
});


test('nonterminal empty offset page preserves patient records and allows retry',async()=>{
 let broken=true;
 const h=harness(async offset=>offset===undefined
  ?{items:[row(101)],next_before:1}
  :broken?{items:[],next_before:2}:{items:[row(102)],next_before:null},
  true,false,'offset');
 h.render();await tick();h.render();
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'101');
 assert.equal(h.current.hasMore,true);
 assert.match(h.current.error,/Geçersiz sayfalama imleci/);
 broken=false;await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'101,102');
 assert.equal(h.current.error,'');
});
test('invalid ID cursor on later page retains previous clinical data for retry',async()=>{
 let broken=true;
 const h=harness(async before=>before===undefined
  ?{items:[row(10)],next_before:10}
  :broken?{items:[row(9)],next_before:999}:{items:[row(9)],next_before:null},
  true,false,'id');
 h.render();await tick();h.render();
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'10');
 assert.equal(h.current.hasMore,true);
 assert.match(h.current.error,/Geçersiz sayfalama imleci/);
 broken=false;await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'10,9');
});


test('invalid first-page ID cursor preserves verified clinical rows and allows retry',async()=>{
 let malformed=false;
 const h=harness(async()=>malformed
  ?{items:[{id:90,content:'unverified'}],next_before:999}
  :{items:[{id:91,content:'verified'}],next_before:null},true,false,'id');
 h.render();await tick();h.render();
 assert.equal(h.current.items[0].content,'verified');
 malformed=true;await h.current.refresh();h.render();
 assert.equal(h.current.items[0].content,'verified');
 assert.match(h.current.error,/Geçersiz sayfalama imleci/);
 malformed=false;await h.current.refresh();h.render();
 assert.equal(h.current.error,'');
 assert.equal(h.current.items[0].content,'verified');
});


test('offset initial cursor cannot point inside already returned patient rows',async()=>{
 const h=harness(async()=>({items:[row(101),row(102),row(103)],next_before:2}),true,false,'offset');
 h.render();await tick();h.render();
 assert.equal(h.current.items.length,0);
 assert.match(h.current.error,/Geçersiz sayfalama imleci/);
});

test('offset next cursor cannot replay part of a newly received patient page',async()=>{
 let broken=true;
 const h=harness(async offset=>offset===undefined
  ?{items:[row(101),row(102)],next_before:2}
  :broken?{items:[row(103),row(104)],next_before:3}:{items:[row(103),row(104)],next_before:4},true,false,'offset');
 h.render();await tick();h.render();
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'101,102');
 assert.match(h.current.error,/Geçersiz sayfalama ilerlemesi/);
 assert.equal(h.current.hasMore,true);
 broken=false;await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'101,102,103,104');
 assert.equal(h.current.error,'');
});

test('offset cursor cannot skip unseen patient records; corrected retry succeeds',async()=>{
 let gap=true;
 const h=harness(async offset=>offset===undefined
  ?{items:[row(101),row(102)],next_before:2}
  :gap?{items:[row(103)],next_before:8}:{items:[row(103)],next_before:3},
  true,false,'offset');
 h.render();await tick();h.render();
 await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'101,102');
 assert.equal(h.current.hasMore,true);
 assert.match(h.current.error,/Geçersiz sayfalama ilerlemesi/);
 gap=false;await h.current.loadMore();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'101,102,103');
 assert.equal(h.current.error,'');
});

test('initial offset cannot skip unseen patients; corrected refresh can retry',async()=>{
 let broken=true;
 const h=harness(async()=>broken
  ?{items:[row(101),row(102)],next_before:7}
  :{items:[row(101),row(102)],next_before:2},true,false,'offset');
 h.render();await tick();h.render();
 assert.equal(h.current.items.length,0);
 assert.equal(h.current.hasMore,false);
 assert.match(h.current.error,/Geçersiz sayfalama imleci/);
 broken=false;
 await h.current.refresh();h.render();
 assert.equal(h.current.items.map(x=>x.id).join(','),'101,102');
 assert.equal(h.current.hasMore,true);
 assert.equal(h.current.error,'');
});
