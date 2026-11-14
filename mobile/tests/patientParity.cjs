const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict'),{test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,f);
test('patient history rejects another patient or tooth even if the server ignores its filter',async()=>{
 const api=require('../src/modernApi.ts'),original=global.fetch;
 try{
  global.fetch=async url=>{assert.match(url,/patient_id=8/);assert.match(url,/tooth_number=36/);return new Response(JSON.stringify({items:[{id:9,patient_id:7,status:'FINAL',tooth_number:'36'}],total:1}),{status:200})};
  await assert.rejects(()=>api.getAnalysisHistory('test',undefined,8,'36'),/geçersiz liste/);
  global.fetch=async()=>new Response(JSON.stringify({items:[{id:9,patient_id:8,status:'FINAL',tooth_number:'35'}],total:1}),{status:200});
  await assert.rejects(()=>api.getAnalysisHistory('test',undefined,8,'36'),/geçersiz liste/);
 }finally{global.fetch=original}
});
test('calendar preserves local dates and validates leap years',()=>{
 const {calendarDays,parseClinicalDate,clinicalDate}=require('../src/clinicalDate.ts');
 assert.equal(parseClinicalDate('2025-02-29'),null);
 assert.equal(clinicalDate(2024,1,29),'2024-02-29');
 assert.equal(calendarDays(2024,1).filter(Boolean).length,29);
 assert.equal(calendarDays(2026,10)[6],1); // Sunday, Monday-first grid
 assert.equal(parseClinicalDate('2026-13-01'),null);
});
test('primary molars and lower quadrants use the same atlas mapping as the web chart',()=>{
 const {toothVisualModel}=require('../src/toothVisual.ts');
 for(const tooth of ['54','55','64','65','74','75','84','85'])assert.equal(toothVisualModel(tooth).column,0);
 assert.equal(toothVisualModel('14').column,1);assert.equal(toothVisualModel('11').column,3);
 for(const tooth of ['31','41','71','81'])assert.equal(toothVisualModel(tooth).lower,true);
 for(const tooth of ['19','56','89'])assert.throws(()=>toothVisualModel(tooth),/FDI/);
});
test('native chart status overlays use the web crown, canal and extraction paths',()=>{
 const vm=require('node:vm'),exports={},React={default:null,useState:()=>[24,()=>{}],createElement:(type,props,...children)=>({type,props,children})};React.default=React;
 const native={View:'View',Image:'Image'},svg=Object.fromEntries(['Defs','LinearGradient','Path','Stop','SvgXml'].map(key=>[key,key]));svg.default='Svg';
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/NativeToothVisual.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,require:name=>name==='react'?React:name==='react-native'?native:name==='react-native-svg'?svg:name==='./toothVisual'?require('../src/toothVisual.ts'):1});
 const web=fs.readFileSync(require.resolve('../../app/templates/tooth_chart.html'),'utf8');
 function paths(node){return !node||typeof node!=='object'?[]:[...(node.type==='Path'?[node.props.d]:[]),...(node.children||[]).flat(Infinity).flatMap(paths)]}
 for(const [status,className] of [['CROWN','tooth-crown-zone'],['ROOT_CANAL','tooth-canal-lines'],['EXTRACTED','tooth-x']]){
  const expected=web.match(new RegExp(`class="${className}" d="([^"]+)"`))[1];
  assert.ok(paths(exports.default({number:'36',status})).includes(expected),status);
 }
 assert.equal(paths(exports.default({number:'36',status:'HEALTHY'})).length,0);
});
