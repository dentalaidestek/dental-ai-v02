from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def iou(a, b):
    ax1, ay1, ax2, ay2 = map(float, a)
    bx1, by1, bx2, by2 = map(float, b)
    ix1, iy1, ix2, iy2 = max(ax1,bx1), max(ay1,by1), min(ax2,bx2), min(ay2,by2)
    iw, ih = max(0.0, ix2-ix1), max(0.0, iy2-iy1)
    inter = iw * ih
    ua = max(0.0, ax2-ax1) * max(0.0, ay2-ay1)
    ub = max(0.0, bx2-bx1) * max(0.0, by2-by1)
    den = ua + ub - inter
    return inter / den if den else 0.0

def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def normalize_preds(record):
    items = record.get("findings") or record.get("predictions") or []
    out = []
    for x in items:
        code = x.get("finding_code")
        bbox = x.get("bbox_xyxy") or x.get("bbox")
        if code and bbox and len(bbox) == 4:
            out.append({"finding_code": code, "bbox_xyxy": bbox, "confidence": float(x.get("confidence", x.get("score", 1.0)))})
    return out

def main():
    ap = argparse.ArgumentParser(description="Evaluate existing Vision48 predictions against locked gold data. No training.")
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--pred", type=Path, required=True, help="JSONL with image_id and findings/predictions")
    ap.add_argument("--iou", type=float, default=0.25)
    ap.add_argument("--conf", type=float, default=0.50)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    pred_by_id = {x["image_id"]: normalize_preds(x) for x in read_jsonl(args.pred)}
    counts = defaultdict(lambda: {"tp":0,"fp":0,"fn":0,"images":0})

    for rec in read_jsonl(args.gold):
        exhaustive = set(rec.get("exhaustive_codes") or [])
        gold_by_code = defaultdict(list)
        for g in rec.get("annotations") or []:
            if g.get("finding_code") and g.get("bbox_xyxy"):
                gold_by_code[g["finding_code"]].append(g)
        pred_by_code = defaultdict(list)
        for p in pred_by_id.get(rec["image_id"], []):
            if p["confidence"] >= args.conf:
                pred_by_code[p["finding_code"]].append(p)

        for code in set(gold_by_code) | (set(pred_by_code) & exhaustive):
            counts[code]["images"] += 1
            gs = gold_by_code.get(code, [])
            ps = pred_by_code.get(code, [])
            used = set()
            for g in gs:
                best_j, best_iou = None, -1.0
                for j, p in enumerate(ps):
                    if j in used:
                        continue
                    v = iou(g["bbox_xyxy"], p["bbox_xyxy"])
                    if v > best_iou:
                        best_j, best_iou = j, v
                if best_j is not None and best_iou >= args.iou:
                    used.add(best_j)
                    counts[code]["tp"] += 1
                else:
                    counts[code]["fn"] += 1
            if code in exhaustive:
                counts[code]["fp"] += max(0, len(ps)-len(used))

    report = {}
    for code, c in counts.items():
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        precision = tp/(tp+fp) if tp+fp else None
        recall = tp/(tp+fn) if tp+fn else None
        f1 = (2*precision*recall/(precision+recall)) if precision is not None and recall is not None and precision+recall else None
        report[code] = {**c, "precision":precision, "recall":recall, "f1":f1}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "gold": str(args.gold),
        "pred": str(args.pred),
        "iou_threshold": args.iou,
        "confidence_threshold": args.conf,
        "metrics": dict(sorted(report.items())),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.out)

if __name__ == "__main__":
    main()
