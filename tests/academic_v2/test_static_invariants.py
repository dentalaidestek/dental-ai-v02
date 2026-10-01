from pathlib import Path
import ast
import re

ROOT = Path(__file__).resolve().parents[2]
retrieval = (ROOT / "app/study_retrieval_v2.py").read_text(encoding="utf-8")
generation = (ROOT / "app/study_ai_v2.py").read_text(encoding="utf-8")
ocr = (ROOT / "app/study_local_ocr.py").read_text(encoding="utf-8")
chunking = (ROOT / "app/study_chunking.py").read_text(encoding="utf-8")

# Parse first: catches syntax/indentation damage without importing production deps.
ast.parse(retrieval)
ast.parse(generation)
ast.parse(ocr)
ast.parse(chunking)

# A short standalone dental question must not become a follow-up merely due to length.
assert "len(clean.split()) <= 3" not in retrieval
assert "dependent = bool(_FOLLOWUP_RE.search(clean))" in retrieval

# Exhaustive question requests must bypass semantic top-k and support bounded continuation.
assert "_is_exhaustive_question_request" in retrieval
assert "_question_rows" in retrieval
assert "question_limit = 16" in retrieval
assert "if exhaustive_questions:" in retrieval
assert "else:" in retrieval[retrieval.index("if exhaustive_questions:"):retrieval.index("precise_query = _fts_query") + 80]
assert "continuation_cursor" in retrieval
assert "ACADEMIC_Q_CURSOR" in retrieval

# Repeated source-page attachments must not force a full PDF parse every time.
assert "_PAGE_PDF_CACHE_MAX" in retrieval
assert "_PAGE_PDF_CACHE.get(cache_key)" in retrieval

# Academic V2 generation is one Gemini model and one external call, with no fallback chain.
assert 'ACADEMIC_V2_MODEL = "gemini-3.5-flash-lite"' in generation
assert "get_generation_targets" not in generation
assert "if attempted_api_calls >= 1:" in generation
assert "if emitted:" in generation
assert "generation target selected" in generation
assert "classify_dental_intent" in generation
assert "_INTENT_RESPONSE_RULES" in generation
assert "Sen arama/retrieval yapma" in generation
assert "if not retrieval.evidence_sufficient:" in generation
assert "Eksik başlıklar tamamlama görevi değildir" in generation
assert "class EvidenceSufficiency" in retrieval
assert "def _evidence_sufficiency" in retrieval
assert "result.evidence_sufficient = sufficiency.sufficient" in retrieval
assert "DentalSemanticFeatures" in retrieval

# OCR stays local/adaptive and preserves academic/dental structure.
assert "_detect_page_layout" in ocr
assert "PSM.SPARSE_TEXT" in ocr
assert "PSM.SINGLE_BLOCK" in ocr
assert "STUDY_V2_LOCAL_OCR_RETRY_DPI" in ocr
assert "dental_ocr_words.txt" in ocr
assert "pdf_document=None" in ocr
assert "owned_document = document is None" in ocr
assert "semantic_kinds" in retrieval
assert 'meta.get("kinds")' in retrieval
assert "_split_mcq_blocks" in chunking
assert "inherited_section_title" in chunking
assert "_MCQ_EXPLANATION_RE" in chunking
assert '"QUESTION"' in chunking
assert "c.content_kind = 'QUESTION'" in retrieval
assert "_fts_query" in retrieval
assert " OR " in retrieval
assert "embed_text(" not in retrieval
worker = (ROOT / "app/study_index_worker.py").read_text(encoding="utf-8")
jobs = (ROOT / "app/study_index_jobs.py").read_text(encoding="utf-8")
ast.parse(worker)
ast.parse(jobs)
assert '"retrieval_profile": "fts-local-v1"' in worker
assert 'return "VERIFY"' in worker
assert "require_embeddings=False" in worker
assert 'STUDY_V2_PARSE_BATCH_PAGES", 32' in worker
assert 'STUDY_V2_CHUNK_BATCH_PAGES", 32' in worker
assert "session.add_all(pending)" in worker
assert "inherited_section_title=inherited_title" in worker
assert "retrieval_enrichment_text(semantic_source, features=features)" in worker
parse_slice = worker[worker.index("def _extract_pdf_slice"):worker.index("def _chunk_slice")]
assert "session.close()" not in parse_slice
assert "require_embeddings: bool = True" in jobs

print("Academic V2 static invariants: OK")
