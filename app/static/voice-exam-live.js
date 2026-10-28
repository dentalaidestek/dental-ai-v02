(()=>{
  const root=document.getElementById('voice-exam');if(!root)return;
  const panel=root.querySelector('[data-live-panel]');if(!panel)return;
  const start=panel.querySelector('[data-live-start]'),pause=panel.querySelector('[data-live-pause]'),finish=panel.querySelector('[data-live-finish]'),status=panel.querySelector('[data-live-status]'),preview=panel.querySelector('[data-live-preview]'),consent=root.querySelector('[data-voice-consent]');
  let socket=null,stream=null,ctx=null,node=null,source=null,state='idle',reviewBlocked=false,generation=0,finished=false,batch='',batchTimer=null,setupTimer=null,flushDone=null,sessionTimer=null;
  let elapsed=0,clock=null,clockStarted=0,hasListened=false,lastFlush=false,incomplete=false,drainTimer=null;
  const reviewButton=panel.querySelector('[data-live-review]'),subtitle=panel.querySelector('[data-live-subtitle]'),timerLabel=panel.querySelector('[data-live-timer]');
  function drawTime(){if(timerLabel){const seconds=Math.floor((elapsed+(clockStarted?Date.now()-clockStarted:0))/1000);timerLabel.textContent=String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0')}}
  function stopClock(){if(clockStarted)elapsed+=Date.now()-clockStarted;clockStarted=0;clearInterval(clock);clock=null;drawTime()}
  const announce=(text)=>{status.textContent=text};
  function stateChanged(next){state=next;root.dataset.liveState=next;root.dataset.liveFinished=String(finished);root.dataset.hasListened=String(hasListened);root.dataset.liveStarted=String(hasListened||next==='listening');
    if(next==='listening')hasListened=true;
    root.dataset.hasListened=String(hasListened);
    if(next==='listening'&&!clockStarted){clockStarted=Date.now();clock=setInterval(drawTime,1000)}else if(next!=='listening')stopClock();
    if(subtitle)subtitle.textContent=next==='listening'?'Mikrofon açık':'Mikrofon kapalı';
    start.hidden=!['idle','paused','error'].includes(next)||finished;pause.hidden=next!=='listening';finish.hidden=!['listening','paused','error'].includes(next)||finished;
    if(reviewButton)reviewButton.hidden=!finished;
    
    const title=panel.querySelector('[data-live-title]');if(title)title.textContent=({idle:finished?'Dinleme tamamlandı':'Başlamaya hazır',connecting:'Mikrofon hazırlanıyor',listening:'Dinleniyor',stopping:'Dinleme durduruluyor',paused:'Duraklatıldı',error:hasListened?'Dinleme durdu':'Mikrofon açılamadı'})[next]||next;
    start.textContent=next==='paused'||(next==='error'&&hasListened)?'▶  Devam et':next==='error'?'Tekrar dene':'Mikrofonu başlat';
    if(next==='error'&&!hasListened)finish.hidden=true;
    start.disabled=reviewBlocked||!['idle','paused','error'].includes(state);pause.disabled=state!=='listening';finish.disabled=!['listening','paused','error'].includes(state);root.dispatchEvent(new CustomEvent('voice-live-state',{detail:{active:['connecting','listening','stopping'].includes(state)}}))}
  function microphoneOff(){node?.disconnect();if(node)node.port.onmessage=null;source?.disconnect();stream?.getTracks().forEach(t=>t.stop());if(ctx)ctx.close().catch(()=>{});node=null;source=null;stream=null;ctx=null;clearTimeout(setupTimer);clearTimeout(sessionTimer);clearTimeout(drainTimer)}
  function emitBatch(){clearTimeout(batchTimer);batchTimer=null;if(!batch)return;const text=batch;batch='';root.dispatchEvent(new CustomEvent('voice-live-segment',{detail:{text}}))}
  function closePrivate(){hasListened=false;finished=false;lastFlush=false;incomplete=false;stopClock();elapsed=0;drawTime();root.dataset.showReview='false';generation++;clearTimeout(batchTimer);batch='';preview.textContent='';microphoneOff();if(socket){socket.onmessage=null;socket.onclose=null;socket.onerror=null;socket.close();socket=null}stateChanged('idle')}
  function fail(message){incomplete=true;lastFlush=false;root.dataset.showReview='true';microphoneOff();emitBatch();socket?.close();socket=null;preview.textContent='';stateChanged('error');announce(message+(hasListened?' Son konuşma bölümü eksik olabilir; otomatik yeniden kayıt yapılmadı.':''))}
  async function begin(){
    if(!consent.checked){announce('Önce görüşmedeki kişileri bilgilendirip aktarım onayını işaretle.');return}
    if(reviewBlocked||!['idle','paused','error'].includes(state))return;
    if(!window.AudioContext||!window.AudioWorkletNode||!navigator.mediaDevices?.getUserMedia){announce('Bu cihazda canlı ses desteklenmiyor. Bölüm kaydı veya metin girişini kullan.');return}
    const at=++generation;finished=false;lastFlush=false;root.dataset.showReview='false';stateChanged('connecting');announce('Mikrofon ve canlı bağlantı hazırlanıyor…');
    try{
      const acquired=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
      if(at!==generation){acquired.getTracks().forEach(t=>t.stop());return}stream=acquired;
      ctx=new AudioContext({sampleRate:16000});await ctx.resume();await ctx.audioWorklet.addModule('/static/voice-pcm-worklet.js?v=1');
      if(at!==generation)return;
      socket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/patients/'+root.dataset.patientId+'/voice-exam/live');socket.binaryType='arraybuffer';
      setupTimer=setTimeout(()=>{if(at===generation&&state==='connecting')fail('Canlı bağlantı kurulamadı.')},22000);
      socket.onopen=()=>{if(at===generation)socket.send(JSON.stringify({type:'start',consent:true}))};
      socket.onmessage=event=>{
        if(at!==generation)return;
        try{
          const data=JSON.parse(event.data);
          if(data.type==='ready'){
            clearTimeout(setupTimer);source=ctx.createMediaStreamSource(stream);node=new AudioWorkletNode(ctx,'voice-pcm');
            node.port.onmessage=event=>{if(event.data?.type==='flushed'){flushDone?.();flushDone=null;return}if(!['listening','stopping'].includes(state))return;if(socket?.readyState!==WebSocket.OPEN||socket.bufferedAmount>64000){fail('Ses bağlantısı yavaşladı. Mikrofon durduruldu.');return}const samples=new Int16Array(event.data);let peak=0;for(const sample of samples)peak=Math.max(peak,Math.abs(sample)/32768);panel.style?.setProperty('--voice-level',String(Math.min(1,.15+peak*3)));socket.send(event.data)};
            source.connect(node);node.connect(ctx.destination);stateChanged('listening');sessionTimer=setTimeout(()=>{if(state==='listening'){stop(false);announce('Canlı oturum süresi dolmak üzere; dinleme duraklatıldı. Biriken metin korunuyor. Devam etmek için yeniden başlat.')}},540000);announce('Muayene dinleniyor. Konuşma metni geçici olarak birikiyor; değerlendirme bitişte yapılır.');
          }else if(data.type==='interim'){preview.textContent=data.text}
          else if(data.type==='final'){
            preview.textContent='';batch+=(batch?' ':'')+data.text;
            if(batch.length>6000){fail('İşlenecek konuşma sınırına ulaşıldı.');return}
            if(!batchTimer)batchTimer=setTimeout(emitBatch,8000);if(batch.length>=1000)emitBatch();
          }else if(data.type==='ended'){
            lastFlush=!!data.flushed;if(!lastFlush)incomplete=true;
            emitBatch();microphoneOff();socket?.close();socket=null;stateChanged(finished?'idle':'paused');root.dispatchEvent(new CustomEvent('voice-live-ended',{detail:{finished,flushed:lastFlush&&!incomplete}}));
            announce((finished?'Dinleme bitti. Alanlar işlendikten sonra özeti kontrol et.':'Duraklatıldı. Devam etmek için başlat.')+(data.flushed?'':' Son sözlerin döküme geçtiğini kontrol et.'));
          }else if(data.type==='error'){fail(data.message)}
        }catch(error){fail('Canlı yanıt işlenemedi.')}
      };
      socket.onerror=()=>{if(at===generation&&state!=='idle')fail('Canlı bağlantı kurulamadı.')};
      socket.onclose=()=>{if(at===generation&&['listening','connecting','stopping'].includes(state))fail('Canlı bağlantı kesildi.')};
    }catch(error){if(at===generation)fail(error.name==='NotAllowedError'?'Mikrofon erişimi engellendi. Tarayıcıda dentalai.tr site izinlerinden mikrofonu açın. Uygulama içindeyseniz Android uygulama mikrofon iznini de kontrol edin veya sayfayı Chrome’da açın.':error.name==='NotFoundError'?'Kullanılabilir mikrofon bulunamadı. Cihaz bağlantısını kontrol edin.':error.name==='NotReadableError'?'Mikrofon kullanılamıyor. Mikrofonu kullanan diğer uygulamaları kapatıp tekrar deneyin.':'Canlı ses başlatılamadı.')}
  }
  async function stop(end){
    if(['paused','error'].includes(state)&&!end)return;
    finished=end;if(['paused','error'].includes(state)){emitBatch();stateChanged('idle');root.dispatchEvent(new CustomEvent('voice-live-ended',{detail:{finished:true,flushed:lastFlush&&!incomplete}}));announce('Dinleme bitti. Özeti kontrol et.');return}
    if(state!=='listening')return;stateChanged('stopping');source?.disconnect();announce('Son konuşma bölümü tamamlanıyor…');
    if(node){await Promise.race([new Promise(resolve=>{flushDone=resolve;node.port.postMessage({type:'flush'})}),new Promise(resolve=>setTimeout(resolve,300))])}flushDone=null;if(state!=='stopping')return;microphoneOff();
    if(socket?.readyState===WebSocket.OPEN){socket.send(JSON.stringify({type:end?'finish':'pause'}));drainTimer=setTimeout(()=>{if(state==='stopping')fail('Son konuşma yanıtı zamanında gelmedi. Biriken metin korunuyor; metni kontrol edip değerlendirin.')},8000)}else fail('Bağlantı kesildi.');
  }
  if(reviewButton)reviewButton.addEventListener('click',()=>{root.dataset.showReview='true';const summary=root.querySelector('.voice-review');summary?.scrollIntoView?.({behavior:'smooth',block:'start'})});
  stateChanged('idle');
  start.addEventListener('click',begin);pause.addEventListener('click',()=>stop(false));finish.addEventListener('click',()=>stop(true));
  root.addEventListener('voice-review-state',event=>{reviewBlocked=event.detail.blocked;
    if(reviewButton)reviewButton.disabled=!!event.detail.processing||!!event.detail.finalBusy;
    if(finished&&state==='idle'){const title=panel.querySelector('[data-live-title]');if(title)title.textContent=event.detail.finalBusy?'Muayene değerlendiriliyor':event.detail.processing?'Konuşma işleniyor':event.detail.finalReady?'Muayene tamamlandı':'Dinleme tamamlandı'}
    start.disabled=reviewBlocked||!['idle','paused','error'].includes(state)});
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&state==='listening'){stream?.getTracks().forEach(track=>track.stop());stop(false)}});
  root.addEventListener('voice-live-stop',()=>{root.dataset.showReview='true';stop(false)});root.addEventListener('voice-private-clear',closePrivate);
  window.addEventListener('pagehide',closePrivate);
  fetch('/voice-exams/capabilities',{credentials:'same-origin',cache:'no-store'}).then(r=>r.json()).then(data=>{panel.hidden=!data.live_enabled}).catch(()=>{panel.hidden=true});
})();


