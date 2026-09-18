from __future__ import annotations


MODEL_ID = "liodon_panorama3_v1"

# Exact public class labels from liodon-ai/dental-panoramic-detector.
RAW_TO_CANONICAL = {
    "caries": "CARIES",
    "periapical_lesion": "PERIAPICAL_RADIOLUCENCY",
    "impacted_tooth": "IMPACTED_TOOTH",
}


def normalize_class(raw_class: str, **_) -> dict:
    text = str(raw_class or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if text in RAW_TO_CANONICAL:
        return {"type": "finding", "finding_code": RAW_TO_CANONICAL[text]}
    return {"type": "unknown", "raw_class": str(raw_class or "")}
