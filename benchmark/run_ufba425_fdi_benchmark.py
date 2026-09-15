from __future__ import annotations

import hashlib
import json
import re
import shutil
import urllib.request
from collections import defaultdict
from pathlib import Path

DATASET_REPO = "gatilin/rf100-vl"
DATASET_PREFIX = "ufba-425/test"
FDI_URL = "https://github.com/dentalaidestek/dental-ai-v02/releases/download/vision-model-v1/YOLOv11x-seg.pt"
FDI_SHA256 = "2d0c07b878e9f9730eb845a901e85abf3535d49cf4034d2246592f76201ac8af"
PRED_CONF_FLOOR = 0.05
SCREEN_CONF = 0.50
IOU_THR = 0.50


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
    req = urllib.request.Request(url, headers={"User-Agent": "Vision48-UFBA425-Benchmark"})
    with urllib.request.urlopen(req, timeout=900) as r, dest.open("wb") as out:
        shutil.copyfileobj(r, out)
    got = sha256(dest)
    if got != expected_sha:
        raise RuntimeError(f"SHA256 mismatch: {got}")


def parse_fdi(value: object) -> str | None:
    s = str(value).strip()
    m = re.search(r"(?<!\d)([1-4][1-8])(?!\d)", s)
    return m.group(1) if m else None


def iou_xyxy(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    aa = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    ba = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    den = aa + ba - inter
    return inter / den if den > 0 else 0.0


def ap101(recalls: list[float], precisions: list[float]) -> float:
    if not recalls:
        return 0.0
    total = 0.0
    for i in range(101):
        r = i / 100.0
        vals = [p for rr, p in zip(recalls, precisions) if rr >= r]
        total += max(vals) if vals else 0.0
    return total / 101.0


def main() -> None:
    from huggingface_hub import snapshot_download
    from ultralytics import YOLO

    outdir = Path("benchmark-results/ufba425-fdi")
    outdir.mkdir(parents=True, exist_ok=True)

    print("Downloading UFBA-425 test split from Hugging Face mirror...")
    root = Path(snapshot_download(
        repo_id=DATASET_REPO,
        repo_type="dataset",
        allow_patterns=[f"{DATASET_PREFIX}/*"],
    ))
    test_dir = root / DATASET_PREFIX
    anns = test_dir / "_annotations.coco.json"
    if not anns.exists():
        candidates = list(root.rglob("_annotations.coco.json"))
        candidates = [p for p in candidates if "ufba-425" in str(p) and "/test/" in str(p).replace("\\", "/")]
        if not candidates:
            raise RuntimeError("UFBA-425 test COCO annotation file not found")
        anns = candidates[0]
        test_dir = anns.parent

    coco = json.loads(anns.read_text(encoding="utf-8"))
    cat_name = {int(c["id"]): str(c.get("name", "")) for c in coco.get("categories", [])}
    cat_fdi = {cid: parse_fdi(name) for cid, name in cat_name.items()}
    unmapped_gt_categories = {str(cid): name for cid, name in cat_name.items() if cat_fdi[cid] is None}

    image_by_id = {int(x["id"]): x for x in coco.get("images", [])}
    gts_by_image: dict[int, list[dict]] = defaultdict(list)
    gt_count_by_class: dict[str, int] = defaultdict(int)
    for ann in coco.get("annotations", []):
        fdi = cat_fdi.get(int(ann["category_id"]))
        if not fdi:
            continue
        x, y, w, h = [float(v) for v in ann["bbox"]]
        gts_by_image[int(ann["image_id"])].append({"fdi": fdi, "box": [x, y, x + w, y + h]})
        gt_count_by_class[fdi] += 1

    paths = []
    id_for_path = {}
    for iid, item in image_by_id.items():
        p = test_dir / item["file_name"]
        if p.exists():
            paths.append(str(p))
            id_for_path[str(p)] = iid
    if not paths:
        raise RuntimeError("No UFBA-425 test images found")

    model_path = Path(".benchmark-models/YOLOv11x-seg.pt")
    download(FDI_URL, model_path, FDI_SHA256)
    model = YOLO(str(model_path))
    model_names = model.names
    if isinstance(model_names, dict):
        mapped_model_names = {int(k): parse_fdi(v) for k, v in model_names.items()}
        raw_model_names = {str(k): str(v) for k, v in model_names.items()}
    else:
        mapped_model_names = {i: parse_fdi(v) for i, v in enumerate(model_names)}
        raw_model_names = {str(i): str(v) for i, v in enumerate(model_names)}
    valid_model_classes = {v for v in mapped_model_names.values() if v}
    if len(valid_model_classes) < 20:
        raise RuntimeError(f"FDI class mapping unexpectedly weak: {raw_model_names}")

    preds_by_image: dict[int, list[dict]] = defaultdict(list)
    print(f"Running current FDI model on {len(paths)} UFBA-425 test images...")
    results = model.predict(source=paths, imgsz=1280, conf=PRED_CONF_FLOOR, iou=0.60, verbose=False, stream=False)
    for path, res in zip(paths, results):
        iid = id_for_path[path]
        if res.boxes is None:
            continue
        boxes = res.boxes.xyxy.detach().cpu().tolist()
        confs = res.boxes.conf.detach().cpu().tolist()
        clss = res.boxes.cls.detach().cpu().tolist()
        for box, conf, cls in zip(boxes, confs, clss):
            fdi = mapped_model_names.get(int(cls))
            if not fdi:
                continue
            preds_by_image[iid].append({"fdi": fdi, "box": [float(v) for v in box], "conf": float(conf)})

    # Screening metrics at production visibility threshold.
    tp = fp = fn = 0
    per_class_screen = {}
    all_classes = sorted(set(gt_count_by_class) | valid_model_classes)
    for cls in all_classes:
        ctp = cfp = cfn = 0
        for iid in image_by_id:
            gts = [g for g in gts_by_image.get(iid, []) if g["fdi"] == cls]
            preds = [p for p in preds_by_image.get(iid, []) if p["fdi"] == cls and p["conf"] >= SCREEN_CONF]
            preds.sort(key=lambda x: x["conf"], reverse=True)
            used = set()
            for pred in preds:
                best_j, best_iou = None, 0.0
                for j, gt in enumerate(gts):
                    if j in used:
                        continue
                    v = iou_xyxy(pred["box"], gt["box"])
                    if v > best_iou:
                        best_iou, best_j = v, j
                if best_j is not None and best_iou >= IOU_THR:
                    used.add(best_j); ctp += 1
                else:
                    cfp += 1
            cfn += len(gts) - len(used)
        prec = ctp / (ctp + cfp) if ctp + cfp else None
        rec = ctp / (ctp + cfn) if ctp + cfn else None
        per_class_screen[cls] = {"tp": ctp, "fp": cfp, "fn": cfn, "precision": prec, "recall": rec, "gt": gt_count_by_class.get(cls, 0)}
        tp += ctp; fp += cfp; fn += cfn

    # AP50 per class using all predictions above the low floor.
    ap50_by_class = {}
    for cls in sorted(gt_count_by_class):
        total_gt = gt_count_by_class[cls]
        entries = []
        for iid in image_by_id:
            for p in preds_by_image.get(iid, []):
                if p["fdi"] == cls:
                    entries.append((p["conf"], iid, p["box"]))
        entries.sort(reverse=True, key=lambda x: x[0])
        matched: dict[int, set[int]] = defaultdict(set)
        cum_tp = cum_fp = 0
        recalls, precisions = [], []
        for conf, iid, box in entries:
            gts = [g for g in gts_by_image.get(iid, []) if g["fdi"] == cls]
            best_j, best_iou = None, 0.0
            for j, gt in enumerate(gts):
                if j in matched[iid]:
                    continue
                v = iou_xyxy(box, gt["box"])
                if v > best_iou:
                    best_iou, best_j = v, j
            if best_j is not None and best_iou >= IOU_THR:
                matched[iid].add(best_j); cum_tp += 1
            else:
                cum_fp += 1
            recalls.append(cum_tp / total_gt if total_gt else 0.0)
            precisions.append(cum_tp / (cum_tp + cum_fp))
        ap50_by_class[cls] = ap101(recalls, precisions)

    mean_ap50 = sum(ap50_by_class.values()) / len(ap50_by_class) if ap50_by_class else None
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None

    report = {
        "protocol": "UFBA-425 external FDI box benchmark; HF RF100-VL test split; IoU>=0.50; AP50 from conf>=0.05; screening precision/recall at conf>=0.50",
        "dataset": DATASET_REPO,
        "dataset_prefix": DATASET_PREFIX,
        "test_images": len(paths),
        "ground_truth_objects": sum(gt_count_by_class.values()),
        "ground_truth_classes": sorted(gt_count_by_class),
        "unmapped_ground_truth_categories": unmapped_gt_categories,
        "model": "YOLOv11x-seg.pt / vision-model-v1",
        "model_sha256": FDI_SHA256,
        "raw_model_names": raw_model_names,
        "screen_conf": SCREEN_CONF,
        "iou_threshold": IOU_THR,
        "screening": {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall},
        "mean_ap50": mean_ap50,
        "ap50_by_class": ap50_by_class,
        "per_class_screening": per_class_screen,
        "published_reference_only": {
            "paper_repo_yolov8_map": 0.749,
            "paper_repo_yolov8_ap50": 0.946,
            "note": "Published numbers are reference values from the OralBBNet repository; direct comparability depends on using the identical split/evaluation implementation."
        },
        "oralbbnet_weight_status": "Official repository publishes code/notebooks and dataset, but no ready OralBBNet checkpoint was found; notebook weight paths are placeholders."
    }
    (outdir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
