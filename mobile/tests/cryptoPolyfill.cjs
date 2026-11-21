const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const load=(sandbox)=>{
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/cryptoPolyfill.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 vm.runInNewContext(code,sandbox);
};
const fakeExpo=fills=>({getRandomValues:a=>{if(typeof a!=='object'||a===null||typeof a.length!=='number')throw new TypeError('typed array required');fills.push(a.slice());a.fill(7);return a},randomUUID:()=>'0f3a9c1e-77aa-4c2e-9f01-b2d6e4a8c555'});
const sandboxFor=(fills,extra={})=>({require:name=>name==='expo-crypto'?fakeExpo(fills):undefined,console,exports:{},...extra});
test('crypto polyfill installs expo-backed getRandomValues and randomUUID on a bare global',()=>{
 const fills=[];const sandbox=sandboxFor(fills);
 load(sandbox);
 assert.equal(typeof sandbox.crypto.getRandomValues,'function');
 const buf=new Uint8Array(4);const out=sandbox.crypto.getRandomValues(buf);
 assert.equal(out,buf);assert.deepEqual([...buf],[7,7,7,7]);assert.equal(fills.length,1);
 assert.equal(sandbox.crypto.randomUUID(),'0f3a9c1e-77aa-4c2e-9f01-b2d6e4a8c555');
});
test('crypto polyfill is idempotent and never replaces an existing implementation',()=>{
 const fills=[];const sandbox=sandboxFor(fills);
 const native=a=>{a.fill(9);return a};
 sandbox.crypto={getRandomValues:native,randomUUID:()=>'native-uuid'};
 load(sandbox);
 const buf=new Uint8Array(2);sandbox.crypto.getRandomValues(buf);
 assert.deepEqual([...buf],[9,9]);assert.equal(sandbox.crypto.randomUUID(),'native-uuid');assert.equal(fills.length,0);
});
test('crypto polyfill creates the crypto namespace when missing and matches noble requirements',()=>{
 const fills=[];const sandbox=sandboxFor(fills);
 load(sandbox);
 // @noble/hashes utils requires exactly crypto.getRandomValues before first use.
 assert.equal(typeof sandbox.crypto.getRandomValues,'function');
 assert.equal(typeof sandbox.crypto.randomUUID,'function');
});
