// Panoramic-conditioned anatomical viewer.
// Patient-specific cues are limited to evidence visible in the panorama. The
// jaw volume and buccolingual depth remain an anatomical reference, not CBCT.
(function(){
  const ATLAS_REV='c835665a9ade09ee0b993cee6eee1b25b7f7311b';
  const ATLAS_ROOT=`https://raw.githubusercontent.com/choxos/OMFAtlas/${ATLAS_REV}/public/models/dental`;
  const MANIFEST_URL=`${ATLAS_ROOT}/manifest.json`;
  const BUFFER_URL=`${ATLAS_ROOT}/open-full-jaw.bin`;
  const PANORAMIC_SIMULATION_LABEL='Panoramik tabanlı anatomik 3D görselleştirme';
  const MIN_DISPLAY_CONFIDENCE=.50;
  const IMPACTED_CODES=new Set(['IMPACTED_TOOTH','IMPACTED_THIRD_MOLAR','UNERUPTED_TOOTH']);
  const BONE_LOSS_RE=/BONE_LOSS/;
  let dataPromise=null,jawToothMap=new Map(),highlightTimer=null;
  const layerState={bone:true,canal:true};
  const dedupeTeeth=items=>{const best=new Map();for(const t of items||[]){if(!t?.bbox)continue;const f=normalizeFdi(t.fdi);if(!validFdi(f))continue;t.fdi=f;const s=Number(t.confidence??t.score??0)||0,p=best.get(String(f)),ps=Number(p?.confidence??p?.score??0)||0;if(!p||s>ps)best.set(String(f),t)}return [...best.values()]};

  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const validFdi=v=>/^[1-4][1-8]$/.test(String(v??''));
  const upper=fdi=>['1','2'].includes(String(fdi)[0]);
  const median=values=>{const a=values.filter(Number.isFinite).slice().sort((x,y)=>x-y);return a.length?a[Math.floor(a.length/2)]:0};
  const normalizeFdi=v=>{
    const s=String(v??'').trim();
    if(validFdi(s))return Number(s);
    const m=s.match(/(?:^|\D)([1-4][1-8])(?:\D|$)/);if(m)return Number(m[1]);
    const d=s.replace(/\D/g,'');if(d.length>=2){const t=d.slice(-2);if(validFdi(t))return Number(t)}
    return v;
  };
  const boxCenter=b=>[(+b[0]+ +b[2])/2,(+b[1]+ +b[3])/2];

  function geometryFor(part,buffer){
    const THREE=window.D3.THREE,g=new THREE.BufferGeometry();
    // Each mesh needs private arrays: detail/fallback centering transforms must
    // never mutate the shared downloaded atlas buffer used by another tooth.
    g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(new Float32Array(buffer,part.positions,part.vertexCount*3)),3));
    if(Number.isFinite(part.normals))g.setAttribute('normal',new THREE.BufferAttribute(new Float32Array(new Float32Array(buffer,part.normals,part.vertexCount*3)),3));
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(new Uint32Array(buffer,part.indices,part.indexCount)),1));
    if(!g.getAttribute('normal'))g.computeVertexNormals();
    return g;
  }

  function partCenter(part){
    if(Array.isArray(part?.axes?.center)&&part.axes.center.length===3)return part.axes.center.map(Number);
    return part.bounds[0].map((v,i)=>(+v + +part.bounds[1][i])/2);
  }
  function partSpan(part,axis){return Math.max(1e-6,+part.bounds[1][axis]- +part.bounds[0][axis])}

  async function loadData(){
    if(dataPromise)return dataPromise;
    dataPromise=(async()=>{
      const [mr,br]=await Promise.all([fetch(MANIFEST_URL,{cache:'force-cache'}),fetch(BUFFER_URL,{cache:'force-cache'})]);
      if(!mr.ok||!br.ok)throw new Error('Sabitlenmiş anatomik çene modeli yüklenemedi');
      const manifest=await mr.json(),buffer=await br.arrayBuffer();
      const parts=(manifest.parts||[]).filter(p=>p.source==='openfulljaw'&&(p.buffer||'')==='open-full-jaw');
      const bones=parts.filter(p=>p.group==='bone'),teeth=parts.filter(p=>p.group==='tooth'&&validFdi(p.fdi));
      if(bones.length<2||teeth.length<20)throw new Error('Anatomik çene parçaları eksik');
      const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
      for(const p of parts)for(let i=0;i<3;i++){lo[i]=Math.min(lo[i],+p.bounds[0][i]);hi[i]=Math.max(hi[i],+p.bounds[1][i])}
      const center=lo.map((v,i)=>(v+hi[i])/2),centers=teeth.map(p=>partCenter(p)[0]);
      return {buffer,bones,teethByFdi:new Map(teeth.map(p=>[Number(p.fdi),p])),center,toothMinX:Math.min(...centers),toothMaxX:Math.max(...centers)};
    })();
    return dataPromise;
  }

  function findingScore(f){return Number(f?.confidence??f?.score??0)||0}
  function displayFindingFamily(code){const c=String(code||'').toUpperCase();return c==='IMPACTED_THIRD_MOLAR'?'IMPACTED_TOOTH':c}
  function dedupeFindings(items){
    const best=new Map();
    for(const f of items||[]){
      if(!f?.finding_code)continue;
      const fdi=validFdi(normalizeFdi(f.fdi))?String(normalizeFdi(f.fdi)):'';
      const b=Array.isArray(f.bbox)?f.bbox.map(Number):null;
      const spatial=fdi||((b&&b.length===4)?`${Math.round((b[0]+b[2])/40)}:${Math.round((b[1]+b[3])/40)}`:'global');
      const key=`${displayFindingFamily(f.finding_code)}:${spatial}`;
      const prior=best.get(key),moreSpecific=String(f.finding_code)==='IMPACTED_THIRD_MOLAR'&&String(prior?.finding_code)!=='IMPACTED_THIRD_MOLAR';if(!prior||findingScore(f)>findingScore(prior)||(findingScore(f)===findingScore(prior)&&moreSpecific))best.set(key,f);
    }
    return [...best.values()];
  }
  function allFindings(){return dedupeFindings((result?.findings||[]).filter(f=>findingScore(f)>=MIN_DISPLAY_CONFIDENCE))}
  function toothFindings(t){
    const out=[],seen=new Set();
    for(const f of allFindings()){
      if(String(normalizeFdi(f.fdi)||'')!==String(normalizeFdi(t.fdi)))continue;
      const key=String(f.finding_code);if(seen.has(key))continue;seen.add(key);out.push(f);
    }
    return out;
  }

  function resolveToothPart(fdi,data){
    const exact=data.teethByFdi.get(Number(fdi));
    if(exact)return {part:exact,placementCenter:partCenter(exact),mirrorX:false,atlasFallback:false};
    const s=String(fdi),opposite={1:2,2:1,3:4,4:3}[s[0]],source=data.teethByFdi.get(Number(`${opposite}${s[1]}`));
    if(!source)return null;
    const c=partCenter(source),mid=(data.toothMinX+data.toothMaxX)/2;
    return {part:source,placementCenter:[2*mid-c[0],c[1],c[2]],mirrorX:true,atlasFallback:true};
  }

  function polygonAxis(tooth){
    const p=tooth?.polygon;
    if(!Array.isArray(p)||p.length<6){const b=tooth.bbox.map(Number),c=boxCenter(b);return {cx:c[0],cy:c[1],length:Math.max(1,b[3]-b[1]),tilt:0,reliable:false}}
    let mx=0,my=0;for(const q of p){mx+=+q[0];my+=+q[1]}mx/=p.length;my/=p.length;
    let xx=0,yy=0,xy=0;for(const q of p){const dx=+q[0]-mx,dy=+q[1]-my;xx+=dx*dx;yy+=dy*dy;xy+=dx*dy}
    const tr=xx+yy,det=xx*yy-xy*xy,disc=Math.sqrt(Math.max(0,tr*tr/4-det)),lambda=tr/2+disc;
    let vx=xy,vy=lambda-xx;if(Math.abs(vx)+Math.abs(vy)<1e-8){if(xx>yy){vx=1;vy=0}else{vx=0;vy=1}}
    const n=Math.hypot(vx,vy)||1;vx/=n;vy/=n;if(vy<0){vx=-vx;vy=-vy}
    const projections=p.map(q=>(+q[0]-mx)*vx+(+q[1]-my)*vy);
    return {cx:mx,cy:my,length:Math.max(1,Math.max(...projections)-Math.min(...projections)),tilt:clamp(Math.atan2(vx,vy),-1.45,1.45),reliable:true};
  }

  function patientStats(teeth){
    const widths=teeth.map(t=>+t.bbox[2]- +t.bbox[0]),heights=teeth.map(t=>+t.bbox[3]- +t.bbox[1]),byType=new Map();
    for(const t of teeth){const k=String(t.fdi)[1],h=Math.max(1,+t.bbox[3]- +t.bbox[1]),w=Math.max(1,+t.bbox[2]- +t.bbox[0]);if(!byType.has(k))byType.set(k,{h:[],w:[]});byType.get(k).h.push(h);byType.get(k).w.push(w)}
    const archY={upper:median(teeth.filter(t=>upper(t.fdi)).map(t=>boxCenter(t.bbox)[1])),lower:median(teeth.filter(t=>!upper(t.fdi)).map(t=>boxCenter(t.bbox)[1]))};
    return {medianH:Math.max(1,median(heights)),medianW:Math.max(1,median(widths)),minX:Math.min(...teeth.map(t=>+t.bbox[0])),maxX:Math.max(...teeth.map(t=>+t.bbox[2])),byType,archY};
  }

  function patientTransform(tooth,part,data,stats,findings,placementCenter=partCenter(part)){
    const b=tooth.bbox.map(Number),w=Math.max(1,b[2]-b[0]),h=Math.max(1,b[3]-b[1]),type=stats.byType.get(String(tooth.fdi)[1]);
    const refW=Math.max(1,median(type?.w||[])||stats.medianW),refH=Math.max(1,median(type?.h||[])||stats.medianH);
    const sx=clamp(w/refW,.90,1.10),sy=clamp(h/refH,.92,1.08),sz=clamp(Math.sqrt(sx*sy),.94,1.06);
    const axis=polygonAxis(tooth),archCy=upper(tooth.fdi)?stats.archY.upper:stats.archY.lower,imageOffset=(boxCenter(b)[1]-archCy)/stats.medianH,thirdMolar=String(tooth.fdi)[1]==='8',visuallyImpacted=thirdMolar&&(Math.abs(axis.tilt)>.42||Math.abs(imageOffset)>.55),isImpacted=findings.some(f=>IMPACTED_CODES.has(f.finding_code))||visuallyImpacted,c=placementCenter,imageX=boxCenter(b)[0];
    const n=clamp((imageX-stats.minX)/Math.max(1,stats.maxX-stats.minX),0,1),desiredX=data.toothMinX+n*(data.toothMaxX-data.toothMinX),maxShift=partSpan(part,0)*.28;
    // The panorama controls mesiodistal spacing. The old 28%-of-one-tooth cap
    // forced missing-tooth cases back into the complete atlas arrangement.
    const spacingLimit=Math.max(maxShift,partSpan(part,0)*1.15),xShift=clamp(desiredX-c[0],-spacingLimit,spacingLimit);
    // Vertical image position is a panoramic cue for every tooth. Keep the
    // depth small for erupted teeth and allow a stronger offset for impactions.
    let zShift=-clamp(imageOffset,-1.1,1.1)*partSpan(part,2)*(isImpacted?.30:.08);
    return {scale:[sx,sy,sz],rotationY:-axis.tilt*(isImpacted?1:.26),positionShift:[xShift,0,zShift],impacted:isImpacted,axisReliable:axis.reliable};
  }

  function findingColor(code){
    code=String(code||'');
    if(/CARIES|PERIAPICAL|RADIOLUCENT|RESORPTION|FRACTURE/.test(code))return 0xff5b6f;
    if(/ROOT_CANAL|ENDO|POST/.test(code))return 0xff83b3;
    if(/FILLING|CROWN|BRIDGE|INLAY|PONTIC|IMPLANT/.test(code))return 0x60d7ff;
    if(BONE_LOSS_RE.test(code))return 0xa990ff;if(IMPACTED_CODES.has(code))return 0xffc857;return 0xffa34d;
  }
  function toothMaterial(){
    const THREE=window.D3.THREE;
    // Findings no longer permanently recolor teeth. The model stays clean and
    // natural white; selecting a finding gives a temporary highlight instead.
    return new THREE.MeshPhysicalMaterial({color:0xf5f2ea,roughness:.27,metalness:0,clearcoat:.18,clearcoatRoughness:.32,side:THREE.DoubleSide});
  }

  function buildPatientTooth(tooth,resolved,data,stats,findings){
    const THREE=window.D3.THREE,{part,placementCenter,mirrorX}=resolved,sourceCenter=partCenter(part),transform=patientTransform(tooth,part,data,stats,findings,placementCenter),geometry=geometryFor(part,data.buffer);geometry.translate(-sourceCenter[0],-sourceCenter[1],-sourceCenter[2]);const mesh=new THREE.Mesh(geometry,toothMaterial());
    if(mirrorX)mesh.scale.x=-1;mesh.userData.tooth=tooth;mesh.userData.patientTooth=true;
    const wrapper=new THREE.Group();wrapper.userData.tooth=tooth;wrapper.userData.patientTransform=transform;
    wrapper.position.set(placementCenter[0]-data.center[0]+transform.positionShift[0],placementCenter[1]-data.center[1],placementCenter[2]-data.center[2]+transform.positionShift[2]);
    wrapper.scale.set(...transform.scale);wrapper.rotation.y=transform.rotationY;wrapper.add(mesh);return {wrapper,mesh,transform};
  }

  function addMandibularCanals(scene,mandibleRoot){
    const THREE=window.D3.THREE,helper=(result?.helpers||[]).some(h=>h?.signal==='MANDIBULAR_CANAL_HELPER');
    if(!helper)return 'gösterilmedi: filmden mandibular kanal sinyali yok';
    mandibleRoot.updateMatrixWorld(true);
    const box=new THREE.Box3().setFromObject(mandibleRoot),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());
    for(const side of [-1,1]){
      const points=[];for(let i=0;i<=28;i++){const u=i/28;points.push(new THREE.Vector3(center.x+side*size.x*(.08+.34*u),box.min.y+size.y*(.34+.12*u-.025*Math.sin(u*Math.PI)),center.z-size.z*(.03+.16*u)))}
      const curve=new THREE.CatmullRomCurve3(points),geo=new THREE.TubeGeometry(curve,84,Math.max(.014,size.x*.0038),12,false),mat=new THREE.MeshStandardMaterial({color:0xf08daa,emissive:0x7b2645,emissiveIntensity:.24,transparent:true,opacity:.96,depthWrite:false});
      const tube=new THREE.Mesh(geo,mat);tube.userData.anatomicalReference=true;tube.userData.panoramaSupported=helper;tube.userData.layer='canal';tube.visible=layerState.canal;scene.add(tube);
    }
    return 'panoramik kanal sinyali + anatomik referans derinlik';
  }

  function fitCamera(ctx,obj,pad=1.24){
    const THREE=window.D3.THREE;obj.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(obj),c=box.getCenter(new THREE.Vector3()),s=box.getSize(new THREE.Vector3()),radius=Math.max(.1,Math.hypot(s.x,s.y,s.z)/2),fov=ctx.camera.fov*Math.PI/180,dist=(radius/Math.sin(fov/2))*pad;
    ctx.controls.target.copy(c);ctx.camera.position.set(c.x+radius*.12,c.y+radius*.04,c.z+dist);ctx.camera.near=Math.max(.01,dist-radius*2.2);ctx.camera.far=dist+radius*4;ctx.camera.updateProjectionMatrix();ctx.controls.minDistance=Math.max(radius*.65,1.5);ctx.controls.maxDistance=dist*2.4;ctx.controls.update();
  }

  function findingTitle(f){
    const code=String(f?.finding_code||'');
    const fallback={IMPACTED_TOOTH:'Gömülü diş',IMPACTED_THIRD_MOLAR:'Gömülü 20’lik diş',UNERUPTED_TOOTH:'Sürmemiş diş',BONE_LOSS:'Kemik kaybı',HORIZONTAL_BONE_LOSS:'Yatay kemik kaybı',VERTICAL_BONE_LOSS:'Dikey kemik kaybı',ROOT_CANAL_TREATED:'Kanal tedavili diş',ENDO_POST:'Post',CARIES:'Çürük',DEEP_CARIES:'Derin çürük',RECURRENT_CARIES:'Sekonder çürük',IMPLANT:'İmplant',CROWN:'Kron',BRIDGE:'Köprü',FILLING:'Dolgu',MISSING_TOOTH:'Eksik diş'};
    return f?.label||fallback[code]||code.replaceAll('_',' ').toLocaleLowerCase('tr-TR').replace(/^./,c=>c.toLocaleUpperCase('tr-TR'));
  }

  function treatmentItems(){
    const sources=[result?.treatments,result?.treatment_options,result?.preliminary?.treatments,result?.preliminary?.treatment_options];
    const raw=sources.find(Array.isArray)||[];
    return raw.map((x,i)=>({index:i+1,title:typeof x==='string'?x:(x?.label||x?.title||x?.name||x?.treatment||x?.text||'Tedavi seçeneği')})).filter(x=>x.title);
  }

  function restoreHighlight(){
    for(const {mesh} of jawToothMap.values()){
      if(!mesh?.material)continue;
      mesh.material.color?.set(0xf5f2ea);if(mesh.material.emissive){mesh.material.emissive.set(0x000000);mesh.material.emissiveIntensity=0}mesh.material.needsUpdate=true;
    }
  }

  function highlightFinding(f){
    clearTimeout(highlightTimer);restoreHighlight();
    const fdi=normalizeFdi(f?.fdi),entry=validFdi(fdi)?jawToothMap.get(String(fdi)):null;
    if(!entry?.mesh?.material)return;
    const THREE=window.D3.THREE,color=new THREE.Color(findingColor(f.finding_code));entry.mesh.material.color.copy(color.clone().lerp(new THREE.Color(0xf5f2ea),.28));entry.mesh.material.emissive?.copy(color);entry.mesh.material.emissiveIntensity=.42;entry.mesh.material.needsUpdate=true;
    highlightTimer=setTimeout(restoreHighlight,1800);
  }

  function setLayerVisible(layer,visible){
    layerState[layer]=visible;if(!jawScene?.scene)return;
    jawScene.scene.traverse(obj=>{if(obj.userData?.layer===layer)obj.visible=visible});
  }

  function renderSheet(tab='findings'){
    const sheet=$('analysisSheet'),body=$('sheetBody'),stage=$('stage');if(!sheet||!body||!stage)return;
    sheet.classList.remove('hidden');stage.classList.add('has-results');
    document.querySelectorAll('[data-sheet-tab]').forEach(b=>b.classList.toggle('active',b.dataset.sheetTab===tab));
    body.innerHTML='';
    const findings=allFindings().sort((a,b)=>findingScore(b)-findingScore(a));
    if($('findingsCount'))$('findingsCount').textContent=findings.length?`(${findings.length})`:'';
    if(tab==='findings'){
      const note=document.createElement('div');note.className='sheet-note';note.textContent='Bulguya dokununca ilgili diş 3D üzerinde geçici olarak vurgulanır.';body.appendChild(note);
      if(!findings.length){const e=document.createElement('div');e.className='empty-card';e.textContent='%50 ve üzeri gösterilebilir bulgu yok.';body.appendChild(e);return}
      const list=document.createElement('div');list.className='finding-list';
      for(const f of findings){const card=document.createElement('button');card.type='button';card.className='finding-card';const main=document.createElement('div');main.className='finding-main';const title=document.createElement('div');title.className='finding-title';const fdi=normalizeFdi(f.fdi);title.textContent=`${validFdi(fdi)?`${fdi} • `:''}${findingTitle(f)}`;const sub=document.createElement('div');sub.className='finding-sub';sub.textContent=validFdi(fdi)?`Diş ${fdi} • 3D’de vurgulamak için dokun`:'Genel bulgu';main.append(title,sub);const score=document.createElement('div');score.className='finding-score';score.textContent=`%${Math.round(findingScore(f)*100)}`;card.append(main,score);card.onclick=()=>highlightFinding(f);list.appendChild(card)}body.appendChild(list);return;
    }
    if(tab==='treatments'){
      const items=treatmentItems();if(!items.length){const e=document.createElement('div');e.className='empty-card';e.textContent='Bu analizde 3D paneline aktarılmış tedavi seçeneği yok.';body.appendChild(e);return}
      const list=document.createElement('div');list.className='finding-list';for(const item of items){const card=document.createElement('div');card.className='finding-card';const main=document.createElement('div');main.className='finding-main';const title=document.createElement('div');title.className='finding-title';title.textContent=`${item.index}. ${item.title}`;main.appendChild(title);card.appendChild(main);list.appendChild(card)}body.appendChild(list);return;
    }
    const list=document.createElement('div');list.className='view-list';
    const makeToggle=(label,getState,onToggle)=>{const b=document.createElement('button');b.type='button';b.className='view-toggle';const a=document.createElement('span');a.textContent=label;const s=document.createElement('span');const sync=()=>s.textContent=getState()?'Açık':'Kapalı';sync();b.append(a,s);b.onclick=()=>{onToggle(!getState());sync()};return b};
    list.appendChild(makeToggle('Çene kemiği',()=>layerState.bone,v=>setLayerVisible('bone',v)));
    list.appendChild(makeToggle('Mandibular kanal',()=>layerState.canal,v=>setLayerVisible('canal',v)));
    list.appendChild(makeToggle('Panoramik önizleme',()=>!$('panoMini').classList.contains('hidden'),v=>$('panoMini').classList.toggle('hidden',!v)));
    body.appendChild(list);
  }

  function buildPanoramicJaw(teeth,stats,data){
    const THREE=window.D3.THREE,root=new THREE.Group(),upperRoot=new THREE.Group(),lowerRoot=new THREE.Group();root.add(upperRoot,lowerRoot);
    const boneMat=()=>new THREE.MeshPhysicalMaterial({color:0xa9c9e8,transparent:true,opacity:.24,roughness:.46,metalness:0,transmission:.10,depthWrite:false,side:THREE.DoubleSide});
    const placedFor=items=>items.map(t=>{const r=resolveToothPart(t.fdi,data);if(!r)return null;const tr=patientTransform(t,r.part,data,stats,toothFindings(t),r.placementCenter),p=r.placementCenter;return {t,x:p[0]-data.center[0]+tr.positionShift[0],y:p[1]-data.center[1],z:p[2]-data.center[2]+tr.positionShift[2],w:partSpan(r.part,0),h:partSpan(r.part,2)}}).filter(Boolean).sort((a,b)=>a.x-b.x);
    const build=(items,isUp,target)=>{
      const p=placedFor(items);if(p.length<2)return;
      const pts=p.map(q=>new THREE.Vector3(q.x,q.y,q.z)),curve=new THREE.CatmullRomCurve3([pts[0].clone(),...pts,pts.at(-1).clone()],false,'catmullrom',.35),mw=median(p.map(q=>q.w)),mh=median(p.map(q=>q.h)),outerR=Math.max(mw*.82,mh*.22),innerR=Math.max(mw*.52,mh*.13);
      const outer=new THREE.Mesh(new THREE.TubeGeometry(curve,128,outerR,20,false),boneMat()),inner=new THREE.Mesh(new THREE.TubeGeometry(curve,128,innerR,20,false),boneMat());outer.userData.layer='bone';inner.userData.layer='bone';outer.visible=inner.visible=layerState.bone;target.add(outer,inner);
      // Posterior vertical bone gives the generated mandible/maxilla a jaw volume instead of a thin rail.
      for(const q of [p[0],p.at(-1)]){const height=Math.max(mh*2.8,mw*4.0),geo=new THREE.CapsuleGeometry(outerR*.72,height,10,20),m=new THREE.Mesh(geo,boneMat());m.position.set(q.x,q.y,q.z+(isUp?-height*.38:height*.38));m.rotation.x=Math.PI/2;m.userData.layer='bone';m.visible=layerState.bone;target.add(m)}
    };
    build(teeth.filter(t=>upper(t.fdi)),true,upperRoot);build(teeth.filter(t=>!upper(t.fdi)),false,lowerRoot);return {root,upperRoot,lowerRoot};
  }

  renderJaw=async function(){
    await waitD3();disposeScene(jawScene);jawScene=createBase($('jaw3d'));jawToothMap=new Map();
    const {scene,renderer,camera}=jawScene,data=await loadData(),patient=dedupeTeeth(result?.teeth||[]);
    if(!patient.length)throw new Error('FDI diş tespiti yok');
    const stats=patientStats(patient),jaw=buildPanoramicJaw(patient,stats,data),root=jaw.root,maxillaRoot=jaw.upperRoot,mandibleRoot=jaw.lowerRoot;window.jawRoot=root;root.rotation.x=-Math.PI/2;scene.add(root);
    const clickables=[];let impactedAdjusted=0,axisAdjusted=0,atlasFallbacks=0,renderedTeeth=0;
    // Only patient-detected FDI teeth are instantiated. No complete-atlas tooth
    // layer is rendered behind them, so the old translucent/ghost roots vanish.
    for(const tooth of patient){const resolved=resolveToothPart(tooth.fdi,data);if(!resolved)continue;const findings=toothFindings(tooth),built=buildPatientTooth(tooth,resolved,data,stats,findings);renderedTeeth++;if(built.transform.impacted)impactedAdjusted++;if(built.transform.axisReliable)axisAdjusted++;if(resolved.atlasFallback)atlasFallbacks++;clickables.push(built.mesh);jawToothMap.set(String(tooth.fdi),{mesh:built.mesh,wrapper:built.wrapper,tooth});(upper(tooth.fdi)?maxillaRoot:mandibleRoot).add(built.wrapper)}
    root.scale.setScalar(.058);fitCamera(jawScene,root,1.24);const canalLabel='gösterilmedi';
    result.anatomy3d={mode:'panoramic_generated_jaw',diagnostic:false,medical_volume:false,patient_specific_depth:false,reference_teeth_hidden:true,persistent_finding_markers:false,rendered_teeth:renderedTeeth,axis_adjusted:axisAdjusted,impacted_adjusted:impactedAdjusted,atlas_fallbacks:atlasFallbacks,occlusion_compaction_mm:5.6,canal:canalLabel,jaw_source:'panoramic_geometry',atlas_revision:ATLAS_REV};
    const THREE=window.D3.THREE,ray=new THREE.Raycaster(),mouse=new THREE.Vector2();renderer.domElement.addEventListener('pointerdown',ev=>{const r=renderer.domElement.getBoundingClientRect();mouse.x=((ev.clientX-r.left)/r.width)*2-1;mouse.y=-((ev.clientY-r.top)/r.height)*2+1;ray.setFromCamera(mouse,camera);const hit=ray.intersectObjects(clickables,false)[0];if(hit?.object?.userData?.tooth)openTooth(hit.object.userData.tooth)});
  };

  const baseOpenTooth=openTooth;
  openTooth=async function(t){
    await baseOpenTooth(t);
    try{
      const data=await loadData(),resolved=resolveToothPart(normalizeFdi(t.fdi),data);if(!resolved)return;const {part,placementCenter,mirrorX}=resolved;
      disposeScene(toothScene);toothScene=createBase($('tooth3d'));
      const THREE=window.D3.THREE,c=partCenter(part),patient=dedupeTeeth(result?.teeth||[]),stats=patientStats(patient),findings=toothFindings(t),transform=patientTransform(t,part,data,stats,findings,placementCenter),group=new THREE.Group(),pose=new THREE.Group();group.rotation.x=-Math.PI/2;pose.rotation.y=transform.rotationY;
      const geometry=geometryFor(part,data.buffer);geometry.translate(-c[0],-c[1],-c[2]);
      const mesh=new THREE.Mesh(geometry,new THREE.MeshPhysicalMaterial({color:0xf5f2ea,roughness:.24,clearcoat:.20,transparent:true,opacity:.88,side:THREE.DoubleSide,depthWrite:true}));if(mirrorX)mesh.scale.x=-1;mesh.userData.tooth=t;pose.add(mesh);pose.scale.set(...transform.scale);group.add(pose);toothScene.scene.add(group);group.scale.setScalar(.065);fitCamera(toothScene,group,1.72);
      $('chips').innerHTML='';const direct=findings.filter(f=>f.evidence_type==='direct');const shown=direct.length?direct:findings;if(!shown.length){const chip=document.createElement('span');chip.className='chip';chip.textContent='Doğrudan bulgu yok';$('chips').appendChild(chip)}else for(const f of shown){const chip=document.createElement('span');chip.className='chip';chip.textContent=f.label||f.finding_code;$('chips').appendChild(chip)}
      const prior=$('metrics').textContent||'';$('metrics').textContent=`${prior}${prior?' • ':''}${PANORAMIC_SIMULATION_LABEL}; bukkolingual derinlik anatomik referanstır.`;
    }catch(err){console.warn('[ANATOMY_DETAIL_FALLBACK]',err)}
  };

  function renderCurrentToothSheet(){
    if(typeof renderToothSheet==='function')renderToothSheet();
  }
  document.querySelectorAll('[data-tooth-tab]').forEach(b=>{b.onclick=()=>{toothTab=b.dataset.toothTab;document.querySelectorAll('[data-tooth-tab]').forEach(x=>x.classList.toggle('active',x===b));renderCurrentToothSheet()}});

  const baseAnalyze=analyze;
  analyze=async function(){
    $('analysisSheet')?.classList.add('hidden');$('stage')?.classList.remove('has-results');
    await baseAnalyze();if(!result?.anatomy3d)return;
    const count=allFindings().length,hidden=(result.findings||[]).filter(f=>findingScore(f)<MIN_DISPLAY_CONFIDENCE).length,meta=result.anatomy3d;result.anatomy3d.low_confidence_hidden=hidden;$('status').textContent=`${result.unique_fdi_count||result.tooth_count||0} diş • ${count} bulgu • ${meta.rendered_teeth} diş 3D'ye yerleştirildi • ${PANORAMIC_SIMULATION_LABEL}`;renderSheet('findings');setTimeout(()=>{if(jawScene&&window.jawRoot)fitCamera(jawScene,window.jawRoot,1.34)},260);
  };
  $('run').onclick=analyze;
  document.querySelectorAll('[data-sheet-tab]').forEach(b=>{b.onclick=()=>renderSheet(b.dataset.sheetTab)});

  const style=document.createElement('style');style.textContent=`.detail-info{grid-template-columns:min(42vw,250px) 1fr;align-items:start;max-height:34vh;overflow:auto}.detail-info canvas{width:100%;height:auto;max-height:230px;object-fit:contain;background:#000}.chips{max-height:70px;overflow:auto}@media(max-width:620px){.detail-info{grid-template-columns:42vw 1fr;max-height:32vh}.detail-info canvas{width:100%;height:auto;max-height:190px}}`;document.head.appendChild(style);
})();
