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
    revision: str | None = None
    sha256: str | None = None


OPTIONAL_MODEL_SOURCES = {
    "yolo31": ModelSource(
        key="yolo31",
        architecture="ultralytics",
        repo_candidates=("gegesay89/dental-findings-yolo-detector",),
        filename="dental_disease_panoramic_yolov8seg/best.pt",
        local_name="dental_findings_31_seg.pt",
        purpose="31-class panoramic findings helper/direct detector",
    ),
    "liodon3": ModelSource(
        key="liodon3",
        architecture="ultralytics_onnx",
        repo_candidates=("liodon-ai/dental-panoramic-detector",),
        filename="best.onnx",
        local_name="liodon_panorama3.onnx",
        purpose="compact panoramic control detector for caries/periapical lesion/impacted tooth",
        revision="93c7037b11275d94cbf6c2f5d1ea86452910dc3a",
        sha256="4cee38b54203634d895ed30a8910f5d7c4cefe22b18f9116b5561d9dd6e83a71",
    ),
    "panoreader_periapical": ModelSource(
        key="panoreader_periapical",
        architecture="ultralytics_onnx",
        repo_candidates=("chemahc94/Dental_012",),
        filename="best.onnx",
        local_name="panoreader_periapical.onnx",
        purpose="one-class periapical-lesion fallback detector",
        revision="53ef2e5396e065d7d4371fc0c208d90830c5cdb6",
        sha256="fd8ff1ec6c50cbb2342a70b7c3689311d3ac77370a9db6fed6db9465eac07f48",
    ),
    "panoreader_toothseg": ModelSource(
        key="panoreader_toothseg",
        architecture="ultralytics_onnx",
        repo_candidates=("chemahc94/Dental-AI-Models",),
        filename="Dental_008/yolov8m_best.onnx",
        local_name="panoreader_toothseg.onnx",
        purpose="alternate tooth segmentation helper",
        revision="05b496bc104c77601f5f472eb00b0fa646b75895",
    ),
    "panoreader_restoration": ModelSource(
        key="panoreader_restoration",
        architecture="onnx_classifier",
        repo_candidates=("chemahc94/Dental_013",),
        filename="best_restoration_model.onnx",
        local_name="panoreader_restoration.onnx",
        purpose="tooth-ROI restoration classifier fallback",
        revision="eafdac009916ef640d4d9c92c128aae40552fde4",
    ),
    "tvem11": ModelSource(
        key="tvem11",
        architecture="maskdino",
        repo_candidates=("Bryceee/Teeth_Visual_Experts_Models",),
        filename="Teeth_Visual_Experts_Maskdino_Swinl_x-ray_11diseases.pth",
        local_name="tvem_11diseases.pth",
        purpose="TVEM 11-disease specialist; deep caries/residual root/pontic",
        revision="29081baac6b09aab4214477e72e80b25ce0a3eef",
    ),
    "tvem_bone_loss": ModelSource(
        key="tvem_bone_loss",
        architecture="maskdino",
        repo_candidates=("Bryceee/Teeth_Visual_Experts_Models",),
        filename="Teeth_Visual_Experts_Maskdino_Swinl_x-ray_bone_loss_1disease.pth",
        local_name="tvem_bone_loss.pth",
        purpose="TVEM generic bone-loss helper",
        revision="a3e5b74ceb23fd947e9b27dfc3980c22fbf33e27",
        sha256="faea0004a39ef2420369066c546df7a29e2e1906c0247ccb45da44eafd629ddc",
    ),
    "tvem_canal_sinus": ModelSource(
        key="tvem_canal_sinus",
        architecture="maskdino",
        repo_candidates=("Bryceee/Teeth_Visual_Experts_Models",),
        filename="Teeth_Visual_Experts_Maskdino_Swinl_panoramic_x-ray_Mandibular_Canal_Maxillary_Sinus.pth",
        local_name="tvem_mandibular_maxillary.pth",
        purpose="TVEM mandibular-canal/maxillary-sinus anatomy helper",
        revision="0c7dd7ef2404da22889210be9e57a69f0d285052",
        sha256="5e4678afd21c7aa5675982227cc7826b220eefbb98b0dc774dd20077b9d41ad6",
    ),
    "tvem_periapical3": ModelSource(
        key="tvem_periapical3",
        architecture="dino",
        repo_candidates=("Bryceee/Teeth_Visual_Experts_Models",),
        filename="Teeth_Visual_Experts_DINO_r50_5scale_x-ray_periapical_lesions_3classes.pth",
        local_name="tvem_periapical3.pth",
        purpose="periapical lesion subtype helper",
        revision="48be5960dafe950c498fba9075b627fa95acba3f",
        sha256="5bd28f3ab57815c74b52176b0a2b4fa6d147d602f8b057ad12f19585814fc8d0",
    ),
}


def optional_model_path(key: str) -> Path:
    source = OPTIONAL_MODEL_SOURCES[key]
    return BASE_DIR / key / source.local_name
