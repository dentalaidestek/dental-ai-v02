// Load the production React hook through the same CommonJS boundary used by the app.
// VM component tests must receive the real callable default export, not a plain module stub.
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const sessionRenderKey = require('./sessionRenderKeyModule.cjs');

const filename = require.resolve('../../src/useSessionRenderKey.ts');
const source = fs.readFileSync(filename, 'utf8');
const output = ts.transpileModule(source, {
  fileName: filename,
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
}).outputText;

const hookExports = {};
vm.compileFunction(output, ['exports', 'require'])(hookExports, name => {
  if (name === 'react') return React;
  if (name === './sessionRenderKey') return sessionRenderKey;
  throw new Error('Unexpected useSessionRenderKey dependency: ' + name);
});

if (typeof hookExports.default !== 'function') {
  throw new TypeError('useSessionRenderKey.ts did not expose its default hook');
}

module.exports = hookExports;
