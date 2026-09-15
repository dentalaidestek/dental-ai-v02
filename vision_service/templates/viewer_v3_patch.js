// Dental AI 3D viewer compatibility patch: normalize FDI labels before the 3D filter.
(function(){
  function normalizeFdiValue(v){
    const s=String(v ?? '').trim();
    if (/^[1-4][1-8]$/.test(s)) return Number(s);
    const m=s.match(/(?:^|\D)([1-4][1-8])(?:\D|$)/);
    if (m) return Number(m[1]);
    const digits=s.replace(/\D/g,'');
    if (digits.length>=2){
      const tail=digits.slice(-2);
      if (/^[1-4][1-8]$/.test(tail)) return Number(tail);
    }
    return v;
  }

  if (typeof renderJaw !== 'function') return;
  const originalRenderJaw = renderJaw;
  renderJaw = async function(){
    if (result && Array.isArray(result.teeth)){
      for (const t of result.teeth){
        if (t) t.fdi = normalizeFdiValue(t.fdi);
      }
      const rawCount = result.teeth.length;
      const validCount = result.teeth.filter(t=>t?.bbox && /^[1-4][1-8]$/.test(String(t.fdi))).length;
      console.log('[3D_FDI_BRIDGE]', {rawCount, validCount, labels: result.teeth.slice(0,12).map(t=>t?.fdi)});
      if (rawCount>0 && validCount===0){
        throw new Error('Dişler bulundu ancak FDI etiketleri 3D katmanına çevrilemedi');
      }
    }
    return originalRenderJaw();
  };
})();

// This file loads before the real-jaw layer. Install the final corrections on the
// next task, after viewer_v3_realjaw.js has replaced renderJaw/analyze.
setTimeout(function installRealJawFinalPatch(){
  if (window.__DENTAL_REALJAW_FINAL_PATCH) return;
  if (typeof renderJaw !== 'function' || typeof analyze !== 'function' || !window.D3?.THREE){
    setTimeout(installRealJawFinalPatch, 60);
    return;
  }
  window.__DENTAL_REALJAW_FINAL_PATCH = true;

  const THREE = window.D3.THREE;
  const baseRenderJaw = renderJaw;
  const baseAnalyze = analyze;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const upper=fdi=>['1','2'].includes(String(fdi ?? '')[0]);
  const center=b=>[(Number(b[0])+Number(b[2]))/2,(Number(b[1])+Number(b[3]))/2];
  const median=a=>{const v=a.filter(Number.isFinite).slice().sort((x,y)=>x-y);return v.length?v[Math.floor(v.length/2)]:null};

  function shiftWorldY(obj,dy){
    if(!obj?.parent || !Number.isFinite(dy) || Math.abs(dy)<1e-5)return;
    obj.parent.updateMatrixWorld(true);
    obj.updateMatrixWorld(true);
    const world=obj.getWorldPosition(new THREE.Vector3());
    world.y+=dy;
    obj.position.copy(obj.parent.worldToLocal(world));
    obj.updateMatrixWorld(true);
  }

  function topLevelToothGroups(scene){
    const groups=[];
    scene.traverse(n=>{
      if(!n?.isGroup || !n.userData?.tooth)return;
      if(!n.children?.some(c=>c?.isMesh))return;
      groups.push(n);
    });
    return groups;
  }

  function relationLabel(){
    const teeth=(result?.teeth||[]).filter(t=>t?.bbox&&/^[1-4][1-8]$/.test(String(t.fdi)));
    const OPP={11:41,12:42,13:43,14:44,15:45,16:46,17:47,18:48,21:31,22:32,23:33,24:34,25:35,26:36,27:37,28:38};
    const by=new Map(teeth.map(t=>[Number(t.fdi),t])),gaps=[];
    for(const [u,l] of Object.entries(OPP)){
      const U=by.get(Number(u)),L=by.get(Number(l));if(!U||!L)continue;
      const ub=U.bbox.map(Number),lb=L.bbox.map(Number);
      const h=Math.max(1,((ub[3]-ub[1])+(lb[3]-lb[1]))/2);
      const g=(lb[1]-ub[3])/h;
      if(Math.abs(g)<=.9)gaps.push(g);
    }
    const g=median(gaps);
    if(g===null)return 'projeksiyon: değerlendirilemedi';
    if(g<=-.08)return 'projeksiyon: örtüşme';
    if(g>=.08)return 'projeksiyon: açıklık';
    return 'projeksiyon: belirsiz';
  }

  function bboxIou(a,b){
    if(!Array.isArray(a)||!Array.isArray(b)||a.length!==4||b.length!==4)return 0;
    const ax1=+a[0],ay1=+a[1],ax2=+a[2],ay2=+a[3],bx1=+b[0],by1=+b[1],bx2=+b[2],by2=+b[3];
    const ix1=Math.max(ax1,bx1),iy1=Math.max(ay1,by1),ix2=Math.min(ax2,bx2),iy2=Math.min(ay2,by2);
    const inter=Math.max(0,ix2-ix1)*Math.max(0,iy2-iy1);
    const aa=Math.max(1,(ax2-ax1)*(ay2-ay1)),ba=Math.max(1,(bx2-bx1)*(by2-by1));
    return inter/Math.max(1,aa+ba-inter);
  }

  function findingsForTooth(t){
    const fs=(result?.findings||[]).filter(f=>f&&f.finding_code);
    const fdi=String(t?.fdi ?? '');
    return fs.filter(f=>{
      if(f.fdi!==undefined&&f.fdi!==null&&String(f.fdi)!=='')return String(f.fdi)===fdi;
      if(!Array.isArray(f.bbox)||!Array.isArray(t?.bbox))return false;
      const c=center(f.bbox),b=t.bbox.map(Number);
      const inside=c[0]>=b[0]&&c[0]<=b[2]&&c[1]>=b[1]&&c[1]<=b[3];
      return inside||bboxIou(f.bbox,t.bbox)>=.04;
    });
  }

  function findingSprite(text){
    const c=document.createElement('canvas');c.width=256;c.height=72;
    const ctx=c.getContext('2d');
    ctx.fillStyle='rgba(128,18,34,.92)';ctx.beginPath();ctx.roundRect(4,4,248,64,18);ctx.fill();
    ctx.strokeStyle='rgba(255,130,145,.95)';ctx.lineWidth=3;ctx.stroke();
    ctx.font='700 28px system-ui, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle='#fff';ctx.fillText(text,128,36);
    const tex=new THREE.CanvasTexture(c);if('SRGBColorSpace' in THREE)tex.colorSpace=THREE.SRGBColorSpace;
    const mat=new THREE.SpriteMaterial({map:tex,transparent:true,depthTest:false,depthWrite:false});
    const sp=new THREE.Sprite(mat);sp.renderOrder=120;return sp;
  }

  function addFindingVisibility(scene,groups){
    for(const g of groups){
      const tooth=g.userData.tooth,fs=findingsForTooth(tooth);if(!fs.length)continue;
      g.traverse(m=>{
        if(!m.isMesh||!m.material)return;
        m.material=m.material.clone();
        if('emissive' in m.material){m.material.emissive=new THREE.Color(0x6d1020);m.material.emissiveIntensity=.42;}
      });
      const box=new THREE.Box3().setFromObject(g),size=box.getSize(new THREE.Vector3()),c=box.getCenter(new THREE.Vector3());
      const r=Math.max(.18,Math.max(size.x,size.y,size.z)*.60);
      const halo=new THREE.Mesh(new THREE.SphereGeometry(r,18,12),new THREE.MeshBasicMaterial({color:0xff5368,wireframe:true,transparent:true,opacity:.34,depthTest:false,depthWrite:false}));
      halo.position.copy(c);halo.renderOrder=110;scene.add(halo);
      const sp=findingSprite(`${fs.length} bulgu`);sp.position.copy(c).add(new THREE.Vector3(0,r*1.22,0));sp.scale.set(r*1.75,r*.50,1);scene.add(sp);
    }
  }

  function closeReferenceArches(scene,groups){
    const uppers=groups.filter(g=>upper(g.userData?.tooth?.fdi));
    const lowers=groups.filter(g=>!upper(g.userData?.tooth?.fdi));
    if(!uppers.length||!lowers.length)return;
    scene.updateMatrixWorld(true);
    const upperBottom=Math.min(...uppers.map(g=>new THREE.Box3().setFromObject(g).min.y));
    const lowerTop=Math.max(...lowers.map(g=>new THREE.Box3().setFromObject(g).max.y));
    const gap=upperBottom-lowerTop;
    // Open-Full-Jaw is a reference scan, not the uploaded patient's true bite.
    // Bring the reference arches to a neutral near-contact viewing pose only;
    // do not encode this movement as a clinical occlusion measurement.
    const shift=clamp(gap-.08,0,1.15);
    if(shift<=.01)return;
    for(const g of uppers)shiftWorldY(g,-shift);
    const maxilla=[];
    scene.traverse(n=>{if(n?.isMesh&&String(n.userData?.jawPart||'').toLowerCase().includes('maxilla'))maxilla.push(n)});
    for(const m of maxilla)shiftWorldY(m,-shift);
    scene.updateMatrixWorld(true);
    result.reference_arch_visual_shift=shift;
  }

  renderJaw=async function(){
    await baseRenderJaw();
    const scene=jawScene?.scene;if(!scene)return;
    // Keep translucent bone but make roots/crowns readable.
    scene.traverse(n=>{
      if(!n?.isMesh||!n.userData?.jawPart||!n.material)return;
      n.material=n.material.clone();n.material.opacity=.16;n.material.transparent=true;n.material.depthWrite=false;
    });
    const groups=topLevelToothGroups(scene);
    closeReferenceArches(scene,groups);
    addFindingVisibility(scene,groups);
    const hint=document.querySelector('.hint');
    if(hint)hint.textContent='Dişe dokun: büyütme • kemik sınırı • uzun eksen • kanal izi • komşuluk';
  };

  analyze=async function(){
    await baseAnalyze();
    if(!result)return;
    const n=result.unique_fdi_count||result.tooth_count||0;
    const f=(result.findings||[]).filter(x=>x&&x.finding_code).length;
    const s=document.getElementById('status');
    if(s)s.textContent=`${n} diş • ${f} bulgu • ${relationLabel()}`;
  };
  const run=document.getElementById('run');if(run)run.onclick=analyze;
},0);
