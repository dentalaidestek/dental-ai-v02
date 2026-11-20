const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');

const mobileRoot = path.resolve(__dirname, '..');

function read(relativePath) {
  return fs.readFileSync(path.join(mobileRoot, relativePath), 'utf8');
}

function parse(relativePath) {
  return ts.createSourceFile(
    relativePath,
    read(relativePath),
    ts.ScriptTarget.Latest,
    true,
    relativePath.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
}

function hasNamedImport(sourceFile, moduleName, exportedName) {
  return sourceFile.statements.some(statement =>
    ts.isImportDeclaration(statement) &&
    ts.isStringLiteral(statement.moduleSpecifier) &&
    statement.moduleSpecifier.text === moduleName &&
    statement.importClause &&
    statement.importClause.namedBindings &&
    ts.isNamedImports(statement.importClause.namedBindings) &&
    statement.importClause.namedBindings.elements.some(element =>
      element.propertyName?.text === exportedName || element.name.text === exportedName,
    ),
  );
}

test('analysis image limit is defined once in the shared upload contract', () => {
  const source = parse('src/uploadLimits.ts');
  const declaration = source.statements.find(statement =>
    ts.isVariableStatement(statement) &&
    statement.declarationList.declarations.some(item =>
      ts.isIdentifier(item.name) && item.name.text === 'ANALYSIS_MAX_IMAGES',
    ),
  );
  assert.ok(declaration, 'uploadLimits.ts must declare ANALYSIS_MAX_IMAGES');
  assert.ok(declaration.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword));
  const item = declaration.declarationList.declarations.find(item =>
    ts.isIdentifier(item.name) && item.name.text === 'ANALYSIS_MAX_IMAGES',
  );
  assert.equal(item.initializer?.text, '4');
});

test('analysis API imports and re-exports the shared image limit', () => {
  const source = parse('src/analysisApi.ts');
  assert.ok(hasNamedImport(source, './uploadLimits', 'ANALYSIS_MAX_IMAGES'));
  assert.ok(source.statements.some(statement =>
    ts.isExportDeclaration(statement) &&
    statement.moduleSpecifier &&
    ts.isStringLiteral(statement.moduleSpecifier) &&
    statement.moduleSpecifier.text === './uploadLimits' &&
    statement.exportClause &&
    ts.isNamedExports(statement.exportClause) &&
    statement.exportClause.elements.some(element =>
      element.propertyName?.text === 'ANALYSIS_MAX_IMAGES' || element.name.text === 'ANALYSIS_MAX_IMAGES',
    ),
  ), 'existing consumers must receive the same shared constant');
});

test('native analysis composer and gallery consume the API re-export', () => {
  for (const relativePath of ['src/NativeAnalysisUpload.tsx', 'src/NativePatientMedia.tsx']) {
    assert.ok(
      hasNamedImport(parse(relativePath), './analysisApi', 'ANALYSIS_MAX_IMAGES'),
      relativePath + ' must use the canonical analysis image limit',
    );
  }
});
