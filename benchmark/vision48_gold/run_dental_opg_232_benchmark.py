from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

DATASET = "imtkaggleteam/dental-opg-xray-dataset"
TARGETS = ("CARIES", "IMPACTED_TOOTH", "TOOTH_FRACTURE")
CONF = 0.50

FINDINGS9_URL = "https://github.com/dentalaidestek/dental-ai-v02/releases/download/vision-findings9-v1/YOLO26_Dental_Findings_9.pt"
FINDINGS9_SHA = "8070505857f354aae4f18bf621b9b79f0e3b48a2904e44f57a2bc598ed692849"
IMPACTED_URL = "https://github.com/dentalaidestek/dental-ai-v02/releases/download/vision-impacted-v1/OralGuard_Impacted.pt"
IMPACTED_SHA = "c3303656e72ede3f3d3229e58b2da276448fa204046d3e7a11e13f4d77bc723a"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, expected: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and sha256(dest) == expected:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "Vision48-Gold-Benchmark"})
    with urllib.request.urlopen(req, timeout=600) as r, dest.open("wb") as out:
        shutil.copyfileobj(r, out)
    got = sha256(dest)
    if got != expected:
        raise RuntimeError(f"SHA mismatch for {dest.name}: {got}")


def norm_text(value: object) -> str:
    s = str(value or "").casefold().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


def map_label(raw: object) -> str | None:
    s = norm_text(raw)
    if not s:
        return None
    if "caries" in s or "decay" in s:
        return "CARIES"
    if "impacted" in s:
        return "IMPACTED_TOOTH"
    if "fractur" in s and ("tooth" in s or "teeth" in s or s in {"fracture", "fractured"}):
        return "TOOTH_FRACTURE"
    return None


def labels_from_json(data: object) -> set[str]:
    """Read per-image CVAT/LabelMe-like JSON conservatively.

    We only consume label-like fields attached to an annotation object. We do not
    treat top-level category dictionaries as image findings because that would mark
    every class positive in COCO-style metadata.
    """
    found: set[str] = set()
    label_keys = {"label", "class", "class_name", "classname", "category", "category_name", "name"}

    def walk(obj: object, annotation_context: bool = False) -> None:
        if isinstance(obj, list):
            for item in obj:
                walk(item, annotation_context=annotation_context)
            return
        if not isinstance(obj, dict):
            return

        # Containers commonly used for actual per-image annotations.
        ann_keys = {"shapes", "objects", "annotations", "boxes", "regions", "items"}
        local_annotation = annotation_context or any(k in obj for k in ann_keys)

        if local_annotation:
            for key, value in obj.items():
                if key.casefold() in label_keys and isinstance(value, (str, int, float)):
                    code = map_label(value)
                    if code:
                        found.add(code)

        for key, value in obj.items():
            k = key.casefold()
            if k in {"categories", "classes", "labelmap", "label_map"} and not annotation_context:
                # Definitions, not image observations.
                continue
            walk(value, annotation_context=local_annotation or k in ann_keys)

    walk(data)
    return found


def norm_stem(p: Path | str) -> str:
    return re.sub(r"[^a-z0-9]+", "", Path(str(p)).stem.casefold())


def is_original_candidate(path: Path) -> bool:
    s = str(path).casefold()
    # Explicit augmented/split trees are never gold.
    blocked = ("augmented", "/train/", "\\train\\", "/valid/", "\\valid\\", "/test/", "\\test\\")
    if any(x in s for x in blocked):
        return False
    # Ignore classification copies; benchmark uses object-detection annotations.
    if "classification" in s:
        return False
    return True


def discover_records(root: Path, outdir: Path) -> list[dict]:
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    images = [p for p in root.rglob("*") if p.is_file() and p.suffix.casefold() in image_exts and is_original_candidate(p)]
    jsons = [p for p in root.rglob("*.json") if p.is_file() and is_original_candidate(p)]

    by_stem: dict[str, list[Path]] = defaultdict(list)
    for p in images:
        by_stem[norm_stem(p)].append(p)

    records: list[dict] = []
    sample_jsons = []
    raw_label_counts = Counter()
    for jp in jsons:
        try:
            data = json.loads(jp.read_text(encoding="utf-8-sig"))
        except Exception:
            continue

        # Prefer image filename/path stated by the annotation file when present.
        image_hint = ""
        if isinstance(data, dict):
            image_hint = str(data.get("imagePath") or data.get("image") or data.get("filename") or data.get("file_name") or "")
        stem = norm_stem(image_hint or jp.name)
        candidates = by_stem.get(stem, [])
        if not candidates:
            # Some labels append suffixes such as _json; allow a conservative stem containment match.
            candidates = [p for k, vals in by_stem.items() if len(stem) >= 4 and (k.endswith(stem) or stem.endswith(k)) for p in vals]
        if not candidates:
            continue

        labels = labels_from_json(data)
        for x in labels:
            raw_label_counts[x] += 1
        if len(sample_jsons) < 12:
            sample_jsons.append({"json": str(jp.relative_to(root)), "image": str(candidates[0].relative_to(root)), "labels": sorted(labels)})
        records.append({
            "image_id": norm_stem(candidates[0]),
            "image_path": str(candidates[0]),
            "annotation_path": str(jp),
            "labels": sorted(labels),
        })

    # Deduplicate repeated label files pointing to the same original image.
    merged: dict[str, dict] = {}
    for r in records:
        if r["image_id"] not in merged:
            merged[r["image_id"]] = dict(r)
        else:
            merged[r["image_id"]]["labels"] = sorted(set(merged[r["image_id"]]["labels"]) | set(r["labels"]))
    records = list(merged.values())

    probe = {
        "dataset_root": str(root),
        "original_candidate_images": len(images),
        "original_candidate_json": len(jsons),
        "paired_records": len(records),
        "mapped_label_image_counts": dict(raw_label_counts),
        "sample_pairs": sample_jsons,
        "note": "augmented/train/valid/test/classification paths excluded from gold selection",
    }
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "dataset_probe.json").write_text(json.dumps(probe, indent=2, ensure_ascii=False), encoding="utf-8")
    return records


def locked_sample(records: list[dict], code: str, n_pos: int = 15, n_neg: int = 15):
    positives = [r for r in records if code in r["labels"]]
    negatives = [r for r in records if code not in r["labels"]]
    rng = random.Random(f"vision48-gold-opg232-v1::{code}")
    rng.shuffle(positives); rng.shuffle(negatives)
    return positives[:n_pos], negatives[:n_neg], len(positives), len(negatives)


def name_for(names, idx: int) -> str:
    if isinstance(names, dict):
        return str(names.get(idx, idx))
    return str(names[idx])


def predict_ultralytics(model, paths: list[str], mode: str) -> dict[str, list[dict]]:
    from vision_service.motors.findings9 import normalize_class as norm_findings9
    from vision_service.motors.impacted_tooth import normalize_class as norm_impacted
    from vision_service.motors.yolo31 import normalize_class as norm_yolo31

    out = {p: [] for p in paths}
    if not paths:
        return out
    results = model.predict(source=paths, imgsz=1280, conf=0.10, iou=0.45, verbose=False, stream=False)
    for p, res in zip(paths, results):
        count = len(res.names) if hasattr(res.names, "__len__") else None
        if res.boxes is None:
            continue
        for conf, cls in zip(res.boxes.conf.detach().cpu().tolist(), res.boxes.cls.detach().cpu().tolist()):
            raw = name_for(res.names, int(cls))
            if mode == "findings9":
                mapped = norm_findings9(raw, class_count=count)
            elif mode == "impacted":
                mapped = norm_impacted(raw, class_count=count)
            else:
                mapped = norm_yolo31(raw, class_count=count)
            if mapped.get("type") == "finding":
                out[p].append({"finding_code": mapped.get("finding_code"), "confidence": float(conf), "raw_class": raw})
    return out


def metrics(y_true: list[bool], y_pred: list[bool]) -> dict:
    tp = sum(t and p for t, p in zip(y_true, y_pred))
    tn = sum((not t) and (not p) for t, p in zip(y_true, y_pred))
    fp = sum((not t) and p for t, p in zip(y_true, y_pred))
    fn = sum(t and (not p) for t, p in zip(y_true, y_pred))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "specificity": specificity, "f1": f1}


def grade(m: dict) -> str:
    if m.get("recall") is None or m.get("specificity") is None:
        return "UNMEASURED"
    if m["recall"] >= 0.80 and m["specificity"] >= 0.80:
        return "STRONG_MINI"
    if m["recall"] >= 0.60 and m["specificity"] >= 0.70:
        return "MEDIUM_MINI"
    return "WEAK_MINI"


def fmt(v) -> str:
    return "—" if v is None else f"{100*v:.0f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    outdir = args.output
    outdir.mkdir(parents=True, exist_ok=True)

    import kagglehub
    print(f"Downloading {DATASET}...")
    root = Path(kagglehub.dataset_download(DATASET))
    records = discover_records(root, outdir)
    if not records:
        raise RuntimeError("No original image/JSON pairs could be parsed; inspect dataset_probe.json")

    selections = {}
    all_paths: set[str] = set()
    for code in TARGETS:
        pos, neg, avail_pos, avail_neg = locked_sample(records, code)
        selections[code] = {
            "available_positive": avail_pos,
            "available_negative": avail_neg,
            "positive": [r["image_path"] for r in pos],
            "negative": [r["image_path"] for r in neg],
        }
        all_paths.update(selections[code]["positive"] + selections[code]["negative"])
    (outdir / "locked_selection.json").write_text(json.dumps(selections, indent=2, ensure_ascii=False), encoding="utf-8")

    model_dir = Path(".benchmark-models")
    f9 = model_dir / "YOLO26_Dental_Findings_9.pt"
    impacted = model_dir / "OralGuard_Impacted.pt"
    download(FINDINGS9_URL, f9, FINDINGS9_SHA)
    download(IMPACTED_URL, impacted, IMPACTED_SHA)

    from ultralytics import YOLO
    pred_by_code: dict[str, dict[str, list[dict]]] = {}
    paths = sorted(all_paths)
    pred_by_code["CARIES"] = predict_ultralytics(YOLO(str(f9)), paths, "findings9")
    pred_by_code["IMPACTED_TOOTH"] = predict_ultralytics(YOLO(str(impacted)), paths, "impacted")

    fracture_model_status = "not_available"
    try:
        from vision_service.fetch_optional_models import fetch_one
        y31_path = fetch_one("yolo31")
        pred_by_code["TOOTH_FRACTURE"] = predict_ultralytics(YOLO(str(y31_path)), paths, "yolo31")
        fracture_model_status = "ok"
    except Exception as exc:
        pred_by_code["TOOTH_FRACTURE"] = {p: [] for p in paths}
        fracture_model_status = f"error:{type(exc).__name__}:{exc}"

    report = {
        "protocol": "Vision48 Dental OPG 232 mini v1; original images only; locked up to 15 positive + 15 negative; image-level; confidence >= 0.50; no training",
        "source": DATASET,
        "confidence_threshold": CONF,
        "fracture_model_status": fracture_model_status,
        "metrics": {},
    }
    for code in TARGETS:
        sel = selections[code]
        cases = [(p, True) for p in sel["positive"]] + [(p, False) for p in sel["negative"]]
        if code == "TOOTH_FRACTURE" and fracture_model_status != "ok":
            report["metrics"][code] = {
                "n_positive": len(sel["positive"]), "n_negative": len(sel["negative"]),
                "available_positive": sel["available_positive"], "available_negative": sel["available_negative"],
                "grade": "UNMEASURED_MODEL_UNAVAILABLE", "motor": "yolo31",
            }
            continue
        y_true, y_pred = [], []
        for path, truth in cases:
            detected = any(
                x.get("finding_code") == code and float(x.get("confidence", 0.0)) >= CONF
                for x in pred_by_code[code].get(path, [])
            )
            y_true.append(truth); y_pred.append(detected)
        m = metrics(y_true, y_pred)
        report["metrics"][code] = {
            "n_positive": len(sel["positive"]), "n_negative": len(sel["negative"]),
            "available_positive": sel["available_positive"], "available_negative": sel["available_negative"],
            **m, "grade": grade(m),
            "motor": {"CARIES": "findings9", "IMPACTED_TOOTH": "impacted_tooth", "TOOTH_FRACTURE": "yolo31"}[code],
        }

    (outdir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Dental OPG 232 — Vision48 mini benchmark",
        "",
        "Original panoramics only. Augmented copies are excluded. Evaluation only — no training.",
        "",
        "| Finding | + | - | TP | TN | FP | FN | Recall | Specificity | F1 | Grade |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for code in TARGETS:
        m = report["metrics"][code]
        lines.append(
            f"| {code} | {m.get('n_positive',0)} | {m.get('n_negative',0)} | {m.get('tp','—')} | {m.get('tn','—')} | {m.get('fp','—')} | {m.get('fn','—')} | {fmt(m.get('recall'))} | {fmt(m.get('specificity'))} | {fmt(m.get('f1'))} | {m.get('grade')} |"
        )
    if selections["TOOTH_FRACTURE"]["available_positive"] < 15:
        lines += ["", f"Note: TOOTH_FRACTURE has only {selections['TOOTH_FRACTURE']['available_positive']} mapped positive original images in this release, so all available positives are used instead of inventing 15."]
    (outdir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
