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
