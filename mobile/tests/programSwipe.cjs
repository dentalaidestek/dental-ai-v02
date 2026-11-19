const {test}=require('node:test');
const assert=require('node:assert/strict');
const ts=require('typescript');

require.extensions['.ts']=(module,filename)=>{
  const source=require('node:fs').readFileSync(filename,'utf8');
  module._compile(ts.transpileModule(source,{compilerOptions:{
    module:ts.ModuleKind.CommonJS,
    target:ts.ScriptTarget.ES2020
  }}).outputText,filename);
};

const {programSwipeDirection}=require('../src/programSwipe.ts');

test('Program swipe follows the web page direction and threshold',()=>{
  assert.equal(programSwipeDirection(-65,0),1);
  assert.equal(programSwipeDirection(-120,20),1);
  assert.equal(programSwipeDirection(65,0),-1);
  assert.equal(programSwipeDirection(120,20),-1);
});

test('Program swipe ignores short, vertical and invalid gestures',()=>{
  assert.equal(programSwipeDirection(-64.9,0),0);
  assert.equal(programSwipeDirection(100,80),0);
  assert.equal(programSwipeDirection(0,120),0);
  assert.equal(programSwipeDirection(Number.NaN,0),0);
  assert.equal(programSwipeDirection(100,Number.POSITIVE_INFINITY),0);
});
