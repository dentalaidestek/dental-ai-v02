from __future__ import annotations

from collections import Counter

from vision_service.cv_signals import (
    apical_bbox,
    bbox_distance,
    bbox_iou,
    condyle_signals,
    expand_bbox,
    line_score,
    load_gray,
    patch_stats,
    root_curvature_score,
    tooth_crown_bbox,
    tooth_root_bbox,
)
from vision_service.motors.catalog import FINDING_CATALOG


def _finding(code: str, confidence: float, *, bbox=None, fdi=None, motor="derived48", evidence=None, measurement=None):
    label, category = FINDING_CATALOG[code]
    item = {
        "finding_code": code,
        "label": label,
        "category": category,
        "confidence": round(max(0.0, min(0.99, float(confidence))), 4),
        "motor": motor,
        "evidence_type": "derived",
    }
    if bbox:
        item["bbox"] = [round(float(v), 1) for v in bbox]
    if fdi is not None:
        item["fdi"] = fdi
    if evidence:
        item["evidence"] = list(evidence)
    if measurement is not None:
        item["measurement"] = measurement
    return item


def _by_code(findings: list[dict], code: str) -> list[dict]:
    return [x for x in findings if x.get("finding_code") == code]


def _helpers(helpers: list[dict], signal: str) -> list[dict]:
    return [x for x in helpers if x.get("signal") == signal]


def _nearest_tooth(bbox, teeth):
    scored = []
    for tooth in teeth:
        tb = tooth.get("bbox") or []
        if len(tb) == 4:
            scored.append((bbox_distance(bbox, tb), tooth))
    return min(scored, key=lambda x: x[0])[1] if scored else None


def _same_fdi_or_overlap(a, b) -> bool:
    af, bf = a.get("fdi"), b.get("fdi")
    if af is not None and bf is not None and str(af) == str(bf):
        return True
    return bbox_iou(a.get("bbox"), b.get("bbox")) >= 0.12


def derive_findings(image_path: str | None, teeth: list[dict], findings: list[dict], helpers: list[dict], *, patient_age: int | None = None) -> list[dict]:
    out: list[dict] = []
    gray = load_gray(image_path) if image_path else None

    # 2 — supernumerary: duplicate FDI boxes that are spatially distinct, or >32 tooth instances.
    fdis = [str(t.get("fdi")) for t in teeth if t.get("fdi") is not None]
    counts = Counter(fdis)
    for fdi, count in counts.items():
        if count > 1:
            boxes = [t.get("bbox") for t in teeth if str(t.get("fdi")) == fdi and t.get("bbox")]
            if len(boxes) > 1 and max(bbox_distance(a, b) for i, a in enumerate(boxes) for b in boxes[i+1:]) > 4:
                out.append(_finding("SUPERNUMERARY_TOOTH", 0.62, bbox=boxes[-1], evidence=["duplicate_fdi_geometry"]))
    if len(teeth) > 32 and not _by_code(out, "SUPERNUMERARY_TOOTH"):
        out.append(_finding("SUPERNUMERARY_TOOTH", min(0.85, 0.55 + (len(teeth)-32)*0.05), evidence=["tooth_count_above_32"], measurement={"tooth_count": len(teeth)}))

    # 3 — retained primary tooth from explicit helper; age gates obvious pediatric false positives.
    for h in _helpers(helpers, "PRIMARY_TOOTH_HELPER"):
        if patient_age is None or patient_age >= 12:
            tooth = _nearest_tooth(h.get("bbox"), teeth)
            out.append(_finding("RETAINED_PRIMARY_TOOTH", max(0.45, h.get("confidence", 0.0)), bbox=h.get("bbox"), fdi=tooth.get("fdi") if tooth else None, evidence=["PRIMARY_TOOTH_HELPER"]))

    # 4 — unerupted: tooth bbox vertical outlier from quadrant arch, excluding already-impacted regions.
    if len(teeth) >= 10:
        centers = []
        for t in teeth:
            b = t.get("bbox") or []
            if len(b) == 4:
                centers.append(((float(b[1])+float(b[3]))/2.0, t))
        if centers:
            ys = sorted(v for v, _ in centers)
            med = ys[len(ys)//2]; span = max(20.0, ys[-1]-ys[0])
            impacted = _by_code(findings, "IMPACTED_TOOTH")
            for cy, t in centers:
                if abs(cy-med) / span > 0.42 and not any(bbox_iou(t.get("bbox"), x.get("bbox")) > 0.12 for x in impacted):
                    out.append(_finding("UNERUPTED_TOOTH", 0.48, bbox=t.get("bbox"), fdi=t.get("fdi"), evidence=["off_arch_tooth_geometry"]))

    # 6 — impacted third molar.
    for x in _by_code(findings, "IMPACTED_TOOTH"):
        fdi = str(x.get("fdi") or "")
        if fdi in {"18", "28", "38", "48"}:
            out.append(_finding("IMPACTED_THIRD_MOLAR", max(0.55, x.get("confidence", 0.0)), bbox=x.get("bbox"), fdi=x.get("fdi"), evidence=["IMPACTED_TOOTH", "third_molar_fdi"]))

    # 10 — partial coverage radiopaque restoration, only when a filling exists and no crown occupies same tooth.
    crowns = _by_code(findings, "CROWN")
    for fill in _by_code(findings, "FILLING"):
        if any(_same_fdi_or_overlap(fill, c) for c in crowns):
            continue
        tooth = _nearest_tooth(fill.get("bbox"), teeth)
        if tooth and gray is not None:
            stats = patch_stats(gray, tooth_crown_bbox(tooth))
            if stats and 0.02 <= stats.get("bright_fraction", 0.0) <= 0.22:
                out.append(_finding("INLAY_ONLAY", 0.46 + min(0.20, stats["bright_fraction"]), bbox=fill.get("bbox"), fdi=tooth.get("fdi"), evidence=["FILLING", "partial_coverage_radiopacity"]))

    # 12 — pontic fallback: bridge region without a detected tooth at its center.
    if not _by_code(findings, "PONTIC"):
        for bridge in _by_code(findings, "BRIDGE"):
            b = bridge.get("bbox") or []
            if len(b) == 4:
                cx = (float(b[0])+float(b[2]))/2.0; cy = (float(b[1])+float(b[3]))/2.0
                occupied = any((tb := t.get("bbox")) and len(tb) == 4 and tb[0] <= cx <= tb[2] and tb[1] <= cy <= tb[3] for t in teeth)
                if not occupied:
                    out.append(_finding("PONTIC", 0.48, bbox=b, evidence=["BRIDGE", "edentulous_span_geometry"]))

    # 14 — implant-supported crown.
    for imp in _by_code(findings, "IMPLANT"):
        for crown in _by_code(findings, "CROWN"):
            if _same_fdi_or_overlap(imp, crown) or bbox_distance(imp.get("bbox"), crown.get("bbox")) <= 8:
                out.append(_finding("IMPLANT_SUPPORTED_CROWN", min(0.97, (imp.get("confidence",0)+crown.get("confidence",0))/2), bbox=crown.get("bbox") or imp.get("bbox"), fdi=crown.get("fdi") or imp.get("fdi"), evidence=["IMPLANT", "CROWN"]))
    for abut in _helpers(helpers, "ABUTMENT_HELPER"):
        imp = min(_by_code(findings, "IMPLANT"), key=lambda x: bbox_distance(abut.get("bbox"), x.get("bbox")), default=None)
        if imp and bbox_distance(abut.get("bbox"), imp.get("bbox")) <= 12:
            out.append(_finding("IMPLANT_SUPPORTED_CROWN", max(0.52, abut.get("confidence",0)), bbox=abut.get("bbox"), fdi=imp.get("fdi"), evidence=["IMPLANT", "ABUTMENT_HELPER"]))

    # 16-20 — endodontic geometry candidates.
    for rct in _by_code(findings, "ROOT_CANAL_TREATED"):
        tooth = next((t for t in teeth if str(t.get("fdi")) == str(rct.get("fdi")) and t.get("fdi") is not None), None) or _nearest_tooth(rct.get("bbox"), teeth)
        if not tooth or gray is None:
            continue
        root = tooth_root_bbox(tooth); apex = apical_bbox(tooth)
        root_stats = patch_stats(gray, root); apex_stats = patch_stats(gray, apex)
        ls = line_score(gray, root)
        if root_stats and root_stats.get("bright_fraction",0) > 0.075 and ls > 0.16:
            out.append(_finding("ENDO_POST", 0.45 + min(0.25, ls), bbox=root, fdi=tooth.get("fdi"), evidence=["ROOT_CANAL_TREATED", "intraradicular_radiopaque_line"]))
        if root_stats and apex_stats:
            root_bright = root_stats.get("bright_fraction",0); apex_bright = apex_stats.get("bright_fraction",0)
            if root_bright > 0.035 and apex_bright < max(0.015, root_bright * 0.22):
                out.append(_finding("UNDERFILLED_ROOT_CANAL", 0.48, bbox=root, fdi=tooth.get("fdi"), evidence=["ROOT_CANAL_TREATED", "short_fill_extent"]))
            if apex_bright > max(0.08, root_bright * 1.5):
                out.append(_finding("OVERFILLED_ROOT_CANAL", 0.50, bbox=apex, fdi=tooth.get("fdi"), evidence=["ROOT_CANAL_TREATED", "apical_radiopaque_extension"]))
            if ls > 0.38 and root_bright > 0.035:
                out.append(_finding("BROKEN_ENDO_INSTRUMENT", 0.44 + min(0.18, ls*0.2), bbox=root, fdi=tooth.get("fdi"), evidence=["isolated_linear_root_signal"]))
            if apex_bright > 0.09 and ls > 0.22:
                out.append(_finding("APICAL_SURGERY", 0.43, bbox=apex, fdi=tooth.get("fdi"), evidence=["ROOT_CANAL_TREATED", "apical_resection_retrofill_pattern"]))

    # 22 — deep caries fallback: caries bbox extends into central/deeper crown region.
    if not _by_code(findings, "DEEP_CARIES"):
        for caries in _by_code(findings, "CARIES"):
            tooth = _nearest_tooth(caries.get("bbox"), teeth)
            if tooth:
                tb = tooth.get("bbox") or []; cb = caries.get("bbox") or []
                if len(tb)==4 and len(cb)==4:
                    tooth_area=max(1.0,(tb[2]-tb[0])*(tb[3]-tb[1])); caries_area=max(0.0,(cb[2]-cb[0])*(cb[3]-cb[1]))
                    if caries_area/tooth_area >= 0.12:
                        out.append(_finding("DEEP_CARIES", 0.46, bbox=cb, fdi=tooth.get("fdi"), evidence=["CARIES", "large_crown_depth_ratio"]))

    # 23 — recurrent caries at restoration margin.
    restorations = sum((_by_code(findings, c) for c in ("FILLING","CROWN","BRIDGE")), [])
    for caries in _by_code(findings, "CARIES"):
        for restoration in restorations:
            if _same_fdi_or_overlap(caries, restoration) or bbox_distance(caries.get("bbox"), restoration.get("bbox")) <= 6:
                out.append(_finding("RECURRENT_CARIES", min(0.91, (caries.get("confidence",0)+restoration.get("confidence",0))/2), bbox=caries.get("bbox"), fdi=caries.get("fdi") or restoration.get("fdi"), evidence=["CARIES", restoration.get("finding_code")]))
                break

    # 25-28, 31, 33 — per-tooth image geometry.
    if gray is not None:
        for tooth in teeth:
            root = tooth_root_bbox(tooth); apex = apical_bbox(tooth)
            if not root or not apex:
                continue
            rs = patch_stats(gray, root); aps = patch_stats(gray, apex); fdi = tooth.get("fdi")
            if aps and rs:
                if aps.get("mean",0) > rs.get("mean",0) + max(18.0, rs.get("std",0)*0.55):
                    out.append(_finding("PERIAPICAL_RADIOPACITY", 0.47, bbox=apex, fdi=fdi, evidence=["apical_density_high"]))
                if rs.get("dark_fraction",0) > 0.18 and rs.get("std",0) > 32:
                    out.append(_finding("WIDENED_PDL", 0.43, bbox=root, fdi=fdi, evidence=["root_border_dark_band"]))
                if rs.get("std",0) < 22 and rs.get("dark_fraction",0) > 0.10:
                    out.append(_finding("LOSS_OF_LAMINA_DURA", 0.41, bbox=root, fdi=fdi, evidence=["root_border_low_continuity"]))
            curvature = root_curvature_score(gray, tooth)
            if curvature >= 0.42:
                out.append(_finding("ROOT_DILACERATION", 0.45 + min(0.22, curvature*0.25), bbox=root, fdi=fdi, evidence=["root_centerline_curvature"], measurement={"curvature_score": round(curvature,3)}))
            fracture = line_score(gray, root)
            if fracture >= 0.48:
                out.append(_finding("ROOT_FRACTURE", 0.44 + min(0.18, fracture*0.2), bbox=root, fdi=fdi, evidence=["root_fracture_line_score"], measurement={"line_score": round(fracture,3)}))

    for radio in _by_code(out, "PERIAPICAL_RADIOPACITY"):
        b = radio.get("bbox")
        if b and gray is not None:
            st = patch_stats(gray, expand_bbox(b, 0.35))
            if st and st.get("std",0) < 48:
                out.append(_finding("CONDENSING_OSTEITIS_PATTERN", max(0.44, radio.get("confidence",0)-0.02), bbox=expand_bbox(b,0.2), fdi=radio.get("fdi"), evidence=["PERIAPICAL_RADIOPACITY", "diffuse_density_pattern"]))

    # 29-30 — split generic resorption using center-vs-border intensity morphology.
    for res in _helpers(helpers, "ROOT_RESORPTION_GENERIC"):
        tooth = _nearest_tooth(res.get("bbox"), teeth)
        if not tooth:
            continue
        fdi = tooth.get("fdi")
        if gray is None:
            continue
        root = tooth_root_bbox(tooth); stats_root = patch_stats(gray, root); stats_center = None
        if root:
            x1,y1,x2,y2 = map(float,root); center=[x1+(x2-x1)*0.3,y1,x2-(x2-x1)*0.3,y2]
            stats_center=patch_stats(gray,center)
        if stats_root and stats_center and stats_center.get("dark_fraction",0) > stats_root.get("dark_fraction",0)*1.15:
            out.append(_finding("INTERNAL_ROOT_RESORPTION", max(0.44,res.get("confidence",0)*0.85), bbox=res.get("bbox") or root, fdi=fdi, evidence=["ROOT_RESORPTION_GENERIC", "central_lumen_pattern"]))
        else:
            out.append(_finding("EXTERNAL_ROOT_RESORPTION", max(0.42,res.get("confidence",0)*0.80), bbox=res.get("bbox") or root, fdi=fdi, evidence=["ROOT_RESORPTION_GENERIC", "external_contour_pattern"]))

    # 32 — direct helper may already be normalized by yolo31; no duplicate synthesis required.

    # 34-36 — jaw lesions from helper regions and local density.
    radiolucent_candidates = _helpers(helpers,"CYST_HELPER") + _helpers(helpers,"BONE_DEFECT_HELPER")
    for h in radiolucent_candidates:
        out.append(_finding("JAW_RADIOLUCENT_LESION", max(0.42,h.get("confidence",0)), bbox=h.get("bbox"), evidence=[h.get("signal")]))
    # A large bright helper-less jaw lesion candidate is intentionally conservative.
    for dark in _by_code(out,"JAW_RADIOLUCENT_LESION"):
        if gray is not None and dark.get("bbox"):
            st=patch_stats(gray,expand_bbox(dark["bbox"],0.35))
            if st and st.get("p90",0)-st.get("p10",0)>125 and st.get("bright_fraction",0)>0.12:
                bright=_finding("JAW_RADIOPAQUE_LESION",0.42,bbox=expand_bbox(dark["bbox"],0.2),evidence=["large_non_tooth_bright_component"])
                out.append(bright)
                out.append(_finding("MIXED_DENSITY_JAW_LESION",0.44,bbox=expand_bbox(dark["bbox"],0.2),evidence=["radiolucent_and_radiopaque_components"]))

    # 37-39 — classify generic bone-loss geometry.
    for bl in _helpers(helpers, "BONE_LOSS_GENERIC"):
        b=bl.get("bbox") or []; fdi=None; tooth=_nearest_tooth(b,teeth) if b else None
        if tooth: fdi=tooth.get("fdi")
        if len(b)==4:
            w=max(1.0,b[2]-b[0]); h=max(1.0,b[3]-b[1]); ratio=w/h
            if ratio>=1.7:
                out.append(_finding("HORIZONTAL_BONE_LOSS",max(0.45,bl.get("confidence",0)*0.85),bbox=b,fdi=fdi,evidence=["BONE_LOSS_GENERIC","wide_crest_geometry"],measurement={"width_height_ratio":round(ratio,2)}))
            else:
                out.append(_finding("VERTICAL_BONE_LOSS",max(0.43,bl.get("confidence",0)*0.82),bbox=b,fdi=fdi,evidence=["BONE_LOSS_GENERIC","localized_angular_geometry"],measurement={"width_height_ratio":round(ratio,2)}))
            if fdi and str(fdi)[-1:] in {"6","7","8"} and ratio < 1.8:
                out.append(_finding("FURCATION_BONE_LOSS",max(0.41,bl.get("confidence",0)*0.78),bbox=b,fdi=fdi,evidence=["BONE_LOSS_GENERIC","molar_furcation_region"]))

    # 40 — calculus: small bright cervical/interproximal spur.
    if gray is not None:
        for tooth in teeth:
            crown=tooth_crown_bbox(tooth)
            if not crown: continue
            st=patch_stats(gray,expand_bbox(crown,0.12))
            if st and 0.006 <= st.get("bright_fraction",0) <= 0.07 and st.get("p90",0) >= 180:
                out.append(_finding("CALCULUS",0.40,bbox=expand_bbox(crown,0.08),fdi=tooth.get("fdi"),evidence=["cervical_radiopaque_spur"]))

    # 41 — peri-implant bone loss.
    for imp in _by_code(findings,"IMPLANT"):
        for bl in _helpers(helpers,"BONE_LOSS_GENERIC"):
            if bbox_iou(expand_bbox(imp.get("bbox"),0.25),bl.get("bbox"))>0.04 or bbox_distance(imp.get("bbox"),bl.get("bbox"))<=8:
                out.append(_finding("PERI_IMPLANT_BONE_LOSS",min(0.92,(imp.get("confidence",0)+bl.get("confidence",0))/2),bbox=bl.get("bbox"),fdi=imp.get("fdi"),evidence=["IMPLANT","BONE_LOSS_GENERIC"]))

    # 42-44 — sinus opacity/mucosal band and mandibular canal distance.
    for sinus in _helpers(helpers,"MAXILLARY_SINUS_HELPER"):
        if gray is None or not sinus.get("bbox"): continue
        st=patch_stats(gray,sinus.get("bbox"))
        if not st: continue
        if st.get("mean",0)>=105 and st.get("bright_fraction",0)>=0.08:
            out.append(_finding("MAXILLARY_SINUS_OPACIFICATION",0.44+min(0.18,st.get("bright_fraction",0)),bbox=sinus.get("bbox"),evidence=["MAXILLARY_SINUS_HELPER","high_opacity_fraction"],measurement={"mean_intensity":round(st.get("mean",0),1)}))
        if st.get("std",0)>=28 and st.get("mean",0)>=80:
            out.append(_finding("MAXILLARY_SINUS_MUCOSAL_THICKENING",0.43,bbox=sinus.get("bbox"),evidence=["MAXILLARY_SINUS_HELPER","basal_band_texture"]))

    for canal in _helpers(helpers,"MANDIBULAR_CANAL_HELPER"):
        b=canal.get("bbox") or []
        if len(b)!=4: continue
        nearest=None; best=float("inf")
        for tooth in teeth:
            fdi=str(tooth.get("fdi") or "")
            if fdi[:1] not in {"3","4"}: continue
            d=bbox_distance(b,tooth.get("bbox"))
            if d<best: best=d; nearest=tooth
        if nearest:
            width=max(1.0,float(nearest["bbox"][2])-float(nearest["bbox"][0])); normalized=best/width
            if normalized<=0.65:
                conf=max(0.42,min(0.94,1.0-normalized*0.65))
                out.append(_finding("MANDIBULAR_CANAL_PROXIMITY",conf,bbox=b,fdi=nearest.get("fdi"),evidence=["MANDIBULAR_CANAL_HELPER","root_canal_distance"],measurement={"pixel_distance":round(best,1),"tooth_width_ratio":round(normalized,3)}))

    # 45-47 — bilateral condylar morphology.
    if gray is not None:
        cs=condyle_signals(gray)
        for side in ("left","right"):
            s=cs.get(side) or {}
            if s.get("area",0)>0:
                if s.get("flatness",0)>=0.34:
                    out.append(_finding("CONDYLAR_FLATTENING",0.42+min(0.20,s["flatness"]*0.25),bbox=s.get("bbox"),evidence=[f"{side}_condyle","superior_contour_flatness"],measurement={"flatness_score":round(s["flatness"],3)}))
                if s.get("roughness",0)>=0.72:
                    out.append(_finding("CONDYLAR_EROSION",0.41+min(0.18,(s["roughness"]-0.7)*0.4),bbox=s.get("bbox"),evidence=[f"{side}_condyle","contour_irregularity"],measurement={"roughness_score":round(s["roughness"],3)}))
        if cs.get("asymmetry",0)>=0.25:
            out.append(_finding("CONDYLAR_ASYMMETRY",0.43+min(0.22,cs["asymmetry"]*0.3),evidence=["bilateral_condyle_shape_comparison"],measurement={"asymmetry_score":round(cs["asymmetry"],3)}))

    # 48 — union of orthodontic hardware helpers.
    for h in _helpers(helpers,"ORTHODONTIC_APPLIANCE_HELPER"):
        out.append(_finding("ORTHODONTIC_APPLIANCE",max(0.45,h.get("confidence",0)),bbox=h.get("bbox"),evidence=[h.get("raw_class") or h.get("signal")]))

    # Dedupe derived findings by code + FDI + coarse bbox center, retain strongest.
    best={}
    for item in out:
        b=item.get("bbox") or [0,0,0,0]; center=(round((b[0]+b[2])/20) if len(b)==4 else 0,round((b[1]+b[3])/20) if len(b)==4 else 0)
        key=(item.get("finding_code"),str(item.get("fdi") or ""),center)
        if key not in best or item.get("confidence",0)>best[key].get("confidence",0): best[key]=item
    return list(best.values())
