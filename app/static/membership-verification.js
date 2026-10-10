(()=>{
const form=document.getElementById('memberForm');
if(!form)return;
let step=1,previewUrl=null;
const fileInput=document.getElementById('memberDocument'),submit=document.getElementById('memberSubmit');
function selected(){return form.querySelector('[name="document_type"]:checked')}
function show(value){step=value;form.querySelectorAll('[data-member-step]').forEach(panel=>panel.hidden=Number(panel.dataset.memberStep)!==step);document.querySelectorAll('.member-steps li').forEach((li,i)=>{li.classList.toggle('done',i+1<step);if(i+1===step)li.setAttribute('aria-current','step');else li.removeAttribute('aria-current');li.querySelector('b').textContent=i+1<step?'✓':String(i+1)});form.querySelectorAll('[data-selected-label]').forEach(el=>el.textContent=selected()?.dataset.label||'');}
function clear(){fileInput.value='';if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;document.getElementById('memberPreview').hidden=true;form.querySelector('[data-member-file]').hidden=true;form.querySelector('[data-member-step="2"] [data-member-next]').disabled=true;}
form.addEventListener('change',event=>{
 if(event.target.name==='document_type'){clear();form.querySelector('[data-member-step="1"] [data-member-next]').disabled=!selected();}
 if(event.target.name==='consent')submit.disabled=!event.target.checked;
 if(event.target!==fileInput)return;
 const file=fileInput.files?.[0],error=form.querySelector('[data-member-error]');error.hidden=true;if(!file)return;
 if(file.size===0||file.size>Number(form.dataset.maxMb||5)*1024*1024||!(/\.(jpe?g|png|pdf)$/i.test(file.name))){clear();error.textContent='JPG, PNG veya PDF seçin. Belge boş olmamalı ve '+(form.dataset.maxMb||5)+' MB sınırını aşmamalı.';error.hidden=false;return;}
 if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;
 form.querySelectorAll('[data-file-name]').forEach(el=>el.textContent=file.name);
 form.querySelectorAll('[data-file-size]').forEach(el=>el.textContent=(file.size/1024/1024).toFixed(2)+' MB');
 const preview=document.getElementById('memberPreview');preview.hidden=true;
 if(/\.(jpe?g|png)$/i.test(file.name)){previewUrl=URL.createObjectURL(file);preview.src=previewUrl;preview.hidden=false;}
 form.querySelector('[data-member-file]').hidden=false;
 form.querySelector('[data-member-step="2"] [data-member-next]').disabled=false;
});
form.addEventListener('click',event=>{
 if(event.target.closest('[data-member-next]')){if(step===1&&!selected()||step===2&&!fileInput.files?.length)return;show(step+1);}
 if(event.target.closest('[data-member-back]'))show(Math.max(1,step-1));
 if(event.target.closest('[data-member-gallery]')){fileInput.accept='image/jpeg,image/png';fileInput.click();}
 if(event.target.closest('[data-member-pdf]')){fileInput.accept='application/pdf';fileInput.click();}
 if(event.target.closest('[data-member-clear]'))clear();
});
form.addEventListener('submit',async event=>{
 event.preventDefault();
 if(form.dataset.sent==='1'||!selected()||!fileInput.files?.length||!form.querySelector('[name="consent"]').checked)return;
 const live=document.querySelector('[data-member-live]');
 const payload=new FormData(form);
 form.dataset.sent='1';submit.disabled=true;submit.textContent='Gönderiliyor…';
 live.hidden=false;live.textContent='Belgeniz yükleniyor. Lütfen bu ekranı kapatmayın.';
 try{
  const response=await fetch(form.action,{method:'POST',body:payload,credentials:'same-origin',cache:'no-store'});
  const html=await response.text();
  if(!response.ok){
   const doc=new DOMParser().parseFromString(html,'text/html');
   throw new Error(doc.querySelector('.member-error')?.textContent.trim()||doc.body.textContent.trim().slice(0,300)||'Belge gönderilemedi. Tekrar deneyin.');
  }
  if(new URL(response.url).pathname==='/login')throw new Error('Oturumunuz sona erdi. Yeniden giriş yapmanız gerekiyor.');
  live.textContent='Belgeniz başarıyla gönderildi. Başvuru durumu açılıyor…';
  location.assign(response.url);
 }catch(cause){
  form.dataset.sent='';submit.disabled=false;submit.textContent='Tekrar gönder →';
  live.textContent='Gönderme işlemi doğrulanamadı. Seçtiğiniz belge bu ekranda duruyor.';
  // Keep errors visible on the confirmation step, outside the hidden upload step.
  live.textContent+=' '+(cause.message||'Bağlantınızı kontrol edin ve tekrar deneyin.');
 }
});
const choices=form.querySelectorAll('[name="document_type"]');if(choices.length===1){choices[0].checked=true;form.querySelector('[data-member-step="1"] [data-member-next]').disabled=false;show(2);}
window.addEventListener('pageshow',()=>{form.dataset.sent='';submit.disabled=!form.querySelector('[name="consent"]').checked;submit.textContent='İncelemeye Gönder →';});
// Realtime events must not reload an in-progress file selection or submission.
window.addEventListener('dai:sync-event',event=>{if(event.detail?.event_type==='MEMBERSHIP_UPDATED'&&form.dataset.sent!=='1'){const live=document.querySelector('[data-member-live]');live.hidden=false;live.textContent='Belge durumunuz güncellendi. Seçiminiz korunuyor; güncel durumu Profilim bölümünden görebilirsiniz.';}});
})();
