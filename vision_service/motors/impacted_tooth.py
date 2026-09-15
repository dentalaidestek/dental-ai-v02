from __future__ import annotations


MODEL_ID = "oralguard_impacted_v1"
RELEASE_TAG = "vision-impacted-v1"
ASSET_NAME = "OralGuard_Impacted.pt"
SHA256 = "c3303656e72ede3f3d3229e58b2da276448fa204046d3e7a11e13f4d77bc723a"


def normalize_class(raw_class: str, *, class_count: int | None = None) -> dict:
    """Map the dedicated impacted-tooth model without inventing disease labels.

    The release contains a dedicated impacted-tooth detector. If the checkpoint is
    a one-class detector, any emitted class belongs to IMPACTED_TOOTH. For a
    multi-class checkpoint we only accept an explicit impacted/gomulu label.
    """
    text = str(raw_class or "").strip()
    normalized = text.casefold().replace("_", " ").replace("-", " ")

    if class_count == 1 or "impacted" in normalized or "gömülü" in normalized or "gomulu" in normalized:
        return {
            "type": "finding",
            "finding_code": "IMPACTED_TOOTH",
        }

    return {
        "type": "unknown",
        "raw_class": text,
    }
