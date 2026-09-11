from __future__ import annotations

import os
import threading
from pathlib import Path

MODEL_PATH = Path(
    os.getenv(
        "DENTAL_VISION_MODEL_PATH",
        str(
            Path(__file__).resolve().parent.parent
            / "models"
            / "vision"
            / "YOLOv11x-seg.pt"
        ),
    )
).expanduser()

_MODEL = None
_LOCK = threading.Lock()


class VisionError(RuntimeError):
    pass


def model_available() -> bool:
    return MODEL_PATH.is_file()


def get_model():
    global _MODEL

    if _MODEL is not None:
        return _MODEL

    with _LOCK:
        if _MODEL is not None:
            return _MODEL

        if not MODEL_PATH.is_file():
            raise VisionError(f"Model bulunamadı: {MODEL_PATH}")

        try:
            from ultralytics import YOLO
            _MODEL = YOLO(str(MODEL_PATH))
        except Exception as exc:
            raise VisionError(f"Model yüklenemedi: {exc}") from exc

        return _MODEL


def analyze(image_path: str) -> dict:
    model = get_model()

    try:
        result = model.predict(
            source=image_path,
            imgsz=1280,
            conf=0.50,
            iou=0.45,
            verbose=False,
        )[0]
    except Exception as exc:
        raise VisionError(f"Analiz başarısız: {exc}") from exc

    teeth = []

    if result.boxes is not None:
        boxes = result.boxes.xyxy.detach().cpu().numpy()
        scores = result.boxes.conf.detach().cpu().numpy()
        classes = result.boxes.cls.detach().cpu().numpy().astype(int)
        names = result.names

        for box, score, class_id in zip(boxes, scores, classes):
            if isinstance(names, dict):
                label = names.get(class_id, str(class_id))
            else:
                label = names[class_id]

            try:
                fdi = int(str(label))
            except Exception:
                fdi = str(label)

            teeth.append(
                {
                    "fdi": fdi,
                    "confidence": round(float(score), 4),
                    "bbox": [
                        round(float(box[0]), 1),
                        round(float(box[1]), 1),
                        round(float(box[2]), 1),
                        round(float(box[3]), 1),
                    ],
                }
            )

    teeth.sort(key=lambda x: str(x["fdi"]))

    return {
        "engine": "dental_ai_vision_motor_1",
        "tooth_count": len(teeth),
        "unique_fdi_count": len({str(x["fdi"]) for x in teeth}),
        "has_segmentation": result.masks is not None,
        "teeth": teeth,
    }
