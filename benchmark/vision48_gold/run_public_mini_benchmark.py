from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import urllib.request
from collections import defaultdict
from pathlib import Path

TARGETS = {
    "FILLING": {"status": {1}},
    "ROOT_CANAL_TREATED": {"status": {2, 6}},
    "CROWN": {"status": {3, 6}},
    "CARIES": {"status": {4}},
    "RESIDUAL_ROOT": {"status": {5}},
    "SUPERNUMERARY_TOOTH": {"fdi": {91}},
}

FINDINGS9_RAW_TO_CODE = {
    "Apical Periodontitis": "PERIAPICAL_RADIOLUCENCY",
    "Decay": "CARIES",
    "Missing Tooth": "MISSING_TOOTH",
    "Dental Filling": "FILLING",
    "Root Canal Filling": "ROOT_CANAL_TREATED",
    "Implant": "IMPLANT",
    "Porcelain Crown": "CROWN",
    "Ceramic Bridge": "BRIDGE",
}

FINDINGS9_URL = "https://github.com/dentalaidestek/dental-ai-v02/releases/download/vision-findings9-v1/YOLO26_Dental_Findings_9.pt"
FINDINGS9_SHA = "8070505857f354aae4f18bf621b9b79f0e3b48a2904e44f57a2bc598ed692849"
FDI_URL = "https://github.com/dentalaidestek/dental-ai-v02/releases/download/vision-model-v1/YOLOv11x-seg.pt"
FDI_SHA = "2d0c07b878e9f9730eb845a901e85abf3535d49cf4034d2246592f76201ac8af"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, expected_sha: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and sha256(dest) == expected_sha:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "Vision48-Gold-Benchmark"})
    with urllib.request.urlopen(req, timeout=600) as r, dest.open("wb") as out:
        shutil.copyfileobj(r, out)
    got = sha256(dest)
    if got != expected_sha:
        raise RuntimeError(f"SHA mismatch for {dest.name}: {got}")


def norm_stem(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", Path(value).stem.lower())


def bbox_from_points(points):
    if not points:
        return None
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def center(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def box_iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    aa = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    bb = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    den = aa + bb - inter
    return inter / den if den else 0.0


def ints_in(value) -> list[int]:
    if value is None:
        return []
    return [int(x) for x in re.findall(r"(?<!\d)\d{1,2}(?!\d)", str(value))]


def parse_shape(shape: dict, source_path: Path) -> dict:
    label = str(shape.get("label", ""))
    desc = str(shape.get("description", ""))
    blob = " ".join([label, desc, json.dumps(shape.get("flags", {}), ensure_ascii=False), json.dumps(shape.get("attributes", {}), ensure_ascii=False)])
    vals = ints_in(blob)
    lower_path = str(source_path).lower()
    fdi = next((v for v in vals if v == 91 or (11 <= v <= 48 and v % 10 in range(1, 9))), None)
    status = None
    # If two values are embedded in one label, prefer the non-FDI 0..6 value.
    for v in vals:
        if 0 <= v <= 6 and v != fdi:
            status = v
            break
    # Some releases keep state and numbering annotations in separate folders/files.
    if status is None and any(k in lower_path for k in ("state", "status", "condition")):
        status = next((v for v in vals if 0 <= v <= 6), None)
    if fdi is None and any(k in lower_path for k in ("number", "fdi", "seg")):
        fdi = next((v for v in vals if v == 91 or (11 <= v <= 48 and v % 10 in range(1, 9))), None)
    return {
        "label": label,
        "fdi": fdi,
        "status": status,
        "bbox": bbox_from_points(shape.get("points") or []),
    }


def discover_dataset(root: Path, outdir: Path):
    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    images = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in image_exts]
    jsons = [p for p in root.rglob("*.json") if p.is_file()]
    by_stem = defaultdict(list)
    for p in images:
        by_stem[norm_stem(p.name)].append(p)

    raw_records = defaultdict(list)
    probe = {"root": str(root), "image_count": len(images), "json_count": len(jsons), "sample_jsons": [], "sample_labels": []}
    for jp in jsons:
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue
        shapes = data.get("shapes") if isinstance(data, dict) else None
        if not isinstance(shapes, list):
            continue
        image_path = data.get("imagePath") or ""
        stem = norm_stem(image_path or jp.name)
        if len(probe["sample_jsons"]) < 8:
            probe["sample_jsons"].append({"path": str(jp.relative_to(root)), "imagePath": image_path, "keys": sorted(data.keys()), "shape_count": len(shapes)})
        for sh in shapes:
            rec = parse_shape(sh, jp)
            if len(probe["sample_labels"]) < 60:
                probe["sample_labels"].append({"path": str(jp.relative_to(root)), **rec})
            if rec["bbox"]:
                raw_records[stem].append(rec)

    # Pair with image files and combine duplicate/parallel annotations spatially.
    records = []
    for stem, shapes in raw_records.items():
        candidates = by_stem.get(stem) or []
        if not candidates:
            # relaxed match if JSON imagePath is decorated differently
            candidates = [p for k, vals in by_stem.items() if k.endswith(stem) or stem.endswith(k) for p in vals]
        if not candidates:
            continue
        image = candidates[0]
        # Merge spatially overlapping FDI-only and status-only annotations.
        merged = []
        for s in shapes:
            attached = False
            for m in merged:
                if box_iou(s["bbox"], m["bbox"]) >= 0.70:
                    if m.get("fdi") is None and s.get("fdi") is not None:
                        m["fdi"] = s["fdi"]
                    if m.get("status") is None and s.get("status") is not None:
                        m["status"] = s["status"]
                    attached = True
                    break
            if not attached:
                merged.append(dict(s))
        records.append({"image_id": stem, "image_path": str(image), "teeth": merged})

    # A few releases may store labels in txt instead of LabelMe JSON. If no usable
    # JSON records are found we deliberately stop rather than invent semantics.
    probe["matched_record_count"] = len(records)
    probe["records_with_status"] = sum(any(t.get("status") is not None for t in r["teeth"]) for r in records)
    probe["records_with_fdi"] = sum(any(t.get("fdi") is not None for t in r["teeth"]) for r in records)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "dataset_probe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def positives_for(record, code: str) -> bool:
    rule = TARGETS[code]
    if "status" in rule:
        return any(t.get("status") in rule["status"] for t in record["teeth"])
    return any(t.get("fdi") in rule["fdi"] for t in record["teeth"])


def has_exhaustive_status(record) -> bool:
    labeled = [t for t in record["teeth"] if t.get("status") is not None]
    return len(labeled) >= 8


def has_exhaustive_fdi(record) -> bool:
    labeled = [t for t in record["teeth"] if t.get("fdi") is not None]
    return len(labeled) >= 8


def locked_sample(records, code: str, n=15):
    positives = [r for r in records if positives_for(r, code)]
    if "status" in TARGETS[code]:
        negatives = [r for r in records if has_exhaustive_status(r) and not positives_for(r, code)]
    else:
        negatives = [r for r in records if has_exhaustive_fdi(r) and not positives_for(r, code)]
    rng = random.Random(f"vision48-gold-v1::{code}")
    rng.shuffle(positives); rng.shuffle(negatives)
    return positives[:n], negatives[:n], len(positives), len(negatives)


def cls_name(names, idx: int) -> str:
    if isinstance(names, dict):
        return str(names.get(idx, idx))
    return str(names[idx])


def predict_findings9(model, image_paths: list[str]):
    cache = {}
    if not image_paths:
        return cache
    results = model.predict(source=image_paths, imgsz=1280, conf=0.10, iou=0.45, verbose=False, stream=False)
    for path, res in zip(image_paths, results):
        codes = []
        if res.boxes is not None:
            confs = res.boxes.conf.detach().cpu().tolist()
            classes = res.boxes.cls.detach().cpu().tolist()
            for c, k in zip(confs, classes):
                raw = cls_name(res.names, int(k))
                code = FINDINGS9_RAW_TO_CODE.get(raw)
                if code:
                    codes.append({"finding_code": code, "confidence": float(c), "raw_class": raw})
        cache[path] = codes
    return cache


def predict_fdi91(model, image_paths: list[str]):
    cache = {}
    if not image_paths:
        return cache
    results = model.predict(source=image_paths, imgsz=1280, conf=0.10, iou=0.45, verbose=False, stream=False)
    for path, res in zip(image_paths, results):
        hits = []
        if res.boxes is not None:
            confs = res.boxes.conf.detach().cpu().tolist()
            classes = res.boxes.cls.detach().cpu().tolist()
            for c, k in zip(confs, classes):
                raw = cls_name(res.names, int(k)).strip()
                # Raw-model readout. The production parser currently accepts only 11..48.
                nums = ints_in(raw)
                if 91 in nums:
                    hits.append({"confidence": float(c), "raw_class": raw})
        cache[path] = hits
    return cache


def metrics(y_true, y_pred):
    tp = sum(t and p for t, p in zip(y_true, y_pred))
    tn = sum((not t) and (not p) for t, p in zip(y_true, y_pred))
    fp = sum((not t) and p for t, p in zip(y_true, y_pred))
    fn = sum(t and (not p) for t, p in zip(y_true, y_pred))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "specificity": specificity, "f1": f1}


def grade(m):
    if not m or m.get("recall") is None or m.get("specificity") is None:
        return "UNMEASURED"
    r, s = m["recall"], m["specificity"]
    if r >= 0.80 and s >= 0.80:
        return "STRONG_MINI"
    if r >= 0.60 and s >= 0.70:
        return "MEDIUM_MINI"
    return "WEAK_MINI"


def main():
    ap = argparse.ArgumentParser(description="Public evaluation-only Vision48 15+/15- mini benchmark. Never trains models.")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    outdir = args.output
    outdir.mkdir(parents=True, exist_ok=True)

    import kagglehub
    print("Downloading public dual-labeled dataset...")
    dataset_root = Path(kagglehub.dataset_download("zwbzwb12341234/a-dual-labeled-dataset"))
    records = discover_dataset(dataset_root, outdir)
    if not records:
        raise RuntimeError("No usable image/LabelMe record pairs found. See dataset_probe.json")

    selections = {}
    selected_paths = set()
    for code in TARGETS:
        pos, neg, available_pos, available_neg = locked_sample(records, code, 15)
        selections[code] = {
            "available_positive_images": available_pos,
            "available_negative_images": available_neg,
            "positive": [r["image_path"] for r in pos],
            "negative": [r["image_path"] for r in neg],
        }
        selected_paths.update(selections[code]["positive"])
        selected_paths.update(selections[code]["negative"])
    (outdir / "locked_selection.json").write_text(json.dumps(selections, ensure_ascii=False, indent=2), encoding="utf-8")

    # Test data must remain evaluation-only. We record only source-local paths and IDs,
    # not images, in GitHub artifacts.
    model_dir = Path(".benchmark-models")
    findings9_path = model_dir / "YOLO26_Dental_Findings_9.pt"
    fdi_path = model_dir / "YOLOv11x-seg.pt"
    download(FINDINGS9_URL, findings9_path, FINDINGS9_SHA)
    download(FDI_URL, fdi_path, FDI_SHA)

    from ultralytics import YOLO
    findings9 = YOLO(str(findings9_path))

    finding_targets = {"FILLING", "ROOT_CANAL_TREATED", "CROWN", "CARIES"}
    finding_paths = sorted({p for code in finding_targets for p in selections[code]["positive"] + selections[code]["negative"]})
    print(f"findings9 unique images: {len(finding_paths)}")
    pred_findings = predict_findings9(findings9, finding_paths)

    report = {
        "protocol": "Vision48 Gold Mini v1: fixed 15 positive + 15 negative per finding when available; image-level screening; confidence >= 0.50; no training",
        "source": "zwbzwb12341234/a-dual-labeled-dataset",
        "confidence_threshold": 0.50,
        "metrics": {},
    }

    for code in sorted(finding_targets):
        sel = selections[code]
        cases = [(p, True) for p in sel["positive"]] + [(p, False) for p in sel["negative"]]
        y_true, y_pred = [], []
        for p, truth in cases:
            pred = any(x["finding_code"] == code and x["confidence"] >= 0.50 for x in pred_findings.get(p, []))
            y_true.append(truth); y_pred.append(pred)
        m = metrics(y_true, y_pred)
        report["metrics"][code] = {
            "n_positive": len(sel["positive"]), "n_negative": len(sel["negative"]),
            "available_positive_images": sel["available_positive_images"],
            "available_negative_images": sel["available_negative_images"],
            **m, "grade": grade(m), "motor": "findings9",
        }

    # Residual root is deliberately not fabricated: the currently pinned findings9
    # motor has no residual-root output class.
    report["metrics"]["RESIDUAL_ROOT"] = {
        "n_positive": len(selections["RESIDUAL_ROOT"]["positive"]),
        "n_negative": len(selections["RESIDUAL_ROOT"]["negative"]),
        "available_positive_images": selections["RESIDUAL_ROOT"]["available_positive_images"],
        "available_negative_images": selections["RESIDUAL_ROOT"]["available_negative_images"],
        "grade": "UNMEASURED_CURRENT_PINNED_MOTOR_HAS_NO_CLASS",
        "motor": "findings9",
    }

    # Supernumerary: inspect raw FDI model and report the system-level parser gap separately.
    super_sel = selections["SUPERNUMERARY_TOOTH"]
    super_paths = sorted(set(super_sel["positive"] + super_sel["negative"]))
    fdi_model = YOLO(str(fdi_path))
    raw91 = predict_fdi91(fdi_model, super_paths)
    y_true, y_raw = [], []
    for p in super_sel["positive"]:
        y_true.append(True); y_raw.append(any(h["confidence"] >= 0.50 for h in raw91.get(p, [])))
    for p in super_sel["negative"]:
        y_true.append(False); y_raw.append(any(h["confidence"] >= 0.50 for h in raw91.get(p, [])))
    raw_m = metrics(y_true, y_raw)
    report["metrics"]["SUPERNUMERARY_TOOTH"] = {
        "n_positive": len(super_sel["positive"]), "n_negative": len(super_sel["negative"]),
        "available_positive_images": super_sel["available_positive_images"],
        "available_negative_images": super_sel["available_negative_images"],
        "raw_fdi_model": {**raw_m, "grade": grade(raw_m)},
        "production_parser_accepts_fdi_91": False,
        "production_grade": "WEAK_MINI_PARSER_BLOCKS_91" if len(super_sel["positive"]) else "UNMEASURED",
        "motor": "motor1_fdi",
    }

    (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_lines = ["# Vision48 public mini benchmark", "", "Evaluation only — no training.", "", "| Finding | + | - | Recall | Specificity | F1 | Grade |", "|---|---:|---:|---:|---:|---:|---|"]
    for code, m in report["metrics"].items():
        if code == "SUPERNUMERARY_TOOTH":
            mm = m.get("raw_fdi_model", {})
            summary_lines.append(f"| {code} (raw FDI; production blocks 91) | {m['n_positive']} | {m['n_negative']} | {fmt(mm.get('recall'))} | {fmt(mm.get('specificity'))} | {fmt(mm.get('f1'))} | {m['production_grade']} |")
        else:
            summary_lines.append(f"| {code} | {m.get('n_positive',0)} | {m.get('n_negative',0)} | {fmt(m.get('recall'))} | {fmt(m.get('specificity'))} | {fmt(m.get('f1'))} | {m.get('grade')} |")
    (outdir / "SUMMARY.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def fmt(v):
    return "—" if v is None else f"{v:.2f}"


if __name__ == "__main__":
    main()
