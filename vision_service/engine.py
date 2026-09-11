from __future__ import annotations

import os
import resource
import threading
import time
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


def _rss_mb() -> float:
    try:
        return round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            1,
        )
    except Exception:
        return -1.0


def _trace(stage: str, **fields) -> None:
    parts = [
        "[VISION_TRACE]",
        f"stage={stage}",
        f"rss_mb={_rss_mb()}",
    ]

    for key, value in fields.items():
        parts.append(f"{key}={value}")

    print(" ".join(parts), flush=True)


def model_available() -> bool:
    return MODEL_PATH.is_file()


def get_model():
    global _MODEL

    _trace(
        "get_model_enter",
        cached=_MODEL is not None,
        model_exists=MODEL_PATH.is_file(),
    )

    if _MODEL is not None:
        _trace("get_model_cached")
        return _MODEL

    with _LOCK:
        if _MODEL is not None:
            _trace("get_model_cached_after_lock")
            return _MODEL

        if not MODEL_PATH.is_file():
            _trace("model_file_missing")
            raise VisionError(f"Model bulunamadı: {MODEL_PATH}")

        try:
            _trace("torch_import_start")
            t_torch = time.perf_counter()

            import torch

            _trace(
                "torch_import_ok",
                seconds=round(time.perf_counter() - t_torch, 3),
                torch_version=torch.__version__,
            )

            _trace("ultralytics_import_start")
            t0 = time.perf_counter()

            from ultralytics import YOLO

            _trace(
                "ultralytics_import_ok",
                seconds=round(time.perf_counter() - t0, 3),
            )

            _trace("yolo_load_start")
            t1 = time.perf_counter()

            _MODEL = YOLO(str(MODEL_PATH))

            _trace(
                "yolo_load_ok",
                seconds=round(time.perf_counter() - t1, 3),
            )

        except Exception as exc:
            _trace(
                "yolo_load_error",
                error_type=type(exc).__name__,
            )
            raise VisionError(
                f"Model yüklenemedi: {exc}"
            ) from exc

        return _MODEL


def analyze(image_path: str) -> dict:
    _trace("analyze_enter")

    model = get_model()

    _trace("predict_start", imgsz=1280, conf=0.50, iou=0.45)
    started = time.perf_counter()

    try:
        result = model.predict(
            source=image_path,
            imgsz=1280,
            conf=0.50,
            iou=0.45,
            verbose=False,
        )[0]

        box_count = (
            len(result.boxes)
            if result.boxes is not None
            else 0
        )

        _trace(
            "predict_ok",
            seconds=round(time.perf_counter() - started, 3),
            boxes=box_count,
            masks=result.masks is not None,
        )

    except Exception as exc:
        _trace(
            "predict_error",
            error_type=type(exc).__name__,
            seconds=round(time.perf_counter() - started, 3),
        )
        raise VisionError(
            f"Analiz başarısız: {exc}"
        ) from exc

    teeth = []

    if result.boxes is not None:
        boxes = result.boxes.xyxy.detach().cpu().numpy()
        scores = result.boxes.conf.detach().cpu().numpy()
        classes = (
            result.boxes.cls
            .detach()
            .cpu()
            .numpy()
            .astype(int)
        )

        names = result.names

        for box, score, class_id in zip(
            boxes,
            scores,
            classes,
        ):
            if isinstance(names, dict):
                label = names.get(
                    class_id,
                    str(class_id),
                )
            else:
                label = names[class_id]

            try:
                fdi = int(str(label))
            except Exception:
                fdi = str(label)

            teeth.append(
                {
                    "fdi": fdi,
                    "confidence": round(
                        float(score),
                        4,
                    ),
                    "bbox": [
                        round(float(box[0]), 1),
                        round(float(box[1]), 1),
                        round(float(box[2]), 1),
                        round(float(box[3]), 1),
                    ],
                }
            )

    teeth.sort(
        key=lambda x: str(x["fdi"])
    )

    _trace(
        "analyze_complete",
        teeth=len(teeth),
        unique_fdi=len(
            {str(x["fdi"]) for x in teeth}
        ),
    )

    return {
        "engine": "dental_ai_vision_motor_1",
        "tooth_count": len(teeth),
        "unique_fdi_count": len(
            {str(x["fdi"]) for x in teeth}
        ),
        "has_segmentation": (
            result.masks is not None
        ),
        "teeth": teeth,
    }
