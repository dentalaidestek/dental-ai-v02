from __future__ import annotations


MODEL_ID = "insmile_dental_yolov8m_12_v1"

# Keep only mappings whose public class semantics match our canonical finding.
# Ambiguous/generic classes remain helpers and must never be promoted to a
# more specific canonical subtype without separate evidence.
RAW_TO_CANONICAL = {
    "Caries": "CARIES",
    "Periapical Lesion": "PERIAPICAL_RADIOLUCENCY",
    "Retained Root": "RESIDUAL_ROOT",
    "Root Piece": "RESIDUAL_ROOT",
    "Impacted Tooth": "IMPACTED_TOOTH",
}

RAW_TO_HELPER = {
    "Bone Loss": "BONE_LOSS_GENERIC",
    "Fracture": "TOOTH_FRACTURE_CANDIDATE",
    "Supra Eruption": "SUPRA_ERUPTION_HELPER",
    "Attrition": "ATTRITION_HELPER",
    "Bone Defect": "BONE_DEFECT_HELPER",
    "Cyst": "CYST_HELPER",
    "Root Resorption": "ROOT_RESORPTION_GENERIC",
}


def normalize_class(raw_class: str, **_) -> dict:
    text = str(raw_class or "").strip()
    if text in RAW_TO_CANONICAL:
        return {"type": "finding", "finding_code": RAW_TO_CANONICAL[text]}
    if text in RAW_TO_HELPER:
        return {"type": "helper", "signal": RAW_TO_HELPER[text]}
    return {"type": "unknown", "raw_class": text}
