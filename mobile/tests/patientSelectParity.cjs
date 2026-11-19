const ts=require('typescript'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {test}=require('node:test');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);

const {
 PATIENT_SELECT_QUERY_MAX_LENGTH,
 normalizePatientSelectQuery,
 patientSelectEmptyState,
 patientSelectRowDetails,
}=require('../src/patientSelectPresentation.ts');

test('appointment patient search normalizes Turkish whitespace and enforces the API bound',()=>{
 assert.equal(PATIENT_SELECT_QUERY_MAX_LENGTH,100);
 assert.equal(normalizePatientSelectQuery('  İpek   Çetin\n  0555 123 45 67  '),'İpek Çetin 0555 123 45 67');
 assert.equal(normalizePatientSelectQuery('   '),'');
 assert.equal(normalizePatientSelectQuery('a'.repeat(100)),'a'.repeat(100));
 assert.throws(()=>normalizePatientSelectQuery('a'.repeat(101)),/100 karakter/);
});

test('appointment patient rows disambiguate with patient number and phone but never expose TCKN',()=>{
 const details=patientSelectRowDetails({
  anonymous_id:' PAT-123 ',
  phone:' 05551234567 ',
  tc_kimlik_no:'12345678901',
 });
 assert.deepEqual(details,['Hasta No: PAT-123','Telefon: 05551234567']);
 assert.ok(!details.join(' ').includes('12345678901'));
});

test('appointment patient selector has explicit loading, empty and error states',()=>{
 assert.equal(patientSelectEmptyState('',true,''),'Hastalar yükleniyor…');
 assert.equal(patientSelectEmptyState('İpek',false,''),'Eşleşen hasta bulunamadı.');
 assert.equal(patientSelectEmptyState('',false,''),'Henüz hasta bulunmuyor.');
 assert.equal(patientSelectEmptyState('İpek',false,'network'),'Hasta listesi alınamadı.');
});

test('appointment patient selector advertises bounded web-compatible search and paginates',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../src/NativePatientSelect.tsx'),'utf8');
 assert.match(source,/Hasta ara: ad, soyad, hasta numarası, telefon veya TC/);
 assert.match(source,/maxLength=\{PATIENT_SELECT_QUERY_MAX_LENGTH\}/);
 assert.match(source,/onEndReachedThreshold=\{0\.4\}/);
 assert.match(source,/keyboardShouldPersistTaps="handled"/);
 assert.match(source,/patientSelectRowDetails\(item\)/);
 assert.match(source,/Daha fazla hasta/);
 assert.match(source,/Eşleşen hasta bulunamadı/);
 assert.doesNotMatch(source,/item\.tc_kimlik_no/);
});
