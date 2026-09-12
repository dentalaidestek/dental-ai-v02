MODEL_ID = "dental_findings_9_v1"

RELEASE_TAG = "vision-findings9-v1"
ASSET_NAME = "YOLO26_Dental_Findings_9.pt"
SHA256 = "8070505857f354aae4f18bf621b9b79f0e3b48a2904e44f57a2bc598ed692849"

RAW_CLASS_TO_FINDING = {
    "Apical Periodontitis": "PERIAPICAL_RADIOLUCENCY",
    "Decay": "CARIES",
    "Missing Tooth": "MISSING_TOOTH",
    "Dental Filling": "FILLING",
    "Root Canal Filling": "ROOT_CANAL_TREATED",
    "Implant": "IMPLANT",
    "Porcelain Crown": "CROWN",
    "Ceramic Bridge": "BRIDGE",
}

# Bu sınıf tek başına "gömülü" anlamına gelmez.
AUXILIARY_CLASSES = {
    "Wisdom Tooth": "WISDOM_TOOTH_PRESENT",
}


def normalize_class(raw_class: str) -> dict:
    if raw_class in RAW_CLASS_TO_FINDING:
        return {
            "type": "finding",
            "finding_code": RAW_CLASS_TO_FINDING[raw_class],
        }

    if raw_class in AUXILIARY_CLASSES:
        return {
            "type": "auxiliary",
            "signal": AUXILIARY_CLASSES[raw_class],
        }

    return {
        "type": "unknown",
        "raw_class": raw_class,
    }
