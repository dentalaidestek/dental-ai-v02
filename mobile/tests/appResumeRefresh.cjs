const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vm = require('node:vm');

function loadRefreshGate() {
  const source = fs.readFileSync(path.join(__dirname, '../src/appResumeRefresh.ts'), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(compiled, { exports });
  return exports.shouldRefreshOnAppResume;
}

test('only a focused real background or inactive transition refreshes a screen', () => {
  const shouldRefresh = loadRefreshGate();
  assert.equal(shouldRefresh('background', 'active', true), true);
  assert.equal(shouldRefresh('inactive', 'active', true), true);
  assert.equal(shouldRefresh('active', 'active', true), false);
  assert.equal(shouldRefresh('background', 'inactive', true), false);
  assert.equal(shouldRefresh('active', 'background', true), false);
  assert.equal(shouldRefresh(null, 'active', true), false);
  assert.equal(shouldRefresh('background', 'active', false), false);
  assert.equal(shouldRefresh('unknown', 'active', true), false);
});

test('profile, analysis history and tooth chart use the shared resume gate', () => {
  const root = path.join(__dirname, '../src');
  for (const file of ['NativePatientProfile.tsx', 'NativePatientHistory.tsx', 'NativeToothChart.tsx', 'NativePatientMedia.tsx', 'NativeProgram.tsx']) {
    const source = fs.readFileSync(path.join(root, file), 'utf8');
    assert.match(source, /shouldRefreshOnAppResume/, file + ' must use the shared gate');
    assert.match(source, /AppState\.currentState/, file + ' must snapshot the initial app state');
  }
});
