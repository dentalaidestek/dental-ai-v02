import inspect
import pytest

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


def test_visual_request_limits_original_pages_and_combined_payload(monkeypatch):
    from unittest.mock import Mock
    import app.study_retrieval_v2 as retrieval
    monkeypatch.setattr(retrieval,'_VISUAL_REQUEST_MAX_BYTES',10)
    sources=[dict(owner_user_id=17,material_id=1,index_version='v1',reference='ref',
                  page_number=i,mime_type='application/pdf',display_name='fixture') for i in range(1,41)]
    with retrieval._PAGE_PDF_CACHE_LOCK:
        retrieval._PAGE_PDF_CACHE.clear()
        for source in sources:
            retrieval._PAGE_PDF_CACHE[('17:1:v1:ref',source['page_number'])]=b'123'
    db=Mock(side_effect=AssertionError('cached pages must not perform storage or database I/O'))
    try:
        result=retrieval.RetrievalResult(visual_sources=sources[:2],evidence_sufficient=True,source_coverage_complete=True)
        retrieval.materialize_visual_sources(db,result)
        assert result.source_coverage_complete and len(result.attachments)==2
        result=retrieval.RetrievalResult(visual_sources=sources,evidence_sufficient=True,source_coverage_complete=True)
        retrieval.materialize_visual_sources(db,result)
        assert len(result.attachments)==3
        assert sum(len(a['data']) for a in result.attachments)==9
        assert not result.source_coverage_complete
        monkeypatch.setattr(retrieval,'_VISUAL_REQUEST_MAX_BYTES',100)
        result=retrieval.RetrievalResult(visual_sources=sources,evidence_sufficient=True)
        retrieval.materialize_visual_sources(db,result)
        assert len(result.attachments)==32
        assert sum(len(a['data']) for a in result.attachments)==96
        db.assert_not_called()
    finally:
        with retrieval._PAGE_PDF_CACHE_LOCK:
            retrieval._PAGE_PDF_CACHE.clear()


def test_account_erasure_evicts_only_erased_owner_visual_cache():
    import app.study_retrieval_v2 as retrieval
    with retrieval._PAGE_PDF_CACHE_LOCK:
        retrieval._PAGE_PDF_CACHE.clear()
        retrieval._PAGE_PDF_CACHE[("31:1:v:r", 1)] = b"erase"
        retrieval._PAGE_PDF_CACHE[("31:2:v:r", 2)] = b"erase-too"
        retrieval._PAGE_PDF_CACHE[("32:1:v:r", 1)] = b"keep"
    retrieval.invalidate_user_retrieval_caches(31)
    with retrieval._PAGE_PDF_CACHE_LOCK:
        assert all(not key[0].startswith("31:") for key in retrieval._PAGE_PDF_CACHE)
        assert ("32:1:v:r", 1) in retrieval._PAGE_PDF_CACHE
        retrieval._PAGE_PDF_CACHE.clear()


@pytest.mark.parametrize('evict_all', [False, True])
def test_visual_materialization_pins_cached_pages_during_its_own_lru_evictions(monkeypatch, evict_all):
    from unittest.mock import Mock
    from contextlib import nullcontext
    import app.study_retrieval_v2 as retrieval
    monkeypatch.setattr(retrieval, '_PAGE_PDF_CACHE_MAX', 12)
    sources = [dict(owner_user_id=17, material_id=1, index_version='v1', reference='ref',
                    page_number=n, mime_type='application/pdf', display_name='fixture') for n in range(1,17)]
    with retrieval._PAGE_PDF_CACHE_LOCK:
        retrieval._PAGE_PDF_CACHE.clear()
        for n in range(5,17):
            retrieval._PAGE_PDF_CACHE[('17:1:v1:ref',n)] = f'page-{n}'.encode()
    session = Mock()
    # Only the four cache misses are hydrated. Adding them to the 12-slot LRU
    # evicts pages 5–8 before the materializer reaches those original hits.
    def hydrate():
        if evict_all:  # Another worker evicts the original hits during DB I/O.
            with retrieval._PAGE_PDF_CACHE_LOCK:
                retrieval._PAGE_PDF_CACHE.clear()
        return [(1,n,'ref','application/pdf','fixture','v1',f'page-{n}'.encode(),0) for n in range(1,5)]
    session.exec.return_value.all.side_effect = hydrate
    result = retrieval.RetrievalResult(visual_sources=sources, evidence_sufficient=True,
                                       source_coverage_complete=True)
    try:
        retrieval.materialize_visual_sources(lambda:nullcontext(session),result)
        assert {a['page_number'] for a in result.attachments} == set(range(1,17))
        assert result.source_coverage_complete
        session.exec.assert_called_once()
        assert len(retrieval._PAGE_PDF_CACHE) <= 12
        # A second preparation must not append duplicates or consume the byte
        # budget twice, even if another worker has evicted every global page.
        with retrieval._PAGE_PDF_CACHE_LOCK:
            retrieval._PAGE_PDF_CACHE.clear()
        retrieval.materialize_visual_sources(Mock(side_effect=AssertionError('already prepared')),result)
        assert len(result.attachments)==16 and result.source_coverage_complete
    finally:
        with retrieval._PAGE_PDF_CACHE_LOCK:
            retrieval._PAGE_PDF_CACHE.clear()
