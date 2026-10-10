const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
function wizard(fetch){
 const handlers={},windows={},elements=new Map();
 const element=key=>{if(!elements.has(key))elements.set(key,{hidden:false,disabled:false,textContent:'',dataset:{},style:{},classList:{toggle(){}},setAttribute(){},removeAttribute(){}});return elements.get(key)};
 const choice={dataset:{label:'Diploma'},checked:true};
 const file=element('#memberDocument');file.files=[{name:'belge.pdf',size:100}];file.click=()=>file.clicks=(file.clicks||0)+1;
 const form={action:'https://dental.test/account/verification',dataset:{maxMb:'5'},querySelector:s=>s.includes(':checked')?choice:s==='[name="consent"]'?{checked:true}:element(s),querySelectorAll:s=>s==='[name="document_type"]'?[choice,{},{},{}]:[],addEventListener:(n,f)=>handlers[n]=f};
 const location={assigned:null,assign(url){this.assigned=url},reload(){throw Error('Unexpected reload')}};
 vm.runInNewContext(fs.readFileSync('app/static/membership-verification.js','utf8'),{
  document:{getElementById:id=>id==='memberForm'?form:element('#'+id),querySelector:element,querySelectorAll:()=>[]},window:{addEventListener:(n,f)=>windows[n]=f},location,URL,FormData:class{constructor(){this.file=file.files[0]}},fetch,
  DOMParser:class{parseFromString(){return{querySelector:()=>({textContent:'Dosya geçersiz'}),body:{textContent:''}}}}
 });
 return{handlers,windows,file,form,location,element};
}
test('PDF and gallery chooser can be opened repeatedly; sync preserves the selection',()=>{
 const w=wizard(()=>{});
 for(const selector of ['[data-member-gallery]','[data-member-pdf]','[data-member-gallery]'])w.handlers.click({target:{closest:s=>s===selector?{}:null}});
 assert.equal(w.file.clicks,3);assert.equal(w.file.accept,'image/jpeg,image/png');
 w.handlers.change({target:w.file});
 assert.equal(w.element('[data-member-step="2"] [data-member-next]').disabled,false);
 assert.equal(w.element('[data-member-file]').hidden,false);
 w.windows['dai:sync-event']({detail:{event_type:'MEMBERSHIP_UPDATED'}});
 assert.equal(w.file.files[0].name,'belge.pdf');assert.equal(w.location.assigned,null);
});
test('failed upload keeps the file, permits retry and blocks duplicate POSTs',async()=>{
 let resolve,calls=0;const w=wizard(()=>{calls++;return new Promise(r=>resolve=r)});
 const first=w.handlers.submit({preventDefault(){}});
 await w.handlers.submit({preventDefault(){}});
 assert.equal(calls,1);
 w.windows['dai:sync-event']({detail:{event_type:'MEMBERSHIP_SUBMITTED'}});
 resolve({ok:false,text:async()=>'<div class="member-error">Dosya geçersiz</div>'});await first;
 assert.equal(w.form.dataset.sent,'');assert.equal(w.file.files[0].name,'belge.pdf');assert.equal(w.element('#memberSubmit').disabled,false);
 assert.match(w.element('[data-member-live]').textContent,/Dosya geçersiz/);
});
test('successful upload navigates only after server confirmation',async()=>{
 const target='https://dental.test/account/documents?purpose=membership&submitted=1';
 const w=wizard(async()=>({ok:true,url:target,text:async()=>'<h2>Belgeniz başarıyla gönderildi</h2>'}));
 await w.handlers.submit({preventDefault(){}});assert.equal(w.location.assigned,target);
});
test('chat bottom inset follows composer size and bottom scrolling keeps that inset',()=>{
 const text=fs.readFileSync('app/templates/expert_case_room.html','utf8');
 const sync=text.slice(text.indexOf('function syncKeyboardComposer(){'),text.indexOf('if(window.visualViewport){'));
 const scroll=text.slice(text.indexOf('function scrollChatToBottom('),text.indexOf('document.addEventListener("submit",async e=>{const form=e.target.closest?.(".case-state-form'));
 let top=610,aligned=0;const styles={};
 const chat={scrollHeight:1000,clientHeight:200,scrollTop:800,isConnected:true,getBoundingClientRect:()=>({bottom:700}),style:{setProperty:(k,v)=>styles[k]=v},lastElementChild:{scrollIntoView(){aligned++}}};
 const composer={hidden:false,style:{setProperty(){}},getBoundingClientRect:()=>({top}),closest:()=>({getBoundingClientRect:()=>({top:80}),style:{setProperty(){}}})};
 const context={destroyed:false,suspended:false,currentComposer:()=>composer,chat,window:{innerWidth:390,innerHeight:700,visualViewport:{height:700,offsetTop:0}},requestAnimationFrame:f=>f(),setTimeout:f=>f(),Math};
 vm.runInNewContext(sync+scroll+';syncKeyboardComposer();',context);
 assert.equal(styles['padding-bottom'],'106px');
 top=550;context.syncKeyboardComposer();assert.equal(styles['padding-bottom'],'166px');
 context.scrollChatToBottom();assert.equal(chat.scrollTop,1000);assert.equal(aligned,0);
});
