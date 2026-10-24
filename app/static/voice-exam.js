(()=>{
  const root=document.getElementById('voice-exam');if(!root||root.dataset.bound)return;root.dataset.bound='true';
  const $=s=>root.querySelector(s),status=$('.voice-exam-status'),start=$('[data-voice-start]'),stop=$('[data-voice-stop]'),retry=$('[data-voice-retry]'),textButton=$('[data-voice-text]'),transcript=$('[data-voice-transcript]'),consent=$('[data-voice-consent]'),review=$('.voice-review'),save=$('[data-voice-save]');
  const audioFile=$('[data-voice-audio-file]');
  const finalizeButton=$('[data-voice-finalize]');
  let failedLiveText='';
  let finalReady=false,finalBusy=false,finalRequested=false,finalSnapshot='',insights=[],historyFields={},historyRevision='',uncertainties=[],followups=[],sourceRequests=[],literatureTopics=[],unprocessed=false;
  const labels={first_name:'Ad',last_name:'Soyad',age:'Yaş',chief_complaint:'Başvuru şikâyeti',medical_history:'Sistemik hastalık / hasta beyanı',medications:'İlaç / hasta beyanı',allergies:'Alerji / hasta beyanı',clinical_findings:'Klinik bulgular',plan:'Hekimin belirttiği plan'};
  const states={CARIES:'Çürük',FILLING:'Dolgu',CROWN:'Kron',ROOT_CANAL:'Kanal tedavisi',EXTRACTED:'Çekilmiş',IMPLANT:'İmplant',OTHER:'Diğer'};
  let available=false,busy=false,recording=false,liveActive=false,liveQueue=[],disposed=false,recorder=null,stream=null,audio=null,timer=null,deadline=null,started=0,revision='',requestKey='',unsaved=false,fieldState={},teethState=[],appointmentQuote='',appointmentContext=null;
  let epoch=0,clinicalTimer=null,lastClinicalInput='',lastClinicalKey='',clinicalRequest=0;const pending=new Set();
  async function voiceFetch(url,options={}){
    const at=epoch,controller=new AbortController();pending.add(controller);
    try{const response=await fetch(url,{...options,signal:controller.signal});
      const body=await response.json();if(disposed||at!==epoch)throw Error('Görüşme kapatıldı.');
      return {ok:response.ok,json:async()=>body};
    }finally{pending.delete(controller)}
  }
  function clearPrivateDraft(){
    failedLiveText='';finalReady=false;finalBusy=false;finalRequested=false;finalSnapshot='';insights=[];historyFields={};historyRevision='';uncertainties=[];followups=[];sourceRequests=[];literatureTopics=[];unprocessed=false;$('[data-voice-followups]').replaceChildren();
    $('[data-voice-final-results]').replaceChildren();$('[data-voice-history-results]').replaceChildren();
    $('[data-voice-use-history]').hidden=true;$('[data-voice-history-confirm]').checked=false;
    root.dispatchEvent(new CustomEvent('voice-private-clear'));liveQueue=[];liveActive=false;epoch++;clearTimeout(clinicalTimer);lastClinicalInput='';lastClinicalKey='';clinicalRequest++;$('[data-voice-clinical]').disabled=false;pending.forEach(c=>c.abort());pending.clear();
    fieldState={};teethState=[];appointmentQuote='';appointmentContext=null;revision='';requestKey='';audio=null;
    if(audioFile)audioFile.value='';
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
  function controls(){root.dataset.finalReady=String(finalReady);if(audioFile)audioFile.disabled=!available||busy||recording||liveActive||finalBusy||!!audio;const stage=$('[data-voice-stage]');stage.textContent=finalBusy?'Son değerlendirme':recording||liveActive?'Görüşme sürüyor':busy||liveQueue.length?'Bilgiler işleniyor':finalReady?'Hekim onayı ve kayıt':review.hidden?'Başlamaya hazır':'Muayene taslağı';root.dispatchEvent(new CustomEvent('voice-review-state',{detail:{blocked:busy||recording||!!audio||finalBusy,processing:busy||liveQueue.length>0,finalBusy,finalReady}}));start.disabled=!available||busy||recording||liveActive||finalBusy;stop.disabled=!recording;textButton.disabled=!available||busy||recording||liveActive||finalBusy;save.disabled=!finalReady||busy||recording||liveActive||liveQueue.length>0||finalBusy||!!audio||unprocessed;finalizeButton.disabled=!available||busy||recording||liveActive||liveQueue.length>0||finalBusy||!!audio||unprocessed;const historyBlocked=busy||recording||liveActive||finalBusy;$('[data-voice-history]').disabled=historyBlocked;$('[data-voice-use-history]').disabled=historyBlocked;if(finalRequested&&!busy&&!recording&&!liveActive&&!liveQueue.length&&!finalBusy&&!audio&&!unprocessed){finalRequested=false;Promise.resolve().then(finalizeReview)};retry.disabled=busy||recording;consent.disabled=busy||recording||liveActive||finalBusy}
  function micOff(){clearInterval(timer);clearTimeout(deadline);stream?.getTracks().forEach(track=>track.stop());stream=null;recording=false;controls()}
  function invalidateFinal(){finalReady=false;finalSnapshot='';$('[data-voice-confirm]').checked=false;$('[data-voice-final-results]').textContent='Bilgiler değişti. Son değerlendirmeyi yeniden çalıştırın.';}
  function currentFields(){
    root.querySelectorAll('[data-field-row]').forEach(row=>{const item=fieldState[row.dataset.fieldRow];if(item){const edited=row.querySelector('textarea').value;if(edited!==item.value)item.edited=true;item.value=edited;item.selected=row.querySelector('input').checked}});
  }
  function render(){
    const host=$('[data-voice-fields]');host.replaceChildren();
    Object.entries(fieldState).forEach(([name,item])=>{
      const row=document.createElement('div');row.dataset.fieldRow=name;
      const label=document.createElement('label');label.className='voice-check';const choice=document.createElement('input');choice.type='checkbox';choice.checked=item.selected;label.append(choice,document.createTextNode(labels[name]));
      const value=document.createElement('textarea');value.rows=2;value.maxLength=3000;value.value=item.value;value.setAttribute('aria-label',labels[name]);const wrap=document.createElement('label');wrap.className='voice-field';wrap.append(value);
      const quote=document.createElement('small');quote.className='voice-field-quote';quote.textContent=(item.origin==='history'?'Önceki hekim onaylı kayıttaki dayanak: ':'Konuşmadaki dayanak: ')+item.quote;row.append(label,wrap,quote);host.append(row);
    });
    const teeth=$('[data-voice-teeth]');teeth.replaceChildren();
    teethState.forEach(item=>{const label=document.createElement('label');label.className='voice-check';const choice=document.createElement('input');choice.type='checkbox';choice.dataset.toothKey=item.tooth+':'+item.status;label.append(choice,document.createTextNode('Diş '+item.tooth+' — '+states[item.status]+'; bu hastanın diş şemasına bulgu olarak kaydet. Dayanak: '+item.quote));teeth.append(label)});
    $('[data-voice-appointment]').hidden=!appointmentQuote;$('[data-voice-appointment-quote]').textContent=appointmentQuote;
    review.hidden=false;unsaved=true;$('[data-voice-confirm]').checked=false;
  }
  async function jsonResponse(response){const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||'İşlem tamamlanamadı. Tekrar dene.');return result}
  function context(){
    currentFields();const fields={};for(const [name,item] of Object.entries(fieldState))fields[name]={value:item.value,quote:item.quote};
    const data={fields,teeth:teethState,source_requests:sourceRequests,literature_topics:literatureTopics,...(appointmentContext?{appointment:appointmentContext}:{})};if(new TextEncoder().encode(JSON.stringify(data)).length>24000)throw Error('Görüşme bağlamı sınırına ulaşıldı. Alanları kısaltıp son değerlendirmeyi yeniden çalıştır.');return data;
  }
  function riskKey(){return JSON.stringify(Object.fromEntries(['medical_history','medications','allergies','plan','clinical_findings'].map(k=>[k,fieldState[k]?.value||''])))}
  function invalidateClinical(){clinicalRequest++;$('[data-voice-clinical]').disabled=false;$('[data-voice-clinical-results]').textContent='Klinik bilgiler değişti; önceki değerlendirme geçersiz. Güncel bilgilerle yeniden değerlendirin.';}
  function merge(result){
    invalidateFinal();currentFields();const previousRiskKey=riskKey();const data=result.review;if(!revision)revision=result.revision;if(!requestKey)requestKey=key();
    unprocessed=!!failedLiveText;const next={};for(const [name,item] of Object.entries(data.fields||{})){if(!labels[name])continue;const old=fieldState[name];if(old?.edited&&old.value!==item.value){next[name]={...old};const note=labels[name]+' alanını hekim düzenledi; yeni konuşmadaki öneri: '+item.value;if(!uncertainties.includes(note))uncertainties.push(note)}else next[name]={...item,origin:old?.quote===item.quote?old.origin:undefined,edited:!!old?.edited,selected:!!old?.selected&&old.value===item.value}}for(const [name,old] of Object.entries(fieldState)){if(old.edited&&!next[name]){next[name]=old;uncertainties.push(labels[name]+' alanındaki hekim düzeltmesi korundu; konuşmadaki son düzeltmeyi kontrol edin.')}}fieldState=next;if(previousRiskKey!==riskKey())invalidateClinical();
    sourceRequests=data.source_requests||[];literatureTopics=data.literature_topics||[];teethState=data.teeth||[];appointmentQuote=data.appointment?.quote||'';appointmentContext=data.appointment?{quote:data.appointment.quote,acceptance_quote:data.appointment.acceptance_quote||''}:null;
    $('[data-voice-appointment-start]').value=data.appointment?.start_at||'';
    $('[data-voice-save-appointment]').checked=!!data.appointment?.agreed;
    if(appointmentQuote&&data.appointment?.acceptance_quote&&!appointmentQuote.includes(data.appointment.acceptance_quote))appointmentQuote+=' · Hasta: '+data.appointment.acceptance_quote;if(appointmentQuote)appointmentQuote+=data.appointment?.agreed?' · Konuşulan gün ve saat randevu taslağına eklendi. Onaylayıp kaydettiğinizde programınızda oluşur.':' · Tarih/saat veya karşılıklı kabul net değil; eksik bilgiyi tamamla.';
    const coaching=$('[data-voice-communication]');coaching.replaceChildren();const previous=insights;const incoming=[...(data.communication||[]),...(data.decision_barriers||[])];const unique=new Map();for(const item of [...previous,...incoming])unique.set((item.category||'communication')+':'+item.quote,item);insights=Array.from(unique.values()).slice(-24);for(const item of insights.filter(x=>!x.category)){const p=document.createElement('p');p.textContent='İletişim önerisi: '+item.observation+' · Dayanak: “'+item.quote+'” · Öneri: '+item.suggestion;coaching.append(p)}
    const barrierNames={COST:'Ücret kaygısı',FEAR:'Tedavi korkusu',TIME:'Zaman engeli',TRUST:'Güven ihtiyacı',UNDERSTANDING:'Açıklama ihtiyacı',UNCLEAR:'Neden net değil'};
    for(const item of insights.filter(x=>x.category)){const block=document.createElement('article');for(const text of [barrierNames[item.category]+': '+item.observation,'Dayanak: '+item.quote,'Sorulabilecek soru: '+item.question,'Açıklama önerisi: '+item.explanation]){const p=document.createElement('p');p.textContent=text;block.append(p)}coaching.append(block)}
    if(data.uncertain&&!uncertainties.includes(data.uncertain))uncertainties.push(data.uncertain);uncertainties=uncertainties.slice(-8);$('[data-voice-uncertain]').textContent=uncertainties.length?'Kontrol edilmesi gereken ifadeler: '+uncertainties.join(' · '):'';
    const asks=new Map(followups.map(x=>[x.quote+':'+x.question,x]));for(const item of data.follow_up_questions||[]){const key=item.quote+':'+item.question;asks.set(key,{...item,resolved:!!asks.get(key)?.resolved})}followups=Array.from(asks.values()).slice(-24);const askHost=$('[data-voice-followups]');askHost.replaceChildren();for(const item of followups){const article=document.createElement('article'),heading=document.createElement('strong'),detail=document.createElement('p');heading.textContent=(item.priority==='CLARIFY_NOW'?'Görüşmede netleştir: ':'Son kontrolde sor: ')+item.question;detail.textContent=item.reason+' · Dayanak: '+item.quote;const label=document.createElement('label'),resolved=document.createElement('input');label.className='voice-check';resolved.type='checkbox';resolved.checked=!!item.resolved;resolved.addEventListener('change',()=>{item.resolved=resolved.checked;article.classList.toggle('voice-question-resolved',item.resolved);invalidateFinal();controls()});label.append(resolved,document.createTextNode('Bu soruyu netleştirdim; yanıtını ilgili alana ekledim.'));article.classList.toggle('voice-question-resolved',!!item.resolved);article.append(heading,detail,label);askHost.append(article)}
    render();message(failedLiveText?'Yeni bölüm işlendi; önceki işlenemeyen metin hâlâ bekliyor. Duraklatıp korunan metni yeniden işleyin.':'Güncel görüşme özeti hazır. Alanları kontrol et veya dinlemeye devam et.',!!failedLiveText);clearTimeout(clinicalTimer);// Source verification is deferred to the one whole-examination review.
    clinicalTimer=null; // No automatic second clinical call; complete review runs on Finish.
  }
  async function drainLive(){
    if(busy||!liveQueue.length||disposed)return;
    const text=liveQueue.splice(0,liveQueue.length).join(' ');busy=true;controls();message('Görüşmenin klinik özeti güncelleniyor…');
    try{const result=await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/text',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({transcript:text,consent:consent.checked,context:context()})}));transcript.value=failedLiveText||result.review.transcript;merge(result)}
    catch(error){if(!disposed){unprocessed=true;finalRequested=false;failedLiveText=[failedLiveText,text].filter(Boolean).join(' ');transcript.value=failedLiveText;root.dataset.showReview='true';message(error.message+' Dinleme sürüyorsa devam edebilirsiniz. İşlenemeyen metin korundu; duraklattıktan sonra metinden alanları yeniden çıkarın.',true);if(failedLiveText.length+liveQueue.join(' ').length>18000){root.dispatchEvent(new CustomEvent('voice-live-stop'));message('İşlenemeyen konuşma sınırına ulaşıldı. Duraklatıldı; korunan metni kontrol edin.',true)}}}
    finally{busy=false;controls();if(liveQueue.length)drainLive()}
  }
  root.addEventListener('voice-live-state',event=>{liveActive=event.detail.active;if(liveActive)invalidateFinal();controls()});
  root.addEventListener('voice-live-ended',event=>{if(event.detail.finished){clearTimeout(clinicalTimer);if(!event.detail.flushed){uncertainties.push('Son konuşma bölümünün eksiksiz aktarıldığı doğrulanamadı.');$('[data-voice-uncertain]').textContent=uncertainties.join(' · ');}finalRequested=true;controls()}});
  root.addEventListener('voice-live-segment',event=>{if(disposed)return;invalidateFinal();const text=event.detail.text;if(typeof text!=='string'||!text)return;unsaved=true;liveQueue.push(text);if(liveQueue.join(' ').length>18000){root.dispatchEvent(new CustomEvent('voice-live-stop'));message('İşlenecek konuşma birikti. Dinleme duraklatıldı.',true)}drainLive()});
  async function processAudio(){
    if(!audio||busy)return;if(!consent.checked){message('Ses aktarımı onayını işaretle.',true);return}
    busy=true;controls();message('Ses bölümü çözümleniyor…');
    try{const metadata=new TextEncoder().encode(JSON.stringify(context()));const header=new Uint8Array(4);new DataView(header.buffer).setUint32(0,metadata.length,false);const packet=new Blob([header,metadata,audio]);const result=await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/audio',{method:'POST',body:packet,credentials:'same-origin',headers:{'Content-Type':'application/vnd.dentalai.voice-packet','X-Voice-Mime':audio.type,'X-Voice-Consent':'yes'}}));
      transcript.value=failedLiveText||result.review.transcript;merge(result);audio=null;retry.hidden=true;
    }catch(error){if(!disposed){finalRequested=false;message(error.message,true);retry.hidden=false}}finally{busy=false;controls()}
  }
  function audioDuration(file){
    return new Promise((resolve,reject)=>{
      const objectURL=URL.createObjectURL(file),player=new Audio();let timeout;
      function finish(error){clearTimeout(timeout);player.onloadedmetadata=null;player.onerror=null;player.removeAttribute('src');player.load();URL.revokeObjectURL(objectURL);error?reject(error):resolve()}
      player.preload='metadata';
      player.onloadedmetadata=()=>finish(!Number.isFinite(player.duration)||player.duration<=0||player.duration>90.5?Error('Ses dosyası en fazla 90 saniye olmalı. Daha kısa bir bölüm seç.'):null);
      player.onerror=()=>finish(Error('Ses dosyası okunamadı. MP3, WAV veya WebM biçimini dene.'));
      timeout=setTimeout(()=>finish(Error('Ses süresi okunamadı. Daha kısa bir MP3 veya WAV dosyası seç.')),8000);player.src=objectURL;
    });
  }
  if(audioFile)audioFile.addEventListener('change',async()=>{
    const file=audioFile.files?.[0];audioFile.value='';if(!file)return;
    if(!consent.checked){message('Ses dosyasını işlemeden önce aktarım onayını işaretle.',true);return}
    if(busy||recording||liveActive||finalBusy||audio||!available)return;
    if(file.size<100||file.size>8*1024*1024){message('En fazla 8 MB ses dosyası seç.',true);return}
    const supported=['audio/mpeg','audio/wav','audio/x-wav','audio/webm','audio/ogg','audio/mp4'];
    if(!supported.includes(file.type)){message('MP3, WAV, WebM, Ogg veya M4A ses dosyası seç.',true);return}
    busy=true;controls();message('Ses dosyasının süresi kontrol ediliyor…');const at=epoch;
    try{await audioDuration(file);if(disposed||at!==epoch)return;audio=new Blob([file],{type:file.type==='audio/x-wav'?'audio/wav':file.type});unsaved=true;invalidateFinal()}
    catch(error){message(error.message,true)}finally{busy=false;controls()}
    if(!disposed&&at===epoch&&audio)await processAudio();
  });
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
      invalidateFinal();recorder.start(1000);recording=true;started=Date.now();timer=setInterval(()=>{const seconds=Math.floor((Date.now()-started)/1000);$('[data-voice-timer]').textContent=String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0')},500);
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
    if(!manual&&finalRequested)return;const button=$('[data-voice-clinical]'),host=$('[data-voice-clinical-results]');if(busy||recording||finalBusy||!consent.checked)return;
    const clinical=context();delete clinical.appointment;delete clinical.fields.first_name;delete clinical.fields.last_name;const snapshot=JSON.stringify(clinical);const clinicalKey=JSON.stringify(Object.fromEntries(['medical_history','medications','allergies','plan','clinical_findings'].map(k=>[k,clinical.fields[k]?.value||''])));if(!manual&&(snapshot===lastClinicalInput||clinicalKey===lastClinicalKey||!['medical_history','medications','allergies','plan','clinical_findings'].some(k=>clinical.fields[k]?.value)))return;const request=++clinicalRequest;button.disabled=true;host.textContent='Resmî belge içeriğiyle değerlendiriliyor…';
    try{const result=await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/clinical',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({context:JSON.parse(snapshot),consent:true})}));
      const current=context();delete current.appointment;delete current.fields.first_name;delete current.fields.last_name;if(request!==clinicalRequest||snapshot!==JSON.stringify(current))throw Error('Hasta bilgileri değişti; güncel bilgilerle yeniden değerlendir.');
      lastClinicalInput=snapshot;lastClinicalKey=clinicalKey;host.replaceChildren();const notice=document.createElement('p');notice.textContent=result.notice;host.append(notice);
      for(const item of result.items){const card=document.createElement('article');for(const text of ['Hekim kontrolü: '+item.consideration,'Hasta bilgisi: '+item.patient_quote,'Tamamlanacak bilgi: '+item.missing_information,...(item.alternative?['Değerlendirilebilecek seçenek: '+item.alternative]:[]),'Belge dayanağı: '+item.source_quote]){const p=document.createElement('p');p.textContent=text;card.append(p)}const source=result.references.find(r=>r.id===item.source_id);const link=document.createElement('a');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=source.institution+' · '+source.title;card.append(link);host.append(card)}
      if(!result.items.length)host.append(document.createTextNode('Doğrulanmış bir kontrol noktası üretilemedi. Bu, risk bulunmadığı anlamına gelmez.'));
      if(result.unavailable.length)host.append(document.createTextNode('Bazı kaynaklara erişilemedi.'));
    }catch(error){if(!disposed&&request===clinicalRequest)host.textContent=error.message}finally{if(request===clinicalRequest)button.disabled=false}
  }
  $('[data-voice-clinical]').addEventListener('click',()=>assessClinical(true).catch(error=>message(error.message,true)));
  textButton.addEventListener('click',async()=>{
    if(!consent.checked){message('Metin aktarımı onayını işaretle.',true);return}
    invalidateFinal();busy=true;controls();message('Metindeki alanlar çıkarılıyor…');
    try{const retried=await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/text',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({transcript:transcript.value,consent:true,context:context()})}));failedLiveText='';merge(retried)}catch(error){message(error.message,true)}finally{busy=false;controls()}
  });
  function snapshot(){return JSON.stringify({context:context(),insights,uncertain:uncertainties,followups,appointment:[$('[data-voice-appointment-title]').value,$('[data-voice-appointment-start]').value,$('[data-voice-appointment-end]').value]})}
  function reviewSection(host,title,count){
    const section=document.createElement('details'),heading=document.createElement('summary');section.className='voice-result-section';
    const label=document.createElement('span');label.textContent=title;heading.append(label);
    if(count){const badge=document.createElement('span');badge.className='voice-result-count';badge.textContent=String(count);heading.append(badge)}
    section.append(heading);host.append(section);return section;
  }
  function reviewDetail(host,label,value){
    if(!value?.trim())return;const group=document.createElement('div'),heading=document.createElement('dt'),text=document.createElement('dd');
    heading.textContent=label;text.textContent=value;group.append(heading,text);host.append(group);
  }
  function reviewHeadline(value){
    const text=String(value||'Klinik değerlendirme').trim();if(text.length<=100)return text;
    const short=text.slice(0,97);return short.slice(0,short.lastIndexOf(' ')>40?short.lastIndexOf(' '):short.length)+'…';
  }
  function finalList(host,title,items,seen){
    const unique=items.filter(item=>{const key=JSON.stringify([item.text?.trim(),item.quote?.trim()]);if(!item.text?.trim()||seen.has(key))return false;seen.add(key);return true});
    if(!unique.length)return;const section=reviewSection(host,title,unique.length);
    for(const item of unique){const article=document.createElement('article'),body=document.createElement('dl');reviewDetail(body,'Bilgi',item.text);reviewDetail(body,'Dayanak',item.quote);article.append(body);section.append(article)}
  }
  function renderFinalReview(host,result,insights){
    host.replaceChildren();const clinicalKeys=new Set(),seen=new Set(result.clinical_items.map(item=>JSON.stringify([item.consideration?.trim(),item.patient_quote?.trim()])));
    finalList(host,'Muayene özeti',result.summary,seen);
    for(const item of result.clinical_items){
      const key=JSON.stringify([item.consideration?.trim(),item.patient_quote?.trim()]);if(clinicalKeys.has(key))continue;clinicalKeys.add(key);
      const section=reviewSection(host,reviewHeadline(item.consideration)),body=document.createElement('dl');
      reviewDetail(body,'Dayanak · konuşma',item.patient_quote);reviewDetail(body,'Dayanak · literatür',item.source_quote);
      const source=result.references.find(x=>x.id===item.source_id);
      if(source){const link=document.createElement('a');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=source.institution+' · '+source.title;link.className='voice-result-source';body.append(link)}
      reviewDetail(body,'Değerlendirme',item.consideration);reviewDetail(body,'Netleştirilecek bilgi',item.missing_information);reviewDetail(body,'Öneri',item.alternative);section.append(body);
    }
    const communication=insights.filter((item,index,items)=>items.findIndex(other=>other.quote===item.quote&&other.observation===item.observation)===index);
    if(communication.length){const section=reviewSection(host,'Hasta yaklaşımı ve iletişim',communication.length);for(const item of communication){const article=document.createElement('article'),body=document.createElement('dl');reviewDetail(body,'Gözlem',item.observation);reviewDetail(body,'Dayanak',item.quote);reviewDetail(body,'Sorulabilecek soru',item.question);reviewDetail(body,'Öneri',item.explanation||item.suggestion);article.append(body);section.append(article)}}
    finalList(host,'Netleştirilecek sorular',result.questions,seen);finalList(host,'Çelişkili bilgiler',result.contradictions,seen);
    const coverage=reviewSection(host,'Kaynaklar ve değerlendirme kapsamı',result.references.length),body=document.createElement('dl');
    reviewDetail(body,'Kapsam',result.notice);
    if(!result.clinical_items.length)reviewDetail(body,'Klinik kontrol','Kaynakla doğrulanmış bir kontrol noktası üretilmedi. Bu sonuç güvenlik onayı değildir.');
    if(result.review_status?.rejected_clinical_items)reviewDetail(body,'Dayanağı doğrulanamayan öneriler','Hasta veya kaynak dayanağı doğrulanamayan öneriler gösterilmedi.');
    if(result.unavailable.length)reviewDetail(body,'Eksik değerlendirme','Bazı konularda uygun kaynak bulunamadı veya kaynaklara erişilemedi.');
    coverage.append(body);
    const evidenceLabels={guideline:'Kılavuz',systematic_review:'Sistematik derleme',meta_analysis:'Meta-analiz',background_review:'Arka plan derlemesi',professional_information:'Meslek kuruluşu bilgisi'};
    for(const source of result.references){const line=document.createElement('p'),link=document.createElement('a');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=source.institution+' · '+source.title;line.append(link);const meta=document.createElement('small');meta.textContent=[evidenceLabels[source.evidence_level]||'Kaynak belgesi',source.publication_year,source.clinical_use===false?'Klinik öneriye dayanak yapılmadı':'',...(source.topic_labels||[])].filter(Boolean).join(' · ');line.append(meta);coverage.append(line)}
  }
  async function finalizeReview(){
    if(disposed||finalBusy||busy||recording||liveActive||liveQueue.length||audio||unprocessed)return;
    if(!consent.checked){message('İşleme onayını kontrol et.',true);return}
    if(finalReady&&finalSnapshot===snapshot()){message('Güncel son değerlendirme zaten hazır; alanları kontrol ederek onaylayabilirsiniz.');return}
    finalReady=false;$('[data-voice-confirm]').checked=false;finalBusy=true;controls();message('Tüm muayene bilgileri birlikte değerlendiriliyor…');
    let before;
    try{before=snapshot();const result=await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/finalize',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({context:context(),insights,uncertain:uncertainties.join(' · ').slice(0,3000),consent:true})}));
      if(before!==snapshot())throw Error('Bilgiler değişti. Son değerlendirmeyi güncel bilgilerle tekrarla.');
      if(revision&&revision!==result.revision)throw Error('Hasta dosyası görüşme sırasında değişmiş. Kaydetmeden önce dosyayı yeniden kontrol et.');
      if(!revision)revision=result.revision;const host=$('[data-voice-final-results]');host.replaceChildren();
      renderFinalReview(host,result.final,insights);
      finalSnapshot=before;finalReady=true;review.hidden=false;host.scrollIntoView?.({behavior:'smooth',block:'start'});unsaved=true;message('Son değerlendirme hazır. Açık noktaları ve kaydedilecek alanları kontrol ederek onayla.');
    }catch(error){if(!disposed){finalReady=false;$('[data-voice-final-results]').textContent=error.message;message(error.message,true)}}finally{finalBusy=false;controls()}
  }
  finalizeButton.addEventListener('click',()=>{finalRequested=false;return finalizeReview()});
  root.addEventListener('input',event=>{if(event.target?.type!=='checkbox'&&event.target?.closest?.('[data-voice-fields], [data-voice-appointment]')){currentFields();invalidateFinal();invalidateClinical();controls()}});
  $('[data-voice-history]').addEventListener('click',async()=>{
    if(busy||recording||liveActive||finalBusy)return;busy=true;controls();const host=$('[data-voice-history-results]');host.textContent='Önceki hekim onaylı kayıtlar getiriliyor…';
    try{const result=await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/history',{credentials:'same-origin',cache:'no-store'}));historyFields=result.fields;historyRevision=result.revision;host.replaceChildren();const note=document.createElement('p');note.textContent=result.notice;host.append(note);for(const [name,item] of Object.entries(historyFields)){const p=document.createElement('p');p.textContent=labels[name]+': '+item.value+' (Kayıt #'+item.analysis_id+')';host.append(p)}if(!Object.keys(historyFields).length){const p=document.createElement('p');p.textContent='Önceki hekim onaylı sesli muayeneden aktarılabilecek bilgi bulunamadı. Diğer hasta kayıtlarını ayrıca kontrol edin.';host.append(p)}$('[data-voice-use-history]').hidden=!Object.keys(historyFields).length;
    }catch(error){host.textContent=error.message}finally{busy=false;controls()}
  });
  $('[data-voice-use-history]').addEventListener('click',()=>{
    if(busy||recording||liveActive||finalBusy)return;if(!$('[data-voice-history-confirm]').checked){message('Önceki bilgileri hastayla doğruladığını onayla.',true);return}
    currentFields();for(const [name,item] of Object.entries(historyFields)){if(!fieldState[name])fieldState[name]={value:item.value,quote:item.quote,selected:false,origin:'history'};else if(fieldState[name].value!==item.value){const detail=labels[name]+' için önceki kayıt: '+item.value+'; bu görüşme: '+fieldState[name].value;if(!uncertainties.includes(detail))uncertainties.push(detail)}}
    uncertainties=uncertainties.slice(-8);if(!revision)revision=historyRevision;if(!requestKey)requestKey=key();invalidateFinal();render();$('[data-voice-uncertain]').textContent=uncertainties.join(' · ');controls();message('Doğruladığın önceki bilgiler bağlama eklendi. Çelişkili ifadeler ayrıca gösteriliyor.');
  });
  save.addEventListener('click',async()=>{
    if(busy||recording||liveActive||finalBusy||liveQueue.length||audio||unprocessed||!finalReady||finalSnapshot!==snapshot()){message('Önce dinlemeyi bitirip güncel bilgilerle son değerlendirmeyi tamamla.',true);return}
    if(!$('[data-voice-confirm]').checked){message('Seçilen alanları kontrol edip onay kutusunu işaretle.',true);return}
    currentFields();const fields={};Object.entries(fieldState).forEach(([name,item])=>{if(item.selected&&item.value.trim())fields[name]=item.value.trim()});
    const teeth=teethState.filter(item=>Array.from(root.querySelectorAll('[data-tooth-key]:checked')).some(input=>input.dataset.toothKey===item.tooth+':'+item.status)).map(item=>({tooth:item.tooth,status:item.status,note:'Sesli muayeneden hekim tarafından doğrulandı.'}));
    let appointment=null;if($('[data-voice-save-appointment]').checked)appointment={title:$('[data-voice-appointment-title]').value,start_at:$('[data-voice-appointment-start]').value,end_at:$('[data-voice-appointment-end]').value};
    busy=true;controls();message('Onayladığın alanlar kaydediliyor…');
    try{const result=await jsonResponse(await voiceFetch('/patients/'+root.dataset.patientId+'/voice-exam/apply',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_key:requestKey,revision,confirmed:true,fields,teeth,appointment})}));clearPrivateDraft();location.assign(result.patient_url+'?voice_saved=1')}
    catch(error){message(error.message,true)}finally{busy=false;controls()}
  });
  $('[data-voice-discard]').addEventListener('click',()=>{if(busy||recording||liveActive||finalBusy)return;if(!confirm('Kaydedilmemiş muayene taslağı temizlensin mi?'))return;clearPrivateDraft();message('Taslak ve geçici görüşme verileri temizlendi.')});
  window.addEventListener('beforeunload',event=>{if(recording||liveActive||busy||finalBusy||unsaved||audio){event.preventDefault();event.returnValue=''}});
  transcript.addEventListener('input',()=>{unprocessed=!!transcript.value.trim();invalidateFinal();controls();unsaved=!!transcript.value.trim()||Object.keys(fieldState).length>0});
  window.addEventListener('pagehide',()=>{disposed=true;clearPrivateDraft()});
  window.addEventListener('pageshow',()=>{disposed=false});
  fetch('/voice-exams/capabilities',{credentials:'same-origin',cache:'no-store'}).then(jsonResponse).then(data=>{available=data.enabled;message(available?'Muayeneyi başlatabilir veya metin ekleyebilirsin.':'Sesli muayene henüz etkinleştirilmedi.');controls()}).catch(()=>message('Sesli muayene durumuna erişilemedi. Sayfayı tekrar açabilirsin.',true));
  if(location.hash==='#voice-exam')root.open=true;
})();

