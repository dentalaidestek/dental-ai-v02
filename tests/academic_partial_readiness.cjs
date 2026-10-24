const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const template = fs.readFileSync('app/templates/notes_ai.html', 'utf8');
const code = template.slice(template.indexOf('    function renderIndexFiles()'), template.indexOf('    function escapeHtml('));
function node() { return {textContent:'', children:[], appendChild(child){this.children.push(child);}, replaceChildren(){this.children=[];}}; }
async function check(result) {
    const nodes = Object.fromEntries(['studyIndexSummary','studyIndexFileList','studyIndexCoverage'].map(id => [id,node()]));
    const buttons=[{disabled:true}];
    const ctx={input:{disabled:true},send:{disabled:true},status:node(),materialCount:4,
        v2Ready:false,indexState:{complete:false},activeRun:null,uploading:false,
        indexTimer:null,indexPolling:false,courseId:7,timers:0,
        setTimeout:()=>{ctx.timers++;return 1;},clearTimeout:()=>{},
        fetch:async()=>({ok:true,json:async()=>result}),
        document:{hidden:false,getElementById:id=>nodes[id],querySelectorAll:()=>buttons,
            createElement:node,createTextNode:text=>({textContent:text})}};
    vm.createContext(ctx);vm.runInContext(code,ctx);
    await vm.runInContext('waitForIndex()',ctx);
    return {ctx,nodes,buttons};
}
(async()=>{
    const partial={ready:true,complete:false,completed:3,total:4,state:'partial',files:[
        {filename:'hazır.pdf',state:'ready',usable:true},
        {filename:'<img src=x onerror=bad()>.pdf',state:'failed',usable:false,message:'OCR tamamlanamadı.'}]};
    const {ctx,nodes,buttons}=await check(partial);
    assert.equal(ctx.input.disabled,false);assert.equal(ctx.send.disabled,false);
    assert.equal(buttons[0].disabled,false);assert.equal(ctx.timers,0);
    assert.equal(nodes.studyIndexSummary.textContent,'3/4 dosya kullanılabilir');
    assert.equal(nodes.studyIndexFileList.children[1].children[0].textContent,partial.files[1].filename);
    assert.match(nodes.studyIndexCoverage.textContent,/yalnızca hazır/);
    const none=await check({ready:false,complete:false,completed:0,total:1,state:'failed',files:[partial.files[1]]});
    assert.equal(none.ctx.input.disabled,true);assert.equal(none.ctx.send.disabled,true);assert.equal(none.ctx.timers,0);
    const pending=await check({...partial,files:[{filename:'sırada.pdf',state:'preparing',usable:false}]});
    assert.equal(pending.ctx.input.disabled,false);assert.equal(pending.ctx.timers,1);
    console.log('3 frontend readiness scenarios passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
