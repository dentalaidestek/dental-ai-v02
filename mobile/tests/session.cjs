const ts = require('typescript');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {test} = require('node:test');
require.extensions['.ts'] = (module, filename) => {
 const source = fs.readFileSync(filename, 'utf8');
 const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}});
 module._compile(compiled.outputText, filename);
};
const {ApiError, getMe} = require('../src/api.ts');
const {restoreStoredSession} = require('../src/session.ts');

for (const [name,error,shouldDelete] of [
 ['offline',new TypeError('Network request failed'),false],
 ['server failure',new ApiError(503,'Unavailable'),false],
 ['forbidden',new ApiError(403,'Forbidden'),false],
 ['rate limit',new ApiError(429,'Retry later'),false],
 ['invalid session',new ApiError(401,'Unauthorized'),true],
]) {
 test(`session restore: ${name}`,async()=>{
  const deleted=[];
  const store={getItemAsync:async()=> 'stored-token',deleteItemAsync:async key=>{deleted.push(key)}};
  const action=()=>restoreStoredSession(store,async()=>{throw error});
  if(shouldDelete)assert.equal(await action(),null);
  else await assert.rejects(action,error);
  assert.deepEqual(deleted,shouldDelete?['dentalai_token']:[]);
 });
}
test('successful restore keeps token and returns validated user',async()=>{
 const user={id:7};
 const store={getItemAsync:async()=> 'stored-token',deleteItemAsync:async()=>{assert.fail('must not delete')}};
 assert.deepEqual(await restoreStoredSession(store,async token=>{assert.equal(token,'stored-token');return {user}}),{token:'stored-token',user});
});
test('API error retains HTTP status for session policy',async()=>{
 const original=global.fetch;
 try{
  global.fetch=async()=>new Response(JSON.stringify({detail:'Unauthorized'}),{status:401});
  await assert.rejects(()=>getMe('stored-token'),error=>error instanceof ApiError&&error.status===401);
 }finally{global.fetch=original;}
});
