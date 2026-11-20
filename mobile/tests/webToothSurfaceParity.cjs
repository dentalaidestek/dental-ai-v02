const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');

require.extensions['.ts']=(module,filename)=>module._compile(
 ts.transpileModule(fs.readFileSync(filename,'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
 }).outputText,
 filename
);

const webOptions=require('../../static/tooth-chart/surface-options.js');
const {toothSurfaceOptionsForTooth}=require('../src/toothSurfaceOptions.ts');
const web=fs.readFileSync(require.resolve('../../app/templates/tooth_chart.html'),'utf8');
const codes=number=>toothSurfaceOptionsForTooth(number).map(([code])=>code);

test('web and native charts expose the same anatomical FDI surface contract',()=>{
 for(const number of ['11','23','31','43','51','63','71','83','14','18','24','48','54','55','64','85']){
  assert.deepEqual(webOptions(number),codes(number),number);
 }
});

test('anterior teeth expose INCISAL and never OCCLUSAL',()=>{
 for(const number of ['11','13','21','23','31','43','51','53','61','83']){
  const options=webOptions(number);
  assert.equal(options[0],'INCISAL',number);
  assert.ok(!options.includes('OCCLUSAL'),number);
 }
});

test('posterior teeth expose OCCLUSAL and never INCISAL',()=>{
 for(const number of ['14','18','24','28','34','48','54','55','64','85']){
  const options=webOptions(number);
  assert.equal(options[0],'OCCLUSAL',number);
  assert.ok(!options.includes('INCISAL'),number);
 }
});

test('invalid and incomplete FDI values expose no writable surfaces',()=>{
 for(const value of ['', '9', '19', '49', '56', '89', 'abc', 11, null, undefined]){
  assert.deepEqual(webOptions(value),[]);
 }
});

test('web chart loads the shared contract and builds safe tooth-specific controls',()=>{
 const helper=web.indexOf('<script src="/static/tooth-chart/surface-options.js"></script>');
 const inline=web.indexOf('<script>\nconst TOOTH_NOTES=');
 assert.ok(helper>=0&&inline>helper,'surface contract must load before chart initialization');
 assert.match(web,/function renderSurfaceOptions\(number\)/);
 assert.match(web,/renderSurfaceOptions\(number\);setSurface\(""\)/);
 assert.match(web,/pin\.dataset\.pin=first/);
 assert.match(web,/pin\.textContent=first==="INCISAL"\?"İ":"O"/);
 assert.match(web,/button\.addEventListener\("click",function\(\)\{setSurface\(code\)\}\)/);
 assert.match(web,/\.preview-tooth\[data-surface="INCISAL"\] \.status-mark/);
 assert.doesNotMatch(web,/<button[^>]+data-surface=/);
 assert.doesNotMatch(web,/grid\.innerHTML\s*=/);
});
