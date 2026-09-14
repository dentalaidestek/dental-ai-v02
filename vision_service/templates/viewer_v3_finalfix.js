// Final visual alignment patch: same-source jaw + teeth, compact findings, smooth detail tooth.
(function(){
  const MANIFEST_URL='https://raw.githubusercontent.com/choxos/OMFAtlas/main/public/models/dental/manifest.json';
  const BUFFER_URL='https://raw.githubusercontent.com/choxos/OMFAtlas/main/public/models/dental/open-full-jaw.bin';
  let dataPromise=null;

  const validFdi=v=>/^[1-4][1-8]$/.test(String(v??''));
  const upper=fdi=>['1','2'].includes(String(fdi)[0]);
  const normalizeFdi=v=>{
    const s=String(v??'').trim();
    if(validFdi(s)) return Number(s);
    const m=s.match(/(?:^|\D)([1-4][1-8])(?:\D|$)/); if(m) return Number(m[1]);
    const d=s.replace(/\D/g,''); if(d.length>=2){const t=d.slice(-2); if(validFdi(t)) return Number(t)}
    return v;
  };

  function geometryFor(part,buffer){
    const THREE=window.D3.THREE;
    const g=new THREE.BufferGeometry();
    g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(buffer,part.positions,part.vertexCount*3),3));
    if(Number.isFinite(part.normals)) g.setAttribute('normal',new THREE.BufferAttribute(new Float32Array(buffer,part.normals,part.vertexCount*3),3));
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(buffer,part.indices,part.indexCount),1));
    if(!g.getAttribute('normal')) g.computeVertexNormals();
    return g;
  }

  async function loadData(){
    if(dataPromise) return dataPromise;
    dataPromise=(async()=>{
      const [mr,br]=await Promise.all([fetch(MANIFEST_URL,{cache:'force-cache'}),fetch(BUFFER_URL,{cache:'force-cache'})]);
      if(!mr.ok||!br.ok) throw new Error('Open-Full-Jaw modeli yüklenemedi');
      const manifest=await mr.json(),buffer=await br.arrayBuffer();
      const parts=(manifest.parts||[]).filter(p=>p.source==='openfulljaw'&&(p.buffer||'')==='open-full-jaw');
      const bones=parts.filter(p=>p.group==='bone');
      const teeth=parts.filter(p=>p.group==='tooth'&&validFdi(p.fdi));
      if(bones.length<2||teeth.length<20) throw new Error('Open-Full-Jaw parçaları eksik');
      const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
      for(const p of parts) for(let i=0;i<3;i++){lo[i]=Math.min(lo[i],+p.bounds[0][i]);hi[i]=Math.max(hi[i],+p.bounds[1][i]);}
      const center=lo.map((v,i)=>(v+hi[i])/2);
      return {buffer,bones,teethByFdi:new Map(teeth.map(p=>[Number(p.fdi),p])),center};
    })();
    return dataPromise;
  }

  function toothFindings(t){
    const all=(result?.findings||[]).filter(f=>f&&f.finding_code);
    const out=[];
    const seen=new Set();
    for(const f of all){
      if(String(f.fdi||'')!==String(t.fdi)) continue;
      const k=String(f.finding_code); if(seen.has(k)) continue; seen.add(k); out.push(f);
    }
    return out;
  }

  function findingColor(code){
    code=String(code||'');
    if(/CARIES|PERIAPICAL|RADIOLUCENT|RESORPTION/.test(code)) return 0xff5b6f;
    if(/ROOT_CANAL|ENDO|POST/.test(code)) return 0xff83b3;
    if(/FILLING|CROWN|BRIDGE|INLAY|PONTIC|IMPLANT/.test(code)) return 0x60d7ff;
    return 0xffa34d;
  }

  function makeToothMesh(part,buffer,center,findings){
    const THREE=window.D3.THREE;
    const has=Array.isArray(findings)&&findings.length>0;
    const mat=new THREE.MeshPhysicalMaterial({
      color:has?0xffe3df:0xf4f1e8,
      roughness:.30,metalness:0,clearcoat:.14,
      transparent:false,opacity:1,side:THREE.DoubleSide
    });
    const mesh=new THREE.Mesh(geometryFor(part,buffer),mat);
    mesh.position.set(-center[0],-center[1],-center[2]);
    return mesh;
  }

  function fitCamera(ctx,obj,pad=1.28){
    const {THREE}=window.D3;
    obj.updateMatrixWorld(true);
    const box=new THREE.Box3().setFromObject(obj),c=new THREE.Vector3(),s=new THREE.Vector3();
    box.getCenter(c);box.getSize(s);
    const radius=Math.max(.1,Math.hypot(s.x,s.y,s.z)/2);
    const fov=ctx.camera.fov*Math.PI/180;
    const dist=(radius/Math.sin(fov/2))*pad;
    ctx.controls.target.copy(c);
    ctx.camera.position.set(c.x,c.y+radius*.05,c.z+dist);
    ctx.camera.near=Math.max(.01,dist-radius*2.2);
    ctx.camera.far=dist+radius*4;
    ctx.camera.updateProjectionMatrix();
    ctx.controls.minDistance=Math.max(radius*.65,1.5);
    ctx.controls.maxDistance=dist*2.4;
    ctx.controls.update();
  }

  function addFindingMarker(group,part,assemblyCenter,count,color){
    if(!count) return;
    const THREE=window.D3.THREE;
    const c=Array.isArray(part?.axes?.center)?part.axes.center:part.bounds[0].map((v,i)=>(+v + +part.bounds[1][i])/2);
    const p=new THREE.Vector3(c[0]-assemblyCenter[0],c[1]-assemblyCenter[1],c[2]-assemblyCenter[2]);
    const dot=new THREE.Mesh(
      new THREE.SphereGeometry(1.25,16,12),
      new THREE.MeshStandardMaterial({color,emissive:color,emissiveIntensity:.28,transparent:true,opacity:.90,depthWrite:false})
    );
    dot.position.copy(p);
    dot.userData.findingMarker=true;
    group.add(dot);
  }

  renderJaw=async function(){
    await waitD3();
    disposeScene(jawScene); jawScene=createBase($('jaw3d'));
    const {scene,renderer,camera}=jawScene;
    const data=await loadData();
    const patient=(result?.teeth||[]).map(t=>{if(t)t.fdi=normalizeFdi(t.fdi);return t}).filter(t=>t?.bbox&&validFdi(t.fdi));
    if(!patient.length) throw new Error('FDI diş tespiti yok');

    const root=new window.D3.THREE.Group();
    root.rotation.x=-Math.PI/2;
    scene.add(root);

    const boneMat=()=>new window.D3.THREE.MeshPhysicalMaterial({
      color:0xa8b9de,transparent:true,opacity:.16,roughness:.56,metalness:0,transmission:.06,depthWrite:false,side:window.D3.THREE.DoubleSide
    });
    for(const part of data.bones){
      const mesh=new window.D3.THREE.Mesh(geometryFor(part,data.buffer),boneMat());
      mesh.position.set(-data.center[0],-data.center[1],-data.center[2]);
      root.add(mesh);
    }

    const clickables=[];
    for(const t of patient){
      const part=data.teethByFdi.get(Number(t.fdi));
      if(!part) continue;
      const findings=toothFindings(t);
      const mesh=makeToothMesh(part,data.buffer,data.center,findings);
      mesh.userData.tooth=t;
      clickables.push(mesh);
      root.add(mesh);
      if(findings.length){
        addFindingMarker(root,part,data.center,findings.length,findingColor(findings[0].finding_code));
      }
    }

    root.scale.setScalar(.058);
    fitCamera(jawScene,root,1.18);

    const THREE=window.D3.THREE,ray=new THREE.Raycaster(),mouse=new THREE.Vector2();
    renderer.domElement.addEventListener('pointerdown',ev=>{
      const r=renderer.domElement.getBoundingClientRect();
      mouse.x=((ev.clientX-r.left)/r.width)*2-1;mouse.y=-((ev.clientY-r.top)/r.height)*2+1;
      ray.setFromCamera(mouse,camera);
      const hit=ray.intersectObjects(clickables,false)[0];
      if(hit?.object?.userData?.tooth) openTooth(hit.object.userData.tooth);
    });
  };

  const oldOpenTooth=openTooth;
  openTooth=async function(t){
    await oldOpenTooth(t);
    try{
      const data=await loadData(),part=data.teethByFdi.get(Number(normalizeFdi(t.fdi)));
      if(!part) return;
      await waitD3();
      disposeScene(toothScene); toothScene=createBase($('tooth3d'));
      const THREE=window.D3.THREE;
      const group=new THREE.Group(); group.rotation.x=-Math.PI/2;
      const g=geometryFor(part,data.buffer);
      const c=Array.isArray(part?.axes?.center)?part.axes.center:part.bounds[0].map((v,i)=>(+v + +part.bounds[1][i])/2);
      g.translate(-c[0],-c[1],-c[2]);
      const f=toothFindings(t);
      const mesh=new THREE.Mesh(g,new THREE.MeshPhysicalMaterial({
        color:0xf2eee6,roughness:.24,clearcoat:.20,transparent:true,opacity:.78,side:THREE.DoubleSide,depthWrite:true
      }));
      group.add(mesh);

      const tb=t.bbox.map(Number),tw=Math.max(1,tb[2]-tb[0]),th=Math.max(1,tb[3]-tb[1]);
      const box=new THREE.Box3().setFromObject(group),size=new THREE.Vector3();box.getSize(size);
      for(const item of f){
        if(!Array.isArray(item.bbox)||item.bbox.length!==4) continue;
        const b=item.bbox.map(Number),cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2;
        const nx=((cx-(tb[0]+tb[2])/2)/tw), ny=((cy-(tb[1]+tb[3])/2)/th);
        const marker=new THREE.Mesh(
          new THREE.SphereGeometry(Math.max(.35,size.x*.035),18,12),
          new THREE.MeshStandardMaterial({color:findingColor(item.finding_code),emissive:findingColor(item.finding_code),emissiveIntensity:.35,transparent:true,opacity:.86,depthWrite:false})
        );
        marker.position.set(nx*size.x*.72,-ny*size.y*.86,size.z*.52);
        group.add(marker);
      }
      toothScene.scene.add(group);
      group.scale.setScalar(.065);
      fitCamera(toothScene,group,1.34);
    }catch(err){console.warn('[SMOOTH_DETAIL_FALLBACK]',err);}
  };

  const style=document.createElement('style');
  style.textContent=`
    .detail-info{grid-template-columns:min(42vw,250px) 1fr;align-items:start;max-height:38vh;overflow:auto}
    .detail-info canvas{width:100%;height:auto;max-height:250px;object-fit:contain;background:#000}
    .chips{max-height:82px;overflow:auto}
    @media(max-width:620px){.detail-info{grid-template-columns:42vw 1fr}.detail-info canvas{width:100%;height:auto;max-height:210px}}
  `;
  document.head.appendChild(style);
})();
