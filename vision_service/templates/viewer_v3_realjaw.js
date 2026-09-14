// Dental AI real-jaw viewer v3.
// Open-Full-Jaw provides a real CBCT-derived maxilla/mandible + tooth socket reference.
// Uploaded panoramic supplies tooth presence, visible tilt, 2-D length/contact cues and findings.
// Bone depth and true 3-D occlusion are never invented from a panorama.
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

  function sourceCenter(part){
    if(Array.isArray(part?.axes?.center)&&part.axes.center.length===3)return part.axes.center.map(Number);
    return part.bounds[0].map((v,i)=>(+v + +part.bounds[1][i])/2);
  }

  function projectedSpan(bounds,axis){
    if(!bounds||!axis)return 1;
    const a=axis.map(Number), corners=[];
    for(const x of [bounds[0][0],bounds[1][0]])for(const y of [bounds[0][1],bounds[1][1]])for(const z of [bounds[0][2],bounds[1][2]])corners.push([+x,+y,+z]);
    const vals=corners.map(p=>p[0]*a[0]+p[1]*a[1]+p[2]*a[2]);
    return Math.max(1e-6,Math.max(...vals)-Math.min(...vals));
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
      const toothParts=source.filter(p=>p.group==='tooth'&&validFdi(p.fdi));
      if(bones.length<2||toothParts.length<20)throw new Error('Open-Full-Jaw parçaları eksik');

      const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
      for(const p of source)for(let i=0;i<3;i++){lo[i]=Math.min(lo[i],+p.bounds[0][i]);hi[i]=Math.max(hi[i],+p.bounds[1][i]);}
      const assemblyCenter=lo.map((v,i)=>(v+hi[i])/2);

      const rawBone=new THREE.Group();
      for(const p of bones){
        const mat=new THREE.MeshPhysicalMaterial({color:0xa9bde8,transparent:true,opacity:.22,roughness:.55,metalness:0,transmission:.09,depthWrite:false,side:THREE.DoubleSide});
        const mesh=new THREE.Mesh(geometryFor(p,buffer),mat);
        mesh.position.set(-assemblyCenter[0],-assemblyCenter[1],-assemblyCenter[2]);
        mesh.userData.jawPart=p.id;
        rawBone.add(mesh);
      }
      const boneGroup=new THREE.Group();
      boneGroup.rotation.x=-Math.PI/2;
      boneGroup.add(rawBone);
      boneGroup.updateMatrixWorld(true);
      const box=new THREE.Box3().setFromObject(boneGroup),size=new THREE.Vector3();box.getSize(size);

      const partsByFdi=new Map(toothParts.map(p=>[Number(p.fdi),p]));
      return {boneGroup,size,partsByFdi,buffer,assemblyCenter};
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
      if(gap<=-.08)label='röntgende örtüşme görülüyor';
      else if(gap>=.08)label='röntgende temas görünmüyor';
    }
    return {gapNorm:gap,pairs:gaps.length,label};
  }

  function polygonAxis(t){
    const p=t?.polygon;
    if(!Array.isArray(p)||p.length<6){
      const b=t.bbox.map(Number),c=center(b);
      return {cx:c[0],cy:c[1],vx:0,vy:1,length:Math.max(1,b[3]-b[1]),width:Math.max(1,b[2]-b[0]),tilt:0};
    }
    let mx=0,my=0;for(const q of p){mx+=+q[0];my+=+q[1]}mx/=p.length;my/=p.length;
    let xx=0,yy=0,xy=0;
    for(const q of p){const dx=+q[0]-mx,dy=+q[1]-my;xx+=dx*dx;yy+=dy*dy;xy+=dx*dy}
    const tr=xx+yy,det=xx*yy-xy*xy,disc=Math.sqrt(Math.max(0,tr*tr/4-det)),lambda=tr/2+disc;
    let vx=xy,vy=lambda-xx;if(Math.abs(vx)+Math.abs(vy)<1e-8){vx=0;vy=1}
    const n=Math.hypot(vx,vy)||1;vx/=n;vy/=n;if(vy<0){vx=-vx;vy=-vy}
    const ux=-vy,uy=vx,lp=[],wp=[];
    for(const q of p){const dx=+q[0]-mx,dy=+q[1]-my;lp.push(dx*vx+dy*vy);wp.push(dx*ux+dy*uy)}
    return {
      cx:mx,cy:my,vx,vy,
      length:Math.max(1,Math.max(...lp)-Math.min(...lp)),
      width:Math.max(1,Math.max(...wp)-Math.min(...wp)),
      tilt:clamp(Math.atan2(vx,vy),-.55,.55)
    };
  }

  function allPatientTeeth(){
    return (result?.teeth||[]).map(t=>{if(t)t.fdi=normalizeFdi(t.fdi);return t}).filter(t=>t?.bbox&&validFdi(t.fdi));
  }

  function contactMetrics(tooth,teeth){
    const same=teeth.filter(t=>upper(t.fdi)===upper(tooth.fdi)).sort((a,b)=>center(a.bbox)[0]-center(b.bbox)[0]);
    const i=same.findIndex(t=>String(t.fdi)===String(tooth.fdi));
    const out={mesial:null,distal:null};
    const pair=(a,b)=>{
      if(!a||!b)return null;
      const ab=a.bbox.map(Number),bb=b.bbox.map(Number);
      const gap=bb[0]-ab[2],w=Math.max(1,Math.min(ab[2]-ab[0],bb[2]-bb[0])),r=gap/w;
      if(r>0.10)return {label:'aralık',ratio:r};
      if(r<-0.10)return {label:'projeksiyonda örtüşme',ratio:r};
      return {label:'temas/belirsiz',ratio:r};
    };
    if(i>0)out.mesial=pair(same[i-1],same[i]);
    if(i>=0&&i<same.length-1)out.distal=pair(same[i],same[i+1]);
    return out;
  }

  function estimateCrest(t,crop){
    const c=crop.canvas,img=crop.image,[x1,y1,x2,y2]=t.bbox.map(Number);
    const L=clamp(Math.round(x1-crop.sx),0,c.width-1),R=clamp(Math.round(x2-crop.sx),0,c.width-1);
    const T=clamp(Math.round(y1-crop.sy),0,c.height-1),B=clamp(Math.round(y2-crop.sy),0,c.height-1);
    const w=Math.max(3,R-L),h=Math.max(3,B-T),isUp=upper(t.fdi);
    const yA=Math.round(T+h*(isUp?.43:.22)),yB=Math.round(T+h*(isUp?.78:.57));
    const gray=(x,y)=>{const i=(y*c.width+x)*4;return (img.data[i]+img.data[i+1]+img.data[i+2])/3};
    const bestInBand=(xa,xb)=>{
      let bestY=null,best=-1;
      for(let y=Math.max(1,yA);y<=Math.min(c.height-2,yB);y++){
        let s=0,n=0;
        for(let x=Math.max(1,xa);x<=Math.min(c.width-2,xb);x++){
          s+=Math.abs(gray(x,y+1)-gray(x,y-1))+0.35*Math.abs(gray(x+1,y)-gray(x-1,y));n++;
        }
        if(n&&s/n>best){best=s/n;bestY=y}
      }
      return bestY;
    };
    const left=bestInBand(L+Math.round(w*.05),L+Math.round(w*.30));
    const right=bestInBand(L+Math.round(w*.70),L+Math.round(w*.95));
    return {left,right,L,R,T,B,score:Math.max(0,left!==null&&right!==null?1:0)};
  }

  function estimateCanalTrace(t,crop){
    const c=crop.canvas,img=crop.image,[x1,y1,x2,y2]=t.bbox.map(Number),isUp=upper(t.fdi);
    const L=clamp(Math.round(x1-crop.sx),0,c.width-1),R=clamp(Math.round(x2-crop.sx),0,c.width-1);
    const T=clamp(Math.round(y1-crop.sy),0,c.height-1),B=clamp(Math.round(y2-crop.sy),0,c.height-1);
    const w=Math.max(4,R-L),h=Math.max(6,B-T);
    let ys=[];
    if(isUp){for(let y=Math.round(T+h*.08);y<=Math.round(T+h*.66);y+=2)ys.push(y)}
    else{for(let y=Math.round(T+h*.34);y<=Math.round(T+h*.94);y+=2)ys.push(y)}
    const gray=(x,y)=>{const i=(y*c.width+x)*4;return (img.data[i]+img.data[i+1]+img.data[i+2])/3};
    const pts=[];let prev=(L+R)/2;
    for(const y of ys){
      let bestX=null,best=1e9;
      const xa=Math.max(L+Math.round(w*.18),Math.round(prev-w*.20)),xb=Math.min(R-Math.round(w*.18),Math.round(prev+w*.20));
      for(let x=xa;x<=xb;x++){
        const v=(gray(x-1,y)+2*gray(x,y)+gray(x+1,y))/4;
        if(v<best){best=v;bestX=x}
      }
      if(bestX!==null){pts.push([bestX,y]);prev=bestX}
    }
    if(pts.length<7)return [];
    const smooth=pts.map((p,i)=>{
      let sx=0,sy=0,n=0;
      for(let j=Math.max(0,i-2);j<=Math.min(pts.length-1,i+2);j++){sx+=pts[j][0];sy+=pts[j][1];n++}
      return [sx/n,sy/n];
    });
    return smooth.filter((_,i)=>i%2===0);
  }

  function drawDiagnosticCrop(t){
    const crop=cropTooth(t),ctx=crop.canvas.getContext('2d'),axis=polygonAxis(t),contacts=contactMetrics(t,allPatientTeeth()),crest=estimateCrest(t,crop),canal=estimateCanalTrace(t,crop);
    ctx.save();

    if(Array.isArray(t.polygon)&&t.polygon.length>2){
      ctx.beginPath();
      t.polygon.forEach((p,i)=>{const x=p[0]-crop.sx,y=p[1]-crop.sy;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});
      ctx.closePath();ctx.lineWidth=2;ctx.strokeStyle='rgba(92,255,189,.95)';ctx.stroke();
    }

    const len=Math.max(axis.length*.62,18),cx=axis.cx-crop.sx,cy=axis.cy-crop.sy;
    ctx.beginPath();ctx.moveTo(cx-axis.vx*len,cy-axis.vy*len);ctx.lineTo(cx+axis.vx*len,cy+axis.vy*len);
    ctx.lineWidth=2;ctx.strokeStyle='rgba(255,218,91,.95)';ctx.setLineDash([5,4]);ctx.stroke();ctx.setLineDash([]);

    if(crest.left!==null&&crest.right!==null){
      ctx.beginPath();ctx.moveTo(crest.L+Math.max(2,(crest.R-crest.L)*.10),crest.left);ctx.lineTo(crest.R-Math.max(2,(crest.R-crest.L)*.10),crest.right);
      ctx.lineWidth=2;ctx.strokeStyle='rgba(94,180,255,.95)';ctx.setLineDash([3,3]);ctx.stroke();ctx.setLineDash([]);
    }

    if(canal.length){
      ctx.beginPath();canal.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));
      ctx.lineWidth=1.6;ctx.strokeStyle='rgba(255,105,154,.88)';ctx.setLineDash([3,2]);ctx.stroke();ctx.setLineDash([]);
    }

    for(const f of findingsFor(t)){
      if(!Array.isArray(f.bbox)||f.bbox.length!==4)continue;
      const b=f.bbox.map(Number),x=b[0]-crop.sx,y=b[1]-crop.sy,w=b[2]-b[0],h=b[3]-b[1];
      ctx.strokeStyle='rgba(255,94,94,.95)';ctx.lineWidth=1.6;ctx.strokeRect(x,y,w,h);
    }
    ctx.restore();

    const fmt=x=>x?x.label:'yok';
    const base=$('metrics').textContent||'';
    $('metrics').textContent=
      `${base}${base?' • ':''}Röntgen uzun eksen: ${Math.round(axis.length)} px`+
      ` • M/D: ${fmt(contacts.mesial)} / ${fmt(contacts.distal)}`+
      ` • mavi kesik: tahmini kemik sınırı`+
      ` • pembe kesik: görünür kanal izi (2D tahmin)`;
  }

  function findingColor(code){
    const s=String(code||'');
    if(/CARIES|PERIAPICAL|RADIOLUCENT|RESORPTION|FRACTURE/.test(s))return 0xff5a66;
    if(/FILLING|CROWN|BRIDGE|INLAY|POST|ROOT_CANAL/.test(s))return 0x4fd7ff;
    if(/IMPACTED|ERUPTION|THIRD_MOLAR/.test(s))return 0xffc857;
    if(/BONE|CALCULUS|LAMINA|PDL/.test(s))return 0x9b8cff;
    return 0xff7bc8;
  }

  function addFindingMarker(parent,part,tooth,assemblyCenter){
    const list=findingsFor(tooth);if(!list.length)return;
    const THREE=window.D3.THREE,c=sourceCenter(part),up=part?.axes?.up||[0,0,1];
    const g=new THREE.Group();
    const base=[c[0]-assemblyCenter[0],c[1]-assemblyCenter[1],c[2]-assemblyCenter[2]];
    for(let i=0;i<Math.min(3,list.length);i++){
      const m=new THREE.Mesh(
        new THREE.SphereGeometry(1.15+i*.20,16,12),
        new THREE.MeshStandardMaterial({color:findingColor(list[i].finding_code),emissive:findingColor(list[i].finding_code),emissiveIntensity:.22,transparent:true,opacity:.82})
      );
      m.position.set(base[0]+up[0]*(5.0+i*1.2),base[1]+up[1]*(5.0+i*1.2),base[2]+up[2]*(5.0+i*1.2));
      m.userData.tooth=tooth;g.add(m);
    }
    parent.add(g);
  }

  function buildRegisteredTooth(part,buffer,assemblyCenter,tooth,sizeScale){
    const THREE=window.D3.THREE,c=sourceCenter(part),mesh=new THREE.Mesh(
      geometryFor(part,buffer),
      new THREE.MeshPhysicalMaterial({color:0xf5f1e8,roughness:.28,metalness:0,clearcoat:.18,side:THREE.DoubleSide})
    );
    mesh.position.set(-c[0],-c[1],-c[2]);
    const wrapper=new THREE.Group();
    wrapper.position.set(c[0]-assemblyCenter[0],c[1]-assemblyCenter[1],c[2]-assemblyCenter[2]);
    wrapper.scale.setScalar(sizeScale);
    wrapper.rotation.y=-polygonAxis(tooth).tilt*.20;
    mesh.userData.tooth=tooth;wrapper.userData.tooth=tooth;wrapper.add(mesh);
    return wrapper;
  }

  renderJaw=async function(){
    await waitD3();disposeScene(jawScene);jawScene=createBase($('jaw3d'));
    const {scene,camera,controls,renderer}=jawScene,THREE=window.D3.THREE;
    const teeth=allPatientTeeth();
    if(!teeth.length)throw new Error('FDI diş tespiti yok');

    const occ=occlusionFromPanorama(teeth);result.occlusion_profile=occ;result.occlusion_label=occ.label;
    camera.position.set(0,.35,20.5);controls.target.set(0,-.15,.0);controls.minDistance=8;controls.maxDistance=30;

    const template=await loadTemplate(),jawScale=7.45/Math.max(1,template.size.x),jawOffset=new THREE.Vector3(0,-.10,.10);
    const jaw=template.boneGroup.clone(true);jaw.scale.setScalar(jawScale);jaw.position.copy(jawOffset);
    jaw.traverse(n=>{if(n.isMesh){n.material=n.material.clone();n.material.opacity=.20;n.material.depthWrite=false;}});scene.add(jaw);

    const toothLayer=new THREE.Group();toothLayer.rotation.x=-Math.PI/2;toothLayer.scale.setScalar(jawScale);toothLayer.position.copy(jawOffset);scene.add(toothLayer);
    const clickables=[], ratios=[];
    for(const t of teeth){
      const part=template.partsByFdi.get(Number(t.fdi));if(!part)continue;
      const srcLen=projectedSpan(part.bounds,part?.axes?.up||[0,0,1]),imgLen=polygonAxis(t).length;
      ratios.push(imgLen/srcLen);
    }
    const k=Math.max(1e-6,med(ratios));
    for(const t of teeth){
      const part=template.partsByFdi.get(Number(t.fdi));
      if(!part){
        console.warn('[NO_REGISTERED_SOCKET]',t.fdi);
        continue;
      }
      const srcLen=projectedSpan(part.bounds,part?.axes?.up||[0,0,1]),imgLen=polygonAxis(t).length;
      const patientScale=clamp((imgLen/srcLen)/k,.92,1.08);
      const obj=buildRegisteredTooth(part,template.buffer,template.assemblyCenter,t,patientScale);
      obj.traverse(n=>{if(n.isMesh){n.userData.tooth=t;clickables.push(n)}});toothLayer.add(obj);
      addFindingMarker(toothLayer,part,t,template.assemblyCenter);
    }

    const ray=new THREE.Raycaster(),mouse=new THREE.Vector2();
    renderer.domElement.addEventListener('pointerdown',ev=>{
      const r=renderer.domElement.getBoundingClientRect();mouse.x=((ev.clientX-r.left)/r.width)*2-1;mouse.y=-((ev.clientY-r.top)/r.height)*2+1;
      ray.setFromCamera(mouse,camera);const hit=ray.intersectObjects(clickables,false)[0];if(hit?.object?.userData?.tooth)openTooth(hit.object.userData.tooth);
    });
  };

  const previousOpenTooth=openTooth;
  openTooth=async function(t){
    await previousOpenTooth(t);
    try{drawDiagnosticCrop(t)}catch(err){console.warn('[PANO_GEOMETRY_OVERLAY]',err)}
  };

  const previousAnalyze=analyze;
  analyze=async function(){
    await previousAnalyze();if(!result)return;
    const count=(result.findings||[]).filter(f=>f&&f.finding_code).length;
    $('status').textContent=`${result.unique_fdi_count||result.tooth_count||0} diş • ${count} bulgu • ${result.occlusion_label||'temas belirsiz'}`;
  };
  $('run').onclick=analyze;
})();
