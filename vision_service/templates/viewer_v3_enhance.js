// Dental AI 3D enhancement layer: jaw/maxilla framework, occlusion-aware placement,
// root-in-bone visualization and reliable per-tooth finding attachment.
(function(){
  const OPP={11:41,12:42,13:43,14:44,15:45,16:46,17:47,18:48,21:31,22:32,23:33,24:34,25:35,26:36,27:37,28:38};
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const med=a=>{const x=a.filter(Number.isFinite).slice().sort((p,q)=>p-q);return x.length?x[Math.floor(x.length/2)]:0};
  const center=b=>[(+b[0]+ +b[2])/2,(+b[1]+ +b[3])/2];
  const validFdi=t=>/^[1-4][1-8]$/.test(String(t?.fdi||''));
  const allFindings=()=> (result?.findings||[]).filter(f=>f&&f.finding_code);

  function pointInside(box,x,y){return box&&box.length===4&&x>=box[0]&&x<=box[2]&&y>=box[1]&&y<=box[3]}
  function boxIou(a,b){
    if(!a||!b||a.length!==4||b.length!==4)return 0;
    const x1=Math.max(+a[0],+b[0]),y1=Math.max(+a[1],+b[1]),x2=Math.min(+a[2],+b[2]),y2=Math.min(+a[3],+b[3]);
    const inter=Math.max(0,x2-x1)*Math.max(0,y2-y1);
    const aa=Math.max(1,(+a[2]-+a[0])*(+a[3]-+a[1])),bb=Math.max(1,(+b[2]-+b[0])*(+b[3]-+b[1]));
    return inter/(aa+bb-inter||1);
  }

  findingsFor=function(t){
    const tf=String(t.fdi);
    return allFindings().filter(f=>{
      if(f.fdi!=null&&String(f.fdi)!=='')return String(f.fdi)===tf;
      if(!f.bbox||!t.bbox)return false;
      const [cx,cy]=center(f.bbox);
      return pointInside(t.bbox,cx,cy)||boxIou(f.bbox,t.bbox)>=0.06;
    });
  };

  function occlusionProfile(teeth){
    const by=new Map(teeth.filter(validFdi).map(t=>[Number(t.fdi),t]));
    const gaps=[],shifts=[],heights=[],pairDetails=[];
    for(const [u,l] of Object.entries(OPP)){
      const U=by.get(Number(u)),L=by.get(Number(l)); if(!U||!L)continue;
      const ub=U.bbox.map(Number),lb=L.bbox.map(Number);
      const uw=Math.max(1,ub[2]-ub[0]),lw=Math.max(1,lb[2]-lb[0]);
      const uh=Math.max(1,ub[3]-ub[1]),lh=Math.max(1,lb[3]-lb[1]);
      const gap=lb[1]-ub[3];
      const h=(uh+lh)/2;
      const gn=gap/Math.max(1,h);
      if(Math.abs(gn)<=0.65){
        gaps.push(gn);heights.push(uh,lh);
        const shift=(center(ub)[0]-center(lb)[0])/((uw+lw)/2);
        shifts.push(shift);pairDetails.push({upper:Number(u),lower:Number(l),gapNorm:gn,shift});
      }
    }
    const gapNorm=med(gaps),mesioDistal=clamp(med(shifts),-.35,.35);
    // Panoramik bite-block kaynaklı küçük radyografik aralıkları açık kapanış sayma.
    const separation=clamp(1.10+gapNorm*.22,.96,1.28);
    const overbite=gapNorm<-.10?clamp(-gapNorm,0,.65):(gapNorm>.32?-clamp(gapNorm,0,.55):0);
    return {separation,overbite,mesioDistal,gapNorm,pairs:pairDetails.length,pairDetails};
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

  function archData(teeth){
    const upperY=teeth.filter(t=>isUpper(t.fdi)).map(t=>center(t.bbox)[1]);
    const lowerY=teeth.filter(t=>!isUpper(t.fdi)).map(t=>center(t.bbox)[1]);
    const heights=teeth.map(t=>+t.bbox[3]-+t.bbox[1]);
    return {upperCy:med(upperY),lowerCy:med(lowerY),medianH:Math.max(1,med(heights))};
  }

  function archPose(t,minX,maxX,profile,ad){
    const [x1,,x2]=t.bbox.map(Number),c=(x1+x2)/2,n=(c-minX)/Math.max(1,maxX-minX),s=(n-.5)*2;
    const upper=isUpper(t.fdi),cy=center(t.bbox)[1],baseCy=upper?ad.upperCy:ad.lowerCy;
    const imageOffset=clamp((cy-baseCy)/ad.medianH,-.9,.9)*.25;
    const y=(upper?1:-1)*(profile.separation/2)-imageOffset;
    const z=-.78+2.22*(1-s*s)+(upper?-.08:.08)*profile.mesioDistal;
    const tilt=polygonTilt(t);
    return {x,y,z,rotY:-s*.60,rotZ:(upper?Math.PI:0)-tilt,upper,tilt};
  }

  function tube(scene,pts,radius,color,opacity){
    const {THREE}=window.D3;if(pts.length<2)return;
    const curve=new THREE.CatmullRomCurve3(pts),geo=new THREE.TubeGeometry(curve,112,radius,18,false);
    const mat=new THREE.MeshPhysicalMaterial({color,transparent:true,opacity,roughness:.42,transmission:.16,depthWrite:false,side:THREE.DoubleSide});
    scene.add(new THREE.Mesh(geo,mat));
  }

  function boneMaterial(opacity=.24){
    const {THREE}=window.D3;
    return new THREE.MeshPhysicalMaterial({color:0x9bb5ef,transparent:true,opacity,roughness:.46,transmission:.14,depthWrite:false,side:THREE.DoubleSide});
  }

  function addJawBone(scene,teeth,poseMap,scaleMap,profile){
    const {THREE}=window.D3;
    const upperCrest=[],lowerCrest=[],upperBase=[],lowerBody=[];
    for(let i=0;i<=48;i++){
      const s=-1+i/24,z=-.78+2.22*(1-s*s);
      upperCrest.push(new THREE.Vector3(s*3.34, profile.separation/2+.28,z));
      lowerCrest.push(new THREE.Vector3(s*3.34,-profile.separation/2-.28,z));
      upperBase.push(new THREE.Vector3(s*3.42, profile.separation/2+.92,z-.05));
      lowerBody.push(new THREE.Vector3(s*3.42,-profile.separation/2-1.00,z-.08));
    }
    // Alveolar process hugs the root halves; body/base supplies an actual jaw silhouette.
    tube(scene,upperCrest,.48,0x9bb5ef,.25);
    tube(scene,lowerCrest,.50,0x9bb5ef,.27);
    tube(scene,upperBase,.62,0x8fa9df,.16);
    tube(scene,lowerBody,.72,0x8fa9df,.23);

    for(const t of teeth){
      const p=poseMap.get(String(t.fdi)),s=scaleMap.get(String(t.fdi));if(!p||!s)continue;
      const g=new THREE.SphereGeometry(1,26,20);
      const rootDir=p.upper?1:-1;
      const socket=new THREE.Mesh(g,boneMaterial(.20));
      socket.scale.set(.34*s.x,.66*s.y,.40*s.z);
      socket.position.set(p.x,p.y+rootDir*.42*s.y,p.z);
      socket.rotation.y=p.rotY;socket.rotation.z=p.rotZ-(p.upper?Math.PI:0);
      scene.add(socket);
    }

    // Mandibular ramus and angle regions: connected to the body, not a floating face shell.
    for(const side of [-1,1]){
      tube(scene,[
        new THREE.Vector3(side*3.30,-profile.separation/2-.92,-.66),
        new THREE.Vector3(side*3.64,-1.20,-1.02),
        new THREE.Vector3(side*3.72,-.08,-1.12),
        new THREE.Vector3(side*3.54,.70,-1.06)
      ],.42,0x8fa9df,.22);
    }

    const canal=[];for(let i=0;i<=42;i++){const s=-1+i/21;canal.push(new THREE.Vector3(s*3.02,-profile.separation/2-.83,-.70+1.92*(1-s*s)))}
    tube(scene,canal,.052,0xff7898,.88);
  }

  renderJaw=async function(){
    await waitD3();disposeScene(jawScene);jawScene=createBase($('jaw3d'));
    const {scene,camera,controls,renderer}=jawScene;
    const teeth=(result?.teeth||[]).filter(t=>t?.bbox&&validFdi(t));
    if(!teeth.length)throw new Error('FDI diş tespiti yok');
    const profile=occlusionProfile(teeth);result.occlusion_profile=profile;

    // Start farther away so the whole jaw is visible on a phone screen.
    camera.position.set(0,.05,13.8);controls.target.set(0,-.05,.28);controls.minDistance=5.4;controls.maxDistance=20;

    const widths=teeth.map(t=>t.bbox[2]-t.bbox[0]),heights=teeth.map(t=>t.bbox[3]-t.bbox[1]);
    const mw=median(widths),mh=median(heights),minX=Math.min(...teeth.map(t=>t.bbox[0])),maxX=Math.max(...teeth.map(t=>t.bbox[2]));
    const ad=archData(teeth),poseMap=new Map(),scaleMap=new Map();
    for(const t of teeth){poseMap.set(String(t.fdi),archPose(t,minX,maxX,profile,ad));scaleMap.set(String(t.fdi),patientScale(t,mw,mh))}
    addJawBone(scene,teeth,poseMap,scaleMap,profile);

    const clickables=[];
    const loaded=await Promise.all(teeth.map(async t=>{try{return[t,await loadToothObject(t.fdi)]}catch(e){console.warn('anatomy',t.fdi,e);return[t,null]}}));
    for(const [t,obj] of loaded){
      if(!obj)continue;
      const p=poseMap.get(String(t.fdi)),s=scaleMap.get(String(t.fdi));
      obj.scale.set(.60*s.x,.60*s.y,.60*s.z);obj.position.set(p.x,p.y,p.z);obj.rotation.y=p.rotY;obj.rotation.z=p.rotZ;
      obj.userData.tooth=t;obj.traverse(n=>{if(n.isMesh){n.userData.tooth=t;clickables.push(n)}});scene.add(obj);
    }

    const {THREE}=window.D3,ray=new THREE.Raycaster(),mouse=new THREE.Vector2();
    renderer.domElement.addEventListener('pointerdown',ev=>{
      const r=renderer.domElement.getBoundingClientRect();mouse.x=((ev.clientX-r.left)/r.width)*2-1;mouse.y=-((ev.clientY-r.top)/r.height)*2+1;
      ray.setFromCamera(mouse,camera);const hit=ray.intersectObjects(clickables,false)[0];if(hit?.object?.userData?.tooth)openTooth(hit.object.userData.tooth);
    });
  };

  const originalAnalyze=analyze;
  analyze=async function(){
    await originalAnalyze();
    if(!result)return;
    const oc=result.occlusion_profile,fcount=(result.findings||[]).filter(f=>f&&f.finding_code).length;
    let bite='hesaplanmadı';
    if(oc){bite=oc.overbite>0.10?'örtüşme var':oc.overbite<-.30?'belirgin açıklık':'yakın temas'}
    $('status').textContent=`${result.unique_fdi_count||result.tooth_count||0} diş • ${fcount} bulgu • kapanış: ${bite}`;
  };
  $('run').onclick=analyze;
})();
