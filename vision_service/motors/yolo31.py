from __future__ import annotations


MODEL_ID = "dental_findings_31_helper_v1"

# Labels are kept exactly as used by the public 31-class panoramic dataset/checkpoint.
RAW_TO_CANONICAL = {
    "Caries": "CARIES",
    "Crown": "CROWN",
    "Filling": "FILLING",
    "Implant": "IMPLANT",
    "Missing teeth": "MISSING_TOOTH",
    "Periapical lesion": "PERIAPICAL_RADIOLUCENCY",
    "Retained root": "RESIDUAL_ROOT",
    "Root Piece": "RESIDUAL_ROOT",
    "Root Canal Treatment": "ROOT_CANAL_TREATED",
    "Impacted tooth": "IMPACTED_TOOTH",
    "Fracture teeth": "TOOTH_FRACTURE",
    "Post-core": "ENDO_POST",
}

RAW_TO_HELPER = {
    "Malaligned": "MALALIGNED_HELPER",
    "Mandibular Canal": "MANDIBULAR_CANAL_HELPER",
    "Maxillary sinus": "MAXILLARY_SINUS_HELPER",
    "Bone Loss": "BONE_LOSS_GENERIC",
    "Permanent Teeth": "PERMANENT_TOOTH_HELPER",
    "Supra Eruption": "SUPRA_ERUPTION_HELPER",
    "TAD": "ORTHODONTIC_APPLIANCE_HELPER",
    "Abutment": "ABUTMENT_HELPER",
    "Attrition": "ATTRITION_HELPER",
    "Bone defect": "BONE_DEFECT_HELPER",
    "Gingival former": "GINGIVAL_FORMER_HELPER",
    "Metal band": "ORTHODONTIC_APPLIANCE_HELPER",
    "Orthodontic brackets": "ORTHODONTIC_APPLIANCE_HELPER",
    "Permanent retainer": "ORTHODONTIC_APPLIANCE_HELPER",
    "Plating": "PLATING_HELPER",
    "Wire": "ORTHODONTIC_APPLIANCE_HELPER",
    "Cyst": "CYST_HELPER",
    "Root resorption": "ROOT_RESORPTION_GENERIC",
    "Primary teeth": "PRIMARY_TOOTH_HELPER",
}


def normalize_class(raw_class: str, **_) -> dict:
    text = str(raw_class or "").strip()
    if text in RAW_TO_CANONICAL:
        return {"type": "finding", "finding_code": RAW_TO_CANONICAL[text]}
    if text in RAW_TO_HELPER:
        return {"type": "helper", "signal": RAW_TO_HELPER[text]}
    return {"type": "unknown", "raw_class": text}
