from pathlib import Path

import pytest
from PIL import Image

from app.clinical_media import sanitize_clinical_media_image


ROOT = Path(__file__).resolve().parents[1]


def test_jpeg_orientation_is_applied_and_identifying_exif_is_removed(tmp_path):
    path = tmp_path / "clinical.jpg"
    exif = Image.Exif()
    exif[274] = 6  # Rotate 90 degrees clockwise.
    exif[315] = "Synthetic dental device"
    Image.new("RGB", (20, 10), "white").save(path, format="JPEG", exif=exif)

    sanitize_clinical_media_image(path, ".jpg", max_pixels=1_000)

    with Image.open(path) as clean:
        assert clean.format == "JPEG"
        assert clean.size == (10, 20)
        assert not dict(clean.getexif())
        assert "exif" not in clean.info
    assert not path.with_name(path.name + ".sanitized").exists()


def test_png_text_metadata_is_not_carried_into_persisted_clinical_image(tmp_path):
    from PIL.PngImagePlugin import PngInfo

    path = tmp_path / "clinical.png"
    metadata = PngInfo()
    metadata.add_text("Author", "Synthetic device owner")
    Image.new("RGBA", (12, 8), (20, 80, 120, 128)).save(path, pnginfo=metadata)

    sanitize_clinical_media_image(path, ".png", max_pixels=1_000)

    with Image.open(path) as clean:
        assert clean.format == "PNG"
        assert clean.mode == "RGBA"
        assert "Author" not in clean.info


def test_webp_is_reencoded_losslessly(tmp_path):
    path = tmp_path / "clinical.webp"
    original = Image.new("RGB", (16, 12), (17, 91, 203))
    original.save(path, format="WEBP", lossless=True)

    sanitize_clinical_media_image(path, ".webp", max_pixels=1_000)

    with Image.open(path) as clean:
        assert clean.format == "WEBP"
        assert clean.size == (16, 12)
        assert clean.convert("RGB").getpixel((0, 0)) == (17, 91, 203)


def test_sanitizer_rejects_extension_mismatch_and_corrupt_image(tmp_path):
    mismatch = tmp_path / "wrong-extension.jpg"
    Image.new("RGB", (8, 8), "white").save(mismatch, format="PNG")
    with pytest.raises(ValueError, match="uzantısı"):
        sanitize_clinical_media_image(mismatch, ".jpg", max_pixels=1_000)

    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"\\xff\\xd8\\xffnot-a-real-jpeg")
    with pytest.raises(ValueError, match="Geçersiz veya bozuk"):
        sanitize_clinical_media_image(corrupt, ".jpg", max_pixels=1_000)


def test_sanitizer_rejects_oversized_and_animated_clinical_images(tmp_path):
    oversized = tmp_path / "large.png"
    Image.new("RGB", (20, 10), "white").save(oversized, format="PNG")
    with pytest.raises(ValueError, match="çözünürlüğü"):
        sanitize_clinical_media_image(oversized, ".png", max_pixels=100)

    animated = tmp_path / "animated.webp"
    first = Image.new("RGB", (8, 8), "white")
    second = Image.new("RGB", (8, 8), "black")
    first.save(animated, format="WEBP", save_all=True, append_images=[second], duration=100, loop=0)
    with pytest.raises(ValueError, match="Hareketli"):
        sanitize_clinical_media_image(animated, ".webp", max_pixels=1_000)


def test_web_and_native_upload_routes_use_the_same_sanitizer_before_persistence():
    main_source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    web_upload = main_source.split("def upload_patient_media", 1)[1].split(
        '@app.get("/patients/{patient_id}/media/{media_id}/file")', 1
    )[0]
    assert "sanitize_clinical_media_image(destination, extension" in web_upload
    assert web_upload.index("sanitize_clinical_media_image(") < web_upload.index("storage_persist_file(")

    mobile_source = (ROOT / "app/mobile_api.py").read_text(encoding="utf-8")
    copy_block = mobile_source.split("def _copy_validated_image", 1)[1].split(
        "class LoginRequest", 1
    )[0]
    assert "sanitize_clinical_media_image(" in copy_block
    upload_block = mobile_source.split('async def mobile_patient_media_upload', 1)[1].split(
        'def _mobile_access_token', 1
    )[0]
    assert "_copy_validated_image(image, destination, MOBILE_MAX_IMAGE_BYTES)" in upload_block
