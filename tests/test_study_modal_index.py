from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "app" / "study_modal_index.py").read_text(encoding="utf-8")

def test_modal_index_benchmark_is_parallel_and_isolated():
    assert "extract_page.map(" in SRC
    assert "volume.batch_upload" in SRC
    assert "[data] * page_count" not in SRC
    assert "pdf_bytes" not in SRC
    assert "ocr_page.map(" in SRC
    assert "max_containers=OCR_CONCURRENCY" in SRC
    assert "run_one_slice" not in SRC
    assert "session" not in SRC.lower()

def test_modal_index_preserves_native_fallback_when_ocr_is_worse():
    assert 'item["visual_only"] or len(item["text"]) < len(fallback)' in SRC
