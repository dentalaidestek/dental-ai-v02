from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


INREDD_MAP = {
    "Im": "IMPLANT",
    "Cp": "CROWN",
    "CpuM": "CROWN",
    "P": "PONTIC",
    "Rr": "RESIDUAL_ROOT",
    "M3i": "IMPACTED_THIRD_MOLAR",
    "Te": "ROOT_CANAL_TREATED",
    "TeM": "ROOT_CANAL_TREATED",
    "Ri": "ENDO_POST",
    "RiM": "ENDO_POST",
    "C": "CARIES",
    "I": "IMPACTED_TOOTH",
}

def xywh_to_xyxy(b):
    x, y, w, h = map(float, b)
    return [x, y, x + w, y + h]

def write_jsonl(records, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def normalize_inredd(coco_path: Path, image_root: Path):
    data = json.loads(coco_path.read_text(encoding="utf-8"))
    images = {int(x["id"]): x for x in data.get("images", [])}
    categories = {int(x["id"]): x["name"] for x in data.get("categories", [])}
    by_image = {}
    for ann in data.get("annotations", []):
        raw = categories.get(int(ann["category_id"]), "")
        code = INREDD_MAP.get(raw)
        if not code:
            continue
        item = {
            "finding_code": code,
            "raw_label": raw,
            "bbox_xyxy": xywh_to_xyxy(ann["bbox"]),
            "annotation_quality": "forced_consensus_radiologists",
        }
        by_image.setdefault(int(ann["image_id"]), []).append(item)
    exact = sorted(set(INREDD_MAP.values()))
    for image_id, info in images.items():
        yield {
            "image_id": f"inredd:{image_id}",
            "source": "inredd_pan924",
            "image_path": str(image_root / info["file_name"]),
            "width": info.get("width"),
            "height": info.get("height"),
            "annotations": by_image.get(image_id, []),
            "exhaustive_codes": exact,
        }

def normalize_hanoi(xml_root: Path, image_root: Path):
    # The released cohort contains lesion-positive cases only.
    for xml_path in sorted(xml_root.rglob("*.xml")):
        root = ET.parse(xml_path).getroot()
        filename = root.findtext("filename") or (xml_path.stem + ".jpg")
        size = root.find("size")
        width = int(size.findtext("width")) if size is not None and size.findtext("width") else None
        height = int(size.findtext("height")) if size is not None and size.findtext("height") else None
        anns = []
        for obj in root.findall("object"):
            box = obj.find("bndbox")
            if box is None:
                continue
            anns.append({
                "finding_code": "PERIAPICAL_RADIOLUCENCY",
                "raw_label": obj.findtext("name") or "periapical_lesion",
                "bbox_xyxy": [
                    float(box.findtext("xmin")), float(box.findtext("ymin")),
                    float(box.findtext("xmax")), float(box.findtext("ymax")),
                ],
                "annotation_quality": "three_dentist_consensus",
            })
        if anns:
            yield {
                "image_id": f"hanoi:{xml_path.stem}",
                "source": "hanoi_periapical",
                "image_path": str(image_root / filename),
                "width": width,
                "height": height,
                "annotations": anns,
                "exhaustive_codes": ["PERIAPICAL_RADIOLUCENCY"],
                "cohort_note": "positive_only_no_population_specificity",
            }

def main():
    ap = argparse.ArgumentParser(description="Normalize independent expert datasets into Vision48 gold JSONL. No training.")
    sub = ap.add_subparsers(dest="source", required=True)
    p = sub.add_parser("inredd")
    p.add_argument("--coco", type=Path, required=True)
    p.add_argument("--images", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("hanoi")
    p.add_argument("--xml", type=Path, required=True)
    p.add_argument("--images", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.source == "inredd":
        records = normalize_inredd(args.coco, args.images)
    else:
        records = normalize_hanoi(args.xml, args.images)
    write_jsonl(records, args.out)
    print(args.out)

if __name__ == "__main__":
    main()
