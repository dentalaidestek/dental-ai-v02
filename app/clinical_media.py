"""Shared validation and privacy sanitization for clinical image uploads.

Only decoded pixel data and a bounded color profile are persisted. EXIF/XMP
and other container metadata are deliberately not copied to the output file.
"""
from pathlib import Path

from PIL import Image, ImageOps


_EXPECTED_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}


def sanitize_clinical_media_image(
    path: Path,
    extension: str,
    max_pixels: int = 40_000_000,
) -> None:
    """Validate a still image, apply EXIF orientation, and strip identifying metadata.

    The caller owns byte-count enforcement while streaming the upload. This
    helper bounds decoded pixels, rejects animated containers, verifies that
    the extension matches the actual image format, and atomically replaces the
    original with a metadata-clean encoding. JPEGs are saved at high quality
    without chroma subsampling; WebP is saved losslessly so radiographic detail
    is not needlessly degraded.
    """
    normalized_extension = (extension or "").lower()
    expected_format = _EXPECTED_FORMATS.get(normalized_extension)
    if expected_format is None:
        raise ValueError("Desteklenmeyen klinik görüntü formatı.")
    if not isinstance(max_pixels, int) or isinstance(max_pixels, bool) or max_pixels <= 0:
        raise ValueError("Geçersiz görüntü çözünürlük sınırı.")

    temporary = path.with_name(path.name + ".sanitized")
    try:
        with Image.open(path) as probe:
            width, height = probe.size
            if probe.format != expected_format:
                raise ValueError("Dosya uzantısı görüntü formatıyla eşleşmiyor.")
            if width <= 0 or height <= 0 or width * height > max_pixels:
                raise ValueError("Görüntü çözünürlüğü çok büyük.")
            if getattr(probe, "n_frames", 1) != 1:
                raise ValueError("Hareketli klinik görüntüler desteklenmiyor.")
            probe.verify()

        with Image.open(path) as original:
            if original.format != expected_format:
                raise ValueError("Dosya uzantısı görüntü formatıyla eşleşmiyor.")
            oriented = ImageOps.exif_transpose(original)
            mode = "RGB" if expected_format == "JPEG" else (
                "RGBA" if "A" in oriented.getbands() else "RGB"
            )
            pixels = oriented.convert(mode)
            clean = Image.new(mode, pixels.size)
            clean.paste(pixels)

            save_options = {}
            icc_profile = original.info.get("icc_profile")
            if isinstance(icc_profile, bytes) and 0 < len(icc_profile) <= 4 * 1024 * 1024:
                # ICC affects color interpretation, unlike EXIF device/location data.
                save_options["icc_profile"] = icc_profile
            if expected_format == "JPEG":
                save_options.update(quality=95, optimize=True, subsampling=0)
            elif expected_format == "WEBP":
                save_options.update(lossless=True, method=6)
            elif expected_format == "PNG":
                save_options.update(optimize=True)

            clean.save(temporary, format=expected_format, **save_options)
            temporary.replace(path)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Geçersiz veya bozuk klinik görüntü dosyası.") from exc
    finally:
        temporary.unlink(missing_ok=True)
