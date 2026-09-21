from __future__ import annotations
import cv2
import numpy as np

def _smooth(points, win=11):
    if len(points)<5:return points
    a=np.asarray(points,np.float32); k=max(3,min(win,len(a)//2*2-1))
    if k<3:return points
    ker=np.ones(k,dtype=np.float32)/k; pad=k//2
    x=np.convolve(np.pad(a[:,0],(pad,pad),mode='edge'),ker,mode='valid')
    y=np.convolve(np.pad(a[:,1],(pad,pad),mode='edge'),ker,mode='valid')
    return [[round(float(px),1),round(float(py),1)] for px,py in zip(x,y)]

def _tooth_envelope(teeth, upper):
    boxes=[list(map(float,t.get("bbox",[]))) for t in teeth if len(t.get("bbox") or [])==4 and str(t.get("fdi",""))[:1] in (("1","2") if upper else ("3","4"))]
    if len(boxes)<4:return None
    boxes.sort(key=lambda b:(b[0]+b[2])/2)
    top=[[ (b[0]+b[2])/2,b[1]] for b in boxes]; bot=[[ (b[0]+b[2])/2,b[3]] for b in boxes]
    return top,bot

def extract_panorama_anatomy(image_path:str, teeth:list[dict])->dict:
    """Conservative image-derived jaw/sinus contours.
    Returns nothing for structures that cannot be supported by image edges.
    """
    img=cv2.imread(image_path,cv2.IMREAD_GRAYSCALE)
    if img is None:return {}
    h,w=img.shape; blur=cv2.GaussianBlur(img,(7,7),0)
    clahe=cv2.createCLAHE(2.0,(8,8)).apply(blur)
    edges=cv2.Canny(clahe,45,115)
    out={}

    # Mandible: track strongest inferior cortical edge below lower teeth.
    env=_tooth_envelope(teeth,False)
    if env:
        _,bottom=env; xs=np.linspace(max(0,bottom[0][0]-w*.08),min(w-1,bottom[-1][0]+w*.08),72)
        medh=np.median([b[3]-b[1] for b in [list(map(float,t["bbox"])) for t in teeth if len(t.get("bbox") or [])==4]]) if teeth else h*.08
        pts=[]; prev=None
        for x in xs:
            near=min(bottom,key=lambda p:abs(p[0]-x)); y0=int(min(h-2,near[1]+medh*.20)); y1=int(min(h-2,near[1]+medh*1.65))
            if y1<=y0:continue
            col=edges[y0:y1+1,max(0,int(x)-2):min(w,int(x)+3)].mean(axis=1)
            cand=np.where(col>30)[0]
            if not len(cand):continue
            ys=y0+cand; y=int(ys[np.argmax(ys)]) if prev is None else int(ys[np.argmin(abs(ys-prev))])
            if prev is None or abs(y-prev)<medh*.55:pts.append([float(x),float(y)]);prev=y
        if len(pts)>=24:
            inferior=_smooth(pts,13)
            # alveolar boundary follows actual tooth-adjacent edge, not a primitive.
            crest=[]
            for x,_ in pts:
                near=min(bottom,key=lambda p:abs(p[0]-x)); cy=int(near[1]); span=int(max(8,medh*.45)); ya=max(1,cy-span);yb=min(h-2,cy+span)
                col=edges[ya:yb+1,max(0,int(x)-2):min(w,int(x)+3)].mean(axis=1); cand=np.where(col>28)[0]
                if len(cand):crest.append([float(x),float(ya+cand[0])])
            if len(crest)>=20:
                crest=_smooth(crest,11)
                out["mandible"]=_smooth(crest+inferior[::-1],11)

    # Maxillary alveolar envelope: image edge immediately apical to upper teeth.
    env=_tooth_envelope(teeth,True)
    if env:
        top,_=env; medh=np.median([float(t["bbox"][3])-float(t["bbox"][1]) for t in teeth if len(t.get("bbox") or [])==4])
        xs=np.linspace(top[0][0],top[-1][0],64); alve=[]
        for x in xs:
            near=min(top,key=lambda p:abs(p[0]-x)); cy=int(near[1]); ya=max(1,int(cy-medh*.55));yb=min(h-2,int(cy+medh*.22))
            col=edges[ya:yb+1,max(0,int(x)-2):min(w,int(x)+3)].mean(axis=1); cand=np.where(col>28)[0]
            if len(cand):alve.append([float(x),float(ya+cand[-1])])
        if len(alve)>=20:
            crest=_smooth(alve,11); thickness=max(10.0,medh*.55)
            outer=[[x,max(0.0,y-thickness)] for x,y in crest]
            out["maxilla"]=_smooth(outer+crest[::-1],11)

    # Sinus: only accept large closed edge contours in upper posterior ROIs.
    sinuses=[]
    for side in (0,1):
        xa,xb=(int(w*.08),int(w*.48)) if side==0 else (int(w*.52),int(w*.92))
        ya,yb=int(h*.08),int(h*.55); roi=edges[ya:yb,xa:xb]
        cs,_=cv2.findContours(roi,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        best=None;score=0
        for c in cs:
            area=cv2.contourArea(c); peri=cv2.arcLength(c,True)
            if area<roi.size*.025 or peri<=0:continue
            x,y,cw,ch=cv2.boundingRect(c)
            if cw<roi.shape[1]*.18 or ch<roi.shape[0]*.12:continue
            s=area/(cw*ch+1)
            if s>score:best=c;score=s
        if best is not None and score>.12:
            eps=cv2.approxPolyDP(best,4.0,True).reshape(-1,2)
            if len(eps)>=6:sinuses.append([[float(x+xa),float(y+ya)] for x,y in eps])
    if sinuses:out["maxillary_sinuses"]=sinuses
    return out
