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

const {toothVisualModel}=require('../src/toothVisual.ts');

test('permanent FDI teeth use the same four enamel-atlas columns as the web chart',()=>{
  assert.equal(toothVisualModel('16').column,0,'molar');
  assert.equal(toothVisualModel('14').column,1,'premolar');
  assert.equal(toothVisualModel('13').column,2,'canine');
  assert.equal(toothVisualModel('11').column,3,'incisor');
});

test('primary FDI teeth use the web atlas columns rather than a separate SVG palette',()=>{
  assert.equal(toothVisualModel('55').column,0,'primary molar');
  assert.equal(toothVisualModel('53').column,2,'primary canine');
  assert.equal(toothVisualModel('51').column,3,'primary incisor');
  assert.equal(toothVisualModel('85').column,0,'lower primary molar');
});

test('lower quadrants rotate the visual while upper quadrants remain upright',()=>{
  for(const number of ['31','41','71','81'])assert.equal(toothVisualModel(number).lower,true,number);
  for(const number of ['11','21','51','61'])assert.equal(toothVisualModel(number).lower,false,number);
});

test('native renderer uses the shared atlas for primary and permanent teeth',()=>{
  const source=fs.readFileSync(require.resolve('../src/NativeToothVisual.tsx'),'utf8');
  assert.match(source,/Image source=\{atlas\}/);
  assert.match(source,/left:-model\.column\*width/);
  assert.doesNotMatch(source,/primarySvg|primary-enamel/);
});

test('invalid FDI positions are rejected before rendering',()=>{
  for(const number of ['19','29','39','49','56','66','76','86','99','1','']) {
    assert.throws(()=>toothVisualModel(number),/Geçersiz FDI/);
  }
});


const {
  EXTRACTED_TOOTH_FILTER_ID,
  EXTRACTED_TOOTH_FILTER_URL,
  EXTRACTED_TOOTH_FILTER_MATRIX,
  toothVisualFilter
}=require('../src/toothVisual.ts');

test('extracted tooth uses the web grayscale and 70 percent brightness contract',()=>{
  assert.equal(EXTRACTED_TOOTH_FILTER_ID,'tooth-extracted-grayscale');
  assert.equal(toothVisualFilter('EXTRACTED'),EXTRACTED_TOOTH_FILTER_URL);
  assert.equal(toothVisualFilter('HEALTHY'),undefined);
  assert.equal(toothVisualFilter('CARIES'),undefined);
  const values=EXTRACTED_TOOTH_FILTER_MATRIX.trim().split(/\\s+/).map(Number);
  assert.equal(values.length,20);
  assert.ok(values.every(Number.isFinite));
  const luminance=values[0]+values[1]+values[2];
  assert.ok(Math.abs(luminance-0.7)<1e-9,'grayscale output must retain 70% brightness');
  assert.deepEqual(values.slice(0,5),values.slice(5,10));
  assert.deepEqual(values.slice(0,5),values.slice(10,15));
  assert.deepEqual(values.slice(15,20),[0,0,0,1,0],'alpha must remain unchanged');
  const web=fs.readFileSync(require.resolve('../../app/templates/tooth_chart.html'),'utf8');
  assert.ok(web.includes('filter:grayscale(1) brightness(.7)'),'web CSS remains the visual source of truth');
});
