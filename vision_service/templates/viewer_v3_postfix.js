// Final panoramic-geometry correction layer.
// Keeps the real CBCT reference jaws, but lets only cues visible on the
// uploaded panorama control jaw separation and 2-D dental measurements.
(function(){
  const MIN_CONF=.50;
  const OPP={11:41,12:42,13:43,14:44,15:45,16:46,17:47,18:48,21:31,22:32,23:33,24:34,25:35,26:36,27:37,28:38};
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const median=a=>{const v=a.filter(Number.isFinite).slice().sort((x,y)=>x-y);return v.length?v[Math.floor(v.length/2)]:null};
  const validFdi=v=>/^[1-4][1-8]$/.test(String(v??''));
  const normalizeFdi=v=>{const s=String(v??'').trim();if(validFdi(s))return Number(s);const m=s.match(/(?:^|\D)([1-4][1-8])(?:\D|$)/);if(m)return Number(m[1]);const d=s.replace(/\D/g,'');if(d.length>=2){const t=d.slice(-2);if(validFdi(t))return Number(t)}return v};
  const upper=fdi=>['1','2'].includes(String(fdi)[0]);
  const center=b=>[(+b[0]+ +b[2])/2,(+b[1]+ +b[3])/2];
  const score=f=>Number(f?.confidence??f?.score??f?.conf??0)||0;

  function projectionProfile(){
    const teeth=(result?.teeth||[]).map(t=>{if(t)t.fdi=normalizeFdi(t.fdi);return t}).filter(t=>t?.bbox&&validFdi(t.fdi));
    const by=new Map(teeth.map(t=>[Number(t.fdi),t])),gaps=[];
    for(const [u,l] of Object.entries(OPP)){
      const U=by.get(+u),L=by.get(+l);if(!U||!L)continue;
      const ub=U.bbox.map(Number),lb=L.bbox.map(Number),h=Math.max(1,((ub[3]-ub[1])+(lb[3]-lb[1]))/2);
      const g=(lb[1]-ub[3])/h;if(Math.abs(g)<=1.0)gaps.push(g);
    }
    const gap=median(gaps);let label='temas belirsiz';
    if(gap!==null){if(gap<=-.08)label='örtüşme';else if(gap>=.08)label='açıklık'}
    return {gapNorm:gap,pairs:gaps.length,label,teeth};
  }

  function desiredHalfSeparation(profile){
    if(profile.gapNorm===null)return .55;
    if(profile.gapNorm<=-.08)return .12;
    if(profile.gapNorm<.08)return .28;
    return clamp(.40+profile.gapNorm*.75,.40,.95);
  }

  function refitJaw(){
    if(!jawScene?.scene||!window.jawRoot)return;
    const THREE=window.D3?.THREE;if(!THREE)return;
    window.jawRoot.updateMatrixWorld(true);
    const box=new THREE.Box3().setFromObject(window.jawRoot),c=box.getCenter(new THREE.Vector3()),s=box.getSize(new THREE.Vector3());
    const radius=Math.max(.1,Math.hypot(s.x,s.y,s.z)/2),fov=jawScene.camera.fov*Math.PI/180,dist=(radius/Math.sin(fov/2))*1.18;
    jawScene.controls.target.copy(c);jawScene.camera.position.set(c.x+radius*.10,c.y+radius*.03,c.z+dist);jawScene.camera.near=Math.max(.01,dist-radius*2.2);jawScene.camera.far=dist+radius*4;jawScene.camera.updateProjectionMatrix();jawScene.controls.update();
  }

  const priorRenderJaw=renderJaw;
  renderJaw=async function(){
    if(result&&Array.isArray(result.teeth))for(const t of result.teeth)if(t)t.fdi=normalizeFdi(t.fdi);
    await priorRenderJaw();
    const profile=projectionProfile();
    if(window.jawRoot?.children?.length>=2){
      const maxilla=window.jawRoot.children[0],mandible=window.jawRoot.children[1],half=desiredHalfSeparation(profile);
      maxilla.position.z=-half*.72;mandible.position.z=half*.72;
      if(result?.anatomy3d){result.anatomy3d.projection_gap_norm=profile.gapNorm;result.anatomy3d.projection_pairs=profile.pairs;result.anatomy3d.projection_label=profile.label;result.anatomy3d.jaw_half_separation_local=half}
      refitJaw();
    }
  };

  function contactMetrics(tooth,teeth){
    const same=teeth.filter(t=>upper(t.fdi)===upper(tooth.fdi)).sort((a,b)=>center(a.bbox)[0]-center(b.bbox)[0]);
    const i=same.findIndex(t=>String(t.fdi)===String(tooth.fdi));
    const pair=(a,b)=>{if(!a||!b)return null;const A=a.bbox.map(Number),B=b.bbox.map(Number),gap=B[0]-A[2],w=Math.max(1,Math.min(A[2]-A[0],B[2]-B[0])),r=gap/w;return {ratio:r,label:r>.10?'aralık':r<-.10?'projeksiyonda örtüşme':'temas/belirsiz'}};
    return {mesial:i>0?pair(same[i-1],same[i]):null,distal:i>=0&&i<same.length-1?pair(same[i],same[i+1]):null};
  }

  function pcaAxis(tooth){
    const p=tooth?.polygon;
    if(!Array.isArray(p)||p.length<6){const b=tooth.bbox.map(Number),c=center(b);return {cx:c[0],cy:c[1],vx:0,vy:1,length:Math.max(1,b[3]-b[1])}}
    let mx=0,my=0;for(const q of p){mx+=+q[0];my+=+q[1]}mx/=p.length;my/=p.length;
    let xx=0,yy=0,xy=0;for(const q of p){const dx=+q[0]-mx,dy=+q[1]-my;xx+=dx*dx;yy+=dy*dy;xy+=dx*dy}
    const tr=xx+yy,det=xx*yy-xy*xy,disc=Math.sqrt(Math.max(0,tr*tr/4-det)),lambda=tr/2+disc;let vx=xy,vy=lambda-xx;if(Math.abs(vx)+Math.abs(vy)<1e-8){vx=0;vy=1}const n=Math.hypot(vx,vy)||1;vx/=n;vy/=n;if(vy<0){vx=-vx;vy=-vy}
    const proj=p.map(q=>(+q[0]-mx)*vx+(+q[1]-my)*vy);return {cx:mx,cy:my,vx,vy,length:Math.max(1,Math.max(...proj)-Math.min(...proj))};
  }

  function drawRegionalOverlay(tooth){
    if(typeof cropTooth!=='function')return;
    const crop=cropTooth(tooth);if(!crop?.canvas||!crop?.image)return;
    const canvas=crop.canvas,ctx=canvas.getContext('2d'),axis=pcaAxis(tooth),all=(result?.teeth||[]).filter(t=>t?.bbox&&validFdi(normalizeFdi(t.fdi))),contacts=contactMetrics(tooth,all);
    const [x1,y1,x2,y2]=tooth.bbox.map(Number),L=clamp(Math.round(x1-crop.sx),0,canvas.width-1),R=clamp(Math.round(x2-crop.sx),0,canvas.width-1),T=clamp(Math.round(y1-crop.sy),0,canvas.height-1),B=clamp(Math.round(y2-crop.sy),0,canvas.height-1),w=Math.max(3,R-L),h=Math.max(3,B-T);
    const gray=(x,y)=>{x=clamp(Math.round(x),0,canvas.width-1);y=clamp(Math.round(y),0,canvas.height-1);const i=(y*canvas.width+x)*4,d=crop.image.data;return (d[i]+d[i+1]+d[i+2])/3};
    ctx.save();
    if(Array.isArray(tooth.polygon)&&tooth.polygon.length>2){ctx.beginPath();tooth.polygon.forEach((p,i)=>{const x=p[0]-crop.sx,y=p[1]-crop.sy;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.closePath();ctx.lineWidth=2;ctx.strokeStyle='rgba(88,255,184,.95)';ctx.stroke()}
    const len=Math.max(axis.length*.58,18),cx=axis.cx-crop.sx,cy=axis.cy-crop.sy;ctx.beginPath();ctx.moveTo(cx-axis.vx*len,cy-axis.vy*len);ctx.lineTo(cx+axis.vx*len,cy+axis.vy*len);ctx.setLineDash([5,4]);ctx.lineWidth=2;ctx.strokeStyle='rgba(255,218,91,.95)';ctx.stroke();ctx.setLineDash([]);
    const isUp=upper(tooth.fdi),ya=Math.round(T+h*(isUp?.38:.18)),yb=Math.round(T+h*(isUp?.78:.60));
    const bestY=(xa,xb)=>{let by=null,bs=-1;for(let y=Math.max(1,ya);y<=Math.min(canvas.height-2,yb);y++){let s=0,n=0;for(let x=Math.max(1,xa);x<=Math.min(canvas.width-2,xb);x++){s+=Math.abs(gray(x,y+1)-gray(x,y-1))+.35*Math.abs(gray(x+1,y)-gray(x-1,y));n++}if(n&&s/n>bs){bs=s/n;by=y}}return by};
    const yl=bestY(L+Math.round(w*.04),L+Math.round(w*.30)),yr=bestY(L+Math.round(w*.70),L+Math.round(w*.96));if(yl!==null&&yr!==null){ctx.beginPath();ctx.moveTo(L+w*.08,yl);ctx.lineTo(R-w*.08,yr);ctx.setLineDash([3,3]);ctx.lineWidth=2;ctx.strokeStyle='rgba(92,178,255,.95)';ctx.stroke();ctx.setLineDash([])}
    const pts=[];let prev=(L+R)/2,ys=[];if(isUp){for(let y=T+Math.round(h*.10);y<=T+Math.round(h*.68);y+=2)ys.push(y)}else{for(let y=T+Math.round(h*.32);y<=T+Math.round(h*.94);y+=2)ys.push(y)}
    for(const y of ys){let bx=null,bv=1e9;const xa=Math.max(L+Math.round(w*.16),Math.round(prev-w*.22)),xb=Math.min(R-Math.round(w*.16),Math.round(prev+w*.22));for(let x=xa;x<=xb;x++){const v=(gray(x-1,y)+2*gray(x,y)+gray(x+1,y))/4;if(v<bv){bv=v;bx=x}}if(bx!==null){pts.push([bx,y]);prev=bx}}
    if(pts.length>=7){ctx.beginPath();pts.filter((_,i)=>i%2===0).forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.setLineDash([3,2]);ctx.lineWidth=1.6;ctx.strokeStyle='rgba(255,112,160,.9)';ctx.stroke();ctx.setLineDash([])}
    const trusted=(result?.findings||[]).filter(f=>score(f)>=MIN_CONF&&String(normalizeFdi(f.fdi)||'')===String(normalizeFdi(tooth.fdi)));for(const f of trusted){if(!Array.isArray(f.bbox)||f.bbox.length!==4)continue;const b=f.bbox.map(Number);ctx.strokeStyle='rgba(255,78,78,.95)';ctx.lineWidth=2;ctx.strokeRect(b[0]-crop.sx,b[1]-crop.sy,b[2]-b[0],b[3]-b[1])}
    ctx.restore();
    const fmt=x=>x?x.label:'yok',prior=$('metrics')?.textContent||'';if($('metrics'))$('metrics').textContent=`${prior}${prior?' • ':''}Röntgen diş boyu: ${Math.round(axis.length)} px • M/D: ${fmt(contacts.mesial)} / ${fmt(contacts.distal)} • yeşil: diş sınırı • sarı: uzun eksen • mavi: tahmini kemik sınırı • pembe: 2D kanal izi`;
  }

  const priorOpenTooth=openTooth;
  openTooth=async function(tooth){await priorOpenTooth(tooth);try{drawRegionalOverlay(tooth)}catch(err){console.warn('[REGIONAL_PANO_OVERLAY]',err)}};

  const priorAnalyze=analyze;
  analyze=async function(){
    await priorAnalyze();if(!result)return;
    const profile=projectionProfile(),trusted=(result.findings||[]).filter(f=>f?.finding_code&&score(f)>=MIN_CONF),hidden=(result.findings||[]).filter(f=>f?.finding_code&&score(f)<MIN_CONF).length,n=result.unique_fdi_count||result.tooth_count||0;
    const hiddenText=hidden?` • ${hidden} düşük güven gizli`:'';$('status').textContent=`${n} diş • ${trusted.length} güvenilir bulgu${hiddenText} • projeksiyon: ${profile.label}`;
  };
  $('run').onclick=analyze;
})();
