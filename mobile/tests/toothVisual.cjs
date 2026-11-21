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
  assert.match(source,/SvgImage\s+href=\{atlas\}/);
  assert.match(source,/x=\{-model\.column\*60\}/);
  assert.doesNotMatch(source,/primarySvg|primary-enamel/);
});

test('native tooth rows use the web mobile permanent and primary visual dimensions',()=>{
  const chart=fs.readFileSync(require.resolve('../src/NativeToothChart.tsx'),'utf8');
  const web=fs.readFileSync(require.resolve('../../app/templates/tooth_chart.html'),'utf8');
  assert.match(web,/\.tooth-visual\{height:64px/);
  assert.match(web,/\.primary-row \.tooth-visual\{height:70px/);
  assert.match(chart,/visualHeight=primary\?70:64/);
  assert.match(chart,/height:visualHeight\+16/);
  assert.equal((chart.match(/height:visualHeight,borderRadius:7/g)||[]).length,2);
  assert.equal((chart.match(/NativeToothVisual number=\{n\} status=\{st\} height=\{58\}/g)||[]).length,2);
  assert.doesNotMatch(chart,/NativeToothVisual number=\{n\} status=\{st\} height=\{37\}/);
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
  const values=EXTRACTED_TOOTH_FILTER_MATRIX.trim().split(/\s+/).map(Number);
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


const vm=require('node:vm');
const React=require('react');
const renderer=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;

function nativeToothVisual(){
  const source=fs.readFileSync(require.resolve('../src/NativeToothVisual.tsx'),'utf8');
  const code=ts.transpileModule(source,{
    compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020,esModuleInterop:true}
  }).outputText;
  const exports={};
  const svg={
    __esModule:true,
    default:'Svg',
    ClipPath:'ClipPath',
    Defs:'Defs',
    FeColorMatrix:'FeColorMatrix',
    Filter:'Filter',
    G:'G',
    Image:'SvgImage',
    LinearGradient:'LinearGradient',
    Path:'Path',
    Rect:'Rect',
    Stop:'Stop',
    SvgXml:'SvgXml'
  };
  vm.runInNewContext(code,{exports,require:name=>{
    if(name==='react')return {...React,default:React};
    if(name==='react-native')return {View:'View'};
    if(name==='react-native-svg')return svg;
    if(name==='./api')return {};
    if(name==='./toothVisual')return require('../src/toothVisual.ts');
    if(name==='../assets/enamel-atlas-v2.webp')return 1;
    throw Error('unexpected import '+name);
  }});
  return exports.default;
}

test('extracted native tooth applies the web grayscale filter to its atlas and status overlay',async()=>{
  const Visual=nativeToothVisual();
  let tree;
  await renderer.act(async()=>{tree=renderer.create(React.createElement(Visual,{number:'11',status:'EXTRACTED',height:82}))});
  const filter=tree.root.findByType('Filter');
  const matrix=tree.root.findByType('FeColorMatrix');
  const group=tree.root.findByType('G');
  const atlasImage=tree.root.findByType('SvgImage');
  assert.equal(filter.props.id,EXTRACTED_TOOTH_FILTER_ID);
  assert.equal(matrix.props.type,'matrix');
  assert.equal(matrix.props.values,EXTRACTED_TOOTH_FILTER_MATRIX);
  assert.equal(group.props.filter,EXTRACTED_TOOTH_FILTER_URL);
  assert.equal(atlasImage.props.href,1);
  assert.equal(atlasImage.props.clipPath,'url(#tooth-atlas-clip)');
  assert.ok(tree.root.findAllByType('Path').some(path=>path.props.d==='M20 35l20 24M40 35L20 59'));
  await renderer.act(async()=>tree.unmount());
});

test('healthy and carious teeth stay colored while implant keeps its canonical SVG',async()=>{
  const Visual=nativeToothVisual();
  let healthy,caries,implant;
  await renderer.act(async()=>{healthy=renderer.create(React.createElement(Visual,{number:'16',status:'HEALTHY'}))});
  assert.equal(healthy.root.findAllByType('Filter').length,0);
  assert.equal(healthy.root.findByType('G').props.filter,undefined);
  await renderer.act(async()=>healthy.unmount());
  await renderer.act(async()=>{caries=renderer.create(React.createElement(Visual,{number:'16',status:'CARIES'}))});
  assert.equal(caries.root.findAllByType('Filter').length,0);
  assert.equal(caries.root.findByType('G').props.filter,undefined);
  await renderer.act(async()=>caries.unmount());
  await renderer.act(async()=>{implant=renderer.create(React.createElement(Visual,{number:'36',status:'IMPLANT'}))});
  assert.equal(implant.root.findAllByType('SvgXml').length,1);
  assert.equal(implant.root.findAllByType('SvgImage').length,0);
  assert.equal(implant.root.findAllByType('Filter').length,0);
  await renderer.act(async()=>implant.unmount());
});
