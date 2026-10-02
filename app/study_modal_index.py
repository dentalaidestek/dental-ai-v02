"""Parallel Academic V2 preprocessing entrypoint for Modal.

This module is deliberately isolated from the live web/index worker. It benchmarks
and prepares page text in parallel; publication to the durable DB remains a
separate fail-closed step.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import modal
from pypdf import PdfReader

volume = modal.Volume.from_name("dental-ai-models", create_if_missing=False)
PDF_ROOT = Path("/academic-input")

app = modal.App("dental-academic-index")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements-web.lock")
    .add_local_python_source("app")
)


OCR_CONCURRENCY = int(os.getenv("STUDY_MODAL_OCR_CONCURRENCY", "16"))


@app.function(image=image, cpu=1.0, memory=1024, timeout=300, volumes={"/academic-input": volume})
def extract_page(pdf_name: str, page_number: int) -> dict:
    from app.study_chunking import normalize_extracted_text
    from app.study_index_worker import _text_quality
    started = time.perf_counter()
    reader = PdfReader(str(PDF_ROOT / pdf_name))
    text = normalize_extracted_text(reader.pages[page_number - 1].extract_text())
    ok, reason = _text_quality(text)
    return {"page": page_number, "text": text, "quality_ok": ok, "reason": reason,
            "elapsed_ms": int((time.perf_counter() - started) * 1000)}


@app.function(image=image, cpu=2.0, memory=2048, timeout=300, max_containers=OCR_CONCURRENCY, volumes={"/academic-input": volume})
def ocr_page(pdf_name: str, page_number: int) -> dict:
    from app.study_local_ocr import ocr_material_page
    started = time.perf_counter()
    result = ocr_material_page(PDF_ROOT / pdf_name, mime_type="application/pdf", page_number=page_number)
    return {"page": page_number, "text": result.text, "confidence": result.confidence,
            "visual_only": result.visual_only, "retried": result.retried,
            "layout": result.layout_kind, "ocr_ms": result.elapsed_ms,
            "elapsed_ms": int((time.perf_counter() - started) * 1000)}


@app.local_entrypoint()
def benchmark(pdf: str):
    started = time.perf_counter()
    source = Path(pdf)
    pdf_name = source.name
    remote_path = PDF_ROOT / pdf_name
    with volume.batch_upload(force=True) as batch:
        batch.put_file(source, str(remote_path))
    page_count = len(PdfReader(pdf).pages)
    extracted = list(extract_page.map([pdf_name] * page_count, range(1, page_count + 1)))
    need_ocr = [x["page"] for x in extracted if not x["quality_ok"]]
    ocr = list(ocr_page.map([pdf_name] * len(need_ocr), need_ocr)) if need_ocr else []
    by_page = {x["page"]: x for x in extracted}
    for item in ocr:
        fallback = by_page[item["page"]]["text"]
        if item["visual_only"] or len(item["text"]) < len(fallback):
            item["text"] = fallback
    from app.study_chunking import chunk_dental_page
    chunk_started = time.perf_counter()
    chunks = 0
    chars = 0
    for page in range(1, page_count + 1):
        o = next((x for x in ocr if x["page"] == page), None)
        text = o["text"] if o else by_page[page]["text"]
        made = chunk_dental_page(text)
        chunks += len(made); chars += sum(len(x.text) for x in made)
    chunk_s = time.perf_counter() - chunk_started
    total_s = time.perf_counter() - started
    retries = sum(bool(x["retried"]) for x in ocr)
    visual = sum(bool(x["visual_only"]) for x in ocr)
    print({"pages": page_count, "native_ok": page_count-len(need_ocr), "ocr_pages": len(need_ocr),
           "ocr_retries": retries, "visual_only": visual, "chunks": chunks, "chunk_chars": chars,
           "chunk_seconds_local": round(chunk_s,3), "total_wall_seconds": round(total_s,3),
           "ocr_worker_cap": OCR_CONCURRENCY})
