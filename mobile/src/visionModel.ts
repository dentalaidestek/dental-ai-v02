export type VisionFinding={id:string;label:string;tooth:string;surface:string;description:string;category:string;confidence:number|null;attention:boolean;box:number[]|null};
const commonPools=['findings','auxiliary_radiographic_findings','image_level_findings'];
const radiographicModalities=new Set(['PANORAMIC','BITEWING','PERIAPICAL']);

function box(raw:any){
 const value=raw.bbox||raw.region||raw.localization?.bbox;
 if(!Array.isArray(value)||value.length!==4||value.some((n:unknown)=>typeof n!=='number'||!Number.isFinite(n))||value[2]<=value[0]||value[3]<=value[1])return null;
 return value as number[];
}
function safeText(value:unknown,maximum:number){
 return typeof value==='string'?value.trim().slice(0,maximum):'';
}

export function visionFindings(snapshot:any,modality:string=''):VisionFinding[]{
 const data=snapshot?.result||snapshot,seen=new Set<string>(),out:VisionFinding[]=[];
 const key=String(modality||'').toUpperCase();
 const pools=radiographicModalities.has(key)?[...commonPools,'gradcam_attention']:commonPools;
 for(const pool of pools){
  const list=data?.[pool];
  if(!Array.isArray(list))continue;
  for(const f of list){
   if(!f||typeof f!=='object')continue;
   const value=f.confidence??f.score,n=value==null?null:Number(value);
   const confidence=n===null?null:Number.isFinite(n)&&n>=0&&n<=100?(n>1?n/100:n):NaN;
   if(Number.isNaN(confidence)||confidence!==null&&confidence<.5&&!f.fusion_supported)continue;
   const code=safeText(f.finding_code||f.code||f.label,120);
   const label=safeText(f.label||f.finding_code||f.code||'Bulgu',120)||'Bulgu';
   const rawTooth=safeText(f.fdi||f.tooth_id||f.tooth,8);
   const tooth=/^(?:[1-4][1-8]|[5-8][1-5])$/.test(rawTooth)?rawTooth:'';
   const surface=safeText(f.surface,80);
   const b=box(f);
   const attention=String(f.localization_type||(pool==='gradcam_attention'?'gradcam':'')).includes('gradcam');
   const id=JSON.stringify([code,tooth,confidence,b]);
   if(seen.has(id))continue;
   seen.add(id);
   const suppliedDescription=safeText(f.description||f.explanation||f.note,4000);
   const description=suppliedDescription||(attention
    ?'Bu görüntüde işaretlenen dikkat bölgesi. Bu işaret doğrulanmış lezyon sınırı değildir.'
    :`${label}${tooth?' '+tooth+' numaralı diş ile ilişkilendirilmiştir.':''}${surface?' İlgili yüzey: '+surface+'.':''}`);
   const upper=code.toUpperCase();
   const category=upper.includes('CARIES')?'Çürük':upper.includes('GING')?'Diş eti':upper.includes('CALCUL')?'Diş taşı':upper.includes('PLAQUE')?'Plak':'Diğer';
   out.push({id,label,tooth,surface,description,category,confidence,attention,box:b});
  }
 }
 return out;
}

export function visionBox(finding:VisionFinding,width:number,height:number){
 if(!finding.box||!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)return null;
 let[x1,y1,x2,y2]=finding.box;
 if(Math.max(x1,y1,x2,y2)<=1){x1*=width;x2*=width;y1*=height;y2*=height}
 x1=Math.max(0,Math.min(width,x1));x2=Math.max(0,Math.min(width,x2));
 y1=Math.max(0,Math.min(height,y1));y2=Math.max(0,Math.min(height,y2));
 return x2>x1&&y2>y1?{x:x1,y:y1,width:x2-x1,height:y2-y1}:null;
}
