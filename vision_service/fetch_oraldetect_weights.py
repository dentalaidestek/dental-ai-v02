from __future__ import annotations

import os
from pathlib import Path

from huggingface_hub import snapshot_download

REPO_ID = "OralGPT/OralDetect-Family"
DEFAULT_DIR = Path(__file__).resolve().parent.parent / "models" / "vision" / "oraldetect"

# Only runtime-required OralDetect assets. This avoids downloading the full 2.7 GB family bundle.
ALLOW_PATTERNS = [
    "OralDetect/oraldetect.pth",
    "OralDetect/class_names_oraldetect.json",
    "OralDetect/class_texts_oraldetect.json",
    "OralCLIP/oralbert/*",
]


def fetch_oraldetect_weights(local_dir: Path | None = None) -> Path:
    target = Path(local_dir or os.getenv("ORALDETECT_MODEL_DIR", "") or DEFAULT_DIR)
    target.mkdir(parents=True, exist_ok=True)

    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
    try:
        snapshot_download(
            repo_id=REPO_ID,
            local_dir=str(target),
            allow_patterns=ALLOW_PATTERNS,
            token=token or None,
        )
    except Exception as exc:
        raise RuntimeError(
            "OralDetect ağırlıkları indirilemedi. Model deposu gated olduğundan "
            "Hugging Face hesabında erişim şartlarının kabul edilmiş olması ve gerekirse "
            "HF_TOKEN tanımlanması gerekir."
        ) from exc

    detector = target / "OralDetect" / "oraldetect.pth"
    names = target / "OralDetect" / "class_names_oraldetect.json"
    texts = target / "OralDetect" / "class_texts_oraldetect.json"
    oralbert = target / "OralCLIP" / "oralbert"
    missing = [str(p) for p in (detector, names, texts, oralbert) if not p.exists()]
    if missing:
        raise RuntimeError(f"OralDetect runtime dosyaları eksik: {missing}")

    print(f"ORALDETECT_READY dir={target}")
    print(f"detector_mb={detector.stat().st_size / 1024 / 1024:.1f}")
    return target


if __name__ == "__main__":
    fetch_oraldetect_weights()
