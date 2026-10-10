const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
function expertForm(fetch){
 const handlers={},windows={},error={hidden:true,textContent:'',focus(){this.focused=true}},submit={disabled:false};
 const orcid={value:'0000-0001-8203-1176',setAttribute(k,v){this[k]=v},removeAttribute(k){delete this[k]}};
 const form={action:'https://dental.test/expert-support/profile',bio:'Yazdıklarım',file:{name:'diploma.pdf'},querySelector:s=>s==='[type="submit"]'?submit:s==='[name="orcid_url"]'?orcid:error,addEventListener:(n,f)=>handlers[n]=f,setAttribute(){},removeAttribute(){}};
 const location={href:form.action,origin:'https://dental.test',assign(url){this.assigned=url}};
 vm.runInNewContext(fs.readFileSync('app/static/expert-profile-form.js','utf8'),{
  document:{querySelector:()=>form},window:{addEventListener:(n,f)=>windows[n]=f},location,URL,fetch,
  FormData:class{constructor(f){assert.equal(submit.disabled,false);this.bio=f.bio;this.file=f.file;this.orcid=f.querySelector('[name="orcid_url"]').value}},
  DOMParser:class{parseFromString(text){return{body:{textContent:text}}}}
 });return{handlers,windows,error,submit,orcid,form,location};
}
test('invalid ORCID stays on the form with the document and other input intact; retry works',async()=>{
 let calls=0;const w=expertForm(async()=>{calls++;return{ok:false,status:400,text:async()=> 'ORCID iD doğrulama hanesi geçersiz.'}});
 await w.handlers.submit({preventDefault(){}});
 assert.equal(w.location.assigned,undefined);assert.equal(w.error.hidden,false);assert.equal(w.error.focused,true);
 assert.match(w.error.textContent,/ORCID/);assert.equal(w.orcid['aria-invalid'],'true');assert.equal(w.orcid.value,'0000-0001-8203-1176');
 assert.equal(w.form.bio,'Yazdıklarım');assert.equal(w.form.file.name,'diploma.pdf');assert.equal(w.submit.disabled,false);
 await w.handlers.submit({preventDefault(){}});assert.equal(calls,2);
});
test('expert save blocks concurrent submissions and navigates after confirmed save',async()=>{
 let finish,calls=0;const w=expertForm(()=>{calls++;return new Promise(r=>finish=r)});
 const first=w.handlers.submit({preventDefault(){}});await w.handlers.submit({preventDefault(){}});assert.equal(calls,1);
 finish({ok:true,redirected:true,url:'https://dental.test/expert-support/profile?saved=1'});await first;
 assert.equal(w.location.assigned,'https://dental.test/expert-support/profile?saved=1');
 w.windows.pageshow();assert.equal(w.submit.disabled,false);
});
test('expired session and server errors keep expert profile inputs on screen',async()=>{
 for(const response of [{ok:true,redirected:true,url:'https://dental.test/login'},{ok:false,status:500,text:async()=> 'Internal traceback'}]){
  const w=expertForm(async()=>response);await w.handlers.submit({preventDefault(){}});
  assert.equal(w.location.assigned,undefined);assert.equal(w.error.hidden,false);assert.equal(w.submit.disabled,false);
  assert.doesNotMatch(w.error.textContent,/traceback/);assert.equal(w.form.file.name,'diploma.pdf');
 }
});
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
