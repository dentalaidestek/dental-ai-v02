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
const {toothChartSurfaceForTooth,toothChartSurfaceSelection}=require('../src/toothChartSurfaceSelection.ts');
const native=fs.readFileSync(require.resolve('../src/NativeToothChart.tsx'),'utf8');
const web=fs.readFileSync(require.resolve('../../app/templates/tooth_chart.html'),'utf8');
const codes=number=>toothSurfaceOptionsForTooth(number).map(([code])=>code);
const allFdiToothNumbers=[..."1234"].flatMap(quadrant=>[..."12345678"].map(unit=>quadrant+unit)).concat([..."5678"].flatMap(quadrant=>[..."12345"].map(unit=>quadrant+unit)));

test('web and native charts expose the same anatomical FDI surface contract for all 52 teeth',()=>{
 assert.equal(allFdiToothNumbers.length,52);
 for(const number of allFdiToothNumbers)assert.deepEqual(webOptions(number),codes(number),number);
});

test('every anterior permanent and primary tooth exposes INCISAL and never OCCLUSAL',()=>{
 for(const number of allFdiToothNumbers.filter(value=>Number(value[1])<=3)){
  const options=webOptions(number);
  assert.equal(options[0],'INCISAL',number);
  assert.ok(!options.includes('OCCLUSAL'),number);
 }
});

test('every posterior permanent and primary tooth exposes OCCLUSAL and never INCISAL',()=>{
 for(const number of allFdiToothNumbers.filter(value=>Number(value[1])>=4)){
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


test('native preview maps the fixed web occlusal pin to INCISAL for anterior FDI teeth',()=>{
 for(const number of ['11','13','21','23','31','43','51','53','61','83'])assert.equal(toothChartSurfaceForTooth(number,'OCCLUSAL'),'INCISAL',number);
 for(const number of ['14','18','24','28','34','48','54','55','64','85'])assert.equal(toothChartSurfaceForTooth(number,'OCCLUSAL'),'OCCLUSAL',number);
 assert.equal(toothChartSurfaceForTooth('14','INCISAL'),null);
 assert.equal(toothChartSurfaceForTooth('56','OCCLUSAL'),null);
});

test('native surface selection matches web setSurface: same tap stays selected and new tap replaces it',()=>{
 assert.deepEqual(toothChartSurfaceSelection('MESIAL'),['MESIAL']);
 assert.deepEqual(toothChartSurfaceSelection('MESIAL'),['MESIAL']);
 assert.deepEqual(toothChartSurfaceSelection('BUCCAL'),['BUCCAL']);
});

test('native map pins clear the independent editor and show its active surface without stale highlights',()=>{
 assert.match(native,/const chosen=surfaceEditor\?surfaceEditor===actualCode:surfaces\.includes\(actualCode\)/);
 assert.match(native,/setSurfaceEditor\(null\);setSurfaces\(toothChartSurfaceSelection\(actualCode\)\)/);
 assert.match(native,/setSurfaceEditor\(null\);setSurfaces\(toothChartSurfaceSelection\(v\)\)/);
});
