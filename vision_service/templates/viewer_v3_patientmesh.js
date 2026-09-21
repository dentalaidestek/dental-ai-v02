// Patient-coordinate panoramic 3D rebuild.
// No atlas jaw, no spheres/capsules/tube stand-ins for bone.
// x/z come from the panorama; y is only a conservative anatomical depth prior.
(function(){
  const valid=v=>/^[1-4][1-8]$/.test(String(v??''));
  const upper=v=>['1','2'].includes(String(v)[0]);
  const med=a=>{const v=a.filter(Number.isFinite).sort((a,b)=>a-b);return v.length?v[Math.floor(v.length/2)]:1};
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  function pts(poly){if(!Array.isArray(poly))return[];let p=poly;if(p.length===1&&Array.isArray(p[0]))p=p[0];if(p.length&&typeof p[0]==='number'){const q=[];for(let i=0;i+1<p.length;i+=2)q.push([+p[i],+p[i+1]]);return q}return p.filter(q=>Array.isArray(q)&&q.length>=2).map(q=>[+q[0],+q[1]])}
  function axis(t){const p=pts(t.polygon);const b=t.bbox.map(Number),cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2;if(p.length<5)return{cx,cy,tilt:0,h:b[3]-b[1],w:b[2]-b[0]};let mx=0,my=0;for(const q of p){mx+=q[0];my+=q[1]}mx/=p.length;my/=p.length;let xx=0,yy=0,xy=0;for(const q of p){const x=q[0]-mx,y=q[1]-my;xx+=x*x;yy+=y*y;xy+=x*y}const a=.5*Math.atan2(2*xy,xx-yy),candidates=[a,a+Math.PI/2],best=candidates.reduce((u,v)=>Math.abs(Math.cos(v))<Math.abs(Math.cos(u))?v:u);return{cx:mx,cy:my,tilt:clamp(Math.PI/2-best,-1.25,1.25),h:Math.max(1,b[3]-b[1]),w:Math.max(1,b[2]-b[0])}}
  function contourSet(){const c=result?.anatomy_contours||{};return {mandible:c.mandible||c.mandibular_bone||c.mandible_outer||null,maxilla:c.maxilla||c.maxillary_bone||c.maxilla_outer||null,sinuses:c.maxillary_sinuses||c.sinuses||null}}
  function contourMesh(raw,stats,isUpper){
    const THREE=window.D3.THREE,p=pts(raw);if(p.length<3)return null;
    const shape=new THREE.Shape(),map=q=>new THREE.Vector2((q[0]-stats.cx)*stats.k,(stats.cy-q[1])*stats.k);
    const first=map(p[0]);shape.moveTo(first.x,first.y);for(const q of p.slice(1)){const v=map(q);shape.lineTo(v.x,v.y)}shape.closePath();
    const depth=stats.depth,geo=new THREE.ExtrudeGeometry(shape,{depth,steps:1,bevelEnabled:true,bevelSegments:3,bevelSize:depth*.045,bevelThickness:depth*.04});
    geo.translate(0,0,-depth/2);geo.rotateX(Math.PI/2);
    const mat=new THREE.MeshPhysicalMaterial({color:0xb8d7ee,transparent:true,opacity:.20,roughness:.38,metalness:0,transmission:.16,depthWrite:false,side:THREE.DoubleSide});
    const m=new THREE.Mesh(geo,mat);m.userData.layer='bone';m.userData.patientContour=true;m.userData.arch=isUpper?'upper':'lower';return m;
  }
  function toothFromPolygon(t,stats){
    const THREE=window.D3.THREE,a=axis(t),p=pts(t.polygon),w=Math.max(a.w*stats.k,.16),h=Math.max(a.h*stats.k,.34),depth=clamp(w*.78,.13,.42);
    // Silhouette is patient-derived. A shallow extrusion gives display depth
    // without claiming a CBCT root/crown surface.
    let shape=new THREE.Shape();
    if(p.length>=5){const q=p.map(v=>[(v[0]-a.cx)*stats.k,(a.cy-v[1])*stats.k]);shape.moveTo(q[0][0],q[0][1]);for(const v of q.slice(1))shape.lineTo(v[0],v[1]);shape.closePath()}
    else{shape.ellipse(0,0,w*.46,h*.50,0,Math.PI*2,false,0)}
    const geo=new THREE.ExtrudeGeometry(shape,{depth,steps:1,bevelEnabled:true,bevelSegments:3,bevelSize:Math.min(w,h)*.035,bevelThickness:Math.min(w,h)*.03});geo.translate(0,0,-depth/2);geo.rotateX(Math.PI/2);
    const mat=new THREE.MeshPhysicalMaterial({color:0xf5f2ea,roughness:.27,metalness:0,clearcoat:.18,side:THREE.DoubleSide}),mesh=new THREE.Mesh(geo,mat),g=new THREE.Group();
    g.position.set((a.cx-stats.cx)*stats.k,0,(stats.cy-a.cy)*stats.k);
    // Arch depth is inferred only; panorama controls x/z exactly.
    const nx=clamp((a.cx-stats.minX)/Math.max(1,stats.maxX-stats.minX),0,1),side=(nx-.5)*2;
    g.position.y=(side*side)*stats.depth*.28-(stats.depth*.20);
    g.rotation.y=a.tilt;g.userData.tooth=t;mesh.userData.tooth=t;g.add(mesh);return{g,mesh};
  }
  function fit(ctx,obj){const THREE=window.D3.THREE;obj.updateMatrixWorld(true);const b=new THREE.Box3().setFromObject(obj),c=b.getCenter(new THREE.Vector3()),s=b.getSize(new THREE.Vector3()),r=Math.max(.4,Math.hypot(s.x,s.y,s.z)/2),f=ctx.camera.fov*Math.PI/180,d=r/Math.sin(f/2)*1.18;ctx.controls.target.copy(c);ctx.camera.position.set(c.x+r*.32,c.y+r*.10,c.z+d);ctx.camera.near=.01;ctx.camera.far=d+r*5;ctx.camera.updateProjectionMatrix();ctx.controls.update()}
  window.renderPatientPanoramicMesh=async function(){
    await waitD3();disposeScene(jawScene);jawScene=createBase($('jaw3d'));const THREE=window.D3.THREE,root=new THREE.Group();jawScene.scene.add(root);
    const teeth=(result?.teeth||[]).filter(t=>t?.bbox&&valid(t.fdi));if(!teeth.length)throw new Error('FDI diş tespiti yok');
    const centers=teeth.map(t=>axis(t)),minX=Math.min(...centers.map(a=>a.cx)),maxX=Math.max(...centers.map(a=>a.cx)),minY=Math.min(...centers.map(a=>a.cy-a.h/2)),maxY=Math.max(...centers.map(a=>a.cy+a.h/2)),cx=(minX+maxX)/2,cy=(minY+maxY)/2,k=7.2/Math.max(1,maxX-minX),mw=med(centers.map(a=>a.w))*k,stats={minX,maxX,minY,maxY,cx,cy,k,depth:Math.max(.55,mw*3.0)};
    const click=[];window.jawToothMap=new Map();for(const t of teeth){const o=toothFromPolygon(t,stats);root.add(o.g);click.push(o.mesh);window.jawToothMap.set(String(t.fdi),{mesh:o.mesh,wrapper:o.g,tooth:t})}
    const c=contourSet();let boneN=0;for(const [raw,isUp] of [[c.maxilla,true],[c.mandible,false]]){if(Array.isArray(raw)&&Array.isArray(raw[0])&&Array.isArray(raw[0][0])){for(const x of raw){const m=contourMesh(x,stats,isUp);if(m){root.add(m);boneN++}}}else{const m=contourMesh(raw,stats,isUp);if(m){root.add(m);boneN++}}}
    // Render sinus only from a real image-derived contour; never synthesize it.
    const sinusRaw=c.sinuses;let sinusN=0;if(sinusRaw){const list=(Array.isArray(sinusRaw)&&Array.isArray(sinusRaw[0])&&Array.isArray(sinusRaw[0][0]))?sinusRaw:[sinusRaw];for(const raw of list){const m=contourMesh(raw,stats,true);if(!m)continue;m.material=m.material.clone();m.material.opacity=.08;m.material.depthWrite=false;m.userData.layer='sinus_boundary';root.add(m);sinusN++}}
    result.anatomy3d={mode:'panoramic_patient_mesh',rendered_teeth:teeth.length,patient_specific_depth:false,bone_contours_rendered:boneN,sinus_contours_rendered:sinusN,atlas_used:false,primitive_jaw_used:false};
    fit(jawScene,root);
    const ray=new THREE.Raycaster(),mouse=new THREE.Vector2(),canvas=jawScene.renderer.domElement;canvas.addEventListener('pointerdown',ev=>{const r=canvas.getBoundingClientRect();mouse.x=((ev.clientX-r.left)/r.width)*2-1;mouse.y=-((ev.clientY-r.top)/r.height)*2+1;ray.setFromCamera(mouse,jawScene.camera);const h=ray.intersectObjects(click,false)[0];if(h?.object?.userData?.tooth)openTooth(h.object.userData.tooth)});
    return result.anatomy3d;
  };
})();