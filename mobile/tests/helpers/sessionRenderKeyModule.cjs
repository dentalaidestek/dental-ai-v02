// CommonJS bridge for VM-based native component tests that import the TypeScript session-key helper.
const fs = require('node:fs');
const ts = require('typescript');
const filename = require.resolve('../../src/sessionRenderKey.ts');
const source = fs.readFileSync(filename, 'utf8');
const output = ts.transpileModule(source, {
  fileName: filename,
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
}).outputText;
const exports = {};
require('node:vm').runInNewContext(output, { exports });
module.exports = exports;
