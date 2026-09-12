from __future__ import annotations

from pathlib import Path


MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "vision"

MODEL_ASSETS = {
    "motor1_fdi": {
        "release_tag": "vision-model-v1",
        "asset_name": "YOLOv11x-seg.pt",
        "sha256": "2d0c07b878e9f9730eb845a901e85abf3535d49cf4034d2246592f76201ac8af",
        "role": "FDI tooth detection / segmentation",
    },
    "findings9": {
        "release_tag": "vision-findings9-v1",
        "asset_name": "YOLO26_Dental_Findings_9.pt",
        "sha256": "8070505857f354aae4f18bf621b9b79f0e3b48a2904e44f57a2bc598ed692849",
        "role": "Panoramic findings detector",
    },
    "impacted_tooth": {
        "release_tag": "vision-impacted-v1",
        "asset_name": "OralGuard_Impacted.pt",
        "sha256": "c3303656e72ede3f3d3229e58b2da276448fa204046d3e7a11e13f4d77bc723a",
        "role": "Impacted tooth detector",
    },
}


def model_path(model_key: str) -> Path:
    spec = MODEL_ASSETS[model_key]
    return MODEL_DIR / spec["asset_name"]


def iter_model_assets():
    for key, spec in MODEL_ASSETS.items():
        yield key, spec, model_path(key)
