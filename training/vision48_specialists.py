from __future__ import annotations

"""Resumable specialist training for Vision48 panoramic motors.

This script deliberately excludes the already-pinned 9 findings. It prepares two
public panoramic sources and trains only missing specialist/helper outputs. Every
run writes checkpoints into a persistent workspace and resumes from last.pt.

Typical GPU execution:
    python training/vision48_specialists.py --workspace /content/drive/MyDrive/DentalAI_Vision48_Training
"""

import argparse
import json
import random
import shutil
import zipfile
from collections import Counter
from pathlib import Path


IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

SOURCE31 = {
    0: "Caries", 1: "Crown", 2: "Filling", 3: "Implant", 4: "Malaligned",
    5: "Mandibular Canal", 6: "Missing teeth", 7: "Periapical lesion",
    8: "Retained root", 9: "Root Canal Treatment", 10: "Root Piece",
    11: "Impacted tooth", 12: "Maxillary sinus", 13: "Bone Loss",
    14: "Fracture teeth", 15: "Permanent Teeth", 16: "Supra Eruption",
    17: "TAD", 18: "Abutment", 19: "Attrition", 20: "Bone defect",
    21: "Gingival former", 22: "Metal band", 23: "Orthodontic brackets",
    24: "Permanent retainer", 25: "Post-core", 26: "Plating", 27: "Wire",
    28: "Cyst", 29: "Root resorption", 30: "Primary teeth",
}

# Track A is a fallback specialist/helper source. Existing nine findings are not
# included as training targets even though the source dataset contains them.
MAP31 = {
    8: 0, 10: 0,                       # residual root
    14: 1,                              # tooth fracture
    29: 2,                              # generic root resorption helper
    25: 3,                              # endo post / post-core
    17: 4, 22: 4, 23: 4, 24: 4, 27: 4, # orthodontic appliance union
    30: 5,                              # primary-tooth helper
    5: 6,                               # mandibular-canal helper
    13: 7,                              # generic bone-loss helper
    28: 8,                              # cyst helper
    20: 9,                              # bone-defect helper
}
NAMES31 = {
    0: "RESIDUAL_ROOT",
    1: "TOOTH_FRACTURE",
    2: "ROOT_RESORPTION_GENERIC",
    3: "ENDO_POST",
    4: "ORTHODONTIC_APPLIANCE",
    5: "PRIMARY_TOOTH_HELPER",
    6: "MANDIBULAR_CANAL_HELPER",
    7: "BONE_LOSS_GENERIC",
    8: "CYST_HELPER",
    9: "BONE_DEFECT_HELPER",
}

ZENODO_URL = (
    "https://zenodo.org/records/15487430/files/"
    "panoramic_radiography_yolo_dataset_14_classes.zip?download=1"
)
MAP_Z = {
    5: 0,   # BON -> generic bone loss
    8: 1,   # ROT -> residual root
    9: 2,   # FUR -> furcation bone loss
    10: 3,  # APS -> apical surgery
    11: 4,  # ROR -> generic root resorption
    12: 5,  # ORD -> orthodontic appliance
}
NAMES_Z = {
    0: "BONE_LOSS_GENERIC",
    1: "RESIDUAL_ROOT",
    2: "FURCATION_BONE_LOSS",
    3: "APICAL_SURGERY",
    4: "ROOT_RESORPTION_GENERIC",
    5: "ORTHODONTIC_APPLIANCE",
}


def image_for_label(img_dir: Path, stem: str) -> Path | None:
    for p in img_dir.glob(stem + ".*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            return p
    return None


def yolo_line_to_bbox(parts):
    if len(parts) < 5:
        return None
    try:
        cls = int(float(parts[0])); vals = [float(x) for x in parts[1:]]
    except Exception:
        return None
    if len(vals) == 4:
        return cls, *vals
    if len(vals) >= 6 and len(vals) % 2 == 0:
        xs, ys = vals[0::2], vals[1::2]
        x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
        return cls, (x1+x2)/2, (y1+y2)/2, max(1e-6, x2-x1), max(1e-6, y2-y1)
    return None


def remap_split(src_img: Path, src_lbl: Path, dst_img: Path, dst_lbl: Path, class_map: dict[int, int], *, negative_fraction: float) -> dict:
    dst_img.mkdir(parents=True, exist_ok=True); dst_lbl.mkdir(parents=True, exist_ok=True)
    positives = 0; negatives = []; class_counts = Counter(); image_counts = Counter()
    for lf in sorted(src_lbl.glob("*.txt")):
        img = image_for_label(src_img, lf.stem)
        if img is None:
            continue
        kept = []; present = set(); text = lf.read_text(encoding="utf-8", errors="ignore").strip()
        for raw in text.splitlines() if text else []:
            parsed = yolo_line_to_bbox(raw.split())
            if parsed is None:
                continue
            old_id, x, y, w, h = parsed
            if old_id not in class_map:
                continue
            new_id = class_map[old_id]
            x=max(0,min(1,x)); y=max(0,min(1,y)); w=max(1e-6,min(1,w)); h=max(1e-6,min(1,h))
            kept.append(f"{new_id} {x:.7f} {y:.7f} {w:.7f} {h:.7f}")
            class_counts[new_id] += 1; present.add(new_id)
        if kept:
            shutil.copy2(img, dst_img / img.name)
            (dst_lbl / f"{lf.stem}.txt").write_text("\n".join(kept)+"\n", encoding="utf-8")
            positives += 1
            for cid in present: image_counts[cid] += 1
        else:
            negatives.append((img, lf.stem))
    random.shuffle(negatives)
    nneg = min(len(negatives), int(round(positives * negative_fraction)))
    for img, stem in negatives[:nneg]:
        shutil.copy2(img, dst_img / img.name); (dst_lbl / f"{stem}.txt").write_text("", encoding="utf-8")
    return {"positive_images": positives, "negative_images": nneg, "annotations": dict(class_counts), "images_per_class": dict(image_counts)}


def write_yaml(root: Path, names: dict[int, str]) -> Path:
    import yaml
    payload = {"path": str(root), "train": "train/images", "val": "valid/images", "test": "test/images", "names": names, "nc": len(names)}
    path = root / "data.yaml"; path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def find_standard_root(start: Path) -> Path | None:
    candidates = []
    for p in start.rglob("train"):
        if not p.is_dir() or not (p/"images").is_dir() or not (p/"labels").is_dir():
            continue
        root = p.parent
        if (root/"valid"/"images").is_dir() or (root/"val"/"images").is_dir():
            candidates.append(root)
    return max(candidates, key=lambda r: len(list((r/"train"/"images").glob("*")))) if candidates else None


def prepare_31(data_out: Path) -> tuple[Path, dict]:
    import kagglehub
    source = Path(kagglehub.dataset_download("lokisilvres/dental-disease-panoramic-detection-dataset"))
    root = find_standard_root(source)
    if root is None:
        raise RuntimeError("31-class panoramik dataset yapısı bulunamadı")
    out = data_out / "track_A_core31"
    if out.exists(): shutil.rmtree(out)
    stats = {}
    for split in ("train", "valid", "test"):
        src_split = split
        if split == "valid" and not (root/src_split/"images").is_dir(): src_split = "val"
        if not (root/src_split/"images").is_dir(): continue
        stats[split] = remap_split(root/src_split/"images", root/src_split/"labels", out/split/"images", out/split/"labels", MAP31, negative_fraction=0.10 if split == "train" else 0.0)
    return write_yaml(out, NAMES31), stats


def download(url: str, path: Path):
    import requests
    if path.is_file() and path.stat().st_size > 10_000_000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8*1024*1024):
                if chunk: f.write(chunk)


def prepare_zenodo(data_out: Path, cache: Path) -> tuple[Path, dict]:
    z = cache / "panoramic14.zip"; extracted = cache / "panoramic14"
    download(ZENODO_URL, z)
    if not extracted.exists():
        extracted.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z) as arc: arc.extractall(extracted)
    root = find_standard_root(extracted)
    if root is None:
        raise RuntimeError("Zenodo14 standard train/valid yapısı bulunamadı")
    out = data_out / "track_B_zenodo14"
    if out.exists(): shutil.rmtree(out)
    stats = {}
    for split in ("train", "valid", "test"):
        src_split = split
        if split == "valid" and not (root/src_split/"images").is_dir(): src_split = "val"
        if not (root/src_split/"images").is_dir(): continue
        stats[split] = remap_split(root/src_split/"images", root/src_split/"labels", out/split/"images", out/split/"labels", MAP_Z, negative_fraction=0.10 if split == "train" else 0.0)
    return write_yaml(out, NAMES_Z), stats


def train_or_resume(data_yaml: Path, run_dir: Path, *, epochs: int, imgsz: int, batch: int):
    import torch
    from ultralytics import YOLO
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU gerekli; CPU üzerinde eğitim başlatılmadı")
    last_pt = run_dir / "weights" / "last.pt"
    if last_pt.is_file():
        return YOLO(str(last_pt)).train(resume=True)
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    return YOLO("yolo11s.pt").train(
        data=str(data_yaml), imgsz=imgsz, epochs=epochs, batch=batch, device=0,
        workers=2, cache=False, project=str(run_dir.parent), name=run_dir.name,
        exist_ok=True, patience=15, save=True, save_period=5, plots=True,
        verbose=True, seed=42, deterministic=True,
    )


def export_run(run_dir: Path, export_dir: Path, stable_name: str, data_yaml: Path, imgsz: int) -> dict:
    from ultralytics import YOLO
    export_dir.mkdir(parents=True, exist_ok=True)
    best = run_dir / "weights" / "best.pt"; last = run_dir / "weights" / "last.pt"
    result = {"run": run_dir.name, "best": str(best) if best.is_file() else None, "last": str(last) if last.is_file() else None}
    if best.is_file():
        metrics = YOLO(str(best)).val(data=str(data_yaml), imgsz=imgsz, device=0, verbose=False)
        try:
            result.update(map50=float(metrics.box.map50), map50_95=float(metrics.box.map), map75=float(metrics.box.map75))
        except Exception as exc:
            result["metric_parse_error"] = str(exc)
        stable = export_dir / stable_name; shutil.copy2(best, stable); result["export_best"] = str(stable)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", default="/content/drive/MyDrive/DentalAI_Vision48_Training")
    p.add_argument("--track", choices=["A", "B", "all"], default="all")
    p.add_argument("--epochs", type=int, default=80)
    p.add_argument("--imgsz", type=int, default=960)
    p.add_argument("--batch", type=int, default=4)
    args = p.parse_args()

    random.seed(42)
    ws = Path(args.workspace); data_out = ws/"prepared_datasets"; runs = ws/"runs"; export = ws/"export"; cache = ws/"cache"
    for d in (data_out, runs, export, cache): d.mkdir(parents=True, exist_ok=True)
    manifest = {"workspace": str(ws), "tracks": {}}

    if args.track in {"A", "all"}:
        yaml_a, stats_a = prepare_31(data_out)
        train_or_resume(yaml_a, runs/"vision48_core31_v2", epochs=args.epochs, imgsz=args.imgsz, batch=args.batch)
        manifest["tracks"]["A"] = {"stats": stats_a, "result": export_run(runs/"vision48_core31_v2", export, "vision48_core31_best.pt", yaml_a, args.imgsz)}

    if args.track in {"B", "all"}:
        yaml_b, stats_b = prepare_zenodo(data_out, cache)
        train_or_resume(yaml_b, runs/"vision48_zenodo14_v2", epochs=args.epochs, imgsz=args.imgsz, batch=args.batch)
        manifest["tracks"]["B"] = {"stats": stats_b, "result": export_run(runs/"vision48_zenodo14_v2", export, "vision48_zenodo14_best.pt", yaml_b, args.imgsz)}

    path = export / "vision48_training_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"MANIFEST={path}")


if __name__ == "__main__":
    main()
