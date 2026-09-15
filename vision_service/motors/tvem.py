from __future__ import annotations


# Exact OPGAgent TVEM category names.
TVEM11_TO_CANONICAL = {
    "Impacted": "IMPACTED_TOOTH",
    "Caries": "CARIES",
    "Filling": "FILLING",
    "Periapical Lesion": "PERIAPICAL_RADIOLUCENCY",
    "Deep Caries": "DEEP_CARIES",
    "Residual Root": "RESIDUAL_ROOT",
    "Implant": "IMPLANT",
    "Crown": "CROWN",
    "Pontic": "PONTIC",
}

TVEM11_TO_HELPER = {
    "Residual Crown": "RESIDUAL_CROWN_HELPER",
    "Prosthesis": "PROSTHESIS_HELPER",
}

TVEM_ANATOMY_TO_HELPER = {
    "Mandibular Canal": "MANDIBULAR_CANAL_HELPER",
    "Maxillary Sinus": "MAXILLARY_SINUS_HELPER",
}


def normalize_tvem11(raw_class: str) -> dict:
    text = str(raw_class or "").strip()
    if text in TVEM11_TO_CANONICAL:
        return {"type": "finding", "finding_code": TVEM11_TO_CANONICAL[text]}
    if text in TVEM11_TO_HELPER:
        return {"type": "helper", "signal": TVEM11_TO_HELPER[text]}
    return {"type": "unknown", "raw_class": text}


def normalize_tvem_anatomy(raw_class: str) -> dict:
    text = str(raw_class or "").strip()
    if text in TVEM_ANATOMY_TO_HELPER:
        return {"type": "helper", "signal": TVEM_ANATOMY_TO_HELPER[text]}
    return {"type": "unknown", "raw_class": text}


def normalize_tvem_bone_loss(raw_class: str) -> dict:
    text = str(raw_class or "").strip()
    if text == "Bone Loss" or text.startswith("class_"):
        return {"type": "helper", "signal": "BONE_LOSS_GENERIC"}
    return {"type": "unknown", "raw_class": text}
