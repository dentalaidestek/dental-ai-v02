// Load the production TypeScript helper through Node's CommonJS module loader.
// VM-created exports crossed into React's separately transpiled component harnesses
// inconsistently; a real Module instance preserves the same callable export shape.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
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

const compiled = new Module(filename, module);
compiled.filename = filename;
compiled.paths = Module._nodeModulePaths(path.dirname(filename));
compiled._compile(output, filename);

if (typeof compiled.exports.nextSessionRenderKey !== 'function') {
  throw new TypeError('sessionRenderKey.ts did not expose nextSessionRenderKey');
}

module.exports = compiled.exports;
