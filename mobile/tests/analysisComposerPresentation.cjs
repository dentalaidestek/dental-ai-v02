const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');

require.extensions['.ts'] = (module, filename) => {
  const source = fs.readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    fileName: filename,
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  module._compile(output, filename);
};

const mobileRoot = path.resolve(__dirname, '..');
const presentation = require('../src/analysisComposerPresentation.ts');
const component = fs.readFileSync(path.join(mobileRoot, 'src/NativeAnalysisUpload.tsx'), 'utf8');

test('analysis composer keeps the web three-step order and labels', () => {
  const steps = presentation.analysisComposerSteps(0);
  assert.deepEqual(steps.map(step => step.number), [1, 2, 3]);
  assert.deepEqual(steps.map(step => step.title), ['Diş', 'Kısa klinik bilgi', 'Fotoğraf / Röntgen']);
  assert.equal(steps[0].label, 'Diş numarası');
  assert.equal(steps[1].label, 'Hekim notu');
  assert.equal(steps[1].helper, 'Görüntü olmadan da klinik bilgiyle analiz başlatabilirsiniz.');
  assert.equal(steps[2].label, 'Görüntü yükle');
});

test('saved gallery media changes the third web step to Ek görünt', () => {
  const steps = presentation.analysisComposerSteps(2);
  assert.equal(steps[2].title, 'Ek görünt');
  assert.match(steps[2].helper, /Kayıtlı görüntüler dahil toplam en fazla 4/);
  assert.match(steps[2].helper, /15 MiB/);
  assert.match(steps[2].helper, /48 MiB/);
});

test('new image guidance is derived from the shared upload byte contract', () => {
  const helper = presentation.analysisComposerImageHelp(false);
  assert.match(helper, /En fazla 4 görüntü yükleyebilirsiniz/);
  assert.match(helper, /Dosya başına 15 MiB/);
  assert.match(helper, /toplam yeni dosya boyutu 48 MiB/);
});

test('image count distinguishes saved archive references from new files', () => {
  assert.equal(
    presentation.analysisComposerImageCountLabel(2, 1),
    '3 / 4 görüntü seçildi · 2 kayıtlı · 1 yeni',
  );
  assert.equal(presentation.analysisComposerImageCountLabel(-2, 0), '0 / 4 görüntü seçildi');
});

test('native composer renders numbered steps, web safety guidance and primary action', () => {
  assert.match(component, /analysisComposerSteps\(savedIds\.length\)/);
  assert.match(component, /ANALYSIS_COMPOSER_SAFETY_NOTE/);
  assert.match(component, /primaryButton/);
  assert.match(component, /accessibilityLabel=\{toothStep\.accessibilityLabel\}/);
  assert.match(component, /accessibilityLabel=\{clinicalStep\.accessibilityLabel\}/);
  assert.doesNotMatch(component, /Görüntüler ve Klinik Bilgi/);
  assert.doesNotMatch(component, /15 MiB|48 MiB/);
});
