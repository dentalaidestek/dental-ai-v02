const ts=require('typescript'),fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
test('foreground resume revalidates the active token and cleanup detaches the old account',async()=>{
 const effects=[],requests=[];let listener,cleanup;
 const react={useEffect:fn=>effects.push(fn)};
 const exports={};
 const filename=require('node:path').join(__dirname,'../src/useSessionHealth.ts');
 const source=fs.existsSync(filename)?fs.readFileSync(filename,'utf8'):'';
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,require:name=>name==='react'?react:name==='react-native'?{AppState:{addEventListener:(_event,fn)=>{listener=fn;return{remove:()=>{listener=null}}}}}:{revalidateSession:async token=>requests.push(token)}});
 assert.equal(typeof exports.useSessionHealth,'function');
 const mount=token=>{exports.useSessionHealth(token);cleanup=effects.shift()()};
 mount('first');listener('background');assert.deepEqual(requests,[]);listener('active');assert.deepEqual(requests,['first']);
 cleanup();assert.equal(listener,null);mount('second');listener('active');assert.deepEqual(requests,['first','second']);cleanup();
 mount(undefined);assert.equal(listener,null);
});
