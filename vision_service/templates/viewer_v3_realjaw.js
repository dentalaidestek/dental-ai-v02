// Dental AI experimental real-jaw layer.
// Loads ONLY the maxilla/mandible bone surfaces from the openly published
// Open-Full-Jaw patient-12 package redistributed by OMFAtlas. The bone is a
// visual anatomical reference, not a patient-specific reconstruction from a panorama.
(function(){
  const MANIFEST_URL='https://raw.githubusercontent.com/choxos/OMFAtlas/main/public/models/dental/manifest.json';
  const BUFFER_URL='https://raw.githubusercontent.com/choxos/OMFAtlas/main/public/models/dental/open-full-jaw.bin';
  let jawTemplatePromise=null;

  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const med=a=>{const x=a.filter(Number.isFinite).slice().sort((p,q)=>p-q);return x.length?x[Math.floor(x.length/2)]:0};
  const validFdi=v=>/^[1-4][1-8]$/.test(String(v??''));
  const normalizeFdi=v=>{
    const s=String(v??'').trim();
    if(validFdi(s))return Number(s);
    const m=s.match(/(?:^|\D)([1-4][1-8])(?:\D|$)/);if(m)return Number(m[1]);
    const d=s.replace(/\D/g,'');if(d.length>=2){const t=d.slice(-2);if(validFdi(t))return Number(t)}
    return v;
  };
  const center=b=>[(+b[0]+ +b[2])/2,(+b[1]+ +b[3])/2];
  const upper=fdi=>['1','2'].includes(String(fdi)[0]);

  function geometryFor(part,buffer){
    const THREE=window.D3.THREE;
    const g=new THREE.BufferGeometry();
    g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(buffer,part.positions,part.vertexCount*3),3));
    if(Number.isFinite(part.normals))g.setAttribute('normal',new THREE.BufferAttribute(new Float32Array(buffer,part.normals,part.vertexCount*3),3));
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(buffer,part.indices,part.indexCount),1));
    if(!g.getAttribute('normal'))g.computeVertexNormals();
    return g;
  }

  async function loadJawTemplate(){
    if(jawTemplatePromise)return jawTemplatePromise;
    jawTemplatePromise=(async()=>{
      const THREE=window.D3.THREE;
      const [mr,br]=await Promise.all([fetch(MANIFEST_URL,{cache:'force-cache'}),fetch(BUFFER_URL,{cache:'force-cache'})]);
      if(!mr.ok)throw new Error('Çene manifesti yüklenemedi: '+mr.status);
      if(!br.ok)throw new Error('Çene modeli yüklenemedi: '+br.status);
      const manifest=await mr.json(),buffer=await br.arrayBuffer();
      const parts=(manifest.parts||[]).filter(p=>p.source==='openfulljaw'&&p.group==='bone'&&(p.buffer||'')==='open-full-jaw');
      if(parts.length<2)throw new Error('Gerçek mandibula/maksilla parçaları bulunamadı');
      const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
      for(const p of parts)for(let i=0;i<3;i++){lo[i]=Math.min(lo[i],+p.bounds[0][i]);hi[i]=Math.max(hi[i],+p.bounds[1][i]);}
      const c=lo.map((v,i)=>(v+hi[i])/2);
      const group=new THREE.Group();
      for(const p of parts){
        const mat=new THREE.MeshPhysicalMaterial({color:0xa9bde8,transparent:true,opacity:.22,roughness:.52,metalness:0,transmission:.10,depthWrite:false,side:THREE.DoubleSide});
        const mesh=new THREE.Mesh(geometryFor(p,buffer),mat);
        mesh.position.set(-c[0],-c[1],-c[2]);mesh.userData.jawPart=p.id;group.add(mesh);
      }
      // Same source orientation used by OMFAtlas: long tooth axis upright.
      group.rotation.x=-Math.PI/2;
      group.updateMatrixWorld(true);
      const box=new THREE.Box3().setFromObject(group),size=new THREE.Vector3();box.getSize(size);
      group.userData.rawSize=size.clone();
      return group;
    })();
    return jawTemplatePromise;
  }

  function occlusionFromPanorama(teeth){
    const OPP={11:41,12:42,13:43,14:44,15:45,16:46,17:47,18:48,21:31,22:32,23:33,24:34,25:35,26:36,27:37,28:38};
    const by=new Map(teeth.map(t=>[Number(t.fdi),t])),gaps=[];
    for(const [u,l] of Object.entries(OPP)){
      const U=by.get(+u),L=by.get(+l);if(!U||!L)continue;
      const ub=U.bbox.map(Number),lb=L.bbox.map(Number);
      const h=Math.max(1,((ub[3]-ub[1])+(lb[3]-lb[1]))/2);
      const g=(lb[1]-ub[3])/h;
      if(Math.abs(g)<=.9)gaps.push(g);
    }
    const gap=med(gaps);
    let label='temas belirsiz';
    if(gaps.length){
      if(gap<=-.035)label='röntgende örtüşme görülüyor';
      else if(gap>=.045)label='röntgende temas görünmüyor';
    }
    // Visual spacing only. Never treat this as measured 3-D occlusion.
    const separation=clamp(1.00+gap*.32,.86,1.36);
    return {gapNorm:gap,pairs:gaps.length,label,separation};
  }

  function polygonTilt(t){
    const p=t?.polygon;if(!Array.isArray(p)||p.length<6)return 0;
    let mx=0,my=0;for(const q of p){mx+=+q[0];my+=+q[1]}mx/=p.length;my/=p.length;
    let xx=0,yy=0,xy=0;for(const q of p){const x=+q[0]-mx,y=+q[1]-my;xx+=x*x;yy+=y*y;xy+=x*y}
    const tr=xx+yy,det=xx*yy-xy*xy,disc=Math.sqrt(Math.max(0,tr*tr/4-det)),lambda=tr/2+disc;
    let vx=xy,vy=lambda-xx;if(Math.abs(vx)+Math.abs(vy)<1e-8){vx=0;vy=1}
    const len=Math.hypot(vx,vy)||1;vx/=len;vy/=len;if(vy<0){vx=-vx;vy=-vy}
    return clamp(Math.atan2(vx,vy),-.55,.55);
  }

  function toothPose(t,minX,maxX,occ,upperCy,lowerCy,mh){
    const b=t.bbox.map(Number),cx=(b[0]+b[2])/2,n=(cx-minX)/Math.max(1,maxX-minX),s=(n-.5)*2,isUp=upper(t.fdi);
    const cy=(b[1]+b[3])/2,base=isUp?upperCy:lowerCy,imgOff=clamp((cy-base)/mh,-.8,.8)*.20;
    return {x:s*3.10,y:(isUp?1:-1)*(occ.separation/2)-imgOff,z:-.72+2.05*(1-s*s),rotY:-s*.58,rotZ:(isUp?Math.PI:0)-polygonTilt(t),upper:isUp};
  }

  function addCanal(scene,occ){
    const THREE=window.D3.THREE,pts=[];
    for(let i=0;i<=42;i++){const s=-1+i/21;pts.push(new THREE.Vector3(s*2.95,-occ.separation/2-.78,-.62+1.76*(1-s*s)));}
    const curve=new THREE.CatmullRomCurve3(pts),geo=new THREE.TubeGeometry(curve,96,.045,10,false);
    scene.add(new THREE.Mesh(geo,new THREE.MeshStandardMaterial({color:0xff7898,emissive:0x67172a,emissiveIntensity:.25,transparent:true,opacity:.82})));
  }

  renderJaw=async function(){
    await waitD3();
    disposeScene(jawScene);jawScene=createBase($('jaw3d'));
    const {scene,camera,controls,renderer}=jawScene;
    const teeth=(result?.teeth||[]).map(t=>{if(t)t.fdi=normalizeFdi(t.fdi);return t}).filter(t=>t?.bbox&&validFdi(t.fdi));
    if(!teeth.length)throw new Error('FDI diş tespiti yok');

    const occ=occlusionFromPanorama(teeth);result.occlusion_profile=occ;result.occlusion_label=occ.label;
    camera.position.set(0,.15,15.8);controls.target.set(0,-.05,.15);controls.minDistance=6.0;controls.maxDistance=24;

    // Real maxilla + mandible surface mesh. It remains reference anatomy; patient teeth come from this panorama.
    try{
      const template=await loadJawTemplate(),jaw=template.clone(true),raw=template.userData.rawSize||new window.D3.THREE.Vector3(140,95,100);
      const targetWidth=7.65,scale=targetWidth/Math.max(1,raw.x);
      jaw.scale.setScalar(scale);
      jaw.position.set(0,-.05,.30);
      jaw.traverse(n=>{if(n.isMesh){n.material=n.material.clone();n.material.opacity=.20;n.material.depthWrite=false;}});
      scene.add(jaw);
    }catch(err){
      console.warn('[REAL_JAW_FALLBACK]',err);
      showError('Gerçek çene modeli yüklenemedi; dişler yine gösteriliyor.');
    }
    addCanal(scene,occ);

    const widths=teeth.map(t=>+t.bbox[2]-+t.bbox[0]),heights=teeth.map(t=>+t.bbox[3]-+t.bbox[1]);
    const mw=Math.max(1,med(widths)),mh=Math.max(1,med(heights));
    const minX=Math.min(...teeth.map(t=>+t.bbox[0])),maxX=Math.max(...teeth.map(t=>+t.bbox[2]));
    const upperCy=med(teeth.filter(t=>upper(t.fdi)).map(t=>center(t.bbox)[1]));
    const lowerCy=med(teeth.filter(t=>!upper(t.fdi)).map(t=>center(t.bbox)[1]));
    const clickables=[];
    const loaded=await Promise.all(teeth.map(async t=>{try{return[t,await loadToothObject(t.fdi)]}catch(e){console.warn('anatomy',t.fdi,e);return[t,null]}}));
    for(const [t,obj] of loaded){
      if(!obj)continue;
      const p=toothPose(t,minX,maxX,occ,upperCy,lowerCy,mh),s=patientScale(t,mw,mh);
      obj.scale.set(.57*s.x,.57*s.y,.57*s.z);obj.position.set(p.x,p.y,p.z);obj.rotation.y=p.rotY;obj.rotation.z=p.rotZ;
      obj.userData.tooth=t;obj.traverse(n=>{if(n.isMesh){n.userData.tooth=t;clickables.push(n)}});scene.add(obj);
    }
    const THREE=window.D3.THREE,ray=new THREE.Raycaster(),mouse=new THREE.Vector2();
    renderer.domElement.addEventListener('pointerdown',ev=>{
      const r=renderer.domElement.getBoundingClientRect();mouse.x=((ev.clientX-r.left)/r.width)*2-1;mouse.y=-((ev.clientY-r.top)/r.height)*2+1;
      ray.setFromCamera(mouse,camera);const hit=ray.intersectObjects(clickables,false)[0];if(hit?.object?.userData?.tooth)openTooth(hit.object.userData.tooth);
    });
  };

  const previousAnalyze=analyze;
  analyze=async function(){
    await previousAnalyze();
    if(!result)return;
    const count=(result.findings||[]).filter(f=>f&&f.finding_code).length;
    const label=result.occlusion_label||'temas belirsiz';
    $('status').textContent=`${result.unique_fdi_count||result.tooth_count||0} diş • ${count} bulgu • ${label}`;
  };
  $('run').onclick=analyze;
})();
