"""Benchmark term checks must distinguish inflection from arbitrary substrings."""
from scripts.benchmark_multiturn_continuity_50k import has_term, n


def test_term_boundaries_and_nominal_inflections():
    for text, term in [('lütfen', 'Le'), ('table', 'Le'),
                       ('irreversible', 'reversible'), ('çocukça', 'çocuk')]:
        assert not has_term(n(text), term)
    for text, term in [('avülsiyonu', 'avülsiyon'), ('çocuklarda', 'çocuk'),
                       ('Wilson eğrisi', 'eğri'), ('Bennett açısı', 'açı')]:
        assert has_term(n(text), term)


def test_negated_normalized_format_is_not_inherited_format():
    from types import SimpleNamespace
    from unittest.mock import patch
    from scripts.benchmark_multiturn_continuity_50k import score
    case = SimpleNamespace(query='taaabloo olmasın normal anlat',
        history=(('user', 'gingivitis anlat'), ('user', 'tablo şeklinde anlat')),
        expected={'format': None}, must=('gingivitis',), must_not=())
    assert score(case)[0]
    with patch('scripts.benchmark_multiturn_continuity_50k.resolve_followup_query',
               return_value='gingivitis tablo şeklinde — tablo olmasın normal anlat'):
        assert score(case)[1] == 'stale_format'
