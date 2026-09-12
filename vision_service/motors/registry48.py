from __future__ import annotations

from dataclasses import dataclass

from vision_service.motors.catalog import FINDING_CATALOG


@dataclass(frozen=True)
class MotorSpec:
    code: str
    strategy: str
    sources: tuple[str, ...]
    description: str


# IMPORTANT: This registry describes implemented inference strategies. It does not
# claim that a finding has passed clinical/runtime validation. Validation status is
# tracked separately in readiness.py.
_SPECS = [
    MotorSpec("MISSING_TOOTH", "direct+topology", ("findings9", "fdi"), "Direct detector with FDI-topology backup."),
    MotorSpec("SUPERNUMERARY_TOOTH", "composed", ("fdi",), "Duplicate/out-of-arch tooth candidates from FDI topology."),
    MotorSpec("RETAINED_PRIMARY_TOOTH", "composed", ("yolo31:PRIMARY_TOOTH_HELPER", "fdi"), "Primary-tooth helper combined with dentition context."),
    MotorSpec("UNERUPTED_TOOTH", "cv_derived", ("fdi", "tooth_position"), "Off-arch permanent tooth candidate not already classified as impacted."),
    MotorSpec("IMPACTED_TOOTH", "direct", ("impacted_tooth",), "Dedicated impacted-tooth detector."),
    MotorSpec("IMPACTED_THIRD_MOLAR", "composed", ("IMPACTED_TOOTH", "fdi", "WISDOM_TOOTH_PRESENT"), "Impacted finding restricted to third-molar anatomy."),
    MotorSpec("RESIDUAL_ROOT", "direct_fallback", ("tvem11:Residual Root", "yolo31:Retained root", "yolo31:Root Piece"), "Residual-root detector ensemble."),
    MotorSpec("FILLING", "direct", ("findings9",), "Direct panoramic filling detector."),
    MotorSpec("CROWN", "direct", ("findings9",), "Direct panoramic crown detector."),
    MotorSpec("INLAY_ONLAY", "cv_derived", ("fdi", "radiopaque_restoration_geometry"), "Intracoronal partial-coverage radiopaque restoration geometry."),
    MotorSpec("BRIDGE", "direct", ("findings9",), "Direct bridge detector."),
    MotorSpec("PONTIC", "direct_fallback", ("tvem11:Pontic", "bridge_geometry"), "TVEM pontic detector with bridge-span geometry fallback."),
    MotorSpec("IMPLANT", "direct", ("findings9",), "Direct implant detector."),
    MotorSpec("IMPLANT_SUPPORTED_CROWN", "composed", ("IMPLANT", "CROWN", "yolo31:ABUTMENT_HELPER"), "Implant/crown/abutment spatial composition."),
    MotorSpec("ROOT_CANAL_TREATED", "direct", ("findings9",), "Direct root-canal-treated detector."),
    MotorSpec("ENDO_POST", "direct_fallback", ("yolo31:Post-core", "endo_post_geometry"), "Post-core detector with high-density intraradicular geometry fallback."),
    MotorSpec("UNDERFILLED_ROOT_CANAL", "cv_derived", ("ROOT_CANAL_TREATED", "fdi", "endo_fill_extent"), "Canal-fill end point short of estimated root apex."),
    MotorSpec("OVERFILLED_ROOT_CANAL", "cv_derived", ("ROOT_CANAL_TREATED", "fdi", "endo_fill_extent"), "Canal-fill radiopacity extending beyond estimated root apex."),
    MotorSpec("BROKEN_ENDO_INSTRUMENT", "cv_derived", ("fdi", "endo_linear_fragment"), "Short isolated high-density linear fragment in root-canal region."),
    MotorSpec("APICAL_SURGERY", "direct_fallback", ("zenodo14:APS", "apical_resection_geometry"), "Apical-surgery class when available, otherwise resection/retrofill morphology."),
    MotorSpec("CARIES", "direct", ("findings9",), "Direct caries detector."),
    MotorSpec("DEEP_CARIES", "direct_fallback", ("tvem11:Deep Caries", "caries_depth_geometry"), "TVEM deep-caries detector with pulp-proximity geometry fallback."),
    MotorSpec("RECURRENT_CARIES", "composed", ("CARIES", "FILLING", "CROWN", "BRIDGE"), "Caries overlapping or immediately adjacent to an existing restoration margin."),
    MotorSpec("PERIAPICAL_RADIOLUCENCY", "direct", ("findings9", "panoreader_periapical"), "Direct/fallback periapical lesion detector."),
    MotorSpec("PERIAPICAL_RADIOPACITY", "cv_derived", ("fdi", "apical_density"), "Localized high-density anomaly in estimated apical region."),
    MotorSpec("WIDENED_PDL", "cv_derived", ("fdi", "root_border_dark_band"), "Abnormally wide radiolucent band along root outline."),
    MotorSpec("LOSS_OF_LAMINA_DURA", "cv_derived", ("fdi", "root_border_continuity"), "Discontinuity of the radiopaque root-border line."),
    MotorSpec("CONDENSING_OSTEITIS_PATTERN", "composed", ("PERIAPICAL_RADIOPACITY", "apical_density"), "Diffuse periapical radiopaque pattern rather than a compact foreign body."),
    MotorSpec("EXTERNAL_ROOT_RESORPTION", "composed", ("yolo31:ROOT_RESORPTION_GENERIC", "root_contour"), "Generic resorption signal with external root-contour indentation."),
    MotorSpec("INTERNAL_ROOT_RESORPTION", "composed", ("yolo31:ROOT_RESORPTION_GENERIC", "root_lumen"), "Generic resorption signal with central canal/root-lumen expansion."),
    MotorSpec("ROOT_DILACERATION", "cv_derived", ("fdi", "root_centerline_curvature"), "Root-axis/centerline curvature measurement."),
    MotorSpec("TOOTH_FRACTURE", "direct_fallback", ("yolo31:Fracture teeth", "fracture_line"), "Fracture detector with ROI line-pattern fallback."),
    MotorSpec("ROOT_FRACTURE", "cv_derived", ("fdi", "root_fracture_line"), "Transverse/oblique fracture-line candidate restricted to root ROI."),
    MotorSpec("JAW_RADIOLUCENT_LESION", "composed", ("yolo31:CYST_HELPER", "yolo31:BONE_DEFECT_HELPER", "jaw_dark_component"), "Large non-tooth radiolucent jaw component supported by lesion helpers."),
    MotorSpec("JAW_RADIOPAQUE_LESION", "cv_derived", ("jaw_bright_component",), "Large non-tooth radiopaque jaw component after excluding restorations/teeth."),
    MotorSpec("MIXED_DENSITY_JAW_LESION", "composed", ("JAW_RADIOLUCENT_LESION", "JAW_RADIOPAQUE_LESION"), "Co-localized radiolucent and radiopaque components."),
    MotorSpec("HORIZONTAL_BONE_LOSS", "composed", ("bone_loss", "fdi", "crest_orientation"), "Bone-loss helper plus broadly horizontal alveolar-crest geometry."),
    MotorSpec("VERTICAL_BONE_LOSS", "composed", ("bone_loss", "fdi", "angular_defect"), "Bone-loss helper plus localized angular defect geometry."),
    MotorSpec("FURCATION_BONE_LOSS", "direct_fallback", ("zenodo14:FUR", "bone_loss", "molar_furcation"), "Furcation class when available, otherwise bone-loss signal centered between molar roots."),
    MotorSpec("CALCULUS", "cv_derived", ("fdi", "cervical_radiopaque_spur"), "Small high-density spur adjacent to cervical/interproximal tooth surface."),
    MotorSpec("PERI_IMPLANT_BONE_LOSS", "composed", ("IMPLANT", "bone_loss", "implant_cervical_zone"), "Bone-loss signal spatially associated with implant cervical region."),
    MotorSpec("MAXILLARY_SINUS_MUCOSAL_THICKENING", "composed", ("tvem_anatomy:Maxillary Sinus", "sinus_basal_band"), "Sinus segmentation plus basal soft-tissue/radiopacity band ratio."),
    MotorSpec("MAXILLARY_SINUS_OPACIFICATION", "composed", ("tvem_anatomy:Maxillary Sinus", "sinus_opacity_fraction"), "Sinus segmentation plus diffuse internal opacity fraction."),
    MotorSpec("MANDIBULAR_CANAL_PROXIMITY", "composed", ("tvem_anatomy:Mandibular Canal", "fdi", "distance"), "Minimum tooth/root-to-canal geometric distance."),
    MotorSpec("CONDYLAR_FLATTENING", "cv_derived", ("bilateral_condyle_roi", "superior_contour_curvature"), "Reduced superior condylar contour curvature."),
    MotorSpec("CONDYLAR_EROSION", "cv_derived", ("bilateral_condyle_roi", "contour_irregularity"), "Condylar cortical contour irregularity/erosive edge signal."),
    MotorSpec("CONDYLAR_ASYMMETRY", "cv_derived", ("bilateral_condyle_roi", "shape_comparison"), "Left/right condylar shape, height and area asymmetry."),
    MotorSpec("ORTHODONTIC_APPLIANCE", "direct_union", ("yolo31:TAD", "yolo31:Metal band", "yolo31:Orthodontic brackets", "yolo31:Permanent retainer", "yolo31:Wire"), "Union of orthodontic hardware classes."),
]

MOTOR_SPECS = {spec.code: spec for spec in _SPECS}

assert len(_SPECS) == 48
assert len(MOTOR_SPECS) == 48
assert set(MOTOR_SPECS) == set(FINDING_CATALOG)
assert all(spec.strategy not in {"placeholder", "todo", "unknown"} for spec in _SPECS)
