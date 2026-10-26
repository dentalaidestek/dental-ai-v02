const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.open=false;}
  append(...items){this.children.push(...items)}
  replaceChildren(...items){this.children=items;this.textContent=''}
}
const code=fs.readFileSync('app/static/voice-exam.js','utf8');
const scope={labels:{medications:'İlaç / hasta beyanı',allergies:'Alerji / hasta beyanı'},document:{createElement:tag=>new Element(tag),createTextNode:text=>Object.assign(new Element('#text'),{textContent:text})}};
vm.createContext(scope);vm.runInContext(code.slice(code.indexOf('  function reviewIcon('),code.indexOf('  async function finalizeReview(')),scope);
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
assert.ok(text(host).includes('Soğuk içemiyorum.'),'Distinct supporting quote remains visible');
assert.equal(all(host).filter(x=>x.textContent===clinical.source_quote).length,1,'Clinical evidence survives duplicate summary and finding');
assert.ok(text(host).includes(clinical.missing_information));assert.ok(text(host).includes(clinical.alternative));
assert.equal(all(host).find(x=>x.className==='voice-result-source').href,result.references[0].url);
scope.renderFinalReview(host,{...result,clinical_items:[clinical,{...clinical,source_quote:'İkinci belge dayanağı.'}]},[]);
assert.ok(text(host).includes('İkinci belge dayanağı.'),'Distinct evidence must not be lost when finding and patient quote match');
const advice={observation:'Kaygı beyanı',quote:'Korkuyorum.',suggestion:'İşlemi açıklayın.'};
scope.renderFinalReview(host,{...result,summary:[],clinical_items:[]},[advice,advice,{...advice,suggestion:'Ara vermeyi teklif edin.'}]);
assert.equal(all(host).filter(x=>x.textContent===advice.suggestion).length,1);
assert.ok(text(host).includes('Ara vermeyi teklif edin.'),'Distinct communication advice is preserved');
const unsafe='<img src=x onerror=alert(1)>';
scope.renderFinalReview(host,{...result,summary:[
  {field:'medications',text:'Yok',quote:'Yok'},
  {field:'allergies',text:'Yok',quote:'Yok'},
  {field:'medications',text:'Yok',quote:'Yok'}
],clinical_items:[],references:[]},[]);
assert.equal(host.children[0].children.filter(x=>x.tag==='article').length,2,
  'Equal values in medication and allergy fields are separate facts; only the exact same field can be deduplicated');
assert.ok(text(host).includes('İlaç / hasta beyanı')&&text(host).includes('Alerji / hasta beyanı'),
  'Each summary fact identifies the reviewed patient field');
assert.equal(all(host).filter(x=>x.textContent==='Yok').length,2,
  'Identical evidence and reviewed value appear only once per field');
scope.renderFinalReview(host,{...result,summary:[{text:unsafe,quote:'Alıntı'}],clinical_items:[],references:[]},[]);
assert.ok(text(host).includes(unsafe));assert.ok(all(host).filter(x=>x.tag==='img').every(x=>x.src.startsWith('/static/vendor/tabler/')),'Only fixed library icons are images; model output stays plain text');
assert.equal(host.children.length,2,'Empty categories do not repeat empty-state notices');
assert.ok(text(host).includes('Bu sonuç güvenlik onayı değildir.'));
console.log('Review layout: collapsed headings, duplicate removal, preserved clinical evidence, empty state and plain-text rendering passed.');
