// Execute the actual stream rendering closure with a deterministic clock/DOM.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('app/templates/notes_ai.html', 'utf8');
const start = html.indexOf("        let answer='',artifact=null,pdfOutput=false,renderTimer=null;");
assert(start >= 0);
const closure = html.slice(start, html.indexOf('        try {', start));
const deltaStart = html.indexOf("                            answer+=event.text||'';", start);
const delta = html.slice(deltaStart, html.indexOf('\n                        }', deltaStart));

function exercise(pdf) {
  let paints=0,markdownCalls=0,scrolls=0,token=0;
  const queued=new Map(),element={value:''};
  Object.defineProperty(element,'innerHTML',{set(v){paints++;this.value=v;},get(){return this.value;}});
  const context={
    pending:{classList:{remove(){}},querySelector(){return element;}},
    safeMarkdown(text){markdownCalls++;return text;},
    scrollChatBottom(){scrolls++;},
    setTimeout(fn){queued.set(++token,fn);return token;},
    clearTimeout(id){queued.delete(id);},
    pdf,
  };
  const result=vm.runInNewContext(`(() => {
    ${closure}
    pdfOutput=pdf;
    for(let i=0;i<1000;i++) { const event={text:'Konu açıklaması. '}; ${delta} }
    cancelRender(); renderPending();
    return answer;
  })()`,context);
  assert.equal(result,'Konu açıklaması. '.repeat(1000));
  assert.equal(paints,1); assert.equal(scrolls,1); assert.equal(queued.size,0);
  assert.equal(markdownCalls,pdf?0:1);
  assert.equal(element.value,pdf?'PDF hazırlanıyor...':result);
  // A delayed repaint must not overwrite the completed PDF artifact notice.
  element.value='İstediğin PDF hazır.';
  for(const fn of queued.values()) fn();
  assert.equal(element.value,'İstediğin PDF hazır.');
  return {deltas:1000,paints,markdownCalls,scrolls};
}
console.log(JSON.stringify({text:exercise(false),pdf:exercise(true)}));
