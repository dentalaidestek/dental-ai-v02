FINDING_CATALOG = {
    # MOTOR 1 — TOOTH / FDI
    "MISSING_TOOTH": ("Eksik diş", "tooth"),
    "SUPERNUMERARY_TOOTH": ("Süpernümerer diş", "tooth"),
    "RETAINED_PRIMARY_TOOTH": ("Persistan süt dişi", "tooth"),
    "UNERUPTED_TOOTH": ("Sürmemiş diş", "tooth"),
    "IMPACTED_TOOTH": ("Gömülü diş", "tooth"),
    "IMPACTED_THIRD_MOLAR": ("Gömülü 20 yaş dişi", "tooth"),
    "RESIDUAL_ROOT": ("Rezidüel kök", "tooth"),

    # MOTOR 2 — RESTORATIVE / ENDO
    "FILLING": ("Dolgu", "restorative_endo"),
    "CROWN": ("Kron", "restorative_endo"),
    "INLAY_ONLAY": ("İnley / Onley", "restorative_endo"),
    "BRIDGE": ("Köprü", "restorative_endo"),
    "PONTIC": ("Pontik", "restorative_endo"),
    "IMPLANT": ("İmplant", "restorative_endo"),
    "IMPLANT_SUPPORTED_CROWN": ("İmplant üstü kron", "restorative_endo"),
    "ROOT_CANAL_TREATED": ("Kanal tedavili diş", "restorative_endo"),
    "ENDO_POST": ("Endodontik post", "restorative_endo"),
    "UNDERFILLED_ROOT_CANAL": ("Kısa kanal dolgusu şüphesi", "restorative_endo"),
    "OVERFILLED_ROOT_CANAL": ("Taşkın kanal dolgusu şüphesi", "restorative_endo"),
    "BROKEN_ENDO_INSTRUMENT": ("Kırık endodontik alet şüphesi", "restorative_endo"),
    "APICAL_SURGERY": ("Apikal cerrahi bulgusu", "restorative_endo"),

    # MOTOR 3 — PATHOLOGY
    "CARIES": ("Çürük şüphesi", "pathology"),
    "DEEP_CARIES": ("Derin çürük şüphesi", "pathology"),
    "RECURRENT_CARIES": ("Sekonder çürük şüphesi", "pathology"),
    "PERIAPICAL_RADIOLUCENCY": ("Periapikal radyolüsensi", "pathology"),
    "PERIAPICAL_RADIOPACITY": ("Periapikal radyoopasite", "pathology"),
    "WIDENED_PDL": ("PDL aralığında genişleme", "pathology"),
    "LOSS_OF_LAMINA_DURA": ("Lamina dura bütünlüğünde kayıp", "pathology"),
    "CONDENSING_OSTEITIS_PATTERN": ("Kondanse kemik paterni", "pathology"),
    "EXTERNAL_ROOT_RESORPTION": ("Eksternal kök rezorpsiyonu", "pathology"),
    "INTERNAL_ROOT_RESORPTION": ("İnternal kök rezorpsiyonu", "pathology"),
    "ROOT_DILACERATION": ("Kök dilaserasyonu", "pathology"),
    "TOOTH_FRACTURE": ("Diş / kron kırığı şüphesi", "pathology"),
    "ROOT_FRACTURE": ("Kök kırığı şüphesi", "pathology"),
    "JAW_RADIOLUCENT_LESION": ("Çenede radyolüsent lezyon", "pathology"),
    "JAW_RADIOPAQUE_LESION": ("Çenede radyoopak lezyon", "pathology"),
    "MIXED_DENSITY_JAW_LESION": ("Mikst dansiteli çene lezyonu", "pathology"),

    # MOTOR 4 — PERIODONTAL
    "HORIZONTAL_BONE_LOSS": ("Horizontal kemik kaybı", "periodontal"),
    "VERTICAL_BONE_LOSS": ("Vertikal kemik kaybı", "periodontal"),
    "FURCATION_BONE_LOSS": ("Furkasyon kemik kaybı", "periodontal"),
    "CALCULUS": ("Radyografik diş taşı", "periodontal"),
    "PERI_IMPLANT_BONE_LOSS": ("Peri-implant kemik kaybı", "periodontal"),

    # MOTOR 5 — ANATOMY / EXTRA
    "MAXILLARY_SINUS_MUCOSAL_THICKENING": ("Sinüs mukozasında kalınlaşma", "anatomy"),
    "MAXILLARY_SINUS_OPACIFICATION": ("Maksiller sinüste opasifikasyon", "anatomy"),
    "MANDIBULAR_CANAL_PROXIMITY": ("Mandibular kanala yakınlık", "anatomy"),
    "CONDYLAR_FLATTENING": ("Kondilde düzleşme", "anatomy"),
    "CONDYLAR_EROSION": ("Kondilde erozyon şüphesi", "anatomy"),
    "CONDYLAR_ASYMMETRY": ("Kondiler asimetri", "anatomy"),
    "ORTHODONTIC_APPLIANCE": ("Ortodontik aparey", "anatomy"),
}

assert len(FINDING_CATALOG) == 48
