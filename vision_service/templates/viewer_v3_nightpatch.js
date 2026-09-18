// Dental AI nightly correction layer: keep teeth in their atlas sockets,
// close the two jaws as whole units, and expose panorama-derived 2-D cues.
(function(){
  const MIN=.50;
  let signals=[];
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const valid=v=>/^[1-4][1-8]$/.test(String(v??''));
  const fdi=v=>{const s=String(v??'').trim();if(valid(s))return Number(s);const m=s.match(/(?:^|\D)([1-4][1-8])(?:\D|$)/);return m?Number(m[1]):v};
  const upper=v=>['1','2'].includes(String(v)[0]);
  const center=b=>[(+b[0]+ +b[2])/2,(+b[1]+ +b[3])/2];
  const pct=(a,p)=>{const v=a.filter(Number.isFinite).sort((x,y)=>x-y);return v.length?v[Math.floor((v.length-1)*p)]:0};
  const score=x=>{const n=Number(x?.confidence??x?.score??0);return Number.isFinite(n)?(n>1?n/100:n):0};

  function acceptedFindings(){
    const out=[],seen=new Set();
    for(const x of result?.findings||[]){if(!x?.finding_code||score(x)<MIN)continue;const n=fdi(x.fdi),b=Array.isArray(x.bbox)?x.bbox:null,k=`${x.finding_code}:${valid(n)?n:(b?b.map(v=>Math.round(+v/30)).join(':'):'g')}`;if(seen.has(k))continue;seen.add(k);out.push({...x,fdi:n})}
    return out;
  }
  function tooth(n){return (result?.teeth||[]).find(t=>String(fdi(t?.fdi))===String(n))||null}
  function toothFindings(t){return acceptedFindings().filter(x=>String(fdi(x.fdi))===String(fdi(t.fdi)))}
  function toothSignals(t){return signals.filter(x=>String(x.fdi)===String(fdi(t.fdi)))}
  function gray(img,w,x,y){const i=(y*w+x)*4;return(img.data[i]+img.data[i+1]+img.data[i+2])/3}

  function cropData(t,pad=.07){
    const b=t.bbox.map(Number),w=Math.max(2,b[2]-b[0]),h=Math.max(2,b[3]-b[1]),sx=Math.max(0,b[0]-w*pad),sy=Math.max(0,b[1]-h*pad),sw=Math.min(panoImage.naturalWidth-sx,w*(1+2*pad)),sh=Math.min(panoImage.naturalHeight-sy,h*(1+2*pad)),c=document.createElement('canvas');c.width=Math.max(8,Math.round(sw));c.height=Math.max(8,Math.round(sh));const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(panoImage,sx,sy,sw,sh,0,0,c.width,c.height);return{c,ctx,img:ctx.getImageData(0,0,c.width,c.height),sx,sy}}

  function restorationSignal(t){
    const q=cropData(t),b=t.bbox.map(Number),L=clamp(Math.floor(b[0]-q.sx),0,q.c.width-1),R=clamp(Math.ceil(b[2]-q.sx),0,q.c.width-1),T=clamp(Math.floor(b[1]-q.sy),0,q.c.height-1),B=clamp(Math.ceil(b[3]-q.sy),0,q.c.height-1),h=Math.max(1,B-T),y0=upper(t.fdi)?Math.floor(T+h*.52):T,y1=upper(t.fdi)?B:Math.ceil(T+h*.48),vals=[];
    for(let y=y0;y<=y1;y++)for(let x=L;x<=R;x++)vals.push(gray(q.img,q.c.width,x,y));if(vals.length<30)return null;const med=pct(vals,.5),p98=pct(vals,.98),thr=Math.max(205,med+48,pct(vals,.94));if(p98-med<48)return null;
    let minx=Infinity,miny=Infinity,maxx=-Infinity,maxy=-Infinity,n=0,sum=0;for(let y=y0;y<=y1;y++)for(let x=L;x<=R;x++){const g=gray(q.img,q.c.width,x,y);if(g>=thr){n++;sum+=g;minx=Math.min(minx,x);maxx=Math.max(maxx,x);miny=Math.min(miny,y);maxy=Math.max(maxy,y)}}
    const area=Math.max(1,(R-L+1)*(y1-y0+1)),frac=n/area;if(!n||frac<.012||frac>.30||(sum/n)-med<42||(maxx-minx)<2||(maxy-miny)<1)return null;
    return{finding_code:'RADIOPAQUE_RESTORATION_SIGNAL',label:'Radyopak restorasyon işareti',fdi:fdi(t.fdi),bbox:[minx+q.sx,miny+q.sy,maxx+q.sx,maxy+q.sy],confidence:clamp(.64+((sum/n)-med-42)/120,.64,.95),evidence_type:'visual_signal'};
  }

  function computeSignals(){const out=[];for(const x of result?.teeth||[]){const t={...x,fdi:fdi(x.fdi)};if(!t.bbox||!valid(t.fdi))continue;const s=restorationSignal(t);if(s&&!out.some(v=>v.fdi===s.fdi&&v.finding_code===s.finding_code))out.push(s)}return out}

  function findJawRoot(){let best=null,bestN=0;jawScene?.scene?.traverse(o=>{if(!o.isGroup)return;let n=0;o.traverse(x=>{if(x.userData?.patientTooth)n++});if(n>bestN&&Math.abs(o.rotation.x+Math.PI/2)<.2){best=o;bestN=n}});return best}
  function toothBox(group){const THREE=window.D3.THREE,b=new THREE.Box3(),tmp=new THREE.Box3();let any=false;group.traverse(o=>{if(o.userData?.patientTooth){tmp.setFromObject(o);if(!any){b.copy(tmp);any=true}else b.union(tmp)}});return any?b:null}
  function jawType(group){let u=0,l=0;group.traverse(o=>{if(!o.userData?.patientTooth)return;const n=fdi(o.userData.tooth?.fdi);if(!valid(n))return;(upper(n)?u++:l++)});return u>=l?'upper':'lower'}

  function closeJaws(){
    const root=findJawRoot();if(!root||root.children.length<2)return;const a=root.children[0],b=root.children[1],up=jawType(a)==='upper'?a:b,lo=up===a?b:a;up.position.z=0;lo.position.z=0;root.updateMatrixWorld(true);const ub=toothBox(up),lb=toothBox(lo);if(!ub||!lb)return;const gap=ub.min.y-lb.max.y,target=.055,delta=gap-target,scale=Math.max(.001,Math.abs(root.scale.x||1)),move=clamp(delta/(2*scale),-16,16);up.position.z-=move;lo.position.z+=move;root.updateMatrixWorld(true);
    if(jawScene?.camera&&jawScene?.controls){const t=jawScene.controls.target.clone(),v=jawScene.camera.position.clone().sub(t).multiplyScalar(1.08);jawScene.camera.position.copy(t.add(v));jawScene.controls.update()}
    result.anatomy3d=result.anatomy3d||{};result.anatomy3d.interarch_position='reference_near_occlusion';result.anatomy3d.panorama_not_used_as_true_bite=true;
  }

  function addMarkers(){
    if(!jawScene?.scene)return;const THREE=window.D3.THREE;jawScene.scene.traverse(o=>{if(o.userData?.nightMarker)o.parent?.remove(o)});
    const items=[...acceptedFindings().map(x=>({...x,_sig:false})),...signals.map(x=>({...x,_sig:true}))];
    for(const it of items){const n=fdi(it.fdi);if(!valid(n))continue;let mesh=null;jawScene.scene.traverse(o=>{if(!mesh&&o.userData?.patientTooth&&String(fdi(o.userData.tooth?.fdi))===String(n))mesh=o});if(!mesh)continue;const color=it._sig?0x4fd7ff:/CARIES|PERIAPICAL|FRACTURE|RESORPTION/.test(it.finding_code)?0xff5f73:/ROOT|ENDO|POST/.test(it.finding_code)?0xff83b3:0xffc857,m=new THREE.Mesh(new THREE.SphereGeometry(1.15,16,12),new THREE.MeshStandardMaterial({color,emissive:color,emissiveIntensity:.28,transparent:true,opacity:.88,depthWrite:false}));m.position.set(0,0,2.0);m.userData.nightMarker=true;mesh.add(m)}
  }

  function renderResults(){
    const body=$('sheetBody');if(!body)return;const fs=acceptedFindings(),ss=signals;if($('findingsCount'))$('findingsCount').textContent=(fs.length||ss.length)?`(${fs.length}+${ss.length})`:'';body.innerHTML='';const note=document.createElement('div');note.className='sheet-note';note.textContent='İlk sayı ≥%50 motor bulgusu; ikinci sayı panoramikten çıkarılan güçlü görüntüsel işaret. Görüntüsel işaret tanı değildir.';body.appendChild(note);const items=[...fs.map(x=>({...x,k:'Bulgu'})),...ss.map(x=>({...x,k:'Görüntüsel işaret'}))];if(!items.length){const e=document.createElement('div');e.className='empty-card';e.textContent='≥%50 bulgu veya güçlü görüntüsel işaret yok.';body.appendChild(e);return}const list=document.createElement('div');list.className='finding-list';for(const x of items){const c=document.createElement('button');c.type='button';c.className='finding-card';const main=document.createElement('div');main.className='finding-main',title=document.createElement('div');title.className='finding-title';title.textContent=`${valid(fdi(x.fdi))?`${fdi(x.fdi)} • `:''}${x.label||x.finding_code}`;const sub=document.createElement('div');sub.className='finding-sub';sub.textContent=x.k;main.append(title,sub);const sc=document.createElement('div');sc.className='finding-score';sc.textContent=`%${Math.round(score(x)*100)}`;c.append(main,sc);c.onclick=()=>{const t=tooth(fdi(x.fdi));if(t)openTooth(t)};list.appendChild(c)}body.appendChild(list)
  }

  function axis(t){const p=t?.polygon;if(!Array.isArray(p)||p.length<6){const b=t.bbox.map(Number);return{cx:(b[0]+b[2])/2,cy:(b[1]+b[3])/2,vx:0,vy:1,len:b[3]-b[1]}}let mx=0,my=0;for(const q of p){mx+=+q[0];my+=+q[1]}mx/=p.length;my/=p.length;let xx=0,yy=0,xy=0;for(const q of p){const dx=+q[0]-mx,dy=+q[1]-my;xx+=dx*dx;yy+=dy*dy;xy+=dx*dy}const tr=xx+yy,det=xx*yy-xy*xy,disc=Math.sqrt(Math.max(0,tr*tr/4-det)),lam=tr/2+disc;let vx=xy,vy=lam-xx;if(Math.abs(vx)+Math.abs(vy)<1e-8){vx=0;vy=1}const z=Math.hypot(vx,vy)||1;vx/=z;vy/=z;if(vy<0){vx=-vx;vy=-vy}const pr=p.map(q=>(+q[0]-mx)*vx+(+q[1]-my)*vy);return{cx:mx,cy:my,vx,vy,len:Math.max(...pr)-Math.min(...pr)}}
  function contacts(t){const same=(result?.teeth||[]).map(x=>({...x,fdi:fdi(x.fdi)})).filter(x=>x.bbox&&valid(x.fdi)&&upper(x.fdi)===upper(fdi(t.fdi))).sort((a,b)=>center(a.bbox)[0]-center(b.bbox)[0]),i=same.findIndex(x=>String(x.fdi)===String(fdi(t.fdi))),pair=(a,b)=>{if(!a||!b)return null;const A=a.bbox.map(Number),B=b.bbox.map(Number),r=(B[0]-A[2])/Math.max(1,Math.min(A[2]-A[0],B[2]-B[0]));return r>.1?'aralık':r<-.1?'projeksiyonda örtüşme':'temas/belirsiz'};return{m:i>0?pair(same[i-1],same[i]):null,d:i>=0&&i<same.length-1?pair(same[i],same[i+1]):null}}

  function drawDetail(t){
    const q=cropTooth(t),ctx=q.canvas.getContext('2d'),a=axis(t),b=t.bbox.map(Number),L=clamp(Math.round(b[0]-q.sx),1,q.canvas.width-2),R=clamp(Math.round(b[2]-q.sx),1,q.canvas.width-2),T=clamp(Math.round(b[1]-q.sy),1,q.canvas.height-2),B=clamp(Math.round(b[3]-q.sy),1,q.canvas.height-2),h=Math.max(3,B-T),ya=Math.round(T+h*(upper(t.fdi)?.40:.18)),yb=Math.round(T+h*(upper(t.fdi)?.76:.56)),g=(x,y)=>gray(q.image,q.canvas.width,x,y),edge=(xa,xb)=>{let yy=null,bs=-1;for(let y=ya;y<=yb;y++){let s=0,n=0;for(let x=xa;x<=xb;x++){s+=Math.abs(g(x,y+1)-g(x,y-1));n++}if(n&&s/n>bs){bs=s/n;yy=y}}return yy},cl=edge(L,Math.round(L+(R-L)*.3)),cr=edge(Math.round(L+(R-L)*.7),R);ctx.save();if(Array.isArray(t.polygon)&&t.polygon.length>2){ctx.beginPath();t.polygon.forEach((p,i)=>{const x=p[0]-q.sx,y=p[1]-q.sy;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.closePath();ctx.strokeStyle='#55f0b4';ctx.lineWidth=2;ctx.stroke()}const cx=a.cx-q.sx,cy=a.cy-q.sy,len=Math.max(18,a.len*.58);ctx.beginPath();ctx.moveTo(cx-a.vx*len,cy-a.vy*len);ctx.lineTo(cx+a.vx*len,cy+a.vy*len);ctx.strokeStyle='#ffd75b';ctx.setLineDash([5,4]);ctx.lineWidth=2;ctx.stroke();ctx.setLineDash([]);if(cl!==null&&cr!==null){ctx.beginPath();ctx.moveTo(L+4,cl);ctx.lineTo(R-4,cr);ctx.strokeStyle='#63b8ff';ctx.setLineDash([4,3]);ctx.stroke();ctx.setLineDash([])}for(const x of [...toothFindings(t),...toothSignals(t)]){if(!Array.isArray(x.bbox))continue;const z=x.bbox.map(Number);ctx.strokeStyle=x.evidence_type==='visual_signal'?'#4fd7ff':'#ff5f73';ctx.lineWidth=2;ctx.strokeRect(z[0]-q.sx,z[1]-q.sy,z[2]-z[0],z[3]-z[1])}ctx.restore();const c=contacts(t),txt=[`Diş boyu ≈ ${Math.round(a.len)} px (ölçeksiz)`];if(c.m)txt.push(`Mezial: ${c.m}`);if(c.d)txt.push(`Distal: ${c.d}`);if(cl!==null&&cr!==null)txt.push('Mavi: tahmini alveoler kemik sınırı');txt.push('Yeşil: segment • Sarı: uzun eksen');$('metrics').textContent=txt.join(' • ');$('chips').innerHTML='';const items=[...toothFindings(t),...toothSignals(t)];if(!items.length){const s=document.createElement('span');s.className='chip';s.textContent='≥%50 bulgu yok';$('chips').appendChild(s)}for(const x of items){const s=document.createElement('span');s.className='chip';s.textContent=x.label||x.finding_code;$('chips').appendChild(s)}
  }

  const oldRender=renderJaw;renderJaw=async function(){await oldRender();signals=computeSignals();closeJaws();addMarkers()};
  const oldOpen=openTooth;openTooth=async function(t){await oldOpen(t);try{drawDetail({...t,fdi:fdi(t.fdi)})}catch(e){console.warn('[DETAIL_PATCH]',e)}};
  const oldAnalyze=analyze;analyze=async function(){await oldAnalyze();if(!result)return;const fs=acceptedFindings();$('status').textContent=`${result.unique_fdi_count||result.tooth_count||0} diş • ${fs.length} ≥%50 bulgu • ${signals.length} görüntüsel işaret • kapanış panoramikten kesin ölçülmez`;renderResults()};$('run').onclick=analyze;
  document.querySelectorAll('[data-sheet-tab]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.sheetTab==='findings')setTimeout(renderResults,0)}));
})();
