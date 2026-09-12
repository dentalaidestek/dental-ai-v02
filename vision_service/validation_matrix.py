from __future__ import annotations

from dataclasses import dataclass

from vision_service.motors.catalog import FINDING_CATALOG


@dataclass(frozen=True)
class ValidationTarget:
    code: str
    lane: str
    primary_sources: tuple[str, ...]
    train_if_fail: bool
    note: str


# This is an execution/acceptance plan, not a clinical-performance claim.
# Lanes:
# - pinned_direct: already integrated release weight; still needs positive/negative panorama smoke.
# - ready_candidate: public checkpoint/helper exists; accept only after exact-label + smoke validation.
# - composed_candidate: deterministic composition/measurement on validated upstream motors; train only if validation fails.
# - train_required: no sufficiently specific ready panoramic checkpoint has been confirmed; dedicated training remains required.
_TARGETS = [
    ValidationTarget("MISSING_TOOTH", "pinned_direct", ("findings9", "fdi"), False, "Pinned direct detector with FDI topology check."),
    ValidationTarget("SUPERNUMERARY_TOOTH", "composed_candidate", ("fdi",), True, "FDI/tooth-instance topology; train a dedicated detector only if topology validation is weak."),
    ValidationTarget("RETAINED_PRIMARY_TOOTH", "ready_candidate", ("yolo31:Primary teeth", "fdi", "age"), True, "Primary-tooth checkpoint signal + adult dentition context."),
    ValidationTarget("UNERUPTED_TOOTH", "train_required", ("rvg18:Unerupted", "fdi"), True, "No strong ready panoramic checkpoint confirmed; RVG-18 provides a relevant training class but no released best.pt."),
    ValidationTarget("IMPACTED_TOOTH", "pinned_direct", ("impacted_tooth",), False, "Dedicated pinned impacted-tooth checkpoint."),
    ValidationTarget("IMPACTED_THIRD_MOLAR", "composed_candidate", ("IMPACTED_TOOTH", "fdi"), True, "Validated impacted detector restricted to FDI 18/28/38/48."),
    ValidationTarget("RESIDUAL_ROOT", "ready_candidate", ("tvem11:Residual Root", "yolo31:Retained root", "yolo31:Root Piece"), True, "Multiple public checkpoint signals exist; exact TVEM label is Residual Root."),
    ValidationTarget("FILLING", "pinned_direct", ("findings9",), False, "Pinned direct finding."),
    ValidationTarget("CROWN", "pinned_direct", ("findings9",), False, "Pinned direct finding."),
    ValidationTarget("INLAY_ONLAY", "train_required", ("partial_coverage_dataset_needed",), True, "No sufficiently specific ready panoramic checkpoint confirmed."),
    ValidationTarget("BRIDGE", "pinned_direct", ("findings9",), False, "Pinned direct finding."),
    ValidationTarget("PONTIC", "ready_candidate", ("tvem11:Pontic",), True, "Exact public TVEM class available."),
    ValidationTarget("IMPLANT", "pinned_direct", ("findings9",), False, "Pinned direct finding."),
    ValidationTarget("IMPLANT_SUPPORTED_CROWN", "composed_candidate", ("IMPLANT", "CROWN", "yolo31:Abutment"), True, "Spatial composition of validated implant/crown plus optional abutment."),
    ValidationTarget("ROOT_CANAL_TREATED", "pinned_direct", ("findings9",), False, "Pinned direct finding."),
    ValidationTarget("ENDO_POST", "ready_candidate", ("yolo31:Post-core",), True, "Public checkpoint class exists; validate tooth-ROI localization."),
    ValidationTarget("UNDERFILLED_ROOT_CANAL", "train_required", ("endo_quality_dataset_needed",), True, "No specific released panoramic checkpoint confirmed."),
    ValidationTarget("OVERFILLED_ROOT_CANAL", "train_required", ("endo_quality_dataset_needed",), True, "No specific released panoramic checkpoint confirmed."),
    ValidationTarget("BROKEN_ENDO_INSTRUMENT", "train_required", ("endo_instrument_dataset_needed",), True, "No specific released panoramic checkpoint confirmed."),
    ValidationTarget("APICAL_SURGERY", "train_required", ("zenodo14:APS",), True, "Open annotated class exists; train/resume specialist if no stronger checkpoint appears."),
    ValidationTarget("CARIES", "pinned_direct", ("findings9", "liodon3"), False, "Pinned direct detector; compact Liodon model can serve as a control motor."),
    ValidationTarget("DEEP_CARIES", "ready_candidate", ("tvem11:Deep Caries", "oralguard"), True, "Exact TVEM class and an additional ready detector candidate exist."),
    ValidationTarget("RECURRENT_CARIES", "composed_candidate", ("CARIES", "FILLING", "CROWN", "BRIDGE"), True, "Restoration-margin composition; dedicate training if false positives remain high."),
    ValidationTarget("PERIAPICAL_RADIOLUCENCY", "pinned_direct", ("findings9", "panoreader_periapical", "liodon3"), False, "Pinned direct detector with ready control/fallback models."),
    ValidationTarget("PERIAPICAL_RADIOPACITY", "train_required", ("radiopaque_apical_dataset_needed",), True, "No specific ready panoramic checkpoint confirmed."),
    ValidationTarget("WIDENED_PDL", "train_required", ("periodontal_roi_dataset_needed",), True, "Panoramic-specific ready checkpoint not confirmed."),
    ValidationTarget("LOSS_OF_LAMINA_DURA", "train_required", ("periodontal_roi_dataset_needed",), True, "Published work found on periapicals, but no ready panoramic checkpoint confirmed."),
    ValidationTarget("CONDENSING_OSTEITIS_PATTERN", "train_required", ("condensing_osteitis_dataset_needed",), True, "High-performing published panoramic YOLO study exists, but no public checkpoint was confirmed."),
    ValidationTarget("EXTERNAL_ROOT_RESORPTION", "train_required", ("yolo31:Root resorption", "root_resorption_subtype_dataset_needed"), True, "Generic ready resorption signal is not enough to assert external subtype."),
    ValidationTarget("INTERNAL_ROOT_RESORPTION", "train_required", ("yolo31:Root resorption", "root_resorption_subtype_dataset_needed"), True, "Generic ready resorption signal is not enough to assert internal subtype."),
    ValidationTarget("ROOT_DILACERATION", "train_required", ("root_dilaceration_dataset_needed",), True, "Published panoramic models exist, but no public checkpoint was confirmed."),
    ValidationTarget("TOOTH_FRACTURE", "ready_candidate", ("yolo31:Fracture teeth",), True, "Public 31-class checkpoint contains a fracture class; keep only if smoke performance is acceptable."),
    ValidationTarget("ROOT_FRACTURE", "train_required", ("root_fracture_dataset_needed",), True, "Tooth-fracture class is not specific enough for root fracture."),
    ValidationTarget("JAW_RADIOLUCENT_LESION", "train_required", ("yolo31:Cyst", "yolo31:Bone defect", "jaw_lesion_dataset_needed"), True, "Helpers exist, but broad radiolucent jaw-lesion checkpoint is not confirmed."),
    ValidationTarget("JAW_RADIOPAQUE_LESION", "train_required", ("jaw_lesion_dataset_needed",), True, "Published radiopaque jaw-lesion models found, but no public checkpoint confirmed."),
    ValidationTarget("MIXED_DENSITY_JAW_LESION", "composed_candidate", ("JAW_RADIOLUCENT_LESION", "JAW_RADIOPAQUE_LESION"), True, "Co-localization of two validated lesion motors; train directly if composition underperforms."),
    ValidationTarget("HORIZONTAL_BONE_LOSS", "composed_candidate", ("tvem_bone_loss", "fdi", "crest_geometry"), True, "TVEM bone-loss segmentation + validated crest orientation measurement."),
    ValidationTarget("VERTICAL_BONE_LOSS", "composed_candidate", ("tvem_bone_loss", "fdi", "angular_defect_geometry"), True, "TVEM bone-loss segmentation + localized angular-defect measurement."),
    ValidationTarget("FURCATION_BONE_LOSS", "train_required", ("zenodo14:FUR", "tvem_bone_loss"), True, "Zenodo annotated FUR class is available; train/resume a specialist rather than relabel generic bone loss."),
    ValidationTarget("CALCULUS", "train_required", ("rvg18:Calculus",), True, "Relevant annotated class exists in RVG-18, but no released checkpoint confirmed."),
    ValidationTarget("PERI_IMPLANT_BONE_LOSS", "composed_candidate", ("IMPLANT", "tvem_bone_loss", "implant_cervical_geometry"), True, "Public study reports strong dedicated performance but releases no weights/data; validate composition first."),
    ValidationTarget("MAXILLARY_SINUS_MUCOSAL_THICKENING", "composed_candidate", ("tvem_canal_sinus:Maxillary Sinus", "sinus_density_geometry"), True, "Validated sinus mask + basal soft-tissue thickness measurement."),
    ValidationTarget("MAXILLARY_SINUS_OPACIFICATION", "composed_candidate", ("tvem_canal_sinus:Maxillary Sinus", "sinus_density_geometry"), True, "Validated sinus mask + internal opacity fraction."),
    ValidationTarget("MANDIBULAR_CANAL_PROXIMITY", "composed_candidate", ("tvem_canal_sinus:Mandibular Canal", "fdi", "distance"), True, "Anatomy segmentation + geometric distance; output is measurement-driven."),
    ValidationTarget("CONDYLAR_FLATTENING", "train_required", ("tmj_panorama_dataset_needed",), True, "No public ready panoramic checkpoint confirmed."),
    ValidationTarget("CONDYLAR_EROSION", "train_required", ("tmj_panorama_dataset_needed",), True, "No public ready panoramic checkpoint confirmed."),
    ValidationTarget("CONDYLAR_ASYMMETRY", "composed_candidate", ("bilateral_condyle_segmentation", "shape_measurement"), True, "Can be measurement-driven after reliable bilateral condyle localization; train if localization is weak."),
    ValidationTarget("ORTHODONTIC_APPLIANCE", "ready_candidate", ("yolo31:TAD", "yolo31:Metal band", "yolo31:Orthodontic brackets", "yolo31:Permanent retainer", "yolo31:Wire"), True, "Ready 31-class checkpoint exposes multiple orthodontic hardware labels."),
]

VALIDATION_TARGETS = {target.code: target for target in _TARGETS}

assert len(_TARGETS) == 48
assert len(VALIDATION_TARGETS) == 48
assert set(VALIDATION_TARGETS) == set(FINDING_CATALOG)


def by_lane(lane: str) -> list[ValidationTarget]:
    return [target for target in _TARGETS if target.lane == lane]
