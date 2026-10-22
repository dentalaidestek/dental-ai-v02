(()=>{
  const root=document.getElementById('voice-device-check');if(!root)return;
  const $=s=>root.querySelector(s),start=$('[data-device-start]'),stop=$('[data-device-stop]'),status=$('[data-device-status]'),level=$('[data-device-level]'),results=$('[data-device-results]');
  let epoch=0,stream=null,ctx=null,source=null,node=null,timer=null,packets=0,samples=0,peak=0;
  function close(){epoch++;clearTimeout(timer);node?.disconnect();source?.disconnect();if(node)node.port.onmessage=null;stream?.getTracks().forEach(t=>t.stop());ctx?.close().catch(()=>{});node=null;source=null;stream=null;ctx=null;level.value=0;start.disabled=false;stop.disabled=true}
  stop.addEventListener('click',()=>{close();status.textContent='Test durduruldu. Mikrofon kapalı.'});
  start.addEventListener('click',async()=>{
    close();const at=epoch;packets=0;samples=0;peak=0;results.replaceChildren();start.disabled=true;stop.disabled=false;
    if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia||!window.AudioContext||!window.AudioWorkletNode){close();status.textContent='Canlı ses için HTTPS, mikrofon erişimi ve AudioWorklet destekleyen bir tarayıcı gerekiyor.';return}
    status.textContent='Mikrofon izni bekleniyor…';
    try{
      const acquired=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
      if(at!==epoch){acquired.getTracks().forEach(t=>t.stop());return}stream=acquired;
      ctx=new AudioContext({sampleRate:16000});await ctx.resume();await ctx.audioWorklet.addModule('/static/voice-pcm-worklet.js?v=1');
      if(at!==epoch)return;
      source=ctx.createMediaStreamSource(stream);node=new AudioWorkletNode(ctx,'voice-pcm');
      node.port.onmessage=event=>{if(at!==epoch||!(event.data instanceof ArrayBuffer))return;const values=new Int16Array(event.data);packets++;samples+=values.length;let current=0;for(const value of values)current=Math.max(current,Math.abs(value)/32768);peak=Math.max(peak,current);level.value=current;};
      source.connect(node);node.connect(ctx.destination);status.textContent='Şimdi birkaç kelime söyleyin. Test altı saniye sonra mikrofonu kapatacak.';
      timer=setTimeout(()=>{if(at!==epoch)return;const converted=packets>0&&samples>0,heard=peak>.01;close();status.textContent='Test bitti. Mikrofon kapalı.';const p=document.createElement('p');p.textContent=converted?(heard?'Mikrofon sinyali ve PCM16 dönüşümü bu cihazda alındı.':'Ses dönüşümü çalıştı fakat yeterli ses algılanmadı. Mikrofon seçimini kontrol edip konuşarak tekrar deneyin.'):'Mikrofondan canlı ses paketi alınamadı.';results.append(p);},6000);
    }catch(error){if(at!==epoch)return;close();status.textContent=error.name==='NotAllowedError'?'Mikrofon izni verilmedi. Tarayıcı izinlerini kontrol edip tekrar deneyin.':'Mikrofon testi başlatılamadı. Başka uygulamanın mikrofonu kullanmadığını kontrol edin.';}
  });
  window.addEventListener('pagehide',()=>{close();results.replaceChildren();status.textContent='Mikrofon kapalı.'});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){close();status.textContent='Sayfa arka plana geçti. Mikrofon kapatıldı.'}});
})();
