// Dental AI experimental real-jaw layer.
// Uses Open-Full-Jaw patient-12 bone surfaces only as an anatomical reference frame.
// Patient tooth presence/tilt/relative spacing still comes from the uploaded panorama.
(function(){
  const MANIFEST_URL='https://raw.githubusercontent.com/choxos/OMFAtlas/main/public/models/dental/manifest.json';
  const BUFFER_URL='https://raw.githubusercontent.com/choxos/OMFAtlas/main/public/models/dental/open-full-jaw.bin';
  let templatePromise=null;

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
  const upper=fdi=>['1','2'].includes(String(fdi)[0]);
  const center=b=>[(+b[0]+ +b[2])/2,(+b[1]+ +b[3])/2];

  function geometryFor(part,buffer){
    const THREE=window.D3.THREE;
    const g=new THREE.BufferGeometry();
    g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(buffer,part.positions,part.vertexCount*3),3));
    if(Number.isFinite(part.normals))g.setAttribute('normal',new THREE.BufferAttribute(new Float32Array(buffer,part.normals,part.vertexCount*3),3));
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(buffer,part.indices,part.indexCount),1));
    if(!g.getAttribute('normal'))g.computeVertexNormals();
    return g;
  }

  function rotateSourcePoint(p){
    // Rx(-90°): x'=x, y'=z, z'=-y
    return [p[0],p[2],-p[1]];
  }

  async function loadTemplate(){
    if(templatePromise)return templatePromise;
    templatePromise=(async()=>{
      const THREE=window.D3.THREE;
      const [mr,br]=await Promise.all([fetch(MANIFEST_URL,{cache:'force-cache'}),fetch(BUFFER_URL,{cache:'force-cache'})]);
      if(!mr.ok)throw new Error('Çene manifesti yüklenemedi: '+mr.status);
      if(!br.ok)throw new Error('Çene modeli yüklenemedi: '+br.status);
      const manifest=await mr.json(),buffer=await br.arrayBuffer();
      const source=(manifest.parts||[]).filter(p=>p.source==='openfulljaw'&&(p.buffer||'')==='open-full-jaw');
      const bones=source.filter(p=>p.group==='bone');
      const teeth=source.filter(p=>p.group==='tooth'&&validFdi(p.fdi));
      if(bones.length<2||teeth.length<20)throw new Error('Open-Full-Jaw parçaları eksik');

      // Center against the entire source assembly so bone and tooth anchors stay registered.
      const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
      for(const p of source){for(let i=0;i<3;i++){lo[i]=Math.min(lo[i],+p.bounds[0][i]);hi[i]=Math.max(hi[i],+p.bounds[1][i]);}}
      const c=lo.map((v,i)=>(v+hi[i])/2);

      const raw=new THREE.Group();
      for(const p of bones){
        const mat=new THREE.MeshPhysicalMaterial({color:0xa9bde8,transparent:true,opacity:.24,roughness:.54,metalness:0,transmission:.08,depthWrite:false,side:THREE.DoubleSide});
        const mesh=new THREE.Mesh(geometryFor(p,buffer),mat);
        mesh.position.set(-c[0],-c[1],-c[2]);mesh.userData.jawPart=p.id;raw.add(mesh);
      }
      const oriented=new THREE.Group();oriented.rotation.x=-Math.PI/2;oriented.add(raw);oriented.updateMatrixWorld(true);
      const box=new THREE.Box3().setFromObject(oriented),size=new THREE.Vector3();box.getSize(size);

      // Hidden FDI anchors from the same real CBCT assembly. These are what keep roots inside sockets.
      const anchors=new Map();
      for(const p of teeth){
        const rawCenter=[(p.bounds[0][0]+p.bounds[1][0])/2-c[0],(p.bounds[0][1]+p.bounds[1][1])/2-c[1],(p.bounds[0][2]+p.bounds[1][2])/2-c[2]];
        anchors.set(Number(p.fdi),rotateSourcePoint(rawCenter));
      }
      return {group:oriented,size,anchors};
    })();
    return templatePromise;
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
    const gap=gaps.length?med(gaps):0;
    let label='temas belirsiz';
    if(gaps.length){
      if(gap<=-.035)label='röntgende örtüşme görülüyor';
      else if(gap>=.045)label='röntgende temas görünmüyor';
    }
    return {gapNorm:gap,pairs:gaps.length,label};
  }

  function polygonTilt(t){
    const p=t?.polygon;if(!Array.isArray(p)||p.length<6)return 0;
    let mx=0,my=0;for(const q of p){mx+=+q[0];my+=+q[1]}mx/=p.length;my/=p.length;
    let xx=0,yy=0,xy=0;for(const q of p){const x=+q[0]-mx,y=+q[1]-my;xx+=x*x;yy+=y*y;xy+=x*y}
    const tr=xx+yy,det=xx*yy-xy*xy,disc=Math.sqrt(Math.max(0,tr*tr/4-det)),lambda=tr/2+disc;
    let vx=xy,vy=lambda-xx;if(Math.abs(vx)+Math.abs(vy)<1e-8){vx=0;vy=1}
    const len=Math.hypot(vx,vy)||1;vx/=len;vy/=len;if(vy<0){vx=-vx;vy=-vy}
    return clamp(Math.atan2(vx,vy),-.48,.48);
  }

  function addCanal(scene,scale,offset){
    const THREE=window.D3.THREE,pts=[];
    // Reference-only canal visual; not claimed as patient-specific from a panorama.
    for(let i=0;i<=42;i++){const s=-1+i/21;pts.push(new THREE.Vector3(s*2.86,-1.02,-.56+1.68*(1-s*s)));}
    const curve=new THREE.CatmullRomCurve3(pts),geo=new THREE.TubeGeometry(curve,96,.042,10,false);
    const mesh=new THREE.Mesh(geo,new THREE.MeshStandardMaterial({color:0xff7898,emissive:0x67172a,emissiveIntensity:.24,transparent:true,opacity:.78}));
    mesh.position.copy(offset);scene.add(mesh);
  }

  function panoArchTarget(t,minX,maxX){
    const b=t.bbox.map(Number),cx=(b[0]+b[2])/2,n=(cx-minX)/Math.max(1,maxX-minX),s=(n-.5)*2;
    return {x:s*3.0,z:-.55+1.72*(1-s*s)};
  }

  renderJaw=async function(){
    await waitD3();disposeScene(jawScene);jawScene=createBase($('jaw3d'));
    const {scene,camera,controls,renderer}=jawScene;
    const teeth=(result?.teeth||[]).map(t=>{if(t)t.fdi=normalizeFdi(t.fdi);return t}).filter(t=>t?.bbox&&validFdi(t.fdi));
    if(!teeth.length)throw new Error('FDI diş tespiti yok');

    const occ=occlusionFromPanorama(teeth);result.occlusion_profile=occ;result.occlusion_label=occ.label;
    camera.position.set(0,.20,18.2);controls.target.set(0,-.10,.05);controls.minDistance=7;controls.maxDistance=28;

    const template=await loadTemplate();
    const jawScale=7.55/Math.max(1,template.size.x);
    const jawOffset=new window.D3.THREE.Vector3(0,-.08,.18);
    const jaw=template.group.clone(true);jaw.scale.setScalar(jawScale);jaw.position.copy(jawOffset);
    jaw.traverse(n=>{if(n.isMesh){n.material=n.material.clone();n.material.opacity=.23;n.material.depthWrite=false;}});
    scene.add(jaw);
    addCanal(scene,jawScale,jawOffset);

    const widths=teeth.map(t=>+t.bbox[2]-+t.bbox[0]),heights=teeth.map(t=>+t.bbox[3]-+t.bbox[1]);
    const mw=Math.max(1,med(widths)),mh=Math.max(1,med(heights));
    const minX=Math.min(...teeth.map(t=>+t.bbox[0])),maxX=Math.max(...teeth.map(t=>+t.bbox[2]));
    const upperCy=med(teeth.filter(t=>upper(t.fdi)).map(t=>center(t.bbox)[1]));
    const lowerCy=med(teeth.filter(t=>!upper(t.fdi)).map(t=>center(t.bbox)[1]));

    const clickables=[];
    const loaded=await Promise.all(teeth.map(async t=>{try{return[t,await loadToothObject(t.fdi)]}catch(e){console.warn('anatomy',t.fdi,e);return[t,null]}}));
    for(const [t,obj] of loaded){
      if(!obj)continue;
      const anchor=template.anchors.get(Number(t.fdi));
      const pano=panoArchTarget(t,minX,maxX);
      let x=pano.x,y=upper(t.fdi)?.58:-.58,z=pano.z;
      if(anchor){
        // Bone/tooth registration comes first; panorama only nudges the source anchor.
        const ax=anchor[0]*jawScale+jawOffset.x,ay=anchor[1]*jawScale+jawOffset.y,az=anchor[2]*jawScale+jawOffset.z;
        x=ax*.88+pano.x*.12;z=az*.90+pano.z*.10;y=ay;
      }

      // Only a small visible-radiograph correction: panoramic geometry cannot supply true 3-D bite depth.
      const cy=center(t.bbox)[1],base=upper(t.fdi)?upperCy:lowerCy;
      y+=clamp((cy-base)/mh,-.7,.7)*.08;
      if(occ.label==='röntgende temas görünmüyor')y+=upper(t.fdi)?.055:-.055;
      else if(occ.label==='röntgende örtüşme görülüyor')y+=upper(t.fdi)?-.025:.025;

      const s=patientScale(t,mw,mh),side=clamp(x/3.2,-1,1);
      obj.scale.set(.48*s.x,.48*s.y,.48*s.z);obj.position.set(x,y,z);obj.rotation.y=-side*.52;obj.rotation.z=(upper(t.fdi)?Math.PI:0)-polygonTilt(t);
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
    await previousAnalyze();if(!result)return;
    const count=(result.findings||[]).filter(f=>f&&f.finding_code).length;
    $('status').textContent=`${result.unique_fdi_count||result.tooth_count||0} diş • ${count} bulgu • ${result.occlusion_label||'temas belirsiz'}`;
  };
  $('run').onclick=analyze;
})();
