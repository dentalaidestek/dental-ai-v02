from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldSource:
    key: str
    title: str
    locator: str
    access: str
    license_note: str
    annotation_quality: str
    exact_codes: tuple[str, ...]
    partial_codes: tuple[str, ...] = ()
    negative_coverage: str = "unknown"
    allowed_for_training: bool = False
    note: str = ""


# Gold benchmark rule:
# - This catalog is for evaluation only.
# - Sources already used by current model training are blocked from gold evaluation.
# - Generic labels are never promoted to a more specific Vision48 subtype.
SOURCES = {
    "inredd_pan924": GoldSource(
        key="inredd_pan924",
        title="InReDD-Dataset-PAN924",
        locator="https://physionet.org/content/inredd-dataset-pan924/",
        access="credentialed_dua_author_approval",
        license_note="PhysioNet Contributor Review Health Data License 1.5.0",
        annotation_quality=(
            "Three dentomaxillofacial radiologists (~10 years experience); "
            "second-reader review and forced third-reader consensus."
        ),
        exact_codes=(
            "IMPLANT", "CROWN", "PONTIC", "RESIDUAL_ROOT",
            "IMPACTED_THIRD_MOLAR", "ROOT_CANAL_TREATED",
            "ENDO_POST", "CARIES", "IMPACTED_TOOTH",
        ),
        partial_codes=("FILLING", "UNERUPTED_TOOTH"),
        negative_coverage="tooth-level condition labels; exact negative semantics depend on released category flags",
        note="Primary independent gold candidate once access is approved. FDI and tooth geometry are also available.",
    ),
    "hanoi_periapical": GoldSource(
        key="hanoi_periapical",
        title="Panoramic radiographs with periapical lesions",
        locator="https://data.mendeley.com/datasets/kx52tk2ddj/3",
        access="public",
        license_note="CC BY 4.0 according to repository metadata",
        annotation_quality=(
            "3,926 original panoramic radiographs selected from 16,519; "
            "three experienced dentists; majority agreement and IoU consensus."
        ),
        exact_codes=("PERIAPICAL_RADIOLUCENCY",),
        negative_coverage="positive-cohort only; useful for lesion recall/localization, not population specificity",
        note="Use ORIGINAL images only. Never mix augmented copies into gold evaluation.",
    ),
    "boneloss_pan769": GoldSource(
        key="boneloss_pan769",
        title="BoneLoss-PAN769",
        locator="https://zenodo.org/records/21114193",
        access="restricted_request",
        license_note="restricted dataset; obey Zenodo access terms",
        annotation_quality=(
            "Expert CEJ and alveolar-ridge landmarks plus specialist review of tooth-wise crown regions."
        ),
        exact_codes=(),
        partial_codes=("HORIZONTAL_BONE_LOSS", "VERTICAL_BONE_LOSS", "PERI_IMPLANT_BONE_LOSS"),
        negative_coverage="landmark/severity reference; subtype derivation must be pre-specified",
        note="Do not call horizontal/vertical loss directly unless a locked geometry rule derives it.",
    ),
    "toothpix_8655": GoldSource(
        key="toothpix_8655",
        title="ToothPix / multi-focus panoramic pixel-level dataset",
        locator="https://doi.org/10.5281/zenodo.18439233",
        access="restricted_dua_request",
        license_note="restricted; academic/internal commercial R&D under DUA; no redistribution",
        annotation_quality=(
            "8,655 panoramics; >30,000 pixel-level lesion annotations; "
            "20 experienced dental imaging specialists with standardized training."
        ),
        exact_codes=(),
        partial_codes=(
            "CARIES", "IMPACTED_TOOTH", "JAW_RADIOLUCENT_LESION",
            "JAW_RADIOPAQUE_LESION", "MIXED_DENSITY_JAW_LESION",
        ),
        negative_coverage="class list must be checked from granted release before canonical mapping",
        note="High-value broad external-validation source after access is granted.",
    ),
    "tufts1000": GoldSource(
        key="tufts1000",
        title="Tufts Dental Database",
        locator="https://tdd.ece.tufts.edu/",
        access="registration_or_request",
        license_note="follow Tufts dataset terms",
        annotation_quality="1,000 panoramic radiographs with expert teeth/abnormality annotations.",
        exact_codes=(),
        partial_codes=(
            "JAW_RADIOLUCENT_LESION", "JAW_RADIOPAQUE_LESION",
            "MIXED_DENSITY_JAW_LESION",
        ),
        negative_coverage="requires label-dictionary inspection before use",
        note="Useful for external abnormality benchmarking; no speculative canonical remapping.",
    ),
    "dentalopg1550": GoldSource(
        key="dentalopg1550",
        title="DentalOPG-1550",
        locator="https://data.mendeley.com/datasets/rtt726b26d/1",
        access="public_metadata_verify_files",
        license_note="verify dataset terms before local materialization",
        annotation_quality="1,550 clinical panoramics with image-level dental-condition labels.",
        exact_codes=(),
        partial_codes=(
            "CARIES", "BRIDGE", "FILLING", "ROOT_CANAL_TREATED",
            "UNERUPTED_TOOTH", "IMPACTED_THIRD_MOLAR",
            "PERIAPICAL_RADIOLUCENCY",
        ),
        negative_coverage="image-level only unless released files prove localization labels",
        note="Screening/secondary benchmark only; not localization gold unless annotations support it.",
    ),
    "mopg7_v4": GoldSource(
        key="mopg7_v4",
        title="MOPG-7 v4: Multi-Clinic Dental Panoramic Radiograph Dataset with Expert YOLO/COCO Labels",
        locator="https://data.mendeley.com/datasets/r43v452t29/4",
        access="public",
        license_note="CC BY 4.0 in Mendeley v4 metadata",
        annotation_quality=(
            "2,095 anonymized panoramics from four clinics; initial boxes by a licensed dentist, "
            "independent review by a second dental professional, followed by quality control; "
            "9,834 retained boxes."
        ),
        exact_codes=("MISSING_TOOTH", "CROWN", "ROOT_CANAL_TREATED", "CARIES"),
        negative_coverage="seven-class detection release; class-specific negative use requires annotation-completeness audit",
        note=(
            "Use Missing Teeth/Crown/Root Canal/Caries only. Wisdom Teeth is not equivalent to impacted third molar, "
            "and Broken Down Teeth must not be promoted to fracture or residual-root labels."
        ),
    ),
    "dual_labeled_500": GoldSource(
        key="dual_labeled_500",
        title="A dual-labeled dataset for panoramic tooth numbering and state assessment — public 500-image subset",
        locator="https://www.kaggle.com/datasets/zwbzwb12341234/a-dual-labeled-dataset/data",
        access="public_500_author_request_remaining_1500",
        license_note="Kaggle metadata currently reports Unknown; rights review required before redistribution or production use",
        annotation_quality=(
            "Four doctors jointly annotated tooth polygons, FDI numbering and tooth state; difficult boundaries, "
            "numbering and status cases were resolved by joint discussion. Full study contains 2,000 panoramics; "
            "500 images and labels are publicly posted."
        ),
        exact_codes=("SUPERNUMERARY_TOOTH", "FILLING", "CROWN", "ROOT_CANAL_TREATED", "CARIES", "RESIDUAL_ROOT"),
        negative_coverage="all visible teeth receive numbering/state labels in the released annotation scheme; public subset must be audited before scoring negatives",
        note="FDI 91 is the dataset's explicit supernumerary-tooth label. Use only the actually released 500-image subset unless author access is granted.",
    ),
    "pdcnn_perio1747": GoldSource(
        key="pdcnn_perio1747",
        title="PDCNN public panoramic periodontitis dataset",
        locator="https://github.com/PuckBlink/PDCNN",
        access="public_google_drive_via_repository",
        license_note="dataset is publicly released by the authors; repository does not state a clear reuse license, so rights review is required",
        annotation_quality=(
            "1,747 high-resolution panoramic radiographs with tooth-location and professional-doctor periodontitis annotations; "
            "repository publishes separate COCO metadata for bone loss and furcation involvement."
        ),
        exact_codes=("FURCATION_BONE_LOSS",),
        negative_coverage="furcation-involvement annotations are suitable for class-localized scoring; inspect JSON category semantics before negative scoring",
        note="Do not derive horizontal/vertical bone-loss subtype from this source unless a locked geometric rule is validated first.",
    ),
    "contact_m3m_iac": GoldSource(
        key="contact_m3m_iac",
        title="CONTACT: mandibular third-molar / inferior-alveolar-canal contact dataset",
        locator="https://www.kaggle.com/datasets/tugcetoprak92/contact-dataset",
        access="public_kaggle",
        license_note="verify Kaggle dataset license before redistribution",
        annotation_quality=(
            "1,478 M3M/IAC pairs with semantic panoramic annotations; actual root-canal contact determined on CBCT by "
            "three oral and maxillofacial radiologists, with a fourth expert for disagreements."
        ),
        exact_codes=(),
        partial_codes=("MANDIBULAR_CANAL_PROXIMITY",),
        negative_coverage="CBCT-confirmed contact/no-contact; includes difficult panoramic overlap without true CBCT contact",
        note=(
            "High-value risk benchmark. Kept partial because Vision48 says PROXIMITY rather than strict CONTACT; "
            "it can become exact only after the production proximity threshold is explicitly locked to a contact endpoint."
        ),
    ),
}

# Known overlap/leakage sources. These may be useful for training, but they must not
# be used to score the same models as independent gold data.
BLOCKED_FROM_GOLD = {
    "DENTEX",
    "OralXrays-9",
    "liodon-ai/dental-panoramic-xray-yolo",
    "kaggle31",
    "lokisilvres/dental-disease-panoramic-detection-dataset",
    "zenodo14",
    "zenodo:15487430",
}

VISION48 = (
    "MISSING_TOOTH","SUPERNUMERARY_TOOTH","RETAINED_PRIMARY_TOOTH","UNERUPTED_TOOTH",
    "IMPACTED_TOOTH","IMPACTED_THIRD_MOLAR","RESIDUAL_ROOT","FILLING","CROWN",
    "INLAY_ONLAY","BRIDGE","PONTIC","IMPLANT","IMPLANT_SUPPORTED_CROWN",
    "ROOT_CANAL_TREATED","ENDO_POST","UNDERFILLED_ROOT_CANAL","OVERFILLED_ROOT_CANAL",
    "BROKEN_ENDO_INSTRUMENT","APICAL_SURGERY","CARIES","DEEP_CARIES","RECURRENT_CARIES",
    "PERIAPICAL_RADIOLUCENCY","PERIAPICAL_RADIOPACITY","WIDENED_PDL","LOSS_OF_LAMINA_DURA",
    "CONDENSING_OSTEITIS_PATTERN","EXTERNAL_ROOT_RESORPTION","INTERNAL_ROOT_RESORPTION",
    "ROOT_DILACERATION","TOOTH_FRACTURE","ROOT_FRACTURE","JAW_RADIOLUCENT_LESION",
    "JAW_RADIOPAQUE_LESION","MIXED_DENSITY_JAW_LESION","HORIZONTAL_BONE_LOSS",
    "VERTICAL_BONE_LOSS","FURCATION_BONE_LOSS","CALCULUS","PERI_IMPLANT_BONE_LOSS",
    "MAXILLARY_SINUS_MUCOSAL_THICKENING","MAXILLARY_SINUS_OPACIFICATION",
    "MANDIBULAR_CANAL_PROXIMITY","CONDYLAR_FLATTENING","CONDYLAR_EROSION",
    "CONDYLAR_ASYMMETRY","ORTHODONTIC_APPLIANCE",
)

def coverage():
    out = {code: {"exact": [], "partial": []} for code in VISION48}
    for src in SOURCES.values():
        for code in src.exact_codes:
            out[code]["exact"].append(src.key)
        for code in src.partial_codes:
            out[code]["partial"].append(src.key)
    return out

assert len(VISION48) == 48
assert all(not src.allowed_for_training for src in SOURCES.values())
assert set(coverage()) == set(VISION48)