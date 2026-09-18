from __future__ import annotations
import csv, hashlib, json, os, shutil, time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

ROOT=Path(os.getenv("DENTALAI_BASELINE_ROOT","/kaggle/working/dentalai_baseline"))
POOL=ROOT/"TEST_LOCKED"; STATE=ROOT/"state"; REPORTS=ROOT/"reports"; RAW=ROOT/"raw"
for p in (POOL,STATE,REPORTS,RAW): p.mkdir(parents=True,exist_ok=True)
TARGET_POS=int(os.getenv("DENTALAI_TEST_POS","15")); TARGET_NEG=int(os.getenv("DENTALAI_TEST_NEG","15"))

@dataclass
class Case:
    case_id:str; modality:str; finding_code:str; polarity:str; image_path:str
    source:str; source_id:str=""; patient_id:str=""; annotation:dict|None=None
    sha256:str=""

def sha256_file(path:str|Path)->str:
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def atomic_json(path:Path,obj:Any):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(tmp,path)

def load_json(path:Path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default

def case_key(c:Case)->str:return f"{c.modality}:{c.finding_code}:{c.polarity}:{c.case_id}"

def _image_ok(path:Path)->bool:
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False

def lock_cases(cases:list[Case])->list[Case]:
    """Copy immutable holdout images, hash them, reject leakage/duplicates."""
    seen_hash:dict[str,str]={}; seen_patient:dict[str,str]={}; out=[]
    for c in cases:
        src=Path(c.image_path)
        if not src.is_file() or not _image_ok(src): continue
        digest=sha256_file(src)
        duplicate_key=f"{c.modality}:{c.finding_code}:{c.polarity}:{digest}"
        if duplicate_key in seen_hash: continue
        # A patient may not contribute to opposite polarity for the same target.
        pk=f"{c.modality}:{c.finding_code}:{c.patient_id}" if c.patient_id else ""
        if pk and pk in seen_patient and seen_patient[pk]!=c.polarity: continue
        dst_dir=POOL/c.modality/c.finding_code/c.polarity
        dst_dir.mkdir(parents=True,exist_ok=True)
        dst=dst_dir/f"{digest[:16]}{src.suffix.lower()}"
        if not dst.exists(): shutil.copy2(src,dst)
        c.image_path=str(dst); c.sha256=digest
        seen_hash[duplicate_key]=case_key(c)
        if pk: seen_patient[pk]=c.polarity
        out.append(c)
    return out

def _patient_unique(cases:list[Case])->list[Case]:
    seen=set(); out=[]
    for c in cases:
        key=(c.source,c.patient_id) if c.patient_id else (c.source,c.source_id or c.case_id)
        if key in seen: continue
        seen.add(key); out.append(c)
    return out

def balanced_select(cases:list[Case], seed:int=42)->tuple[list[Case],str]:
    import random
    pos=[c for c in cases if c.polarity=="positive"]; neg=[c for c in cases if c.polarity=="negative"]
    # Deterministic pseudo-random holdout: reproducible, but not dataset-order/cherry-pick biased.
    rng=random.Random(seed)
    pos=sorted(pos,key=lambda c:(c.source,c.source_id,c.case_id)); neg=sorted(neg,key=lambda c:(c.source,c.source_id,c.case_id))
    rng.shuffle(pos); rng.shuffle(neg)
    pos=_patient_unique(pos)
    pos_patient={(c.source,c.patient_id) for c in pos if c.patient_id}
    neg=[c for c in _patient_unique(neg) if not c.patient_id or (c.source,c.patient_id) not in pos_patient]
    pos=pos[:TARGET_POS]; neg=neg[:TARGET_NEG]
    status="READY" if len(pos)>=TARGET_POS and len(neg)>=TARGET_NEG else "TEST_DATA_INSUFFICIENT"
    return pos+neg,status

def bbox_iou(a,b)->float:
    if not a or not b or len(a)!=4 or len(b)!=4:return 0.0
    x1,y1=max(a[0],b[0]),max(a[1],b[1]); x2,y2=min(a[2],b[2]),min(a[3],b[3])
    inter=max(0,x2-x1)*max(0,y2-y1)
    aa=max(0,a[2]-a[0])*max(0,a[3]-a[1]); bb=max(0,b[2]-b[0])*max(0,b[3]-b[1])
    return inter/(aa+bb-inter) if aa+bb-inter>0 else 0.0

def _gt_boxes(annotation:dict|None):
    ann=annotation or {}
    boxes=ann.get("bboxes") or []
    # Convert normalized YOLO xywh to normalized xyxy when supplied.
    for q in ann.get("yolo_xywh") or []:
        if isinstance(q,(list,tuple)) and len(q)==4:
            x,y,w,h=map(float,q); boxes.append([x-w/2,y-h/2,x+w/2,y+h/2])
    return boxes

def evaluate_target(cases:list[Case], infer:Callable[[str,str],dict], finding_code:str, modality:str)->dict:
    result_path=STATE/f"{modality}__{finding_code}.json"
    old=load_json(result_path,{})
    # Cache identity includes polarity; a hash legitimately reused for another target is stored in a different state file.
    done={(x["sha256"],x.get("polarity")):x for x in old.get("cases",[]) if x.get("sha256")}
    rows=[]
    for c in cases:
        if (c.sha256,c.polarity) in done: rows.append(done[(c.sha256,c.polarity)]); continue
        row={"case_id":c.case_id,"sha256":c.sha256,"polarity":c.polarity,"source":c.source}
        try:
            pred=infer(c.image_path,modality) or {}
            fs=pred.get("findings",[]) if isinstance(pred,dict) else []
            matches=[x for x in fs if isinstance(x,dict) and (x.get("finding_code") or x.get("code") or x.get("label"))==finding_code]
            detected=bool(matches)
            row["detected"]=detected
            row["raw_matches"]=matches
            gt_boxes=_gt_boxes(c.annotation)
            pred_boxes=[x.get("bbox") for x in matches if x.get("bbox")]
            # Production motors generally return pixel xyxy, while YOLO GT is normalized.
            # Normalize predictions only when image dimensions are available and coordinates exceed 1.
            if gt_boxes and pred_boxes and any(max(map(float,b))>1.5 for b in pred_boxes):
                try:
                    from PIL import Image
                    w,h=Image.open(c.image_path).size
                    pred_boxes=[[float(b[0])/w,float(b[1])/h,float(b[2])/w,float(b[3])/h] for b in pred_boxes]
                except Exception:
                    pred_boxes=[]
            if gt_boxes and pred_boxes:
                row["max_iou"]=max(bbox_iou(g,p) for g in gt_boxes for p in pred_boxes)
                row["localized"]=row["max_iou"]>=0.20
            row["outcome"]=("TP" if detected else "FN") if c.polarity=="positive" else ("FP" if detected else "TN")
        except Exception as e:
            row.update(outcome="MOTOR_ERROR",error=f"{type(e).__name__}: {e}"[:800])
        rows.append(row)
        atomic_json(result_path,{"modality":modality,"finding_code":finding_code,"cases":rows})
    counts={k:sum(r.get("outcome")==k for r in rows) for k in ("TP","FN","TN","FP","MOTOR_ERROR")}
    p=counts["TP"]+counts["FN"]; n=counts["TN"]+counts["FP"]
    recall=counts["TP"]/p if p else None; spec=counts["TN"]/n if n else None
    localized=[r for r in rows if r.get("polarity")=="positive" and "max_iou" in r]
    loc=sum(r["max_iou"]>=0.20 for r in localized)/len(localized) if localized else None
    loc50=sum(r["max_iou"]>=0.50 for r in localized)/len(localized) if localized else None
    return {"modality":modality,"finding_code":finding_code,**counts,"recall":recall,"sensitivity":recall,"specificity":spec,
            "localization_iou20_rate":loc,"localization_iou50_rate":loc50,"localization_rate":loc,"n":len(rows)}

def validate_locked_pool(cases:list[Case]):
    errors=[]
    by_target={}
    hashes=set()
    for c in cases:
        if c.polarity not in {"positive","negative"}: errors.append(f"bad polarity:{c.case_id}")
        p=Path(c.image_path)
        if not p.is_file(): errors.append(f"missing:{c.case_id}"); continue
        if not _image_ok(p): errors.append(f"corrupt image:{c.case_id}"); continue
        actual=sha256_file(p)
        if actual!=c.sha256: errors.append(f"hash mismatch:{c.case_id}")
        hk=(c.modality,c.finding_code,c.polarity,actual)
        if hk in hashes: errors.append(f"duplicate target hash:{c.case_id}")
        hashes.add(hk)
        by_target.setdefault((c.modality,c.finding_code),{"positive":0,"negative":0})
        by_target[(c.modality,c.finding_code)][c.polarity]+=1
    if errors: raise RuntimeError("Locked test pool integrity failed: "+"; ".join(errors[:20]))
    return by_target

def write_manifest(cases:list[Case], source_meta:dict[str,Any]):
    atomic_json(ROOT/"locked_test_manifest.json",{
        "schema":1,"created_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
        "target_positive":TARGET_POS,"target_negative":TARGET_NEG,
        "cases":[asdict(c) for c in cases],"sources":source_meta,
        "rule":"TEST_LOCKED hashes/patients are forbidden from train and validation pools."
    })

def forbidden_test_hashes(manifest_path:Path|None=None)->set[str]:
    manifest_path=manifest_path or ROOT/"locked_test_manifest.json"
    return {x.get("sha256") for x in load_json(manifest_path,{}).get("cases",[]) if x.get("sha256")}

def assert_training_pool_clean(paths:list[str|Path], manifest_path:Path|None=None):
    forbidden=forbidden_test_hashes(manifest_path)
    collisions=[]
    for p in paths:
        p=Path(p)
        if p.is_file() and sha256_file(p) in forbidden: collisions.append(str(p))
    if collisions: raise RuntimeError("TEST LEAKAGE: "+", ".join(collisions[:20]))
    return True

def export_report(rows:list[dict]):
    atomic_json(REPORTS/"baseline_report.json",rows)
    fields=["modality","finding_code","TP","FN","TN","FP","MOTOR_ERROR","recall","specificity","localization_rate","n","decision"]
    with open(REPORTS/"baseline_report.csv","w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in rows:w.writerow({k:r.get(k) for k in fields})

def disk_guard(min_free_gb:float=3.0):
    free=shutil.disk_usage("/kaggle/working").free/1024**3
    if free<min_free_gb: raise RuntimeError(f"Disk guard: only {free:.1f} GB free")
    return free


def compare_reports(before_path:str|Path, after_path:str|Path, contract_path:str|Path)->list[dict]:
    """Compare before/after metrics only when the after run used the exact locked hash set."""
    before=load_json(Path(before_path),[])
    after=load_json(Path(after_path),[])
    contract=load_json(Path(contract_path),{})
    expected=set(contract.get("locked_hashes",[]))
    if not expected:
        raise RuntimeError("comparison contract has no locked hashes")
    current=forbidden_test_hashes()
    if current!=expected:
        raise RuntimeError("AFTER-TRAIN TEST POOL CHANGED")
    b={(r.get("modality"),r.get("finding_code")):r for r in before if isinstance(r,dict)}
    out=[]
    for a in after:
        if not isinstance(a,dict): continue
        k=(a.get("modality"),a.get("finding_code")); old=b.get(k,{})
        out.append({"modality":k[0],"finding_code":k[1],
                    "before_recall":old.get("recall"),"after_recall":a.get("recall"),
                    "before_specificity":old.get("specificity"),"after_specificity":a.get("specificity"),
                    "before_decision":old.get("decision"),"after_decision":a.get("decision")})
    return out
