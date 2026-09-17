from __future__ import annotations

from typing import Any

# Grad-CAM is an explainability signal, not a lesion detector. The inference
# worker computes the heatmap from the ResNet50 last convolutional block and
# sends compact regions here. We deliberately never relabel these as bbox.


def normalize_gradcam_regions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        region = item.get("region") or item.get("bbox")
        if not (isinstance(region, list) and len(region) == 4):
            continue
        try:
            region = [float(v) for v in region]
            strength = max(0.0, min(1.0, float(item.get("strength", item.get("score", 0.0)))))
        except (TypeError, ValueError):
            continue
        label = str(item.get("label") or item.get("class_name") or "").strip()
        out.append({
            "class_label": label,
            "region": region,
            "strength": round(strength, 4),
            "localization_type": "gradcam_attention",
            "display_label": "Modelin odaklandığı bölge",
            "is_lesion_location": False,
        })
    return out
