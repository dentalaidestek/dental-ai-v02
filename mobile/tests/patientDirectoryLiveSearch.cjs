const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),ts=require('typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
const {PATIENT_DIRECTORY_SEARCH_DEBOUNCE_MS,normalizePatientDirectorySearch}=require('../src/patientDirectoryPresentation.ts');

test('patient directory live search uses a bounded debounce instead of a request per key',()=>{
 assert.equal(PATIENT_DIRECTORY_SEARCH_DEBOUNCE_MS,300);
 const source=fs.readFileSync(path.join(__dirname,'../App.tsx'),'utf8');
 assert.match(source,/normalizePatientDirectorySearch\(q\)/);
 assert.match(source,/setTimeout\(\(\)=>setSearch\(normalized\),PATIENT_DIRECTORY_SEARCH_DEBOUNCE_MS\)/);
 assert.match(source,/return\(\)=>clearTimeout\(timer\)/);
 assert.match(source,/onSubmitEditing=\{applySearch\}/);
});

test('live search normalization preserves Turkish input and bounds whitespace',()=>{
 assert.equal(normalizePatientDirectorySearch('  İpek   Çetin   0555  '),'İpek Çetin 0555');
 assert.equal(normalizePatientDirectorySearch('   '),'');
});
