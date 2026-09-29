from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.study_local_ocr import LOCAL_OCR_ENGINE_VERSION, ocr_material_page


def _font(size: int):
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def test_local_ocr_reads_turkish_and_english_without_provider(tmp_path):
    image = Image.new("RGB", (1600, 700), "white")
    draw = ImageDraw.Draw(image)
    font = _font(52)
    draw.text((60, 70), "ORTODONTİ Angle Sınıf II", fill="black", font=font)
    draw.text((60, 170), "Tedavi endikasyonları değerlendirilir.", fill="black", font=font)
    source = tmp_path / "page.png"
    image.save(source)

    result = ocr_material_page(source, mime_type="image/png", page_number=1)

    assert "ORTODONT" in result.text
    assert "Angle" in result.text
    assert "Tedavi" in result.text
    assert result.confidence >= 35
    assert result.visual_only is False
    assert LOCAL_OCR_ENGINE_VERSION.startswith("tesseract-")


def test_local_ocr_marks_blank_page_visual_only(tmp_path):
    source = tmp_path / "blank.png"
    Image.new("RGB", (1000, 1000), "white").save(source)

    result = ocr_material_page(source, mime_type="image/png", page_number=1)

    assert result.text == ""
    assert result.visual_only is True


def test_local_ocr_renders_only_requested_pdf_page(tmp_path):
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((70, 90), "Ortodonti Angle Sınıf II", fill="black", font=_font(48))
    source = tmp_path / "lecture.pdf"
    image.save(source, "PDF", resolution=150)

    result = ocr_material_page(source, mime_type="application/pdf", page_number=1)

    assert "Ortodonti" in result.text
    assert "Angle" in result.text
    assert result.visual_only is False
