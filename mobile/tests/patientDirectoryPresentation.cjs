const ts=require('typescript'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);

const {normalizePatientDirectorySearch,patientDirectoryDetails,patientDirectoryAgeLabel}=require('../src/patientDirectoryPresentation.ts');

test('patient directory search trims and collapses whitespace without changing Turkish characters',()=>{
 assert.equal(normalizePatientDirectorySearch('  İpek   Çetin\n  12345678901  '),'İpek Çetin 12345678901');
 assert.equal(normalizePatientDirectorySearch('   '),'');
});

test('patient directory rows show both web directory identifiers without exposing TCKN',()=>{
 assert.deepEqual(patientDirectoryDetails({anonymous_id:' PAT-123 ',phone:' 05551234567 '}),[
  'Hasta No: PAT-123','Telefon: 05551234567'
 ]);
 assert.deepEqual(patientDirectoryDetails({anonymous_id:null,phone:null}),[
  'Hasta No: -','Telefon: -'
 ]);
});

test('patient directory age label preserves a valid zero age',()=>{
 assert.equal(patientDirectoryAgeLabel(0),'0 yaş');
 assert.equal(patientDirectoryAgeLabel(null),'Hasta kaydı');
 assert.equal(patientDirectoryAgeLabel(undefined),'Hasta kaydı');
});

test('patient API sends a normalized Turkish query with bearer-only credentials',async()=>{
 const {getPatients}=require('../src/api.ts'),original=global.fetch,calls=[];
 global.fetch=async(url,init)=>{
  calls.push({url:String(url),init});
  return {ok:true,status:200,text:async()=>JSON.stringify({items:[],total:0})};
 };
 try{
  await getPatients('synthetic-token','  İpek   12345678901  ');
  assert.match(calls[0].url,/q=%C4%B0pek%2012345678901$/);
  assert.equal(calls[0].init.credentials,'omit');
  assert.equal(calls[0].init.headers.Authorization,'Bearer synthetic-token');
 }finally{global.fetch=original}
});

test('native directory is wired to bounded server search, automatic paging and explicit empty state',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../App.tsx'),'utf8');
 assert.match(source,/patientDirectoryDetails/);
 assert.match(source,/maxLength=\{100\}/);
 assert.match(source,/Ana sayfada hasta ara/);
 assert.match(source,/Hasta adı, hasta no, telefon veya TC ile ara/);
 assert.ok((source.match(/maxLength=\{100\}/g)||[]).length>=2,'home and directory search must share the server bound');
 assert.match(source,/onEndReachedThreshold=\{0\.4\}/);
 assert.match(source,/Daha fazla hasta/);
 assert.match(source,/Eşleşen hasta bulunamadı/);
});
