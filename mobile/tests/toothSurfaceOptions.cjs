const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);

const {toothSurfaceOptionsForTooth}=require('../src/toothSurfaceOptions.ts');
const codes=number=>toothSurfaceOptionsForTooth(number).map(([code])=>code);

test('permanent anterior FDI teeth expose incisal, never occlusal',()=>{
 assert.deepEqual(codes('11'),['INCISAL','MESIAL','DISTAL','BUCCAL','LINGUAL']);
 assert.deepEqual(codes('23'),['INCISAL','MESIAL','DISTAL','BUCCAL','LINGUAL']);
});

test('permanent posterior FDI teeth expose occlusal, never incisal',()=>{
 assert.deepEqual(codes('14'),['OCCLUSAL','MESIAL','DISTAL','BUCCAL','LINGUAL']);
 assert.deepEqual(codes('48'),['OCCLUSAL','MESIAL','DISTAL','BUCCAL','LINGUAL']);
});

test('primary anterior and posterior teeth use the correct surface',()=>{
 assert.deepEqual(codes('51'),['INCISAL','MESIAL','DISTAL','BUCCAL','LINGUAL']);
 assert.deepEqual(codes('83'),['INCISAL','MESIAL','DISTAL','BUCCAL','LINGUAL']);
 assert.deepEqual(codes('55'),['OCCLUSAL','MESIAL','DISTAL','BUCCAL','LINGUAL']);
 assert.deepEqual(codes('85'),['OCCLUSAL','MESIAL','DISTAL','BUCCAL','LINGUAL']);
});

test('invalid or incomplete FDI numbers expose no writable surface options',()=>{
 for(const value of ['', '9', '19', '49', '56', '89', 'abc']) assert.deepEqual(codes(value),[]);
});

test('native chart uses the same tooth-scoped options for selection, editing and pin labels',()=>{
 const chart=fs.readFileSync(require.resolve('../src/NativeToothChart.tsx'),'utf8');
 assert.match(chart,/toothSurfaceOptionsForTooth\(selected\)/);
 assert.equal((chart.match(/surfaceOptions\.map\(/g)||[]).length,2);
 assert.ok(chart.includes('surfaceOptions.find(x=>x[0]===surfaceEditor)?.[1]'));
 assert.ok(chart.includes('surfaceOptions.find(x=>x[0]===actualCode)?.[1]'));
 assert.doesNotMatch(chart,/const SURFACES:/);
});
