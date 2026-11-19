const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const source=fs.readFileSync(require.resolve('../src/voiceDraftScope.ts'),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const moduleExports={};
vm.runInNewContext(code,{exports:moduleExports});
const {isVoiceDraftScopeCurrent}=moduleExports;

test('voice draft scope accepts only the active owner-patient key',()=>{
 assert.equal(isVoiceDraftScopeCurrent('dai.voice.1.8','dai.voice.1.8'),true);
 assert.equal(isVoiceDraftScopeCurrent('dai.voice.1.8','dai.voice.2.8'),false);
 assert.equal(isVoiceDraftScopeCurrent('dai.voice.1.8','dai.voice.1.9'),false);
 assert.equal(isVoiceDraftScopeCurrent('',''),false);
 assert.equal(isVoiceDraftScopeCurrent('dai.voice.1.8',''),false);
});
