from __future__ import annotations


MODEL_ID = "oralguard4_panoramic_v1"
RELEASE_TAG = "vision-oralguard4-v1"
ASSET_NAME = "OralGuard_Impacted.pt"
SHA256 = "c3303656e72ede3f3d3229e58b2da276448fa204046d3e7a11e13f4d77bc723a"


def normalize_class(raw_class: str, *, class_count: int | None = None) -> dict:
    """Normalize the verified four-class OralGuard panoramic checkpoint.

    Runtime inspection confirmed these classes:
    caries, deep_caries, periapical_lesion, impacted_tooth.
    Unknown labels are never coerced into impacted-tooth findings.
    """
    text = str(raw_class or "").strip()
    normalized = text.casefold().replace("_", " ").replace("-", " ")
    aliases = {
        "caries": "CARIES",
        "deep caries": "DEEP_CARIES",
        "periapical lesion": "PERIAPICAL_RADIOLUCENCY",
        "impacted tooth": "IMPACTED_TOOTH",
    }
    code = aliases.get(normalized)
    if code:
        return {"type": "finding", "finding_code": code}
    return {"type": "unknown", "raw_class": text}
