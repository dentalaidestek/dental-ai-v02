const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');

require.extensions['.ts']=(module,filename)=>{
  const source=fs.readFileSync(filename,'utf8');
  module._compile(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,filename);
};

const {programInlineCreateFor,programDateTimeOnDay}=require('../src/programInlineAdd.ts');

test('web inline-add intent preserves view-specific type and target date',()=>{
  assert.deepEqual(programInlineCreateFor('today','2030-01-08'),{date:'2030-01-08',type:'APPOINTMENT',label:'＋ Program ekle'});
  assert.deepEqual(programInlineCreateFor('week','2030-01-09'),{date:'2030-01-09',type:'CLASS',label:'＋ Ders ekle'});
  assert.equal(programInlineCreateFor('month','2030-01-09'),null);
  assert.equal(programInlineCreateFor('week','2030-02-30'),null);
});

test('inline add applies the selected day without changing suggested wall-clock times',()=>{
  assert.deepEqual(programDateTimeOnDay('2030-01-07T10:15','2030-01-07T10:45','2030-01-09'),{
    start_at:'2030-01-09T10:15',end_at:'2030-01-09T10:45'
  });
  assert.deepEqual(programDateTimeOnDay('2030-01-07T23:00','2030-01-08T01:00','2030-01-09'),{
    start_at:'2030-01-09T23:00',end_at:'2030-01-10T01:00'
  });
  assert.deepEqual(programDateTimeOnDay('2030-01-07T10:15','','2030-01-09'),{
    start_at:'2030-01-09T10:15',end_at:''
  });
});

test('inline add rejects invalid source and target dates rather than saving a malformed appointment',()=>{
  assert.throws(()=>programDateTimeOnDay('2030-02-30T10:00','2030-02-30T10:30','2030-03-01'));
  assert.throws(()=>programDateTimeOnDay('2030-01-07T10:00','2030-01-06T10:30','2030-03-01'));
  assert.throws(()=>programDateTimeOnDay('2030-01-07T24:00','','2030-03-01'));
});
