from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.study_local_ocr import LOCAL_OCR_ENGINE_VERSION, ocr_material_page


def _font(size: int):
    candidates = (
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
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


def test_higher_confidence_empty_or_partial_retry_cannot_erase_page_text():
    from app.study_local_ocr import _prefer_ocr_retry
    page='Soru 14. Çenelerin açma hareketi? A) Şık B) Şık\n'*30
    assert not _prefer_ocr_retry(page,51,'',95)
    assert not _prefer_ocr_retry(page,62,'14. Son soru A) Şık',91)
    assert _prefer_ocr_retry(page,51,page.replace('Şık','Seçenek'),80)


def test_failed_quality_retry_preserves_weak_search_text_and_marks_it_unreliable(monkeypatch):
    from types import SimpleNamespace
    import app.study_local_ocr as module
    page='18. Pubertal büyüme atılımı\n19. El bilek kemikleri\n'*20
    monkeypatch.setattr(module,'_render_pdf_page',lambda *a,**k:Image.new('L',(200,300),255))
    monkeypatch.setattr(module,'_orientation_candidate',lambda im:im.copy())
    monkeypatch.setattr(module,'_deskew_image',lambda im:im.copy())
    monkeypatch.setattr(module,'_detect_page_layout',lambda im:SimpleNamespace(kind='single_block',psm=6))
    monkeypatch.setattr(module,'_recognize_layout',lambda *a,**k:(page,51))
    monkeypatch.setattr(module,'_recognize',lambda *a,**k:('',95))
    result=module.ocr_material_page(Path('synthetic.pdf'),mime_type='application/pdf',page_number=4)
    assert result.text==page.strip() and result.confidence==51
    assert result.retried and result.visual_only
