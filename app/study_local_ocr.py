"""Bounded, offline OCR for Academic AI source pages.

The indexer must not upload course pages to an LLM just to recover a missing
PDF text layer.  PDFium renders exactly one requested page and Tesseract reads
it locally with bundled Turkish and English language data.  Both dependencies
ship self-contained wheels, so the Render native runtime needs no apt package.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps


LOCAL_OCR_ENGINE_VERSION = "tesseract-5.5-adaptive-dental-tur-eng-v2"
_DENTAL_WORDS_PATH = Path(__file__).with_name("dental_ocr_words.txt")
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


def _render_pdf_page(
    path: Path, page_number: int, *, dpi: int | None = None, document=None
) -> Image.Image:
    import pypdfium2 as pdfium

    owned_document = document is None
    document = document or pdfium.PdfDocument(str(path))
    page = None
    bitmap = None
    try:
        if page_number < 1 or page_number > len(document):
            raise LocalOCRError(f"OCR_PAGE_OUT_OF_RANGE:{page_number}")
        page = document[page_number - 1]
        width, height = page.get_size()
        requested_dpi = dpi or _int_env("STUDY_V2_LOCAL_OCR_DPI", 150, 120, 240)
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
        if owned_document:
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
    """Normalize OCR without flattening academic structure.

    Preserve line boundaries and meaningful multi-space column gaps so MCQ
    choices, tables and two-column material remain recoverable downstream.
    """
    cleaned: list[str] = []
    blank = False
    for raw in (value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.replace("\t", "    ").strip()
        # Collapse extreme OCR spacing but retain 2+ spaces as a table/column cue.
        line = re.sub(r" {5,}", "    ", line)
        if line:
            cleaned.append(line)
            blank = False
        elif cleaned and not blank:
            cleaned.append("")
            blank = True
    return "\n".join(cleaned).strip()



_MC_OPTION_RE = re.compile(r"^\s*(?:[A-Ea-e][\)\].:-]|[1-9][\)\].:-])\s+")
_LIST_RE = re.compile(r"^\s*(?:[-•▪◦]|\d+[\).])\s+")
_TABLE_GAP_RE = re.compile(r"\S\s{2,}\S")


def _preserve_academic_structure(text: str) -> str:
    """Cheap text-only structure pass; no OCR/model call and no content invention."""
    lines = (text or "").splitlines()
    if not lines:
        return ""
    out: list[str] = []
    for raw in lines:
        line = raw.rstrip()
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        if _MC_OPTION_RE.match(line) or _LIST_RE.match(line) or _TABLE_GAP_RE.search(line):
            out.append(line)
            continue
        # Repair only obvious word hyphenation. Do not merge headings,
        # measurements, options, lists or table-like rows.
        if out and out[-1].endswith("-") and re.match(r"^[a-zçğıöşü]", line):
            out[-1] = out[-1][:-1] + line.lstrip()
        else:
            out.append(line)
    return "\n".join(out).strip()

@dataclass(frozen=True)
class _PageLayout:
    psm: int
    kind: str
    split_x: int | None = None  # normalized 0..10000, independent of probe size


def _detect_page_layout(image: Image.Image) -> _PageLayout:
    """Cheap projection-based layout hint; no OCR/provider call required."""
    import tesserocr

    # Work on a small thumbnail: layout detection should cost milliseconds,
    # not another full-resolution recognition pass.
    probe = image.copy()
    try:
        probe.thumbnail((900, 1200), Image.Resampling.BILINEAR)
        # Ink projection after a conservative threshold. We only need rough
        # occupied regions, not semantic interpretation.
        binary = probe.point(lambda p: 0 if p < 210 else 255, mode="1")
        w, h = binary.size
        if w < 20 or h < 20:
            return _PageLayout(tesserocr.PSM.AUTO, "unknown")
        pix = binary.load()
        col_ink = [sum(1 for y in range(h) if pix[x, y] == 0) for x in range(w)]
        row_ink = [sum(1 for x in range(w) if pix[x, y] == 0) for y in range(h)]
        occupied_rows = sum(v > max(2, w * 0.01) for v in row_ink)
        density = sum(col_ink) / max(1, w * h)

        # A persistent low-ink valley around the middle strongly suggests a
        # two-column article/thesis page.
        mid_lo, mid_hi = int(w * 0.42), int(w * 0.58)
        side = col_ink[int(w * 0.12):int(w * 0.38)] + col_ink[int(w * 0.62):int(w * 0.88)]
        valley = col_ink[mid_lo:mid_hi]
        side_mean = sum(side) / max(1, len(side))
        valley_mean = sum(valley) / max(1, len(valley))
        if occupied_rows > h * 0.35 and side_mean > 0 and valley_mean < side_mean * 0.38:
            return _PageLayout(tesserocr.PSM.AUTO, "two_column", int(((mid_lo + mid_hi) / 2) * 10000 / max(1, w)))

        # Sparse lecture slides/figures benefit from sparse-text segmentation.
        if density < 0.035 or occupied_rows < h * 0.22:
            return _PageLayout(tesserocr.PSM.SPARSE_TEXT, "sparse")

        # Dense thesis/article prose is usually one uniform text block.
        if occupied_rows > h * 0.45 and density > 0.06:
            return _PageLayout(tesserocr.PSM.SINGLE_BLOCK, "single_block")

        return _PageLayout(tesserocr.PSM.AUTO, "mixed")
    finally:
        probe.close()


def _deskew_image(image: Image.Image) -> Image.Image:
    """Estimate small skew from a tiny projection probe; no extra OCR pass."""
    probe = image.copy()
    try:
        probe.thumbnail((700, 900), Image.Resampling.BILINEAR)
        binary = probe.point(lambda p: 0 if p < 205 else 255, mode="1")

        def score(angle: float) -> float:
            rotated = binary if angle == 0 else binary.rotate(
                angle, resample=Image.Resampling.NEAREST, expand=False, fillcolor=255
            )
            try:
                w, h = rotated.size
                pix = rotated.load()
                rows = [sum(1 for x in range(w) if pix[x, y] == 0) for y in range(h)]
                if not rows:
                    return 0.0
                mean = sum(rows) / len(rows)
                return sum((v - mean) ** 2 for v in rows) / len(rows)
            finally:
                if rotated is not binary:
                    rotated.close()

        base = score(0.0)
        candidates = [(-3.0, score(-3.0)), (-1.5, score(-1.5)), (1.5, score(1.5)), (3.0, score(3.0))]
        angle, best = max(candidates, key=lambda item: item[1])
        # Require a meaningful projection improvement; otherwise avoid a
        # needless full-resolution rotate on already straight pages.
        if base <= 0 or best < base * 1.10:
            return image.copy()
        return image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=255)
    finally:
        probe.close()


def _recognize_layout(image: Image.Image, *, layout: _PageLayout, timeout_ms: int) -> tuple[str, int]:
    """Preserve reading order for obvious two-column academic pages."""
    import tesserocr

    if layout.kind != "two_column" or not layout.split_x:
        return _recognize(image, psm=layout.psm, timeout_ms=timeout_ms)
    split = int(image.width * (layout.split_x / 10000.0))
    margin = max(8, int(image.width * 0.015))
    split = max(margin * 2, min(image.width - margin * 2, split))
    regions = [
        image.crop((0, 0, min(image.width, split + margin), image.height)),
        image.crop((max(0, split - margin), 0, image.width, image.height)),
    ]
    try:
        results = _recognize_many(
            regions, psm=tesserocr.PSM.SINGLE_BLOCK, timeout_ms=timeout_ms
        )
    finally:
        for region in regions:
            region.close()
    texts = [text for text, _ in results if text]
    confidence = int(sum(conf for _, conf in results) / max(1, len(results)))
    return _normalize_ocr_text("\n\n".join(texts)), confidence


def _recognize_two_columns_selective(
    image: Image.Image, *, layout: _PageLayout, timeout_ms: int
) -> tuple[str, int, tuple[bool, bool], tuple[int, int]]:
    """OCR columns independently and preserve per-column retry quality."""
    import tesserocr

    split = int(image.width * ((layout.split_x or 5000) / 10000.0))
    margin = max(8, int(image.width * 0.015))
    split = max(margin * 2, min(image.width - margin * 2, split))
    regions = [
        image.crop((0, 0, min(image.width, split + margin), image.height)),
        image.crop((max(0, split - margin), 0, image.width, image.height)),
    ]
    try:
        results = [
            _recognize(region, psm=tesserocr.PSM.SINGLE_BLOCK, timeout_ms=timeout_ms)
            for region in regions
        ]
    finally:
        for region in regions:
            region.close()
    weak = tuple(_needs_quality_retry(text, conf) for text, conf in results)
    column_confidences = tuple(int(conf) for _, conf in results)
    texts = [text for text, _ in results if text]
    confidence = int(sum(column_confidences) / max(1, len(column_confidences)))
    return _normalize_ocr_text("\n\n".join(texts)), confidence, weak, column_confidences


def _ocr_anomaly_score(text: str) -> float:
    """Local corruption signal used to spend retry cost only on suspicious OCR."""
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return 1.0
    alnum = sum(ch.isalnum() for ch in compact) / len(compact)
    replacement = sum(ch in "�□■" for ch in compact) / len(compact)
    noisy_tokens = re.findall(r"(?u)\b[^\W\d_]{1}\b|[^\w\s.,;:!?%°µμ+\-/()]+", text or "")
    noise = min(1.0, len(noisy_tokens) / max(1, len((text or "").split())))
    return min(1.0, (1.0 - alnum) * 0.55 + replacement * 3.0 + noise * 0.45)


def _recognize_many(images: list[Image.Image], *, psm, timeout_ms: int) -> list[tuple[str, int]]:
    """Reuse one Tesseract language-model session for multiple page regions."""
    import tesserocr

    results: list[tuple[str, int]] = []
    with tesserocr.PyTessBaseAPI(
        path=str(_TESSDATA_PATH) + "/",
        lang="tur+eng",
        psm=psm,
    ) as api:
        if _DENTAL_WORDS_PATH.exists():
            api.SetVariable("user_words_file", str(_DENTAL_WORDS_PATH))
        api.SetVariable("preserve_interword_spaces", "1")
        for image in images:
            api.SetImage(image)
            if not api.Recognize(timeout=timeout_ms):
                raise LocalOCRError("OCR_RECOGNITION_TIMEOUT")
            results.append((
                _normalize_ocr_text(api.GetUTF8Text()),
                max(0, min(100, int(api.MeanTextConf()))),
            ))
            api.Clear()
    return results


def _recognize(image: Image.Image, *, psm, timeout_ms: int) -> tuple[str, int]:
    import tesserocr
    with tesserocr.PyTessBaseAPI(
        path=str(_TESSDATA_PATH) + "/",
        lang="tur+eng",
        psm=psm,
    ) as api:
        if _DENTAL_WORDS_PATH.exists():
            # Tesseract user_words_file improves recognition of specialty terms
            # without replacing the Turkish/English language models.
            api.SetVariable("user_words_file", str(_DENTAL_WORDS_PATH))
        api.SetVariable("preserve_interword_spaces", "1")
        api.SetImage(image)
        if not api.Recognize(timeout=timeout_ms):
            raise LocalOCRError("OCR_RECOGNITION_TIMEOUT")
        return _normalize_ocr_text(api.GetUTF8Text()), max(0, min(100, int(api.MeanTextConf())))


def _needs_quality_retry(text: str, confidence: int) -> bool:
    if confidence < _int_env("STUDY_V2_LOCAL_OCR_RETRY_CONFIDENCE", 58, 20, 90):
        return True
    compact = re.sub(r"\\s+", "", text or "")
    if len(compact) < 40:
        # A short but confidently recognized heading/slide label is not by
        # itself evidence that a second full render will recover more text.
        return confidence < 78
    return _ocr_anomaly_score(text) >= 0.34


def ocr_material_page(
    path: Path,
    *,
    mime_type: str,
    page_number: int,
    pdf_document=None,
) -> LocalOCRResult:
    """Adaptive local OCR: cheap first pass, bounded quality retry only when needed."""
    import tesserocr

    fast_dpi = _int_env("STUDY_V2_LOCAL_OCR_DPI", 150, 120, 200)
    retry_dpi = _int_env("STUDY_V2_LOCAL_OCR_RETRY_DPI", 210, 160, 240)
    timeout_ms = _int_env("STUDY_V2_LOCAL_OCR_PAGE_TIMEOUT_MS", 45_000, 5_000, 90_000)

    def load(dpi: int) -> Image.Image:
        if mime_type == "application/pdf":
            return _render_pdf_page(path, page_number, dpi=dpi, document=pdf_document)
        if mime_type in {"image/jpeg", "image/png", "image/webp"}:
            if page_number != 1:
                raise LocalOCRError(f"OCR_PAGE_OUT_OF_RANGE:{page_number}")
            return _load_image(path)
        raise LocalOCRError(f"OCR_UNSUPPORTED_MIME:{mime_type}")

    image = load(fast_dpi)
    try:
        image = ImageOps.autocontrast(image)
        deskewed = _deskew_image(image)
        try:
            layout = _detect_page_layout(deskewed)
            weak_columns = (False, False)
            column_confidences = (0, 0)
            if layout.kind == "two_column":
                text, confidence, weak_columns, column_confidences = _recognize_two_columns_selective(
                    deskewed, layout=layout, timeout_ms=timeout_ms
                )
            else:
                text, confidence = _recognize_layout(deskewed, layout=layout, timeout_ms=timeout_ms)
        finally:
            deskewed.close()
    except LocalOCRError:
        raise
    except RuntimeError as exc:
        code = "OCR_RECOGNITION_TIMEOUT" if "timeout" in str(exc).lower() else "OCR_ENGINE_FAILED"
        raise LocalOCRError(code) from exc
    except Exception as exc:
        raise LocalOCRError(f"OCR_ENGINE_FAILED:{type(exc).__name__}") from exc
    finally:
        image.close()

    # Most clean scans finish above. Spend extra pixels only on weak pages.
    if _needs_quality_retry(text, confidence) and retry_dpi > fast_dpi:
        retry_image = load(retry_dpi)
        try:
            retry_image = ImageOps.autocontrast(retry_image)
            retry_deskewed = _deskew_image(retry_image)
            try:
                retry_layout = _detect_page_layout(retry_deskewed)
                # Preserve explicit column order on retry; other weak layouts
                # use AUTO to avoid repeating a bad specialized segmentation.
                if retry_layout.kind == "two_column" and layout.kind == "two_column" and any(weak_columns):
                    # Re-run only weak columns at high DPI; preserve strong fast-pass
                    # text instead of paying for and potentially degrading both sides.
                    split = int(retry_deskewed.width * ((retry_layout.split_x or 5000) / 10000.0))
                    margin = max(8, int(retry_deskewed.width * 0.015))
                    split = max(margin * 2, min(retry_deskewed.width - margin * 2, split))
                    retry_regions = [
                        retry_deskewed.crop((0, 0, min(retry_deskewed.width, split + margin), retry_deskewed.height)),
                        retry_deskewed.crop((max(0, split - margin), 0, retry_deskewed.width, retry_deskewed.height)),
                    ]
                    try:
                        fast_parts = text.split("\n\n", 1)
                        while len(fast_parts) < 2:
                            fast_parts.append("")
                        confidences = list(column_confidences)
                        for idx, region in enumerate(retry_regions):
                            if not weak_columns[idx]:
                                continue
                            part_text, part_conf = _recognize(
                                region, psm=tesserocr.PSM.SINGLE_BLOCK, timeout_ms=timeout_ms
                            )
                            if part_conf >= confidences[idx] or len(part_text) > len(fast_parts[idx]):
                                fast_parts[idx], confidences[idx] = part_text, part_conf
                        retry_text = _normalize_ocr_text("\n\n".join(fast_parts))
                        retry_confidence = int(sum(confidences) / len(confidences))
                    finally:
                        for region in retry_regions:
                            region.close()
                elif retry_layout.kind == "two_column":
                    retry_text, retry_confidence = _recognize_layout(
                        retry_deskewed, layout=retry_layout, timeout_ms=timeout_ms
                    )
                else:
                    retry_text, retry_confidence = _recognize(
                        retry_deskewed, psm=tesserocr.PSM.AUTO, timeout_ms=timeout_ms
                    )
            finally:
                retry_deskewed.close()
            if retry_confidence > confidence or (
                retry_confidence == confidence and len(retry_text) > len(text)
            ):
                text, confidence = retry_text, retry_confidence
        finally:
            retry_image.close()

    text = _preserve_academic_structure(text)
    minimum_confidence = _int_env("STUDY_V2_LOCAL_OCR_MIN_CONFIDENCE", 35, 0, 90)
    visual_only = not text or confidence < minimum_confidence
    return LocalOCRResult(text=text, confidence=confidence, visual_only=visual_only)
