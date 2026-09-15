from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrainingSource:
    key: str
    access: str
    locator: str
    modality: str
    target_signals: tuple[str, ...]
    note: str


SOURCES = {
    "kaggle31": TrainingSource(
        key="kaggle31",
        access="automatic_kagglehub",
        locator="lokisilvres/dental-disease-panoramic-detection-dataset",
        modality="PANORAMIC",
        target_signals=(
            "RESIDUAL_ROOT", "TOOTH_FRACTURE", "ROOT_RESORPTION_GENERIC",
            "ENDO_POST", "ORTHODONTIC_APPLIANCE", "PRIMARY_TOOTH_HELPER",
            "MANDIBULAR_CANAL_HELPER", "BONE_LOSS_GENERIC", "CYST_HELPER",
            "BONE_DEFECT_HELPER",
        ),
        note="31-class public panoramic source. Existing pinned nine findings are excluded from retraining.",
    ),
    "zenodo14": TrainingSource(
        key="zenodo14",
        access="automatic_http",
        locator="https://zenodo.org/records/15487430/files/panoramic_radiography_yolo_dataset_14_classes.zip?download=1",
        modality="PANORAMIC",
        target_signals=(
            "BONE_LOSS_GENERIC", "RESIDUAL_ROOT", "FURCATION_BONE_LOSS",
            "APICAL_SURGERY", "ROOT_RESORPTION_GENERIC", "ORTHODONTIC_APPLIANCE",
        ),
        note="Open 14-class panoramic source used as a specialist track.",
    ),
    "roboflow_rvg18": TrainingSource(
        key="roboflow_rvg18",
        access="public_dataset_export_required",
        locator="https://universe.roboflow.com/x-f3gb6/rvg-v1",
        modality="DENTAL_XRAY",
        target_signals=(
            "UNERUPTED_TOOTH", "CALCULUS", "TOOTH_FRACTURE", "FURCATION_BONE_LOSS",
            "RESIDUAL_ROOT", "BONE_LOSS_GENERIC", "CYST_HELPER", "SINUS_HELPER",
        ),
        note="1.1k-image, 18-class instance-segmentation dataset. No public best.pt confirmed.",
    ),
    "roboflow_caries87": TrainingSource(
        key="roboflow_caries87",
        access="public_dataset_export_required",
        locator="https://universe.roboflow.com/dental-xray-analysis/caries-tsrca-jmwwl",
        modality="DENTAL_XRAY",
        target_signals=(
            "UNERUPTED_TOOTH", "CALCULUS", "TOOTH_FRACTURE", "FURCATION_BONE_LOSS",
            "UNDERFILLED_ROOT_CANAL", "OVERFILLED_ROOT_CANAL", "VERTICAL_BONE_LOSS",
            "PRIMARY_TOOTH_HELPER", "ENDO_POST", "CONDYLE_HELPER", "SINUS_HELPER",
        ),
        note="3k-image, 87-label instance-segmentation source; exact labels include SHORTENED RCT, ROOT CANAL BEYOND APEX, Unerupted, Calculus and VERTICAL BONE LOSS.",
    ),
    "roboflow_apex_resorption": TrainingSource(
        key="roboflow_apex_resorption",
        access="hosted_model_or_export_required",
        locator="https://universe.roboflow.com/tooth-g5ed6/apex-detection-resorption",
        modality="DENTAL_XRAY",
        target_signals=("UNERUPTED_TOOTH", "ROOT_RESORPTION_GENERIC"),
        note=(
            "Public 2026 project with explicit Unerupted Tooth and Resorbed Apex labels. "
            "Do not split generic/resorbed-apex evidence into EXTERNAL_ROOT_RESORPTION or "
            "INTERNAL_ROOT_RESORPTION. Local checkpoint SHA and panoramic-only suitability "
            "must be verified before runtime use."
        ),
    ),
    "roboflow_lamina_pdl": TrainingSource(
        key="roboflow_lamina_pdl",
        access="hosted_model_or_export_required",
        locator="https://universe.roboflow.com/ld-1rvyz/lamina-dura-loss-5-mx-and-mn-2jxyv",
        modality="DENTAL_XRAY",
        target_signals=("LOSS_OF_LAMINA_DURA", "WIDENED_PDL", "FURCATION_BONE_LOSS"),
        note=(
            "Research candidate with lamina-dura/PDL/furcation-related labels. Exact raw-label "
            "semantics, image modality, export rights and a local checkpoint hash are required "
            "before any canonical mapping or PASS."
        ),
    ),
    "roboflow_furcation_detection": TrainingSource(
        key="roboflow_furcation_detection",
        access="hosted_model_or_export_required",
        locator="https://universe.roboflow.com/m-owrxi/furcation-detection",
        modality="DENTAL_XRAY",
        target_signals=("FURCATION_BONE_LOSS",),
        note=(
            "Public trained YOLO project (reported 3,204 images). Treat as a research candidate, "
            "not a local ready weight, until checkpoint export, SHA256, license, panoramic "
            "modality and positive/negative runtime behavior are verified."
        ),
    ),
    "roboflow_tmj_morphology": TrainingSource(
        key="roboflow_tmj_morphology",
        access="hosted_model_or_export_required",
        locator="https://universe.roboflow.com/tesis-lana/tmj-anotation-all-zl04j",
        modality="DENTAL_XRAY",
        target_signals=("TMJ_MORPHOLOGY_HELPER",),
        note=(
            "TMJ morphology research candidate. Class names such as FLATTENED must not be "
            "mapped directly to CONDYLAR_FLATTENING until anatomy/class-code semantics and "
            "panoramic applicability are independently verified."
        ),
    ),
    "pandent": TrainingSource(
        key="pandent",
        access="gated_manual_approval",
        locator="Desperado1103/Pandent",
        modality="PANORAMIC",
        target_signals=(
            "UNERUPTED_TOOTH", "FURCATION_BONE_LOSS", "ENDO_POST", "VERTICAL_BONE_LOSS",
            "HORIZONTAL_BONE_LOSS", "MAXILLARY_SINUS_ABNORMALITY", "TMJ_ABNORMALITY",
        ),
        note="9,524 OPG-report pairs with tooth-level/region-level findings; gated access, so it is not a blocking source for the current automatic tracks.",
    ),
}


def automatic_sources() -> list[TrainingSource]:
    return [s for s in SOURCES.values() if s.access.startswith("automatic_")]
