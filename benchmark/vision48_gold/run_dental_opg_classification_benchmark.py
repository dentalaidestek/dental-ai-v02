from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import urllib.request
from collections import defaultdict
from pathlib import Path

DATASET = "imtkaggleteam/dental-opg-xray-dataset"
CONF = 0.50
TARGETS = ("CARIES", "IMPACTED_TOOTH", "TOOTH_FRACTURE")

FINDINGS9_URL = "https://github.com/dentalaidestek/dental-ai-v02/releases/download/vision-findings9-v1/YOLO26_Dental_Findings_9.pt"
FINDINGS9_SHA = "8070505857f354aae4f18bf621b9b79f0e3b48a2904e44f57a2bc598ed692849"
IMPACTED_URL = "https://github.com/dentalaidestek/dental-ai-v02/releases/download/vision-impacted-v1/OralGuard_Impacted.pt"
IMPACTED_SHA = "c3303656e72ede3f3d3229e58b2da276448fa204046d3e7a11e13f4d77bc723a"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, expected: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and _sha256(dest) == expected:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "Vision48-Gold-Benchmark"})
    with urllib.request.urlopen(req, timeout=600) as r, dest.open("wb") as out:
        shutil.copyfileobj(r, out)
    got = _sha256(dest)
    if got != expected:
        raise RuntimeError(f"SHA mismatch for {dest.name}: {got}")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).casefold()).strip()


def _classify_path(path: Path) -> str | None:
    s = _norm(str(path))
    if "classification" not in s:
        return None
    if "caries" in s:
        return "CARIES"
    if "impacted" in s:
        return "IMPACTED_TOOTH"
    if "fractur" in s:
        return "TOOTH_FRACTURE"
    if "healthy" in s:
        return "HEALTHY"
    if "infection" in s:
        return "INFECTION"
    if "broken" in s or "bdc" in s or "bdr" in s:
        return "BROKEN_DOWN"
    return None


def discover_classification(root: Path, outdir: Path) -> dict[str, list[str]]:
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    buckets: dict[str, list[str]] = defaultdict(list)
    samples = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.casefold() not in exts:
            continue
        cls = _classify_path(p)
        if cls:
            buckets[cls].append(str(p))
            if len(samples) < 80:
                samples.append({"class": cls, "path": str(p.relative_to(root))})
    probe = {
        "dataset_root": str(root),
        "classification_counts": {k: len(v) for k, v in sorted(buckets.items())},
        "sample_paths": samples,
        "note": "Classification folders only; augmented object-detection train/valid/test trees are not used here.",
    }
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "classification_probe.json").write_text(json.dumps(probe, indent=2, ensure_ascii=False), encoding="utf-8")
    return buckets


def _locked(paths: list[str], seed: str, n: int = 15) -> list[str]:
    xs = sorted(set(paths))
    rng = random.Random(seed)
    rng.shuffle(xs)
    return xs[:n]


def _name_for(names, idx: int) -> str:
    if isinstance(names, dict):
        return str(names.get(idx, idx))
    return str(names[idx])


def _predict(model, paths: list[str], mode: str) -> dict[str, list[dict]]:
    from vision_service.motors.findings9 import normalize_class as norm_findings9
    from vision_service.motors.impacted_tooth import normalize_class as norm_impacted
    from vision_service.motors.yolo31 import normalize_class as norm_yolo31

    out = {p: [] for p in paths}
    if not paths:
        return out
    results = model.predict(source=paths, imgsz=1280, conf=0.10, iou=0.45, verbose=False, stream=False)
    for p, res in zip(paths, results):
        class_count = len(res.names) if hasattr(res.names, "__len__") else None
        if res.boxes is None:
            continue
        for conf, cls in zip(res.boxes.conf.detach().cpu().tolist(), res.boxes.cls.detach().cpu().tolist()):
            raw = _name_for(res.names, int(cls))
            if mode == "findings9":
                mapped = norm_findings9(raw, class_count=class_count)
            elif mode == "impacted":
                mapped = norm_impacted(raw, class_count=class_count)
            else:
                mapped = norm_yolo31(raw, class_count=class_count)
            if mapped.get("type") == "finding":
                out[p].append({"finding_code": mapped.get("finding_code"), "confidence": float(conf), "raw_class": raw})
    return out


def _metrics(y_true: list[bool], y_pred: list[bool]) -> dict:
    tp = sum(t and p for t, p in zip(y_true, y_pred))
    tn = sum((not t) and (not p) for t, p in zip(y_true, y_pred))
    fp = sum((not t) and p for t, p in zip(y_true, y_pred))
    fn = sum(t and (not p) for t, p in zip(y_true, y_pred))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "specificity": specificity, "f1": f1}


def _grade(m: dict) -> str:
    if m.get("recall") is None or m.get("specificity") is None:
        return "UNMEASURED"
    if m["recall"] >= 0.80 and m["specificity"] >= 0.80:
        return "STRONG_MINI"
    if m["recall"] >= 0.60 and m["specificity"] >= 0.70:
        return "MEDIUM_MINI"
    return "WEAK_MINI"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    outdir = args.output
    outdir.mkdir(parents=True, exist_ok=True)

    import kagglehub
    from ultralytics import YOLO

    print(f"Downloading {DATASET}...")
    root = Path(kagglehub.dataset_download(DATASET))
    buckets = discover_classification(root, outdir)
    if not buckets.get("HEALTHY"):
        raise RuntimeError("HEALTHY classification folder could not be found; inspect classification_probe.json")

    selections = {}
    all_paths: set[str] = set()
    for code in TARGETS:
        pos = _locked(buckets.get(code, []), f"vision48-opg-class-pos::{code}")
        neg = _locked(buckets["HEALTHY"], f"vision48-opg-class-neg::{code}")
        selections[code] = {
            "available_positive": len(set(buckets.get(code, []))),
            "available_healthy_negative": len(set(buckets["HEALTHY"])),
            "positive": pos,
            "negative": neg,
        }
        all_paths.update(pos + neg)
    (outdir / "locked_selection.json").write_text(json.dumps(selections, indent=2, ensure_ascii=False), encoding="utf-8")

    model_dir = Path(".benchmark-models")
    f9 = model_dir / "YOLO26_Dental_Findings_9.pt"
    impacted = model_dir / "OralGuard_Impacted.pt"
    _download(FINDINGS9_URL, f9, FINDINGS9_SHA)
    _download(IMPACTED_URL, impacted, IMPACTED_SHA)

    paths = sorted(all_paths)
    pred_by_code = {
        "CARIES": _predict(YOLO(str(f9)), paths, "findings9"),
        "IMPACTED_TOOTH": _predict(YOLO(str(impacted)), paths, "impacted"),
    }

    fracture_status = "not_available"
    try:
        from vision_service.fetch_optional_models import fetch_one
        y31_path = fetch_one("yolo31")
        pred_by_code["TOOTH_FRACTURE"] = _predict(YOLO(str(y31_path)), paths, "yolo31")
        fracture_status = "ok"
    except Exception as exc:
        pred_by_code["TOOTH_FRACTURE"] = {p: [] for p in paths}
        fracture_status = f"error:{type(exc).__name__}:{exc}"

    report = {
        "protocol": "Vision48 Dental OPG classification mini v1; original classification folders; locked up to 15 positive + 15 HEALTHY negative; image-level; confidence >= 0.50; no training",
        "source": DATASET,
        "confidence_threshold": CONF,
        "fracture_model_status": fracture_status,
        "metrics": {},
    }

    for code in TARGETS:
        sel = selections[code]
        if not sel["positive"]:
            report["metrics"][code] = {"grade": "UNMEASURED_NO_POSITIVES", "n_positive": 0, "n_negative": len(sel["negative"])}
            continue
        if code == "TOOTH_FRACTURE" and fracture_status != "ok":
            report["metrics"][code] = {
                "grade": "UNMEASURED_MODEL_UNAVAILABLE",
                "n_positive": len(sel["positive"]),
                "n_negative": len(sel["negative"]),
                "motor": "yolo31",
                "status": fracture_status,
            }
            continue
        y_true, y_pred = [], []
        for path, truth in [(p, True) for p in sel["positive"]] + [(p, False) for p in sel["negative"]]:
            detected = any(
                x.get("finding_code") == code and float(x.get("confidence", 0.0)) >= CONF
                for x in pred_by_code[code].get(path, [])
            )
            y_true.append(truth)
            y_pred.append(detected)
        m = _metrics(y_true, y_pred)
        report["metrics"][code] = {
            "n_positive": len(sel["positive"]),
            "n_negative": len(sel["negative"]),
            "available_positive": sel["available_positive"],
            "available_healthy_negative": sel["available_healthy_negative"],
            **m,
            "grade": _grade(m),
            "motor": {"CARIES": "findings9", "IMPACTED_TOOTH": "impacted_tooth", "TOOTH_FRACTURE": "yolo31"}[code],
        }

    (outdir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Vision48 Dental OPG classification mini benchmark", "", f"Threshold: {CONF:.2f}", ""]
    for code, m in report["metrics"].items():
        lines.append(f"- {code}: {m.get('grade')} | TP={m.get('tp','—')} TN={m.get('tn','—')} FP={m.get('fp','—')} FN={m.get('fn','—')} | recall={m.get('recall','—')} specificity={m.get('specificity','—')}")
    (outdir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
