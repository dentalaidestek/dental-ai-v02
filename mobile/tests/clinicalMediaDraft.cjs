const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');

require.extensions['.ts']=(module,filename)=>{
 const source=fs.readFileSync(filename,'utf8');
 const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 module._compile(output,filename);
};

const {clearClinicalMediaDraft}=require('../src/clinicalMediaDraft.ts');

test('encrypted vault cleanup starts only after the durable pending intent is deleted',async()=>{
 let intentExists=true;
 let vaultFileExists=true;
 const order=[];
 await clearClinicalMediaDraft(
  async()=>{order.push('intent');intentExists=false;},
  async()=>{order.push('vault');assert.equal(intentExists,false);vaultFileExists=false;}
 );
 assert.deepEqual(order,['intent','vault']);
 assert.equal(intentExists,false);
 assert.equal(vaultFileExists,false);
});

test('a failed durable intent deletion preserves encrypted files and never runs cleanup',async()=>{
 let cleanupCalled=false;
 let vaultFileExists=true;
 await assert.rejects(()=>clearClinicalMediaDraft(
  async()=>{throw Error('SecureStore unavailable');},
  async()=>{cleanupCalled=true;vaultFileExists=false;}
 ),/SecureStore unavailable/);
 assert.equal(cleanupCalled,false);
 assert.equal(vaultFileExists,true);
});

test('orphan cleanup failure cannot resurrect a successfully cleared intent',async()=>{
 let intentExists=true;
 await clearClinicalMediaDraft(
  async()=>{intentExists=false;},
  async()=>{assert.equal(intentExists,false);throw Error('directory listing unavailable');}
 );
 assert.equal(intentExists,false);
});

test('native gallery uses durable-intent-first cleanup for explicit draft clearing',()=>{
 const source=fs.readFileSync(require.resolve('../src/NativePatientMedia.tsx'),'utf8');
 assert.match(source,/clearClinicalMediaDraft\(/);
 assert.match(source,/\(\)=>uploadStore\.deleteItemAsync\(uploadKey\)/);
 assert.match(source,/\(\)=>cleanupOrphanedClinicalMediaVaultFiles\(userId,patientId,\[\]\)/);
});
