(()=>{
  const root=document.getElementById('voice-exam');if(!root||root.dataset.bound)return;root.dataset.bound='true';
  const $=s=>root.querySelector(s),status=$('.voice-exam-status'),start=$('[data-voice-start]'),stop=$('[data-voice-stop]'),retry=$('[data-voice-retry]'),textButton=$('[data-voice-text]'),transcript=$('[data-voice-transcript]'),consent=$('[data-voice-consent]'),review=$('.voice-review'),save=$('[data-voice-save]');
  const labels={first_name:'Ad',last_name:'Soyad',age:'Yaş',chief_complaint:'Başvuru şikâyeti',medical_history:'Sistemik hastalık / hasta beyanı',medications:'İlaç / hasta beyanı',allergies:'Alerji / hasta beyanı',clinical_findings:'Klinik bulgular',plan:'Hekimin belirttiği plan'};
  const states={CARIES:'Çürük',FILLING:'Dolgu',CROWN:'Kron',ROOT_CANAL:'Kanal tedavisi',EXTRACTED:'Çekilmiş',IMPLANT:'İmplant',OTHER:'Diğer'};
  let available=false,busy=false,recording=false,disposed=false,recorder=null,stream=null,audio=null,timer=null,deadline=null,started=0,revision='',requestKey='',unsaved=false,fieldState={},teethState=[],appointmentQuote='',appointmentContext=null;
  let epoch=0,clinicalTimer=null,lastClinicalInput='',clinicalRequest=0;const pending=new Set();
  async function voiceFetch(url,options={}){
    const at=epoch,controller=new AbortController();pending.add(controller);
    try{const response=await fetch(url,{...options,signal:controller.signal});
      const body=await response.json();if(disposed||at!==epoch)throw Error('Görüşme kapatıldı.');
      return {ok:response.ok,json:async()=>body};
    }finally{pending.delete(controller)}
  }
  function clearPrivateDraft(){
    epoch++;clearTimeout(clinicalTimer);lastClinicalInput='';clinicalRequest++;pending.forEach(c=>c.abort());pending.clear();
    fieldState={};teethState=[];appointmentQuote='';appointmentContext=null;revision='';requestKey='';audio=null;
    transcript.value='';unsaved=false;review.hidden=true;retry.hidden=true;
    for(const selector of ['[data-voice-fields]','[data-voice-teeth]','[data-voice-communication]','[data-voice-source-results]','[data-voice-clinical-results]'])$(selector).replaceChildren();
    $('[data-voice-uncertain]').textContent='';$('[data-voice-appointment-quote]').textContent='';
    for(const selector of ['[data-voice-source-query]','[data-voice-appointment-start]','[data-voice-appointment-end]'])$(selector).value='';
    $('[data-voice-appointment-title]').value='Kontrol randevusu';
    $('[data-voice-save-appointment]').checked=false;$('[data-voice-confirm]').checked=false;
    consent.checked=false;$('[data-voice-timer]').textContent='00:00';
    if(recorder){recorder.ondataavailable=null;recorder.onstop=null;recorder.onerror=null;if(recorder.state==='recording')recorder.stop();recorder=null}
    micOff();busy=false;controls();
  }
  const key=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
  function message(text,error=false){status.textContent=text;status.classList.toggle('voice-error',error)}
  function controls(){start.disabled=!available||busy||recording;stop.disabled=!recording;textButton.disabled=!available||busy||recording;save.disabled=busy||recording;retry.disabled=busy||recording;consent.disabled=busy||recording}
  function micOff(){clearInterval(timer);clearTimeout(deadline);stream?.getTracks().forEach(track=>track.stop());stream=null;recording=false;controls()}
  function currentFields(){
    root.querySelectorAll('[data-field-row]').forEach(row=>{const item=fieldState[row.dataset.fieldRow];if(item){item.value=row.querySelector('textarea').value;item.selected=row.querySelector('input').checked}});
  }
  function render(){
    const host=$('[data-voice-fields]');host.replaceChildren();
    Object.entries(fieldState).forEach(([name,item])=>{
      const row=document.createElement('div');row.dataset.fieldRow=name;
      const label=document.createElement('label');label.className='voice-check';const choice=document.createElement('input');choice.type='checkbox';choice.checked=item.selected;label.append(choice,document.createTextNode(labels[name]));
      const value=document.createElement('textarea');value.rows=2;value.maxLength=3000;value.value=item.value;value.setAttribute('aria-label',labels[name]);const wrap=document.createElement('label');wrap.className='voice-field';wrap.append(value);
      const quote=document.createElement('small');quote.className='voice-field-quote';quote.textContent='Konuşmadaki dayanak: '+item.quote;row.append(label,wrap,quote);host.append(row);
    });
    const teeth=$('[data-voice-teeth]');teeth.replaceChildren();
    teethState.forEach(item=>{const label=document.createElement('label');label.className='voice-check';const choice=document.createElement('input');choice.type='checkbox';choice.dataset.toothKey=item.tooth+':'+item.status;label.append(choice,document.createTextNode('Diş '+item.tooth+' — '+states[item.status]+'; hekim bulgusu olarak şemaya uygula. Dayanak: '+item.quote));teeth.append(label)});
    $('[data-voice-appointment]').hidden=!appointmentQuote;$('[data-voice-appointment-quote]').textContent=appointmentQuote;
    review.hidden=false;unsaved=true;$('[data-voice-confirm]').checked=false;
  }
  async function jsonResponse(response){const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||'İşlem tamamlanamadı. Tekrar dene.');return result}
  function context(){
    currentFields();const fields={};for(const [name,item] of Object.entries(fieldState))fields[name]={value:item.value,quote:item.quote};
    const data={fields,teeth:teethState,...(appointmentContext?{appointment:appointmentContext}:{})};if(new TextEncoder().encode(JSON.stringify(data)).length>6000)throw Error('Görüşme bağlamı sınırına ulaşıldı. Önce alanları kontrol ederek kaydet.');return data;
  }
  function merge(result){
    currentFields();$('[data-voice-clinical-results]').textContent='Görüşme bilgileri güncellendi; önceki klinik değerlendirme geçersiz. Yeniden değerlendir.';const data=result.review;if(!revision)revision=result.revision;if(!requestKey)requestKey=key();
    const next={};for(const [name,item] of Object.entries(data.fields||{})){if(!labels[name])continue;const old=fieldState[name];next[name]={...item,selected:!!old?.selected&&old.value===item.value}}fieldState=next;
    teethState=data.teeth||[];appointmentQuote=data.appointment?.quote||'';appointmentContext=data.appointment?{quote:data.appointment.quote,acceptance_quote:data.appointment.acceptance_quote||''}:null;
    $('[data-voice-appointment-start]').value=data.appointment?.start_at||'';
    $('[data-voice-save-appointment]').checked=!!data.appointment?.agreed;
    if(appointmentQuote&&!data.appointment?.agreed)appointmentQuote+=' · Tarih/saat veya karşılıklı kabul net değil; eksik bilgiyi tamamla.';
    const coaching=$('[data-voice-communication]');coaching.replaceChildren();for(const item of data.communication||[]){const p=document.createElement('p');p.textContent='İletişim önerisi: '+item.observation+' · Dayanak: “'+item.quote+'” · Öneri: '+item.suggestion;coaching.append(p)}
    const barrierNames={COST:'Ücret kaygısı',FEAR:'Tedavi korkusu',TIME:'Zaman engeli',TRUST:'Güven ihtiyacı',UNDERSTANDING:'Açıklama ihtiyacı',UNCLEAR:'Neden net değil'};
    for(const item of data.decision_barriers||[]){const block=document.createElement('article');for(const text of [barrierNames[item.category]+': '+item.observation,'Dayanak: '+item.quote,'Sorulabilecek soru: '+item.question,'Açıklama önerisi: '+item.explanation]){const p=document.createElement('p');p.textContent=text;block.append(p)}coaching.append(block)}
    $('[data-voice-uncertain]').textContent=data.uncertain?'Kontrol edilmesi gereken ifade: '+data.uncertain:'';
    render();message('Güncel görüşme özeti hazır. Alanları kontrol et veya dinlemeye devam et.');clearTimeout(clinicalTimer);clinicalTimer=setTimeout(()=>assessClinical(false).catch(error=>message(error.message,true)),1200);
  }
  async function processAudio(){
    if(!audio||busy)return;if(!consent.checked){message('Ses aktarımı onayını işaretle.',true);return}
    busy=true;controls();message('Ses bölümü çözümleniyor…');
    try{const result=await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/audio',{method:'POST',body:audio,credentials:'same-origin',headers:{'Content-Type':audio.type,'X-Voice-Consent':'yes','X-Voice-Context':btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(context()))))}}));
      transcript.value=result.review.transcript;merge(result);audio=null;retry.hidden=true;
    }catch(error){if(!disposed){message(error.message,true);retry.hidden=false}}finally{busy=false;controls()}
  }
  start.addEventListener('click',async()=>{
    if(!consent.checked){message('Ses aktarımı onayını işaretle.',true);return}
    if(audio){message('Önce bekleyen ses bölümünü işle veya taslağı temizle.',true);return}
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){message('Bu tarayıcıda ses kaydı yok. Konuşma metnini elle ekleyebilirsin.',true);return}
    busy=true;controls();const startEpoch=epoch;
    try{const acquired=await navigator.mediaDevices.getUserMedia({audio:true});if(disposed||startEpoch!==epoch){acquired.getTracks().forEach(track=>track.stop());return}stream=acquired;
      const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(x=>MediaRecorder.isTypeSupported(x));
      if(!mime)throw Error('Desteklenen ses biçimi yok. Metin girişini kullanabilirsin.');
      recorder=new MediaRecorder(stream,{mimeType:mime});const chunks=[];let size=0,overflow=false;
      recorder.ondataavailable=event=>{size+=event.data.size;if(size>8*1024*1024){overflow=true;if(recorder.state==='recording')recorder.stop()}else if(event.data.size)chunks.push(event.data)};
      recorder.onerror=()=>{message('Mikrofon kaydı kesildi. Kaydı tekrar başlat veya metin gir.',true);micOff()};
      recorder.onstop=()=>{micOff();if(disposed){chunks.length=0;return}if(overflow){chunks.length=0;message('Ses bölümü 8 MB sınırını aştı. Daha kısa bölüm kaydet.',true);return}audio=new Blob(chunks,{type:mime});chunks.length=0;recorder.ondataavailable=null;recorder.onstop=null;recorder.onerror=null;recorder=null;processAudio()};
      recorder.start(1000);recording=true;started=Date.now();timer=setInterval(()=>{const seconds=Math.floor((Date.now()-started)/1000);$('[data-voice-timer]').textContent=String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0')},500);
      deadline=setTimeout(()=>{if(recorder?.state==='recording')recorder.stop()},90000);message('Dinleniyor. Hazır olduğunda “Duraklat ve işle”ye bas.');
    }catch(error){micOff();message(error.name==='NotAllowedError'?'Mikrofon izni verilmedi. Metin girişi kullanılabilir.':error.message,true)}finally{busy=false;controls()}
  });
  stop.addEventListener('click',()=>{if(recorder?.state==='recording')recorder.stop()});retry.addEventListener('click',processAudio);
  $('[data-voice-sources]').addEventListener('click',async()=>{
    const button=$('[data-voice-sources]'),results=$('[data-voice-source-results]');button.disabled=true;results.textContent='Resmî kaynak dizini kontrol ediliyor…';
    try{const data=await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/sources',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:$('[data-voice-source-query]').value})}));
      results.replaceChildren();const notice=document.createElement('p');notice.className='voice-help';notice.textContent=data.notice;results.append(notice);
      for(const item of data.references){const section=document.createElement('details'),heading=document.createElement('summary'),text=document.createElement('p');heading.textContent=item.institution+' · '+item.title;const link=document.createElement('a');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Resmî belgeyi aç';text.textContent=(item.excerpts||[]).join('\n\n')+' · Erişim: '+item.retrieved_at;section.append(heading,text,link);results.append(section)}
      if(!data.references.length)results.append(document.createTextNode('Bu konuda dizin eşleşmesi bulunamadı; klinik güvenlik değerlendirmesi yapılmadı.'));
    }catch(error){results.textContent=error.message}finally{button.disabled=false}
  });
  async function assessClinical(manual=true){
    const button=$('[data-voice-clinical]'),host=$('[data-voice-clinical-results]');if(busy||recording||!consent.checked)return;
    const clinical=context();delete clinical.appointment;delete clinical.fields.first_name;delete clinical.fields.last_name;const snapshot=JSON.stringify(clinical);if(!manual&&snapshot===lastClinicalInput)return;lastClinicalInput=snapshot;const request=++clinicalRequest;button.disabled=true;host.textContent='Resmî belge içeriğiyle değerlendiriliyor…';
    try{const result=await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/clinical',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({context:JSON.parse(snapshot),consent:true})}));
      const current=context();delete current.appointment;delete current.fields.first_name;delete current.fields.last_name;if(request!==clinicalRequest||snapshot!==JSON.stringify(current))throw Error('Hasta bilgileri değişti; güncel bilgilerle yeniden değerlendir.');
      host.replaceChildren();const notice=document.createElement('p');notice.textContent=result.notice;host.append(notice);
      for(const item of result.items){const card=document.createElement('article');for(const text of ['Hekim kontrolü: '+item.consideration,'Hasta bilgisi: '+item.patient_quote,'Tamamlanacak bilgi: '+item.missing_information,...(item.alternative?['Değerlendirilebilecek seçenek: '+item.alternative]:[]),'Belge dayanağı: '+item.source_quote]){const p=document.createElement('p');p.textContent=text;card.append(p)}const source=result.references.find(r=>r.id===item.source_id);const link=document.createElement('a');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=source.institution+' · '+source.title;card.append(link);host.append(card)}
      if(!result.items.length)host.append(document.createTextNode('Doğrulanmış bir kontrol noktası üretilemedi. Bu, risk bulunmadığı anlamına gelmez.'));
      if(result.unavailable.length)host.append(document.createTextNode('Bazı kaynaklara erişilemedi.'));
    }catch(error){if(!disposed&&request===clinicalRequest)host.textContent=error.message}finally{if(request===clinicalRequest)button.disabled=false}
  }
  $('[data-voice-clinical]').addEventListener('click',()=>assessClinical(true).catch(error=>message(error.message,true)));
  textButton.addEventListener('click',async()=>{
    if(!consent.checked){message('Metin aktarımı onayını işaretle.',true);return}
    busy=true;controls();message('Metindeki alanlar çıkarılıyor…');
    try{merge(await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/text',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({transcript:transcript.value,consent:true,context:context()})})))}catch(error){message(error.message,true)}finally{busy=false;controls()}
  });
  save.addEventListener('click',async()=>{
    if(!$('[data-voice-confirm]').checked){message('Seçilen alanları kontrol edip onay kutusunu işaretle.',true);return}
    currentFields();const fields={};Object.entries(fieldState).forEach(([name,item])=>{if(item.selected&&item.value.trim())fields[name]=item.value.trim()});
    const teeth=teethState.filter(item=>Array.from(root.querySelectorAll('[data-tooth-key]:checked')).some(input=>input.dataset.toothKey===item.tooth+':'+item.status)).map(item=>({tooth:item.tooth,status:item.status,note:'Sesli muayeneden hekim tarafından doğrulandı.'}));
    let appointment=null;if($('[data-voice-save-appointment]').checked)appointment={title:$('[data-voice-appointment-title]').value,start_at:$('[data-voice-appointment-start]').value,end_at:$('[data-voice-appointment-end]').value};
    busy=true;controls();message('Onayladığın alanlar kaydediliyor…');
    try{const result=await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/apply',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_key:requestKey,revision,confirmed:true,fields,teeth,appointment})}));clearPrivateDraft();location.assign(result.patient_url+'?voice_saved=1')}
    catch(error){message(error.message,true)}finally{busy=false;controls()}
  });
  $('[data-voice-discard]').addEventListener('click',()=>{if(busy||recording)return;if(!confirm('Kaydedilmemiş muayene taslağı temizlensin mi?'))return;clearPrivateDraft();message('Taslak ve geçici görüşme verileri temizlendi.')});
  window.addEventListener('beforeunload',event=>{if(recording||busy||unsaved||audio){event.preventDefault();event.returnValue=''}});
  transcript.addEventListener('input',()=>{unsaved=!!transcript.value.trim()||Object.keys(fieldState).length>0});
  window.addEventListener('pagehide',()=>{disposed=true;clearPrivateDraft()});
  window.addEventListener('pageshow',()=>{disposed=false});
  fetch('/voice-exams/capabilities',{credentials:'same-origin',cache:'no-store'}).then(jsonResponse).then(data=>{available=data.enabled;message(available?'Muayeneyi başlatabilir veya metin ekleyebilirsin.':'Sesli muayene henüz etkinleştirilmedi.');controls()}).catch(()=>message('Sesli muayene durumuna erişilemedi. Sayfayı tekrar açabilirsin.',true));
  if(location.hash==='#voice-exam')root.open=true;
})();
