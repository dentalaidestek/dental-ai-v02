"""Dependency-free behavioral checks for local dental retrieval semantics.

These cases protect the semantic bridges that embeddings used to provide.
The benchmark intentionally tests query construction rather than a live DB so
CI remains fast and deterministic.
"""
from pathlib import Path
import ast
from app.dental_query_intent import classify_dental_intent
from app.dental_knowledge_graph import graph_expansion_terms

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "app/study_retrieval_v2.py").read_text(encoding="utf-8")
tree = ast.parse(source)

terms_source = (ROOT / "app/dental_retrieval_terms.py").read_text(encoding="utf-8")
terms_ns = {}
exec(compile(terms_source, "<dental-terms>", "exec"), terms_ns)
wanted = {"_QUERY_NOISE_RE", "_DENTAL_NOTATION_RULES"}
namespace = {"re": __import__("re"), "classify_dental_intent": classify_dental_intent, "graph_expansion_terms": graph_expansion_terms}
namespace["DENTAL_ALIAS_GROUPS"] = terms_ns["DENTAL_ALIAS_GROUPS"]
namespace["_DENTAL_CONCEPT_GROUPS"] = terms_ns["DENTAL_ALIAS_GROUPS"]
for node in tree.body:
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        names = []
        if isinstance(node, ast.Assign):
            names = [x.id for x in node.targets if isinstance(x, ast.Name)]
        elif isinstance(node.target, ast.Name):
            names = [node.target.id]
        if any(name in wanted for name in names):
            exec(compile(ast.Module(body=[node], type_ignores=[]), "<retrieval-data>", "exec"), namespace)
    elif isinstance(node, ast.FunctionDef) and node.name in {
        "_normalize_dental_notation", "_query_term_present", "_concept_alternatives", "_retrieval_terms", "_fts_query"
    }:
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<retrieval-fn>", "exec"), namespace)

cases = [
    ("alt çenenin geriliğini anlat", ("mandibular retrognati", "retrognati")),
    ("çene eklemi bozuklukları", ("TME", "TMJ", "temporomandibular")),
    ("kanal tedavisi nedir", ("endodonti", "root canal")),
    ("yirmi yaş dişi komplikasyonları", ("third molar", "üçüncü molar")),
    ("derin kapanış nedir", ("deep bite", "overbite")),
    ("kök ucu lezyonu", ("apikal", "periapikal")),
    ("diş eti hastalıkları", ("gingiva", "gingival")),
    ("aljinat özelliklerini açıkla", ("alginate", "irreversible hydrocolloid")),
    ("çalışma boyu nasıl belirlenir", ("working length", "WL")),
    ("sondalama derinliği nedir", ("probing depth", "PD")),
    ("klinik ataşman kaybı", ("clinical attachment loss", "CAL")),
    ("inferior alveolar sinir", ("IAN",)),
    ("dikey boyut nedir", ("VDO", "vertical dimension")),
    ("sentrik ilişki", ("centric relation", "CR")),
    ("panoramik radyografi", ("OPG", "orthopantomogram")),
    ("erken çocukluk çağı çürüğü", ("ECC",)),
]
for query, expected_any in cases:
    broad = namespace["_fts_query"](query, broad=True)
    assert " OR " in broad, (query, broad)
    assert any(term.casefold() in broad.casefold() for term in expected_any), (query, broad)

precise = namespace["_fts_query"]("ANB açısı kaçtır?", broad=False)
assert "kaçtır" not in precise.casefold()
assert "ANB".casefold() in precise.casefold()

# Broad mode must retain the original concept as well as alternatives.
broad = namespace["_fts_query"]("çürük nedir?", broad=True)
assert "çürük" in broad.casefold()
assert "karies" in broad.casefold() or "caries" in broad.casefold()

print("Academic V2 dental retrieval behavior: OK")


assert namespace["_normalize_dental_notation"]("A-N-B açısı") == "ANB açısı"
assert namespace["_normalize_dental_notation"]("Go-Gn düzlemi") == "GoGn düzlemi"
assert namespace["_normalize_dental_notation"]("sınıf 2 maloklüzyon") == "sınıf 2 maloklüzyon"
# Short aliases must not match inside unrelated words.
assert "CR" not in namespace["_concept_alternatives"]("screen görüntüsü")
assert "PD" not in namespace["_concept_alternatives"]("rapidly ilerleyen")


# Multi-evidence planning must stay bounded and intent-aware.
source = Path("app/study_retrieval_v2.py").read_text(encoding="utf-8")
assert "def _evidence_queries" in source
assert "max_queries: int = 4" in source
assert "def _coverage_select" in source
assert "candidate_target = max(limit * 4, 24)" in source
assert "if len(rows) < max(limit, 6):" in source
assert "rows = _coverage_select(resolved, rows, limit=limit)" in source


# Latency guard: simple factual questions stay on one-pass retrieval.
assert '_FAST_INTENTS = {"value", "definition", "measurement"}' in source
assert "def _needs_multi_evidence" in source
assert "coverage < 0.34" in source
assert "At most one extra local DB query" in source


# Multi-query reranking must not treat append order as lexical relevance.
assert "raw_lexical = float(row[9] or 0.0)" in source
assert "subject_alignment = _subject_alignment_score" in source
assert "(0.42 * lexical)" in source
assert "aligned or candidates" in source

# Neighbor rows must keep the same chunk-index/semantic metadata tail as FTS rows.
assert "hybrid_score, chunk_index, semantic_json" in source


# Sufficiency must consume the same persisted dental semantic fingerprint used
# by indexing/reranking, not only generic facet words.
assert "class EvidenceSufficiency" in source
assert "def _row_semantic_features" in source
assert "meta.get(\"nodes\")" in source
assert "meta.get(\"specialties\")" in source
assert "meta.get(\"measurements\")" in source
assert "meta.get(\"teeth\")" in source
assert "meta.get(\"imaging\")" in source
assert '"indication": ("endikasyon", "kullanım", "durum")' in source
assert '"contraindication": ("kontrendikasyon", "sakınca", "kullanılmaz")' in source

assert "if len(row) > 14 and row[-1]:" in source
assert "json.loads(row[-1])" in source
assert "row[14]" not in source


def test_extended_dental_semantic_vocabulary_is_query_matchable():
    from app.dental_knowledge_graph import matched_nodes

    cases = {
        "MRONJ nedir": "mronj",
        "NaOCl irrigasyonda": "sodium_hypochlorite",
        "Kennedy classification": "kennedy_classification",
        "MIH bulguları": "mih",
        "IANB tekniği": "ianb",
        "OSCC özellikleri": "oscc",
    }
    for query, expected in cases.items():
        assert expected in {node.id for node in matched_nodes(query)}


def test_extended_cross_discipline_dental_terms_are_matchable():
    from app.dental_knowledge_graph import matched_nodes

    cases = {
        "Hertwig epitel kök kını ne yapar": "hertwig_root_sheath",
        "DMFT indeksi": "dmft",
        "ICDAS sınıflaması": "icdas",
        "lityum disilikat özellikleri": "lithium_disilicate",
        "bisfosfonat kullanan hasta": "bisphosphonate",
        "Miller mobility sınıflaması": "mobility_grade",
        "PAI nedir": "periapical_index",
    }
    for query, expected in cases.items():
        assert expected in {node.id for node in matched_nodes(query)}


def test_dental_graph_has_unique_canonical_ids_and_merged_aliases():
    from app.dental_knowledge_graph import ALL_NODES

    ids = [node.id for node in ALL_NODES]
    assert len(ids) == len(set(ids))
    by_id = {node.id: node for node in ALL_NODES}
    # Existing canonical nodes survive vocabulary enrichment; aliases are merged.
    assert "bitewing" in by_id
    assert "interproximal radiograph" in by_id["bitewing"].aliases
    assert "biodentine" in by_id
