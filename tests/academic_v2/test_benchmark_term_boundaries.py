"""Benchmark term checks must distinguish inflection from arbitrary substrings."""
from scripts.benchmark_multiturn_continuity_50k import has_term, n


def test_term_boundaries_and_nominal_inflections():
    for text, term in [('lütfen', 'Le'), ('table', 'Le'),
                       ('irreversible', 'reversible'), ('çocukça', 'çocuk')]:
        assert not has_term(n(text), term)
    for text, term in [('avülsiyonu', 'avülsiyon'), ('çocuklarda', 'çocuk'),
                       ('Wilson eğrisi', 'eğri'), ('Bennett açısı', 'açı')]:
        assert has_term(n(text), term)
