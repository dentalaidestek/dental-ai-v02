// Dental AI 3D enhancement layer: jaw/maxilla framework, occlusion-aware placement,
// face/skull context and reliable per-tooth finding attachment.
(function(){
  const OPP = {11:41,12:42,13:43,14:44,15:45,16:46,17:47,18:48,21:31,22:32,23:33,24:34,25:35,26:36,27:37,28:38};
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

  // Do not hide a valid finding merely because it is derived rather than direct.
  // Prefer explicit FDI; otherwise spatially attach it to the tooth it overlaps.
  findingsFor = function(t){
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
    const gaps=[], shifts=[], widths=[], heights=[], pairDetails=[];
    for(const [u,l] of Object.entries(OPP)){
      const U=by.get(Number(u)),L=by.get(Number(l)); if(!U||!L)continue;
      const ub=U.bbox.map(Number),lb=L.bbox.map(Number);
      const gap=lb[1]-ub[3]; // lower crown top minus upper crown bottom in panorama pixels
      const uw=Math.max(1,ub[2]-ub[0]),lw=Math.max(1,lb[2]-lb[0]);
      const uh=Math.max(1,ub[3]-ub[1]),lh=Math.max(1,lb[3]-lb[1]);
      const shift=(center(ub)[0]-center(lb)[0])/((uw+lw)/2);
      gaps.push(gap); shifts.push(shift); widths.push(uw,lw); heights.push(uh,lh);
      pairDetails.push({upper:Number(u),lower:Number(l),gap,shift});
    }
    const h=Math.max(1,med(heights)||1), gapPx=med(gaps), gapNorm=gapPx/h;
    // Negative panorama gap = visible crown overlap/deeper bite; positive = more separation.
    const separation=clamp(1.30+gapNorm*0.70,0.94,1.62);
    const overbite=clamp(-gapNorm,-0.35,0.75);
    const mesioDistal=clamp(med(shifts),-0.45,0.45);
    return {separation,overbite,mesioDistal,gapPx,pairs:pairDetails.length,pairDetails};
  }

  function archPose(t,minX,maxX,profile){
    const [x1,,x2]=t.bbox.map(Number),c=(x1+x2)/2,n=(c-minX)/Math.max(1,maxX-minX),s=(n-.5)*2;
    const upper=isUpper(t.fdi);
    const y=(upper?1:-1)*(profile.separation/2);
    // Small sagittal offset from visible upper/lower mesiodistal relation; never pretend it is true CBCT depth.
    const z=-.72+2.18*(1-s*s)+(upper?-.10: .10)*profile.mesioDistal;
    return {x:s*3.15,y,z,rotY:-s*.62,upper};
  }

  function tube(scene,pts,radius,color,opacity){
    const {THREE}=window.D3;if(pts.length<2)return;
    const curve=new THREE.CatmullRomCurve3(pts),geo=new THREE.TubeGeometry(curve,96,radius,14,false);
    const mat=new THREE.MeshPhysicalMaterial({color,transparent:true,opacity,roughness:.24,transmission:.28,depthWrite:false,side:THREE.DoubleSide});
    scene.add(new THREE.Mesh(geo,mat));
  }

  function addJawFramework(scene,profile){
    const {THREE}=window.D3, up=[],low=[];
    for(let i=0;i<=44;i++){
      const s=-1+i/22,z=-.72+2.18*(1-s*s);
      up.push(new THREE.Vector3(s*3.32, profile.separation/2+.38,z));
      low.push(new THREE.Vector3(s*3.30,-profile.separation/2-.48,z-.04));
    }
    // Alveolar maxilla and mandibular body follow the patient's tooth arch rather than a floating generic ring.
    tube(scene,up,.42,0x8ba9ff,.18);
    tube(scene,low,.50,0x8ba9ff,.20);

    // Mandibular rami / angle regions.
    for(const side of [-1,1]){
      tube(scene,[
        new THREE.Vector3(side*3.22,-profile.separation/2-.52,-.62),
        new THREE.Vector3(side*3.55,-.35,-.95),
        new THREE.Vector3(side*3.48,.72,-1.08)
      ],.33,0x8ba9ff,.18);
      // Zygomatic/maxillary side frame.
      tube(scene,[
        new THREE.Vector3(side*2.45,profile.separation/2+.45,.20),
        new THREE.Vector3(side*3.18,1.45,-.18),
        new THREE.Vector3(side*3.38,1.92,-.82)
      ],.18,0x8ba9ff,.12);
    }

    // Maxillary sinus cavities as subtle translucent anatomical context.
    for(const side of [-1,1]){
      const g=new THREE.SphereGeometry(1,28,20);g.scale(1.12,.82,.72);
      const m=new THREE.MeshPhysicalMaterial({color:0x86a6ff,transparent:true,opacity:.055,roughness:.1,transmission:.55,depthWrite:false,side:THREE.DoubleSide});
      const o=new THREE.Mesh(g,m);o.position.set(side*1.72,1.55,.12);scene.add(o);
    }

    // Mandibular canal is illustrative context only; patient-specific canal path still comes from image/CBCT data when available.
    const canal=[];for(let i=0;i<=40;i++){const s=-1+i/20;canal.push(new THREE.Vector3(s*3.00,-profile.separation/2-.54,-.68+1.92*(1-s*s)))}
    tube(scene,canal,.055,0xff6d8b,.86);
  }

  function addFaceSkullEnvelope(scene){
    const {THREE}=window.D3;
    const skull=new THREE.Mesh(
      new THREE.SphereGeometry(1,42,32),
      new THREE.MeshBasicMaterial({color:0x9bb7ff,transparent:true,opacity:.035,wireframe:true,depthWrite:false})
    );
    skull.scale.set(3.72,4.38,2.50);skull.position.set(0,.55,.10);scene.add(skull);
    // Chin/lower facial contour gives the subtle outer-human silhouette seen in the reference without claiming patient-specific soft tissue.
    const chin=new THREE.Mesh(
      new THREE.SphereGeometry(1,32,22),
      new THREE.MeshBasicMaterial({color:0x7899e8,transparent:true,opacity:.025,wireframe:true,depthWrite:false})
    );
    chin.scale.set(2.62,2.35,1.85);chin.position.set(0,-2.25,.18);scene.add(chin);
  }

  const originalRenderJaw=renderJaw;
  renderJaw=async function(){
    await waitD3();disposeScene(jawScene);jawScene=createBase($('jaw3d'));
    const {scene,camera,controls,renderer}=jawScene;
    const teeth=(result?.teeth||[]).filter(t=>t?.bbox&&validFdi(t));
    if(!teeth.length)throw new Error('FDI diş tespiti yok');
    const profile=occlusionProfile(teeth);result.occlusion_profile=profile;

    // Wider initial framing: show the jaw/skull context first, user can pinch to enter a single region.
    camera.position.set(0,.15,10.6);controls.target.set(0,.05,.35);controls.minDistance=3.4;controls.maxDistance=16;
    addFaceSkullEnvelope(scene);addJawFramework(scene,profile);

    const widths=teeth.map(t=>t.bbox[2]-t.bbox[0]),heights=teeth.map(t=>t.bbox[3]-t.bbox[1]);
    const mw=median(widths),mh=median(heights),minX=Math.min(...teeth.map(t=>t.bbox[0])),maxX=Math.max(...teeth.map(t=>t.bbox[2]));
    const clickables=[];
    const loaded=await Promise.all(teeth.map(async t=>{try{return[t,await loadToothObject(t.fdi)]}catch(e){console.warn('anatomy',t.fdi,e);return[t,null]}}));
    for(const [t,obj] of loaded){
      if(!obj)continue;
      const p=archPose(t,minX,maxX,profile),s=patientScale(t,mw,mh);
      obj.scale.set(.62*s.x,.62*s.y,.62*s.z);obj.position.set(p.x,p.y,p.z);obj.rotation.y=p.rotY;if(p.upper)obj.rotation.z=Math.PI;
      obj.userData.tooth=t;obj.traverse(n=>{if(n.isMesh){n.userData.tooth=t;clickables.push(n)}});scene.add(obj);
    }
    const {THREE}=window.D3,ray=new THREE.Raycaster(),mouse=new THREE.Vector2();
    renderer.domElement.addEventListener('pointerdown',ev=>{
      const r=renderer.domElement.getBoundingClientRect();mouse.x=((ev.clientX-r.left)/r.width)*2-1;mouse.y=-((ev.clientY-r.top)/r.height)*2+1;
      ray.setFromCamera(mouse,camera);const hit=ray.intersectObjects(clickables,false)[0];if(hit?.object?.userData?.tooth)openTooth(hit.object.userData.tooth);
    });
  };

  // Refresh the status after the original analyze finishes so finding count and the visible 2D occlusal relation are not hidden.
  const originalAnalyze=analyze;
  analyze=async function(){
    await originalAnalyze();
    if(!result)return;
    const oc=result.occlusion_profile;
    const fcount=(result.findings||[]).filter(f=>f&&f.finding_code).length;
    const bite=oc?(oc.overbite>0.12?'örtüşme var':oc.overbite<-.08?'açıklık var':'yakın temas'):'hesaplanmadı';
    $('status').textContent=`${result.unique_fdi_count||result.tooth_count||0} diş • ${fcount} bulgu • kapanış: ${bite}`;
  };
  $('run').onclick=analyze;
})();
