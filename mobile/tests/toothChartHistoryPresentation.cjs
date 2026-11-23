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

const {
 toothChartHistorySurfaceLabel,
 toothChartHistoryStatusLabel,
}=require('../src/toothChartHistoryPresentation.ts');

test('native tooth history localizes every supported FDI surface and clinical status',()=>{
 const surfaces={
  OCCLUSAL:'Oklüzal',INCISAL:'İnsizal',MESIAL:'Mesial',DISTAL:'Distal',
  BUCCAL:'Bukkal / Vestibül',LINGUAL:'Lingual / Palatinal',
 };
 const statuses={
  HEALTHY:'Sağlıklı',CARIES:'Çürük',FILLING:'Dolgu',CROWN:'Kron',
  ROOT_CANAL:'Kanal Tedavisi',EXTRACTED:'Çekilmiş',IMPLANT:'İmplant',OTHER:'Diğer',
 };
 for(const [code,label] of Object.entries(surfaces))assert.equal(toothChartHistorySurfaceLabel(code),label);
 for(const [code,label] of Object.entries(statuses))assert.equal(toothChartHistoryStatusLabel(code),label);
});

test('unknown future clinical codes remain visible instead of disappearing',()=>{
 assert.equal(toothChartHistorySurfaceLabel('FUTURE_SURFACE'),'FUTURE_SURFACE');
 assert.equal(toothChartHistoryStatusLabel('FUTURE_STATUS'),'FUTURE_STATUS');
});

test('native selected-tooth history preserves the three web history sources',()=>{
 const web=fs.readFileSync(require.resolve('../../app/templates/tooth_chart.html'),'utf8');
 const native=fs.readFileSync(require.resolve('../src/NativeToothChart.tsx'),'utf8');
 assert.ok(web.includes('(data.surface_statuses||[])'));
 assert.ok(web.includes('(data.treatments||[])'));
 assert.ok(web.includes('(data.analyses||[])'));
 assert.ok(native.includes('toothChartHistorySurfaceLabel(item.surface)'));
 assert.ok(native.includes('toothChartHistoryStatusLabel(item.status)'));
 assert.ok(native.includes('<NativePatientHistory'));
 assert.ok(native.includes('toothNumber={selected}'));
 assert.ok(native.includes('getToothTreatments(token,patientId,selected'));
 assert.ok(native.includes('next_cursor'));
});
