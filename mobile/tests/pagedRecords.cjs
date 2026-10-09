const ts=require('typescript'),fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {test}=require('node:test');const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(fetchPage){
 const states=[],refs=[],previous=[],callbacks=[],effects=[];let si=0,ri=0,ei=0,ci=0,scope='owner:course1',current;
 const same=(a,b)=>a&&a.length===b.length&&b.every((v,i)=>Object.is(v,a[i]));
 const react={useState:value=>{const i=si++;if(!(i in states))states[i]=value;return[states[i],v=>states[i]=typeof v==='function'?v(states[i]):v]},useRef:value=>{const i=ri++;return refs[i]??(refs[i]={current:value})},useCallback:(f,deps)=>{const i=ci++;if(!same(callbacks[i]?.deps,deps))callbacks[i]={f,deps};return callbacks[i].f},useEffect:(f,deps)=>{const i=ei++;if(!same(previous[i]?.deps,deps))effects.push(()=>{previous[i]?.cleanup?.();previous[i]={deps,cleanup:f()}})}};
 const exports={};const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/usePagedRecords.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 vm.runInNewContext(code,{exports,Error,require:()=>react});
 const render=()=>{si=ri=ei=ci=0;current=exports.usePagedRecords(scope,fetchPage,true);while(effects.length)effects.shift()();return current};
 return {render,get current(){return current},changeScope:s=>{scope=s;render()},unmount:()=>previous.forEach(e=>e.cleanup?.())};
}
const row=id=>({id,content:'answer-'+id});
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
