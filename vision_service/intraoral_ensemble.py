from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from vision_service.gradcam_localizer import normalize_gradcam_regions

class IntraoralEnsembleError(RuntimeError): pass
INTRAORAL_ENSEMBLE_URL=os.getenv("INTRAORAL_ENSEMBLE_URL","").strip().rstrip("/")
INTRAORAL_ENSEMBLE_API_KEY=os.getenv("INTRAORAL_ENSEMBLE_API_KEY","").strip()
INTRAORAL_ENSEMBLE_TIMEOUT_SECONDS=float(os.getenv("INTRAORAL_ENSEMBLE_TIMEOUT_SECONDS","90"))
INTRAORAL_INTERNAL_CANDIDATE_THRESHOLD=float(os.getenv("INTRAORAL_INTERNAL_CANDIDATE_THRESHOLD","0.02"))
INTRAORAL_DISPLAY_THRESHOLD=float(os.getenv("INTRAORAL_DISPLAY_THRESHOLD","0.50"))
INTRAORAL_SPATIAL_SUPPORT_MIN_CONFIDENCE=float(os.getenv("INTRAORAL_SPATIAL_SUPPORT_MIN_CONFIDENCE","0.05"))
INTRAORAL_FUSION_IOU_THRESHOLD=float(os.getenv("INTRAORAL_FUSION_IOU_THRESHOLD","0.20"))
ALPHADENT_LABELS={"abrasion":("DENTAL_ABRASION","Diş abrazyonu"),"filling":("DENTAL_FILLING","Dolgu/restorasyon"),"crown":("CROWN_RESTORATION","Kron restorasyonu"),**{f"caries {i} class":("VISIBLE_CARIES","Çürük şüphesi") for i in range(1,7)}}
DAATH_CARIES_LABELS={"d","caries","cavity","decay","dental caries"}
ORAL_CLASSIFIER_LABELS={"calculus":("CALCULUS","Diş taşı şüphesi"),"caries":("VISIBLE_CARIES","Çürük şüphesi"),"gingivitis":("GINGIVAL_INFLAMMATION","Dişeti iltihabı şüphesi"),"hypodontia":("HYPODONTIA_CANDIDATE","Diş eksikliği şüphesi"),"tooth discoloration":("TOOTH_DISCOLORATION","Diş renklenmesi şüphesi"),"ulcers":("ORAL_ULCER_CANDIDATE","Ağız ülseri şüphesi"),"ulcer":("ORAL_ULCER_CANDIDATE","Ağız ülseri şüphesi")}
def configured(): return bool(INTRAORAL_ENSEMBLE_URL)
def _multipart_body(image_path):
    boundary="----DentalAIIntraoralEnsembleBoundary"; path=Path(image_path); mime=mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body=b"".join([f"--{boundary}\r\n".encode(),f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode(),f"Content-Type: {mime}\r\n\r\n".encode(),path.read_bytes(),b"\r\n",f"--{boundary}--\r\n".encode()]); return body,f"multipart/form-data; boundary={boundary}"
def _bbox(item):
    box=item.get("bbox") or item.get("box")
    if isinstance(box,dict):
        if all(k in box for k in ("x1","y1","x2","y2")): box=[box["x1"],box["y1"],box["x2"],box["y2"]]
        elif all(k in box for k in ("x","y","w","h")): box=[box["x"],box["y"],box["x"]+box["w"],box["y"]+box["h"]]
    try: return [float(x) for x in box] if isinstance(box,list) and len(box)==4 else None
    except Exception: return None
def _score(item):
    try: return max(0.,min(1.,float(item.get("confidence",item.get("score",item.get("probability",0.))))))
    except Exception: return 0.
def _raw_label(item): return str(item.get("label") or item.get("class_name") or item.get("class") or item.get("name") or "").strip().casefold()
def _iou(a,b):
    if not a or not b:return 0.
    x1,y1=max(a[0],b[0]),max(a[1],b[1]);x2,y2=min(a[2],b[2]),min(a[3],b[3]);inter=max(0.,x2-x1)*max(0.,y2-y1);aa=max(0.,a[2]-a[0])*max(0.,a[3]-a[1]);bb=max(0.,b[2]-b[0])*max(0.,b[3]-b[1]);u=aa+bb-inter;return inter/u if u>0 else 0.
def _normalize_alpha(item):
    raw=_raw_label(item);m=ALPHADENT_LABELS.get(raw)
    if not m:return None
    return {"finding_code":m[0],"label":m[1],"raw_label":raw,"confidence":round(_score(item),4),"bbox":_bbox(item),"source_motor":"alphadent_9class_960","candidate_only":False,"modality":"INTRAORAL_PHOTO"}
def _normalize_daath(item):
    raw=_raw_label(item)
    if raw not in DAATH_CARIES_LABELS:return None
    return {"finding_code":"VISIBLE_CARIES","label":"Çürük şüphesi","raw_label":raw,"confidence":round(_score(item),4),"bbox":_bbox(item),"source_motor":"daath_caries","candidate_only":True,"modality":"INTRAORAL_PHOTO"}
def _normalize_classifier(item):
    raw=_raw_label(item);m=ORAL_CLASSIFIER_LABELS.get(raw)
    if not m:return None
    return {"finding_code":m[0],"label":m[1],"raw_label":raw,"confidence":round(_score(item),4),"source_motor":"oral_diseases_resnet50","candidate_only":True,"image_level":True,"localization_available":False,"modality":"INTRAORAL_PHOTO"}
def _dedupe_alpha_caries(alpha_caries):
    """Collapse overlapping AlphaDent Caries 1-6 detections into one canonical lesion."""
    pending=sorted(alpha_caries,key=lambda x:x.get("confidence",0),reverse=True);groups=[]
    while pending:
        seed=pending.pop(0);group=[seed];rest=[]
        for item in pending:
            if any(_iou(item.get("bbox"),g.get("bbox"))>=.20 for g in group):group.append(item)
            else:rest.append(item)
        pending=rest
        best=max(group,key=lambda x:x.get("confidence",0))
        groups.append({**best,"raw_label":"caries","alpha_candidates":[{"raw_label":g["raw_label"],"confidence":g["confidence"],"bbox":g.get("bbox")} for g in group],"deduped_count":len(group)})
    return groups

def _merge_caries(alpha,daath,classifier=None):
    classifier=classifier or []
    classifier_caries=next((x for x in classifier if x.get("finding_code")=="VISIBLE_CARIES"),None)
    ac=_dedupe_alpha_caries([x for x in alpha if x["finding_code"]=="VISIBLE_CARIES" and x["confidence"]>=INTRAORAL_INTERNAL_CANDIDATE_THRESHOLD]);out=[x for x in alpha if x["finding_code"]!="VISIBLE_CARIES" and x["confidence"]>=INTRAORAL_DISPLAY_THRESHOLD];used=set()
    for a in ac:
        bi,bo=None,0.
        for i,d in enumerate(daath):
            if i in used or d.get("confidence",0)<INTRAORAL_SPATIAL_SUPPORT_MIN_CONFIDENCE:continue
            o=_iou(a.get("bbox"),d.get("bbox"))
            if o>bo:bi,bo=i,o
        if bi is not None and bo>=INTRAORAL_FUSION_IOU_THRESHOLD:
            d=daath[bi];used.add(bi);out.append({**a,"source_motor":"alphadent+daath","agreement":True,"fusion_supported":True,"support_motor":"daath_caries","support_confidence":d["confidence"],"support_iou":round(bo,4),"motor_scores":{"alphadent":a["confidence"],"daath":d["confidence"]},"internal_evidence":{"alphadent_candidates":a.get("alpha_candidates",[]),"daath":{"raw_label":d["raw_label"],"confidence":d["confidence"],"bbox":d.get("bbox")}}})
        elif a["confidence"]>=INTRAORAL_DISPLAY_THRESHOLD:out.append(a)
        elif classifier_caries and classifier_caries["confidence"]>=INTRAORAL_DISPLAY_THRESHOLD:
            # Image-level ResNet may support a weak localized AlphaDent caries
            # candidate, but never supplies or changes its bbox.
            out.append({**a,"source_motor":"alphadent+oral_resnet50_support","agreement":True,"classifier_support":{"motor":"oral_diseases_resnet50","confidence":classifier_caries["confidence"],"image_level":True,"bbox":None},"internal_evidence":{"alphadent_candidates":a.get("alpha_candidates",[]),"oral_resnet50":{"raw_label":classifier_caries["raw_label"],"confidence":classifier_caries["confidence"],"image_level":True,"bbox":None}}})
    out.extend(d for i,d in enumerate(daath) if i not in used and d["confidence"]>=.70);out.sort(key=lambda x:x.get("confidence",0),reverse=True);return out
def analyze_intraoral_ensemble(image_path):
    if not configured():raise IntraoralEnsembleError("Ağız içi motor servisi yapılandırılmadı: INTRAORAL_ENSEMBLE_URL eksik.")
    path=Path(image_path)
    if not path.is_file():raise IntraoralEnsembleError("Ağız içi görüntü dosyası bulunamadı.")
    body,ct=_multipart_body(str(path));headers={"Content-Type":ct,"Accept":"application/json","User-Agent":"DentalAI-Intraoral-Ensemble/2.1"}
    if INTRAORAL_ENSEMBLE_API_KEY:headers["Authorization"]=f"Bearer {INTRAORAL_ENSEMBLE_API_KEY}"
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{INTRAORAL_ENSEMBLE_URL}/infer",data=body,headers=headers,method="POST"),timeout=INTRAORAL_ENSEMBLE_TIMEOUT_SECONDS) as r:payload=json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:raise IntraoralEnsembleError(f"Intraoral ensemble HTTP {exc.code}: {exc.read().decode(errors='replace')[-1200:]}") from exc
    except (urllib.error.URLError,TimeoutError,json.JSONDecodeError) as exc:raise IntraoralEnsembleError(f"Intraoral ensemble erişim/yanıt hatası: {exc}") from exc
    if not isinstance(payload,dict):raise IntraoralEnsembleError("Intraoral ensemble geçersiz JSON döndürdü.")
    ar,dr,cr=payload.get("alphadent",[]),payload.get("daath",[]),payload.get("oral_resnet50",payload.get("classifier",[]))
    if not all(isinstance(x,list) for x in (ar,dr,cr)):raise IntraoralEnsembleError("Yanıtta motor çıktıları liste olmalı.")
    alpha=[x for i in ar if isinstance(i,dict) if (x:=_normalize_alpha(i))];daath=[x for i in dr if isinstance(i,dict) if (x:=_normalize_daath(i))];classifier=[x for i in cr if isinstance(i,dict) if (x:=_normalize_classifier(i))]
    findings=_merge_caries(alpha,daath,classifier);support={x["finding_code"]:x for x in classifier}
    for f in findings:
        if f["finding_code"] in support:
            s=support[f["finding_code"]]
            f["classifier_support"]={"motor":"oral_diseases_resnet50","confidence":s["confidence"],"image_level":True,"bbox":None}
            f.setdefault("internal_evidence",{})["oral_resnet50"]={"raw_label":s["raw_label"],"confidence":s["confidence"],"image_level":True,"bbox":None}
    gradcam=normalize_gradcam_regions(payload.get("gradcam",[]));by_label={x["class_label"].casefold():[] for x in gradcam}
    for x in gradcam:by_label.setdefault(x["class_label"].casefold(),[]).append(x)
    image_level=[]
    for x in classifier:
        if x["confidence"]<.50:continue
        regions=by_label.get(x["raw_label"],[])
        if regions:x={**x,"attention_regions":regions,"localization_available":True,"localization_type":"gradcam_attention","localization_disclaimer":"Modelin karar verirken odaklandığı bölgedir; doğrulanmış lezyon sınırı değildir."}
        image_level.append(x)
    return {"ok":True,"engine":"intraoral_ensemble_v2_1","engine_role":"primary","modality":"INTRAORAL_PHOTO","findings":findings,"finding_count":len(findings),"image_level_findings":image_level,"gradcam_attention":gradcam,"motors":["alphadent_9class_960","daath_caries","oral_diseases_resnet50","resnet50_gradcam"],"notes":["AlphaDent ve Daath gerçek detector lokalizasyonu sağlar.","ResNet50 Grad-CAM bölgeleri yalnız model odağıdır; lezyon kutusu olarak sunulmaz.","Zayıf lokalize çürük adayı için Daath desteği en az 0.05 skor ve 0.20 IoU gerektirir.","Motor güven skorları birbirine eklenmez."]}
