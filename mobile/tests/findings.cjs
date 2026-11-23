const ts=require('typescript'),fs=require('node:fs'),assert=require('node:assert/strict'),{test}=require('node:test');
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,f);
test('only findings with finite confidence of at least 50% are displayed',()=>{
 const {displayFindings}=require('../src/findings.ts');
 const f=displayFindings({findings:[{label:'low',confidence:.49},{label:'edge',confidence:.5},{label:'percent',confidence:75},{label:'unknown'},{label:'bad',confidence:'NaN'},{label:'invalid',confidence:120},{label:'null',confidence:null}]});
 assert.deepEqual(f.map(x=>x.label),['edge','percent']);assert.deepEqual(f.map(x=>x.confidence),[.5,.75]);assert.deepEqual(displayFindings({raw:'private result'}),[]);
});
test('validated web clinical string findings remain visible without invented confidence',()=>{
 const {displayFindings}=require('../src/findings.ts');const result=displayFindings({status:'INITIAL',findings:['Synthetic clinical finding',' ',null,{label:'low',confidence:.2}]});assert.equal(result.length,1);assert.equal(result[0].label,'Synthetic clinical finding');assert.equal(result[0].confidence,null);
});
