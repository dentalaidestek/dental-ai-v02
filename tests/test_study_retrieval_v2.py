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
