import inspect

from app.study_retrieval_v2 import _fts_rows, resolve_followup_query


def test_independent_query_is_not_polluted_by_history():
    history = [{"role": "USER", "content": "Angle Sınıf II nedir?"}]
    query = "Mandibular sinirin dallarını ayrıntılı karşılaştır"
    assert resolve_followup_query(query, history) == query


def test_short_followup_includes_near_conversation_context():
    history = [
        {"role": "USER", "content": "Angle Sınıf II bölüm 1'i anlat"},
        {"role": "ASSISTANT", "content": "Bölüm 1 iskeletsel ilişkiyi açıklar."},
    ]
    resolved = resolve_followup_query("Peki neden?", history)
    assert resolved.endswith("Peki neden?")
    assert "Angle Sınıf II bölüm 1'i" in resolved
    assert "iskeletsel ilişki" not in resolved


def test_optional_legacy_semantic_candidates_are_bound_to_embedding_identity():
    # New Academic V2 generations are local-FTS and pass no query vector.
    # If a legacy vector is explicitly supplied, it must still be scoped to
    # the exact embedding identity so incompatible vectors cannot mix.
    source = inspect.getsource(_fts_rows)
    assert "if query_vector:" in source
    assert "c.embedding_provider=:embedding_provider" in source
    assert "c.embedding_model=:embedding_model" in source
    assert "c.embedding_dimensions=:embedding_dimensions" in source


def test_deleted_material_visual_cache_is_evicted_without_touching_other_owner():
    import app.study_retrieval_v2 as retrieval
    with retrieval._PAGE_PDF_CACHE_LOCK:
        retrieval._PAGE_PDF_CACHE.clear()
        retrieval._PAGE_PDF_CACHE[("10:20:v1:ref", 1)] = b"secret"
        retrieval._PAGE_PDF_CACHE[("10:21:v1:ref", 1)] = b"keep"
        retrieval._PAGE_PDF_CACHE[("11:20:v1:ref", 1)] = b"other-owner"
    retrieval.invalidate_retrieval_caches(10, 7, (20,))
    with retrieval._PAGE_PDF_CACHE_LOCK:
        assert ("10:20:v1:ref", 1) not in retrieval._PAGE_PDF_CACHE
        assert ("10:21:v1:ref", 1) in retrieval._PAGE_PDF_CACHE
        assert ("11:20:v1:ref", 1) in retrieval._PAGE_PDF_CACHE
        retrieval._PAGE_PDF_CACHE.clear()


def test_visual_page_cache_enforces_total_byte_budget(monkeypatch):
    import app.study_retrieval_v2 as retrieval
    monkeypatch.setattr(retrieval, "_PAGE_PDF_CACHE_MAX", 10)
    monkeypatch.setattr(retrieval, "_PAGE_PDF_CACHE_MAX_BYTES", 5)
    with retrieval._PAGE_PDF_CACHE_LOCK:
        retrieval._PAGE_PDF_CACHE.clear()
    retrieval._cache_visual_page(("1:1:v:r", 1), b"abc")
    retrieval._cache_visual_page(("1:2:v:r", 1), b"def")
    with retrieval._PAGE_PDF_CACHE_LOCK:
        assert sum(len(v) for v in retrieval._PAGE_PDF_CACHE.values()) <= 5
        assert ("1:1:v:r", 1) not in retrieval._PAGE_PDF_CACHE
        assert ("1:2:v:r", 1) in retrieval._PAGE_PDF_CACHE
        retrieval._PAGE_PDF_CACHE.clear()
