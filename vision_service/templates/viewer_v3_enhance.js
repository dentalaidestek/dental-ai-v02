// Dental AI 3D enhancement layer: occlusion-aware placement and root-in-bone jaw context.
(function(){
  const OPP={11:41,12:42,13:43,14:44,15:45,16:46,17:47,18:48,21:31,22:32,23:33,24:34,25:35,26:36,27:37,28:38};
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const validFdi=t=>/^[1-4][1-8]$/.test(String(t?.fdi ?? ''));
  const boxCenter=b=>[(Number(b[0])+Number(b[2]))/2,(Number(b[1])+Number(b[3]))/2];
  const median=arr=>{const values=arr.filter(Number.isFinite).slice().sort((a,b)=>a-b);return values.length?values[Math.floor(values.length/2)]:0};
  const allFindings=()=>Array.isArray(result?.findings)?result.findings.filter(f=>f?.finding_code):[];

  function pointInside(box,px,py){
    return Array.isArray(box)&&box.length===4&&px>=Number(box[0])&&px<=Number(box[2])&&py>=Number(box[1])&&py<=Number(box[3]);
  }

  function boxIou(a,b){
    if(!Array.isArray(a)||!Array.isArray(b)||a.length!==4||b.length!==4)return 0;
    const ax1=Number(a[0]),ay1=Number(a[1]),ax2=Number(a[2]),ay2=Number(a[3]);
    const bx1=Number(b[0]),by1=Number(b[1]),bx2=Number(b[2]),by2=Number(b[3]);
    const ix1=Math.max(ax1,bx1),iy1=Math.max(ay1,by1),ix2=Math.min(ax2,bx2),iy2=Math.min(ay2,by2);
    const inter=Math.max(0,ix2-ix1)*Math.max(0,iy2-iy1);
    const areaA=Math.max(1,(ax2-ax1)*(ay2-ay1));
    const areaB=Math.max(1,(bx2-bx1)*(by2-by1));
    return inter/Math.max(1,areaA+areaB-inter);
  }

  findingsFor=function(tooth){
    const fdi=String(tooth.fdi);
    return allFindings().filter(finding=>{
      if(finding.fdi!==undefined&&finding.fdi!==null&&String(finding.fdi)!=='')return String(finding.fdi)===fdi;
      if(!finding.bbox||!tooth.bbox)return false;
      const c=boxCenter(finding.bbox);
      return pointInside(tooth.bbox,c[0],c[1])||boxIou(finding.bbox,tooth.bbox)>=0.06;
    });
  };

  function occlusionProfile(teeth){
    const byFdi=new Map(teeth.filter(validFdi).map(t=>[Number(t.fdi),t]));
    const gapNorms=[],shifts=[],details=[];
    for(const pair of Object.entries(OPP)){
      const upper=byFdi.get(Number(pair[0]));
      const lower=byFdi.get(Number(pair[1]));
      if(!upper||!lower)continue;
      const ub=upper.bbox.map(Number),lb=lower.bbox.map(Number);
      const upperW=Math.max(1,ub[2]-ub[0]),lowerW=Math.max(1,lb[2]-lb[0]);
      const upperH=Math.max(1,ub[3]-ub[1]),lowerH=Math.max(1,lb[3]-lb[1]);
      const gap=lb[1]-ub[3];
      const gapNorm=gap/Math.max(1,(upperH+lowerH)/2);
      if(Math.abs(gapNorm)>0.65)continue;
      const uc=boxCenter(ub),lc=boxCenter(lb);
      const shift=(uc[0]-lc[0])/Math.max(1,(upperW+lowerW)/2);
      gapNorms.push(gapNorm);shifts.push(shift);details.push({upper:Number(pair[0]),lower:Number(pair[1]),gapNorm,shift});
    }
    const gapNorm=median(gapNorms);
    const mesioDistal=clamp(median(shifts),-0.35,0.35);
    const separation=clamp(1.08+gapNorm*0.18,0.94,1.24);
    let overbite=0;
    if(gapNorm<-.10)overbite=clamp(-gapNorm,0,.65);
    else if(gapNorm>.34)overbite=-clamp(gapNorm,0,.55);
    return {separation,overbite,mesioDistal,gapNorm,pairs:details.length,pairDetails:details};
  }

  function polygonTilt(tooth){
    const poly=tooth?.polygon;
    if(!Array.isArray(poly)||poly.length<6)return 0;
    let meanX=0,meanY=0;
    for(const pt of poly){meanX+=Number(pt[0]);meanY+=Number(pt[1]);}
    meanX/=poly.length;meanY/=poly.length;
    let xx=0,yy=0,xy=0;
    for(const pt of poly){
      const dx=Number(pt[0])-meanX,dy=Number(pt[1])-meanY;
      xx+=dx*dx;yy+=dy*dy;xy+=dx*dy;
    }
    const trace=xx+yy;
    const determinant=xx*yy-xy*xy;
    const disc=Math.sqrt(Math.max(0,trace*trace/4-determinant));
    const lambda=trace/2+disc;
    let vx=xy,vy=lambda-xx;
    if(Math.abs(vx)+Math.abs(vy)<1e-8){vx=0;vy=1;}
    const len=Math.hypot(vx,vy)||1;
    vx/=len;vy/=len;
    if(vy<0){vx=-vx;vy=-vy;}
    return clamp(Math.atan2(vx,vy),-.55,.55);
  }

  function archStats(teeth){
    const upperCenters=[],lowerCenters=[],heights=[];
    for(const tooth of teeth){
      const c=boxCenter(tooth.bbox);
      (isUpper(tooth.fdi)?upperCenters:lowerCenters).push(c[1]);
      heights.push(Number(tooth.bbox[3])-Number(tooth.bbox[1]));
    }
    return {upperCy:median(upperCenters),lowerCy:median(lowerCenters),medianH:Math.max(1,median(heights))};
  }

  function toothPose(tooth,minX,maxX,profile,stats){
    const b=tooth.bbox.map(Number);
    const centerX=(b[0]+b[2])/2;
    const n=(centerX-minX)/Math.max(1,maxX-minX);
    const side=(n-.5)*2;
    const upper=isUpper(tooth.fdi);
    const cy=(b[1]+b[3])/2;
    const baseCy=upper?stats.upperCy:stats.lowerCy;
    const imageOffset=clamp((cy-baseCy)/stats.medianH,-.8,.8)*.20;
    const posY=(upper?1:-1)*(profile.separation/2)-imageOffset;
    const posZ=-.78+2.18*(1-side*side)+(upper?-.08:.08)*profile.mesioDistal;
    const tilt=polygonTilt(tooth);
    return {x:side*3.15,y:posY,z:posZ,rotY:-side*.60,rotZ:(upper?Math.PI:0)-tilt,upper};
  }

  function tube(scene,points,radius,color,opacity){
    if(points.length<2)return;
    const THREE=window.D3.THREE;
    const curve=new THREE.CatmullRomCurve3(points);
    const geometry=new THREE.TubeGeometry(curve,112,radius,18,false);
    const material=new THREE.MeshPhysicalMaterial({color,transparent:true,opacity,roughness:.42,transmission:.12,depthWrite:false,side:THREE.DoubleSide});
    scene.add(new THREE.Mesh(geometry,material));
  }

  function boneMaterial(opacity){
    const THREE=window.D3.THREE;
    return new THREE.MeshPhysicalMaterial({color:0x9bb5ef,transparent:true,opacity,roughness:.46,transmission:.12,depthWrite:false,side:THREE.DoubleSide});
  }

  function addJawBone(scene,teeth,poseMap,scaleMap,profile){
    const THREE=window.D3.THREE;
    const upperCrest=[],lowerCrest=[],upperBase=[],lowerBody=[];
    for(let i=0;i<=48;i++){
      const side=-1+i/24;
      const z=-.78+2.18*(1-side*side);
      upperCrest.push(new THREE.Vector3(side*3.34,profile.separation/2+.24,z));
      lowerCrest.push(new THREE.Vector3(side*3.34,-profile.separation/2-.24,z));
      upperBase.push(new THREE.Vector3(side*3.42,profile.separation/2+.82,z-.05));
      lowerBody.push(new THREE.Vector3(side*3.44,-profile.separation/2-.94,z-.08));
    }
    tube(scene,upperCrest,.46,0x9bb5ef,.24);
    tube(scene,lowerCrest,.48,0x9bb5ef,.26);
    tube(scene,upperBase,.60,0x8fa9df,.16);
    tube(scene,lowerBody,.72,0x8fa9df,.23);

    for(const tooth of teeth){
      const pose=poseMap.get(String(tooth.fdi));
      const scale=scaleMap.get(String(tooth.fdi));
      if(!pose||!scale)continue;
      const socket=new THREE.Mesh(new THREE.SphereGeometry(1,26,20),boneMaterial(.20));
      const rootDirection=pose.upper?1:-1;
      socket.scale.set(.34*scale.x,.62*scale.y,.40*scale.z);
      socket.position.set(pose.x,pose.y+rootDirection*.46*scale.y,pose.z);
      socket.rotation.y=pose.rotY;
      socket.rotation.z=pose.rotZ-(pose.upper?Math.PI:0);
      scene.add(socket);
    }

    for(const side of [-1,1]){
      const ramus=[
        new THREE.Vector3(side*3.30,-profile.separation/2-.90,-.66),
        new THREE.Vector3(side*3.62,-1.18,-1.00),
        new THREE.Vector3(side*3.70,-.08,-1.10),
        new THREE.Vector3(side*3.54,.68,-1.04)
      ];
      tube(scene,ramus,.42,0x8fa9df,.22);
    }

    const canal=[];
    for(let i=0;i<=42;i++){
      const side=-1+i/21;
      canal.push(new THREE.Vector3(side*3.02,-profile.separation/2-.80,-.70+1.90*(1-side*side)));
    }
    tube(scene,canal,.052,0xff7898,.88);
  }

  renderJaw=async function(){
    await waitD3();
    disposeScene(jawScene);
    jawScene=createBase($('jaw3d'));
    const scene=jawScene.scene,camera=jawScene.camera,controls=jawScene.controls,renderer=jawScene.renderer;
    const teeth=(result?.teeth||[]).filter(tooth=>tooth?.bbox&&validFdi(tooth));
    if(!teeth.length)throw new Error('FDI diş tespiti yok');

    const profile=occlusionProfile(teeth);
    result.occlusion_profile=profile;
    camera.position.set(0,.02,15.2);
    controls.target.set(0,-.05,.22);
    controls.minDistance=5.6;
    controls.maxDistance=22;

    const widths=teeth.map(t=>Number(t.bbox[2])-Number(t.bbox[0]));
    const heights=teeth.map(t=>Number(t.bbox[3])-Number(t.bbox[1]));
    const medianW=Math.max(1,median(widths)),medianH=Math.max(1,median(heights));
    const minX=Math.min(...teeth.map(t=>Number(t.bbox[0])));
    const maxX=Math.max(...teeth.map(t=>Number(t.bbox[2])));
    const stats=archStats(teeth);
    const poseMap=new Map(),scaleMap=new Map();
    for(const tooth of teeth){
      poseMap.set(String(tooth.fdi),toothPose(tooth,minX,maxX,profile,stats));
      scaleMap.set(String(tooth.fdi),patientScale(tooth,medianW,medianH));
    }

    addJawBone(scene,teeth,poseMap,scaleMap,profile);

    const clickables=[];
    const loaded=await Promise.all(teeth.map(async tooth=>{
      try{return [tooth,await loadToothObject(tooth.fdi)];}
      catch(err){console.warn('anatomy',tooth.fdi,err);return [tooth,null];}
    }));
    for(const pair of loaded){
      const tooth=pair[0],obj=pair[1];
      if(!obj)continue;
      const pose=poseMap.get(String(tooth.fdi)),scale=scaleMap.get(String(tooth.fdi));
      obj.scale.set(.58*scale.x,.58*scale.y,.58*scale.z);
      obj.position.set(pose.x,pose.y,pose.z);
      obj.rotation.y=pose.rotY;
      obj.rotation.z=pose.rotZ;
      obj.userData.tooth=tooth;
      obj.traverse(node=>{if(node.isMesh){node.userData.tooth=tooth;clickables.push(node);}});
      scene.add(obj);
    }

    const THREE=window.D3.THREE;
    const raycaster=new THREE.Raycaster(),mouse=new THREE.Vector2();
    renderer.domElement.addEventListener('pointerdown',event=>{
      const rect=renderer.domElement.getBoundingClientRect();
      mouse.x=((event.clientX-rect.left)/rect.width)*2-1;
      mouse.y=-((event.clientY-rect.top)/rect.height)*2+1;
      raycaster.setFromCamera(mouse,camera);
      const hit=raycaster.intersectObjects(clickables,false)[0];
      if(hit?.object?.userData?.tooth)openTooth(hit.object.userData.tooth);
    });
  };

  const baseAnalyze=analyze;
  analyze=async function(){
    await baseAnalyze();
    if(!result)return;
    const oc=result.occlusion_profile;
    const findingCount=allFindings().length;
    let bite='hesaplanmadı';
    if(oc){
      if(oc.overbite>0.10)bite='örtüşme var';
      else if(oc.overbite<-.30)bite='belirgin açıklık';
      else bite='yakın temas';
    }
    $('status').textContent=`${result.unique_fdi_count||result.tooth_count||0} diş • ${findingCount} bulgu • kapanış: ${bite}`;
  };
  $('run').onclick=analyze;
})();
