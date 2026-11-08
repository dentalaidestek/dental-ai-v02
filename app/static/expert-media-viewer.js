/* Authenticated post images stay on this page; no original-file navigation. */
(() => {
  'use strict';
  if (window.DentalMediaViewer) return;
  let dialog, image, stage, position, zoomLabel, message, retry, previous, next;
  let items=[], index=0, scale=1, x=0, y=0, opener=null, scroll=0, overflow='', entry=null, sequence=0;
  const pointers=new Map();
  let gesture=null,closing=false;
  function node(tag, cls, text){const n=document.createElement(tag);if(cls)n.className=cls;if(text)n.textContent=text;return n;}
  function control(label,text,fn){const b=node('button','',text);b.type='button';b.setAttribute('aria-label',label);b.addEventListener('click',fn);return b;}
  function url(raw){try{const u=new URL(raw,location.href);return u.origin===location.origin&&u.pathname.startsWith('/api/expert-social/media/')?u.href:null;}catch{return null;}}
  function layout(){
    if(!stage||!image)return;
    const ratio=Math.min(stage.clientWidth/(image.naturalWidth||1),stage.clientHeight/(image.naturalHeight||1));
    const maxX=Math.max(0,((image.naturalWidth||0)*ratio*scale-stage.clientWidth)/2);
    const maxY=Math.max(0,((image.naturalHeight||0)*ratio*scale-stage.clientHeight)/2);
    x=Math.max(-maxX,Math.min(maxX,x));y=Math.max(-maxY,Math.min(maxY,y));
    image.style.transform=`translate(${x}px, ${y}px) scale(${scale})`;
    zoomLabel.textContent=Math.round(scale*100)+'%';
    stage.dataset.zoomed=String(scale>1);
  }
  function zoom(value){scale=Math.max(1,Math.min(5,value));if(scale===1)x=y=0;layout();}
  function reset(){scale=1;x=y=0;pointers.clear();gesture=null;layout();}
  function load(){
    const at=++sequence;reset();image.hidden=true;retry.hidden=true;
    position.textContent=`${index+1} / ${items.length}`;message.textContent='Görsel yükleniyor…';
    previous.hidden=next.hidden=items.length<2;previous.disabled=index===0;next.disabled=index===items.length-1;
    image.onload=()=>{if(at!==sequence)return;image.hidden=false;message.textContent='';layout();};
    image.onerror=()=>{if(at!==sequence)return;image.hidden=true;message.textContent='Görsel açılamadı.';retry.hidden=false;};
    image.alt=`Gönderi görseli ${index+1} / ${items.length}`;
    image.src=items[index];
  }
  function slide(offset){const target=index+offset;if(target<0||target>=items.length)return;index=target;load();}
  function finish(){
    if(!dialog?.open)return;
    sequence++;dialog.close();image.removeAttribute('src');items=[];pointers.clear();gesture=null;
    document.body.style.overflow=overflow;
    window.scrollTo(0,scroll);opener?.focus?.({preventScroll:true});opener=null;entry=null;closing=false;
  }
  function close(){if(!dialog?.open||closing)return;if(history.state?.dentalMedia===entry){closing=true;history.back();}else finish();}
  function setup(){
    if(dialog)return;
    dialog=node('dialog','ds-media-viewer');dialog.id='dentalMediaViewer';dialog.setAttribute('aria-label','Gönderi görselleri');
    const head=node('header');position=node('span');position.dataset.mediaPosition='';
    const closeButton=control('Görseli kapat','×',close);head.append(position,closeButton);
    stage=node('div','ds-media-stage');image=node('img');image.draggable=false;
    message=node('p','ds-media-message');message.setAttribute('role','status');
    retry=control('Görseli yeniden yükle','Yeniden dene',load);retry.hidden=true;
    stage.append(image,message,retry);
    const tools=node('footer');previous=control('Önceki görsel','‹',()=>slide(-1));next=control('Sonraki görsel','›',()=>slide(1));
    zoomLabel=node('output');zoomLabel.dataset.mediaZoom='';zoomLabel.setAttribute('aria-label','Yakınlaştırma');
    tools.append(previous,control('Uzaklaştır','−',()=>zoom(scale-.5)),zoomLabel,control('Yakınlaştır','+',()=>zoom(scale+.5)),control('Görseli sığdır','Sığdır',()=>zoom(1)),next);
    dialog.append(head,stage,tools);document.body.append(dialog);
    dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
    dialog.addEventListener('click',event=>{if(event.target===dialog)close();});
    dialog.addEventListener('keydown',event=>{
      if(event.key==='ArrowLeft'){event.preventDefault();slide(-1);}
      if(event.key==='ArrowRight'){event.preventDefault();slide(1);}
      if(event.key==='+'||event.key==='='){event.preventDefault();zoom(scale+.5);}
      if(event.key==='-'){event.preventDefault();zoom(scale-.5);}
      if(event.key==='0'){event.preventDefault();zoom(1);}
    });
    stage.addEventListener('dblclick',()=>zoom(scale>1?1:2));
    stage.addEventListener('wheel',event=>{if(!event.ctrlKey)return;event.preventDefault();zoom(scale+(event.deltaY<0?.25:-.25));},{passive:false});
    const points=()=>[...pointers.values()];
    stage.addEventListener('pointerdown',event=>{
      if(event.target.closest('button'))return;
      pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});stage.setPointerCapture?.(event.pointerId);
      const p=points();gesture=p.length===2?{distance:Math.hypot(p[1].x-p[0].x,p[1].y-p[0].y),scale}:{startX:event.clientX,startY:event.clientY,x,y};
    });
    stage.addEventListener('pointermove',event=>{
      if(!pointers.has(event.pointerId))return;
      pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});const p=points();
      if(p.length===2&&gesture?.distance){zoom(gesture.scale*Math.hypot(p[1].x-p[0].x,p[1].y-p[0].y)/Math.max(1,gesture.distance));}
      else if(p.length===1&&gesture&&scale>1){x=gesture.x+event.clientX-gesture.startX;y=gesture.y+event.clientY-gesture.startY;layout();}
    });
    function pointerEnd(event){
      if(!pointers.has(event.pointerId))return;
      if(event.type==='pointerup'&&pointers.size===1&&scale===1&&gesture?.startX!==undefined){
        const dx=event.clientX-gesture.startX,dy=event.clientY-gesture.startY;
        if(Math.abs(dx)>60&&Math.abs(dy)<Math.abs(dx)*.7)slide(dx<0?1:-1);
      }
      pointers.delete(event.pointerId);const p=points();gesture=p.length===1?{startX:p[0].x,startY:p[0].y,x,y}:null;
    }
    stage.addEventListener('pointerup',pointerEnd);stage.addEventListener('pointercancel',pointerEnd);
    window.addEventListener('resize',layout);
    window.addEventListener('popstate',()=>{if(dialog.open&&history.state?.dentalMedia!==entry)finish();});
    window.addEventListener('pagehide',finish);window.addEventListener('dai:session-ending',finish);
  }
  function open(media,selected=0,trigger=null){
    const safe=media.slice(0,4).map(m=>url(typeof m==='string'?m:m.url)).filter(Boolean);if(!safe.length)return;
    setup();if(dialog.open)return;
    items=safe;index=Math.max(0,Math.min(selected,items.length-1));opener=trigger;scroll=scrollY;overflow=document.body.style.overflow;
    entry=Date.now().toString(36)+Math.random().toString(36).slice(2);history.pushState({...history.state,dentalMedia:entry},'');
    document.body.style.overflow='hidden';dialog.showModal();load();
  }
  window.DentalMediaViewer={open};
})();
