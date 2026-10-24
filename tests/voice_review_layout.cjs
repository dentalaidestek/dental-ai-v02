const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.open=false;}
  append(...items){this.children.push(...items)}
  replaceChildren(...items){this.children=items;this.textContent=''}
}
const code=fs.readFileSync('app/static/voice-exam.js','utf8');
const scope={document:{createElement:tag=>new Element(tag)}};
vm.createContext(scope);vm.runInContext(code.slice(code.indexOf('  function reviewSection('),code.indexOf('  async function finalizeReview(')),scope);
const all=node=>[node,...node.children.flatMap(all)];
const text=node=>all(node).map(x=>x.textContent).join('\n');
const host=new Element('div');
// Synthetic display data only; no external AI call or patient record.
const clinical={consideration:'İlaç ve plan birlikte kontrol edilmeli.',patient_quote:'Örnek ilaç kullanıyorum.',source_quote:'Örnek belge dayanağı.',missing_information:'İlaç dozunu doğrulayın.',alternative:'Planı hekimle değerlendirin.',source_id:'s1'};
const result={summary:[{text:clinical.consideration,quote:clinical.patient_quote},{text:'Soğukta ağrı',quote:'Soğuk içemiyorum.'},{text:'Soğukta ağrı',quote:'Soğuk içemiyorum.'}],clinical_items:[clinical,clinical],questions:[],contradictions:[],references:[{id:'s1',url:'https://example.org/guideline',institution:'Örnek',title:'Test kılavuzu',evidence_level:'guideline'}],notice:'Örnek kapsam',unavailable:[]};
scope.renderFinalReview(host,result,[]);
assert.equal(host.children.length,3,'Only nonempty summary, clinical finding and source coverage headings');
assert.ok(host.children.every(x=>x.tag==='details'&&!x.open),'Initial view contains collapsed headings');
assert.equal(all(host).filter(x=>x.textContent==='Soğukta ağrı').length,1,'Exact duplicate summary removed');
assert.equal(all(host).filter(x=>x.textContent===clinical.source_quote).length,1,'Clinical evidence survives duplicate summary and finding');
assert.ok(text(host).includes(clinical.missing_information));assert.ok(text(host).includes(clinical.alternative));
assert.equal(all(host).find(x=>x.className==='voice-result-source').href,result.references[0].url);
const unsafe='<img src=x onerror=alert(1)>';
scope.renderFinalReview(host,{...result,summary:[{text:unsafe,quote:'Alıntı'}],clinical_items:[],references:[]},[]);
assert.ok(text(host).includes(unsafe));assert.ok(!all(host).some(x=>x.tag==='img'),'Model output stays plain text');
assert.equal(host.children.length,2,'Empty categories do not repeat empty-state notices');
assert.ok(text(host).includes('Bu sonuç güvenlik onayı değildir.'));
console.log('Review layout: collapsed headings, duplicate removal, preserved clinical evidence, empty state and plain-text rendering passed.');
