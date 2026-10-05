from pathlib import Path


def test_modal_enables_bounded_intra_pdf_ocr_parallelism():
    modal_source = Path("modal_academic_indexer.py").read_text(encoding="utf-8")
    worker_source = Path("app/study_index_worker.py").read_text(encoding="utf-8")

    assert 'STUDY_V2_OCR_BATCH_PAGES", "16"' in modal_source
    assert 'STUDY_V2_OCR_PARALLELISM", "4"' in modal_source
    assert 'STUDY_V2_LEASE_SECONDS", "600"' in modal_source
    assert "ThreadPoolExecutor" in worker_source
    assert 'STUDY_V2_OCR_PARALLELISM", 1' in worker_source
    assert "session" not in worker_source[worker_source.index("def recognize(page):"):worker_source.index("with ThreadPoolExecutor", worker_source.index("def recognize(page):"))]
