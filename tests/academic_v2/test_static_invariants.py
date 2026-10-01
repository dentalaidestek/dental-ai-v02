from pathlib import Path
import ast
import re

ROOT = Path(__file__).resolve().parents[2]
retrieval = (ROOT / "app/study_retrieval_v2.py").read_text(encoding="utf-8")
generation = (ROOT / "app/study_ai_v2.py").read_text(encoding="utf-8")

# Parse first: catches syntax/indentation damage without importing production deps.
ast.parse(retrieval)
ast.parse(generation)

# A short standalone dental question must not become a follow-up merely due to length.
assert "len(clean.split()) <= 3" not in retrieval
assert "dependent = bool(_FOLLOWUP_RE.search(clean))" in retrieval

# Exhaustive question requests must bypass semantic top-k and support bounded continuation.
assert "_is_exhaustive_question_request" in retrieval
assert "_question_rows" in retrieval
assert "question_limit = 16" in retrieval
assert "if not exhaustive_questions:" in retrieval
assert "continuation_cursor" in retrieval
assert "ACADEMIC_Q_CURSOR" in retrieval

# Repeated source-page attachments must not force a full PDF parse every time.
assert "_PAGE_PDF_CACHE_MAX" in retrieval
assert "_PAGE_PDF_CACHE.get(cache_key)" in retrieval

# Generation remains bounded: primary plus at most one fallback, never provider mixing after output.
assert "if attempted_api_calls >= 2:" in generation
assert "if emitted:" in generation
assert "generation target selected" in generation
assert "generation target skipped" in generation

print("Academic V2 static invariants: OK")
