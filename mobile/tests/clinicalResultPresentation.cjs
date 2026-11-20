const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const assert = require('node:assert/strict');
const {test} = require('node:test');

const source = fs.readFileSync(require.resolve('../src/clinicalResultPresentation.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  fileName: 'clinicalResultPresentation.ts',
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
}).outputText;
const moduleExports = {};
vm.runInNewContext(compiled, {exports: moduleExports});
const {CLINICAL_QUESTION_GUIDANCE, clinicalResultSections, clinicalResultTitle} = moduleExports;

const webOrder = [
  'En Olası Durum',
  'Önemli Bulgular',
  'Tedavi Seçenekleri',
  'Tedaviye Bağlı Dikkat Edilecekler',
  'Önerilen Yaklaşım',
  'Diğer Olası Tanılar',
];

test('native clinical result sections follow the web initial/final order', () => {
  const result = {
    status: 'FINAL',
    most_likely: 'Synthetic likely condition',
    findings: ['Synthetic finding'],
    treatment_options: ['Synthetic treatment'],
    treatment_cautions: ['Synthetic caution'],
    preferred_approach: 'Synthetic approach',
    differential: ['Synthetic differential'],
    recommended_evaluation: ['Must stay outside the web result summary'],
    uncertainty: 'Must stay outside the web result summary',
    preliminary_assessment: 'Must stay outside the web result summary',
  };
  const sections = clinicalResultSections(result);
  assert.equal(JSON.stringify(sections.map(section => section.label)), JSON.stringify(webOrder));
  assert.equal(JSON.stringify(sections.map(section => section.kind)), JSON.stringify([
    'text', 'unordered', 'ordered', 'unordered', 'text', 'unordered',
  ]));
  assert.equal(sections.some(section => section.label === 'Belirsizlik'), false);
  assert.equal(sections.some(section => section.label === 'Ön Değerlendirme'), false);
  assert.equal(sections.some(section => section.label === 'Önerilen Klinik Değerlendirmeler'), false);
});

test('clinical result titles and question guidance use the web wording', () => {
  assert.equal(clinicalResultTitle('INITIAL'), 'Klinik Değerlendirme');
  assert.equal(clinicalResultTitle('ANALYSIS_COMPLETE'), 'Klinik Değerlendirme');
  assert.equal(clinicalResultTitle('FINAL'), 'Nihai Klinik Değerlendirme');
  assert.equal(clinicalResultTitle('READY'), 'Ön değerlendirme');
  assert.equal(clinicalResultTitle('AI_ANALYZING'), 'AI analizi sürüyor');
  assert.equal(CLINICAL_QUESTION_GUIDANCE, 'Yalnız tedavi sırasını, uygulanabilirliği veya vaka-özel komplikasyon riskini değiştirebilecek eksik bilgiler sorulur.');
});

test('missing clinical result has no sections', () => {
  assert.equal(clinicalResultSections(null).length, 0);
  assert.equal(clinicalResultSections(undefined).length, 0);
});
