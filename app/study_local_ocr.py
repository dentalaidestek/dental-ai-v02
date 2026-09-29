"""Bounded, offline OCR for Academic AI source pages.

The indexer must not upload course pages to an LLM just to recover a missing
PDF text layer.  PDFium renders exactly one requested page and Tesseract reads
it locally with bundled Turkish and English language data.  Both dependencies
ship self-contained wheels, so the Render native runtime needs no apt package.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps


LOCAL_OCR_ENGINE_VERSION = "tesseract-5.5-fast-tur-eng-v1"
_TESSDATA_PATH = Path(__file__).with_name("tessdata")


class LocalOCRError(RuntimeError):
    """Raised when a source page cannot safely be rendered or recognized."""


@dataclass(frozen=True)
class LocalOCRResult:
    text: str
    confidence: int
    visual_only: bool


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(value, high))


def _render_pdf_page(path: Path, page_number: int) -> Image.Image:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    page = None
    bitmap = None
    try:
        if page_number < 1 or page_number > len(document):
            raise LocalOCRError(f"OCR_PAGE_OUT_OF_RANGE:{page_number}")
        page = document[page_number - 1]
        width, height = page.get_size()
        requested_dpi = _int_env("STUDY_V2_LOCAL_OCR_DPI", 180, 120, 240)
        max_pixels = _int_env("STUDY_V2_LOCAL_OCR_MAX_PIXELS", 6_000_000, 1_000_000, 12_000_000)
        scale = requested_dpi / 72.0
        projected = max(1.0, width * scale) * max(1.0, height * scale)
        if projected > max_pixels:
            scale *= (max_pixels / projected) ** 0.5
        bitmap = page.render(
            scale=scale,
            grayscale=True,
            optimize_mode="print",
            fill_color=(255, 255, 255, 255),
        )
        return bitmap.to_pil().convert("L").copy()
    except LocalOCRError:
        raise
    except Exception as exc:
        raise LocalOCRError(f"OCR_RENDER_FAILED:{type(exc).__name__}") from exc
    finally:
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()
        document.close()


def _load_image(path: Path) -> Image.Image:
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("L")
            max_pixels = _int_env("STUDY_V2_LOCAL_OCR_MAX_PIXELS", 6_000_000, 1_000_000, 12_000_000)
            if image.width * image.height > max_pixels:
                ratio = (max_pixels / (image.width * image.height)) ** 0.5
                image = image.resize(
                    (max(1, int(image.width * ratio)), max(1, int(image.height * ratio))),
                    Image.Resampling.LANCZOS,
                )
            return image.copy()
    except Exception as exc:
        raise LocalOCRError(f"OCR_IMAGE_LOAD_FAILED:{type(exc).__name__}") from exc


def _normalize_ocr_text(value: str) -> str:
    lines = [" ".join(line.split()) for line in (value or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def ocr_material_page(
    path: Path,
    *,
    mime_type: str,
    page_number: int,
) -> LocalOCRResult:
    """Read one page locally with strict memory, pixel, and time bounds."""
    if mime_type == "application/pdf":
        image = _render_pdf_page(path, page_number)
    elif mime_type in {"image/jpeg", "image/png", "image/webp"}:
        if page_number != 1:
            raise LocalOCRError(f"OCR_PAGE_OUT_OF_RANGE:{page_number}")
        image = _load_image(path)
    else:
        raise LocalOCRError(f"OCR_UNSUPPORTED_MIME:{mime_type}")

    try:
        # Autocontrast improves faint lecture scans without converting diagrams
        # into a lossy hard-threshold image.
        # Do not discard histogram tails: a diagram page can have less than one
        # percent ink, and a percentile cutoff would erase its labels entirely.
        image = ImageOps.autocontrast(image)
        import tesserocr

        timeout_ms = _int_env("STUDY_V2_LOCAL_OCR_PAGE_TIMEOUT_MS", 90_000, 5_000, 120_000)
        with tesserocr.PyTessBaseAPI(
            path=str(_TESSDATA_PATH) + "/",
            lang="tur+eng",
            psm=tesserocr.PSM.AUTO,
        ) as api:
            api.SetImage(image)
            if not api.Recognize(timeout=timeout_ms):
                raise LocalOCRError("OCR_RECOGNITION_TIMEOUT")
            text = _normalize_ocr_text(api.GetUTF8Text())
            confidence = max(0, min(100, int(api.MeanTextConf())))
    except LocalOCRError:
        raise
    except RuntimeError as exc:
        message = str(exc).lower()
        code = "OCR_RECOGNITION_TIMEOUT" if "timeout" in message else "OCR_ENGINE_FAILED"
        raise LocalOCRError(code) from exc
    except Exception as exc:
        raise LocalOCRError(f"OCR_ENGINE_FAILED:{type(exc).__name__}") from exc
    finally:
        image.close()

    minimum_confidence = _int_env("STUDY_V2_LOCAL_OCR_MIN_CONFIDENCE", 35, 0, 90)
    visual_only = not text or confidence < minimum_confidence
    return LocalOCRResult(text=text, confidence=confidence, visual_only=visual_only)
