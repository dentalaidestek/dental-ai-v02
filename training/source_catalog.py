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
    "prad_periapical": TrainingSource(
        key="prad_periapical",
        access="gated_application",
        locator="https://github.com/nkicsl/PRAD",
        modality="PERIAPICAL",
        target_signals=("APICAL_PERIODONTITIS_PAI","ROOT_CANAL_TREATED","CROWN","FILLING","IMPLANT","ORTHODONTIC_APPLIANCE"),
        note="PRAD: 5,000 periapical radiographs; nine expert-verified segmentation labels. Access requires application/approval; never treat as automatic.",
    ),
    "mouthcare_intraoral_sample": TrainingSource(
        key="mouthcare_intraoral_sample",
        access="gated_huggingface_auto_approval",
        locator="MouthCare/intraoral-sample",
        modality="INTRAORAL_PHOTO",
        target_signals=("VISIBLE_CARIES","CALCULUS","GINGIVAL_INFLAMMATION","DENTAL_RESTORATION"),
        note="480-image/80-patient evaluation sample with dentist-authored polygon annotations for tooth, gum, tartar, cavity, gingivitis and restoration. Keep patient-level split.",
    ),
    "intraoral_caries_6313": TrainingSource(
        key="intraoral_caries_6313",
        access="restricted_zenodo",
        locator="https://zenodo.org/records/14769743",
        modality="INTRAORAL_PHOTO",
        target_signals=("VISIBLE_CARIES",),
        note="6,313 dentist-verified intraoral caries images with YOLO/COCO/VOC/LabelMe annotations. Record is public but files are restricted; do not assume unattended download.",
    ),
    "gingivitis_caption_1096": TrainingSource(
        key="gingivitis_caption_1096",
        access="public_research_dataset",
        locator="https://doi.org/10.1016/j.dib.2024.110960",
        modality="INTRAORAL_PHOTO",
        target_signals=("GINGIVAL_INFLAMMATION",),
        note="1,096 high-resolution intraoral images labeled by three periodontists with MGI scores; use only after exact downloadable artifact and license are verified.",
    ),
    "panoramic_apical_3926": TrainingSource(
        key="panoramic_apical_3926",
        access="public_mendeley",
        locator="https://doi.org/10.17632/3p6rbrp8yb.2",
        modality="PANORAMIC",
        target_signals=("PERIAPICAL_RADIOLUCENCY",),
        note="3,926 original panoramic radiographs with XML lesion localization, selected from 16,519 radiographs and annotated by three experienced dentists. Use originals only; never mix augmented derivatives into locked holdout.",
    ),
    "oral_mamba_3365": TrainingSource(
        key="oral_mamba_3365",
        access="publication_verify_download",
        locator="https://doi.org/10.1186/s12903-024-05072-1",
        modality="INTRAORAL_PHOTO",
        target_signals=("VISIBLE_CARIES","CALCULUS","GINGIVAL_INFLAMMATION"),
        note="3,365 oral endoscopy images with lesion segmentation for caries, supragingival calculus and gingivitis; annotations reviewed by calibrated clinicians. Download artifact/license must be verified before automatic use.",
    ),
    "rct_pearl": TrainingSource(
        key="rct_pearl",
        access="restricted_zenodo",
        locator="https://zenodo.org/records/20284981",
        modality="PERIAPICAL",
        target_signals=("ROOT_CANAL_TREATED","UNDERFILLED_ROOT_CANAL","OVERFILLED_ROOT_CANAL","BROKEN_ENDO_INSTRUMENT"),
        note="RCT-PEARL: periapical RCT dataset with treated-tooth polygons, filling-instance polygons, apex keypoints, filling-quality labels, separated instruments and missed canals. Files restricted; never assume unattended access.",
    ),
    "mouthcare_full": TrainingSource(
        key="mouthcare_full",
        access="gated_huggingface_auto_approval",
        locator="MouthCare/intraoral-sample",
        modality="INTRAORAL_PHOTO",
        target_signals=("VISIBLE_CARIES","CALCULUS","GINGIVAL_INFLAMMATION","DENTAL_RESTORATION"),
        note="Evaluation sample: 480 images/80 patients, patient-disjoint split, 3,632 dentist-authored polygons. Full collection is 18,000 images/3,000 patient series and 122,877 polygons; do not mix patient series across holdout/train.",
    ),
    "mio_periodontal": TrainingSource(
        key="mio_periodontal",
        access="public_zenodo",
        locator="https://zenodo.org/records/22047269",
        modality="INTRAORAL_PHOTO",
        target_signals=("GINGIVAL_INFLAMMATION","PERIODONTITIS_IMAGE_LEVEL"),
        note="MIO 2026: 765 intraoral photographs independently classified by trained dental professionals as healthy gingiva, gingivitis or periodontitis. Image-level classification only; never use as lesion localization GT.",
    ),
    "roboflow_lesi_intraoral": TrainingSource(
        key="roboflow_lesi_intraoral",
        access="public_dataset_export_required",
        locator="https://universe.roboflow.com/oelya-s/lesi_intraoral_rgb",
        modality="INTRAORAL_PHOTO",
        target_signals=("VISIBLE_CARIES","CALCULUS","GINGIVAL_INFLAMMATION","ORAL_ULCER_CANDIDATE"),
        note="2026 Roboflow instance-segmentation dataset, CC BY 4.0. Classes include Calculus, Caries, Gingivitis and Ulcer. Verify export/version and class counts before locked-test use.",
    ),
    "brar_pan_periodontal": TrainingSource(
        key="brar_pan_periodontal",
        access="public_figshare",
        locator="https://doi.org/10.6084/m9.figshare.30155974.v3",
        modality="PANORAMIC",
        target_signals=("BONE_LOSS_GENERIC","MISSING_TOOTH","IMPLANT","RESIDUAL_ROOT"),
        note="Expert periodontal panoramic dataset with tooth-level missing teeth, implants, residual roots and adjudicated bone-resorption grading. Grading is not interchangeable with geometric horizontal/vertical subtype localization.",
    ),
    "boneloss_pan769": TrainingSource(
        key="boneloss_pan769",
        access="restricted_zenodo",
        locator="https://zenodo.org/records/21114193",
        modality="PANORAMIC",
        target_signals=("BONE_LOSS_GENERIC",),
        note="769 panoramic radiographs with expert-reviewed CEJ/alveolar-ridge/tooth-crown COCO-compatible annotations. Restricted; use only after access approval and never invent horizontal/vertical subtype labels.",
    ),
    "bitewing_caries_100_multiannotator": TrainingSource(
        key="bitewing_caries_100_multiannotator",
        access="public_mendeley",
        locator="https://data.mendeley.com/datasets/4fbdxs7s7w/1",
        modality="BITEWING",
        target_signals=("CARIES",),
        note="100 bitewings; COCO caries boxes from 8 independent dentist annotators (5 experienced, 3 less experienced). CC BY-NC 3.0. Suitable for caries baseline and annotator-variability analysis.",
    ),
    "periapical_lesions_450": TrainingSource(
        key="periapical_lesions_450",
        access="public_zenodo",
        locator="https://zenodo.org/records/13772918",
        modality="PERIAPICAL",
        target_signals=("APICAL_PERIODONTITIS_PAI",),
        note="450 anterior periapical radiographs classified lesion/no-lesion by five dental specialists. Image-level GT only; never score lesion localization from this source.",
    ),
    "intraoral_caries_6313_open": TrainingSource(
        key="intraoral_caries_6313_open",
        access="public_zenodo",
        locator="https://zenodo.org/records/14827784",
        modality="INTRAORAL_PHOTO",
        target_signals=("VISIBLE_CARIES",),
        note="Public downloadable 2025 release: 6,313 dentist-verified intraoral images with decay localization in YOLO/COCO/VOC/LabelMe. Prefer Benchmarking Dataset.zip for held-out evaluation and preserve patient/view grouping when metadata permits.",
    ),
    "intraoral_lesion_200": TrainingSource(
        key="intraoral_lesion_200",
        access="publication_only_no_verified_download",
        locator="https://pmc.ncbi.nlm.nih.gov/articles/PMC9696071/",
        modality="INTRAORAL_PHOTO",
        target_signals=("CALCULUS","GINGIVAL_INFLAMMATION","DENTAL_ABRASION"),
        note="Study reports 200 original intraoral-camera images with calculus, gingivitis/tartar and worn-surface lesions. Publication evidence only; do not auto-download or use as locked GT until a primary downloadable artifact and license are verified.",
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
