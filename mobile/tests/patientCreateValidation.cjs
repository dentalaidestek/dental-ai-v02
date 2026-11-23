const {test}=require('node:test');
const assert=require('node:assert/strict');
const ts=require('typescript');
const fs=require('node:fs');

require.extensions['.ts']=(module,filename)=>{
  const source=fs.readFileSync(filename,'utf8');
  module._compile(ts.transpileModule(source,{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020},
  }).outputText,filename);
};

const {
  normalizePatientCreatePhone,
  patientCreateValidationError,
}=require('../src/patientCreateValidation.ts');

test('new patient requires a Turkish mobile number like the web form',()=>{
  assert.equal(patientCreateValidationError({
    first_name:'Ada',last_name:'Kaya',phone:'',
  }),'Telefon numarası zorunludur.');
  assert.equal(patientCreateValidationError({
    first_name:'Ada',last_name:'Kaya',phone:'05551234567',
  }),null);
});

test('new patient rejects invalid phone prefix and length before API submission',()=>{
  for(const phone of ['5551234567','04551234567','0555123456','055512345678','05abcdefgh1']){
    assert.notEqual(patientCreateValidationError({
      first_name:'Ada',last_name:'Kaya',phone,
    }),null,phone);
  }
});

test('phone input sanitization matches the web numeric input and eleven-digit cap',()=>{
  assert.equal(normalizePatientCreatePhone('+90 (555) 123-45-67'),'90555123456');
  assert.equal(normalizePatientCreatePhone('0555abc1234567'),'05551234567');
  assert.equal(normalizePatientCreatePhone(null),'');
});

test('required names remain validated together with phone',()=>{
  assert.equal(patientCreateValidationError({first_name:' ',last_name:'Kaya',phone:'05551234567'}),'Ad ve soyad zorunludur.');
  assert.equal(patientCreateValidationError({first_name:'Ada',last_name:' ',phone:'05551234567'}),'Ad ve soyad zorunludur.');
});
