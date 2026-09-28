import inspect

from app.study_retrieval_v2 import _hybrid_rows, resolve_followup_query


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
    assert resolved.startswith("Peki neden?")
    assert "iskeletsel ilişki" in resolved


def test_semantic_candidates_are_bound_to_embedding_identity():
    source = inspect.getsource(_hybrid_rows)
    assert "c.embedding_provider=:embedding_provider" in source
    assert "c.embedding_model=:embedding_model" in source
    assert "c.embedding_dimensions=:embedding_dimensions" in source
