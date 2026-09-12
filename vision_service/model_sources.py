from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent / "models" / "vision" / "optional"


@dataclass(frozen=True)
class ModelSource:
    key: str
    architecture: str
    repo_candidates: tuple[str, ...]
    filename: str
    local_name: str
    purpose: str


OPTIONAL_MODEL_SOURCES = {
    "yolo31": ModelSource(
        key="yolo31",
        architecture="ultralytics",
        repo_candidates=("gegesay89/dental-findings-yolo-detector",),
        filename="dental_disease_panoramic_yolov8seg/best.pt",
        local_name="dental_findings_31_seg.pt",
        purpose="31-class panoramic findings helper/direct detector",
    ),
    "panoreader_boneloss": ModelSource(
        key="panoreader_boneloss",
        architecture="ultralytics",
        repo_candidates=("chemahc94/dental-boneloss", "schemahc94/dental-boneloss"),
        filename="best.pt",
        local_name="panoreader_boneloss.pt",
        purpose="generic alveolar bone-loss helper",
    ),
    "panoreader_periapical": ModelSource(
        key="panoreader_periapical",
        architecture="ultralytics",
        repo_candidates=("chemahc94/dental-periapical", "schemahc94/dental-periapical"),
        filename="best.pt",
        local_name="panoreader_periapical.pt",
        purpose="periapical lesion fallback detector",
    ),
    "panoreader_toothseg": ModelSource(
        key="panoreader_toothseg",
        architecture="ultralytics",
        repo_candidates=("chemahc94/dental-seg", "schemahc94/dental-seg"),
        filename="yolov8m-seg.pt",
        local_name="panoreader_toothseg.pt",
        purpose="alternate tooth segmentation helper",
    ),
    "panoreader_restoration": ModelSource(
        key="panoreader_restoration",
        architecture="torchvision_state_dict",
        repo_candidates=("chemahc94/dental-restoration", "schemahc94/dental-restoration"),
        filename="best.pt",
        local_name="panoreader_restoration.pt",
        purpose="tooth-ROI restoration classifier fallback",
    ),
    "tvem11": ModelSource(
        key="tvem11",
        architecture="maskdino",
        repo_candidates=("Bryceee/Teeth_Visual_Experts_Models",),
        filename="Teeth_Visual_Experts_Maskdino_Swinl_x-ray_11diseases.pth",
        local_name="tvem_11diseases.pth",
        purpose="TVEM 11-disease specialist; deep caries/residual root/pontic",
    ),
    "tvem_bone_loss": ModelSource(
        key="tvem_bone_loss",
        architecture="maskdino",
        repo_candidates=("Bryceee/Teeth_Visual_Experts_Models",),
        filename="Teeth_Visual_Experts_Maskdino_Swinl_x-ray_bone_loss_1disease.pth",
        local_name="tvem_bone_loss.pth",
        purpose="TVEM generic bone-loss helper",
    ),
    "tvem_canal_sinus": ModelSource(
        key="tvem_canal_sinus",
        architecture="maskdino",
        repo_candidates=("Bryceee/Teeth_Visual_Experts_Models",),
        filename="Teeth_Visual_Experts_Maskdino_Swinl_panoramic_x-ray_Mandibular_Canal_Maxillary_Sinus.pth",
        local_name="tvem_mandibular_maxillary.pth",
        purpose="TVEM mandibular-canal/maxillary-sinus anatomy helper",
    ),
    "tvem_periapical3": ModelSource(
        key="tvem_periapical3",
        architecture="dino",
        repo_candidates=("Bryceee/Teeth_Visual_Experts_Models",),
        filename="Teeth_Visual_Experts_DINO_r50_5scale_x-ray_periapical_lesions_3classes.pth",
        local_name="tvem_periapical3.pth",
        purpose="periapical lesion subtype helper",
    ),
}


def optional_model_path(key: str) -> Path:
    source = OPTIONAL_MODEL_SOURCES[key]
    return BASE_DIR / key / source.local_name
